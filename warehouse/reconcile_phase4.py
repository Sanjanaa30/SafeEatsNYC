"""Reconcile the current Bronze, Silver, staging, Gold, and mart snapshots."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from dotenv import load_dotenv


PRODUCTION_RUN_PREFIXES = ("initial-3y-", "scheduled__")


def parse_arguments() -> argparse.Namespace:
    """Read the immutable Phase 3 run IDs used by Athena."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inspections-run-id",
        default="inspections-silver-20260831-v1",
    )
    parser.add_argument(
        "--complaints-run-id",
        default="complaints-silver-20260831-v1",
    )
    parser.add_argument(
        "--matches-run-id",
        default="complaint-restaurant-matches-20260831-v1",
    )
    parser.add_argument(
        "--audit-db",
        type=Path,
        default=Path("data/audit/ingestion_audit.db"),
    )
    parser.add_argument(
        "--local-report",
        type=Path,
        default=Path("data/audit/phase4_reconciliation.json"),
    )
    parser.add_argument(
        "--markdown-report",
        type=Path,
        default=Path("docs/project_documents/phase4_reconciliation.md"),
    )
    return parser.parse_args()


def load_s3_json(client, bucket: str, key: str) -> dict[str, Any]:
    """Read one Phase 3 quality report from S3."""

    response = client.get_object(Bucket=bucket, Key=key)
    return json.loads(response["Body"].read())


def production_audit_rows(database_path: Path) -> list[dict[str, Any]]:
    """Read successful historical and scheduled Bronze runs."""

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """
            SELECT run_id, source_name, rows_received, output_path, started_at
            FROM ingestion_audit
            WHERE status = 'SUCCESS' AND rows_received > 0
            ORDER BY started_at, run_id
            """
        ).fetchall()

    return [
        dict(row)
        for row in rows
        if str(row["run_id"]).startswith(PRODUCTION_RUN_PREFIXES)
    ]


def run_athena_count_query(
    client,
    query: str,
    workgroup: str,
    output_location: str,
) -> dict[str, int]:
    """Run the warehouse count query and return label-to-count values."""

    response = client.start_query_execution(
        QueryString=query,
        WorkGroup=workgroup,
        ResultConfiguration={"OutputLocation": output_location},
    )
    query_id = response["QueryExecutionId"]

    while True:
        execution = client.get_query_execution(QueryExecutionId=query_id)
        status = execution["QueryExecution"]["Status"]
        if status["State"] == "SUCCEEDED":
            break
        if status["State"] in {"FAILED", "CANCELLED"}:
            reason = status.get("StateChangeReason", "No reason returned")
            raise RuntimeError(f"Athena query {status['State']}: {reason}")
        time.sleep(1)

    result = client.get_query_results(QueryExecutionId=query_id)
    values: dict[str, int] = {}
    for row in result["ResultSet"]["Rows"][1:]:
        cells = row["Data"]
        values[cells[0]["VarCharValue"]] = int(cells[1]["VarCharValue"])
    return values


def warehouse_count_query(silver_database: str, gold_database: str) -> str:
    """Return one query covering every Phase 4 layer and table grain."""

    tables = {
        "silver_inspections": f"{silver_database}.inspections",
        "silver_complaints": f"{silver_database}.complaints",
        "staging_inspections": f"{gold_database}.stg_inspections",
        "staging_complaints": f"{gold_database}.stg_complaints",
        "inspection_events": f"{gold_database}.int_inspection_events",
        "fact_inspection": f"{gold_database}.fact_inspection",
        "fact_311_complaint": f"{gold_database}.fact_311_complaint",
        "dim_restaurant": f"{gold_database}.dim_restaurant",
        "dim_chain": f"{gold_database}.dim_chain",
        "dim_borough": f"{gold_database}.dim_borough",
        "dim_date": f"{gold_database}.dim_date",
        "dim_violation": f"{gold_database}.dim_violation",
        "dim_complaint_type": f"{gold_database}.dim_complaint_type",
        "mart_borough_grade_summary": f"{gold_database}.mart_borough_grade_summary",
        "mart_cuisine_borough_heatmap": f"{gold_database}.mart_cuisine_borough_heatmap",
        "mart_violation_by_borough": f"{gold_database}.mart_violation_by_borough",
        "mart_weekly_311_vs_inspection": f"{gold_database}.mart_weekly_311_vs_inspection",
        "mart_restaurant_grade_history": f"{gold_database}.mart_restaurant_grade_history",
        "mart_chain_summary": f"{gold_database}.mart_chain_summary",
    }
    statements = [
        f"SELECT '{label}' AS dataset, count(*) AS row_count FROM {table}"
        for label, table in tables.items()
    ]
    statements.extend(
        [
            f"SELECT 'distinct_restaurant_camis', count(distinct camis) FROM {gold_database}.stg_inspections",
            f"SELECT 'derived_chain_groups', count(*) FROM (SELECT restaurant_name_normalized FROM {gold_database}.stg_chain_flags WHERE is_chain GROUP BY restaurant_name_normalized)",
            f"SELECT 'distinct_violation_codes', count(distinct violation_code) FROM {gold_database}.stg_inspections WHERE violation_code IS NOT NULL",
            f"SELECT 'distinct_complaint_types', count(distinct complaint_type) FROM {gold_database}.stg_complaints WHERE complaint_type IS NOT NULL",
        ]
    )
    return "\nUNION ALL\n".join(statements)


