"""Reliable paginated NYC Open Data ingestion into Bronze object storage."""
# This module contains the core logic for paginated ingestion of NYC Open Data into the Bronze storage layer.
# It handles timestamp parsing, window building, retrying HTTP sessions, and record validation.
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ingestion.audit import AuditRecord, AuditStore
from ingestion.sources import SourceConfig
from ingestion.storage import BronzeStorage, LocalBronzeStorage


LOGGER = logging.getLogger(__name__)
DEFAULT_PAGE_SIZE = 10_000
DEFAULT_OVERLAP_DAYS = 2
DEFAULT_INITIAL_LOOKBACK_DAYS = 3 * 365
RETRYABLE_STATUS_CODES = (429, 500, 502, 503, 504)


@dataclass(frozen=True)
class IngestionWindow:
    """Frozen lower and upper source timestamps for one logical run."""

    start: datetime
    end: datetime
    where_clause: str


def utc_now() -> datetime:
    """Return an aware UTC timestamp; isolated for deterministic tests."""

    return datetime.now(timezone.utc)

# Clean up and format dates so they match exactly what the Socrata API expects.
def parse_timestamp(value: str) -> datetime:
    """Parse Socrata or ISO timestamps and normalize them to UTC."""

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)

# Format timestamps for use in Socrata SoQL predicates.
def format_socrata_timestamp(value: datetime) -> str:
    """Format an aware timestamp for a Socrata SoQL predicate."""

    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000")

# Clean up orchestrator run IDs to make them safe for use in file paths.
def safe_run_id(run_id: str) -> str:
    """Convert an orchestrator run ID into one safe path component."""

    safe_value = re.sub(r"[^A-Za-z0-9._-]+", "_", run_id).strip("._")
    if not safe_value:
        raise ValueError("run_id must contain at least one path-safe character.")
    return safe_value[:180]


def select_storage(
    storage: BronzeStorage | None,
    bronze_root: Path | None,
) -> BronzeStorage:
    if storage is not None and bronze_root is not None:
        raise ValueError("Provide storage or bronze_root, not both.")
    if storage is not None:
        return storage
    return LocalBronzeStorage(bronze_root or Path("data") / "bronze")


def build_run_prefix(source: SourceConfig, ingest_date: str, run_id: str) -> str:
    return "/".join(
        (
            source.bronze_directory,
            f"ingest_date={ingest_date}",
            f"run_id={safe_run_id(run_id)}",
        )
    )

# Create a retrying HTTP session for making requests to the NYC Open Data API.
# build_retrying_session(): Sets up an intelligent network session that automatically retries if the API fails due to temporary connection drops or server errors (status codes like 429, 500, etc.).
def build_retrying_session(app_token: str | None = None) -> requests.Session:
    """Create a session that retries transient NYC API failures."""

    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1,
        status_forcelist=RETRYABLE_STATUS_CODES,
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(
        {
            "Accept": "application/json",
            "User-Agent": "SafeEatsNYC-ingestion/1.0",
        }
    )
    if app_token:
        session.headers["X-App-Token"] = app_token
    return session

# build_window(): Defines the time range and SQL-like filter for the data extraction, ensuring that only the relevant records are fetched based on the last successful ingestion and any explicit start times provided.
def build_window(
    *,
    source: SourceConfig,
    audit_store: AuditStore,
    run_end: datetime,
    explicit_start: datetime | None,
    overlap_days: int,
    initial_lookback_days: int,
) -> IngestionWindow:
    """Build a bounded initial or incremental extraction window."""

    if overlap_days < 0 or initial_lookback_days <= 0:
        raise ValueError("Window day settings must be positive or zero.")

    previous_value = audit_store.last_successful_timestamp(source.name)
    if explicit_start is not None:
        start = explicit_start
    elif previous_value is not None:
        start = parse_timestamp(previous_value) - timedelta(days=overlap_days)
    else:
        start = run_end - timedelta(days=initial_lookback_days)

    start = start.astimezone(timezone.utc)
    run_end = run_end.astimezone(timezone.utc)
    if start >= run_end:
        raise ValueError("The ingestion start must be earlier than its end.")

    timestamp_predicate = (
        f"{source.timestamp_field} >= '{format_socrata_timestamp(start)}' "
        f"AND {source.timestamp_field} < '{format_socrata_timestamp(run_end)}'"
    )
    where_clause = (
        f"({source.base_where}) AND ({timestamp_predicate})"
        if source.base_where
        else timestamp_predicate
    )
    return IngestionWindow(start=start, end=run_end, where_clause=where_clause)

