"""
Initial SafeEats daily ingestion DAG: two independent source tasks.

This script defines the automated Airflow Directed Acyclic Graph (DAG) that orchestrates your daily data downloads. 
It tells Airflow how and when to run your ingestion pipeline for both restaurant inspections and 311 complaints in 
parallel, handling retries, schedules, and logging automatically.

"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pendulum
from airflow.sdk import dag, get_current_context, task  # type: ignore[import-not-found]

from ingestion.audit import AuditStore
from ingestion.pipeline import run_ingestion, utc_now
from ingestion.sources import COMPLAINTS_311, DOHMH_INSPECTIONS, SourceConfig
from ingestion.storage import BronzeStorage, LocalBronzeStorage, S3BronzeStorage


LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(os.getenv("SAFEEATS_PROJECT_ROOT", "/opt/safeeats"))
AUDIT_DATABASE = Path(
    os.getenv(
        "SAFEEATS_AUDIT_DB",
        PROJECT_ROOT / "data" / "audit" / "ingestion_audit.db",
    )
)


def configured_bronze_storage() -> BronzeStorage:
    """Build the Bronze storage selected by the Airflow environment."""

    backend = os.getenv("SAFEEATS_STORAGE_BACKEND", "s3").strip().lower()
    if backend == "local":
        bronze_root = Path(
            os.getenv(
                "SAFEEATS_BRONZE_ROOT",
                PROJECT_ROOT / "data" / "bronze",
            )
        )
        return LocalBronzeStorage(bronze_root)
    if backend != "s3":
        raise ValueError("SAFEEATS_STORAGE_BACKEND must be 'local' or 's3'.")

    bucket = os.getenv("SAFEEATS_S3_BUCKET", "").strip()
    if not bucket:
        raise ValueError("SAFEEATS_S3_BUCKET is required for S3 Bronze storage.")
    return S3BronzeStorage(
        bucket=bucket,
        prefix=os.getenv("SAFEEATS_S3_PREFIX", "bronze"),
        region=os.getenv("AWS_REGION") or None,
        profile=os.getenv("AWS_PROFILE") or None,
    )


def context_run_end(context: dict[str, Any]) -> datetime:
    """Use Airflow's bounded interval when present, including manual runs."""

    interval_end = context.get("data_interval_end")
    if interval_end is None:
        return utc_now()
    if interval_end.tzinfo is None:
        return interval_end.replace(tzinfo=timezone.utc)
    return interval_end.astimezone(timezone.utc)


def ingest_source(source: SourceConfig) -> dict[str, Any]:
    """Run a configured source using the current logical Airflow run ID."""

    context = get_current_context()
    result = run_ingestion(
        source=source,
        run_id=context["run_id"],
        run_end=context_run_end(context),
        storage=configured_bronze_storage(),
        audit_database=AUDIT_DATABASE,
        page_size=int(os.getenv("SAFEEATS_INGESTION_PAGE_SIZE", "10000")),
        overlap_days=int(os.getenv("SAFEEATS_OVERLAP_DAYS", "2")),
        initial_lookback_days=int(
            os.getenv("SAFEEATS_INITIAL_LOOKBACK_DAYS", "1095")
        ),
        app_token=os.getenv("NYC_OPEN_DATA_APP_TOKEN"),
    )
    return AuditStore.as_dict(result)


@dag(
    dag_id="safeeats_ingestion",
    description="Incrementally preserve DOHMH and relevant 311 JSON in Bronze.",
    schedule="0 10 * * *",
    start_date=pendulum.datetime(2026, 8, 29, tz="America/New_York"),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "safeeats",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["safeeats", "bronze", "ingestion"],
)
def safeeats_ingestion():
    """Ingest both independent sources, then emit one completion summary."""

    @task(task_id="ingest_inspections")
    def ingest_inspections() -> dict[str, Any]:
        return ingest_source(DOHMH_INSPECTIONS)

    @task(task_id="ingest_311")
    def ingest_311() -> dict[str, Any]:
        return ingest_source(COMPLAINTS_311)

    @task(task_id="ingestion_complete")
    def ingestion_complete(results: list[dict[str, Any]]) -> None:
        LOGGER.info(
            "Ingestion complete: %s",
            {
                result["source_name"]: result["rows_received"]
                for result in results
            },
        )

    ingestion_complete([ingest_inspections(), ingest_311()])


safeeats_ingestion()
