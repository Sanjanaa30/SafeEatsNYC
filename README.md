# SafeEats NYC

SafeEats NYC is an end-to-end restaurant-safety data platform for New York
City. It collects official public data, cleans and tests it, builds analytical
tables, estimates future inspection risk, and presents the results in a
four-page website.

The project is designed to make restaurant-safety information easier to
understand without replacing official NYC Department of Health inspection
results.

## What the project answers

SafeEats NYC helps answer these questions:

1. What does restaurant safety look like across NYC and its five boroughs?
2. Which cuisines and violations may need the most attention?
3. Do changes in food-related 311 complaints match later inspection findings?
4. What is the inspection history of a particular restaurant?
5. Which locations belong to the same restaurant group?
6. Which restaurants may be more likely to receive a B or C grade next time?

## Project status

All seven planned phases are implemented.

| Phase | Main result | Status |
|---|---|---|
| 1. Scope and profiling | Defined the data, rules, assumptions, and dashboard questions | Complete |
| 2. Bronze ingestion | Saved original inspection and 311 API responses in private S3 storage | Complete |
| 3. Silver processing | Cleaned, typed, deduplicated, and geographically matched the data | Complete |
| 4. Gold warehouse | Built tested Athena and dbt tables for analysis | Complete |
| 5. Predictive model | Trained and evaluated an XGBoost model for future B/C-grade risk | Complete |
| 6. Automation and CI | Connected the pipeline with Airflow and automated code checks | Complete |
| 7. Dashboard and API | Built the Next.js website and FastAPI backend | Complete |

## The complete project flow

~~~text
Phase 1
Understand the sources, data quality, and business rules
        |
        v
Phase 2
Download unchanged NYC API responses into S3 Bronze
        |
        v
Phase 3
Clean and deduplicate data into S3 Silver
        |
        v
Phase 4
Build tested Athena and dbt Gold tables
        |
        +-----------------------------+
        |                             |
        v                             v
Phase 5                       Dashboard-ready data
Train and score the model              |
        |                              |
        +---------------+--------------+
                        v
Phase 7
FastAPI sends approved data to the Next.js website

Phase 6 surrounds Phases 2-5 with scheduling, retries,
monitoring, reconciliation, and continuous integration.
~~~

## Bronze, Silver, and Gold in simple words

| Layer | Simple meaning | Example |
|---|---|---|
| Bronze | The original source response, kept unchanged | One page returned by the NYC inspections API |
| Silver | Clean and consistently typed records | Duplicate inspection rows removed and dates standardized |
| Gold | Business-ready tables and metrics | Grade A share by borough or violations per 100 restaurants |

Keeping these layers separate makes it possible to trace a dashboard result
back to the original source.

## Data sources

| Source | Dataset | Purpose |
|---|---|---|
| NYC Restaurant Inspection Results | 43nn-pn8j | Restaurant names, locations, cuisines, grades, scores, inspections, and violations |
| NYC 311 Service Requests | erm2-nwe9 | Food Poisoning, Food Establishment, and Rodent complaints |
| NYC geographic boundaries | gthc-hcne, 35j5-n34v, and 9nt8-h7nd | Borough shapes, ZIP areas, and neighborhood labels |
| OpenStreetMap | Overpass API | Reviewed fast-food and quick-service brand references |

Restaurant inspection data can contain several rows for one visit because each
violation is stored separately. The pipeline preserves that source detail and
then creates inspection-level results where needed.

## Phase 1: Scope, discovery, and profiling

**Goal:** Understand the data before building the pipeline.

Phase 1:

- inspected samples from the inspections and 311 APIs
- confirmed the meaning and grain of important fields
- selected the food-related complaint categories
- reviewed missing values and duplicate patterns
- downloaded geographic reference files
- created restaurant-name normalization rules
- documented brand aliases and co-brand locations
- defined what the first version of the dashboard would and would not include

**Input:** NYC Open Data samples and static reference sources.

**Output:** A clear project scope, data-quality findings, matching rules, and
reference files.

