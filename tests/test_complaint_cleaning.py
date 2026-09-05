"""Spark tests for Phase 3 NYC 311 cleaning."""

from __future__ import annotations

import pytest


pytest.importorskip("pyspark")

from pyspark.sql import SparkSession

from spark.complaint_cleaning import prepare_complaints, split_complaints
from spark.schemas import COMPLAINT_311_RAW_SCHEMA


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = (
        SparkSession.builder.master("local[1]")
        .appName("test-complaint-cleaning")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    yield session
    session.stop()


def test_complaints_are_cleaned_and_split_without_losing_valid_records(
    spark: SparkSession,
) -> None:
    rows = [
        {
            "unique_key": "1",
            "created_date": "2026-08-20T10:30:00.000",
            "complaint_type": "Food Poisoning",
            "borough": "New York",
            "incident_zip": "10001-1234",
            "latitude": "40.7500",
            "longitude": "-73.9900",
        },
        {
            "unique_key": "2",
            "created_date": "2026-08-20T11:30:00.000",
            "complaint_type": "Rodent",
            "borough": "Brooklyn",
            "incident_zip": "bad",
            "latitude": None,
            "longitude": None,
        },
        {
            "unique_key": None,
            "created_date": "bad-date",
            "complaint_type": "Noise",
            "borough": "Queens",
            "incident_zip": "11373",
            "latitude": "40.73",
            "longitude": "-73.87",
        },
    ]
    source = spark.createDataFrame(rows, COMPLAINT_311_RAW_SCHEMA)
    ready, nonspatial, rejected = split_complaints(prepare_complaints(source))

    ready_row = ready.collect()[0]
    assert ready_row.unique_key == "1"
    assert ready_row.borough == "MANHATTAN"
    assert ready_row.incident_zip == "10001"
    assert ready_row.coordinate_status == "VALID"

    nonspatial_row = nonspatial.collect()[0]
    assert nonspatial_row.unique_key == "2"
    assert nonspatial_row.coordinate_status == "MISSING"
    assert nonspatial_row.incident_zip_status == "INVALID"

    rejected_row = rejected.collect()[0]
    assert set(rejected_row.rejection_reasons) == {
        "MISSING_UNIQUE_KEY",
        "INVALID_CREATED_DATE",
        "IRRELEVANT_COMPLAINT_TYPE",
    }

