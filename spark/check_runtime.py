"""Small test proving that PySpark can run and write Parquet to SafeEats S3."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from spark.session import create_spark_session


def main() -> None:
    """Create two rows, write them to S3 as Parquet, and read them back."""

    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    silver_prefix = os.getenv("SAFEEATS_SILVER_PREFIX", "silver").strip("/")
    checked_at = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = (
        f"s3a://{bucket}/{silver_prefix}/_system_checks/"
        f"spark_runtime_{checked_at}"
    )

    spark = create_spark_session("safeeats-spark-runtime-check")
    try:
        java_version = spark._jvm.java.lang.System.getProperty("java.version")
        sample = spark.createDataFrame(
            [(1, "DOHMH"), (2, "311")],
            ["row_number", "source_name"],
        )
        sample.write.mode("errorifexists").parquet(output_path)
        rows_read_back = spark.read.parquet(output_path).count()
        if rows_read_back != 2:
            raise RuntimeError(f"Expected 2 rows but read back {rows_read_back}.")

        print("Spark runtime check succeeded.")
        print(f"Spark version: {spark.version}")
        print(f"Container Java version: {java_version}")
        print(f"Rows written and read back: {rows_read_back}")
        print(f"Output: {output_path}")
    finally:
        try:
            spark.stop()
        except Exception:
            # If the JVM has already stopped, preserve the original Spark error.
            pass


if __name__ == "__main__":
    main()
