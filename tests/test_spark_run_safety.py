"""Offline tests for safe Spark retry handling in S3."""

import io
import json

from botocore.exceptions import ClientError

from spark.run_safety import prepare_run_output


class FakeS3:
    def __init__(self, objects=None):
        self.objects = dict(objects or {})

    def get_object(self, *, Bucket, Key):
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404"}}, "GetObject")
        return {"Body": io.BytesIO(self.objects[Key])}

    def list_objects_v2(self, *, Bucket, Prefix, MaxKeys=None, **kwargs):
        matches = [key for key in self.objects if key.startswith(Prefix)]
        if MaxKeys is not None:
            matches = matches[:MaxKeys]
        return {
            "KeyCount": len(matches),
            "Contents": [{"Key": key} for key in matches],
            "IsTruncated": False,
        }

    def delete_objects(self, *, Bucket, Delete):
        for item in Delete["Objects"]:
            self.objects.pop(item["Key"], None)


def test_successful_run_is_reused_without_deletion():
    report = {"status": "SUCCESS", "accepted_rows": 10}
    client = FakeS3({"silver/x/run_id=1/quality_report.json": json.dumps(report).encode()})

    found = prepare_run_output(
        client,
        "bucket",
        ["silver/x/run_id=1"],
        "silver/x/run_id=1/quality_report.json",
        retry_incomplete=True,
    )

    assert found == report
    assert client.objects


def test_retry_removes_only_the_same_incomplete_run():
    client = FakeS3(
        {
            "silver/x/run_id=failed/data/part.parquet": b"partial",
            "silver/x/run_id=previous/data/part.parquet": b"good",
        }
    )

    found = prepare_run_output(
        client,
        "bucket",
        ["silver/x/run_id=failed"],
        "silver/x/run_id=failed/quality_report.json",
        retry_incomplete=True,
    )

    assert found is None
    assert "silver/x/run_id=failed/data/part.parquet" not in client.objects
    assert "silver/x/run_id=previous/data/part.parquet" in client.objects
