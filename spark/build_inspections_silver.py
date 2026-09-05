"""Build the production DOHMH Silver Parquet dataset in Amazon S3."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from spark.bronze_io import read_bronze_json
from spark.bronze_runs import select_bronze_runs
from spark.inspection_cleaning import clean_inspections
from spark.inspection_deduplication import deduplicate_inspections
from spark.schemas import DOHMH_RAW_SCHEMA
from spark.session import create_spark_session


SAFE_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def parse_arguments() -> argparse.Namespace:
    """Read the immutable Silver run ID and optional audit database path."""

    parser = argparse.ArgumentParser(
        description="Clean, deduplicate, and write DOHMH Silver Parquet."
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


def validated_run_id(run_id: str) -> str:
    """Allow a simple S3-safe run identifier only."""

    if not SAFE_RUN_ID.fullmatch(run_id):
        raise ValueError(
            "--run-id may contain only letters, numbers, dots, underscores, "
            "and hyphens."
        )
    return run_id


def s3_locations(run_id: str) -> dict[str, str]:
    """Build the versioned accepted, rejected, and report locations."""

    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    prefix = os.getenv("SAFEEATS_SILVER_PREFIX", "silver").strip("/")
    accepted_key = f"{prefix}/inspections/run_id={run_id}"
    rejected_key = f"{prefix}/inspections_rejected/run_id={run_id}"
    return {
        "bucket": bucket,
        "accepted_key": accepted_key,
        "accepted_data": f"s3a://{bucket}/{accepted_key}/data",
        "rejected_key": rejected_key,
        "rejected_data": f"s3a://{bucket}/{rejected_key}/data",
        "report_key": f"{accepted_key}/quality_report.json",
    }


def ensure_prefix_is_new(client, bucket: str, prefix: str) -> None:
    """Prevent a run ID from overwriting any existing Silver objects."""

    response = client.list_objects_v2(
        Bucket=bucket,
        Prefix=f"{prefix}/",
        MaxKeys=1,
    )
    if response.get("KeyCount", 0):
        raise FileExistsError(
            f"Silver run already exists: s3://{bucket}/{prefix}/"
        )


def grouped_counts(frame, column_name: str) -> dict[str, int]:
    """Collect a small quality-status count table as a dictionary."""

    return {
        str(row[column_name]): int(row["count"])
        for row in frame.groupBy(column_name).count().collect()
    }


def write_report(client, bucket: str, key: str, report: dict) -> None:
    """Write the immutable JSON quality report after Parquet verification."""

    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=json.dumps(report, indent=2, sort_keys=True).encode("utf-8"),
            ContentType="application/json",
            ServerSideEncryption="AES256",
            IfNoneMatch="*",
        )
    except ClientError as error:
        if error.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 412:
            raise FileExistsError(
                f"Quality report already exists: s3://{bucket}/{key}"
            ) from error
        raise


def main() -> None:
    """Run Steps 7–9 and verify the written Parquet row counts."""

    arguments = parse_arguments()
    run_id = validated_run_id(arguments.run_id)
    runs = select_bronze_runs(arguments.audit_db, "dohmh_inspections")
    if not runs:
        raise RuntimeError("No successful production DOHMH Bronze runs were selected.")

    region = os.getenv("AWS_REGION", "us-east-1")
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    client = boto3.Session(profile_name=profile, region_name=region).client("s3")
    locations = s3_locations(run_id)
    ensure_prefix_is_new(client, locations["bucket"], locations["accepted_key"])
    ensure_prefix_is_new(client, locations["bucket"], locations["rejected_key"])

    spark = create_spark_session("safeeats-build-inspections-silver")
    try:
        bronze = read_bronze_json(
            spark,
            [run.page_glob for run in runs],
            DOHMH_RAW_SCHEMA,
        ).cache()
        raw_count = bronze.count()
        expected_raw_count = sum(run.rows_received for run in runs)
        if raw_count != expected_raw_count:
            raise RuntimeError(
                "Bronze row count does not match the successful audit records: "
                f"read {raw_count}, expected {expected_raw_count}."
            )

        deduplicated = deduplicate_inspections(bronze).cache()
        deduplicated_count = deduplicated.count()
        accepted, rejected = clean_inspections(deduplicated)
        accepted.cache()
        rejected.cache()
        accepted_count = accepted.count()
        rejected_count = rejected.count()
        if accepted_count + rejected_count != deduplicated_count:
            raise RuntimeError("Accepted and rejected counts do not reconcile.")

        accepted.write.mode("errorifexists").partitionBy(
            "inspection_year", "inspection_month"
        ).parquet(locations["accepted_data"])
        if rejected_count:
            rejected.write.mode("errorifexists").parquet(
                locations["rejected_data"]
            )

        accepted_readback_count = spark.read.parquet(
            locations["accepted_data"]
        ).count()
        rejected_readback_count = (
            spark.read.parquet(locations["rejected_data"]).count()
            if rejected_count
            else 0
        )
        if accepted_readback_count != accepted_count:
            raise RuntimeError("Accepted Silver read-back count does not match.")
        if rejected_readback_count != rejected_count:
            raise RuntimeError("Rejected Silver read-back count does not match.")

        report = {
            "silver_run_id": run_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "source_name": "dohmh_inspections",
            "bronze_run_ids": [run.run_id for run in runs],
            "bronze_audit_rows_expected": expected_raw_count,
            "raw_rows_read": raw_count,
            "exact_duplicates_removed": raw_count - deduplicated_count,
            "deduplicated_rows": deduplicated_count,
            "accepted_rows": accepted_count,
            "rejected_rows": rejected_count,
            "accepted_readback_rows": accepted_readback_count,
            "rejected_readback_rows": rejected_readback_count,
            "coordinate_status_counts": grouped_counts(
                accepted, "coordinate_status"
            ),
            "inspection_date_status_counts": grouped_counts(
                accepted, "inspection_date_status"
            ),
            "output_path": locations["accepted_data"].replace(
                "s3a://", "s3://", 1
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