**Connection to Phase 2:** The validated fields, filters, and assumptions become
the rules used when downloading full historical and incremental data.

Detailed guide:
[Phase 1 scope and assumptions](docs/project_documents/phase1_scope.md)

## Phase 2: Bronze data ingestion

**Goal:** Download source data safely without changing it.

Phase 2:

- downloads restaurant inspections and relevant 311 complaints
- supports historical and incremental date windows
- saves each original API page as JSON in private Amazon S3 storage
- records the exact request and source window
- uses retries for temporary failures
- records successful runs and watermarks in a local audit database
- prevents a repeated successful run ID from silently overwriting data

The normal incremental load starts from the last successful source timestamp,
moves back two days, and downloads through the current run time. The overlap
helps capture recently corrected source records.

**Input:** NYC Open Data APIs and Phase 1 selection rules.

**Output:** Immutable Bronze JSON plus audit and watermark records.

**Connection to Phase 3:** Silver jobs read only approved successful Bronze
runs, combine the historical baseline with later increments, and remove the
intentional overlap.

Detailed guide:
[Phase 2 ingestion](docs/project_documents/phase2_ingestion.md)

## Phase 3: Silver cleaning and geographic matching

**Goal:** Turn raw API pages into reliable analytical records.

Phase 3 uses PySpark to:

- apply explicit schemas and data types
- standardize dates, coordinates, boroughs, ZIP codes, and text fields
- preserve useful records with missing optional values
- remove exact or older duplicate records
- keep the correct inspection, violation, and complaint grains
- select each restaurant's latest valid location for geographic work
- match complaints to the nearest restaurant within 100 meters
- keep unmatched and coordinate-less complaints for honest reporting
- write immutable Parquet snapshots and quality reports to S3 Silver

A geographic match means that a complaint was near a restaurant. It does not
prove that the restaurant caused the complaint.

**Input:** Successful Bronze inspection and 311 runs.

**Output:** Clean inspection, complaint, and complaint-to-restaurant Parquet
datasets.

**Connection to Phase 4:** Athena registers the Silver snapshots so dbt can
turn technical records into business-friendly dimensions, facts, and marts.

Detailed guide:
[Phase 3 Silver processing](docs/project_documents/phase3_silver.md)

## Phase 4: Athena and dbt Gold warehouse

**Goal:** Build trusted tables that are easy to query.

Phase 4:

- registers Silver Parquet files as Athena tables
- creates clean staging views
- prepares restaurant and restaurant-group records
- keeps reviewed brand confirmation separate from automatic group detection
- builds dimensions for restaurants, boroughs, dates, violations, and other
  descriptive fields
- builds inspection and complaint fact tables
- creates dashboard marts for grades, cuisines, violations, weekly complaint
  patterns, restaurant history, and groups
- uses fair rates such as per 100 restaurants or per 100 inspections
- runs dbt tests and cross-layer reconciliation checks

Reconciliation checks that important counts still agree from Silver through
Gold. This helps detect missing, duplicated, or unexpectedly changed data.

**Input:** Phase 3 Silver snapshots and reviewed reference files.

**Output:** Tested Gold tables in Athena.

**Connection to Phase 5:** The model uses historical Gold inspection and
complaint features.

**Connection to Phase 7:** The API reads the Gold tables used by the dashboard.

Detailed guide:
[Phase 4 warehouse](docs/project_documents/phase4_warehouse.md)

## Phase 5: Predictive restaurant-risk model

**Goal:** Estimate whether a restaurant's next graded inspection may receive B
or C instead of A.

Phase 5:

- creates one prediction example from information available before a later
  inspection
- excludes future information to prevent data leakage
- splits older and newer examples by time
- trains an explainable logistic-regression baseline
- compares it fairly with XGBoost
- evaluates precision, recall, F1, ROC-AUC, and probability calibration
- selects XGBoost for the current operational goal
- retrains the selected model on mature historical results
- scores eligible current restaurants
- records feature contributions for restaurant-level explanations
- stores versioned model files, reports, and scores in S3