# validate_records(): Checks each record in the API response to ensure it conforms to the expected format and required fields for the source.
def validate_records(
    records: Any,
    source: SourceConfig,
    page_size: int,
) -> list[dict[str, Any]]:
    """Validate one decoded API page against its source contract."""

    if not isinstance(records, list):
        raise TypeError("NYC Open Data response must be a JSON list.")
    if len(records) > page_size:
        raise ValueError("API returned more records than the requested page size.")

    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise TypeError(f"Record {index} is not a JSON object.")
        missing = source.required_fields - record.keys()
        if missing:
            raise ValueError(
                f"Record {index} is missing required fields: {sorted(missing)}"
            )
        if (
            source.allowed_complaint_types is not None
            and record["complaint_type"] not in source.allowed_complaint_types
        ):
            raise ValueError(
                "311 response contained an unexpected complaint type: "
                f"{record['complaint_type']!r}"
            )
    return records

# decode_and_validate_page(): Decodes the raw bytes of an API response into JSON and then validates the records against the source contract.
def decode_and_validate_page(
    content: bytes,
    source: SourceConfig,
    page_size: int,
) -> list[dict[str, Any]]:
    """Decode a raw response only for validation and audit calculations."""

    try:
        decoded = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("API response is not valid UTF-8 JSON.") from error
    return validate_records(decoded, source, page_size)

# write_manifest(): Writes immutable request metadata through the selected storage backend.
# Setup & Storage Selection
# Validates parameters and sets up either local storage (LocalBronzeStorage) or cloud storage (S3BronzeStorage).
# Generates a unique run path folder structure.
def write_manifest(
    storage: BronzeStorage,
    relative_key: str,
    manifest: dict[str, Any],
) -> None:
    """Persist and validate immutable request metadata for idempotent retries."""

    serialized = json.dumps(manifest, sort_keys=True, indent=2).encode("utf-8")
    if storage.exists(relative_key):
        existing = json.loads(storage.read_bytes(relative_key).decode("utf-8"))
        if existing != manifest:
            raise ValueError(
                "Existing Bronze run directory has different request metadata."
            )
        return
    storage.write_bytes(relative_key, serialized)

# max_source_timestamp(): Determines the maximum timestamp from a page of validated records, comparing it with an existing watermark to advance the ingestion progress.
def max_source_timestamp(
    records: list[dict[str, Any]],
    source: SourceConfig,
    current: datetime | None,
) -> datetime | None:
    """Advance a watermark using validated records from one page."""

    values = [parse_timestamp(record[source.timestamp_field]) for record in records]
    page_max = max(values) if values else None
    if current is None:
        return page_max
    if page_max is None:
        return current
    return max(current, page_max)

