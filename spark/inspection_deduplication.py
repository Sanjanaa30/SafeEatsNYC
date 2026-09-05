"""Exact-record deduplication for DOHMH inspection/violation rows."""

from __future__ import annotations

from pyspark.sql import DataFrame, Window, functions as F

from spark.schemas import DOHMH_RAW_SCHEMA


DOHMH_SOURCE_COLUMNS = tuple(DOHMH_RAW_SCHEMA.fieldNames())


def add_inspection_violation_id(frame: DataFrame) -> DataFrame:
    """Hash every original source field into one deterministic row ID."""

    source_record = F.struct(*(F.col(name) for name in DOHMH_SOURCE_COLUMNS))
    source_json = F.to_json(source_record, options={"ignoreNullFields": "false"})
    return frame.withColumn(
        "inspection_violation_id",
        F.sha2(source_json, 256),
    )


def deduplicate_inspections(frame: DataFrame) -> DataFrame:
    """Remove only exact repeated source rows and preserve distinct violations."""

    identified = add_inspection_violation_id(frame)
    ordering = Window.partitionBy("inspection_violation_id").orderBy(
        F.col("source_file").desc(),
        F.col("bronze_run_id").desc(),
    )
    return (
        identified.withColumn("_duplicate_rank", F.row_number().over(ordering))
        .filter(F.col("_duplicate_rank") == 1)
        .drop("_duplicate_rank")
    )
