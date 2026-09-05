"""Build the production NYC 311 Silver Parquet datasets in Amazon S3."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import boto3
from spark.bronze_io import read_bronze_json
from spark.bronze_runs import select_bronze_runs
from spark.build_inspections_silver import (
    ensure_prefix_is_new,
    grouped_counts,
    validated_run_id,
    write_report,
)
from spark.complaint_cleaning import prepare_complaints, split_complaints
from spark.complaint_deduplication import deduplicate_complaints
from spark.schemas import COMPLAINT_311_RAW_SCHEMA
from spark.session import create_spark_session


def parse_arguments() -> argparse.Namespace:
    """Read the immutable Silver run ID and optional audit database path."""

    parser = argparse.ArgumentParser(
        description="Clean, deduplicate, and write NYC 311 Silver Parquet."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument(
        "--audit-db",
        type=Path,
        default=Path(
            os.getenv("SAFEEATS_AUDIT_DB", "data/audit/ingestion_audit.db")
        ),
    )
    return parser.parse_args()


def s3_locations(run_id: str) -> dict[str, str]:
    """Build immutable locations for each 311 Silver outcome."""

    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    prefix = os.getenv("SAFEEATS_SILVER_PREFIX", "silver").strip("/")
    ready_key = f"{prefix}/complaints_311/run_id={run_id}"
    nonspatial_key = (
        f"{prefix}/complaints_311_without_valid_coordinates/run_id={run_id}"
    )
    rejected_key = f"{prefix}/complaints_311_rejected/run_id={run_id}"
    return {
        "bucket": bucket,
        "ready_key": ready_key,
        "ready_data": f"s3a://{bucket}/{ready_key}/data",
        "nonspatial_key": nonspatial_key,
        "nonspatial_data": f"s3a://{bucket}/{nonspatial_key}/data",
        "rejected_key": rejected_key,
        "rejected_data": f"s3a://{bucket}/{rejected_key}/data",
        "report_key": f"{ready_key}/quality_report.json",
    }


def main() -> None:
    """Clean, deduplicate, write, and verify production 311 Silver data."""

    arguments = parse_arguments()
    run_id = validated_run_id(arguments.run_id)
    runs = select_bronze_runs(arguments.audit_db, "complaints_311")
    if not runs:
        raise RuntimeError("No successful production 311 Bronze runs were selected.")

    region = os.getenv("AWS_REGION", "us-east-1")
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    client = boto3.Session(profile_name=profile, region_name=region).client("s3")
    locations = s3_locations(run_id)
    for key_name in ("ready_key", "nonspatial_key", "rejected_key"):
        ensure_prefix_is_new(client, locations["bucket"], locations[key_name])

    spark = create_spark_session("safeeats-build-complaints-silver")
    try:
        bronze = read_bronze_json(
            spark,
            [run.page_glob for run in runs],
            COMPLAINT_311_RAW_SCHEMA,
        ).cache()
        raw_count = bronze.count()
        expected_raw_count = sum(run.rows_received for run in runs)
        if raw_count != expected_raw_count:
            raise RuntimeError(
                "Bronze row count does not match the successful audit records: "
                f"read {raw_count}, expected {expected_raw_count}."
            )

        prepared = prepare_complaints(bronze)
        deduplicated = deduplicate_complaints(prepared).cache()
        deduplicated_count = deduplicated.count()
        ready, nonspatial, rejected = split_complaints(deduplicated)
        ready.cache()
        nonspatial.cache()
        rejected.cache()
        ready_count = ready.count()
        nonspatial_count = nonspatial.count()
        rejected_count = rejected.count()
        if ready_count + nonspatial_count + rejected_count != deduplicated_count:
            raise RuntimeError("The three 311 Silver outcomes do not reconcile.")

        ready.write.mode("errorifexists").partitionBy(
            "complaint_year", "complaint_month"
        ).parquet(locations["ready_data"])
        if nonspatial_count:
            nonspatial.write.mode("errorifexists").partitionBy(
                "complaint_year", "complaint_month"
            ).parquet(locations["nonspatial_data"])
        if rejected_count:
            rejected.write.mode("errorifexists").parquet(
                locations["rejected_data"]
            )

        ready_readback = spark.read.parquet(locations["ready_data"]).count()
        nonspatial_readback = (
            spark.read.parquet(locations["nonspatial_data"]).count()
            if nonspatial_count
            else 0
        )
        rejected_readback = (
            spark.read.parquet(locations["rejected_data"]).count()
            if rejected_count
            else 0
        )
        if (ready_readback, nonspatial_readback, rejected_readback) != (
            ready_count,
            nonspatial_count,
            rejected_count,
        ):
            raise RuntimeError("A 311 Silver Parquet read-back count does not match.")

        report = {
            "silver_run_id": run_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "source_name": "complaints_311",
            "bronze_run_ids": [run.run_id for run in runs],
            "bronze_audit_rows_expected": expected_raw_count,
            "raw_rows_read": raw_count,
            "duplicate_complaint_rows_removed": raw_count - deduplicated_count,
            "deduplicated_rows": deduplicated_count,
            "geospatial_ready_rows": ready_count,
            "without_valid_coordinates_rows": nonspatial_count,
            "rejected_rows": rejected_count,
            "geospatial_ready_readback_rows": ready_readback,
            "without_valid_coordinates_readback_rows": nonspatial_readback,
            "rejected_readback_rows": rejected_readback,
            "coordinate_status_counts": grouped_counts(
                deduplicated, "coordinate_status"
            ),
            "created_date_status_counts": grouped_counts(
                deduplicated, "created_date_status"
            ),
            "output_path": locations["ready_data"].replace("s3a://", "s3://", 1),
            "without_valid_coordinates_output_path": (
                locations["nonspatial_data"].replace("s3a://", "s3://", 1)
                if nonspatial_count
                else None
            ),
            "rejected_output_path": (
                locations["rejected_data"].replace("s3a://", "s3://", 1)
                if rejected_count
                else None
            ),
            "status": "SUCCESS",
        }
        write_report(
            client,
            locations["bucket"],
            locations["report_key"],
            report,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        try:
            spark.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()

