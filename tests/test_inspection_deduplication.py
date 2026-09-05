"""Tests for exact DOHMH inspection/violation deduplication."""

from __future__ import annotations

import pytest


pytest.importorskip("pyspark")

from pyspark.sql import SparkSession, functions as F

from spark.inspection_deduplication import deduplicate_inspections
from spark.schemas import DOHMH_RAW_SCHEMA


def test_exact_duplicates_removed_but_distinct_violations_preserved() -> None:
    spark = (
        SparkSession.builder.master("local[1]")
        .appName("test-inspection-deduplication")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    rows = [
        {
            "camis": "12345678",
            "inspection_date": "2026-08-20T00:00:00.000",
            "violation_code": "04L",
        },
        {
            "camis": "12345678",
            "inspection_date": "2026-08-20T00:00:00.000",
            "violation_code": "04L",
        },
        {
            "camis": "12345678",
            "inspection_date": "2026-08-20T00:00:00.000",
            "violation_code": "06D",
        },
    ]
    source = (
        spark.createDataFrame(rows, DOHMH_RAW_SCHEMA)
        .withColumn("source_file", F.lit("test.json"))
        .withColumn("bronze_run_id", F.lit("test-run"))
    )

    try:
        result = deduplicate_inspections(source).orderBy("violation_code").collect()
    finally:
        spark.stop()

    assert [row.violation_code for row in result] == ["04L", "06D"]
    assert all(len(row.inspection_violation_id) == 64 for row in result)
