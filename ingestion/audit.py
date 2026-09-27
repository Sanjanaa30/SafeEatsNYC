"""SQLite-backed ingestion audit state and incremental watermarks."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AuditRecord:
    """One source execution within a logical pipeline run."""

    run_id: str
    source_name: str
    started_at: str
    completed_at: str | None
    rows_requested: int
    rows_received: int
    page_count: int
    last_source_timestamp: str | None
    output_path: str
    request_where: str
    status: str
    error_message: str | None


class AuditStore:
    """Persist audit records safely across independent ingestion tasks."""

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
                CREATE TABLE IF NOT EXISTS ingestion_audit (
                    run_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    rows_requested INTEGER NOT NULL DEFAULT 0,
                    rows_received INTEGER NOT NULL DEFAULT 0,
                    page_count INTEGER NOT NULL DEFAULT 0,
                    last_source_timestamp TEXT,
                    output_path TEXT NOT NULL,
                    request_where TEXT NOT NULL,
                    status TEXT NOT NULL CHECK (
                        status IN ('RUNNING', 'SUCCESS', 'FAILED')
                    ),
                    error_message TEXT,
                    PRIMARY KEY (run_id, source_name)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_audit_success_watermark
                ON ingestion_audit (
                    source_name,
                    status,
                    last_source_timestamp
                )
                """
            )

    @staticmethod
    def _record(row: sqlite3.Row | None) -> AuditRecord | None:
        return AuditRecord(**dict(row)) if row is not None else None

    def get_run(self, run_id: str, source_name: str) -> AuditRecord | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM ingestion_audit
                WHERE run_id = ? AND source_name = ?
                """,
                (run_id, source_name),
            ).fetchone()
        return self._record(row)

    def last_successful_timestamp(self, source_name: str) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT last_source_timestamp
                FROM ingestion_audit
                WHERE source_name = ?
                  AND status = 'SUCCESS'
                  AND last_source_timestamp IS NOT NULL
                ORDER BY last_source_timestamp DESC
                LIMIT 1
                """,
                (source_name,),
            ).fetchone()
        return str(row[0]) if row is not None else None

    def start(
        self,
        *,
        run_id: str,
        source_name: str,
        started_at: str,
        output_path: str,
        request_where: str,
    ) -> AuditRecord:
        existing = self.get_run(run_id, source_name)
        if existing and existing.request_where != request_where:
            raise ValueError(
                "A run_id cannot be reused with different request parameters."
            )
        if existing and existing.status == "SUCCESS":
            return existing

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO ingestion_audit (
                    run_id, source_name, started_at, completed_at,
                    rows_requested, rows_received, page_count,
                    last_source_timestamp, output_path, request_where,
                    status, error_message
                ) VALUES (?, ?, ?, NULL, 0, 0, 0, NULL, ?, ?, 'RUNNING', NULL)
                ON CONFLICT(run_id, source_name) DO UPDATE SET
                    started_at = excluded.started_at,
                    completed_at = NULL,
                    rows_requested = 0,
                    rows_received = 0,
                    page_count = 0,
                    last_source_timestamp = NULL,
                    output_path = excluded.output_path,
                    status = 'RUNNING',
                    error_message = NULL
                """,
                (
                    run_id,
                    source_name,
                    started_at,
                    output_path,
                    request_where,
                ),
            )
        record = self.get_run(run_id, source_name)
        if record is None:
            raise RuntimeError("Failed to create ingestion audit record.")
        return record

    def succeed(
        self,
        *,
        run_id: str,
        source_name: str,
        completed_at: str,
        rows_requested: int,
        rows_received: int,
        page_count: int,
        last_source_timestamp: str | None,
    ) -> AuditRecord:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_audit
                SET completed_at = ?, rows_requested = ?, rows_received = ?,
                    page_count = ?, last_source_timestamp = ?,
                    status = 'SUCCESS', error_message = NULL
                WHERE run_id = ? AND source_name = ?
                """,
                (
                    completed_at,
                    rows_requested,
                    rows_received,
                    page_count,
                    last_source_timestamp,
                    run_id,
                    source_name,
                ),
            )
        record = self.get_run(run_id, source_name)
        if record is None:
            raise RuntimeError("Failed to complete ingestion audit record.")
        return record

    def fail(
        self,
        *,
        run_id: str,
        source_name: str,
        completed_at: str,
        error_message: str,
    ) -> AuditRecord:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE ingestion_audit
                SET completed_at = ?, status = 'FAILED', error_message = ?
                WHERE run_id = ? AND source_name = ?
                """,
                (
                    completed_at,
                    error_message[:4000],
                    run_id,
                    source_name,
                ),
            )
        record = self.get_run(run_id, source_name)
        if record is None:
            raise RuntimeError("Failed to record ingestion failure.")
        return record

    @staticmethod
    def as_dict(record: AuditRecord) -> dict[str, Any]:
        return asdict(record)
