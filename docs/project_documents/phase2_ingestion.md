# SafeEats NYC - Phase 2: Data ingestion

## Phase 2 status

Phase 2 is complete.

The project can now:

1. Download DOHMH inspections and relevant 311 complaints separately.
2. Request every available page in a bounded time window.
3. Retry temporary API and network failures.
4. Validate every response before saving it.
5. Preserve the unchanged JSON responses in private Amazon S3 Bronze storage.
6. Record each source run in an ingestion audit database.
7. Perform a three-year historical load.
8. Continue incrementally from the last successful source timestamp.
9. Re-read a two-day overlap to capture late source updates.
10. Rerun safely without overwriting or duplicating S3 objects.
11. Run both ingestion tasks through Apache Airflow in Docker.
12. Run automatically every day at 10:00 AM New York time.

## The simplest mental model

Docker, Airflow, and S3 have three different jobs:

```text
Docker Desktop
    provides the containers/computers
                  |
                  v
Apache Airflow
    decides when and in what order the Python jobs run
                  |
                  v
SafeEats ingestion Python code
    requests and validates NYC API data
                  |
                  v
Amazon S3 Bronze
    permanently stores the unchanged JSON responses
```

S3 does not schedule anything. Airflow does not permanently contain the raw
restaurant data. Docker Desktop does not contain the project source code. The
three parts work together through the repository files and mounted folders.

## Complete architecture flow

```text
                                 +-------------------------+
                                 | Airflow API server/UI   |
                                 | http://localhost:8080   |
                                 +------------+------------+
                                              |
                                              v
+----------------------+            +----------------------+
| safeeats_ingestion.py|----------->| Airflow PostgreSQL   |
| DAG and 10 AM schedule|           | DAG/task metadata    |
+----------+-----------+            +----------------------+
           |
           v
+----------------------+            +----------------------+
| Airflow scheduler    |----------->| Redis task queue     |
+----------------------+            +----------+-----------+
                                              |
                                              v
                                   +----------------------+
                                   | Airflow worker       |
                                   +----------+-----------+
                                              |
                         +--------------------+--------------------+
                         |                                         |
                         v                                         v
              +----------------------+                  +----------------------+
              | NYC Open Data APIs   |                  | ingestion Python     |
              | DOHMH and 311        |                  | pipeline/storage     |
              +----------+-----------+                  +----------+-----------+
                         |                                         |
                         +--------------------+--------------------+
                                              |
                         +--------------------+--------------------+
                         |                                         |
                         v                                         v
              +----------------------+                  +----------------------+
              | Amazon S3 Bronze     |                  | SQLite audit DB      |
              | unchanged raw JSON   |                  | ingestion watermark  |
              +----------------------+                  +----------------------+
```

Important distinction:

- Airflow PostgreSQL stores Airflow's internal DAG and task status.
- `data/audit/ingestion_audit.db` stores SafeEats ingestion results and source
  watermarks.
- Amazon S3 stores the actual raw DOHMH and 311 JSON.
- Redis is only the temporary queue between the scheduler and worker.

## Files and what each one does

### Docker and Airflow files

| File | Purpose |
|---|---|
| `docker-compose.yml` | Defines and connects every Airflow, PostgreSQL, and Redis container. It also passes S3 settings and mounts the project and AWS profile. |
| `airflow/Dockerfile` | Builds the custom Airflow images from `apache/airflow:3.3.1` and installs the root requirements file. |
| `requirements.txt` | Installs Python packages used inside the Airflow images, including `boto3` and `botocore[crt]`. |
| `airflow/dags/safeeats_ingestion.py` | Defines the daily schedule, two ingestion tasks, completion task, retry policy, and S3 storage selection. |
| `.env` | Holds local configuration such as bucket, AWS profile, region, page size, overlap, and Airflow development credentials. It is ignored by Git. |
| `.env.example` | Safe template showing which settings `.env` supports. |

### Ingestion files

