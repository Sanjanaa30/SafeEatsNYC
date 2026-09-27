"""Daily SafeEats pipeline from NYC Open Data through the Gold warehouse.

The two API downloads run in parallel. The data-processing stages then run in
order so each stage uses only successful outputs from the preceding stage.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
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
from orchestration.audit import PipelineAuditStore
from orchestration.run_context import run_names

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
            os.getenv("SAFEEATS_BRONZE_ROOT", PROJECT_ROOT / "data" / "bronze")
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
    """Run one source with the current logical Airflow run ID."""

    context = get_current_context()
    result = run_ingestion(
        source=source,
        run_id=context["run_id"],
        run_end=context_run_end(context),
        storage=configured_bronze_storage(),
        audit_database=AUDIT_DATABASE,
        page_size=int(os.getenv("SAFEEATS_INGESTION_PAGE_SIZE", "10000")),
        overlap_days=int(os.getenv("SAFEEATS_OVERLAP_DAYS", "2")),
        initial_lookback_days=int(os.getenv("SAFEEATS_INITIAL_LOOKBACK_DAYS", "1095")),
        app_token=os.getenv("NYC_OPEN_DATA_APP_TOKEN"),
    )
    return AuditStore.as_dict(result)


def run_stage(
    stage_name: str,
    pipeline_run_id: str,
    commands: list[list[str]],
) -> None:
    """Run a stage, audit its attempt, and preserve the original error."""

    context = get_current_context()
    attempt_number = int(context["task_instance"].try_number)
    audit = PipelineAuditStore(AUDIT_DATABASE)
    audit.start(
        pipeline_run_id,
        stage_name,
        attempt_number,
        utc_now().isoformat(),
    )
    try:
        for command in commands:
            LOGGER.info("Running project command: %s", " ".join(command))
            subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    except Exception as error:
        audit.finish(
            pipeline_run_id,
            stage_name,
            attempt_number,
            utc_now().isoformat(),
            "FAILED",
            f"{type(error).__name__}: {error}",
        )
        raise
    audit.finish(
        pipeline_run_id,
        stage_name,
        attempt_number,
        utc_now().isoformat(),
        "SUCCESS",
    )


def run_retry_probe(pipeline_run_id: str) -> None:
    """Optionally fail once to verify Airflow retry behavior safely."""

    context = get_current_context()
    attempt_number = int(context["task_instance"].try_number)
    dag_run = context.get("dag_run")
    configuration = dag_run.conf if dag_run is not None else {}
    should_fail_once = bool(configuration.get("test_retry_once", False))
    audit = PipelineAuditStore(AUDIT_DATABASE)
    audit.start(
        pipeline_run_id,
        "retry_probe",
        attempt_number,
        utc_now().isoformat(),
    )
    if should_fail_once and attempt_number == 1:
        message = "Intentional Phase 6 first-attempt failure."
        audit.finish(
            pipeline_run_id,
            "retry_probe",
            attempt_number,
            utc_now().isoformat(),
            "FAILED",
            message,
        )
        raise RuntimeError(message)
    audit.finish(
        pipeline_run_id,
        "retry_probe",
        attempt_number,
        utc_now().isoformat(),
        "SUCCESS",
    )


def dbt_runtime_paths(names: dict[str, str]) -> tuple[str, str]:
    """Keep dbt's temporary files outside the read-only project mount."""

    runtime_root = (
        Path(os.getenv("SAFEEATS_DBT_RUNTIME_ROOT", "/tmp/safeeats-dbt"))
        / names["run_token"]
    )
    return str(runtime_root / "logs"), str(runtime_root / "target")


