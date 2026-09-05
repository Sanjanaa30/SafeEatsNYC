"""Select production Bronze files recorded by the ingestion audit database."""

from __future__ import annotations

import argparse
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path


PRODUCTION_RUN_PREFIXES = ("initial-3y-", "scheduled__")
SOURCE_NAMES = ("dohmh_inspections", "complaints_311")


@dataclass(frozen=True)
class BronzeRun:
    """One successful production ingestion run selected for Silver processing."""

    run_id: str
    source_name: str
    rows_received: int
    output_path: str

    @property
    def page_glob(self) -> str:
        """Return only raw response pages and exclude request.json."""

        s3a_path = self.output_path.replace("s3://", "s3a://", 1)
        return f"{s3a_path.rstrip('/')}/page_offset=*.json"


def is_production_run(run_id: str) -> bool:
    """Return whether a run belongs to the historical or scheduled dataset."""

    return run_id.startswith(PRODUCTION_RUN_PREFIXES)


def select_bronze_runs(database_path: Path, source_name: str) -> list[BronzeRun]:
    """Read successful, non-empty production runs for one source."""

    with sqlite3.connect(database_path) as connection:
        rows = connection.execute(
            """
            SELECT run_id, source_name, rows_received, output_path
            FROM ingestion_audit
            WHERE source_name = ?
              AND status = 'SUCCESS'
              AND rows_received > 0
            ORDER BY started_at, run_id
            """,
            (source_name,),
        ).fetchall()

    return [
        BronzeRun(
            run_id=row[0],
            source_name=row[1],
            rows_received=row[2],
            output_path=row[3],
        )
        for row in rows
        if is_production_run(row[0])
    ]


def parse_arguments() -> argparse.Namespace:
    """Read the optional audit database location."""

    parser = argparse.ArgumentParser(
        description="Show the production Bronze JSON pages selected for Phase 3."
    )
    parser.add_argument(
        "--audit-db",
        type=Path,
        default=Path(
            os.getenv("SAFEEATS_AUDIT_DB", "data/audit/ingestion_audit.db")
        ),
    )
    return parser.parse_args()


def main() -> None:
    """Print selected runs and their Spark-readable S3 paths."""

    arguments = parse_arguments()
    for source_name in SOURCE_NAMES:
        runs = select_bronze_runs(arguments.audit_db, source_name)
        print(f"{source_name}: {len(runs)} selected run(s)")
        for run in runs:
            print(f"  {run.run_id}: {run.rows_received} rows")
            print(f"    {run.page_glob}")


if __name__ == "__main__":
    main()
