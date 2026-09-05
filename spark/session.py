"""Create the Spark session shared by SafeEats Silver jobs."""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from pyspark.sql import SparkSession


# These versions match the dependencies used by PySpark 4.2.0.
HADOOP_AWS_PACKAGE = "org.apache.hadoop:hadoop-aws:3.5.0"
AWS_SDK_PACKAGE = "software.amazon.awssdk:bundle:2.35.4"
AWS_PROFILE_CREDENTIALS_PROVIDER = (
    "software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider"
)
SPARK_PROFILE = "safeeats-spark"
SPARK_PROFILE_PATH = Path("/tmp/safeeats-spark-aws-config")


def configure_refreshable_spark_profile(profile: str, region: str) -> None:
    """Route Java credentials through boto3's refreshable aws-login provider."""

    source_config = os.getenv(
        "SAFEEATS_SOURCE_AWS_CONFIG_FILE",
        os.getenv("AWS_CONFIG_FILE", "/home/airflow/.aws/config"),
    )
    source_credentials = os.getenv(
        "SAFEEATS_SOURCE_AWS_SHARED_CREDENTIALS_FILE",
        os.getenv(
            "AWS_SHARED_CREDENTIALS_FILE",
            "/home/airflow/.aws/credentials",
        ),
    )
    os.environ["SAFEEATS_SOURCE_AWS_PROFILE"] = profile
    os.environ["SAFEEATS_SOURCE_AWS_CONFIG_FILE"] = source_config
    os.environ[
        "SAFEEATS_SOURCE_AWS_SHARED_CREDENTIALS_FILE"
    ] = source_credentials

    python_path = os.getenv("PYSPARK_PYTHON", "/usr/local/bin/python")
    helper_path = Path(
        os.getenv(
            "SAFEEATS_PROJECT_ROOT",
            Path(__file__).resolve().parents[1],
        )
    ) / "spark" / "aws_credential_process.py"
    SPARK_PROFILE_PATH.write_text(
        "\n".join(
            [
                f"[profile {SPARK_PROFILE}]",
                f"region = {region}",
                f"credential_process = {python_path} {helper_path}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    SPARK_PROFILE_PATH.chmod(0o600)
    os.environ["AWS_PROFILE"] = SPARK_PROFILE
    os.environ["AWS_CONFIG_FILE"] = str(SPARK_PROFILE_PATH)


def create_spark_session(app_name: str) -> SparkSession:
    """Create local Spark with refreshable AWS profile credentials for S3A."""

    profile = os.getenv(
        "SAFEEATS_SOURCE_AWS_PROFILE",
        os.getenv("AWS_PROFILE", "safeeats-dev"),
    )
    region = os.getenv("AWS_REGION", "us-east-1")
    session = boto3.Session(profile_name=profile, region_name=region)
    credentials = session.get_credentials()
    if credentials is None:
        raise RuntimeError(f"AWS profile {profile!r} did not provide credentials.")
    # This validates or refreshes the login before Spark starts. Do not copy the
    # resulting 15-minute credential into environment variables: that would
    # freeze it and prevent the Java SDK from refreshing it during a long job.
    credentials.get_frozen_credentials()
    configure_refreshable_spark_profile(profile, region)

    spark = (
        SparkSession.builder.appName(app_name)
        .master(os.getenv("SAFEEATS_SPARK_MASTER", "local[1]"))
        .config("spark.jars.packages", f"{HADOOP_AWS_PACKAGE},{AWS_SDK_PACKAGE}")
        .config("spark.ui.enabled", "false")
        .config("spark.network.timeout", "600s")
        .config("spark.executor.heartbeatInterval", "60s")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.sql.session.timeZone", "UTC")
        .config("spark.hadoop.fs.s3a.endpoint.region", region)
        .config("spark.hadoop.fs.s3a.path.style.access", "false")
        .config(
            "spark.hadoop.fs.s3a.aws.credentials.provider",
            AWS_PROFILE_CREDENTIALS_PROVIDER,
        )
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel(os.getenv("SAFEEATS_SPARK_LOG_LEVEL", "WARN"))
    return spark
