"""Tests for complaint-to-nearest-restaurant geospatial matching."""

from __future__ import annotations

import pytest


pytest.importorskip("pyspark")

from pyspark.sql import SparkSession

from spark.geospatial_matching import (
    add_unmatched_nonspatial_complaints,
    nearest_restaurant_matches,
)


def test_nearest_match_threshold_and_unmatched_records_are_preserved() -> None:
    spark = (
        SparkSession.builder.master("local[1]")
        .appName("test-geospatial-matching")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )
    complaints = spark.createDataFrame(
        [
            ("near", 40.75000, -73.99000, 2026, 8),
            ("over", 40.75160, -73.99000, 2026, 8),
            ("far", 40.76000, -73.99000, 2026, 8),
        ],
        "unique_key string, latitude double, longitude double, complaint_year int, complaint_month int",
    )
    restaurants = spark.createDataFrame(
        [("100", "TEST", "TEST", "1 MAIN ST", 40.75045, -73.99000)],
        "restaurant_camis string, matched_restaurant_name string, matched_restaurant_name_normalized string, matched_restaurant_address string, restaurant_latitude double, restaurant_longitude double",
    )
    nonspatial = spark.createDataFrame(
        [("missing", None, None, 2026, 8)],
        "unique_key string, latitude double, longitude double, complaint_year int, complaint_month int",
    )

    try:
        spatial = nearest_restaurant_matches(complaints, restaurants, 100.0)
        final = add_unmatched_nonspatial_complaints(spatial, nonspatial, 100.0)
        rows = {row.unique_key: row for row in final.collect()}
    finally:
        spark.stop()

    assert rows["near"].restaurant_match_status == "MATCHED"
    assert rows["near"].restaurant_camis == "100"
    assert 45.0 < rows["near"].match_distance_meters < 55.0
    assert rows["over"].restaurant_match_status == "NO_RESTAURANT_WITHIN_THRESHOLD"
    assert rows["over"].restaurant_camis is None
    assert rows["over"].nearest_candidate_distance_meters > 100.0
    assert rows["far"].restaurant_match_status == "NO_RESTAURANT_WITHIN_THRESHOLD"
    assert rows["far"].restaurant_camis is None
    assert rows["missing"].restaurant_match_status == "NO_VALID_COORDINATES"
