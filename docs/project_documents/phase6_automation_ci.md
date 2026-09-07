# Phase 6: Complete automation and CI

## Phase result

Phase 6 is complete for the current local Docker and AWS environment.

The separate jobs built in Phases 2 through 4 are now connected into one
Airflow DAG. A successful run downloads fresh source data, builds new Silver
data, matches complaints to restaurants, refreshes the Athena/dbt Gold
warehouse, runs every dbt data test, and reconciles the row counts.

Verified results:

- One complete DAG contains 13 tasks in the required dependency order.
- The DAG runs every day at **10:00 AM New York time** while the local Docker
  environment is running.
- DOHMH and 311 ingestion run in parallel because neither source depends on
  the other.
- Spark jobs run sequentially to fit safely within the local Docker memory.
- A controlled failure retried automatically and succeeded on its second
  attempt.
- Rerunning the same pipeline run ID reused successful S3 outputs without
  creating new objects or object versions.
- Older successful Silver outputs remained unchanged during failure and retry
  tests.
- The verified end-to-end run created fresh Bronze, Silver, matched, and Gold
  data.
- All **167 dbt tests** and all **19 reconciliation checks** passed.
- All **57 Python tests** passed, and the critical Ruff lint check passed.
- Airflow reported no DAG import errors.
- GitHub Actions configuration was added for safe checks on pushes and pull
  requests. Its equivalent checks passed locally; the hosted workflow will run
  for the first time after this change is pushed to GitHub.

## The simplest mental model

Airflow is the manager. Docker provides the computers on which the manager and
jobs run. S3 stores the data. Spark cleans the data. Athena makes the S3 data
queryable with SQL. dbt builds and tests dashboard-ready tables.

```text
                        Airflow decides what runs and when
                                      |
                  +-------------------+-------------------+
                  |                                       |
                  v                                       v
         Download DOHMH data                     Download 311 data
                  |                                       |
                  +-------------------+-------------------+
                                      |
                                      v
                            S3 Bronze raw JSON
                                      |
                                      v
                         PySpark cleaning and typing
                                      |
                                      v
                           S3 Silver Parquet data
                                      |
                                      v
                     Match complaints to restaurants
                                      |
                                      v
                    Athena registers the Silver locations
                                      |
                                      v
                    dbt builds Gold tables and six marts
                                      |
                                      v
                       167 tests + 19 count checks
                                      |
                                      v
                            Pipeline SUCCESS
```

GitHub Actions is separate from the daily data flow:

```text
Code pushed to GitHub
        |
        +--> Python tests
        +--> critical Python lint checks
        `--> dbt parse without AWS access
```

CI checks the code safely. It does **not** download production data, use AWS
credentials, or run the production pipeline.

## How Docker, Airflow, and AWS are connected

### Docker Compose

`docker-compose.yml` creates and connects the local services:

- **Airflow API server** provides the web interface at `http://localhost:8080`.
- **Airflow scheduler** decides when a DAG and its tasks should run.
- **Airflow DAG processor** reads and validates the Python DAG files.
- **Airflow worker** executes the ingestion, Spark, Athena, and dbt commands.
- **Airflow triggerer** handles deferred or asynchronous Airflow work.
- **PostgreSQL** stores Airflow's DAG-run and task-state metadata.
- **Redis** carries task messages from the scheduler to the worker.
- **airflow-init** initializes or upgrades Airflow's PostgreSQL metadata and
  then exits successfully. It is not expected to remain running.

The project directory is mounted inside the Airflow containers:

```text
Windows: E:\SafeEatsNYC
Docker:  /opt/safeeats
```

Therefore, the worker runs the same Python, Spark, warehouse, and dbt code that
is visible in the repository.

### Airflow

`airflow/dags/safeeats_pipeline.py` defines the complete DAG named:

```text
safeeats_daily_pipeline
```