| File | Purpose |
|---|---|
| `ingestion/ingest_dohmh.py` | Command-line entry point for DOHMH inspections. |
| `ingestion/ingest_311.py` | Command-line entry point for relevant 311 complaints. |
| `ingestion/sources.py` | Defines API URLs, source fields, ordering, filters, and S3 dataset folder names. |
| `ingestion/cli.py` | Reads command-line arguments and selects local or S3 storage. |
| `ingestion/pipeline.py` | Builds the time window, downloads pages, validates them, writes Bronze files, and updates the audit. |
| `ingestion/storage.py` | Implements local and S3 Bronze storage, encryption metadata, and overwrite protection. |
| `ingestion/audit.py` | Creates and updates the SQLite run log and returns the latest successful watermark. |

### Test files

| File | Purpose |
|---|---|
| `tests/test_ingestion_pipeline.py` | Tests pagination, validation, retries, failure auditing, overlap, resume, and rerun behavior. |
| `tests/test_s3_storage.py` | Tests exact-byte S3 preservation and overwrite protection without contacting AWS. |

## How local code becomes available inside Docker

`docker-compose.yml` mounts the repository into each Airflow container:

```text
Windows                                      Airflow container
E:\SafeEatsNYC                              /opt/safeeats
E:\SafeEatsNYC\airflow\dags                 /opt/airflow/dags
E:\SafeEatsNYC\airflow\logs                 /opt/airflow/logs
C:\Users\<user>\.aws                        /home/airflow/.aws (read-only)
C:\Users\<user>\.aws\login\cache            /home/airflow/.aws/login/cache (writable)
```

The AWS profile is read-only for safety. Only the temporary AWS login cache is
writable because the AWS login provider must refresh its temporary token.

Consequences:

- Editing the DAG or ingestion Python files normally does not require an image
  rebuild because the repository is mounted into the containers.
- Editing `airflow/Dockerfile` or `requirements.txt` does require
  `docker-compose build` followed by `docker-compose up -d`.
- AWS credentials are not copied into an image and are not committed to Git.

## Sources, filters, and dataset grain

| Source | NYC dataset ID | Incremental field | Selection |
|---|---|---|---|
| DOHMH inspections | `43nn-pn8j` | `inspection_date` | All inspection rows inside the bounded time window |
| 311 complaints | `erm2-nwe9` | `created_date` | `Food Poisoning`, `Food Establishment`, and `Rodent` complaints inside the bounded time window |

DOHMH Bronze remains at the original API row grain. Multiple rows may describe
violations from the same inspection. Phase 2 does not collapse them to one row
per restaurant or inspection.

The 311 source remains one service-request row per `unique_key`.

## S3 Bronze layout

```text
s3://<bucket>/bronze/
|-- inspections/
|   `-- ingest_date=YYYY-MM-DD/
|       `-- run_id=<run-id>/
|           |-- request.json
|           |-- page_offset=000000000.json
|           `-- page_offset=000010000.json
`-- complaints_311/
    `-- ingest_date=YYYY-MM-DD/
        `-- run_id=<run-id>/
            |-- request.json
            `-- page_offset=000000000.json
```

Folder and file meanings:

- `inspections/` and `complaints_311/` identify the source dataset.
- `ingest_date=...` is the day SafeEats downloaded the data. It is not
  necessarily the inspection or complaint date.
- `run_id=...` separates one pipeline execution from another.
- `request.json` records the API URL, time boundaries, source filter, ordering,
  page size, source name, and run ID.
- `page_offset=000000000.json` is the first unchanged API response page.
- `page_offset=000010000.json` is the next page when the page size is 10,000.

Page files contain the exact response bytes received from NYC Open Data; the
pipeline does not reformat them. S3 objects are private, use SSE-S3 encryption,
include SHA-256 metadata, and are written with a create-only condition.

If the same object already contains identical bytes, it is safely reused. If a
rerun tries to replace it with different bytes, the pipeline stops instead of
silently overwriting raw history.

## Meaning of the existing inspection run folders

The verified `ingest_date=2026-08-30` partition contains these important run
types:

| Folder | Meaning | Later Silver use |
|---|---|---|
| `run_id=initial-3y-dohmh-20260830-v1/` | Main three-year historical baseline | Include |
| `run_id=incremental-dohmh-20260830-v1/` | Manual command-line incremental validation | Normally exclude as a test run |
| `run_id=airflow-s3-success-20260830-v1/` | Manual Airflow-to-S3 validation | Normally exclude as a test run |
| `run_id=scheduled__.../` | An automatically scheduled Airflow production run | Include successful runs |

The downstream Silver process should initially combine the successful
three-year baseline with successful scheduled runs, then deduplicate by the
source/business keys. Test runs remain valuable evidence but should not be
treated as additional production history.

## Full load, incremental load, and two-day overlap

### First run

When a source has no successful audit watermark and no explicit start timestamp,
the default initial lookback is 1,095 days, or approximately three years.

### Later run

Each source has its own watermark:

```text
latest successful source timestamp
                 minus two days
                        |
                        v
                next window start
                        |
                        v
                 current run end
