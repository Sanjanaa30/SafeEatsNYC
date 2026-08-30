"""
Bronze object storage backends for local development and Amazon S3.
This script defines how and where your raw downloaded data files (Bronze layer) are stored. 
It gives your ingestion pipeline two interchangeable options: saving them locally on your computer's hard drive or securely in an Amazon S3 cloud bucket.

"""

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

# BronzeStorage (Protocol): It dictates that any storage backend you build must have four basic methods:
# uri(): Return the file location address.
# exists(): Check if a file is already there.
# read_bytes(): Read an existing file's contents.
# write_bytes(): Save a file safely.

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

# normalize_relative_key(): A helper function that cleans up file paths. 
# It replaces Windows backslashes (\) with forward slashes (/), blocks empty paths, and prevents security tricks like .. (directory traversal) to keep your file paths clean and safe.
def normalize_relative_key(relative_key: str) -> str:
    """Normalize one safe, relative object key."""

    normalized = relative_key.replace("\\", "/").strip("/")
    if not normalized or any(
        part in {"", ".", ".."} for part in normalized.split("/")
    ):
        raise ValueError("Bronze object keys must be non-empty relative paths.")
    return normalized

# LocalBronzeStorage: Used for your local computer development and testing:
# _path(): Combines your root folder with the normalized file path.
# write_bytes(): Writes files safely using atomic patterns. If a file already exists, it checks if the content is identical. If someone tries to overwrite an existing file with different data, it throws an error to prevent data corruption.
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

# S3BronzeStorage: Used if you want to push your raw data into an AWS S3 cloud bucket:
# Initialization: Connects using standard AWS credentials (boto3), allows custom regions/profiles, and sets up a folder prefix (like s3://my-bucket/bronze/...).
# exists(): Checks if a file exists in S3, gracefully handling standard AWS errors (like 404 or NoSuchKey).
# read_bytes(): Streams and downloads file contents directly from S3.
# write_bytes(): Uploads files to S3 with enterprise security features:
# Enables server-side encryption (AES256).
# Automatically calculates and saves a sha256 hash signature as metadata to verify file integrity.
# Uses an IfNoneMatch="*" condition. If the exact same file is uploaded twice, it succeeds quietly.
# If a file with different content already exists at that path, it safely blocks it and raises an error.

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
