"""Deterministic unique-key deduplication for NYC 311 complaints."""

from __future__ import annotations

from pyspark.sql import DataFrame, Window, functions as F

from spark.schemas import COMPLAINT_311_RAW_SCHEMA


COMPLAINT_SOURCE_COLUMNS = tuple(COMPLAINT_311_RAW_SCHEMA.fieldNames())


def add_complaint_record_id(frame: DataFrame) -> DataFrame:
    """Hash every original source field for traceability."""

    source_record = F.struct(*(F.col(name) for name in COMPLAINT_SOURCE_COLUMNS))
    source_json = F.to_json(source_record, options={"ignoreNullFields": "false"})
    return frame.withColumn("complaint_record_id", F.sha2(source_json, 256))


def deduplicate_complaints(frame: DataFrame) -> DataFrame:
    """Keep the newest version of each complaint ID across overlapping runs."""

    identified = add_complaint_record_id(frame).withColumn(
        "_deduplication_key",
        F.when(
            F.col("unique_key").isNotNull(), F.col("unique_key")
        ).otherwise(F.concat(F.lit("MISSING:"), F.col("complaint_record_id"))),
    )
    ordering = Window.partitionBy("_deduplication_key").orderBy(
        F.col("resolution_action_updated_date").desc_nulls_last(),
        F.col("closed_date").desc_nulls_last(),
        F.col("created_date").desc_nulls_last(),
        F.col("bronze_run_id").desc(),
        F.col("source_file").desc(),
    )
    return (
        identified.withColumn("_duplicate_rank", F.row_number().over(ordering))
        .filter(F.col("_duplicate_rank") == 1)
        .drop("_duplicate_rank", "_deduplication_key")
    )

