"""Reusable PySpark transformations for DOHMH inspection records."""

from __future__ import annotations

import os
from pathlib import Path

from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    StringType,
    StructField,
    StructType,
)

from ingestion.name_normalization import (
    brand_candidates,
    canonicalize_name,
    load_name_references,
    normalize_name,
)


TIMESTAMP_FORMAT = "yyyy-MM-dd'T'HH:mm:ss.SSS"
NYC_LATITUDE_MIN = 40.45
NYC_LATITUDE_MAX = 40.95
NYC_LONGITUDE_MIN = -74.30
NYC_LONGITUDE_MAX = -73.65

NAME_RESULT_SCHEMA = StructType(
    [
        StructField("syntax_normalized", StringType(), True),
        StructField("canonical_normalized", StringType(), True),
        StructField("brand_candidates", ArrayType(StringType()), False),
        StructField("fast_food_brands", ArrayType(StringType()), False),
        StructField("is_reviewed_co_brand", BooleanType(), False),
    ]
)


def default_reference_directory() -> Path:
    """Locate the reviewed Phase 1 name-reference files."""

    project_root = Path(
        os.getenv("SAFEEATS_PROJECT_ROOT", Path(__file__).resolve().parents[1])
    )
    return project_root / "data" / "reference"


def cleaned_text(column_name: str):
    """Trim text, collapse whitespace, and turn blank strings into nulls."""

    value = F.trim(F.regexp_replace(F.col(column_name), r"\s+", " "))
    return F.when(value == "", F.lit(None)).otherwise(value)


def parsed_timestamp(column_name: str):
    """Parse the Socrata timestamp format without failing on bad text."""

    return F.try_to_timestamp(F.col(column_name), F.lit(TIMESTAMP_FORMAT))


def add_name_columns(
    frame: DataFrame,
    reference_directory: Path | None = None,
) -> DataFrame:
    """Apply the exact Phase 1 alias and reviewed co-brand rules."""

    reference_directory = reference_directory or default_reference_directory()
    aliases, co_brands, fast_food_registry = load_name_references(
        reference_directory
    )
    spark_context = frame.sparkSession.sparkContext
    alias_rules = spark_context.broadcast(aliases)
    co_brand_rules = spark_context.broadcast(co_brands)
    fast_food_brands = spark_context.broadcast(fast_food_registry)

    def classify_name(name):
        if not isinstance(name, str) or not name.strip():
            return (None, None, [], [], False)

        syntax_normalized = normalize_name(name)
        canonical_normalized = canonicalize_name(name, alias_rules.value)
        candidates = list(
            brand_candidates(name, alias_rules.value, co_brand_rules.value)
        )
        matched_brands = [
            candidate
            for candidate in candidates
            if candidate in fast_food_brands.value
        ]
        return (
            syntax_normalized,
            canonical_normalized,
            candidates,
            matched_brands,
            len(candidates) > 1,
        )

    classify_name_udf = F.udf(classify_name, NAME_RESULT_SCHEMA)
    classified = frame.withColumn("_name_result", classify_name_udf(F.col("dba")))

    return (
        classified.withColumn("restaurant_name_original", F.col("dba"))
        .withColumn("restaurant_name_standardized", F.upper(cleaned_text("dba")))
        .withColumn(
            "restaurant_name_syntax_normalized",
            F.col("_name_result.syntax_normalized"),
        )
        .withColumn(
            "restaurant_name_normalized",
            F.col("_name_result.canonical_normalized"),
        )
        .withColumn(
            "brand_name_candidates",
            F.col("_name_result.brand_candidates"),
        )
        .withColumn(
            "fast_food_brand_names",
            F.col("_name_result.fast_food_brands"),
        )
        .withColumn(
            "is_reviewed_co_brand",
            F.col("_name_result.is_reviewed_co_brand"),
        )
        .withColumn("is_fast_food", F.size("fast_food_brand_names") > 0)
        .drop("_name_result")
    )


