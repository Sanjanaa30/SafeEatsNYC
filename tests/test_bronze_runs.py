"""Tests for selecting production Bronze inputs for Phase 3."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from spark.bronze_runs import is_production_run, select_bronze_runs


def create_audit_database(path: Path) -> None:
    """Create the small part of the audit schema used by the selector."""

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE ingestion_audit (
                run_id TEXT,
                source_name TEXT,
                started_at TEXT,
                rows_received INTEGER,
                output_path TEXT,
                status TEXT
            )
            """
        )
        


def add_run(
    path: Path,
    run_id: str,
    *,
    status: str = "SUCCESS",
    rows_received: int = 10,
) -> None:
    """Insert one inspection run into a test audit database."""

    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            INSERT INTO ingestion_audit VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                "dohmh_inspections",
                "2026-08-30T00:00:00+00:00",
                rows_received,
                f"s3://example/bronze/inspections/run_id={run_id}",
                status,
            ),
        )


def test_production_run_policy() -> None:
    assert is_production_run("initial-3y-dohmh-20260830-v1")
    assert is_production_run("scheduled__2026-08-30T14:00:00+00:00")
    assert not is_production_run("incremental-dohmh-20260830-v1")
    assert not is_production_run("airflow-s3-success-20260830-v1")


def test_selects_only_successful_non_empty_production_runs(tmp_path: Path) -> None:
    database_path = tmp_path / "audit.db"
    create_audit_database(database_path)
    add_run(database_path, "initial-3y-dohmh-20260830-v1")
    add_run(database_path, "scheduled__2026-08-30T14:00:00+00:00")
    add_run(database_path, "incremental-dohmh-20260830-v1")
    add_run(database_path, "scheduled__failed", status="FAILED")
    add_run(database_path, "scheduled__empty", rows_received=0)

    selected = select_bronze_runs(database_path, "dohmh_inspections")

    assert [run.run_id for run in selected] == [
        "initial-3y-dohmh-20260830-v1",
        "scheduled__2026-08-30T14:00:00+00:00",
    ]
    assert selected[0].page_glob == (
        "s3a://example/bronze/inspections/"
        "run_id=initial-3y-dohmh-20260830-v1/page_offset=*.json"
    )