Airflow does not contain the transformation logic itself. The DAG calls the
existing programs from earlier phases in the correct order.

### AWS and S3

Docker Compose mounts the host's `.aws` configuration into the Airflow
containers. The worker uses the profile named by `AWS_PROFILE` to access S3
and Athena. The bucket and region come from `.env`.

```text
.env
  |
  +--> AWS_PROFILE=safeeats-dev
  +--> AWS_REGION=us-east-1
  `--> SAFEEATS_S3_BUCKET=safeeatsnyc-data-830460571487
          |
          v
docker-compose.yml passes these values to the Airflow worker
          |
          v
Python / Spark / Athena / dbt use the same AWS account and bucket
```

No AWS key is copied into the Docker image or committed to Git.

## Final Airflow task flow

```text
pipeline_context
       |
       v
retry_probe
       |
       +----------------------------+
       |                            |
       v                            v
ingest_inspections              ingest_311
       |                            |
       +-------------+--------------+
                     |
                     v
              bronze_complete
                     |
                     v
        build_inspections_silver
                     |
                     v
         build_complaints_silver
                     |
                     v
        build_geospatial_matches
                     |
                     v
        register_silver_in_athena
                     |
                     v
                 build_gold
                     |
                     v
                  test_gold
                     |
                     v
               reconciliation
                     |
                     v
             pipeline_complete
```

### What each task does

| Task | Simple purpose |
|---|---|
| `pipeline_context` | Creates one safe and consistent set of names for the run. |
| `retry_probe` | Normally passes; it can intentionally fail once for a safe retry test. |
| `ingest_inspections` | Downloads incremental DOHMH inspection JSON to S3 Bronze. |
| `ingest_311` | Downloads incremental relevant 311 JSON to S3 Bronze. |
| `bronze_complete` | Allows processing to continue only after both downloads succeed. |
| `build_inspections_silver` | Cleans, types, and deduplicates inspection records into Parquet. |
| `build_complaints_silver` | Cleans, types, and deduplicates complaint records into Parquet. |
| `build_geospatial_matches` | Finds the nearest restaurant within 100 meters when possible. |
| `register_silver_in_athena` | Points Athena Silver tables at this run's S3 Parquet folders. |
| `build_gold` | Loads reference seeds and builds every dbt Gold model. |
| `test_gold` | Runs all dbt data-quality and relationship tests. |
| `reconciliation` | Explains and validates row counts across Bronze, Silver, and Gold. |
| `pipeline_complete` | Marks the full pipeline successful after every check passes. |

## Files added or changed in Phase 6

### Complete DAG

`airflow/dags/safeeats_pipeline.py`

- Defines the complete 13-task DAG.
- Runs daily at 10:00 AM in `America/New_York`.
- Uses two retries with a five-minute delay for normal tasks.
- Prevents overlapping full runs with `max_active_runs=1`.
- Uses the same Airflow run ID throughout the pipeline.
- Records downstream stage attempts in the audit database.

`airflow/dags/safeeats_ingestion.py`

- Remains available as a manual ingestion-only recovery DAG.
- Its automatic schedule was removed so two DAGs do not download the same data
  every day.

### Run naming and audit helpers

`orchestration/run_context.py`

- Converts an Airflow run ID into an S3-safe token.
- Generates deterministic inspection Silver, complaint Silver, and match run
  IDs.
- Gives every stage of one pipeline run traceable names.

Example:

```text
Airflow run ID:
phase6-e2e-20260906-v1