```

For example:

```text
Last successful source timestamp: August 29 at 01:36
Overlap:                         - two days
Next request starts:              August 27 at 01:36
Next request ends:                current bounded run time
```

Therefore, an incremental page contains a mixture of:

- genuinely new records;
- recent records intentionally requested again; and
- records that the source published or corrected late.

This is expected. Phase 2 preserves the overlapping raw data. The later Silver
stage removes duplicates.

## Audit files

The intended audit files are:

```text
data/audit/ingestion_audit.db   actual historical, incremental, and Airflow runs
data/audit/test_audit.db        manual smoke-test records
```

Pytest may temporarily create `data/audit/pytest-temp/`. It is not a production
audit database and can be removed after tests stop.

The actual audit database must not be overwritten on every run. New logical run
IDs add audit rows, while rerunning the same source and run ID reuses or updates
the existing row. The retained successful rows are necessary for incremental
watermarks and traceability.

Each audit record contains:

```text
run_id
source_name
started_at
completed_at
rows_requested
rows_received
page_count
last_source_timestamp
output_path
request_where
status
error_message
```

The primary key is `(run_id, source_name)`. SQLite WAL mode and a busy timeout
allow the two independent Airflow tasks to update the database safely.

## Airflow schedule and occasional operation

The `safeeats_ingestion` DAG is scheduled for:

```text
10:00 AM America/New_York every day
```

The DAG uses a timezone-aware `pendulum` start date. The schedule therefore
remains at 10:00 AM through daylight-saving changes:

- 10:00 AM EDT is 14:00 UTC.
- 10:00 AM EST is 15:00 UTC.

The Airflow UI may display UTC unless its display timezone is changed.

Automatic local scheduling works only while:

- Docker Desktop is running;
- the Airflow containers are running and healthy;
- the computer is awake and connected to the internet; and
- the AWS login session is valid.

S3 is a cloud service, but this Airflow installation runs locally. Turning off
the computer stops the local scheduler.

The DAG has `catchup=False`. If Airflow is stopped for ten days, it does not
create ten separate missed DAG runs when restarted. The next successful run
still uses the last ingestion watermark minus two days, so one larger request
covers the gap through the new run time.

Running only occasionally is therefore recoverable, but the next ingestion can
take longer and request more pages. Daily operation is recommended. A truly
always-on schedule would require deploying Airflow or another scheduler to an
always-on server/cloud environment, which is outside this local Phase 2 scope.

## Airflow DAG flow

```text
                   +--> ingest_inspections --+
Airflow scheduler -|                          +--> ingestion_complete
                   +--> ingest_311 -----------+
```

The sources are independent and run in parallel. `ingestion_complete` runs only
after both source tasks succeed.

Each task has:

```text
2 Airflow retries
5-minute delay between retries
```

The HTTP client inside each ingestion task separately retries temporary NYC API
responses such as 429, 500, 502, 503, and 504, along with temporary connection
and read failures.

## Complete PowerShell runbook

Run these commands from `E:\SafeEatsNYC`.

### 1. Activate the project virtual environment

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\.venv\Scripts\Activate.ps1
```

Expected prompt:

```text
(.venv) PS E:\SafeEatsNYC>
```

### 2. Load the S3 bucket name from `.env`

