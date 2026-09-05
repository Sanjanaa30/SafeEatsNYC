"""Reusable PySpark transformations for NYC 311 complaint records."""

from __future__ import annotations

from pyspark.sql import DataFrame, functions as F

from spark.inspection_cleaning import (
    NYC_LATITUDE_MAX,
    NYC_LATITUDE_MIN,
    NYC_LONGITUDE_MAX,
    NYC_LONGITUDE_MIN,
    cleaned_text,
    parsed_timestamp,
)


RELEVANT_COMPLAINT_TYPES = (
    "FOOD ESTABLISHMENT",
    "FOOD POISONING",
    "RODENT",
)
NYC_BOROUGHS = (
    "BRONX",
    "BROOKLYN",
    "MANHATTAN",
    "QUEENS",
    "STATEN ISLAND",
)


def prepare_complaints(frame: DataFrame) -> DataFrame:
    """Clean 311 text, dates, ZIP codes, boroughs, and coordinates."""

    prepared = frame
    if "source_file" not in prepared.columns:
        prepared = prepared.withColumn("source_file", F.input_file_name())
    if "bronze_run_id" not in prepared.columns:
        prepared = prepared.withColumn(
            "bronze_run_id",
            F.regexp_extract("source_file", r"run_id=([^/]+)", 1),
        )

    prepared = (
        prepared.withColumn("unique_key_original", F.col("unique_key"))
        .withColumn("created_date_original", F.col("created_date"))
        .withColumn("closed_date_original", F.col("closed_date"))
        .withColumn("due_date_original", F.col("due_date"))
        .withColumn(
            "resolution_action_updated_date_original",
            F.col("resolution_action_updated_date"),
        )
        .withColumn("complaint_type_original", F.col("complaint_type"))
        .withColumn("borough_original", F.col("borough"))
        .withColumn("incident_zip_original", F.col("incident_zip"))
        .withColumn("latitude_original", F.col("latitude"))
        .withColumn("longitude_original", F.col("longitude"))
        .withColumn("unique_key", cleaned_text("unique_key"))
        .withColumn("complaint_type", F.upper(cleaned_text("complaint_type")))
        .withColumn("descriptor", cleaned_text("descriptor"))
        .withColumn("status", F.upper(cleaned_text("status")))
        .withColumn("created_date", parsed_timestamp("created_date"))
        .withColumn("closed_date", parsed_timestamp("closed_date"))
        .withColumn("due_date", parsed_timestamp("due_date"))
        .withColumn(
            "resolution_action_updated_date",
            parsed_timestamp("resolution_action_updated_date"),
        )
    )

    borough_text = F.upper(cleaned_text("borough_original"))
    prepared = (
        prepared.withColumn(
            "borough",
            F.when(borough_text == "NEW YORK", "MANHATTAN").otherwise(
                borough_text
            ),
        )
        .withColumn(
            "borough_status",
            F.when(borough_text.isNull() | (borough_text == "UNSPECIFIED"), "MISSING")
            .when(F.col("borough").isin(*NYC_BOROUGHS), "VALID")
            .otherwise("INVALID"),
        )
        .withColumn(
            "borough",
            F.when(F.col("borough_status") == "VALID", F.col("borough")),
        )
    )

    zip_text = cleaned_text("incident_zip_original")
    prepared = (
        prepared.withColumn(
            "incident_zip",
            F.when(
                zip_text.rlike(r"^\d{5}(-\d{4})?$"),
                F.substring(zip_text, 1, 5),
            ),
        )
        .withColumn(
            "incident_zip_status",
            F.when(zip_text.isNull(), "MISSING")
            .when(F.col("incident_zip").isNull(), "INVALID")
            .otherwise("VALID"),
        )
    )

    latitude_text = cleaned_text("latitude_original")
    longitude_text = cleaned_text("longitude_original")
    prepared = (
        prepared.withColumn("_latitude_parsed", F.col("latitude_original").try_cast("double"))
        .withColumn("_longitude_parsed", F.col("longitude_original").try_cast("double"))
        .withColumn(
            "coordinate_status",
            F.when(latitude_text.isNull() & longitude_text.isNull(), "MISSING")
            .when(latitude_text.isNull() | longitude_text.isNull(), "PARTIAL")
            .when(
                F.col("_latitude_parsed").isNull()
                | F.col("_longitude_parsed").isNull(),
                "INVALID_FORMAT",
            )
            .when(
                ~F.col("_latitude_parsed").between(-90.0, 90.0)
                | ~F.col("_longitude_parsed").between(-180.0, 180.0),
                "OUT_OF_RANGE",
            )
            .when(
                ~F.col("_latitude_parsed").between(
                    NYC_LATITUDE_MIN, NYC_LATITUDE_MAX
                )
                | ~F.col("_longitude_parsed").between(
                    NYC_LONGITUDE_MIN, NYC_LONGITUDE_MAX
                ),
                "OUTSIDE_NYC",
            )
            .otherwise("VALID"),
        )
        .withColumn(
            "latitude",
            F.when(F.col("coordinate_status") == "VALID", F.col("_latitude_parsed")),
        )
        .withColumn(
            "longitude",
            F.when(F.col("coordinate_status") == "VALID", F.col("_longitude_parsed")),
        )
        .drop("_latitude_parsed", "_longitude_parsed")
    )

    created_text = cleaned_text("created_date_original")
    prepared = (
        prepared.withColumn(
            "created_date_status",
            F.when(created_text.isNull(), "MISSING")
            .when(F.col("created_date").isNull(), "INVALID")
            .otherwise("VALID"),
        )
        .withColumn("complaint_year", F.year("created_date"))
        .withColumn("complaint_month", F.month("created_date"))
    )

    rejection_reasons = F.filter(
        F.array(
            F.when(F.col("unique_key").isNull(), F.lit("MISSING_UNIQUE_KEY")),
            F.when(
                F.col("created_date_status") == "MISSING",
                F.lit("MISSING_CREATED_DATE"),
            ),
            F.when(
                F.col("created_date_status") == "INVALID",
                F.lit("INVALID_CREATED_DATE"),
            ),
            F.when(
                F.col("complaint_type").isNull()
                | ~F.col("complaint_type").isin(*RELEVANT_COMPLAINT_TYPES),
                F.lit("IRRELEVANT_COMPLAINT_TYPE"),
            ),
        ),
        lambda reason: reason.isNotNull(),
    )
    return prepared.withColumn("rejection_reasons", rejection_reasons)


def split_complaints(
    frame: DataFrame,
) -> tuple[DataFrame, DataFrame, DataFrame]:
    """Separate geospatial-ready, non-spatial, and rejected complaints."""

    accepted = frame.filter(F.size("rejection_reasons") == 0)
    rejected = frame.filter(F.size("rejection_reasons") > 0)
    geospatial_ready = accepted.filter(F.col("coordinate_status") == "VALID").drop(
        "rejection_reasons"
    )
    without_valid_coordinates = accepted.filter(
        F.col("coordinate_status") != "VALID"
    ).drop("rejection_reasons")
    return geospatial_ready, without_valid_coordinates, rejected