def add_address_columns(frame: DataFrame) -> DataFrame:
    """Create cleaned address parts and one readable display address."""

    cleaned = (
        frame.withColumn("borough_original", F.col("boro"))
        .withColumn("building_original", F.col("building"))
        .withColumn("street_original", F.col("street"))
        .withColumn("zipcode_original", F.col("zipcode"))
        .withColumn("borough", F.upper(cleaned_text("boro")))
        .withColumn("building_clean", F.upper(cleaned_text("building")))
        .withColumn("street_clean", F.upper(cleaned_text("street")))
        .withColumn("_zipcode_text", cleaned_text("zipcode"))
        .withColumn(
            "zipcode",
            F.when(F.col("_zipcode_text").rlike(r"^\d{5}$"), F.col("_zipcode_text")),
        )
        .withColumn(
            "zipcode_status",
            F.when(F.col("_zipcode_text").isNull(), F.lit("MISSING"))
            .when(F.col("zipcode").isNull(), F.lit("INVALID"))
            .otherwise(F.lit("VALID")),
        )
    )

    street_line = F.concat_ws(
        " ", F.col("building_clean"), F.col("street_clean")
    )
    street_line = F.when(street_line == "", F.lit(None)).otherwise(street_line)
    state_and_zip = F.when(
        F.col("zipcode").isNotNull(), F.concat(F.lit("NY "), F.col("zipcode"))
    )

    return (
        cleaned.withColumn(
            "address_display",
            F.concat_ws(", ", street_line, F.col("borough"), state_and_zip),
        )
        .drop("_zipcode_text")
    )


def add_typed_columns(frame: DataFrame) -> DataFrame:
    """Safely create typed dates, score, coordinates, and quality statuses."""

    typed = (
        frame.withColumn("inspection_date_original", F.col("inspection_date"))
        .withColumn("grade_date_original", F.col("grade_date"))
        .withColumn("record_date_original", F.col("record_date"))
        .withColumn("score_original", F.col("score"))
        .withColumn("latitude_original", F.col("latitude"))
        .withColumn("longitude_original", F.col("longitude"))
        .withColumn("inspection_date", parsed_timestamp("inspection_date"))
        .withColumn("grade_date", parsed_timestamp("grade_date"))
        .withColumn("record_date", parsed_timestamp("record_date"))
        .withColumn("score", F.col("score").try_cast("integer"))
        .withColumn("_latitude_parsed", F.col("latitude").try_cast("double"))
        .withColumn("_longitude_parsed", F.col("longitude").try_cast("double"))
    )

    typed = (
        typed.withColumn(
            "inspection_date_status",
            F.when(cleaned_text("inspection_date_original").isNull(), "MISSING")
            .when(F.col("inspection_date").isNull(), "INVALID")
            .when(F.to_date("inspection_date") == F.lit("1900-01-01"), "UNINSPECTED_PLACEHOLDER")
            .otherwise("VALID"),
        )
        .withColumn(
            "score_status",
            F.when(cleaned_text("score_original").isNull(), "MISSING")
            .when(F.col("score").isNull(), "INVALID")
            .otherwise("VALID"),
        )
    )

    latitude_text = cleaned_text("latitude_original")
    longitude_text = cleaned_text("longitude_original")
    typed = typed.withColumn(
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

    return (
        typed.withColumn(
            "latitude",
            F.when(F.col("coordinate_status") == "VALID", F.col("_latitude_parsed")),
        )
        .withColumn(
            "longitude",
            F.when(F.col("coordinate_status") == "VALID", F.col("_longitude_parsed")),
        )
        .withColumn("inspection_year", F.year("inspection_date"))
        .withColumn("inspection_month", F.month("inspection_date"))
        .drop("_latitude_parsed", "_longitude_parsed")
    )


def clean_inspections(
    frame: DataFrame,
    reference_directory: Path | None = None,
) -> tuple[DataFrame, DataFrame]:
    """Return accepted and rejected inspections after Steps 4–6 cleaning."""

    prepared = frame
    if "source_file" not in prepared.columns:
        prepared = prepared.withColumn("source_file", F.input_file_name())
    if "bronze_run_id" not in prepared.columns:
        prepared = prepared.withColumn(
            "bronze_run_id",
            F.regexp_extract("source_file", r"run_id=([^/]+)", 1),
        )
    prepared = prepared.withColumn("camis", cleaned_text("camis"))
    prepared = add_name_columns(prepared, reference_directory)
    prepared = add_address_columns(prepared)
    prepared = add_typed_columns(prepared)

    rejection_reasons = F.filter(
        F.array(
            F.when(F.col("camis").isNull(), F.lit("MISSING_CAMIS")),
            F.when(
                F.col("inspection_date_status") == "MISSING",
                F.lit("MISSING_INSPECTION_DATE"),
            ),
            F.when(
                F.col("inspection_date_status") == "INVALID",
                F.lit("INVALID_INSPECTION_DATE"),
            ),
        ),
        lambda reason: reason.isNotNull(),
    )
    prepared = prepared.withColumn("rejection_reasons", rejection_reasons)

    accepted = prepared.filter(F.size("rejection_reasons") == 0).drop(
        "rejection_reasons"
    )
    rejected = prepared.filter(F.size("rejection_reasons") > 0)
    return accepted, rejected
