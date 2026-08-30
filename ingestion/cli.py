"""
Command-line interface shared by the two Phase 2 ingestion jobs.
This script acts as the control center for running data downloads. 
Instead of hardcoding settings or dates into your code, it lets you trigger data ingestion from your terminal, 
customize how many rows to download at once, specify date ranges, and automatically track the results in an audit database.


That is a very clean update to your command-line interface script (cli.py).

By adding support for the --storage-backend argument (and checking whether to use LocalBronzeStorage or S3BronzeStorage), 
this file now acts as a complete bridge between your terminal inputs and the flexible storage backends you defined earlier!
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from ingestion.audit import AuditStore
from ingestion.pipeline import (
    DEFAULT_INITIAL_LOOKBACK_DAYS,
    DEFAULT_OVERLAP_DAYS,
    DEFAULT_PAGE_SIZE,
    parse_timestamp,
    run_ingestion,
)
from ingestion.sources import SourceConfig
from ingestion.storage import BronzeStorage, LocalBronzeStorage, S3BronzeStorage

# project_root(): Finds where your project folders live on your computer (checking environment variables first, or falling back to the default folder structure).
def project_root() -> Path:
    configured = os.getenv("SAFEEATS_PROJECT_ROOT")
    if configured:
        return Path(configured).resolve()
    return Path(__file__).resolve().parents[1]

# default_run_id(): Generates a unique tracking ID using the current UTC timestamp (e.g., manual__dohmh_inspections__20260829T105313Z) so every run has a unique name.
def default_run_id(source_name: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"manual__{source_name}__{timestamp}"


def optional_timestamp(value: str | None) -> datetime | None:
    return parse_timestamp(value) if value else None


def select_storage(arguments: argparse.Namespace) -> BronzeStorage:
    if arguments.storage_backend == "local":
        return LocalBronzeStorage(arguments.bronze_root)
    if not arguments.s3_bucket:
        raise SystemExit(
            "S3 storage requires --s3-bucket or SAFEEATS_S3_BUCKET."
        )
    return S3BronzeStorage(
        bucket=arguments.s3_bucket,
        prefix=arguments.s3_prefix,
        region=arguments.aws_region,
        profile=arguments.aws_profile,
    )

# build_parser(): Builds the command-line argument parser for the given source configuration.
def build_parser(source: SourceConfig) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=f"Ingest {source.name} into SafeEats Bronze storage."
    )
    root = project_root()
    configured_bronze_root = os.getenv("SAFEEATS_BRONZE_ROOT")
    configured_bucket = os.getenv("SAFEEATS_S3_BUCKET")
    default_backend = os.getenv(
        "SAFEEATS_STORAGE_BACKEND",
        "s3" if configured_bucket else "local",
    ).lower()
    parser.add_argument("--run-id", default=None) # The unique tracking ID for this ingestion run.
    parser.add_argument("--start-timestamp", default=None) # The start timestamp for the date range of data to ingest.
    parser.add_argument("--end-timestamp", default=None)
    parser.add_argument(
        "--page-size", # The number of rows to download at a time.
        type=int,
        default=int(os.getenv("SAFEEATS_INGESTION_PAGE_SIZE", DEFAULT_PAGE_SIZE)),
    )
    parser.add_argument(
        "--overlap-days", # The number of days of overlap to include in the data download.
        type=int,
        default=int(os.getenv("SAFEEATS_OVERLAP_DAYS", DEFAULT_OVERLAP_DAYS)),
    )
    parser.add_argument(
        "--initial-lookback-days", # The number of days to look back for the initial data download.
        type=int,
        default=int(
            os.getenv(
                "SAFEEATS_INITIAL_LOOKBACK_DAYS",
                DEFAULT_INITIAL_LOOKBACK_DAYS,
            )
        ),
    )
    parser.add_argument(
        "--storage-backend",
        choices=("local", "s3"),
        default=default_backend,
        help="Bronze destination. Use s3 for the project architecture.",
    )
    parser.add_argument(
        "--bronze-root", # The root directory for the bronze layer of the data lake.
        type=Path,
        default=Path(configured_bronze_root or root / "data" / "bronze"),
    )
    parser.add_argument("--s3-bucket", default=configured_bucket)
    parser.add_argument(
        "--s3-prefix",
        default=os.getenv("SAFEEATS_S3_PREFIX", "bronze"),
    )
    parser.add_argument("--aws-region", default=os.getenv("AWS_REGION"))
    parser.add_argument("--aws-profile", default=os.getenv("AWS_PROFILE"))
    parser.add_argument(
        "--audit-db", # The path to the audit database file.
        type=Path,
        default=Path(
            os.getenv(
                "SAFEEATS_AUDIT_DB",
                root / "data" / "audit" / "ingestion_audit.db", # The default location for the audit database file. 
            )
        ),
    )
    return parser

#Environment & Logging: Loads your .env file (which keeps secret tokens secure) and sets up standard terminal logging so you can see progress messages.
# Parsing Arguments: Reads whatever options you typed into the terminal.
# run_ingestion(...): Kicks off the actual data pipeline, connecting to NYC Open Data using your source rules, applying your custom dates/page sizes, and attaching your API app token securely.
# Printing Results: Once the ingestion finishes, it formats the audit summary into clean JSON and prints it out to your terminal screen.
def run_cli(source: SourceConfig) -> int:
    """Parse arguments, run one source, and print its audit result."""

    load_dotenv(project_root() / ".env")
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    arguments = build_parser(source).parse_args()
    run_id = arguments.run_id or default_run_id(source.name)
    explicit_start = optional_timestamp(arguments.start_timestamp)
    run_end = optional_timestamp(arguments.end_timestamp)
    storage = select_storage(arguments)

    result = run_ingestion(
        source=source,
        run_id=run_id,
        storage=storage,
        audit_database=arguments.audit_db,
        page_size=arguments.page_size,
        overlap_days=arguments.overlap_days,
        initial_lookback_days=arguments.initial_lookback_days,
        explicit_start=explicit_start,
        run_end=run_end,
        app_token=os.getenv("NYC_OPEN_DATA_APP_TOKEN"),
    )
    print(json.dumps(AuditStore.as_dict(result), indent=2, sort_keys=True))
    return 0

# This script is imported by the two ingestion entry points (ingest_dohmh.py and ingest_311.py) to provide a shared command-line interface for running data ingestion jobs. It handles argument parsing, logging, and invoking the ingestion pipeline with the appropriate configuration for each data source.  