Generated output IDs:
inspections-silver-phase6-e2e-20260906-v1
complaints-silver-phase6-e2e-20260906-v1
complaint-restaurant-matches-phase6-e2e-20260906-v1
```

`orchestration/audit.py`

- Adds the `pipeline_stage_audit` table to the existing SQLite audit database.
- Stores the pipeline run, stage, attempt number, start/end times, status, and
  error message.
- Preserves both the failed attempt and the later successful retry.

`orchestration/trigger_pipeline.py`

- Triggers a manual full run without difficult PowerShell JSON escaping.
- Can turn on the controlled fail-once retry test.

### Safe Spark reruns

`spark/run_safety.py`

- Returns the existing quality report when an output already completed
  successfully.
- Clears only the exact current run's partial files before retrying an
  incomplete run.
- Never clears an older successful run.

The three production Spark build programs now support:

```text
--retry-incomplete
```

This behavior was added to:

- `spark/build_inspections_silver.py`
- `spark/build_complaints_silver.py`
- `spark/build_geospatial_matches.py`

`spark/bronze_runs.py` now recognizes the historical baseline, scheduled
Airflow runs, and `phase6-e2e-` validation runs as production inputs.

### Docker runtime changes

`airflow/Dockerfile`

- Adds the dbt Athena packages to the Airflow image.
- Allows the Airflow worker to run dbt directly after Spark finishes.

`docker-compose.yml`

- Passes S3, Athena, Spark, and AWS profile settings into Airflow.
- Uses Java 21 inside the container.
- Sets Celery worker concurrency to one so a local Spark job has enough memory.
- Shares the Spark connector cache between one-off containers.

`warehouse/requirements.txt`

- Pins compatible dbt, Athena adapter, boto3, and botocore dependencies.

### Reconciliation

`warehouse/reconcile_phase4.py`

- Uses the same production Bronze-run selection policy as Spark.
- Prevents the reconciliation step from overlooking rows from a valid Phase 6
  run.

### Continuous integration

`.github/workflows/ci.yml`

- Runs on every push and pull request.
- Runs the Python test suite with Python 3.13 and Java 21.
- Runs Ruff checks for syntax errors, undefined names, and other critical
  Python failures.
- Parses the dbt project using placeholder settings without contacting AWS.
- Uses read-only repository permission and contains no AWS credentials.

### Phase 6 tests

- `tests/test_phase6_pipeline_helpers.py` tests deterministic and S3-safe run
  names.
- `tests/test_pipeline_audit.py` verifies that a failure and retry are both
  preserved.
- `tests/test_spark_run_safety.py` verifies successful reuse and exact-prefix
  cleanup for incomplete runs.
- `tests/test_bronze_runs.py` verifies that the shared production-run policy is
  applied correctly.

## Run IDs and S3 output flow

Every Airflow run has one logical run ID. The same ID connects its Bronze,
Silver, match, audit, and reconciliation evidence.

For the verified manual run:

```text
phase6-e2e-20260906-v1
```

the important S3 paths are:

```text
s3://safeeatsnyc-data-830460571487/
|
+-- bronze/
|   +-- inspections/ingest_date=2026-09-06/
|   |   `-- run_id=phase6-e2e-20260906-v1/
|   `-- complaints_311/ingest_date=2026-09-06/
|       `-- run_id=phase6-e2e-20260906-v1/
|
+-- silver/
|   +-- inspections/
|   |   `-- run_id=inspections-silver-phase6-e2e-20260906-v1/
|   +-- complaints_311/
|   |   `-- run_id=complaints-silver-phase6-e2e-20260906-v1/
|   `-- complaint_restaurant_matches/
|       `-- run_id=complaint-restaurant-matches-phase6-e2e-20260906-v1/
|
+-- gold/
|   `-- dbt-managed tables and marts
|
`-- gold/_audit/
    `-- pipeline_run_id=phase6-e2e-20260906-v1/
        `-- reconciliation.json
```

The Bronze folder contains only that run's newly downloaded overlap window.
The Silver build reads all selected production Bronze runs and deduplicates
overlap, so Silver represents the complete current dataset rather than only
one day's records.

## What happens when a task fails

Airflow uses successful-only dependencies by default. Therefore:

