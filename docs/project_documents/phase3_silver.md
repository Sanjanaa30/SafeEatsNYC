# Phase 3: Cleaning and geospatial matching

## Status

Phase 3 is complete for the verified three-year snapshot dated August 31, 2026.

The implementation reads successful production Bronze runs, cleans and
deduplicates both sources, writes typed Parquet to S3 Silver, preserves records
without coordinates, and matches complaints to restaurants only when the
nearest location is within 100 meters.

## Simple flow

```text
S3 Bronze inspections JSON
    -> build_inspections_silver.py
    -> clean + exact-row deduplication
    -> S3 Silver inspections Parquet

S3 Bronze complaints_311 JSON
    -> build_complaints_silver.py
    -> clean + newest unique_key deduplication
    -> S3 Silver complaints Parquet

Silver inspections + Silver complaints
    -> build_geospatial_matches.py
    -> nearby grid candidates + exact haversine distance
    -> match only when distance <= 100m
    -> preserve unmatched complaints
    -> S3 Silver complaint/restaurant matches
```

Docker supplies Java 21 and PySpark. Spark uses the AWS profile to read and
write S3. Airflow continues to schedule Bronze ingestion. Phase 3 jobs run as
isolated Docker Compose jobs so local Spark has predictable memory. Adding
Silver to the automatic full Airflow DAG belongs to the later full-DAG step.

## Important files

| File | Responsibility |
|---|---|
| `spark/session.py` | Creates Spark and refreshable AWS access for S3A. |
| `spark/schemas.py` | Defines explicit Bronze schemas and Silver types. |
| `spark/bronze_runs.py` | Selects successful production Bronze runs. |
| `spark/bronze_io.py` | Reads unchanged Socrata JSON-array page files. |
| `spark/inspection_cleaning.py` | Cleans inspection names, addresses, dates, numbers, and coordinates. |
| `spark/inspection_deduplication.py` | Removes only identical inspection/violation rows. |
| `spark/build_inspections_silver.py` | Writes and verifies inspections Parquet. |
| `spark/complaint_cleaning.py` | Cleans complaint categories, dates, boroughs, ZIPs, and coordinates. |
| `spark/complaint_deduplication.py` | Keeps the newest version of each complaint ID. |
| `spark/build_complaints_silver.py` | Writes and verifies complaint Parquet. |
| `spark/geospatial_matching.py` | Calculates nearest restaurant and haversine distance. |
| `spark/build_geospatial_matches.py` | Writes and verifies the final match dataset. |
| `spark/preview_*.py` | Performs read-only checks before production writes. |

## Bronze selection

Silver reads successful non-empty audit records whose run IDs begin with
`initial-3y-` or `scheduled__`. It excludes smoke tests, failed runs, manual
validation runs, `request.json`, and empty runs. Only
`page_offset=*.json` response files are read.

## Inspection rules and grain

The output remains at inspection/violation-row grain. Different violation codes
from one inspection remain legitimate separate rows. An
`inspection_violation_id` SHA-256 hash covers all original source fields, so
only identical source records are removed.

Original values remain traceable while Silver adds typed timestamps, integer
scores, double coordinates, quality statuses, cleaned addresses, Phase 1 name
normalization, reviewed aliases/co-brands, and year/month partitions.

## 311 rules and grain

The complaint output is one newest record per `unique_key`. It keeps Food
Poisoning, Food Establishment, and Rodent complaints; parses dates; cleans
borough and ZIP values; converts coordinates; and places valid complaints
without usable coordinates in a separate Silver path instead of deleting them.

## Geospatial policy

Each restaurant is represented by the latest valid location for its CAMIS. A
small grid produces nearby candidates efficiently, followed by an exact
haversine calculation.

```text
distance <= 100m -> MATCHED
distance > 100m  -> NO_RESTAURANT_WITHIN_THRESHOLD
no coordinates  -> NO_VALID_COORDINATES
```

Every valid complaint remains in the result. Proximity is an association, not
proof that the restaurant caused the complaint.

The real 1,000-row preview produced 652 matches, 348 unmatched complaints, and
136 candidates between 100 and 150 meters that were intentionally not matched.
This confirms that the 100-meter boundary is actively enforced.

## Verified results

### Inspections

| Check | Rows |
|---|---:|
| Bronze expected/read | 250,379 |
| Exact duplicates removed | 2,665 |
| Silver inspection/violation rows | 247,714 |
| Rejected | 0 |
| Parquet read-back | 247,714 |

Coordinate statuses: 244,225 valid, 1,031 missing, and 2,458 outside NYC.

### 311 complaints

