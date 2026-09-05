"""Tests for deterministic 311 complaint deduplication."""

from __future__ import annotations

import pytest


pytest.importorskip("pyspark")

from pyspark.sql import SparkSession, functions as F

from spark.complaint_cleaning import prepare_complaints
from spark.complaint_deduplication import deduplicate_complaints
from spark.schemas import COMPLAINT_311_RAW_SCHEMA


def test_newest_version_of_each_unique_key_is_kept() -> None:
    spark = (
        SparkSession.builder.master("local[1]")
        .appName("test-complaint-deduplication")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    rows = [
        {
            "unique_key": "123",
            "created_date": "2026-08-20T10:00:00.000",
            "resolution_action_updated_date": "2026-08-20T11:00:00.000",
            "complaint_type": "Rodent",
            "status": "Open",
        },
        {
            "unique_key": "123",
            "created_date": "2026-08-20T10:00:00.000",
            "resolution_action_updated_date": "2026-08-21T11:00:00.000",
            "complaint_type": "Rodent",
            "status": "Closed",
        },
        {
            "unique_key": "456",
            "created_date": "2026-08-22T10:00:00.000",
            "complaint_type": "Food Establishment",
            "status": "Open",
        },
    ]
    source = (
        spark.createDataFrame(rows, COMPLAINT_311_RAW_SCHEMA)
        .withColumn("source_file", F.lit("test.json"))
        .withColumn("bronze_run_id", F.lit("test-run"))
    )

    try:
        result = {
            row.unique_key: row
            for row in deduplicate_complaints(
                prepare_complaints(source)
            ).collect()
        }
    finally:
        spark.stop()

    assert set(result) == {"123", "456"}
    assert result["123"].status == "CLOSED"
    assert all(len(row.complaint_record_id) == 64 for row in result.values())

