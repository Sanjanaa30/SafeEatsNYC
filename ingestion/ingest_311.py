"""CLI entry point for relevant NYC 311 complaint ingestion."""

from ingestion.cli import run_cli
from ingestion.sources import COMPLAINTS_311


if __name__ == "__main__":
    raise SystemExit(run_cli(COMPLAINTS_311))
