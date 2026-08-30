"""S3 Bronze storage tests that never contact AWS.

This script tests your S3 storage backend and pipeline integration completely offline without ever touching or connecting to real Amazon Web Services (AWS). 
It uses clever mock objects to simulate how S3 behaves.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import requests
from botocore.exceptions import ClientError

from ingestion.pipeline import run_ingestion
from ingestion.sources import DOHMH_INSPECTIONS
from ingestion.storage import S3BronzeStorage

# FakeS3Client: A simulated in-memory S3 bucket. It mimics real AWS methods like head_object (checking if a file exists), get_object (reading a file), and put_object (writing a file). 
# It even simulates AWS error codes (like 404 for missing files or 412 for conflicting overwrites).
class FakeS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.put_calls: list[dict[str, Any]] = []

    def head_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        if (Bucket, Key) not in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "404", "Message": "Not Found"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "HeadObject",
            )
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def put_object(self, **kwargs: Any) -> dict[str, Any]:
        location = (kwargs["Bucket"], kwargs["Key"])
        if location in self.objects and kwargs.get("IfNoneMatch") == "*":
            raise ClientError(
                {
                    "Error": {
                        "Code": "PreconditionFailed",
                        "Message": "Already exists",
                    },
                    "ResponseMetadata": {"HTTPStatusCode": 412},
                },
                "PutObject",
            )
        self.put_calls.append(kwargs)
        self.objects[location] = bytes(kwargs["Body"])
        return {"ETag": "fake"}

# FakeResponse & FakeSession: Fake network response objects that feed pre-determined dummy data to your pipeline instead of calling the live NYC Open Data API.
class FakeResponse:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        """Raises an exception if the HTTP status code indicates an error."""
        return None

# FakeSession: A fake HTTP session object that returns pre-determined responses when the pipeline tries to fetch data from the NYC Open Data API.
class FakeSession:
    def __init__(self, responses: list[FakeResponse]) -> None:
        self.responses = responses

    def get(self, _url: str, **_kwargs: Any) -> FakeResponse:
        return self.responses.pop(0)

    def close(self) -> None:
        return None

# Test: S3 storage correctly preserves bytes and refuses overwrites with different content.
# What it tests:
# - Verifies that writing to fake S3 correctly applies server-side encryption (AES256), sets unique sha256 metadata tags, and uses conditional writing (IfNoneMatch="*") to prevent duplicates.
# - Confirms that writing the exact same content twice succeeds quietly, but trying to overwrite a file with different data raises a ValueError.

def test_s3_storage_preserves_bytes_and_refuses_different_overwrite() -> None:
    client = FakeS3Client()
    storage = S3BronzeStorage(
        bucket="safeeats-test",
        prefix="bronze",
        client=client,
    )
    relative_key = "inspections/run_id=test/page_offset=000000000.json"

    assert not storage.exists(relative_key)
    storage.write_bytes(relative_key, b'[{"camis":"1"}]')

    assert storage.exists(relative_key)
    assert storage.read_bytes(relative_key) == b'[{"camis":"1"}]'
    assert storage.uri(relative_key) == (
        "s3://safeeats-test/bronze/inspections/run_id=test/"
        "page_offset=000000000.json"
    )
    assert client.put_calls[0]["ServerSideEncryption"] == "AES256"
    assert client.put_calls[0]["IfNoneMatch"] == "*"
    assert "sha256" in client.put_calls[0]["Metadata"]

    storage.write_bytes(relative_key, b'[{"camis":"1"}]')
    with pytest.raises(ValueError, match="different content"):
        storage.write_bytes(relative_key, b'[{"camis":"2"}]')

# Test: The pipeline correctly writes the manifest and exact page to S3.
# What it tests:
# - Verifies that the ingestion pipeline correctly writes the manifest file (request.json) and the exact page of data to the fake S3 storage.
# - Confirms that the manifest contains the correct source name and that the page data is written as expected.  
def test_pipeline_writes_manifest_and_exact_page_to_s3(tmp_path: Path) -> None:
    client = FakeS3Client()
    storage = S3BronzeStorage(
        bucket="safeeats-test",
        prefix="bronze",
        client=client,
    )
    raw_page = b'[{"camis":"1","inspection_date":"2026-08-02T00:00:00.000"}]'

    result = run_ingestion(
        source=DOHMH_INSPECTIONS,
        run_id="s3-run",
        storage=storage,
        audit_database=tmp_path / "audit.db",
        page_size=100,
        explicit_start=datetime(2026, 8, 1, tzinfo=timezone.utc),
        run_end=datetime(2026, 8, 3, tzinfo=timezone.utc),
        session=FakeSession([FakeResponse(raw_page)]),  # type: ignore[arg-type]
    )

    prefix = "bronze/inspections/ingest_date=2026-08-03/run_id=s3-run"
    manifest_key = ("safeeats-test", f"{prefix}/request.json")
    page_key = ("safeeats-test", f"{prefix}/page_offset=000000000.json")

    assert result.status == "SUCCESS"
    assert result.output_path == (
        "s3://safeeats-test/bronze/inspections/"
        "ingest_date=2026-08-03/run_id=s3-run"
    )
    assert json.loads(client.objects[manifest_key])[
        "source_name"
    ] == "dohmh_inspections"
    assert client.objects[page_key] == raw_page
