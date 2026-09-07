"""Prepare leakage-safe, time-split model matrices from Athena Gold data."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os
import time
from datetime import datetime, timezone

import boto3
import joblib
import numpy as np
import pandas as pd
from dotenv import load_dotenv
from botocore.exceptions import ClientError
from scipy import sparse
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


NUMERIC_FEATURES = [
    "previous_score",
    "earlier_score",
    "recent_score_change",
    "days_since_last_graded_inspection",
    "previous_inspection_violation_count",
    "previous_inspection_critical_violation_count",
    "previous_inspection_had_critical_violation",
    "known_graded_inspection_count",
    "historical_violation_count",
    "historical_critical_violation_count",
    "historical_grade_a_count",
    "historical_grade_b_count",
    "historical_grade_c_count",
    "historical_grade_a_rate",
    "historical_grades_consistent",
    "prior_90d_nearby_complaint_count",
    "prior_90d_rodent_complaint_count",
    "prior_90d_food_poisoning_complaint_count",
    "prior_90d_food_establishment_complaint_count",
]

CATEGORICAL_FEATURES = ["cuisine", "borough_name", "previous_grade"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# These columns are useful for splitting or auditing, but must never enter X.
NON_PREDICTOR_COLUMNS = {
    "prediction_anchor_key",
    "target_inspection_key",
    "restaurant_key",
    "camis",
    "prediction_anchor_date",
    "target_inspection_date",
    "target_grade",
    "target_is_bc",
    "borough_key",
    "latitude",
    "longitude",
}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--test-start-date",
        default="2026-05-01",
        help="First target inspection date assigned to the test set.",
    )
    parser.add_argument("--database", default="safeeats_gold")
    parser.add_argument("--table", default="ml_training_features")
    parser.add_argument("--output-prefix", default="ml/prepared")
    return parser.parse_args()


def wait_for_query(client, query_id: str) -> None:
    while True:
        status = client.get_query_execution(QueryExecutionId=query_id)[
            "QueryExecution"
        ]["Status"]
        if status["State"] == "SUCCEEDED":
            return
        if status["State"] in {"FAILED", "CANCELLED"}:
            reason = status.get("StateChangeReason", "No reason returned")
            raise RuntimeError(f"Athena query {status['State']}: {reason}")
        time.sleep(1)


def read_athena_table(
    client,
    database: str,
    table: str,
    workgroup: str,
    query_output: str,
) -> pd.DataFrame:
    sql = f"SELECT * FROM {database}.{table} ORDER BY target_inspection_date, target_inspection_key"
    response = client.start_query_execution(
        QueryString=sql,
        QueryExecutionContext={"Database": database},
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": query_output},
    )
    query_id = response["QueryExecutionId"]
    wait_for_query(client, query_id)

    rows: list[list[str | None]] = []
    columns: list[str] | None = None
    paginator = client.get_paginator("get_query_results")
    for page in paginator.paginate(QueryExecutionId=query_id):
        if columns is None:
            columns = [
                item["Name"]
                for item in page["ResultSet"]["ResultSetMetadata"]["ColumnInfo"]
            ]
        for row in page["ResultSet"]["Rows"]:
            values = [item.get("VarCharValue") for item in row["Data"]]
            if values != columns:
                rows.append(values + [None] * (len(columns) - len(values)))

    if columns is None:
        raise RuntimeError("Athena returned no schema.")
    return pd.DataFrame(rows, columns=columns)


def convert_types(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    frame["prediction_anchor_date"] = pd.to_datetime(
        frame["prediction_anchor_date"], errors="raise"
    )
    frame["target_inspection_date"] = pd.to_datetime(
        frame["target_inspection_date"], errors="raise"
    )
    frame["target_is_bc"] = pd.to_numeric(frame["target_is_bc"], errors="raise").astype("int8")

    boolean_values = {
        "true": 1.0,
        "false": 0.0,
        "1": 1.0,
        "0": 0.0,
    }
    boolean_columns = {
        "previous_inspection_had_critical_violation",
        "historical_grades_consistent",
    }
    for column in NUMERIC_FEATURES:
        if column in boolean_columns:
            frame[column] = frame[column].str.lower().map(boolean_values)
        else:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    for column in CATEGORICAL_FEATURES:
        frame[column] = frame[column].replace({None: np.nan})
    return frame


def validate_leakage_boundary(frame: pd.DataFrame) -> None:
    missing = set(MODEL_FEATURES) - set(frame.columns)
    if missing:
        raise ValueError(f"Required model features are missing: {sorted(missing)}")

    leaked = set(MODEL_FEATURES) & NON_PREDICTOR_COLUMNS
    leaked.update(column for column in MODEL_FEATURES if column.startswith("target_"))
    if leaked:
        raise ValueError(f"Forbidden predictors found: {sorted(leaked)}")

    bad_dates = frame["prediction_anchor_date"] >= frame["target_inspection_date"]
    if bad_dates.any():
        raise ValueError(f"Found {int(bad_dates.sum())} rows with future information.")

    if not frame["target_is_bc"].isin([0, 1]).all():
        raise ValueError("The target contains values other than 0 and 1.")


def build_preprocessor() -> ColumnTransformer:
    numeric = Pipeline(
        [
            ("missing", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    categorical = Pipeline(
        [
            ("missing", SimpleImputer(strategy="constant", fill_value="UNKNOWN")),
            ("encode", OneHotEncoder(handle_unknown="ignore", dtype=np.float32)),
        ]
    )
    return ColumnTransformer(
        [("numeric", numeric, NUMERIC_FEATURES), ("categorical", categorical, CATEGORICAL_FEATURES)]
    )


def upload_bytes(s3, bucket: str, key: str, content: bytes, content_type: str) -> None:
    s3.put_object(Bucket=bucket, Key=key, Body=content, ContentType=content_type)


def numpy_bytes(values: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, values, allow_pickle=False)
    return buffer.getvalue()


def sparse_bytes(values) -> bytes:
    buffer = io.BytesIO()
    sparse.save_npz(buffer, sparse.csr_matrix(values), compressed=True)
    return buffer.getvalue()


def joblib_bytes(value) -> bytes:
    buffer = io.BytesIO()
    joblib.dump(value, buffer)
    return buffer.getvalue()


def metadata_bytes(frame: pd.DataFrame) -> bytes:
    columns = [
        "prediction_anchor_key",
        "target_inspection_key",
        "restaurant_key",
        "camis",
        "prediction_anchor_date",
        "target_inspection_date",
        "target_grade",
        "target_is_bc",
    ]
    return gzip.compress(frame[columns].to_csv(index=False).encode("utf-8"))


def class_summary(values: pd.Series) -> dict[str, float | int]:
    positives = int(values.sum())
    rows = int(len(values))
    return {
        "rows": rows,
        "grade_a_rows": rows - positives,
        "grade_bc_rows": positives,
        "grade_bc_rate": round(positives / rows, 6),
    }


def main() -> None:
    load_dotenv()
    arguments = parse_arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    workgroup = os.getenv("ATHENA_WORKGROUP", "primary")
    query_output = os.getenv(
        "ATHENA_OUTPUT_LOCATION", f"s3://{bucket}/athena/ml-query-results/"
    )
    base_key = f"{arguments.output_prefix.strip('/')}/run_id={arguments.run_id}"

    session = boto3.Session(profile_name=profile, region_name=region)
    athena = session.client("athena")
    s3 = session.client("s3")

    try:
        s3.head_object(Bucket=bucket, Key=f"{base_key}/preparation_report.json")
    except ClientError as error:
        if error.response["Error"]["Code"] not in {"404", "NoSuchKey"}:
            raise
    else:
        raise FileExistsError(f"Preparation run already exists: s3://{bucket}/{base_key}")

    frame = convert_types(
        read_athena_table(
            athena,
            arguments.database,
            arguments.table,
            workgroup,
            query_output,
        )
    )
    validate_leakage_boundary(frame)

    cutoff = pd.Timestamp(arguments.test_start_date)
    train = frame[frame["target_inspection_date"] < cutoff].copy()
    test = frame[frame["target_inspection_date"] >= cutoff].copy()
    if train.empty or test.empty:
        raise ValueError("The selected date cutoff produced an empty train or test set.")
    if train["target_inspection_date"].max() >= test["target_inspection_date"].min():
        raise ValueError("The chronological train/test boundary overlaps.")

    preprocessor = build_preprocessor()
    x_train = preprocessor.fit_transform(train[MODEL_FEATURES])
    x_test = preprocessor.transform(test[MODEL_FEATURES])
    y_train = train["target_is_bc"].to_numpy(dtype=np.int8)
    y_test = test["target_is_bc"].to_numpy(dtype=np.int8)
    feature_names = preprocessor.get_feature_names_out().tolist()

    artifacts = {
        "X_train.npz": (sparse_bytes(x_train), "application/octet-stream"),
        "X_test.npz": (sparse_bytes(x_test), "application/octet-stream"),
        "y_train.npy": (numpy_bytes(y_train), "application/octet-stream"),
        "y_test.npy": (numpy_bytes(y_test), "application/octet-stream"),
        "train_rows.csv.gz": (metadata_bytes(train), "application/gzip"),
        "test_rows.csv.gz": (metadata_bytes(test), "application/gzip"),
        "preprocessor.joblib": (joblib_bytes(preprocessor), "application/octet-stream"),
        "feature_names.json": (
            json.dumps(feature_names, indent=2).encode("utf-8"),
            "application/json",
        ),
    }
    for name, (content, content_type) in artifacts.items():
        upload_bytes(s3, bucket, f"{base_key}/{name}", content, content_type)

    report = {
        "status": "SUCCESS",
        "run_id": arguments.run_id,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "source": f"{arguments.database}.{arguments.table}",
        "source_rows": int(len(frame)),
        "test_start_date": cutoff.date().isoformat(),
        "train_target_date_min": train["target_inspection_date"].min().date().isoformat(),
        "train_target_date_max": train["target_inspection_date"].max().date().isoformat(),
        "test_target_date_min": test["target_inspection_date"].min().date().isoformat(),
        "test_target_date_max": test["target_inspection_date"].max().date().isoformat(),
        "train": class_summary(train["target_is_bc"]),
        "test": class_summary(test["target_is_bc"]),
        "numeric_features": NUMERIC_FEATURES,
        "categorical_features": CATEGORICAL_FEATURES,
        "encoded_feature_count": len(feature_names),
        "missing_values_before_preparation": {
            column: int(frame[column].isna().sum()) for column in MODEL_FEATURES
        },
        "missing_values_after_preparation": int(
            np.isnan(x_train.data).sum() + np.isnan(x_test.data).sum()
        ),
        "leakage_audit": {
            "passed": True,
            "target_columns_excluded": sorted(NON_PREDICTOR_COLUMNS),
            "preprocessing_fit_on_training_rows_only": True,
            "chronological_split_has_no_overlap": True,
        },
        "output_path": f"s3://{bucket}/{base_key}",
    }
    report_content = json.dumps(report, indent=2).encode("utf-8")
    upload_bytes(
        s3,
        bucket,
        f"{base_key}/preparation_report.json",
        report_content,
        "application/json",
    )
    print(report_content.decode("utf-8"))


if __name__ == "__main__":
    main()
