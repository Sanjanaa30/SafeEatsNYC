"""Read unchanged Bronze API pages with explicit Spark schemas."""

from __future__ import annotations

from collections.abc import Sequence

from pyspark.sql import DataFrame, SparkSession, functions as F
from pyspark.sql.types import StructType


def read_bronze_json(
    spark: SparkSession,
    paths: Sequence[str] | str,
    schema: StructType,
) -> DataFrame:
    """Read Socrata response pages, where each file is one JSON array."""

    return (
        spark.read.option("multiLine", "true")
        .schema(schema)
        .json(paths)
        .withColumn("source_file", F.input_file_name())
        .withColumn(
            "bronze_run_id",
            F.regexp_extract("source_file", r"run_id=([^/]+)", 1),
        )
    )