@dag(
    dag_id="safeeats_daily_pipeline",
    description="Automate Bronze, Silver, geospatial matching, and Gold dbt models.",
    schedule="0 10 * * *",
    # Phase 6 was deployed on September 6. The first automatic run is the
    # following 10:00 AM New York schedule; catchup remains disabled.
    start_date=pendulum.datetime(2026, 9, 6, tz=ZoneInfo("America/New_York")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "safeeats",
        "retries": 2,
        "retry_delay": timedelta(minutes=5),
    },
    tags=["safeeats", "bronze", "silver", "gold", "daily"],
)
def safeeats_daily_pipeline():
    """Connect the completed Phase 2, 3, and 4 jobs in dependency order."""

    @task(task_id="pipeline_context")
    def pipeline_context() -> dict[str, str]:
        context = get_current_context()
        return run_names(context["run_id"], context_run_end(context))

    @task(
        task_id="retry_probe",
        retries=1,
        retry_delay=timedelta(seconds=10),
    )
    def retry_probe(names: dict[str, str]) -> None:
        run_retry_probe(names["pipeline_run_id"])

    @task(task_id="ingest_inspections")
    def ingest_inspections() -> dict[str, Any]:
        return ingest_source(DOHMH_INSPECTIONS)

    @task(task_id="ingest_311")
    def ingest_311() -> dict[str, Any]:
        return ingest_source(COMPLAINTS_311)

    @task(task_id="bronze_complete")
    def bronze_complete(results: list[dict[str, Any]]) -> None:
        LOGGER.info(
            "Bronze complete: %s",
            {result["source_name"]: result["rows_received"] for result in results},
        )

    @task(task_id="build_inspections_silver")
    def build_inspections_silver(names: dict[str, str]) -> None:
        run_stage(
            "build_inspections_silver",
            names["pipeline_run_id"],
            [
                [
                    "python",
                    "-m",
                    "spark.build_inspections_silver",
                    "--run-id",
                    names["inspections_silver_run_id"],
                    "--retry-incomplete",
                ]
            ],
        )

    @task(task_id="build_complaints_silver")
    def build_complaints_silver(names: dict[str, str]) -> None:
        run_stage(
            "build_complaints_silver",
            names["pipeline_run_id"],
            [
                [
                    "python",
                    "-m",
                    "spark.build_complaints_silver",
                    "--run-id",
                    names["complaints_silver_run_id"],
                    "--retry-incomplete",
                ]
            ],
        )

    @task(task_id="build_geospatial_matches")
    def build_geospatial_matches(names: dict[str, str]) -> None:
        run_stage(
            "build_geospatial_matches",
            names["pipeline_run_id"],
            [
                [
                    "python",
                    "-m",
                    "spark.build_geospatial_matches",
                    "--run-id",
                    names["matches_run_id"],
                    "--inspections-run-id",
                    names["inspections_silver_run_id"],
                    "--complaints-run-id",
                    names["complaints_silver_run_id"],
                    "--retry-incomplete",
                ]
            ],
        )

    @task(task_id="register_silver_in_athena")
    def register_silver_in_athena(names: dict[str, str]) -> None:
        run_stage(
            "register_silver_in_athena",
            names["pipeline_run_id"],
            [
                [
                    "python",
                    str(PROJECT_ROOT / "warehouse" / "setup_athena.py"),
                    "--inspections-run-id",
                    names["inspections_silver_run_id"],
                    "--matches-run-id",
                    names["matches_run_id"],
                ]
            ],
        )

    @task(task_id="build_gold")
    def build_gold(names: dict[str, str]) -> None:
        log_path, target_path = dbt_runtime_paths(names)
        common = [
            "--project-dir",
            str(PROJECT_ROOT / "dbt"),
            "--profiles-dir",
            str(PROJECT_ROOT / "dbt"),
            "--vars",
            json.dumps({"ml_scoring_date": names["scoring_date"]}),
        ]
        run_stage(
            "build_gold",
            names["pipeline_run_id"],
            [
                [
                    "dbt",
                    "--log-path",
                    log_path,
                    "seed",
                    "--target-path",
                    target_path,
                    *common,
                ],
                [
                    "dbt",
                    "--log-path",
                    log_path,
                    "run",
                    "--target-path",
                    target_path,
                    *common,
                ],
            ],
        )

    @task(task_id="test_gold")
    def test_gold(names: dict[str, str]) -> None:
        log_path, target_path = dbt_runtime_paths(names)
        run_stage(
            "test_gold",
            names["pipeline_run_id"],
            [
                [
                    "dbt",
                    "--log-path",
                    log_path,
                    "test",
                    "--target-path",
                    target_path,
                    "--project-dir",
                    str(PROJECT_ROOT / "dbt"),
                    "--profiles-dir",
                    str(PROJECT_ROOT / "dbt"),
                    "--vars",
                    json.dumps({"ml_scoring_date": names["scoring_date"]}),
                ]
            ],
        )

    @task(task_id="reconciliation")
    def reconciliation(names: dict[str, str]) -> None:
        report_root = PROJECT_ROOT / "data" / "audit" / "pipeline" / names["run_token"]
        run_stage(
            "reconciliation",
            names["pipeline_run_id"],
            [
                [
                    "python",
                    str(PROJECT_ROOT / "warehouse" / "reconcile_phase4.py"),
                    "--inspections-run-id",
                    names["inspections_silver_run_id"],
                    "--complaints-run-id",
                    names["complaints_silver_run_id"],
                    "--matches-run-id",
                    names["matches_run_id"],
                    "--audit-db",
                    str(AUDIT_DATABASE),
                    "--local-report",
                    str(report_root / "reconciliation.json"),
                    "--markdown-report",
                    str(report_root / "reconciliation.md"),
                    "--s3-report-key",
                    f"gold/_audit/pipeline_run_id={names['run_token']}/reconciliation.json",
                ]
            ],
        )

    @task(task_id="pipeline_complete")
    def pipeline_complete(names: dict[str, str]) -> None:
        LOGGER.info("SafeEats daily pipeline completed successfully: %s", names)

    names = pipeline_context()
    retry_checked = retry_probe(names)
    inspections_result = ingest_inspections()
    complaints_result = ingest_311()
    bronze_done = bronze_complete([inspections_result, complaints_result])

    # Spark is intentionally sequential in this local Docker environment so
    # two Java processes do not compete for the worker's limited memory.
    inspections_silver = build_inspections_silver(names)
    complaints_silver = build_complaints_silver(names)
    matches = build_geospatial_matches(names)
    athena_ready = register_silver_in_athena(names)
    gold_ready = build_gold(names)
    tests_passed = test_gold(names)
    reconciled = reconciliation(names)
    done = pipeline_complete(names)

    retry_checked >> [inspections_result, complaints_result]
    bronze_done >> inspections_silver >> complaints_silver >> matches
    matches >> athena_ready >> gold_ready >> tests_passed >> reconciled >> done


safeeats_daily_pipeline()