```powershell
$safeeatsBucketLine = Get-Content .env |
  Where-Object { $_ -match '^SAFEEATS_S3_BUCKET=' } |
  Select-Object -First 1

$safeeatsBucket = ($safeeatsBucketLine -split '=', 2)[1].Trim()
$safeeatsBucket
```

### 3. Refresh and verify the AWS login

```powershell
aws login --profile safeeats-dev
```

Complete the browser login, then run:

```powershell
aws sts get-caller-identity --profile safeeats-dev
```

Verify that the expected account and IAM user are returned.

### 4. Verify access to the private bucket

```powershell
aws s3api head-bucket `
  --bucket $safeeatsBucket `
  --profile safeeats-dev `
  --region us-east-1
```

### 5. Run the automated ingestion tests

```powershell
python -m pytest tests -q --basetemp data/audit/pytest-temp
```

Verified result:

```text
32 passed
```

These tests use local/fake storage and do not perform the full live S3 load.

### 6. Optional one-day DOHMH S3 smoke test

Use a new run ID if performing a new test:

```powershell
python -m ingestion.ingest_dohmh `
  --storage-backend s3 `
  --s3-bucket $safeeatsBucket `
  --s3-prefix bronze `
  --aws-profile safeeats-dev `
  --aws-region us-east-1 `
  --run-id s3-test-dohmh-20260824-v1 `
  --start-timestamp 2026-08-24T00:00:00Z `
  --end-timestamp 2026-08-25T00:00:00Z `
  --page-size 100 `
  --audit-db data/audit/test_audit.db
```

### 7. Optional one-day 311 S3 smoke test

```powershell
python -m ingestion.ingest_311 `
  --storage-backend s3 `
  --s3-bucket $safeeatsBucket `
  --s3-prefix bronze `
  --aws-profile safeeats-dev `
  --aws-region us-east-1 `
  --run-id s3-test-311-20260824-v1 `
  --start-timestamp 2026-08-24T00:00:00Z `
  --end-timestamp 2026-08-25T00:00:00Z `
  --page-size 100 `
  --audit-db data/audit/test_audit.db
```

### 8. Three-year historical DOHMH load

This verified load has already completed. Do not create another baseline unless
a deliberate backfill is required.

```powershell
python -m ingestion.ingest_dohmh `
  --storage-backend s3 `
  --s3-bucket $safeeatsBucket `
  --s3-prefix bronze `
  --aws-profile safeeats-dev `
  --aws-region us-east-1 `
  --run-id initial-3y-dohmh-20260830-v1 `
  --start-timestamp 2023-08-30T00:00:00Z `
  --end-timestamp 2026-08-30T00:00:00Z `
  --page-size 10000 `
  --audit-db data/audit/ingestion_audit.db
```

Verified result: 247,877 rows in 25 page files.

### 9. Three-year historical 311 load

This verified load has already completed. Do not create another baseline unless
a deliberate backfill is required.

```powershell
python -m ingestion.ingest_311 `
  --storage-backend s3 `
  --s3-bucket $safeeatsBucket `
  --s3-prefix bronze `
  --aws-profile safeeats-dev `
  --aws-region us-east-1 `
  --run-id initial-3y-311-20260830-v1 `
  --start-timestamp 2023-08-30T00:00:00Z `
  --end-timestamp 2026-08-30T00:00:00Z `
  --page-size 10000 `
  --audit-db data/audit/ingestion_audit.db
```

Verified result: 150,098 rows in 16 page files.

### 10. List a run in S3

```powershell
aws s3 ls `
  "s3://$safeeatsBucket/bronze/inspections/ingest_date=2026-08-30/run_id=initial-3y-dohmh-20260830-v1/" `
  --profile safeeats-dev `
  --region us-east-1
```

To summarize object count and bytes:

```powershell
aws s3api list-objects-v2 `
  --bucket $safeeatsBucket `
  --prefix "bronze/inspections/ingest_date=2026-08-30/run_id=initial-3y-dohmh-20260830-v1/" `
  --profile safeeats-dev `
  --region us-east-1 `
  --query "{ObjectCount:length(Contents),TotalBytes:sum(Contents[].Size)}"
