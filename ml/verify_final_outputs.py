"""Verify the final Phase 5 model bundle and current risk-score Parquet."""

from __future__ import annotations

import argparse
import io
import json
import os

import boto3
import joblib
import pandas as pd
from dotenv import load_dotenv


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--final-model-run-id", required=True)
    parser.add_argument("--score-run-id", required=True)
    return parser.parse_args()


def main() -> None:
    load_dotenv()
    selected = arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    s3 = boto3.Session(profile_name=profile, region_name=region).client("s3")
    model_key = f"ml/final_models/run_id={selected.final_model_run_id}"
    score_key = f"ml/current_scores/run_id={selected.score_run_id}"

    def read(key: str) -> bytes:
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read()

    bundle = joblib.load(io.BytesIO(read(f"{model_key}/model_bundle.joblib")))
    report = json.loads(read(f"{score_key}/scoring_report.json"))
    scores = pd.read_parquet(
        io.BytesIO(read(f"{score_key}/current_restaurant_risk_scores.parquet"))
    )
    required = {
        "restaurant_id",
        "risk_probability",
        "risk_category",
        "main_contributing_factors",
        "model_version",
        "scoring_timestamp",
    }
    if required - set(scores.columns):
        raise ValueError(
            f"Missing score columns: {sorted(required - set(scores.columns))}"
        )
    if len(scores) != report["eligible_restaurants_scored"]:
        raise ValueError("Parquet row count does not match the scoring report.")
    if not scores["restaurant_id"].is_unique:
        raise ValueError("Restaurant IDs are not unique.")
    if not scores["risk_probability"].between(0, 1).all():
        raise ValueError("Risk probabilities are outside 0 through 1.")
    if set(scores["risk_category"]) - {"LOW", "MODERATE", "HIGH"}:
        raise ValueError("Unexpected risk category found.")
    if scores[list(required)].isna().any().any():
        raise ValueError("Required score output contains null values.")
    factor_counts = scores["main_contributing_factors"].map(
        lambda value: len(json.loads(value))
    )
    if (factor_counts == 0).any():
        raise ValueError("Some restaurants have no contributing factors.")
    if set(scores["model_version"]) != {bundle["model_version"]}:
        raise ValueError("Score model version does not match the saved model bundle.")

    print(
        json.dumps(
            {
                "status": "SUCCESS",
                "rows": int(len(scores)),
                "unique_restaurant_ids": int(scores["restaurant_id"].nunique()),
                "risk_categories": scores["risk_category"].value_counts().to_dict(),
                "minimum_factors_per_restaurant": int(factor_counts.min()),
                "model_version": bundle["model_version"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
