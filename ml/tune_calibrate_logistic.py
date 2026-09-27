"""Tune and calibrate logistic regression without using final test outcomes."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
from datetime import datetime, timezone

import boto3
import joblib
import numpy as np
import pandas as pd
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from scipy import sparse
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.model_selection import TimeSeriesSplit

from ml.train_logistic_regression import (
    calibration_summary,
    classification_metrics,
    risk_categories,
    risk_tier_summary,
    select_risk_thresholds,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation-run-id", required=True)
    parser.add_argument("--model-run-id", required=True)
    parser.add_argument("--calibration-start-date", default="2026-01-01")
    parser.add_argument("--threshold-start-date", default="2026-03-01")
    parser.add_argument(
        "--evaluation-end-date",
        default="2026-07-31",
        help="Latest sufficiently mature target date included in final metrics.",
    )
    parser.add_argument("--prepared-prefix", default="ml/prepared")
    parser.add_argument(
        "--model-prefix", default="ml/models/logistic_regression_calibrated"
    )
    return parser.parse_args()


def read_object(s3, bucket: str, key: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def load_sparse(s3, bucket: str, key: str):
    return sparse.load_npz(io.BytesIO(read_object(s3, bucket, key)))


def load_numpy(s3, bucket: str, key: str) -> np.ndarray:
    return np.load(io.BytesIO(read_object(s3, bucket, key)), allow_pickle=False)


def load_rows(s3, bucket: str, key: str) -> pd.DataFrame:
    content = gzip.decompress(read_object(s3, bucket, key))
    rows = pd.read_csv(io.BytesIO(content))
    rows["target_inspection_date"] = pd.to_datetime(rows["target_inspection_date"])
    return rows


def date_folds(dates: pd.Series, splits: int = 4):
    unique_dates = np.sort(dates.dt.normalize().unique())
    for train_dates, validation_dates in TimeSeriesSplit(n_splits=splits).split(
        unique_dates
    ):
        train_mask = dates.dt.normalize().isin(unique_dates[train_dates]).to_numpy()
        validation_mask = (
            dates.dt.normalize().isin(unique_dates[validation_dates]).to_numpy()
        )
        yield train_mask, validation_mask


def tune_logistic_regression(
    x, y: np.ndarray, dates: pd.Series
) -> tuple[dict, list[dict]]:
    candidates = [
        {"C": regularization, "class_weight": class_weight}
        for regularization in [0.01, 0.1, 1.0, 10.0]
        for class_weight in [None, "balanced"]
    ]
    results = []
    folds = list(date_folds(dates))
    for candidate in candidates:
        fold_scores = []
        for train_mask, validation_mask in folds:
            model = LogisticRegression(
                C=candidate["C"],
                class_weight=candidate["class_weight"],
                max_iter=2000,
                solver="lbfgs",
            )
            model.fit(x[train_mask], y[train_mask])
            probabilities = model.predict_proba(x[validation_mask])[:, 1]
            fold_scores.append(
                {
                    "average_precision": float(
                        average_precision_score(y[validation_mask], probabilities)
                    ),
                    "roc_auc": float(roc_auc_score(y[validation_mask], probabilities)),
                }
            )
        results.append(
            {
                **candidate,
                "mean_average_precision": round(
                    float(
                        np.mean([score["average_precision"] for score in fold_scores])
                    ),
                    6,
                ),
                "mean_roc_auc": round(
                    float(np.mean([score["roc_auc"] for score in fold_scores])), 6
                ),
                "folds": fold_scores,
            }
        )
    best = max(
        results, key=lambda item: (item["mean_average_precision"], item["mean_roc_auc"])
    )
    return {"C": best["C"], "class_weight": best["class_weight"]}, results


def model_bytes(value) -> bytes:
    buffer = io.BytesIO()
    joblib.dump(value, buffer)
    return buffer.getvalue()


def upload(s3, bucket: str, key: str, body: bytes, content_type: str) -> None:
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


def main() -> None:
    load_dotenv()
    arguments = parse_arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    prepared_key = (
        f"{arguments.prepared_prefix.strip('/')}/run_id={arguments.preparation_run_id}"
    )
    model_key = f"{arguments.model_prefix.strip('/')}/run_id={arguments.model_run_id}"
    s3 = boto3.Session(profile_name=profile, region_name=region).client("s3")

    try:
        s3.head_object(Bucket=bucket, Key=f"{model_key}/evaluation_report.json")
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
            raise
    else:
        raise FileExistsError(f"Model run already exists: s3://{bucket}/{model_key}")

    x_train = load_sparse(s3, bucket, f"{prepared_key}/X_train.npz")
    y_train = load_numpy(s3, bucket, f"{prepared_key}/y_train.npy")
    train_rows = load_rows(s3, bucket, f"{prepared_key}/train_rows.csv.gz")
    x_test = load_sparse(s3, bucket, f"{prepared_key}/X_test.npz")
    y_test = load_numpy(s3, bucket, f"{prepared_key}/y_test.npy")
    test_rows = load_rows(s3, bucket, f"{prepared_key}/test_rows.csv.gz")
    feature_names = json.loads(
        read_object(s3, bucket, f"{prepared_key}/feature_names.json")
    )
    preprocessor = joblib.load(
        io.BytesIO(read_object(s3, bucket, f"{prepared_key}/preprocessor.joblib"))
    )

    calibration_start = pd.Timestamp(arguments.calibration_start_date)
    threshold_start = pd.Timestamp(arguments.threshold_start_date)
    evaluation_end = pd.Timestamp(arguments.evaluation_end_date)
    development_mask = (
        train_rows["target_inspection_date"] < calibration_start
    ).to_numpy()
    calibration_mask = (
        (train_rows["target_inspection_date"] >= calibration_start)
        & (train_rows["target_inspection_date"] < threshold_start)
    ).to_numpy()
    threshold_mask = (
        train_rows["target_inspection_date"] >= threshold_start
    ).to_numpy()
    mature_test_mask = (
        test_rows["target_inspection_date"] <= evaluation_end
    ).to_numpy()
    immature_test_mask = ~mature_test_mask
    if not all(
        mask.any()
        for mask in [
            development_mask,
            calibration_mask,
            threshold_mask,
            mature_test_mask,
        ]
    ):
        raise ValueError("One temporal model segment is empty.")

    best_parameters, tuning_results = tune_logistic_regression(
        x_train[development_mask],
        y_train[development_mask],
        train_rows.loc[development_mask, "target_inspection_date"].reset_index(
            drop=True
        ),
    )
    base_model = LogisticRegression(
        **best_parameters,
        max_iter=2000,
        solver="lbfgs",
    )
    base_model.fit(x_train[development_mask], y_train[development_mask])

    calibrated_model = CalibratedClassifierCV(
        FrozenEstimator(base_model), method="sigmoid"
    )
    calibrated_model.fit(x_train[calibration_mask], y_train[calibration_mask])

    threshold_probabilities = calibrated_model.predict_proba(x_train[threshold_mask])[
        :, 1
    ]
    moderate_threshold, high_threshold = select_risk_thresholds(
        y_train[threshold_mask], threshold_probabilities
    )

    mature_x = x_test[mature_test_mask]
    mature_y = y_test[mature_test_mask]
    uncalibrated_probabilities = base_model.predict_proba(mature_x)[:, 1]
    calibrated_probabilities = calibrated_model.predict_proba(mature_x)[:, 1]
    categories = risk_categories(
        calibrated_probabilities, moderate_threshold, high_threshold
    )
    calibration, calibration_bins = calibration_summary(
        mature_y, calibrated_probabilities
    )

    all_test_probabilities = calibrated_model.predict_proba(x_test)[:, 1]
    all_test_categories = risk_categories(
        all_test_probabilities, moderate_threshold, high_threshold
    )
    predictions = test_rows.copy()
    predictions["risk_probability"] = all_test_probabilities
    predictions["risk_category"] = all_test_categories
    predictions["evaluation_status"] = np.where(
        mature_test_mask, "MATURE_EVALUATION", "IMMATURE_EXCLUDED"
    )

    coefficient_rows = pd.DataFrame(
        {"feature": feature_names, "coefficient": base_model.coef_[0]}
    )
    coefficient_rows["absolute_coefficient"] = coefficient_rows["coefficient"].abs()
    coefficient_rows = coefficient_rows.sort_values(
        "absolute_coefficient", ascending=False
    )

    report = {
        "status": "SUCCESS",
        "model_run_id": arguments.model_run_id,
        "preparation_run_id": arguments.preparation_run_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "label_maturation": {
            "evaluation_end_date": evaluation_end.date().isoformat(),
            "reason": "Outcomes after the maturity cutoff are excluded so recent incomplete grades do not distort evaluation.",
            "mature_test_rows": int(mature_test_mask.sum()),
            "immature_rows_excluded_from_metrics": int(immature_test_mask.sum()),
            "immature_grade_bc_rows": int(y_test[immature_test_mask].sum()),
        },
        "temporal_segments": {
            "development": {
                "rows": int(development_mask.sum()),
                "purpose": "hyperparameter tuning and base-model fitting",
            },
            "calibration": {
                "rows": int(calibration_mask.sum()),
                "purpose": "sigmoid probability calibration",
            },
            "threshold_validation": {
                "rows": int(threshold_mask.sum()),
                "purpose": "risk threshold selection",
            },
            "final_test": {
                "rows": int(mature_test_mask.sum()),
                "purpose": "one final untouched evaluation",
            },
        },
        "tuning": {
            "selection_metric": "mean chronological cross-validation average precision",
            "best_parameters": best_parameters,
            "candidates": tuning_results,
        },
        "calibration": {
            "method": "sigmoid",
            "uncalibrated_brier_score": round(
                float(brier_score_loss(mature_y, uncalibrated_probabilities)), 6
            ),
            "calibrated_brier_score": calibration["brier_score"],
            "uncalibrated_mean_probability": round(
                float(uncalibrated_probabilities.mean()), 6
            ),
            "calibrated_mean_probability": calibration["mean_predicted_probability"],
            "observed_grade_bc_rate": calibration["observed_grade_bc_rate"],
            "log_loss": calibration["log_loss"],
        },
        "test": {
            "rows": int(len(mature_y)),
            "grade_bc_rows": int(mature_y.sum()),
            "grade_bc_rate": round(float(mature_y.mean()), 6),
            "roc_auc": round(
                float(roc_auc_score(mature_y, calibrated_probabilities)), 6
            ),
            "average_precision": round(
                float(average_precision_score(mature_y, calibrated_probabilities)), 6
            ),
            "default_0_5_metrics": classification_metrics(
                mature_y, calibrated_probabilities, 0.5
            ),
            "moderate_or_higher_metrics": classification_metrics(
                mature_y, calibrated_probabilities, moderate_threshold
            ),
            "high_risk_metrics": classification_metrics(
                mature_y, calibrated_probabilities, high_threshold
            ),
            "risk_tiers": risk_tier_summary(mature_y, categories),
        },
        "risk_thresholds": {
            "moderate_threshold": round(moderate_threshold, 6),
            "high_threshold": round(high_threshold, 6),
            "LOW": f"probability < {moderate_threshold:.6f}",
            "MODERATE": f"{moderate_threshold:.6f} <= probability < {high_threshold:.6f}",
            "HIGH": f"probability >= {high_threshold:.6f}",
        },
        "leakage_controls": {
            "chronological_cross_validation": True,
            "calibration_after_development_period": True,
            "threshold_selection_after_calibration_period": True,
            "test_not_used_for_tuning_calibration_or_thresholds": True,
        },
        "output_path": f"s3://{bucket}/{model_key}",
    }

    bundle = {
        "model": calibrated_model,
        "base_model": base_model,
        "preprocessor": preprocessor,
        "feature_names": feature_names,
        "moderate_threshold": moderate_threshold,
        "high_threshold": high_threshold,
        "preparation_run_id": arguments.preparation_run_id,
        "model_run_id": arguments.model_run_id,
    }
    artifacts = {
        "model_bundle.joblib": (model_bytes(bundle), "application/octet-stream"),
        "test_predictions.csv.gz": (
            gzip.compress(predictions.to_csv(index=False).encode("utf-8")),
            "application/gzip",
        ),
        "feature_coefficients.csv": (
            coefficient_rows.to_csv(index=False).encode("utf-8"),
            "text/csv",
        ),
        "calibration_bins.csv": (
            calibration_bins.to_csv(index=False).encode("utf-8"),
            "text/csv",
        ),
        "tuning_results.json": (
            json.dumps(tuning_results, indent=2).encode("utf-8"),
            "application/json",
        ),
    }
    for name, (body, content_type) in artifacts.items():
        upload(s3, bucket, f"{model_key}/{name}", body, content_type)
    report_bytes = json.dumps(report, indent=2).encode("utf-8")
    upload(
        s3,
        bucket,
        f"{model_key}/evaluation_report.json",
        report_bytes,
        "application/json",
    )
    print(report_bytes.decode("utf-8"))


if __name__ == "__main__":
    main()
