"""Monthly, quality-gated refresh of the SafeEats B/C-risk model."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pendulum
from airflow.sdk import dag, get_current_context, task  # type: ignore[import-not-found]

from orchestration.run_context import safe_run_token

PROJECT_ROOT = Path(os.getenv("SAFEEATS_PROJECT_ROOT", "/opt/safeeats"))


def run_module(module: str, *arguments: str) -> None:
    subprocess.run(
        [sys.executable, "-m", module, *arguments],
        cwd=PROJECT_ROOT,
        check=True,
    )


@dag(
    dag_id="safeeats_monthly_model_refresh",
    description="Retrain, backtest, monitor, and safely promote restaurant risk scores.",
    schedule="0 14 1 * *",
    start_date=pendulum.datetime(2026, 10, 1, tz=ZoneInfo("America/New_York")),
    catchup=False,
    max_active_runs=1,
    default_args={
        "owner": "safeeats",
        "retries": 1,
        "retry_delay": timedelta(minutes=10),
    },
    tags=["safeeats", "ml", "monthly", "quality-gated"],
)
def safeeats_monthly_model_refresh():
    @task(task_id="refresh_model")
    def refresh_model() -> None:
        context = get_current_context()
        token = safe_run_token(context["run_id"])
        run_end = context.get("data_interval_end") or context["logical_date"]
        mature_through = run_end.date() - timedelta(days=45)
        test_start = mature_through - timedelta(days=90)
        threshold_start = test_start - timedelta(days=60)
        calibration_start = threshold_start - timedelta(days=60)

        prepared = f"prepared-{token}"
        logistic = f"logistic-{token}"
        comparison = f"comparison-{token}"
        final_model = f"xgboost-final-{token}"
        scores = f"current-risk-scores-{token}"

        run_module(
            "ml.prepare_training_data",
            "--run-id",
            prepared,
            "--test-start-date",
            test_start.isoformat(),
        )
        run_module(
            "ml.tune_calibrate_logistic",
            "--preparation-run-id",
            prepared,
            "--model-run-id",
            logistic,
            "--calibration-start-date",
            calibration_start.isoformat(),
            "--threshold-start-date",
            threshold_start.isoformat(),
            "--evaluation-end-date",
            mature_through.isoformat(),
        )
        run_module(
            "ml.compare_xgboost",
            "--preparation-run-id",
            prepared,
            "--logistic-run-id",
            logistic,
            "--comparison-run-id",
            comparison,
            "--calibration-start-date",
            calibration_start.isoformat(),
            "--threshold-start-date",
            threshold_start.isoformat(),
            "--evaluation-end-date",
            mature_through.isoformat(),
        )
        run_module(
            "ml.retrain_and_score",
            "--preparation-run-id",
            prepared,
            "--comparison-run-id",
            comparison,
            "--final-model-run-id",
            final_model,
            "--score-run-id",
            scores,
            "--mature-through-date",
            mature_through.isoformat(),
        )
        run_module(
            "ml.verify_final_outputs",
            "--final-model-run-id",
            final_model,
            "--score-run-id",
            scores,
        )
        run_module(
            "ml.monitor_model",
            "--comparison-run-id",
            comparison,
            "--score-run-id",
            scores,
        )
        run_module("ml.promote_scores", "--score-run-id", scores)

    refresh_model()


safeeats_monthly_model_refresh()
