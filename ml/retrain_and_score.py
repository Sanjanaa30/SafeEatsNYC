"""Retrain the selected model on mature history and score current restaurants."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3
import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from scipy import sparse
from sklearn.linear_model import LogisticRegression

from ml.calibration import PlattCalibratedModel
from ml.compare_xgboost import model as xgboost_model
from ml.prepare_training_data import (
    CATEGORICAL_FEATURES,
    MODEL_FEATURES,
    NUMERIC_FEATURES,
)
from ml.train_logistic_regression import risk_categories, select_risk_thresholds
from ml.tune_calibrate_logistic import date_folds, load_numpy, load_rows, load_sparse

DOHMH_ACTIVE_RESTAURANTS_URL = "https://data.cityofnewyork.us/resource/43nn-pn8j.json"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preparation-run-id", required=True)
    parser.add_argument("--comparison-run-id", required=True)
    parser.add_argument("--final-model-run-id", required=True)
    parser.add_argument("--score-run-id", required=True)
    parser.add_argument("--mature-through-date", default="2026-07-31")
    parser.add_argument(
        "--current-feature-table", default="safeeats_gold.ml_current_features"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace this exact run after correcting an incomplete or invalid artifact.",
    )
    return parser.parse_args()


def read(s3, bucket: str, key: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def upload(s3, bucket: str, key: str, body: bytes, content_type: str) -> None:
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType=content_type)


def wait_for_athena(client, query_id: str) -> None:
    while True:
        status = client.get_query_execution(QueryExecutionId=query_id)[
            "QueryExecution"
        ]["Status"]
        if status["State"] == "SUCCEEDED":
            return
        if status["State"] in {"FAILED", "CANCELLED"}:
            raise RuntimeError(status.get("StateChangeReason", "Athena query failed."))
        time.sleep(1)


def read_current_features(
    client, table: str, workgroup: str, output: str
) -> pd.DataFrame:
    query = client.start_query_execution(
        QueryString=f"SELECT * FROM {table} ORDER BY camis",
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": output},
    )["QueryExecutionId"]
    wait_for_athena(client, query)
    columns = None
    records = []
    paginator = client.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=query):
        if columns is None:
            columns = [
                item["Name"]
                for item in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            ]
        for row in page["ResultSet"]["Rows"]:
            values = [item.get("VarCharValue") for item in row["Data"]]
            if values != columns:
                records.append(values + [None] * (len(columns) - len(values)))
    return pd.DataFrame(records, columns=columns)


def read_active_restaurant_ids() -> set[str]:
    """Read the current official DOHMH population before producing predictions."""
    query = urllib.parse.urlencode(
        {
            "$select": "camis",
            "$group": "camis",
            "$order": "camis",
            "$limit": "50000",
        }
    )
    request = urllib.request.Request(f"{DOHMH_ACTIVE_RESTAURANTS_URL}?{query}")
    app_token = os.getenv("NYC_OPEN_DATA_APP_TOKEN")
    if app_token:
        request.add_header("X-App-Token", app_token)
    with urllib.request.urlopen(request, timeout=90) as response:
        rows = json.load(response)
    active_ids = {str(row["camis"]) for row in rows if row.get("camis")}
    if len(active_ids) < 20_000:
        raise RuntimeError(
            "The official DOHMH active-restaurant snapshot was unexpectedly small; "
            "refusing to publish incomplete predictions."
        )
    return active_ids


def convert_current_features(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    boolean_values = {"true": 1.0, "false": 0.0, "1": 1.0, "0": 0.0}
    boolean_columns = {
        "previous_inspection_had_critical_violation",
        "historical_grades_consistent",
        "latest_score_worsened",
    }
    for column in NUMERIC_FEATURES:
        if column in boolean_columns:
            frame[column] = frame[column].str.lower().map(boolean_values)
        else:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in CATEGORICAL_FEATURES:
        frame[column] = frame[column].replace({None: np.nan})
    return frame


def fit_oof_calibrated_model(
    features, labels: np.ndarray, dates: pd.Series, parameters: dict
):
    oof_probabilities = []
    oof_labels = []
    for train_mask, validation_mask in date_folds(dates, splits=5):
        fold_model = xgboost_model(parameters)
        fold_model.fit(features[train_mask], labels[train_mask])
        oof_probabilities.append(
            fold_model.predict_proba(features[validation_mask])[:, 1]
        )
        oof_labels.append(labels[validation_mask])

    raw_oof = np.concatenate(oof_probabilities)
    calibration_labels = np.concatenate(oof_labels)
    calibrator = LogisticRegression(max_iter=2000)
    calibrator.fit(PlattCalibratedModel.logits(raw_oof), calibration_labels)

    final_base_model = xgboost_model(parameters)
    final_base_model.fit(features, labels)
    calibrated_model = PlattCalibratedModel(final_base_model, calibrator)
    calibrated_oof = calibrator.predict_proba(PlattCalibratedModel.logits(raw_oof))[
        :, 1
    ]
    return calibrated_model, calibrated_oof, calibration_labels


def readable_feature(name: str) -> str:
    return name.replace("numeric__", "").replace("categorical__", "").replace("_", " ")


def contributing_factors(
    base_model, features, feature_names: list[str], count: int = 3
) -> list[str]:
    contributions = base_model.get_booster().predict(
        xgb.DMatrix(features), pred_contribs=True
    )[:, :-1]
    results = []
    for row in contributions:
        positive = np.where(row > 0)[0]
        ranked = positive[np.argsort(row[positive])[::-1]][:count]
        factors = [
            {
                "feature": readable_feature(feature_names[index]),
                "contribution": round(float(row[index]), 6),
            }
            for index in ranked
        ]
        results.append(json.dumps(factors))
    return results


def model_bytes(value) -> bytes:
    buffer = io.BytesIO()
    joblib.dump(value, buffer)
    return buffer.getvalue()


def main() -> None:
    load_dotenv()
    selected = arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    workgroup = os.getenv("ATHENA_WORKGROUP", "primary")
    athena_output = os.getenv(
        "ATHENA_OUTPUT_LOCATION", f"s3://{bucket}/athena/ml-query-results/"
    )
    session = boto3.Session(profile_name=profile, region_name=region)
    s3 = session.client("s3")
    athena = session.client("athena")
    prepared = f"ml/prepared/run_id={selected.preparation_run_id}"
    comparison_key = f"ml/model_comparisons/run_id={selected.comparison_run_id}/comparison_report.json"
    final_key = f"ml/final_models/run_id={selected.final_model_run_id}"
    score_key = f"ml/current_scores/run_id={selected.score_run_id}"

    for marker in [
        f"{final_key}/training_report.json",
        f"{score_key}/scoring_report.json",
    ]:
        try:
            s3.head_object(Bucket=bucket, Key=marker)
        except ClientError as error:
            if error.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
                raise
        else:
            if selected.replace:
                continue
            raise FileExistsError(f"Output already exists: s3://{bucket}/{marker}")

    comparison = json.loads(read(s3, bucket, comparison_key))
    if comparison["selected_model"] != "xgboost":
        raise ValueError("The comparison report did not select XGBoost.")
    parameters = comparison["xgboost_details"]["tuning"]["best_parameters"]

    x_train = load_sparse(s3, bucket, f"{prepared}/X_train.npz")
    y_train = load_numpy(s3, bucket, f"{prepared}/y_train.npy")
    train_rows = load_rows(s3, bucket, f"{prepared}/train_rows.csv.gz")
    x_test = load_sparse(s3, bucket, f"{prepared}/X_test.npz")
    y_test = load_numpy(s3, bucket, f"{prepared}/y_test.npy")
    test_rows = load_rows(s3, bucket, f"{prepared}/test_rows.csv.gz")
    mature = (
        test_rows["target_inspection_date"]
        <= pd.Timestamp(selected.mature_through_date)
    ).to_numpy()

    historical_x = sparse.vstack([x_train, x_test[mature]], format="csr")
    historical_y = np.concatenate([y_train, y_test[mature]])
    historical_dates = pd.concat(
        [
            train_rows["target_inspection_date"],
            test_rows.loc[mature, "target_inspection_date"],
        ],
        ignore_index=True,
    )
    calibrated_model, oof_probabilities, oof_labels = fit_oof_calibrated_model(
        historical_x, historical_y, historical_dates, parameters
    )
    moderate, high = select_risk_thresholds(oof_labels, oof_probabilities)

    preprocessor = joblib.load(
        io.BytesIO(read(s3, bucket, f"{prepared}/preprocessor.joblib"))
    )
    feature_names = json.loads(read(s3, bucket, f"{prepared}/feature_names.json"))
    current = convert_current_features(
        read_current_features(
            athena, selected.current_feature_table, workgroup, athena_output
        )
    )
    warehouse_eligible_count = len(current)
    active_restaurant_ids = read_active_restaurant_ids()
    current = current[current["camis"].astype(str).isin(active_restaurant_ids)].copy()
    if current.empty:
        raise RuntimeError(
            "No current feature rows matched the official DOHMH snapshot."
        )
    current_x = preprocessor.transform(current[MODEL_FEATURES])
    probabilities = calibrated_model.predict_proba(current_x)[:, 1]
    categories = risk_categories(probabilities, moderate, high)
    scoring_timestamp = datetime.now(timezone.utc).isoformat()

    scores = current[
        ["camis", "restaurant_key", "restaurant_name", "address", "scoring_date"]
    ].copy()
    scores = scores.rename(columns={"camis": "restaurant_id"})
    scores["risk_probability"] = probabilities
    scores["risk_category"] = categories
    scores["main_contributing_factors"] = contributing_factors(
        calibrated_model.base_model, current_x, feature_names
    )
    scores["model_version"] = selected.final_model_run_id
    scores["scoring_timestamp"] = scoring_timestamp

    category_counts = scores["risk_category"].value_counts().to_dict()
    training_report = {
        "status": "SUCCESS",
        "selected_model": "xgboost",
        "selection_report": f"s3://{bucket}/{comparison_key}",
        "final_model_run_id": selected.final_model_run_id,
        "mature_through_date": selected.mature_through_date,
        "historical_rows_used": int(len(historical_y)),
        "historical_grade_bc_rows": int(historical_y.sum()),
        "best_parameters": parameters,
        "calibration": "Platt sigmoid fitted to chronological out-of-fold predictions",
        "thresholds": {
            "moderate": round(float(moderate), 6),
            "high": round(float(high), 6),
        },
        "completed_at": scoring_timestamp,
        "model_path": f"s3://{bucket}/{final_key}/model_bundle.joblib",
    }
    scoring_report = {
        "status": "SUCCESS",
        "score_run_id": selected.score_run_id,
        "model_version": selected.final_model_run_id,
        "scoring_timestamp": scoring_timestamp,
        "eligible_restaurants_scored": int(len(scores)),
        "warehouse_eligible_restaurants": int(warehouse_eligible_count),
        "inactive_restaurants_excluded": int(warehouse_eligible_count - len(scores)),
        "active_population_source": DOHMH_ACTIVE_RESTAURANTS_URL,
        "risk_category_counts": {
            key: int(value) for key, value in category_counts.items()
        },
        "mean_risk_probability": round(float(probabilities.mean()), 6),
        "output_path": f"s3://{bucket}/{score_key}/current_restaurant_risk_scores.parquet",
    }
    bundle = {
        "model": calibrated_model,
        "preprocessor": preprocessor,
        "feature_names": feature_names,
        "moderate_threshold": moderate,
        "high_threshold": high,
        "model_version": selected.final_model_run_id,
        "mature_through_date": selected.mature_through_date,
    }
    parquet = io.BytesIO()
    scores.to_parquet(parquet, index=False)
    artifacts = {
        f"{final_key}/model_bundle.joblib": (
            model_bytes(bundle),
            "application/octet-stream",
        ),
        f"{final_key}/training_report.json": (
            json.dumps(training_report, indent=2).encode("utf-8"),
            "application/json",
        ),
        f"{score_key}/current_restaurant_risk_scores.parquet": (
            parquet.getvalue(),
            "application/vnd.apache.parquet",
        ),
        f"{score_key}/current_restaurant_risk_scores.csv.gz": (
            gzip.compress(scores.to_csv(index=False).encode("utf-8")),
            "application/gzip",
        ),
        f"{score_key}/scoring_report.json": (
            json.dumps(scoring_report, indent=2).encode("utf-8"),
            "application/json",
        ),
    }
    for key, (body, content_type) in artifacts.items():
        upload(s3, bucket, key, body, content_type)
    print(
        json.dumps({"training": training_report, "scoring": scoring_report}, indent=2)
    )


if __name__ == "__main__":
    main()
