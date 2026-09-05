# SafeEats NYC

SafeEats NYC is a restaurant-safety and consumer-intelligence platform that
combines NYC restaurant inspections, relevant 311 complaints, geographic
references, and reviewed restaurant-brand mappings.

The project currently has completed scope/discovery, AWS S3 ingestion, and
Silver transformation phases. Bronze data is collected through Python and
Airflow, while isolated PySpark jobs in Docker build typed Parquet in S3 Silver.

## Project goals

The MVP is designed to help users:

1. Look up a restaurant's current grade and inspection history.
2. Compare restaurant-safety patterns across NYC boroughs.
3. Examine relationships between relevant 311 complaints and inspection
   outcomes.
4. Identify restaurants that may be at risk of receiving a B or C grade.

The planned Streamlit dashboard has four pages:

1. City and Borough Safety Overview
2. Violations and 311 Correlation
3. SafeEats Restaurant Finder
4. Predictive Risk

The current visual reference is the
[dashboard HTML mockup](docs/project_documents/safeeats_dashboard_mockup.html).

## Current status

| Phase | Status | Result |
|---|---|---|
| Phase 1: Setup, discovery, profiling, and scope | Complete | APIs, dataset grain, reference data, name normalization, co-brand handling, assumptions, and MVP scope were validated and documented. |
| Phase 2: Data ingestion | Complete | Historical and incremental DOHMH/311 JSON is written to private S3 Bronze through retryable, audited, idempotent Python jobs and an Airflow DAG. |
| Phase 3: Silver transformation | Complete | Clean, typed, deduplicated Parquet and 100-meter complaint/restaurant matches are verified in S3 Silver. |
| Later phases | Not started | dbt Gold models, Athena access, Streamlit implementation, and predictive-risk modeling. |

Verified Phase 2 results:

- 32 automated tests passed.
- Three-year DOHMH load: 247,877 rows in 25 data pages.
- Three-year relevant 311 load: 150,098 rows in 16 data pages.
- Incremental loading uses the latest successful source timestamp with a
  two-day overlap.
- Airflow success, failure, automatic retry, incremental, and same-run
  idempotency behavior were verified.
- Rerunning the same Airflow run did not add S3 object versions or overwrite
  raw data.

Verified Phase 3 results:

- 44 automated tests passed.
- 250,379 Bronze inspection rows became 247,714 Silver
  inspection/violation rows after removing 2,665 exact duplicates.
- 151,170 Bronze 311 rows became 150,231 unique complaints after removing 939
  older duplicate versions.
- 101,757 complaints matched a restaurant within 100 meters; 47,529 remained
  unmatched and 945 coordinate-less complaints were preserved.
- Every production Parquet read-back count matched its expected output count.

## Architecture

### Implemented through Phase 3

```text
NYC DOHMH API ---------+
                       |
                       v
                 Python ingestion
                       |
NYC 311 API ----------+|------> private Amazon S3 Bronze JSON
                       |
                       +------> SQLite ingestion audit/watermarks

Docker Compose
    |
    +--> Airflow scheduler --> Redis queue --> Airflow worker
    |                                            |
    +--> Airflow API/UI                          +--> runs Python ingestion
    |
    +--> PostgreSQL Airflow metadata

S3 Bronze JSON
    |
    +--> isolated PySpark jobs in the Docker Airflow image
             |
             +--> S3 Silver inspections Parquet
             +--> S3 Silver 311 Parquet
             `--> S3 Silver complaint/restaurant matches
```

### Planned end-to-end platform

```text
NYC APIs
   -> Amazon S3 Bronze JSON
   -> PySpark Silver Parquet
   -> dbt Gold models
   -> Amazon Athena
   -> Streamlit dashboard
