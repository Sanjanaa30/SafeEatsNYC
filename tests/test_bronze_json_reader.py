"""Regression test for the unchanged Socrata JSON-array Bronze format."""

from __future__ import annotations

import json

import pytest


pytest.importorskip("pyspark")

from pyspark.sql import SparkSession

from spark.bronze_io import read_bronze_json
from spark.schemas import DOHMH_RAW_SCHEMA


def test_multiline_reader_reads_each_object_in_bronze_array(tmp_path) -> None:
    spark = (
        SparkSession.builder.master("local[1]")
        .appName("test-bronze-json-reader")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    bronze_page = tmp_path / "page_offset=000000000.json"
    bronze_page.write_text(
        json.dumps(
            [
                {
                    "camis": "12345678",
                    "dba": "DUNKIN",
                    "inspection_date": "2026-08-20T00:00:00.000",
                },
                {
                    "camis": "87654321",
                    "dba": "TEST RESTAURANT",
                    "inspection_date": "2026-08-21T00:00:00.000",
                },
            ]
        ),
        encoding="utf-8",
    )

    try:
        rows = read_bronze_json(
            spark, str(bronze_page), DOHMH_RAW_SCHEMA
        ).orderBy("camis").collect()
    finally:
        spark.stop()

    assert [(row.camis, row.dba) for row in rows] == [
        ("12345678", "DUNKIN"),
        ("87654321", "TEST RESTAURANT"),
    ]
