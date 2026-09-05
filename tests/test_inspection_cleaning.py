"""Spark tests for Phase 3 inspection cleaning Steps 4–6."""

from __future__ import annotations

from pathlib import Path

import pytest


pytest.importorskip("pyspark")

from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, StructField, StructType

from spark.inspection_cleaning import clean_inspections


REFERENCE_DIRECTORY = Path(__file__).resolve().parents[1] / "data" / "reference"
INPUT_SCHEMA = StructType(
    [
        StructField("camis", StringType(), True),
        StructField("dba", StringType(), True),
        StructField("boro", StringType(), True),
        StructField("building", StringType(), True),
        StructField("street", StringType(), True),
        StructField("zipcode", StringType(), True),
        StructField("inspection_date", StringType(), True),
        StructField("grade_date", StringType(), True),
        StructField("record_date", StringType(), True),
        StructField("score", StringType(), True),
        StructField("latitude", StringType(), True),
        StructField("longitude", StringType(), True),
    ]
)


@pytest.fixture(scope="module")
def spark() -> SparkSession:
    session = (
        SparkSession.builder.master("local[1]")
        .appName("test-inspection-cleaning")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    yield session
    session.stop()


def sample_rows() -> list[tuple[str | None, ...]]:
    return [
        (
            "12345678",
            "Dunkin Donuts #4021 LLC",
            " Manhattan ",
            " 10 ",
            "MAIN   STREET",
            "10001",
            "2026-08-20T00:00:00.000",
            None,
            "2026-08-21T00:00:00.000",
            "12",
            "40.7500",
            "-73.9900",
        ),
        (
            "87654321",
            "DUNKIN',' BASKIN ROBBINS",
            "Queens",
            "20",
            "QUEENS BOULEVARD",
            "11373",
            "2026-08-20T00:00:00.000",
            "2026-08-21T00:00:00.000",
            "2026-08-21T00:00:00.000",
            "8",
            "40.7350",
            "-73.8700",
        ),
        (
            "11223344",
            "JOE & THE JUICE",
            "Brooklyn",
            "30",
            "FLATBUSH AVENUE",
            "bad zip",
            "2026-08-22T00:00:00.000",
            None,
            "2026-08-22T00:00:00.000",
            "not-a-score",
            "40.7000",
            None,
        ),
        (
            None,
            "Missing ID Restaurant",
            "Bronx",
            "40",
            "GRAND CONCOURSE",
            "10451",
            "not-a-date",
            None,
            "2026-08-22T00:00:00.000",
            "5",
            "999",
            "-73.9000",
        ),
    ]


def cleaned_frames(spark: SparkSession):
    source = spark.createDataFrame(sample_rows(), INPUT_SCHEMA)
    return clean_inspections(source, REFERENCE_DIRECTORY)


def test_types_names_co_brands_and_addresses(spark: SparkSession) -> None:
    accepted, _ = cleaned_frames(spark)
    rows = {row.camis: row for row in accepted.collect()}

    dunkin = rows["12345678"]
    assert dunkin.restaurant_name_original == "Dunkin Donuts #4021 LLC"
    assert dunkin.restaurant_name_normalized == "DUNKIN"
    assert dunkin.fast_food_brand_names == ["DUNKIN"]
    assert not dunkin.is_reviewed_co_brand
    assert dunkin.address_display == "10 MAIN STREET, MANHATTAN, NY 10001"
    assert dunkin.score == 12
    assert dunkin.coordinate_status == "VALID"

    co_brand = rows["87654321"]
    assert co_brand.restaurant_name_normalized == "DUNKIN BASKIN ROBBINS"
    assert co_brand.fast_food_brand_names == ["DUNKIN", "BASKIN ROBBINS"]
    assert co_brand.is_reviewed_co_brand

    ordinary_separator = rows["11223344"]
    assert ordinary_separator.brand_name_candidates == ["JOE AND THE JUICE"]
    assert not ordinary_separator.is_reviewed_co_brand
    assert ordinary_separator.score is None
    assert ordinary_separator.score_status == "INVALID"
    assert ordinary_separator.coordinate_status == "PARTIAL"
    assert ordinary_separator.zipcode is None
    assert ordinary_separator.zipcode_status == "INVALID"


def test_missing_id_and_invalid_date_are_rejected(spark: SparkSession) -> None:
    accepted, rejected = cleaned_frames(spark)

    assert accepted.count() == 3
    rejected_rows = rejected.collect()
    assert len(rejected_rows) == 1
    assert set(rejected_rows[0].rejection_reasons) == {
        "MISSING_CAMIS",
        "INVALID_INSPECTION_DATE",
    }
