"""Deterministic names shared by every stage of one pipeline run."""

from __future__ import annotations

import re
from datetime import datetime


def safe_run_token(value: str) -> str:
    """Convert an Airflow run ID into an S3-safe token."""

    token = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
    if not token:
        raise ValueError("Airflow supplied an empty run ID.")
    return token


def run_names(airflow_run_id: str, run_end: datetime) -> dict[str, str]:
    """Create immutable output IDs shared by all downstream tasks."""

    token = safe_run_token(airflow_run_id)
    return {
        "pipeline_run_id": airflow_run_id,
        "run_token": token,
        "inspections_silver_run_id": f"inspections-silver-{token}",
        "complaints_silver_run_id": f"complaints-silver-{token}",
        "matches_run_id": f"complaint-restaurant-matches-{token}",
        "scoring_date": run_end.date().isoformat(),
    }