```text
task fails
    |
    +--> downstream tasks do not run
    +--> the failure and error are recorded
    +--> Airflow waits and retries the failed task
    +--> only that run's incomplete output may be cleaned
    `--> older successful S3 data remains available
```

The normal task policy is two retries with a five-minute delay. The dedicated
`retry_probe` uses one retry after ten seconds so the retry behavior can be
tested quickly without damaging data.

## Idempotency in simple terms

Idempotency means that safely repeating the same run does not duplicate or
corrupt its data.

For a successful output:

```text
same run ID is executed again
        |
        v
quality_report.json says SUCCESS
        |
        v
reuse the existing output; do not rewrite S3 data
```

For an incomplete output:

```text
retry of the same run
        |
        v
no successful quality report exists
        |
        v
delete only that exact incomplete run folder
        |
        v
build it again
```

Gold tables are dbt-managed current analytical tables and are rebuilt safely.
Bronze and Silver keep run-specific immutable evidence.

## Verified end-to-end run

The controlled full run was:

```text
phase6-e2e-20260906-v1
```

Fresh Bronze received:

| Source | New rows downloaded |
|---|---:|
| DOHMH inspections | 1,081 |
| Relevant 311 complaints | 335 |

Complete refreshed Silver contained:

| Dataset | Final rows |
|---|---:|
| Inspection/violation rows | 251,155 |
| Unique complaints | 151,182 |
| Complaint/restaurant match rows | 151,182 |

Gold results:

- All 24 dbt models built successfully.
- All 167 dbt tests passed.
- All 19 cross-layer reconciliation checks passed.
- Reconciliation reported zero production Bronze rows waiting to enter the
  refreshed Silver snapshot.

## Failure and retry verification

Two forms of retry evidence were verified:

1. The manual `retry_probe` intentionally failed on attempt 1 and succeeded on
   attempt 2.
2. A scheduled inspection Silver task encountered a real Spark memory failure,
   entered Airflow's retry state, and succeeded on attempt 2 after the local
   worker-memory configuration was corrected.

The audit retained the failed and successful attempts instead of hiding the
original error.

## Same-run rerun verification

The completed `phase6-e2e-20260906-v1` DAG run was cleared and executed again
with the same ID. All 13 tasks succeeded.

Before and after the rerun, the run-specific S3 measurements were unchanged:

| Output | Objects | Bytes |
|---|---:|---:|
| Bronze inspections | 2 | 996,660 |
| Bronze 311 | 2 | 355,204 |
| Silver inspections | 78 | 52,568,869 |
| Silver complaints | 78 | 40,552,565 |
| Silver matches | 131 | 50,182,391 |

S3 object-version counts for those paths were also unchanged. This proves the
rerun reused successful outputs instead of overwriting them.

## Previous-output protection verification

Older successful Phase 3 outputs were checked after failure and retry testing:

| Older successful output | Objects | Bytes |
|---|---:|---:|
| Inspections | 76 | 51,859,228 |
| Complaints | 76 | 40,265,649 |
| Matches | 127 | 49,780,937 |

Their measurements remained unchanged. A failed new run therefore did not
damage the previous usable snapshot.

## Commands: start from a new PowerShell terminal

Run all commands from the repository root:

```powershell
Set-Location E:\SafeEatsNYC
```

### 1. Activate the virtual environment

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\.venv\Scripts\Activate.ps1
```

### 2. Load the bucket name from `.env`

```powershell
$safeeatsBucketLine = Get-Content .env |
  Where-Object { $_ -match '^SAFEEATS_S3_BUCKET=' } |
  Select-Object -First 1

$safeeatsBucket = ($safeeatsBucketLine -split '=', 2)[1].Trim()
$safeeatsBucket
```

Expected value for the current project:

```text
safeeatsnyc-data-830460571487
```

### 3. Refresh the AWS login when required

First test the session:

```powershell
aws sts get-caller-identity `
  --profile safeeats-dev
