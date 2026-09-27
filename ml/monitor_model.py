"""Check model quality, subgroup stability, and score drift before promotion."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone

import boto3
from dotenv import load_dotenv


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--comparison-run-id", required=True)
    parser.add_argument("--score-run-id", required=True)
    return parser.parse_args()


def ratio(current: float, expected: float) -> float | None:
    return current / expected if expected > 0 else None


def main() -> None:
    load_dotenv()
    selected = arguments()
    bucket = os.environ["SAFEEATS_S3_BUCKET"]
    session = boto3.Session(
        profile_name=os.getenv("AWS_PROFILE", "safeeats-dev"),
        region_name=os.getenv("AWS_REGION", "us-east-1"),
    )
    s3 = session.client("s3")

    comparison_key = f"ml/model_comparisons/run_id={selected.comparison_run_id}/comparison_report.json"
    score_prefix = f"ml/current_scores/run_id={selected.score_run_id}"
    score_report_key = f"{score_prefix}/scoring_report.json"
    comparison = json.loads(
        s3.get_object(Bucket=bucket, Key=comparison_key)["Body"].read()
    )
    score_report = json.loads(
        s3.get_object(Bucket=bucket, Key=score_report_key)["Body"].read()
    )
    evaluation = comparison["xgboost_details"]
    test = evaluation["test"]
    calibration = evaluation["calibration"]

    checks: list[dict] = []

    def check(
        name: str, passed: bool, value, requirement: str, severity: str = "FAIL"
    ) -> None:
        checks.append(
            {
                "name": name,
                "status": "PASS" if passed else severity,
                "value": value,
                "requirement": requirement,
            }
        )

    check("roc_auc", test["roc_auc"] >= 0.65, test["roc_auc"], ">= 0.65")
    check(
        "high_risk_precision",
        test["high_risk_metrics"]["precision"] >= 0.20,
        test["high_risk_metrics"]["precision"],
        ">= 0.20",
    )
    check(
        "watchlist_recall",
        test["moderate_or_higher_metrics"]["recall"] >= 0.60,
        test["moderate_or_higher_metrics"]["recall"],
        ">= 0.60",
    )
    base_rate = calibration["observed_grade_bc_rate"]
    baseline_brier = base_rate * (1 - base_rate)
    check(
        "probability_calibration",
        calibration["calibrated_brier_score"] < baseline_brier,
        calibration["calibrated_brier_score"],
        f"below no-skill Brier score {baseline_brier:.6f}",
    )

    boroughs = evaluation.get("robustness_checks", {}).get("by_borough", {})
    weak_boroughs = sorted(
        name
        for name, metrics in boroughs.items()
        if metrics.get("roc_auc") is not None and metrics["roc_auc"] < 0.55
    )
    check(
        "borough_consistency",
        not weak_boroughs,
        weak_boroughs,
        "no sufficiently sampled borough below 0.55 ROC-AUC",
        severity="WARN",
    )

    evaluation_counts = test["risk_tiers"]
    evaluation_total = sum(item["rows"] for item in evaluation_counts.values())
    current_counts = score_report["risk_category_counts"]
    current_total = score_report["eligible_restaurants_scored"]
    drift = {}
    for tier in ("MODERATE", "HIGH"):
        expected_share = evaluation_counts[tier]["rows"] / evaluation_total
        current_share = current_counts.get(tier, 0) / current_total
        share_ratio = ratio(current_share, expected_share)
        drift[tier] = {
            "evaluation_share": round(expected_share, 6),
            "current_share": round(current_share, 6),
            "ratio": round(share_ratio, 6) if share_ratio is not None else None,
        }
        check(
            f"{tier.lower()}_share_drift",
            share_ratio is not None and 0.5 <= share_ratio <= 2.0,
            drift[tier],
            "current share between 0.5x and 2.0x the held-out evaluation share",
            severity="WARN",
        )

    statuses = {item["status"] for item in checks}
    status = "FAIL" if "FAIL" in statuses else "WARN" if "WARN" in statuses else "PASS"
    report = {
        "status": status,
        "comparison_run_id": selected.comparison_run_id,
        "score_run_id": selected.score_run_id,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
        "score_distribution_drift": drift,
        "promotion_allowed": status != "FAIL",
    }
    key = f"ml/model_monitoring/run_id={selected.score_run_id}/monitoring_report.json"
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(report, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(json.dumps(report, indent=2))
    if status == "FAIL":
        raise RuntimeError(
            "Model monitoring failed; the score run was not approved for promotion."
        )


if __name__ == "__main__":
    main()
