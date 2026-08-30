"""Phase 2 ingestion, audit, pagination, and idempotency tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import requests

from ingestion.audit import AuditStore
from ingestion.pipeline import (
    build_retrying_session,
    run_ingestion,
    safe_run_id,
    validate_records,
)
from ingestion.sources import COMPLAINTS_311, DOHMH_INSPECTIONS


RUN_END = datetime(2026, 8, 28, 12, 0, tzinfo=timezone.utc)
RUN_START = datetime(2026, 8, 1, 0, 0, tzinfo=timezone.utc)


class FakeResponse:
    def __init__(self, content: bytes, status_code: int = 200) -> None:
        self.content = content
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses
        self.calls: list[dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        if not self.responses:
            raise AssertionError("Unexpected API request.")
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def inspection_record(camis: str, timestamp: str) -> dict[str, str]:
    return {
        "camis": camis,
        "inspection_date": timestamp,
        "dba": f"Restaurant {camis}",
    }


def encoded(records: list[dict[str, str]]) -> bytes:
    return json.dumps(records, separators=(",", ":")).encode("utf-8")


def run_paths(tmp_path: Path) -> tuple[Path, Path]:
    return tmp_path / "bronze", tmp_path / "audit" / "audit.db"


def test_paginates_and_preserves_exact_response_pages(tmp_path: Path) -> None:
    first_content = encoded(
        [
            inspection_record("1", "2026-08-02T00:00:00.000"),
            inspection_record("2", "2026-08-03T00:00:00.000"),
        ]
    )
    second_content = encoded(
        [inspection_record("3", "2026-08-04T00:00:00.000")]
    )
    session = FakeSession(
        [FakeResponse(first_content), FakeResponse(second_content)]
    )
    bronze_root, audit_database = run_paths(tmp_path)

    result = run_ingestion(
        source=DOHMH_INSPECTIONS,
        run_id="scheduled__2026-08-28T12:00:00+00:00",
        bronze_root=bronze_root,
        audit_database=audit_database,
        page_size=2,
        explicit_start=RUN_START,
        run_end=RUN_END,
        session=session,  # type: ignore[arg-type]
    )

    output = Path(result.output_path)
    assert result.status == "SUCCESS"
    assert result.rows_requested == 4
    assert result.rows_received == 3
    assert result.page_count == 2
    assert (output / "page_offset=000000000.json").read_bytes() == first_content
    assert (output / "page_offset=000000002.json").read_bytes() == second_content
    assert [call["params"]["$offset"] for call in session.calls] == [0, 2]


def test_successful_run_id_is_idempotent(tmp_path: Path) -> None:
    bronze_root, audit_database = run_paths(tmp_path)
    first_session = FakeSession(
        [
            FakeResponse(
                encoded([inspection_record("1", "2026-08-02T00:00:00.000")])
            )
        ]
    )
    first = run_ingestion(
        source=DOHMH_INSPECTIONS,
        run_id="same-run",
        bronze_root=bronze_root,
        audit_database=audit_database,
        page_size=2,
        explicit_start=RUN_START,
        run_end=RUN_END,
        session=first_session,  # type: ignore[arg-type]
    )
    second_session = FakeSession([])

    second = run_ingestion(
        source=DOHMH_INSPECTIONS,
        run_id="same-run",
        bronze_root=bronze_root,
        audit_database=audit_database,
        page_size=2,
        explicit_start=RUN_START,
        run_end=RUN_END,
        session=second_session,  # type: ignore[arg-type]
    )

    assert second == first
    assert second_session.calls == []


def test_failed_run_resumes_existing_pages(tmp_path: Path) -> None:
    bronze_root, audit_database = run_paths(tmp_path)
    first_page = encoded(
        [
            inspection_record("1", "2026-08-02T00:00:00.000"),
            inspection_record("2", "2026-08-03T00:00:00.000"),
        ]
    )
    failing_session = FakeSession(
        [FakeResponse(first_page), FakeResponse(b"error", status_code=503)]
    )
    arguments = {
        "source": DOHMH_INSPECTIONS,
        "run_id": "retry-run",
        "bronze_root": bronze_root,
        "audit_database": audit_database,
        "page_size": 2,
        "explicit_start": RUN_START,
        "run_end": RUN_END,
    }

    with pytest.raises(requests.HTTPError):
        run_ingestion(**arguments, session=failing_session)  # type: ignore[arg-type]

    failed = AuditStore(audit_database).get_run(
        "retry-run", DOHMH_INSPECTIONS.name
    )
    assert failed is not None and failed.status == "FAILED"

    final_page = encoded(
        [inspection_record("3", "2026-08-04T00:00:00.000")]
    )
    retry_session = FakeSession([FakeResponse(final_page)])
    result = run_ingestion(
        **arguments,
        session=retry_session,  # type: ignore[arg-type]
    )

    assert result.status == "SUCCESS"
    assert result.rows_received == 3
    assert len(retry_session.calls) == 1
    assert retry_session.calls[0]["params"]["$offset"] == 2


def test_next_run_uses_success_watermark_and_overlap(tmp_path: Path) -> None:
    bronze_root, audit_database = run_paths(tmp_path)
    first_session = FakeSession(
        [
            FakeResponse(
                encoded([inspection_record("1", "2026-08-20T00:00:00.000")])
            )
        ]
    )
    run_ingestion(
        source=DOHMH_INSPECTIONS,
        run_id="first",
        bronze_root=bronze_root,
        audit_database=audit_database,
        page_size=2,
        explicit_start=RUN_START,
        run_end=RUN_END,
        session=first_session,  # type: ignore[arg-type]
    )
    second_session = FakeSession([FakeResponse(b"[]")])

    run_ingestion(
        source=DOHMH_INSPECTIONS,
        run_id="second",
        bronze_root=bronze_root,
        audit_database=audit_database,
        page_size=2,
        overlap_days=2,
        run_end=datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc),
        session=second_session,  # type: ignore[arg-type]
    )

    where_clause = second_session.calls[0]["params"]["$where"]
    assert "inspection_date >= '2026-08-18T00:00:00.000'" in where_clause
    assert "inspection_date < '2026-08-29T12:00:00.000'" in where_clause


def test_validation_failure_is_audited_and_not_written(tmp_path: Path) -> None:
    bronze_root, audit_database = run_paths(tmp_path)
    session = FakeSession([FakeResponse(encoded([{"camis": "1"}]))])

    with pytest.raises(ValueError, match="required fields"):
        run_ingestion(
            source=DOHMH_INSPECTIONS,
            run_id="invalid",
            bronze_root=bronze_root,
            audit_database=audit_database,
            page_size=2,
            explicit_start=RUN_START,
            run_end=RUN_END,
            session=session,  # type: ignore[arg-type]
        )

    record = AuditStore(audit_database).get_run(
        "invalid", DOHMH_INSPECTIONS.name
    )
    assert record is not None and record.status == "FAILED"
    assert "missing required fields" in (record.error_message or "")
    assert not list(bronze_root.rglob("page_*.json"))


def test_311_rejects_unexpected_complaint_type() -> None:
    with pytest.raises(ValueError, match="unexpected complaint type"):
        validate_records(
            [
                {
                    "unique_key": "1",
                    "created_date": "2026-08-20T00:00:00.000",
                    "complaint_type": "Noise",
                }
            ],
            COMPLAINTS_311,
            100,
        )


def test_retrying_session_configures_transient_statuses() -> None:
    session = build_retrying_session("token")
    retry = session.adapters["https://"].max_retries

    assert retry.total == 5
    assert 429 in retry.status_forcelist
    assert session.headers["X-App-Token"] == "token"
    session.close()


def test_run_id_is_sanitized_to_one_path_component() -> None:
    assert safe_run_id("scheduled__2026-08-28T12:00:00+00:00") == (
        "scheduled__2026-08-28T12_00_00_00_00"
    )
    with pytest.raises(ValueError):
        safe_run_id("///")
