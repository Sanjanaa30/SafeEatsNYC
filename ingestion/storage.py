"""Bronze storage backends for local development and Amazon S3."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Protocol

import boto3
from botocore.exceptions import ClientError


def s3_error_details(error: ClientError) -> tuple[str, int | None]:
    code = str(error.response.get("Error", {}).get("Code", ""))
    status = error.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code, status


class BronzeStorage(Protocol):
    """Minimal object operations required by the ingestion pipeline."""

    def uri(self, relative_key: str) -> str:
        """Return the user-facing location for an object or prefix."""

    def exists(self, relative_key: str) -> bool:
        """Return whether an object already exists."""

    def read_bytes(self, relative_key: str) -> bytes:
        """Read an existing object's bytes."""

    def write_bytes(self, relative_key: str, content: bytes) -> None:
        """Write bytes without silently replacing different content."""


def normalize_relative_key(relative_key: str) -> str:
    """Normalize one safe, relative object key."""

    normalized = relative_key.replace("\\", "/").strip("/")
    if not normalized or any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("Bronze object keys must be non-empty relative paths.")
    return normalized


class LocalBronzeStorage:
    """Atomic local-filesystem Bronze storage used by tests and development."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def _path(self, relative_key: str) -> Path:
        return self.root.joinpath(*normalize_relative_key(relative_key).split("/"))

    def uri(self, relative_key: str) -> str:
        return str(self._path(relative_key))

    def exists(self, relative_key: str) -> bool:
        return self._path(relative_key).is_file()

    def read_bytes(self, relative_key: str) -> bytes:
        return self._path(relative_key).read_bytes()

    def write_bytes(self, relative_key: str, content: bytes) -> None:
        path = self._path(relative_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError(f"Bronze object already has different content: {path}")
            return
        temporary_path = path.with_suffix(path.suffix + ".tmp")
        temporary_path.write_bytes(content)
        temporary_path.replace(path)


class S3BronzeStorage:
    """Private S3 Bronze storage using the standard boto3 credential chain."""

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str = "bronze",
        region: str | None = None,
        profile: str | None = None,
        client: Any | None = None,
    ) -> None:
        if not bucket or "/" in bucket:
            raise ValueError("A valid S3 bucket name is required.")
        self.bucket = bucket
        self.prefix = prefix.replace("\\", "/").strip("/")
        if client is not None:
            self.client = client
        else:
            session = boto3.Session(profile_name=profile, region_name=region)
            self.client = session.client("s3", region_name=region)

    def _key(self, relative_key: str) -> str:
        relative = normalize_relative_key(relative_key)
        return f"{self.prefix}/{relative}" if self.prefix else relative

    def uri(self, relative_key: str) -> str:
        return f"s3://{self.bucket}/{self._key(relative_key)}"

    def exists(self, relative_key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=self._key(relative_key))
            return True
        except ClientError as error:
            code, status = s3_error_details(error)
            if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
                return False
            raise

    def read_bytes(self, relative_key: str) -> bytes:
        response = self.client.get_object(
            Bucket=self.bucket,
            Key=self._key(relative_key),
        )
        return response["Body"].read()

    def write_bytes(self, relative_key: str, content: bytes) -> None:
        key = self._key(relative_key)
        try:
            self.client.put_object(
                Bucket=self.bucket,
                Key=key,
                Body=content,
                ContentType="application/json",
                ServerSideEncryption="AES256",
                Metadata={"sha256": hashlib.sha256(content).hexdigest()},
                IfNoneMatch="*",
            )
        except ClientError as error:
            code, status = s3_error_details(error)
            if code not in {"PreconditionFailed", "412"} and status != 412:
                raise
            if self.read_bytes(relative_key) != content:
                raise ValueError(
                    "S3 Bronze object already has different content: "
                    f"s3://{self.bucket}/{key}"
                ) from error


# this script is imported by pipeline.py