```

If AWS reports that the login or refresh token expired, run:

```powershell
aws login --profile safeeats-dev
```

Then repeat `get-caller-identity`.

The local AWS login cache is mounted into Docker. If a newly created cache file
is readable only by `root`, allow the Airflow group to read only those temporary
JSON token files:

```powershell
docker-compose exec --user root airflow-worker `
  sh -lc "chmod 640 /home/airflow/.aws/login/cache/*.json"
```

This command is needed only when the worker reports an AWS login/cache
permission error.

### 4. Build the Airflow image after dependency changes

```powershell
docker-compose build
```

This is not required for every daily run. Run it after changing the Dockerfile
or Python requirements.

### 5. Initialize and start Airflow

```powershell
docker-compose up airflow-init
```

Expected final line:

```text
airflow-init exited with code 0
```

Start all long-running services:

```powershell
docker-compose up -d
```

Check them:

```powershell
docker-compose ps
```

The API server, scheduler, DAG processor, triggerer, worker, PostgreSQL, and
Redis should become healthy. `airflow-init` should show `Exited`; that is
normal because initialization has finished.

### 6. Verify the DAG

```powershell
docker-compose exec airflow-scheduler `
  airflow dags list-import-errors
```

Expected:

```text
No data found
```

Confirm the DAG exists:

```powershell
docker-compose exec airflow-scheduler `
  airflow dags list | Select-String "safeeats_daily_pipeline"
```

Confirm that `is_paused` is `False`. If it is paused:

```powershell
docker-compose exec airflow-scheduler `
  airflow dags unpause -y safeeats_daily_pipeline
```

### 7. Verify AWS access inside the worker

```powershell
docker-compose exec airflow-worker python -c `
  "import os,boto3; b=os.environ['SAFEEATS_S3_BUCKET']; boto3.Session(profile_name=os.environ['AWS_PROFILE']).client('s3',region_name=os.environ['AWS_REGION']).head_bucket(Bucket=b); print('S3 access successful:',b)"
```

### 8. Trigger a normal manual full run

Use a new meaningful run ID each time:

```powershell
docker-compose exec airflow-scheduler python `
  /opt/safeeats/orchestration/trigger_pipeline.py `
  --run-id phase6-manual-YYYYMMDD-v1
```

Do not include `--test-retry-once` for a normal run.

### 9. Trigger the controlled retry test

Use this only when intentionally testing Airflow retries:

```powershell
docker-compose exec airflow-scheduler python `
  /opt/safeeats/orchestration/trigger_pipeline.py `
  --run-id phase6-retry-test-YYYYMMDD-v1 `
  --test-retry-once
```

The `retry_probe` should fail once, wait ten seconds, and then pass. No data is
modified by the intentional failure itself.

### 10. Monitor a run

Open the Airflow UI:

```text
http://localhost:8080
```

Or check from PowerShell:

```powershell
docker-compose exec airflow-scheduler `
  airflow dags list-runs safeeats_daily_pipeline -o table
```

Check each task for one run:

```powershell
docker-compose exec airflow-scheduler `
  airflow tasks states-for-dag-run `
  safeeats_daily_pipeline `
  phase6-manual-YYYYMMDD-v1
```

All 13 tasks should eventually show `success`.

If a task fails or remains in retry, inspect recent worker logs:

```powershell
docker-compose logs --tail 300 airflow-worker
```

### 11. Verify S3 outputs

Bronze inspections:

```powershell
aws s3 ls "s3://$safeeatsBucket/bronze/inspections/" `
  --recursive `
  --profile safeeats-dev `
  --region us-east-1 | Select-String "phase6-manual-YYYYMMDD-v1"
```

Bronze complaints:

```powershell
aws s3 ls "s3://$safeeatsBucket/bronze/complaints_311/" `
  --recursive `
  --profile safeeats-dev `
  --region us-east-1 | Select-String "phase6-manual-YYYYMMDD-v1"