# run_ingestion(): The main entry point for ingesting data from a source. 
# It orchestrates the entire ingestion process, including building the window, fetching pages, validating records, writing files, and updating the audit state.
def run_ingestion(
    *,
    source: SourceConfig,
    run_id: str,
    audit_database: Path,
    bronze_root: Path | None = None,
    storage: BronzeStorage | None = None,
    page_size: int = DEFAULT_PAGE_SIZE,
    overlap_days: int = DEFAULT_OVERLAP_DAYS,
    initial_lookback_days: int = DEFAULT_INITIAL_LOOKBACK_DAYS,
    explicit_start: datetime | None = None,
    run_end: datetime | None = None,
    app_token: str | None = None,
    session: requests.Session | None = None,
) -> AuditRecord:
    """Ingest one source, preserving exact pages and recording audit state."""

    if page_size <= 0 or page_size > 50_000:
        raise ValueError("page_size must be between 1 and 50,000.")
    active_storage = select_storage(storage, bronze_root)

    started = utc_now()
    bounded_end = (run_end or started).astimezone(timezone.utc)
    store = AuditStore(audit_database)
    ingest_date = bounded_end.date().isoformat()
    run_prefix = build_run_prefix(source, ingest_date, run_id)
    output_location = active_storage.uri(run_prefix)
    existing = store.get_run(run_id, source.name)
    if existing and existing.status == "SUCCESS":
        if existing.output_path != output_location:
            raise ValueError(
                "A successful run_id cannot be reused with a different Bronze destination."
            )
        LOGGER.info("Returning prior successful run %s/%s", run_id, source.name)
        return existing

    window = build_window(
        source=source,
        audit_store=store,
        run_end=bounded_end,
        explicit_start=explicit_start,
        overlap_days=overlap_days,
        initial_lookback_days=initial_lookback_days,
    )
    request_order = ", ".join(
        f"{field} ASC" for field in source.order_fields
    )
    manifest = {
        "api_url": source.api_url,
        "order": request_order,
        "page_size": page_size,
        "run_id": run_id,
        "source_name": source.name,
        "where": window.where_clause,
        "window_end": bounded_end.isoformat(),
        "window_start": window.start.isoformat(),
    }

    store.start(
        run_id=run_id,
        source_name=source.name,
        started_at=started.isoformat(),
        output_path=output_location,
        request_where=window.where_clause,
    )

    rows_requested = 0
    rows_received = 0
    page_count = 0
    watermark: datetime | None = None
    owned_session = session is None
    active_session = session or build_retrying_session(app_token)

    try:
        manifest_key = f"{run_prefix}/request.json"
        write_manifest(active_storage, manifest_key, manifest)
        offset = 0

        while True:
            page_key = f"{run_prefix}/page_offset={offset:09d}.json"
            page_exists = active_storage.exists(page_key)
            if page_exists:
                raw_content = active_storage.read_bytes(page_key)
                LOGGER.info(
                    "Reusing validated Bronze page %s",
                    active_storage.uri(page_key),
                )
            else:
                parameters = {
                    "$limit": page_size,
                    "$offset": offset,
                    "$order": request_order,
                    "$where": window.where_clause,
                }
                LOGGER.info(
                    "Requesting %s offset=%s limit=%s",
                    source.name,
                    offset,
                    page_size,
                )
                response = active_session.get(
                    source.api_url,
                    params=parameters,
                    timeout=(10, 120),
                )
                rows_requested += page_size
                response.raise_for_status()
                raw_content = response.content

            records = decode_and_validate_page(
                raw_content,
                source,
                page_size,
            )
            if not page_exists:
                active_storage.write_bytes(page_key, raw_content)

            page_count += 1
            rows_received += len(records)
            watermark = max_source_timestamp(records, source, watermark)

            if len(records) < page_size:
                break
            offset += page_size

        previous = store.last_successful_timestamp(source.name)
        final_watermark = watermark
        if previous is not None:
            previous_timestamp = parse_timestamp(previous)
            if final_watermark is None or previous_timestamp > final_watermark:
                final_watermark = previous_timestamp

        completed = utc_now().isoformat()
        record = store.succeed(
            run_id=run_id,
            source_name=source.name,
            completed_at=completed,
            rows_requested=rows_requested,
            rows_received=rows_received,
            page_count=page_count,
            last_source_timestamp=(
                final_watermark.isoformat() if final_watermark else None
            ),
        )
        LOGGER.info(
            "Completed %s: rows=%s pages=%s output=%s",
            source.name,
            rows_received,
            page_count,
            output_location,
        )
        return record
    except Exception as error:
        store.fail(
            run_id=run_id,
            source_name=source.name,
            completed_at=utc_now().isoformat(),
            error_message=f"{type(error).__name__}: {error}",
        )
        LOGGER.exception("Ingestion failed for %s", source.name)
        raise
    finally:
        if owned_session:
            active_session.close()
