"""
CLI entry point for downloading and ingesting the live NYC DOHMH 
(Department of Health and Mental Hygiene) restaurant inspection data into your pipeline.

"""

from ingestion.cli import run_cli
from ingestion.sources import DOHMH_INSPECTIONS


if __name__ == "__main__":
    raise SystemExit(run_cli(DOHMH_INSPECTIONS))
