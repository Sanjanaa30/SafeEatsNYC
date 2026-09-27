"""Small AWS checks used during Phase 7 application setup."""

import time

import boto3

from api.config import Settings
from api.schemas.health import DependencyHealth


class AwsDependencyChecker:
    """Check S3 access and execute one bounded Athena query."""

    def __init__(self, session: boto3.Session, settings: Settings) -> None:
        self.settings = settings
        self.s3 = session.client("s3", region_name=settings.aws_region)
        self.athena = session.client("athena", region_name=settings.aws_region)

    def check(self, timeout_seconds: int = 30) -> DependencyHealth:
        """Return success only after both AWS services respond correctly."""

        self.s3.head_bucket(Bucket=self.settings.safeeats_s3_bucket)
        response = self.athena.start_query_execution(
            QueryString="SELECT 1 AS connectivity_check",
            QueryExecutionContext={"Database": self.settings.athena_dbt_schema},
            WorkGroup=self.settings.athena_workgroup,
            ResultConfiguration={
                "OutputLocation": self.settings.query_output_location,
            },
        )
        execution_id = response["QueryExecutionId"]
        deadline = time.monotonic() + timeout_seconds

        while time.monotonic() < deadline:
            execution = self.athena.get_query_execution(QueryExecutionId=execution_id)[
                "QueryExecution"
            ]
            state = execution["Status"]["State"]
            if state == "SUCCEEDED":
                return DependencyHealth(
                    status="ok",
                    s3="reachable",
                    athena="reachable",
                )
            if state in {"FAILED", "CANCELLED"}:
                reason = execution["Status"].get("StateChangeReason", state)
                raise RuntimeError(f"Athena connectivity query failed: {reason}")
            time.sleep(1)

        self.athena.stop_query_execution(QueryExecutionId=execution_id)
        raise TimeoutError("Athena connectivity query exceeded 30 seconds.")