| Check | Rows |
|---|---:|
| Bronze expected/read | 151,170 |
| Older duplicate versions removed | 939 |
| Unique complaints | 150,231 |
| Geospatial-ready | 149,286 |
| Without valid coordinates | 945 |
| Rejected | 0 |

### Final complaint/restaurant output

| Match status | Rows |
|---|---:|
| `MATCHED` | 101,757 |
| `NO_RESTAURANT_WITHIN_THRESHOLD` | 47,529 |
| `NO_VALID_COORDINATES` | 945 |
| Total/read-back | 150,231 |

The matcher considered 26,691 current restaurant locations. Final row count,
distinct complaint-ID count, and Parquet read-back count all equal 150,231.

## S3 layout

```text
s3://<bucket>/silver/
|-- inspections/run_id=<id>/
|   |-- quality_report.json
|   `-- data/inspection_year=YYYY/inspection_month=M/*.parquet
|-- complaints_311/run_id=<id>/
|   |-- quality_report.json
|   `-- data/complaint_year=YYYY/complaint_month=M/*.parquet
|-- complaints_311_without_valid_coordinates/run_id=<id>/data/...
`-- complaint_restaurant_matches/run_id=<id>/
    |-- quality_report.json
    `-- data/complaint_year=YYYY/complaint_month=M/*.parquet
```

Run IDs are immutable. Production jobs refuse to overwrite an existing prefix.

## Commands in order

Run from `E:\SafeEatsNYC` in the activated virtual environment.

### 1. Authenticate and start services

```powershell
aws login --profile safeeats-dev
docker-compose up -d
docker-compose ps
```

### 2. Pause Airflow's worker for an isolated local Spark job

```powershell
docker-compose stop airflow-worker
```

### 3. Preview and build inspections

```powershell
docker-compose run --rm --no-deps --entrypoint python airflow-worker `
  -m spark.preview_inspections --limit 100

docker-compose run --rm --no-deps --entrypoint python airflow-worker `
  -m spark.build_inspections_silver `
  --run-id inspections-silver-YYYYMMDD-v1
```

### 4. Preview and build complaints

```powershell
docker-compose run --rm --no-deps --entrypoint python airflow-worker `
  -m spark.preview_complaints --limit 100

docker-compose run --rm --no-deps --entrypoint python airflow-worker `
  -m spark.build_complaints_silver `
  --run-id complaints-silver-YYYYMMDD-v1
```

### 5. Preview and build geospatial matches

```powershell
docker-compose run --rm --no-deps --entrypoint python airflow-worker `
  -m spark.preview_geospatial_matches `
  --inspections-run-id inspections-silver-YYYYMMDD-v1 `
  --complaints-run-id complaints-silver-YYYYMMDD-v1 `
  --limit 1000 --threshold-meters 100

docker-compose run --rm --no-deps --entrypoint python airflow-worker `
  -m spark.build_geospatial_matches `
  --run-id complaint-restaurant-matches-YYYYMMDD-v1 `
  --inspections-run-id inspections-silver-YYYYMMDD-v1 `
  --complaints-run-id complaints-silver-YYYYMMDD-v1 `
  --threshold-meters 100
```

### 6. Restore and verify Airflow

```powershell
docker-compose start airflow-worker
docker-compose ps airflow-worker
```

### 7. Run all tests

```powershell
docker-compose exec airflow-worker python -m pytest `
  /opt/safeeats/tests -q -p no:cacheprovider
```

Verified result: `44 passed`.

## Local Spark warning

Spark 4.2 may print repeated BlockManager heartbeat `NullPointerException`
messages in this local container setup. The verified jobs continued and ended
with successful count reconciliation and Parquet read-back checks. Use the
final JSON `status` and process result: a success report is success; a final
traceback without that report is failure.

## Completion checklist

- [x] Inspection and complaint data are clean and explicitly typed.
- [x] Original values remain traceable.
- [x] Overlap is removed without collapsing legitimate violations.
- [x] Complaint duplicate IDs keep the newest version.
- [x] Parquet is partitioned by year and month.
- [x] Coordinate-less and unmatched complaints are preserved.
- [x] The 100-meter threshold is tested with synthetic and real samples.
- [x] Bronze, output, and read-back counts reconcile.
- [x] S3 quality reports exist.
- [x] The complete suite passes with 44 tests.

## Known limitations

- Nearest location does not prove responsibility for a complaint.
- Matching uses the latest valid CAMIS location, not a reconstructed historical
  location for every complaint date.
- The threshold should receive a larger manually labelled validation sample
  before causal or enforcement use.
- Silver is not automatically scheduled yet. The later full-DAG work must add
  retry-safe immutable-output handling before Airflow runs these jobs daily.