```

Docker, Airflow, and S3 have different responsibilities:

- Docker Desktop provides the local containers.
- Airflow schedules and coordinates the ingestion tasks.
- Python requests, validates, and writes the source responses.
- S3 permanently stores the unchanged Bronze JSON.
- PySpark cleans, types, deduplicates, and geospatially matches Silver data.
- S3 stores versioned, partitioned Silver Parquet and quality reports.
- PostgreSQL stores Airflow's internal metadata.
- SQLite stores SafeEats ingestion audit records and incremental watermarks.
- Redis temporarily passes scheduled tasks to the Airflow worker.

## Data sources

| Source | Dataset ID | Phase 2 selection | Incremental field |
|---|---|---|---|
| NYC DOHMH Restaurant Inspection Results | `43nn-pn8j` | All bounded inspection rows | `inspection_date` |
| NYC 311 Service Requests | `erm2-nwe9` | Food Poisoning, Food Establishment, and Rodent complaints | `created_date` |
| NYC geographic boundaries | Multiple static datasets | Borough, ZIP/ZCTA, and NTA references | Manual refresh |
| OpenStreetMap brand references | Overpass API | Reviewed fast-food/QSR brands | Manual refresh |

DOHMH Bronze remains at the original API-row grain; Phase 2 does not collapse
multiple violation rows into one restaurant or inspection row. Relevant 311
Bronze remains one service request per `unique_key`.

## Bronze storage layout

```text
s3://<private-bucket>/bronze/
|-- inspections/
|   `-- ingest_date=YYYY-MM-DD/
|       `-- run_id=<run-id>/
|           |-- request.json
|           `-- page_offset=000000000.json
`-- complaints_311/
    `-- ingest_date=YYYY-MM-DD/
        `-- run_id=<run-id>/
            |-- request.json
            `-- page_offset=000000000.json
```

- `ingest_date` is the download date, not necessarily the source-event date.
- `run_id` identifies one logical pipeline execution.
- `request.json` records the exact source window and request settings.
- Page files preserve the unchanged response bytes from NYC Open Data.
- S3 writes are private, encrypted, and protected against silent overwrites.

The later Silver layer should combine the successful three-year baseline with
successful scheduled runs and deduplicate the intentional incremental overlap.
Manual smoke-test and Airflow-validation runs should normally be excluded from
production Silver input.

## Daily Airflow schedule

The `safeeats_ingestion` DAG runs every day at:

```text
10:00 AM America/New_York
```

The timezone-aware schedule follows daylight-saving time. `catchup=False`
prevents Airflow from creating one DAG run for every missed day.

This Airflow deployment is local. Automatic runs occur only while Docker
Desktop and the Airflow services are running, the computer is awake and online,
and the AWS login is valid. If Airflow runs only occasionally, the next job
requests data from the last successful watermark minus two days through the new
run time, so the gap is covered in one larger incremental run.

## Repository structure

```text
SafeEatsNYC/
|-- airflow/
|   |-- dags/safeeats_ingestion.py
|   `-- Dockerfile
|-- data/
|   |-- audit/                 # ignored local SQLite audit files
|   |-- reference/             # static geography and brand references
|   `-- samples/               # Phase 1 API samples
|-- docs/
|   |-- project_documents/     # plans, reports, runbooks, README, and mockup
|   |-- brand_alias_review_queue.csv
|   `-- co_brand_review_queue.csv
|-- ingestion/                 # API, validation, storage, and audit code
|-- tests/                     # ingestion, S3, and name-normalization tests
|-- spark/                     # Phase 3 schemas, cleaning, deduplication, and matching
|-- dbt/                       # later Gold-model placeholder
|-- streamlit_app/             # later dashboard placeholder
|-- ml/                        # later predictive-risk placeholder
|-- docker-compose.yml
|-- requirements.txt
|-- .env.example
`-- README.md
```

## Prerequisites

- Python 3.13 was used for the verified local environment.
- Docker Desktop with the standalone `docker-compose` command.
- AWS CLI with an authenticated IAM profile.
- Access to an existing private S3 bucket in the configured AWS region.
- Windows PowerShell for the commands shown below.

## Local setup

From the repository root:

```powershell
py -3.13 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Create the local environment file:

```powershell
Copy-Item .env.example .env
```

At minimum, configure these values in `.env`:

```dotenv
AWS_PROFILE=safeeats-dev
AWS_REGION=us-east-1
SAFEEATS_S3_BUCKET=<your-private-bucket-name>
SAFEEATS_S3_PREFIX=bronze
SAFEEATS_STORAGE_BACKEND=s3
AIRFLOW_JWT_SECRET=<a-private-random-secret>
```

Do not commit `.env`, AWS credentials, or local audit databases.

Refresh and verify AWS access:

```powershell
aws login --profile safeeats-dev
aws sts get-caller-identity --profile safeeats-dev
```

## Run the tests

```powershell
docker-compose exec airflow-worker python -m pytest `
  /opt/safeeats/tests -q -p no:cacheprovider
```

