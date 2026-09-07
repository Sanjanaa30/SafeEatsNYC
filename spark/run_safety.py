"""Safe S3 retry behavior for versioned Spark outputs."""

from __future__ import annotations

import json
from typing import Any

from botocore.exceptions import ClientError


def successful_report(client, bucket: str, report_key: str) -> dict[str, Any] | None:
    """Return an existing successful report, or None when it is absent."""

    try:
        response = client.get_object(Bucket=bucket, Key=report_key)
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
            return None
        raise
    report = json.loads(response["Body"].read())
    return report if report.get("status") == "SUCCESS" else None


def delete_exact_prefix(client, bucket: str, prefix: str) -> int:
    """Delete objects only below one already validated, run-specific prefix."""

    deleted = 0
    continuation_token = None
    while True:
        request: dict[str, Any] = {"Bucket": bucket, "Prefix": f"{prefix.rstrip('/')}/"}
        if continuation_token:
            request["ContinuationToken"] = continuation_token
        response = client.list_objects_v2(**request)
        objects = [{"Key": item["Key"]} for item in response.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=bucket, Delete={"Objects": objects, "Quiet": True})
            deleted += len(objects)
        if not response.get("IsTruncated"):
            return deleted
        continuation_token = response["NextContinuationToken"]


def prepare_run_output(
    client,
    bucket: str,
    output_prefixes: list[str],
    report_key: str,
    retry_incomplete: bool,
) -> dict[str, Any] | None:
    """Reuse success or clear only this run's incomplete output before retry."""

    report = successful_report(client, bucket, report_key)
    if report is not None:
        return report

    existing = []
    for prefix in output_prefixes:
        response = client.list_objects_v2(
            Bucket=bucket,
            Prefix=f"{prefix.rstrip('/')}/",
            MaxKeys=1,
        )
        if response.get("KeyCount", 0):
            existing.append(prefix)

    if existing and not retry_incomplete:
        raise FileExistsError(
            "Incomplete output already exists; use --retry-incomplete to safely "
            f"clear this exact run: s3://{bucket}/{existing[0]}/"
        )
    for prefix in existing:
        delete_exact_prefix(client, bucket, prefix)
    return None
