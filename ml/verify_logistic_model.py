"""Read back and verify a saved SafeEats logistic-regression model run."""

from __future__ import annotations

import argparse
import gzip
import io
import json
import os

import boto3
import joblib
import pandas as pd
from dotenv import load_dotenv


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-run-id", required=True)
    parser.add_argument("--model-prefix", default="ml/models/logistic_regression")
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    arguments = parse_arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    base_key = f"{arguments.model_prefix.strip('/')}/run_id={arguments.model_run_id}"
    s3 = boto3.Session(profile_name=profile, region_name=region).client("s3")

    def read(name: str) -> bytes:
        return s3.get_object(Bucket=bucket, Key=f"{base_key}/{name}")["Body"].read()

    report = json.loads(read("evaluation_report.json"))
    bundle = joblib.load(io.BytesIO(read("model_bundle.joblib")))
    predictions = pd.read_csv(
        io.BytesIO(gzip.decompress(read("test_predictions.csv.gz")))
    )

    expected_rows = report["test"]["rows"]
    if "label_maturation" in report:
        expected_rows += report["label_maturation"][
            "immature_rows_excluded_from_metrics"
        ]
    if len(predictions) != expected_rows:
        raise ValueError("Saved prediction count does not match the evaluation report.")
    if set(predictions["risk_category"]) - {"LOW", "MODERATE", "HIGH"}:
        raise ValueError("Saved predictions contain an invalid risk category.")
    if bundle["model_run_id"] != arguments.model_run_id:
        raise ValueError("The model bundle run ID does not match its S3 folder.")
    if bundle["model"].n_features_in_ != len(bundle["feature_names"]):
        raise ValueError("The saved model and feature names have different dimensions.")

    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "model_run_id": arguments.model_run_id,
                "test_predictions": len(predictions),
                "model_features": int(bundle["model"].n_features_in_),
                "risk_categories": sorted(predictions["risk_category"].unique()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
