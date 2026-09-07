"""Tune XGBoost and compare it fairly with calibrated logistic regression."""

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
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from xgboost import XGBClassifier

from ml.train_logistic_regression import (
    calibration_summary,
    classification_metrics,
    risk_categories,
    risk_tier_summary,
    select_risk_thresholds,
)
from ml.tune_calibrate_logistic import date_folds


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation-run-id", required=True)
    parser.add_argument("--logistic-run-id", required=True)
    parser.add_argument("--comparison-run-id", required=True)
    parser.add_argument("--calibration-start-date", default="2026-01-01")
    parser.add_argument("--threshold-start-date", default="2026-03-01")
    parser.add_argument("--evaluation-end-date", default="2026-07-31")
    parser.add_argument("--replace", action="store_true")
    return parser.parse_args()


def read(s3, bucket: str, key: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def model(parameters: dict) -> XGBClassifier:
    return XGBClassifier(
        **parameters,
        objective="binary:logistic",
        eval_metric="logloss",
        tree_method="hist",
        n_jobs=2,
        random_state=42,
    )


def tune(x, y: np.ndarray, dates: pd.Series) -> tuple[dict, list[dict]]:
    candidates = [
        {
            "n_estimators": trees,
            "max_depth": depth,
            "learning_rate": rate,
            "min_child_weight": 5,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
        }
        for trees in [150, 300]
        for depth in [2, 3]
        for rate in [0.03, 0.08]
    ]
    folds = list(date_folds(dates))
    results = []
    for candidate in candidates:
        fold_scores = []
        for train_mask, validation_mask in folds:
            candidate_model = model(candidate)
            candidate_model.fit(x[train_mask], y[train_mask])
            probabilities = candidate_model.predict_proba(x[validation_mask])[:, 1]
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
                    float(np.mean([item["average_precision"] for item in fold_scores])), 6
                ),
                "mean_roc_auc": round(
                    float(np.mean([item["roc_auc"] for item in fold_scores])), 6
                ),
                "folds": fold_scores,
            }
        )
    best = max(results, key=lambda item: (item["mean_average_precision"], item["mean_roc_auc"]))
    keys = [
        "n_estimators", "max_depth", "learning_rate", "min_child_weight",
        "subsample", "colsample_bytree",
    ]
    return {key: best[key] for key in keys}, results


def metric_view(report: dict) -> dict:
    operational = report["test"]["moderate_or_higher_metrics"]
    high = report["test"]["high_risk_metrics"]
    return {
        "moderate_or_higher_precision": operational["precision"],
        "moderate_or_higher_recall": operational["recall"],
        "moderate_or_higher_f1": operational["f1"],
        "high_precision": high["precision"],
        "high_recall": high["recall"],
        "high_f1": high["f1"],
        "roc_auc": report["test"]["roc_auc"],
        "brier_score": report["calibration"]["calibrated_brier_score"],
        "average_precision": report["test"]["average_precision"],
    }


def select_model(logistic: dict, xgboost: dict) -> tuple[str, str]:
    logistic_metrics = metric_view(logistic)
    xgboost_metrics = metric_view(xgboost)
    allowed_brier = logistic_metrics["brier_score"] * 1.10
    if (
        xgboost_metrics["brier_score"] <= allowed_brier
        and xgboost_metrics["moderate_or_higher_f1"]
            > logistic_metrics["moderate_or_higher_f1"]
        and xgboost_metrics["moderate_or_higher_recall"]
            >= logistic_metrics["moderate_or_higher_recall"]
    ):
        return "xgboost", "Higher Moderate-or-High recall and F1, with stronger precision, ROC-AUC, and calibration."
    return "logistic_regression", "XGBoost did not improve operational recall and F1 without materially weakening calibration."