```

### 11. Manual incremental DOHMH run

The important rule is to omit `--start-timestamp`. The pipeline then reads the
latest successful DOHMH watermark from the actual audit database.

```powershell
python -m ingestion.ingest_dohmh `
  --storage-backend s3 `
  --s3-bucket $safeeatsBucket `
  --s3-prefix bronze `
  --aws-profile safeeats-dev `
  --aws-region us-east-1 `
  --run-id incremental-dohmh-20260830-v1 `
  --end-timestamp 2026-08-30T00:00:00Z `
  --page-size 10000 `
  --overlap-days 2 `
  --audit-db data/audit/ingestion_audit.db
```

Verified result: 834 rows. Its window began at `2026-08-23T00:00:00Z`
because the prior watermark was August 25 and the overlap was two days.

### 12. Manual incremental 311 run

```powershell
python -m ingestion.ingest_311 `
  --storage-backend s3 `
  --s3-bucket $safeeatsBucket `
  --s3-prefix bronze `
  --aws-profile safeeats-dev `
  --aws-region us-east-1 `
  --run-id incremental-311-20260830-v1 `
  --end-timestamp 2026-08-30T00:00:00Z `
  --page-size 10000 `
  --overlap-days 2 `
  --audit-db data/audit/ingestion_audit.db
```

Verified result: 313 rows. Its start timestamp was the prior source watermark
minus two days.

### 13. Inspect the exact incremental request window

```powershell
aws s3 cp `
  "s3://$safeeatsBucket/bronze/inspections/ingest_date=2026-08-30/run_id=incremental-dohmh-20260830-v1/request.json" `
  - `
  --profile safeeats-dev `
  --region us-east-1 `
  --no-progress |
  ConvertFrom-Json |
  Select-Object window_start, window_end, where
```

### 14. Manual successful-run idempotency check

Run the exact same ingestion command again with the same run ID. Expected log:

```text
Returning prior successful run
```

The command returns the existing audit record without another API download or
S3 write.

### 15. Build the Airflow images

Run this after changes to `airflow/Dockerfile` or `requirements.txt`:

```powershell
docker-compose build
```

Expected: six SafeEats Airflow images are built successfully.

### 16. Initialize Airflow

```powershell
docker-compose up airflow-init
```

Expected:

```text
Database migration done!
3.3.1
airflow-init exited with code 0
```

The init container is supposed to exit after initialization.

### 17. Start Airflow

```powershell
docker-compose up -d
```

Then check health:

```powershell
docker-compose ps
```

The API server, DAG processor, scheduler, triggerer, worker, PostgreSQL, and
Redis should eventually show `healthy`. `airflow-init` remains exited normally.

### 18. Verify AWS identity from inside the worker

```powershell
docker-compose exec airflow-worker python -c "import boto3; print(boto3.Session(profile_name='safeeats-dev').client('sts', region_name='us-east-1').get_caller_identity())"
```

If the login grant is expired, refresh it on Windows:

```powershell
aws login --profile safeeats-dev
```

Then repeat the worker identity command.

### 19. Verify worker access to the configured S3 bucket

```powershell
docker-compose exec airflow-worker python -c "import os, boto3; bucket=os.environ['SAFEEATS_S3_BUCKET']; boto3.Session(profile_name='safeeats-dev').client('s3', region_name='us-east-1').head_bucket(Bucket=bucket); print('S3 access successful:', bucket)"
```

### 20. Verify the Airflow DAG

```powershell
docker-compose exec airflow-scheduler airflow dags list |
  Select-String "safeeats_ingestion"
```

Check import errors:

```powershell
docker-compose exec airflow-scheduler airflow dags list-import-errors
```

Expected:

```text
No data found
```

### 21. Enable daily scheduling

```powershell
docker-compose exec airflow-scheduler airflow dags unpause -y safeeats_ingestion
```

Verify that `is_paused` is `False`:

```powershell
docker-compose exec airflow-scheduler airflow dags list |
  Select-String "safeeats_ingestion"
```