The dashboard uses three review categories:

| Stored category | Dashboard wording | Meaning |
|---|---|---|
| LOW | Lower risk | A lower estimated chance of a future B/C grade |
| MODERATE | Watch | The restaurant may deserve review |
| HIGH | Needs attention | A stronger signal for review |

These scores are predictions, not official grades. They do not prove that a
restaurant is unsafe.

**Input:** Historical Gold features from Phase 4.

**Output:** A tested model, evaluation reports, current risk scores, and factor
explanations.

**Connection to Phase 6:** Airflow can refresh, monitor, and safely promote a
new model output.

**Connection to Phase 7:** FastAPI reads only approved promoted scores for the
Predictive Risk page.

Detailed guide:
[Phase 5 predictive model](docs/project_documents/phase5_predictive_model.md)

## Phase 6: Automation, monitoring, and CI

**Goal:** Run the connected pipeline reliably and check code changes.

Phase 6 provides:

- a daily Airflow pipeline from Bronze ingestion through Gold reconciliation
- safe run IDs for immutable outputs
- automatic retries for temporary failures
- protection for previously successful outputs
- idempotent reruns where the same successful run is not duplicated
- data tests and cross-layer reconciliation
- a monthly model refresh with chronological backtesting
- model calibration, subgroup, and drift checks
- score promotion only after quality checks pass
- GitHub Actions checks for Python, Ruff, and offline dbt parsing

Main Airflow schedules:

| DAG | Schedule | Purpose |
|---|---|---|
| safeeats_daily_pipeline | Every day at 10:00 AM New York time | Refresh Bronze, Silver, geographic matches, and Gold |
| safeeats_monthly_model_refresh | First day of each month at 2:00 PM New York time | Retrain, evaluate, monitor, and promote model scores |
| safeeats_ingestion | Manual only | Older ingestion-only workflow |

Automatic runs require Docker Desktop to be running, the computer to be awake
and online, and the AWS login to remain valid.

**Input:** The working jobs from Phases 2-5.

**Output:** Scheduled, retry-safe, tested, and monitored pipeline runs.

**Connection to Phase 7:** Refreshed Gold tables and promoted scores become the
next dashboard snapshot.

Detailed guide:
[Phase 6 automation and CI](docs/project_documents/phase6_automation_ci.md)

## Phase 7: FastAPI and Next.js dashboard

**Goal:** Present the approved results in a clear and interactive website.

Phase 7 contains:

- a read-only FastAPI backend
- a Next.js and React frontend
- Athena query services and short-lived API caching
- approved S3 risk-score loading
- reusable cards, filters, charts, tables, loading states, and modals
- simple explanations and tooltips for difficult metrics
- four connected dashboard pages

### Overview

Shows citywide KPIs, borough comparisons, grade distribution, cuisine patterns,
common violations, and critical versus non-critical findings.

### Correlation

Compares weekly food-related 311 complaint rates with critical inspection
rates after a selected delay. It includes a weekly trend, a correlation score,
a real NYC borough map, and a borough table.

Correlation measures whether two patterns move together. It does not prove
cause and effect.

### Finder

Searches every restaurant in the current warehouse snapshot by name, NYC
restaurant ID, address, ZIP code, and filters. Restaurant and group modals show
grades, inspection history, violations, nearby Grade A options, and links to
risk analysis.

### Predictive Risk

Lists eligible restaurants with approved model scores. Selecting a restaurant
opens a modal explaining the score and its strongest driving factors.

**Input:** Gold tables from Phase 4 and promoted scores from Phase 5 or 6.

**Output:** The website used to explore SafeEats NYC results.

Detailed guide:
[Phase 7 dashboard and API](docs/project_documents/phase7_dashboard.md)

## How the phases connect: one restaurant example

Suppose NYC Open Data contains a restaurant called **TONY'S BRICK OVEN**.

1. **Phase 1** confirms which source fields represent its ID, name, address,
   inspection, grade, and violations.