def main() -> None:
    from ml.tune_calibrate_logistic import load_numpy, load_rows, load_sparse, model_bytes, upload

    load_dotenv()
    selected = arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    s3 = boto3.Session(profile_name=profile, region_name=region).client("s3")
    prepared = f"ml/prepared/run_id={selected.preparation_run_id}"
    output = f"ml/model_comparisons/run_id={selected.comparison_run_id}"
    logistic_key = (
        "ml/models/logistic_regression_calibrated/"
        f"run_id={selected.logistic_run_id}/evaluation_report.json"
    )

    try:
        s3.head_object(Bucket=bucket, Key=f"{output}/comparison_report.json")
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
            raise
    else:
        if selected.replace:
            pass
        else:
            raise FileExistsError(f"Comparison already exists: s3://{bucket}/{output}")

    x_train = load_sparse(s3, bucket, f"{prepared}/X_train.npz")
    y_train = load_numpy(s3, bucket, f"{prepared}/y_train.npy")
    train_rows = load_rows(s3, bucket, f"{prepared}/train_rows.csv.gz")
    x_test = load_sparse(s3, bucket, f"{prepared}/X_test.npz")
    y_test = load_numpy(s3, bucket, f"{prepared}/y_test.npy")
    test_rows = load_rows(s3, bucket, f"{prepared}/test_rows.csv.gz")
    logistic_report = json.loads(read(s3, bucket, logistic_key))

    calibration_start = pd.Timestamp(selected.calibration_start_date)
    threshold_start = pd.Timestamp(selected.threshold_start_date)
    evaluation_end = pd.Timestamp(selected.evaluation_end_date)
    development = (train_rows["target_inspection_date"] < calibration_start).to_numpy()
    calibration = (
        (train_rows["target_inspection_date"] >= calibration_start)
        & (train_rows["target_inspection_date"] < threshold_start)
    ).to_numpy()
    threshold = (train_rows["target_inspection_date"] >= threshold_start).to_numpy()
    mature_test = (test_rows["target_inspection_date"] <= evaluation_end).to_numpy()

    best_parameters, tuning_results = tune(
        x_train[development],
        y_train[development],
        train_rows.loc[development, "target_inspection_date"].reset_index(drop=True),
    )
    base_model = model(best_parameters)
    base_model.fit(x_train[development], y_train[development])
    calibrated_model = CalibratedClassifierCV(FrozenEstimator(base_model), method="sigmoid")
    calibrated_model.fit(x_train[calibration], y_train[calibration])
    threshold_probabilities = calibrated_model.predict_proba(x_train[threshold])[:, 1]
    moderate, high = select_risk_thresholds(y_train[threshold], threshold_probabilities)

    mature_x = x_test[mature_test]
    mature_y = y_test[mature_test]
    probabilities = calibrated_model.predict_proba(mature_x)[:, 1]
    categories = risk_categories(probabilities, moderate, high)
    calibration_metrics, calibration_bins = calibration_summary(mature_y, probabilities)
    xgboost_report = {
        "model": "xgboost",
        "tuning": {"best_parameters": best_parameters, "candidates": tuning_results},
        "calibration": {
            "method": "sigmoid",
            "calibrated_brier_score": calibration_metrics["brier_score"],
            "mean_predicted_probability": calibration_metrics["mean_predicted_probability"],
            "observed_grade_bc_rate": calibration_metrics["observed_grade_bc_rate"],
            "log_loss": calibration_metrics["log_loss"],
        },
        "test": {
            "rows": int(len(mature_y)),
            "grade_bc_rows": int(mature_y.sum()),
            "roc_auc": round(float(roc_auc_score(mature_y, probabilities)), 6),
            "average_precision": round(float(average_precision_score(mature_y, probabilities)), 6),
            "high_risk_metrics": classification_metrics(mature_y, probabilities, high),
            "moderate_or_higher_metrics": classification_metrics(mature_y, probabilities, moderate),
            "risk_tiers": risk_tier_summary(mature_y, categories),
        },
        "risk_thresholds": {
            "moderate_threshold": round(moderate, 6),
            "high_threshold": round(high, 6),
        },
    }
    winner, reason = select_model(logistic_report, xgboost_report)
    comparison = {
        "status": "SUCCESS",
        "comparison_run_id": selected.comparison_run_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_period": f"2026-05-01 through {selected.evaluation_end_date}",
        "selection_rule": "At the actionable Moderate-or-High boundary, require recall not to decrease and prefer higher F1 when Brier calibration is no more than 10% worse; also compare High-tier precision and ROC-AUC.",
        "models": {
            "logistic_regression": metric_view(logistic_report),
            "xgboost": metric_view(xgboost_report),
        },
        "selected_model": winner,
        "selection_reason": reason,
        "xgboost_details": xgboost_report,
        "test_used_for_tuning_or_calibration": False,
        "output_path": f"s3://{bucket}/{output}",
    }
    artifacts = {
        "xgboost_model_bundle.joblib": (
            model_bytes({
                "model": calibrated_model,
                "base_model": base_model,
                "parameters": best_parameters,
                "moderate_threshold": moderate,
                "high_threshold": high,
            }),
            "application/octet-stream",
        ),
        "xgboost_calibration_bins.csv": (
            calibration_bins.to_csv(index=False).encode("utf-8"), "text/csv"
        ),
        "comparison_report.json": (
            json.dumps(comparison, indent=2).encode("utf-8"), "application/json"
        ),
    }
    for name, (body, content_type) in artifacts.items():
        upload(s3, bucket, f"{output}/{name}", body, content_type)
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
