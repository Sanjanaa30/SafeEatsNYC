# SafeEats NYC architecture

## Purpose

This document shows how data moves from NYC Open Data to the SafeEats NYC
website and explains the responsibility of each major component.

## End-to-end architecture

~~~mermaid
flowchart TD
    A[NYC Restaurant Inspection API] --> C[Python ingestion]
    B[NYC 311 Service Request API] --> C
    C --> D[S3 Bronze JSON]
    C --> E[SQLite ingestion audit and watermarks]
    D --> F[PySpark cleaning and deduplication]
    F --> G[S3 Silver Parquet]
    G --> H[Athena Silver tables]
    H --> I[dbt staging and intermediate models]
    I --> J[Gold dimensions and facts]
    J --> K[Dashboard marts]
    J --> L[ML feature tables]
    L --> M[XGBoost training and scoring]
    M --> N[S3 approved model scores]
    K --> O[FastAPI]
    J --> O
    N --> O
    O --> P[Next.js dashboard]
    Q[Airflow] -. schedules and verifies .-> C
    Q -. schedules and verifies .-> F
    Q -. schedules and verifies .-> I
    Q -. monitors and promotes .-> M
~~~

## Data-layer responsibilities

### Source layer

The project reads two changing public sources:

- NYC Restaurant Inspection Results
- NYC 311 Service Requests filtered to relevant food and rodent categories

Static borough, ZIP, neighborhood, brand, alias, and co-brand files are
reviewed separately.

### Bronze layer

Bronze stores the original API response bytes and the request metadata. It does
not clean or collapse records.

Why this matters:

- source records remain auditable
- failed transformations do not destroy the original input
- a later rule change can be applied without downloading the same history again

### Silver layer

Silver converts source text into typed records, standardizes fields, removes
duplicates, and creates complaint-to-restaurant geographic matches.

The three main outputs are:

- inspection and violation records
- unique 311 complaints
- complaint-to-restaurant match results

### Gold layer

Athena reads Silver Parquet from S3. dbt then builds:

- staging views
- intermediate inspection and restaurant records
- dimensions
- facts
- dashboard marts
- machine-learning feature tables

Gold is the business-facing source used by the API and model.

### Model layer

The model uses past-only Gold features to estimate whether the next graded
inspection may receive B or C.

Model artifacts, evaluation reports, current scores, and the approved score
pointer are stored in S3. The API reads approved scores rather than retraining
the model during a web request.

### Application layer

FastAPI queries Athena and S3 on the server. Next.js calls FastAPI and renders
the dashboard.

The browser does not receive AWS credentials and does not query Athena or S3
directly.

## Warehouse data model

~~~mermaid
erDiagram
    DIM_RESTAURANT ||--o{ FACT_INSPECTION : has
    DIM_RESTAURANT o|--o{ FACT_311_COMPLAINT : may_match
    DIM_BOROUGH ||--o{ DIM_RESTAURANT : contains
    DIM_BOROUGH ||--o{ FACT_INSPECTION : groups
    DIM_BOROUGH ||--o{ FACT_311_COMPLAINT : groups
    DIM_DATE ||--o{ FACT_INSPECTION : dates
    DIM_DATE ||--o{ FACT_311_COMPLAINT : dates
    DIM_VIOLATION o|--o{ FACT_INSPECTION : describes
    DIM_COMPLAINT_TYPE ||--o{ FACT_311_COMPLAINT : classifies
    DIM_CHAIN o|--o{ DIM_RESTAURANT : groups
~~~

Important grains:

| Table | Grain |
|---|---|
| dim_restaurant | One current row per DOHMH CAMIS restaurant ID |
| dim_chain | One detected restaurant group |
| dim_borough | One NYC borough |
| dim_date | One calendar day |
| dim_violation | One non-null violation code |
| dim_complaint_type | One relevant 311 complaint category |
| fact_inspection | One deduplicated inspection-and-violation source record |
| fact_311_complaint | One unique 311 complaint |

The facts deliberately have different grains. Inspection totals must use the
inspection identifier rather than counting every violation row as a separate
inspection.

## Local runtime architecture

~~~text
Docker Desktop
|
|-- PostgreSQL
|     Stores Airflow metadata
|
|-- Redis
|     Carries Celery task messages
|
|-- Airflow API, scheduler, DAG processor, worker, and triggerer
|     Schedule and run pipeline tasks
|
|-- FastAPI
|     Serves read-only dashboard endpoints on port 8000
|
+-- Next.js
      Serves the website on port 3000
~~~

The dbt and ML services are command-oriented containers. They run when needed
and do not need to remain active for normal dashboard browsing.

## Automation flow

### Daily pipeline

The daily Airflow DAG runs:

~~~text
Create run context
    |
    +--> Download inspections
    |
    +--> Download 311 complaints
              |
              v
Build Silver inspections and complaints
              |
              v
Build geographic matches
              |
              v
Register Athena locations
              |
              v
Run dbt seeds, models, and tests
              |
              v
Reconcile Bronze, Silver, and Gold
~~~

Independent downloads run in parallel. Memory-heavy local Spark jobs run in a
controlled order.

### Monthly model refresh

~~~text
Prepare chronological training data
    |
    v
Train and calibrate logistic baseline
    |
    v
Compare XGBoost
    |
    v
Retrain selected model and score current restaurants
    |
    v
Verify files and monitor quality
    |
    v
Promote scores only when required checks pass
~~~

## Security boundaries

- Local secrets belong in **.env**, which Git ignores.
- AWS credential folders are mounted into containers rather than copied into
  images.
- The main AWS configuration mount is read-only.
- Only the temporary AWS login cache has the access needed to refresh a login.
- The browser calls FastAPI and never receives AWS credentials.
- Dashboard API routes accept only GET requests.
- Query parameters are validated and page sizes are limited.
- Athena statements use controlled server-side query templates.
- Internal exceptions are logged on the server and returned to users as a
  generic temporary-unavailability message.
- CI runs without production AWS credentials.

The actual IAM policy must still follow least privilege. The dashboard identity
needs read access to approved data plus the minimum Athena query-result access
required by Athena.

## Failure behavior

- A failed ingestion task is recorded and does not advance its successful
  watermark.
- Immutable output paths prevent partial retries from silently replacing a
  previous successful run.
- Airflow stops dependent tasks when an upstream task fails.
- dbt tests and reconciliation can stop a bad refresh before it is treated as
  trusted.
- Model quality gates block score promotion when required checks fail.
- API failures return HTTP 503 with a safe message.
- Dashboard sections display a retryable error state when data is unavailable.

## Related documents

- [Main project guide](../../README.md)
- [Data dictionary](data_dictionary.md)
- [Data quality and limitations](data_quality_and_limitations.md)
- [Automation and CI](phase6_automation_ci.md)
- [Dashboard and API](phase7_dashboard.md)