2. **Phase 2** downloads the unchanged source rows and stores them in Bronze.
3. **Phase 3** cleans those rows, removes duplicates, and creates consistent
   inspection records.
4. **Phase 4** adds the restaurant to the restaurant dimension and prepares its
   history for analysis.
5. **Phase 5** creates a risk score only if the restaurant meets the model's
   eligibility rules.
6. **Phase 6** refreshes and tests the data, then promotes approved results.
7. **Phase 7** lets a user search for the restaurant and open its full details.

If a food-related 311 complaint occurred nearby, it may also contribute to
aggregated geographic and correlation analysis. It is not presented as proof
that the restaurant caused the complaint.

## Technology map

| Technology | Responsibility |
|---|---|
| Python | Ingestion, validation, audits, orchestration helpers, modeling, and API |
| Amazon S3 | Bronze JSON, Silver Parquet, model artifacts, scores, and reports |
| PySpark | Large-scale cleaning, deduplication, and geographic matching |
| Amazon Athena | SQL access to Silver and Gold data stored in S3 |
| dbt | Warehouse transformations, documentation, and data tests |
| XGBoost and scikit-learn | Model training, calibration, evaluation, and scoring |
| Apache Airflow | Scheduling, task order, retries, and pipeline monitoring |
| PostgreSQL | Airflow metadata |
| Redis | Airflow Celery task queue |
| FastAPI | Read-only dashboard API |
| Next.js and React | User-facing website |
| Docker Compose | Repeatable local services |
| GitHub Actions | Automated code and dbt checks |

## Important design decisions

- **Keep Bronze unchanged:** Original API responses remain available for audit
  and reprocessing.
- **Clean downstream:** Typing, standardization, and deduplication happen in
  Silver rather than changing the source record.
- **Keep grains explicit:** Violation rows and inspection events are separate
  so inspection metrics are not accidentally multiplied.
- **Use immutable run IDs:** Retries cannot silently overwrite a previous
  successful output.
- **Preserve unmatched data:** Complaints without coordinates or a nearby
  restaurant remain part of the dataset.
- **Use rates for comparison:** Per-restaurant and per-inspection rates reduce
  the effect of borough and cuisine size.
- **Review uncertain name matches:** Normalization supports matching, but it
  does not replace the official restaurant name or prove common ownership.
- **Prevent model leakage:** Features use only information known before the
  target inspection.
- **Keep AWS access server-side:** The browser calls FastAPI and never receives
  AWS credentials.
- **Return safe errors:** Internal failures are logged, while users see a
  generic temporary-unavailability message.

The reasoning and tradeoffs are explained further in the
[Phase 8 documentation guide](docs/project_documents/phase8_documentation.md).

## Repository structure

~~~text
SafeEatsNYC/
|-- airflow/
|   |-- dags/
|   |   |-- safeeats_ingestion.py
|   |   |-- safeeats_pipeline.py
|   |   +-- safeeats_model_refresh.py
|   +-- Dockerfile
|-- api/
|   |-- routers/             FastAPI endpoints
|   |-- schemas/             Response models
|   |-- services/            Athena, S3, search, and presentation logic
|   |-- tests/               Backend tests
|   +-- main.py
|-- data/
|   |-- reference/           Geography, aliases, brands, and co-brand rules
|   |-- audit/               Ignored local audit database
|   +-- samples/             Source samples used during profiling
|-- dbt/
|   |-- models/              Staging, intermediate, dimensions, facts, marts, ML
|   |-- tests/               Custom warehouse tests
|   +-- seeds and project configuration
|-- docs/
|   +-- project_documents/   Phase guides, reports, plans, and runbooks
|-- frontend/
|   |-- app/                 Next.js routes
|   |-- components/          Charts, layout, overview, and shared UI
|   |-- lib/                 API and display helpers
|   |-- public/maps/         Browser-safe NYC borough map
|   +-- types/               TypeScript API types
|-- ingestion/               Source clients, validation, storage, and audit code
|-- ml/                      Training, comparison, monitoring, and scoring
|-- orchestration/           Shared run naming and pipeline helpers
|-- spark/                   Silver transformations and matching
|-- tests/                   Pipeline, Spark, ingestion, and model tests
|-- warehouse/               Athena setup and reconciliation
|-- .env.example
|-- docker-compose.yml
|-- requirements.txt
+-- README.md
~~~