Expected result inside the Docker worker for the current implementation:

```text
44 passed
```

## Start Airflow

Build or rebuild the images after changing `airflow/Dockerfile` or
`requirements.txt`:

```powershell
docker-compose build
```

Initialize and start the services:

```powershell
docker-compose up airflow-init
docker-compose up -d
docker-compose ps
```

Open the local Airflow UI at <http://localhost:8080>. The default local
development username and password are `airflow` / `airflow` unless changed in
`.env`.

Verify the DAG:

```powershell
docker-compose exec airflow-scheduler airflow dags list |
  Select-String "safeeats_ingestion"

docker-compose exec airflow-scheduler airflow dags list-import-errors
```

Enable daily scheduling if the DAG is paused:

```powershell
docker-compose exec airflow-scheduler airflow dags unpause -y safeeats_ingestion
```

Stop the local services without deleting Airflow metadata:

```powershell
docker-compose stop
```

## Manual ingestion

Manual source commands support explicit historical windows or audit-driven
incremental windows. A new logical run should use a new run ID. Reusing a
successful run ID returns the existing audit record without downloading or
writing the data again.

With `.env` configured, the normal manual incremental commands are:

```powershell
python -m ingestion.ingest_dohmh
python -m ingestion.ingest_311
```

The CLI reads the S3 bucket, AWS profile, region, page size, overlap, and audit
path from `.env`. It generates a unique manual run ID and uses the current time
as the upper boundary. Omit `--start-timestamp` for an incremental run. The
exact historical, incremental, S3 inspection, Airflow, retry, and idempotency
commands are in the
[Phase 2 ingestion runbook](docs/project_documents/phase2_ingestion.md).

## Silver transformation

Phase 3 reads successful production Bronze runs and writes immutable Parquet
snapshots under `s3://<bucket>/silver/`. Each production output includes a JSON
quality report with input, deduplication, output, and read-back counts.

The jobs run as isolated Docker Compose processes so local Spark has predictable
memory. Airflow continues to schedule Bronze ingestion; retry-safe automatic
Silver scheduling is reserved for the later full-DAG orchestration step.

See the [Phase 3 Silver runbook](docs/project_documents/phase3_silver.md) for
the complete commands, data flow, S3 paths, quality results, matching policy,
and Spark warning guidance.

## Documentation

- [Two-week project plan](docs/project_documents/NYC_Restaurant_Safety_Platform_2Week_Plan.md)
- [Phase 1 scope and audit](docs/project_documents/phase1_scope.md)
- [Phase 1 data profile](docs/project_documents/data_profile.md)
- [Restaurant-name profile](docs/project_documents/restaurant_name_profile.md)
- [Static reference-data guide](docs/project_documents/README.md)
- [Phase 2 ingestion runbook](docs/project_documents/phase2_ingestion.md)
- [Phase 3 Silver and geospatial runbook](docs/project_documents/phase3_silver.md)
- [Dashboard HTML mockup](docs/project_documents/safeeats_dashboard_mockup.html)

## MVP assumptions and exclusions

The MVP includes cuisine, grade, borough, distance, and restaurant-history
filters where supported by the selected data. It does not promise price tiers,
open-now status, dietary labels, survey-based recommendations, or precise
walking-distance navigation because those fields are not available in the
selected NYC datasets.

Other important limitations:

- Bronze intentionally contains overlapping incremental records; Silver must
  deduplicate them.
- A nearest-restaurant match means geographic proximity, not proof that a
  restaurant caused a complaint.
- Coordinate-less complaints remain valid but cannot be geospatially matched.
- Restaurant matching currently uses the latest valid location per CAMIS.
- Offset pagination is not a transactional snapshot when the source changes
  during a long download.
- A two-day overlap cannot capture a correction whose source timestamp remains
  older than the overlap; periodic wider backfills may be needed.
- The local SQLite audit should move to durable shared storage before a
  production multi-machine deployment.

Detailed assumptions, dataset grain, normalization policy, and limitations are
documented in the Phase 1, Phase 2, and Phase 3 files linked above.
