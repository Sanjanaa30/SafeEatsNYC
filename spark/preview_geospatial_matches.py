"""Preview real complaint-to-restaurant distance matching without writing S3."""

from __future__ import annotations

import argparse
import os

from pyspark.sql import functions as F

from spark.geospatial_matching import (
    DEFAULT_MATCH_THRESHOLD_METERS,
    current_restaurant_locations,
    nearest_restaurant_matches,
)
from spark.session import create_spark_session


def parse_arguments() -> argparse.Namespace:
    """Read input Silver runs, sample size, and match threshold."""

    parser = argparse.ArgumentParser(
        description="Preview real complaint-to-restaurant matches."
    )
    parser.add_argument("--inspections-run-id", required=True)
    parser.add_argument("--complaints-run-id", required=True)
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--threshold-meters",
        type=float,
        default=DEFAULT_MATCH_THRESHOLD_METERS,
    )
    return parser.parse_args()


def main() -> None:
    """Print match rates, distance bands, and inspectable real examples."""

    arguments = parse_arguments()
    if arguments.limit < 1:
        raise ValueError("--limit must be at least 1.")

    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    prefix = os.getenv("SAFEEATS_SILVER_PREFIX", "silver").strip("/")
    inspections_path = (
        f"s3a://{bucket}/{prefix}/inspections/"
        f"run_id={arguments.inspections_run_id}/data"
    )
    complaints_path = (
        f"s3a://{bucket}/{prefix}/complaints_311/"
        f"run_id={arguments.complaints_run_id}/data"
    )

    spark = create_spark_session("safeeats-preview-geospatial-matches")
    try:
        inspections = spark.read.parquet(inspections_path)
        complaints = spark.read.parquet(complaints_path).limit(arguments.limit)
        restaurants = current_restaurant_locations(inspections).cache()
        matched = nearest_restaurant_matches(
            complaints,
            restaurants,
            arguments.threshold_meters,
        ).cache()

        print(f"Restaurant locations considered: {restaurants.count()}")
        print(f"Complaints previewed: {matched.count()}")
        print(f"Match threshold: {arguments.threshold_meters:.0f} meters")
        print("Match statuses:")
        matched.groupBy("restaurant_match_status").count().orderBy(
            "restaurant_match_status"
        ).show(truncate=False)
        print("Nearest-candidate distance bands:")
        matched.withColumn(
            "distance_band",
            F.when(F.col("nearest_candidate_distance_meters").isNull(), "NO CANDIDATE")
            .when(F.col("nearest_candidate_distance_meters") <= 25, "0-25m")
            .when(F.col("nearest_candidate_distance_meters") <= 50, "25-50m")
            .when(F.col("nearest_candidate_distance_meters") <= 75, "50-75m")
            .when(F.col("nearest_candidate_distance_meters") <= 100, "75-100m")
            .when(F.col("nearest_candidate_distance_meters") <= 150, "100-150m")
            .otherwise("OVER 150m"),
        ).groupBy("distance_band").count().orderBy("distance_band").show(
            truncate=False
        )
        print("Matched examples:")
        matched.filter(F.col("restaurant_match_status") == "MATCHED").select(
            "unique_key",
            "complaint_type",
            "incident_address",
            "matched_restaurant_name",
            "matched_restaurant_address",
            F.round("match_distance_meters", 1).alias("distance_meters"),
        ).orderBy("match_distance_meters").show(20, truncate=False)
    finally:
        try:
            spark.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()