## Run the application

You only need the dashboard services to explore the existing warehouse
snapshot. Airflow does not need to run at the same time.

### 1. Open the project

~~~powershell
Set-Location E:\SafeEatsNYC
~~~

### 2. Start Docker Desktop

Wait until Docker is ready, then confirm that both the Client and Server appear:

~~~powershell
docker version
~~~

### 3. Create the environment file

Do this once:

~~~powershell
Copy-Item .env.example .env
~~~

At minimum, confirm these values in **.env**:

~~~dotenv
AWS_PROFILE=safeeats-dev
AWS_REGION=us-east-1
SAFEEATS_S3_BUCKET=<your-private-bucket-name>
SAFEEATS_FRONTEND_ORIGIN=http://localhost:3000
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
~~~

Do not commit **.env** or AWS credentials.

### 4. Sign in to AWS

~~~powershell
aws login --profile safeeats-dev
aws sts get-caller-identity --profile safeeats-dev
~~~

The second command should return the active AWS account and identity.

### 5. Start the backend and frontend

~~~powershell
docker-compose --profile dashboard up -d api frontend
~~~

The frontend waits for a healthy API before it starts.

### 6. Open the website

- Website: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- API health check: <http://localhost:8000/api/v1/health>

### 7. Restart after a code change

~~~powershell
docker-compose --profile dashboard restart api frontend
~~~

If a Dockerfile, package file, or dependency file changed, rebuild instead:

~~~powershell
docker-compose --profile dashboard up -d --build api frontend
~~~

### 8. Check logs if something fails

~~~powershell
docker-compose logs --tail 100 api frontend
~~~

### 9. Stop the application

~~~powershell
docker-compose stop api frontend
~~~

This stops the containers without deleting saved Docker volumes.

## Optional: run the full Airflow pipeline

The dashboard can run without Airflow. Use these commands only when refreshing
the underlying data:

~~~powershell
docker-compose build
docker-compose up airflow-init
docker-compose up -d
docker-compose ps
~~~

Open the Airflow interface at <http://localhost:8080>. The default local login
is **airflow / airflow** unless it was changed in **.env**.

## Local Python setup

Create the local environment when running tests or scripts outside Docker:

~~~powershell
py -3.13 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
& .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r api/requirements.txt -r ml/requirements.txt
~~~

## Run checks

Backend and pipeline:

~~~powershell
python -m pytest api/tests tests -q
python -m ruff check api airflow/dags ingestion ml orchestration spark warehouse tests
~~~

Frontend:

~~~powershell
Set-Location frontend
npm install
npm run lint
npm test
npx tsc --noEmit --incremental false
Set-Location ..
~~~

## Important interpretation rules

- **Official source:** DOHMH grades and inspections are more authoritative than
  model predictions.
- **Snapshot, not live data:** The website reflects the latest completed
  warehouse refresh shown in the header.
- **Rates versus totals:** Borough and cuisine comparisons use rates where
  possible so larger areas do not dominate.
- **Nearby is not responsible:** A nearby complaint does not prove that a
  restaurant caused it.
- **Correlation is not causation:** Similar weekly movement does not prove that
  complaints caused later inspection findings.
- **Predictions are uncertain:** Risk scores are review signals, not guarantees.
- **Groups need care:** Similar restaurant names can belong to different
  businesses, so uncertain group matches require review.
- **Distances are approximate:** Nearby options use straight-line distance, not
  a walking route.

## Project limitations

- **The data is not live:** The dashboard shows the latest completed warehouse
  snapshot, so very recent inspections or complaints may not appear yet.