```

Silver outputs:

```powershell
aws s3 ls "s3://$safeeatsBucket/silver/" `
  --recursive `
  --profile safeeats-dev `
  --region us-east-1 | Select-String "phase6-manual-YYYYMMDD-v1"
```

Reconciliation report:

```powershell
aws s3 cp `
  "s3://$safeeatsBucket/gold/_audit/pipeline_run_id=phase6-manual-YYYYMMDD-v1/reconciliation.json" `
  - `
  --profile safeeats-dev `
  --region us-east-1
```

Expected report status:

```text
SUCCESS
```

### 12. Run local code checks before committing

Python tests in the same Airflow environment used by the pipeline:

```powershell
docker-compose exec airflow-worker `
  python -m pytest tests -q
```

Critical lint checks:

```powershell
docker-compose exec airflow-worker `
  python -m ruff check . --select E9,F63,F7,F82 --exclude .venv
```

Safe dbt parsing:

```powershell
docker-compose exec airflow-worker dbt parse `
  --project-dir /opt/safeeats/dbt `
  --profiles-dir /opt/safeeats/dbt `
  --no-partial-parse
```

The dbt parse command reads project configuration. It does not rebuild the
production warehouse.

## Automatic daily behavior

The schedule is:

```text
0 10 * * * in America/New_York
```

This means 10:00 AM New York time every day. Airflow's timezone handles the
UTC offset and daylight-saving changes.

The run happens automatically only when Docker Desktop and the Airflow
containers are running at the scheduled time. This is a local deployment, not
an always-on AWS Airflow service.

If the computer or Docker is off at 10:00 AM, `catchup=False` means Airflow
does not create every missed historical daily run. After starting the services,
trigger one manual run if fresh data is needed immediately. The next automatic
run occurs at the next scheduled 10:00 AM.

## CI behavior after a Git push

After this branch is pushed, GitHub reads `.github/workflows/ci.yml` and starts
three independent jobs:

```text
python-tests     lint     dbt-parse
```

They can run in parallel. A pull request should not be treated as ready when a
required CI job is red.

The dbt CI job intentionally performs `dbt parse`, not production `dbt run` or
`dbt test`, because GitHub receives no AWS production credentials. Full data
tests remain part of the Airflow production DAG against the actual Gold data.

## What Phase 6 does not automate

- The Streamlit dashboard has not yet been built; that is the next phase.
- The final XGBoost model retraining and current-risk artifact generation from
  Phase 5 are not part of the daily DAG yet. The DAG refreshes the dbt feature
  models, but model promotion remains a deliberate manual process.
- Docker Desktop must be running for this local Airflow deployment.
- AWS login sessions can expire and may require `aws login` again.
- SQLite audit storage is suitable for one local worker but should move to a
  durable shared database before a multi-machine production deployment.
- GitHub-hosted CI cannot be confirmed until the workflow is committed and
  pushed.

## Phase 6 completion checklist

- [x] One DAG runs Bronze, Silver, matching, Athena, Gold, tests, and
  reconciliation in order.
- [x] Independent ingestion tasks run in parallel.
- [x] Local Spark transformations run sequentially for memory safety.
- [x] Downstream tasks stop when an upstream task fails.
- [x] Stage failures and retry attempts are audited.
- [x] Automatic retry behavior was verified.
- [x] Same-run idempotency was verified.
- [x] Previous successful outputs remain usable after a failure.
- [x] dbt tests run automatically in the data pipeline.
- [x] Reconciliation runs automatically in the data pipeline.
- [x] A successful run produced fresh Bronze, Silver, matched, and Gold data.
- [x] GitHub Actions configuration runs tests, lint, and safe dbt parsing.
- [x] Local equivalents of all CI checks passed.
- [ ] GitHub-hosted CI run is pending the first commit and push.

Phase 6 is complete for the current local Docker/AWS architecture.
