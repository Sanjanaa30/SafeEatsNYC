"""Tests for Phase 6 stage-level audit records."""

from orchestration.audit import PipelineAuditStore


def test_stage_attempts_preserve_failure_and_retry(tmp_path):
    store = PipelineAuditStore(tmp_path / "ingestion_audit.db")
    store.start("run-1", "build_gold", 1, "2026-09-06T10:00:00+00:00")
    store.finish(
        "run-1",
        "build_gold",
        1,
        "2026-09-06T10:01:00+00:00",
        "FAILED",
        "temporary failure",
    )
    store.start("run-1", "build_gold", 2, "2026-09-06T10:06:00+00:00")
    store.finish(
        "run-1",
        "build_gold",
        2,
        "2026-09-06T10:07:00+00:00",
        "SUCCESS",
    )

    records = store.records("run-1")
    assert [record.status for record in records] == ["FAILED", "SUCCESS"]
    assert records[0].error_message == "temporary failure"
    assert records[1].error_message is None