- **Nearby complaints do not prove responsibility:** A complaint close to a
  restaurant may relate to another property or issue nearby.
- **The 100-meter match is an estimate:** It is a practical matching rule, not
  proof that every matched complaint belongs to that restaurant.
- **Correlation does not prove cause:** Similar complaint and inspection trends
  do not mean that one caused the other.
- **Restaurant groups are not ownership records:** Locations are grouped using
  reviewed names and matching rules, so uncertain cases may still require
  manual review.
- **Some source data is incomplete:** Missing coordinates, grades, addresses,
  or inspection history can limit analysis.
- **Neighborhood labels are approximate:** ZIP codes and NYC neighborhood
  boundaries do not match perfectly.
- **Small groups can be unstable:** Results for a cuisine, neighborhood, or
  short time period may change greatly when only a few records are available.
- **Risk scores are predictions:** They estimate a possible future B or C grade
  and do not declare that a restaurant is unsafe.
- **Not every restaurant receives a risk score:** A restaurant needs enough
  usable graded inspection history to qualify.
- **The model can change over time:** Inspection policies, restaurant behavior,
  and new data may affect future model performance.
- **The current system runs locally:** Scheduled refreshes depend on Docker
  Desktop, the computer, internet access, and a valid AWS login.
- **Some consumer information is unavailable:** The selected sources do not
  provide prices, opening hours, dietary guarantees, ratings, or walking
  directions.

## Possible future features

- **Restaurant watchlist:** Let users save restaurants and follow changes in
  grades, violations, or predicted risk.
- **Safety alerts:** Notify users when a saved restaurant receives a new grade,
  critical violation, or major risk change.
- **Neighborhood explorer:** Compare restaurant safety by neighborhood or ZIP,
  with minimum-data rules for fair comparisons.
- **Interactive restaurant map:** Show restaurants, grades, risk levels, and
  nearby complaint patterns on one searchable map.
- **Restaurant comparison:** Place two or more restaurants side by side to
  compare grades, inspection history, violations, and risk.
- **Inspection timeline:** Display a restaurant's complete history as a simple
  visual timeline.
- **Personalized recommendations:** Suggest nearby Grade A options based on
  cuisine and location preferences.
- **Trend and anomaly detection:** Highlight unusual increases in complaints,
  violations, or inspection scores.
- **Risk-change explanations:** Show why a restaurant's predicted risk moved
  up or down between model refreshes.
- **Open data export:** Let users download selected, non-sensitive dashboard
  results as CSV.
- **Multilingual dashboard:** Provide key explanations in additional languages
  commonly spoken across NYC.
- **Mobile-friendly alerts and sharing:** Make restaurant summaries easy to
  save and share from a phone.

## Documentation index

### Core documentation

- [Architecture](docs/project_documents/architecture.md)
- [Data dictionary](docs/project_documents/data_dictionary.md)
- [Data quality, assumptions, and limitations](docs/project_documents/data_quality_and_limitations.md)
- [Static reference data](docs/project_documents/README.md)

### Phase documentation

- [Phase 1: Scope and assumptions](docs/project_documents/phase1_scope.md)
- [Phase 1: Data profile](docs/project_documents/data_profile.md)
- [Phase 1: Restaurant-name profile](docs/project_documents/restaurant_name_profile.md)
- [Phase 2: Ingestion](docs/project_documents/phase2_ingestion.md)
- [Phase 3: Silver processing](docs/project_documents/phase3_silver.md)
- [Phase 4: Athena and dbt warehouse](docs/project_documents/phase4_warehouse.md)
- [Phase 4: Latest warehouse reconciliation](docs/project_documents/phase4_reconciliation.md)
- [Phase 5: Predictive model](docs/project_documents/phase5_predictive_model.md)
- [Phase 6: Automation and CI](docs/project_documents/phase6_automation_ci.md)
- [Phase 7: Dashboard and API](docs/project_documents/phase7_dashboard.md)
- [Phase 8: Documentation readiness](docs/project_documents/phase8_documentation.md)