### 22. Trigger a controlled manual Airflow run

Use a new run ID for a new logical test:

```powershell
docker-compose exec airflow-scheduler airflow dags trigger `
  --run-id airflow-s3-success-20260830-v1 `
  safeeats_ingestion
```

Check the DAG run:

```powershell
docker-compose exec airflow-scheduler airflow dags list-runs `
  safeeats_ingestion -o table |
  Select-String "airflow-s3-success-20260830-v1"
```

Check all three task states:

```powershell
docker-compose exec airflow-scheduler airflow tasks states-for-dag-run `
  safeeats_ingestion `
  airflow-s3-success-20260830-v1
```

Expected final state: both ingestion tasks and `ingestion_complete` are
`success`.

### 23. Inspect Airflow service logs

```powershell
docker-compose logs --tail 200 airflow-worker
```

For a shorter filtered view:

```powershell
docker-compose logs --tail 200 airflow-worker |
  Select-String "Requesting|Completed|ERROR|Traceback|retry"
```

The verified manual run encountered one temporary internal Airflow execution-API
timeout. Both tasks moved to `up_for_retry`, waited five minutes, reran, and
succeeded. This confirmed the configured Airflow failure and retry behavior.

### 24. Verify Airflow output in S3

DOHMH:

```powershell
aws s3 ls `
  "s3://$safeeatsBucket/bronze/inspections/ingest_date=2026-08-30/run_id=airflow-s3-success-20260830-v1/" `
  --profile safeeats-dev `
  --region us-east-1
```

311:

```powershell
aws s3 ls `
  "s3://$safeeatsBucket/bronze/complaints_311/ingest_date=2026-08-30/run_id=airflow-s3-success-20260830-v1/" `
  --profile safeeats-dev `
  --region us-east-1
```

The verified run wrote one `request.json` and one data page for each source.

### 25. Final Airflow same-run idempotency test

Record the S3 version count before clearing the run.

DOHMH:

```powershell
aws s3api list-object-versions `
  --bucket $safeeatsBucket `
  --prefix "bronze/inspections/ingest_date=2026-08-30/run_id=airflow-s3-success-20260830-v1/" `
  --profile safeeats-dev `
  --region us-east-1 `
  --query "length(Versions)"
```

311:

```powershell
aws s3api list-object-versions `
  --bucket $safeeatsBucket `
  --prefix "bronze/complaints_311/ingest_date=2026-08-30/run_id=airflow-s3-success-20260830-v1/" `
  --profile safeeats-dev `
  --region us-east-1 `
  --query "length(Versions)"
