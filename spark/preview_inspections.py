"""Preview Phase 3 inspection cleaning without writing final Silver data."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from pyspark.sql import functions as F

from spark.bronze_io import read_bronze_json
from spark.bronze_runs import select_bronze_runs
from spark.inspection_cleaning import clean_inspections
from spark.schemas import DOHMH_RAW_SCHEMA
from spark.session import create_spark_session


def parse_arguments() -> argparse.Namespace:
    """Read the number of Bronze rows to validate."""

    parser = argparse.ArgumentParser(
        description="Read a bounded DOHMH Bronze preview and apply Steps 4–6."
    )
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument(
        "--audit-db",
        type=Path,
        default=Path(
            os.getenv("SAFEEATS_AUDIT_DB", "data/audit/ingestion_audit.db")
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Read selected S3 files and print cleaning results."""

    arguments = parse_arguments()
    if arguments.limit <= 0:
        raise ValueError("--limit must be greater than zero.")

    runs = select_bronze_runs(arguments.audit_db, "dohmh_inspections")
    if not runs:
        raise RuntimeError("No successful production DOHMH Bronze runs were selected.")

    spark = create_spark_session("safeeats-inspection-cleaning-preview")
    try:
        paths = [run.page_glob for run in runs]
        bronze = read_bronze_json(spark, paths, DOHMH_RAW_SCHEMA).limit(
            arguments.limit
        )
        accepted, rejected = clean_inspections(bronze)
        accepted.cache()
        rejected.cache()

        accepted_count = accepted.count()
        rejected_count = rejected.count()
        print(f"Production Bronze runs selected: {len(runs)}")
        print(f"Rows previewed: {accepted_count + rejected_count}")
        print(f"Accepted rows: {accepted_count}")
        print(f"Rejected rows: {rejected_count}")

        if rejected_count:
            print("Rejection reasons:")
            rejected.select(F.explode("rejection_reasons").alias("reason")) \
                .groupBy("reason").count().orderBy("reason").show(truncate=False)

        if accepted_count == 0:
            raise RuntimeError(
                "All preview rows were rejected. Review the rejection reasons above."
            )

        print("Coordinate statuses:")
        accepted.groupBy("coordinate_status").count().orderBy(
            "coordinate_status"
        ).show(truncate=False)

        print("Name and address examples:")
        accepted.select(
            "restaurant_name_original",
            "restaurant_name_normalized",
            "fast_food_brand_names",
            "is_reviewed_co_brand",
            "address_display",
            "inspection_date",
            "score",
        ).orderBy(F.col("is_reviewed_co_brand").desc()).show(10, truncate=False)
    finally:
        try:
            spark.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
