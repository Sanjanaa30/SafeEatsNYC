"""Tests for explicit Bronze schemas and Silver cast contracts."""

from __future__ import annotations

import pytest


pytest.importorskip("pyspark")

from pyspark.sql.types import ArrayType, DoubleType, StringType, StructType

from spark.schemas import (
    COMPLAINT_311_RAW_SCHEMA,
    COMPLAINT_311_SILVER_CASTS,
    DOHMH_RAW_SCHEMA,
    DOHMH_SILVER_CASTS,
)


def test_identifier_fields_remain_strings() -> None:
    assert isinstance(DOHMH_RAW_SCHEMA["camis"].dataType, StringType)
    assert isinstance(DOHMH_RAW_SCHEMA["zipcode"].dataType, StringType)
    assert isinstance(COMPLAINT_311_RAW_SCHEMA["unique_key"].dataType, StringType)
    assert isinstance(COMPLAINT_311_RAW_SCHEMA["incident_zip"].dataType, StringType)


def test_location_schema_preserves_numeric_coordinates() -> None:
    location_type = DOHMH_RAW_SCHEMA["location"].dataType
    assert isinstance(location_type, StructType)
    coordinates_type = location_type["coordinates"].dataType
    assert isinstance(coordinates_type, ArrayType)
    assert isinstance(coordinates_type.elementType, DoubleType)


def test_silver_cast_contract_contains_required_types() -> None:
    assert DOHMH_SILVER_CASTS["inspection_date"] == "timestamp"
    assert DOHMH_SILVER_CASTS["score"] == "integer"
    assert DOHMH_SILVER_CASTS["latitude"] == "double"
    assert COMPLAINT_311_SILVER_CASTS["created_date"] == "timestamp"
    assert COMPLAINT_311_SILVER_CASTS["longitude"] == "double"