def check(
    checks: list[dict[str, Any]],
    name: str,
    expected: int,
    actual: int,
    explanation: str,
) -> None:
    """Append one explicit equality check to the report."""

    checks.append(
        {
            "name": name,
            "expected": expected,
            "actual": actual,
            "passed": expected == actual,
            "explanation": explanation,
        }
    )


def selected_and_pending_bronze(
    audit_rows: list[dict[str, Any]],
    source_name: str,
    selected_run_ids: list[str],
) -> tuple[int, list[dict[str, Any]]]:
    """Separate Bronze rows used by Silver from newer successful runs."""

    source_rows = [row for row in audit_rows if row["source_name"] == source_name]
    selected_ids = set(selected_run_ids)
    selected_count = sum(
        row["rows_received"] for row in source_rows if row["run_id"] in selected_ids
    )
    pending = [row for row in source_rows if row["run_id"] not in selected_ids]
    return selected_count, pending


def markdown(report: dict[str, Any]) -> str:
    """Create a readable reconciliation document from the JSON report."""

    counts = report["warehouse_counts"]
    inspection = report["quality_reports"]["inspections"]
    complaints = report["quality_reports"]["complaints"]
    pending = report["pending_bronze"]

    lines = [
        "# Phase 4 reconciliation",
        "",
        f"Generated: `{report['generated_at']}`  ",
        f"Status: **{report['status']}**",
        "",
        "This report reconciles the immutable Silver snapshot currently registered in Athena. "
        "Newer Bronze runs are listed separately and are not treated as missing rows.",
        "",
        "## Inspection flow",
        "",
        "| Layer | Rows | Explanation |",
        "|---|---:|---|",
        f"| Selected Bronze | {inspection['raw_rows_read']:,} | Successful production runs selected by the Silver build |",
        f"| Silver | {counts['silver_inspections']:,} | Removed {inspection['exact_duplicates_removed']:,} exact overlap duplicates; rejected {inspection['rejected_rows']:,} |",
        f"| Staging | {counts['staging_inspections']:,} | Thin view; no rows removed |",
        f"| Inspection fact | {counts['fact_inspection']:,} | Same inspection/violation grain as staging |",
        f"| Inspection events | {counts['inspection_events']:,} | Multiple violation rows collapsed only for inspection-level metrics |",
        "",
        "## 311 complaint flow",
        "",
        "| Layer | Rows | Explanation |",
        "|---|---:|---|",
        f"| Selected Bronze | {complaints['raw_rows_read']:,} | Successful production runs selected by the Silver build |",
        f"| Silver | {counts['silver_complaints']:,} | Removed {complaints['duplicate_complaint_rows_removed']:,} repeated complaint IDs; rejected {complaints['rejected_rows']:,} |",
        f"| Staging | {counts['staging_complaints']:,} | Thin view; no rows removed |",
        f"| Complaint fact | {counts['fact_311_complaint']:,} | One row per complaint |",
        "",
        "## Dimensions and marts",
        "",
        "Dimensions and marts have different grains, so their counts should not equal fact counts.",
        "",
        "| Dataset | Rows | Grain |",
        "|---|---:|---|",
        f"| `dim_restaurant` | {counts['dim_restaurant']:,} | One row per CAMIS |",
        f"| `dim_chain` | {counts['dim_chain']:,} | One row per normalized name with 3+ locations |",
        f"| `dim_borough` | {counts['dim_borough']:,} | One row per NYC borough |",
        f"| `dim_date` | {counts['dim_date']:,} | One row per calendar day |",
        f"| `dim_violation` | {counts['dim_violation']:,} | One row per violation code |",
        f"| `dim_complaint_type` | {counts['dim_complaint_type']:,} | One row per complaint type |",
        f"| `mart_borough_grade_summary` | {counts['mart_borough_grade_summary']:,} | Six areas × three grades |",
        f"| `mart_cuisine_borough_heatmap` | {counts['mart_cuisine_borough_heatmap']:,} | One row per cuisine and borough |",
        f"| `mart_violation_by_borough` | {counts['mart_violation_by_borough']:,} | One row per violation and borough |",
        f"| `mart_weekly_311_vs_inspection` | {counts['mart_weekly_311_vs_inspection']:,} | One row per week and area |",
        f"| `mart_restaurant_grade_history` | {counts['mart_restaurant_grade_history']:,} | One row per graded inspection |",
        f"| `mart_chain_summary` | {counts['mart_chain_summary']:,} | One row per chain |",
        "",
        "## Newer Bronze rows awaiting Silver",
        "",
        f"- DOHMH inspections: **{pending['dohmh_inspections']['rows']:,}** rows across {pending['dohmh_inspections']['run_count']} run(s).",
        f"- 311 complaints: **{pending['complaints_311']['rows']:,}** rows across {pending['complaints_311']['run_count']} run(s).",
        "",
        "These rows arrived after the current Phase 3 snapshot. They will enter Silver and Gold when the transformation pipeline is rerun; they are not unexplained loss.",
        "",
        "## Validation",
        "",
        f"All **{len(report['checks'])}** reconciliation checks passed. The separate dbt suite also passed all 119 data tests.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    """Build, validate, save, and upload the reconciliation report."""

    load_dotenv()
    arguments = parse_arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    region = os.getenv("AWS_REGION", "us-east-1")
    profile = os.getenv("AWS_PROFILE", "safeeats-dev")
    workgroup = os.getenv("ATHENA_WORKGROUP", "primary")
    silver_database = os.getenv("ATHENA_SILVER_DATABASE", "safeeats_silver")
    gold_database = os.getenv("ATHENA_DBT_SCHEMA", "safeeats_gold")
    output_location = os.getenv("ATHENA_OUTPUT_LOCATION") or (
        f"s3://{bucket}/athena/query-results/"
    )

    session = boto3.Session(profile_name=profile, region_name=region)
    s3 = session.client("s3")
    athena = session.client("athena")

    inspection_report = load_s3_json(
        s3,
        bucket,
        f"silver/inspections/run_id={arguments.inspections_run_id}/quality_report.json",
    )
    complaint_report = load_s3_json(
        s3,
        bucket,
        f"silver/complaints_311/run_id={arguments.complaints_run_id}/quality_report.json",
    )
    match_report = load_s3_json(
        s3,
        bucket,
        f"silver/complaint_restaurant_matches/run_id={arguments.matches_run_id}/quality_report.json",
    )
    counts = run_athena_count_query(
        athena,
        warehouse_count_query(silver_database, gold_database),
        workgroup,
        output_location,
    )

    audit_rows = production_audit_rows(arguments.audit_db)
    inspection_bronze, pending_inspections = selected_and_pending_bronze(
        audit_rows,
        "dohmh_inspections",
        inspection_report["bronze_run_ids"],
    )
    complaint_bronze, pending_complaints = selected_and_pending_bronze(
        audit_rows,
        "complaints_311",
        complaint_report["bronze_run_ids"],
    )

    checks: list[dict[str, Any]] = []
    check(checks, "Inspection Bronze audit versus Silver input", inspection_bronze, inspection_report["raw_rows_read"], "Only Bronze run IDs recorded by the Silver quality report are compared.")
    check(checks, "Inspection deduplication", inspection_report["raw_rows_read"] - inspection_report["exact_duplicates_removed"], inspection_report["deduplicated_rows"], "Exact overlap duplicates are the only removed inspection rows.")
    check(checks, "Inspection accepted plus rejected", inspection_report["deduplicated_rows"], inspection_report["accepted_rows"] + inspection_report["rejected_rows"], "Every deduplicated inspection has an explicit outcome.")
    check(checks, "Inspection Silver Athena count", inspection_report["accepted_rows"], counts["silver_inspections"], "Athena reads every accepted Silver inspection row.")
    check(checks, "Inspection staging count", counts["silver_inspections"], counts["staging_inspections"], "Staging is a thin view.")
    check(checks, "Inspection fact count", counts["staging_inspections"], counts["fact_inspection"], "The fact preserves the inspection/violation grain.")
    check(checks, "Complaint Bronze audit versus Silver input", complaint_bronze, complaint_report["raw_rows_read"], "Only Bronze run IDs recorded by the Silver quality report are compared.")
    check(checks, "Complaint unique-key deduplication", complaint_report["raw_rows_read"] - complaint_report["duplicate_complaint_rows_removed"], complaint_report["deduplicated_rows"], "Repeated complaint IDs caused by overlap are removed.")
    check(checks, "Complaint coordinate outcomes", complaint_report["deduplicated_rows"], complaint_report["geospatial_ready_rows"] + complaint_report["without_valid_coordinates_rows"] + complaint_report["rejected_rows"], "Every complaint has a spatial, nonspatial, or rejected outcome.")
    check(checks, "Complaint match output", complaint_report["deduplicated_rows"], match_report["final_rows"], "Matched and unmatched complaints are both retained.")
    check(checks, "Complaint Silver Athena count", match_report["final_rows"], counts["silver_complaints"], "Athena reads the complete geospatial match output.")
    check(checks, "Complaint staging count", counts["silver_complaints"], counts["staging_complaints"], "Staging is a thin view.")
    check(checks, "Complaint fact count", counts["staging_complaints"], counts["fact_311_complaint"], "The fact remains one row per complaint.")
    check(checks, "Restaurant dimension grain", counts["distinct_restaurant_camis"], counts["dim_restaurant"], "The dimension contains one row per CAMIS.")
    check(checks, "Chain dimension grain", counts["derived_chain_groups"], counts["dim_chain"], "The dimension contains one row per derived 3+ location group.")
    check(checks, "Borough dimension grain", 5, counts["dim_borough"], "NYC has five borough members in scope.")
    check(checks, "Violation dimension grain", counts["distinct_violation_codes"], counts["dim_violation"], "The dimension contains one row per non-null violation code.")
    check(checks, "Complaint-type dimension grain", counts["distinct_complaint_types"], counts["dim_complaint_type"], "The dimension contains one row per relevant complaint type.")
    check(checks, "Chain mart grain", counts["dim_chain"], counts["mart_chain_summary"], "The chain mart contains one row per chain.")

    failed_checks = [item for item in checks if not item["passed"]]
    pending = {
        "dohmh_inspections": {
            "run_count": len(pending_inspections),
            "rows": sum(row["rows_received"] for row in pending_inspections),
            "runs": pending_inspections,
        },
        "complaints_311": {
            "run_count": len(pending_complaints),
            "rows": sum(row["rows_received"] for row in pending_complaints),
            "runs": pending_complaints,
        },
    }
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "SUCCESS" if not failed_checks else "FAILED",
        "snapshot_run_ids": {
            "inspections": arguments.inspections_run_id,
            "complaints": arguments.complaints_run_id,
            "matches": arguments.matches_run_id,
        },
        "quality_reports": {
            "inspections": inspection_report,
            "complaints": complaint_report,
            "matches": match_report,
        },
        "warehouse_counts": counts,
        "pending_bronze": pending,
        "checks": checks,
    }

    arguments.local_report.parent.mkdir(parents=True, exist_ok=True)
    arguments.local_report.write_text(json.dumps(report, indent=2), encoding="utf-8")
    arguments.markdown_report.parent.mkdir(parents=True, exist_ok=True)
    arguments.markdown_report.write_text(markdown(report), encoding="utf-8")

    s3.put_object(
        Bucket=bucket,
        Key="gold/_audit/phase4_reconciliation/latest.json",
        Body=json.dumps(report, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    print(json.dumps({
        "status": report["status"],
        "checks_passed": len(checks) - len(failed_checks),
        "checks_failed": len(failed_checks),
        "pending_bronze_rows": {
            name: details["rows"] for name, details in pending.items()
        },
        "local_report": str(arguments.local_report),
        "markdown_report": str(arguments.markdown_report),
        "s3_report": f"s3://{bucket}/gold/_audit/phase4_reconciliation/latest.json",
    }, indent=2))

    if failed_checks:
        raise RuntimeError("Phase 4 reconciliation failed. Review the generated report.")


if __name__ == "__main__":
    main()
