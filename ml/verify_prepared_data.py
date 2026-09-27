"""Read Phase 5 preparation artifacts from S3 and verify their contents."""

from __future__ import annotations

import argparse
import io
import json
import os

import boto3
import numpy as np
from dotenv import load_dotenv
from scipy import sparse


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-prefix", default="ml/prepared")
    return parser.parse_args()


def read_object(s3, bucket: str, key: str) -> bytes:
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read()


def main() -> None:
    load_dotenv()
    arguments = parse_arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    base_key = f"{arguments.output_prefix.strip('/')}/run_id={arguments.run_id}"
    s3 = boto3.Session(profile_name=profile, region_name=region).client("s3")

    report = json.loads(read_object(s3, bucket, f"{base_key}/preparation_report.json"))
    feature_names = json.loads(
        read_object(s3, bucket, f"{base_key}/feature_names.json")
    )
    x_train = sparse.load_npz(
        io.BytesIO(read_object(s3, bucket, f"{base_key}/X_train.npz"))
    )
    x_test = sparse.load_npz(
        io.BytesIO(read_object(s3, bucket, f"{base_key}/X_test.npz"))
    )
    y_train = np.load(
        io.BytesIO(read_object(s3, bucket, f"{base_key}/y_train.npy")),
        allow_pickle=False,
    )
    y_test = np.load(
        io.BytesIO(read_object(s3, bucket, f"{base_key}/y_test.npy")),
        allow_pickle=False,
    )

    expected = (report["train"]["rows"], report["test"]["rows"])
    actual = (x_train.shape[0], x_test.shape[0])
    if actual != expected or (len(y_train), len(y_test)) != expected:
        raise ValueError(f"Artifact row counts do not match the report: {actual}")
    if x_train.shape[1] != len(feature_names) or x_test.shape[1] != len(feature_names):
        raise ValueError("The encoded feature count does not match feature_names.json.")
    if int(y_train.sum()) != report["train"]["grade_bc_rows"]:
        raise ValueError("Training target count does not match the report.")
    if int(y_test.sum()) != report["test"]["grade_bc_rows"]:
        raise ValueError("Test target count does not match the report.")
    if np.isnan(x_train.data).any() or np.isnan(x_test.data).any():
        raise ValueError("Prepared matrices still contain missing values.")

    result = {
        "status": "SUCCESS",
        "train_matrix_shape": list(x_train.shape),
        "test_matrix_shape": list(x_test.shape),
        "train_grade_bc_rows": int(y_train.sum()),
        "test_grade_bc_rows": int(y_test.sum()),
        "missing_values": 0,
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
