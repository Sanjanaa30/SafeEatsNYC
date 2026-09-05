"""Build complaint-to-nearest-restaurant Silver matches in Amazon S3."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import boto3
from spark.build_inspections_silver import (
    ensure_prefix_is_new,
    grouped_counts,
    validated_run_id,
    write_report,
)
from spark.geospatial_matching import (
    DEFAULT_MATCH_THRESHOLD_METERS,
    add_unmatched_nonspatial_complaints,
    current_restaurant_locations,
    nearest_restaurant_matches,
)
from spark.session import create_spark_session
from pyspark.sql import functions as F


def parse_arguments() -> argparse.Namespace:
    """Read immutable input/output run IDs and the match threshold."""

    parser = argparse.ArgumentParser(
        description="Match cleaned 311 complaints to nearby restaurants."
    )
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--inspections-run-id", required=True)
    parser.add_argument("--complaints-run-id", required=True)
    parser.add_argument(
        "--threshold-meters",
        type=float,
        default=DEFAULT_MATCH_THRESHOLD_METERS,
    )
    return parser.parse_args()


def load_quality_report(client, bucket: str, key: str) -> dict:
    """Read and validate an upstream Silver quality report."""

    response = client.get_object(Bucket=bucket, Key=key)
    report = json.loads(response["Body"].read())
    if report.get("status") != "SUCCESS":
        raise RuntimeError(f"Upstream Silver report is not successful: {key}")
    return report


def threshold_validation_counts(frame) -> dict[str, int]:
    """Count nearest candidates within several distances in one Spark action."""

    distance = F.col("nearest_candidate_distance_meters")
    row = frame.agg(
        F.sum(F.when(distance <= 25.0, 1).otherwise(0)).alias("within_25m"),
        F.sum(F.when(distance <= 50.0, 1).otherwise(0)).alias("within_50m"),
        F.sum(F.when(distance <= 75.0, 1).otherwise(0)).alias("within_75m"),
        F.sum(F.when(distance <= 100.0, 1).otherwise(0)).alias("within_100m"),
        F.sum(F.when(distance <= 150.0, 1).otherwise(0)).alias("within_150m"),
        F.sum(F.when(distance.isNull(), 1).otherwise(0)).alias(
            "no_candidate_in_search_grid"
        ),
    ).first()
    return {name: int(row[name]) for name in row.asDict()}


def main() -> None:
    """Create, verify, and report the complete geospatial match dataset."""

    arguments = parse_arguments()
    run_id = validated_run_id(arguments.run_id)
    inspections_run_id = validated_run_id(arguments.inspections_run_id)
    complaints_run_id = validated_run_id(arguments.complaints_run_id)
    if arguments.threshold_meters <= 0:
        raise ValueError("--threshold-meters must be greater than zero.")

    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    prefix = os.getenv("SAFEEATS_SILVER_PREFIX", "silver").strip("/")
    region = os.getenv("AWS_REGION", "us-east-1")
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    client = boto3.Session(profile_name=profile, region_name=region).client("s3")

    inspections_key = f"{prefix}/inspections/run_id={inspections_run_id}"
    complaints_key = f"{prefix}/complaints_311/run_id={complaints_run_id}"
    nonspatial_key = (
        f"{prefix}/complaints_311_without_valid_coordinates/"
        f"run_id={complaints_run_id}"
    )
    output_key = f"{prefix}/complaint_restaurant_matches/run_id={run_id}"
    output_data = f"s3a://{bucket}/{output_key}/data"
    report_key = f"{output_key}/quality_report.json"
    ensure_prefix_is_new(client, bucket, output_key)

    inspection_report = load_quality_report(
        client, bucket, f"{inspections_key}/quality_report.json"
    )
    complaint_report = load_quality_report(
        client, bucket, f"{complaints_key}/quality_report.json"
    )

    spark = create_spark_session("safeeats-build-geospatial-matches")
    try:
        inspections = spark.read.parquet(
            f"s3a://{bucket}/{inspections_key}/data"
        ).cache()
        complaints = spark.read.parquet(
            f"s3a://{bucket}/{complaints_key}/data"
        ).cache()
        nonspatial = spark.read.parquet(
            f"s3a://{bucket}/{nonspatial_key}/data"
        ).cache()

        inspection_count = inspections.count()
        complaint_count = complaints.count()
        nonspatial_count = nonspatial.count()
        if inspection_count != inspection_report["accepted_rows"]:
            raise RuntimeError("Inspection Silver input count does not match its report.")
        if complaint_count != complaint_report["geospatial_ready_rows"]:
            raise RuntimeError("Spatial 311 input count does not match its report.")
        if nonspatial_count != complaint_report["without_valid_coordinates_rows"]:
            raise RuntimeError("Non-spatial 311 input count does not match its report.")

        restaurants = current_restaurant_locations(inspections).cache()
        restaurant_count = restaurants.count()
        matched_spatial = nearest_restaurant_matches(
            complaints,
            restaurants,
            arguments.threshold_meters,
        )
        final = add_unmatched_nonspatial_complaints(
            matched_spatial,
            nonspatial,
            arguments.threshold_meters,
        ).cache()
        final_count = final.count()
        expected_final_count = complaint_count + nonspatial_count
        if final_count != expected_final_count:
            raise RuntimeError(
                f"Final match rows were {final_count}; expected {expected_final_count}."
            )
        if final.select("unique_key").distinct().count() != final_count:
            raise RuntimeError("The final match dataset has duplicate complaint IDs.")

        final.write.mode("errorifexists").partitionBy(
            "complaint_year", "complaint_month"
        ).parquet(output_data)
        readback_count = spark.read.parquet(output_data).count()
        if readback_count != final_count:
            raise RuntimeError("Geospatial match Parquet read-back count does not match.")

        report = {
            "silver_run_id": run_id,
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "source_name": "complaint_restaurant_matches",
            "inspections_silver_run_id": inspections_run_id,
            "complaints_silver_run_id": complaints_run_id,
            "match_threshold_meters": float(arguments.threshold_meters),
            "inspection_rows_read": inspection_count,
            "restaurant_locations": restaurant_count,
            "complaints_with_valid_coordinates": complaint_count,
            "complaints_without_valid_coordinates": nonspatial_count,
            "final_rows": final_count,
            "readback_rows": readback_count,
            "match_status_counts": grouped_counts(
                final, "restaurant_match_status"
            ),
            "threshold_validation_counts": threshold_validation_counts(
                matched_spatial
            ),
            "output_path": output_data.replace("s3a://", "s3://", 1),
            "status": "SUCCESS",
        }
        write_report(client, bucket, report_key, report)
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        try:
            spark.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
