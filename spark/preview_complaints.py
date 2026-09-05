"""Preview NYC 311 Silver cleaning without writing production data."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from spark.bronze_io import read_bronze_json
from spark.bronze_runs import select_bronze_runs
from spark.complaint_cleaning import prepare_complaints, split_complaints
from spark.complaint_deduplication import deduplicate_complaints
from spark.schemas import COMPLAINT_311_RAW_SCHEMA
from spark.session import create_spark_session


def parse_arguments() -> argparse.Namespace:
    """Read the preview size and audit database path."""

    parser = argparse.ArgumentParser(
        description="Preview cleaned production 311 Bronze rows."
    )
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument(
        "--audit-db",
        type=Path,
        default=Path(
            os.getenv("SAFEEATS_AUDIT_DB", "data/audit/ingestion_audit.db")
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Read a small real sample and print its three cleaning outcomes."""

    arguments = parse_arguments()
    if arguments.limit < 1:
        raise ValueError("--limit must be at least 1.")

    runs = select_bronze_runs(arguments.audit_db, "complaints_311")
    if not runs:
        raise RuntimeError("No successful production 311 Bronze runs were selected.")

    spark = create_spark_session("safeeats-preview-complaints")
    try:
        bronze = read_bronze_json(
            spark,
            [run.page_glob for run in runs],
            COMPLAINT_311_RAW_SCHEMA,
        ).limit(arguments.limit)
        prepared = prepare_complaints(bronze)
        deduplicated = deduplicate_complaints(prepared).cache()
        ready, nonspatial, rejected = split_complaints(deduplicated)

        print(f"Production Bronze runs selected: {len(runs)}")
        print(f"Rows previewed: {arguments.limit}")
        print(f"Rows after unique-key deduplication: {deduplicated.count()}")
        print(f"Geospatial-ready rows: {ready.count()}")
        print(f"Rows without valid coordinates: {nonspatial.count()}")
        print(f"Rejected rows: {rejected.count()}")
        print("Coordinate statuses:")
        deduplicated.groupBy("coordinate_status").count().orderBy(
            "coordinate_status"
        ).show(truncate=False)
        print("Cleaned examples:")
        deduplicated.select(
            "unique_key",
            "created_date",
            "complaint_type",
            "borough",
            "incident_zip",
            "coordinate_status",
            "latitude",
            "longitude",
        ).show(10, truncate=False)
    finally:
        try:
            spark.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()

