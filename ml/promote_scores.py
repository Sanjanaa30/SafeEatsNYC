"""Promote one verified Phase 5 score run as the deterministic dashboard input."""

import argparse
import json
import os
from datetime import datetime, timezone

import boto3
from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-run-id", required=True)
    arguments = parser.parse_args()

    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    prefix = f"ml/current_scores/run_id={arguments.score_run_id}"
    score_key = f"{prefix}/current_restaurant_risk_scores.parquet"
    report_key = f"{prefix}/scoring_report.json"
    monitoring_key = (
        f"ml/model_monitoring/run_id={arguments.score_run_id}/monitoring_report.json"
    )
    session = boto3.Session(profile_name=profile, region_name=region)
    s3 = session.client("s3")

    s3.head_object(Bucket=bucket, Key=score_key)
    report = json.loads(s3.get_object(Bucket=bucket, Key=report_key)["Body"].read())
    if (
        report.get("status") != "SUCCESS"
        or report.get("score_run_id") != arguments.score_run_id
    ):
        raise ValueError("Only a successful, matching score run can be promoted.")
    monitoring = json.loads(
        s3.get_object(Bucket=bucket, Key=monitoring_key)["Body"].read()
    )
    if not monitoring.get("promotion_allowed") or monitoring.get("status") == "FAIL":
        raise ValueError(
            "Model monitoring did not approve this score run for promotion."
        )

    pointer = {
        "status": "SUCCESS",
        "score_run_id": arguments.score_run_id,
        "score_key": score_key,
        "scoring_report_key": report_key,
        "monitoring_report_key": monitoring_key,
        "monitoring_status": monitoring.get("status"),
        "model_version": report.get("model_version"),
        "scoring_timestamp": report.get("scoring_timestamp"),
        "promoted_at": datetime.now(timezone.utc).isoformat(),
    }
    s3.put_object(
        Bucket=bucket,
        Key="ml/current_scores/latest.json",
        Body=json.dumps(pointer, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(json.dumps(pointer, indent=2))


if __name__ == "__main__":
    main()
