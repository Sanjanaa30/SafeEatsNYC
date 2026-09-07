"""Trigger the complete SafeEats DAG without PowerShell JSON quoting issues."""

from __future__ import annotations

import argparse
import json
import subprocess


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--test-retry-once", action="store_true")
    arguments = parser.parse_args()

    configuration = {"test_retry_once": arguments.test_retry_once}
    subprocess.run(
        [
            "airflow",
            "dags",
            "trigger",
            "--run-id",
            arguments.run_id,
            "--conf",
            json.dumps(configuration),
            "safeeats_daily_pipeline",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()
