"""Register the current SafeEats Silver Parquet snapshots in Athena."""

from __future__ import annotations

import argparse
import os
import time

import boto3
from dotenv import load_dotenv


INSPECTIONS_COLUMNS = """
    inspection_violation_id string,
    camis string,
    restaurant_name_original string,
    restaurant_name_normalized string,
    fast_food_brand_names array<string>,
    is_reviewed_co_brand boolean,
    is_fast_food boolean,
    borough string,
    address_display string,
    zipcode string,
    cuisine_description string,
    inspection_date timestamp,
    violation_code string,
    violation_description string,
    critical_flag string,
    score integer,
    grade string,
    inspection_type string,
    latitude double,
    longitude double,
    coordinate_status string
"""

COMPLAINT_COLUMNS = """
    unique_key string,
    created_date timestamp,
    closed_date timestamp,
    complaint_type string,
    descriptor string,
    location_type string,
    incident_zip string,
    incident_address string,
    borough string,
    status string,
    latitude double,
    longitude double,
    restaurant_camis string,
    matched_restaurant_name string,
    matched_restaurant_name_normalized string,
    matched_restaurant_address string,
    restaurant_latitude double,
    restaurant_longitude double,
    nearest_candidate_distance_meters double,
    match_distance_meters double,
    restaurant_match_status string,
    match_threshold_meters double
"""


def arguments() -> argparse.Namespace:
    """Read the immutable Phase 3 input run IDs."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspections-run-id",
        default="inspections-silver-20260831-v1",
    )
    parser.add_argument(
        "--matches-run-id",
        default="complaint-restaurant-matches-20260831-v1",
    )
    return parser.parse_args()


def run_query(client, sql: str, output_location: str, workgroup: str) -> None:
    """Run one Athena statement and wait for a clear result."""

    response = client.start_query_execution(
        QueryString=sql,
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": output_location},
    )
    query_id = response["QueryExecutionId"]
    while True:
        execution = client.get_query_execution(QueryExecutionId=query_id)
        status = execution["QueryExecution"]["Status"]
        state = status["State"]
        if state == "SUCCEEDED":
            print(f"SUCCEEDED: {sql.splitlines()[0]} ({query_id})")
            return
        if state in {"FAILED", "CANCELLED"}:
            reason = status.get("StateChangeReason", "No reason returned")
            raise RuntimeError(f"Athena {state}: {reason} ({query_id})")
        time.sleep(1)


def external_table_sql(
    database: str,
    table: str,
    columns: str,
    partitions: str,
    location: str,
) -> str:
    """Build a readable external Parquet table statement."""

    return f"""CREATE EXTERNAL TABLE IF NOT EXISTS {database}.{table} (
{columns}
)
PARTITIONED BY ({partitions})
STORED AS PARQUET
LOCATION '{location}'
TBLPROPERTIES ('parquet.compress'='SNAPPY')"""


def main() -> None:
    """Create databases, register tables, and discover their partitions."""

    load_dotenv()
    selected = arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    region = os.getenv("AWS_REGION", "us-east-1")
    workgroup = os.getenv("ATHENA_WORKGROUP", "primary")
    silver_database = os.getenv("ATHENA_SILVER_DATABASE", "safeeats_silver")
    gold_database = os.getenv("ATHENA_DBT_SCHEMA", "safeeats_gold")
    output_location = os.getenv(
        "ATHENA_OUTPUT_LOCATION",
        f"s3://{bucket}/athena/query-results/",
    )
    if not output_location:
        output_location = f"s3://{bucket}/athena/query-results/"

    client = boto3.Session(profile_name=profile, region_name=region).client(
        "athena"
    )
    inspection_location = (
        f"s3://{bucket}/silver/inspections/"
        f"run_id={selected.inspections_run_id}/data/"
    )
    match_location = (
        f"s3://{bucket}/silver/complaint_restaurant_matches/"
        f"run_id={selected.matches_run_id}/data/"
    )
    statements = [
        f"CREATE DATABASE IF NOT EXISTS {silver_database}",
        f"CREATE DATABASE IF NOT EXISTS {gold_database}",
        external_table_sql(
            silver_database,
            "inspections",
            INSPECTIONS_COLUMNS,
            "inspection_year integer, inspection_month integer",
            inspection_location,
        ),
        f"MSCK REPAIR TABLE {silver_database}.inspections",
        external_table_sql(
            silver_database,
            "complaints",
            COMPLAINT_COLUMNS,
            "complaint_year integer, complaint_month integer",
            match_location,
        ),
        f"MSCK REPAIR TABLE {silver_database}.complaints",
    ]
    for statement in statements:
        run_query(client, statement, output_location, workgroup)

    print("Athena Silver tables are ready:")
    print(f"  {silver_database}.inspections -> {inspection_location}")
    print(f"  {silver_database}.complaints -> {match_location}")
    print(f"dbt target database is ready: {gold_database}")


if __name__ == "__main__":
    main()

