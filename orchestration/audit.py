"""Stage-level audit records for the complete Airflow pipeline."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StageAuditRecord:
    pipeline_run_id: str
    stage_name: str
    attempt_number: int
    started_at: str
    completed_at: str | None
    status: str
    error_message: str | None


class PipelineAuditStore:
    """Store every downstream stage attempt in the existing audit database."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS pipeline_stage_audit (
                    pipeline_run_id TEXT NOT NULL,
                    stage_name TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    status TEXT NOT NULL CHECK (
                        status IN ('RUNNING', 'SUCCESS', 'FAILED')
                    ),
                    error_message TEXT,
                    PRIMARY KEY (pipeline_run_id, stage_name, attempt_number)
                )
                """
            )

    def start(
        self,
        pipeline_run_id: str,
        stage_name: str,
        attempt_number: int,
        started_at: str,
    ) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pipeline_stage_audit (
                    pipeline_run_id, stage_name, attempt_number,
                    started_at, completed_at, status, error_message
                ) VALUES (?, ?, ?, ?, NULL, 'RUNNING', NULL)
                ON CONFLICT(pipeline_run_id, stage_name, attempt_number)
                DO UPDATE SET started_at = excluded.started_at,
                    completed_at = NULL, status = 'RUNNING', error_message = NULL
                """,
                (pipeline_run_id, stage_name, attempt_number, started_at),
            )

    def finish(
        self,
        pipeline_run_id: str,
        stage_name: str,
        attempt_number: int,
        completed_at: str,
        status: str,
        error_message: str | None = None,
    ) -> None:
        if status not in {"SUCCESS", "FAILED"}:
            raise ValueError("Final stage status must be SUCCESS or FAILED.")
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE pipeline_stage_audit
                SET completed_at = ?, status = ?, error_message = ?
                WHERE pipeline_run_id = ? AND stage_name = ? AND attempt_number = ?
                """,
                (
                    completed_at,
                    status,
                    error_message[:4000] if error_message else None,
                    pipeline_run_id,
                    stage_name,
                    attempt_number,
                ),
            )

    def records(self, pipeline_run_id: str) -> list[StageAuditRecord]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM pipeline_stage_audit
                WHERE pipeline_run_id = ?
                ORDER BY stage_name, attempt_number
                """,
                (pipeline_run_id,),
            ).fetchall()
        return [StageAuditRecord(**dict(row)) for row in rows]