```

Both verified counts were `2`.

Create a local Airflow API token. These are the default local-development
credentials; use the values configured in `.env` if they were changed.

```powershell
$airflowToken = (Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/auth/token" `
  -ContentType "application/json" `
  -Body '{"username":"airflow","password":"airflow"}'
).access_token

$airflowToken.Length
```

Clear exactly the same DAG run so Airflow executes the same run ID again:

```powershell
$clearBody = @{
  dry_run = $false
  only_failed = $false
  run_on_latest_version = $false
  note = "Phase 2 idempotency test"
} | ConvertTo-Json

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8080/api/v2/dags/safeeats_ingestion/dagRuns/airflow-s3-success-20260830-v1/clear" `
  -Headers @{ Authorization = "Bearer $airflowToken" } `
  -ContentType "application/json" `
  -Body $clearBody
```

Wait for all tasks to return to `success`, then repeat both S3 version-count
commands. Both counts must remain `2`. That proves the Airflow rerun neither
created duplicates nor overwrote the existing raw files.

### 26. Stop and restart the local stack

Stop the running containers without deleting the PostgreSQL volume:

```powershell
docker-compose stop
```

Start them again:

```powershell
docker-compose up -d
```

Do not use `docker-compose down -v` unless the Airflow PostgreSQL metadata volume
is intentionally being deleted.

## Expected results already verified

| Test/load | Result |
|---|---:|
| Automated tests | 32 passed |
| One-day DOHMH smoke test | Approximately 440 rows, 5 pages at page size 100 |
| One-day relevant 311 smoke test | Approximately 211 rows, 3 pages at page size 100 |
| Three-year DOHMH load | 247,877 rows, 25 data pages |
| Three-year 311 load | 150,098 rows, 16 data pages |
| DOHMH incremental validation | 834 rows, 1 page |
| 311 incremental validation | 313 rows, 1 page |
| Airflow S3 manual run | Both sources and completion task succeeded |
| Airflow retry test | Initial timeout, automatic five-minute retry, then success |
| Airflow same-run idempotency | S3 version counts stayed at 2 for each source |

## Troubleshooting

### `MissingDependencyException` for AWS login credentials

Cause: boto3 needs the AWS CRT package for the `aws login` credential provider.

Fix: `botocore[crt]` is already included in `requirements.txt`. Rebuild the
Airflow images after dependency changes:

```powershell
docker-compose build
docker-compose up -d
```

### `Read-only file system: /home/airflow/.aws/login/cache/...`

Cause: the AWS login provider attempted to refresh its temporary token while the
cache was read-only.

Fix: `docker-compose.yml` now mounts the main AWS folder read-only and only the
login cache as writable. Apply Compose changes with:

```powershell
docker-compose up -d
```

### `The provided authorization grant is invalid, expired, revoked, or malformed`

Cause: the host AWS login session expired.

Fix:

```powershell
aws login --profile safeeats-dev
```

Then repeat the AWS identity check inside the worker.

### Airflow services show `health: starting`

Initial startup can take several minutes. Check again:

```powershell
docker-compose ps
```

If they remain unhealthy, inspect logs:

```powershell
docker-compose logs --tail 100 airflow-scheduler airflow-dag-processor airflow-worker airflow-triggerer
```

### `airflow-init` shows `Exited`

This is normal when its exit code is `0`. It performs database migration and
user creation, prints the Airflow version, and stops.

### DAG is found but a manual run remains queued

Check whether the DAG is paused:

```powershell
docker-compose exec airflow-scheduler airflow dags list |
  Select-String "safeeats_ingestion"
```

Unpause it when `is_paused` is `True`:

```powershell
docker-compose exec airflow-scheduler airflow dags unpause -y safeeats_ingestion
```

### `airflow dags list-runs -d` is rejected

Airflow 3 expects the DAG ID as a positional argument:

```powershell
docker-compose exec airflow-scheduler airflow dags list-runs safeeats_ingestion
```

### Tests fail because of a Windows temporary-directory permission

Use the project-local pytest temporary directory:

```powershell
python -m pytest tests -q --basetemp data/audit/pytest-temp
```

### S3 shows `request.json` plus only one page

This is normal when the result contains fewer rows than the configured page
size. `page_offset=000000000.json` is the first page; another page is created
only when pagination needs it.

## Known limitations

- This Airflow deployment is local development infrastructure, not an always-on
  production deployment.
- The ingestion audit is a local SQLite file. It should be backed up or migrated
  to durable shared storage before a production multi-machine deployment.
- Offset pagination is not a transactional source snapshot if NYC changes rows
  during a long load.
- The two-day overlap cannot detect a correction whose source timestamp remains
  older than the overlap window. Periodic wider backfills may be useful.
- Bronze intentionally contains overlapping records. Deduplication belongs in
  Silver, not Bronze.

## Phase 2 completion evidence

- Both APIs download through separate Python entry points.
- Pagination, retries, validation, and exact raw JSON preservation are tested.
- The three-year historical loads are stored in private S3 Bronze.
- Incremental boundaries come from successful audit watermarks.
- The two-day overlap was verified in `request.json`.
- Airflow can authenticate to AWS and access the configured bucket.
- The DAG imports without errors and runs both sources in parallel.
- A temporary failure triggered the configured retry and recovered.
- Clearing and rerunning the same Airflow run left S3 version counts unchanged.
- Daily scheduling is set to 10:00 AM `America/New_York`.

Phase 2 is complete. The next project phase can read the successful historical
baseline and scheduled Bronze runs, transform them into Silver data, and
deduplicate the intentional overlap.
