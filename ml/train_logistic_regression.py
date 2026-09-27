"""Train and evaluate the first SafeEats logistic-regression baseline."""

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
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation-run-id", required=True)
    parser.add_argument("--model-run-id", required=True)
    parser.add_argument(
        "--threshold-validation-start-date",
        default="2026-01-01",
        help="Late-training date used to select risk thresholds.",
    )
    parser.add_argument("--prepared-prefix", default="ml/prepared")
    parser.add_argument("--model-prefix", default="ml/models/logistic_regression")
    return parser.parse_args()


def read_object(s3, bucket: str, key: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def upload_object(s3, bucket: str, key: str, body: bytes, content_type: str) -> None:
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


def load_numpy(s3, bucket: str, key: str) -> np.ndarray:
    return np.load(io.BytesIO(read_object(s3, bucket, key)), allow_pickle=False)


def load_sparse(s3, bucket: str, key: str):
    return sparse.load_npz(io.BytesIO(read_object(s3, bucket, key)))


def load_metadata(s3, bucket: str, key: str) -> pd.DataFrame:
    content = gzip.decompress(read_object(s3, bucket, key))
    frame = pd.read_csv(io.BytesIO(content))
    frame["target_inspection_date"] = pd.to_datetime(frame["target_inspection_date"])
    return frame


def classification_metrics(
    labels: np.ndarray, probabilities: np.ndarray, threshold: float
) -> dict:
    predictions = (probabilities >= threshold).astype(np.int8)
    tn, fp, fn, tp = confusion_matrix(labels, predictions, labels=[0, 1]).ravel()
    return {
        "threshold": round(float(threshold), 6),
        "precision": round(
            float(precision_score(labels, predictions, zero_division=0)), 6
        ),
        "recall": round(float(recall_score(labels, predictions, zero_division=0)), 6),
        "f1": round(float(f1_score(labels, predictions, zero_division=0)), 6),
        "confusion_matrix": {
            "true_negative": int(tn),
            "false_positive": int(fp),
            "false_negative": int(fn),
            "true_positive": int(tp),
        },
    }


MINIMUM_HIGH_RISK_PRECISION = 0.35


def select_risk_thresholds(
    labels: np.ndarray, probabilities: np.ndarray
) -> tuple[float, float]:
    precision, recall, thresholds = precision_recall_curve(labels, probabilities)
    if len(thresholds) == 0:
        raise ValueError("Threshold validation produced no candidate thresholds.")

    candidate_precision = precision[:-1]
    candidate_recall = recall[:-1]
    f1 = np.divide(
        2 * candidate_precision * candidate_recall,
        candidate_precision + candidate_recall,
        out=np.zeros_like(candidate_precision),
        where=(candidate_precision + candidate_recall) > 0,
    )
    f1_high_index = int(np.argmax(f1))
    high_index = f1_high_index
    precision_candidates = np.where(
        (candidate_precision >= MINIMUM_HIGH_RISK_PRECISION)
        & (thresholds >= thresholds[f1_high_index])
        & (candidate_recall > 0)
    )[0]
    if len(precision_candidates):
        # The first eligible threshold is the least restrictive one that meets
        # the precision floor, preserving as much recall as possible.
        high_index = int(precision_candidates[0])
    high = float(thresholds[high_index])

    moderate_candidates = np.where((candidate_recall >= 0.80) & (thresholds < high))[0]
    if len(moderate_candidates):
        best_precision = candidate_precision[moderate_candidates].max()
        best = moderate_candidates[
            np.where(candidate_precision[moderate_candidates] == best_precision)[0]
        ]
        moderate = float(thresholds[int(best[-1])])
    else:
        moderate = max(0.0, high / 2)

    if not 0 <= moderate < high <= 1:
        raise ValueError(f"Invalid risk thresholds: moderate={moderate}, high={high}")
    return moderate, high


def risk_categories(
    probabilities: np.ndarray, moderate: float, high: float
) -> np.ndarray:
    return np.select(
        [probabilities >= high, probabilities >= moderate],
        ["HIGH", "MODERATE"],
        default="LOW",
    )


def risk_tier_summary(labels: np.ndarray, categories: np.ndarray) -> dict:
    result = {}
    for category in ["LOW", "MODERATE", "HIGH"]:
        selected = labels[categories == category]
        result[category] = {
            "rows": int(len(selected)),
            "actual_grade_bc_rows": int(selected.sum()),
            "actual_grade_bc_rate": round(float(selected.mean()), 6)
            if len(selected)
            else None,
        }
    return result


def calibration_summary(
    labels: np.ndarray, probabilities: np.ndarray
) -> tuple[dict, pd.DataFrame]:
    observed, predicted = calibration_curve(
        labels, probabilities, n_bins=10, strategy="quantile"
    )
    bins = pd.DataFrame(
        {
            "mean_predicted_probability": predicted,
            "observed_grade_bc_rate": observed,
        }
    )
    return (
        {
            "brier_score": round(float(brier_score_loss(labels, probabilities)), 6),
            "log_loss": round(float(log_loss(labels, probabilities, labels=[0, 1])), 6),
            "mean_predicted_probability": round(float(probabilities.mean()), 6),
            "observed_grade_bc_rate": round(float(labels.mean()), 6),
            "calibration_bins": int(len(bins)),
        },
        bins,
    )


def joblib_bytes(value) -> bytes:
    buffer = io.BytesIO()
    joblib.dump(value, buffer)
    return buffer.getvalue()


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
    x_test = load_sparse(s3, bucket, f"{prepared_key}/X_test.npz")
    y_train = load_numpy(s3, bucket, f"{prepared_key}/y_train.npy")
    y_test = load_numpy(s3, bucket, f"{prepared_key}/y_test.npy")
    train_rows = load_metadata(s3, bucket, f"{prepared_key}/train_rows.csv.gz")
    test_rows = load_metadata(s3, bucket, f"{prepared_key}/test_rows.csv.gz")
    feature_names = json.loads(
        read_object(s3, bucket, f"{prepared_key}/feature_names.json")
    )
    preprocessor = joblib.load(
        io.BytesIO(read_object(s3, bucket, f"{prepared_key}/preprocessor.joblib"))
    )

    validation_start = pd.Timestamp(arguments.threshold_validation_start_date)
    development_mask = (
        train_rows["target_inspection_date"] < validation_start
    ).to_numpy()
    validation_mask = ~development_mask
    if not development_mask.any() or not validation_mask.any():
        raise ValueError(
            "Threshold-validation date produced an empty development or validation set."
        )

    threshold_model = LogisticRegression(max_iter=2000, solver="lbfgs")
    threshold_model.fit(x_train[development_mask], y_train[development_mask])
    validation_probabilities = threshold_model.predict_proba(x_train[validation_mask])[
        :, 1
    ]
    moderate_threshold, high_threshold = select_risk_thresholds(
        y_train[validation_mask], validation_probabilities
    )

    model = LogisticRegression(max_iter=2000, solver="lbfgs")
    model.fit(x_train, y_train)
    test_probabilities = model.predict_proba(x_test)[:, 1]
    test_categories = risk_categories(
        test_probabilities, moderate_threshold, high_threshold
    )

    calibration, calibration_bins = calibration_summary(y_test, test_probabilities)
    default_metrics = classification_metrics(y_test, test_probabilities, 0.5)
    high_risk_metrics = classification_metrics(
        y_test, test_probabilities, high_threshold
    )

    coefficients = pd.DataFrame(
        {"feature": feature_names, "coefficient": model.coef_[0]}
    )
    coefficients["absolute_coefficient"] = coefficients["coefficient"].abs()
    coefficients = coefficients.sort_values("absolute_coefficient", ascending=False)

    predictions = test_rows.copy()
    predictions["risk_probability"] = test_probabilities
    predictions["risk_category"] = test_categories

    model_bundle = {
        "model": model,
        "preprocessor": preprocessor,
        "feature_names": feature_names,
        "moderate_threshold": moderate_threshold,
        "high_threshold": high_threshold,
        "preparation_run_id": arguments.preparation_run_id,
        "model_run_id": arguments.model_run_id,
    }

    report = {
        "status": "SUCCESS",
        "model_type": "logistic_regression",
        "model_run_id": arguments.model_run_id,
        "preparation_run_id": arguments.preparation_run_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "training": {
            "rows": int(len(y_train)),
            "grade_a_rows": int(len(y_train) - y_train.sum()),
            "grade_bc_rows": int(y_train.sum()),
            "grade_bc_rate": round(float(y_train.mean()), 6),
            "class_weight": None,
        },
        "threshold_validation": {
            "start_date": validation_start.date().isoformat(),
            "development_rows": int(development_mask.sum()),
            "validation_rows": int(validation_mask.sum()),
            "validation_grade_bc_rows": int(y_train[validation_mask].sum()),
            "moderate_rule": "Validation threshold with recall >= 0.80 and highest precision below the high threshold.",
            "high_rule": "Validation threshold that maximizes F1.",
        },
        "test": {
            "rows": int(len(y_test)),
            "grade_a_rows": int(len(y_test) - y_test.sum()),
            "grade_bc_rows": int(y_test.sum()),
            "grade_bc_rate": round(float(y_test.mean()), 6),
            "roc_auc": round(float(roc_auc_score(y_test, test_probabilities)), 6),
            "average_precision": round(
                float(average_precision_score(y_test, test_probabilities)), 6
            ),
            "default_0_5_metrics": default_metrics,
            "high_risk_metrics": high_risk_metrics,
            "calibration": calibration,
            "risk_tiers": risk_tier_summary(y_test, test_categories),
        },
        "risk_thresholds": {
            "LOW": f"probability < {moderate_threshold:.6f}",
            "MODERATE": f"{moderate_threshold:.6f} <= probability < {high_threshold:.6f}",
            "HIGH": f"probability >= {high_threshold:.6f}",
            "moderate_threshold": round(moderate_threshold, 6),
            "high_threshold": round(high_threshold, 6),
        },
        "leakage_controls": {
            "model_uses_prepared_feature_matrix_only": True,
            "test_labels_not_used_for_model_fitting": True,
            "test_labels_not_used_for_threshold_selection": True,
            "thresholds_selected_from_late_training_period": True,
        },
        "output_path": f"s3://{bucket}/{model_key}",
    }

    artifacts = {
        "model_bundle.joblib": (joblib_bytes(model_bundle), "application/octet-stream"),
        "test_predictions.csv.gz": (
            gzip.compress(predictions.to_csv(index=False).encode("utf-8")),
            "application/gzip",
        ),
        "feature_coefficients.csv": (
            coefficients.to_csv(index=False).encode("utf-8"),
            "text/csv",
        ),
        "calibration_bins.csv": (
            calibration_bins.to_csv(index=False).encode("utf-8"),
            "text/csv",
        ),
        "risk_thresholds.json": (
            json.dumps(report["risk_thresholds"], indent=2).encode("utf-8"),
            "application/json",
        ),
    }
    for name, (body, content_type) in artifacts.items():
        upload_object(s3, bucket, f"{model_key}/{name}", body, content_type)

    report_bytes = json.dumps(report, indent=2).encode("utf-8")
    upload_object(
        s3,
        bucket,
        f"{model_key}/evaluation_report.json",
        report_bytes,
        "application/json",
    )
    print(report_bytes.decode("utf-8"))


if __name__ == "__main__":
    main()
