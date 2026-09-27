# Phase 7: Dashboard and API

## Phase result

Phase 7 provides the working SafeEats NYC website and its read-only backend.

The dashboard uses:

- **Next.js** for the website
- **FastAPI** for the backend API
- **Amazon Athena** for approved Gold warehouse queries
- **Amazon S3** for approved predictive-risk results
- **Docker Compose** for local development

The website is available at <http://localhost:3000> when the dashboard services
are running. Interactive API documentation is available at
<http://localhost:8000/docs>.

## The simplest mental model

    User opens the Next.js website
                  |
                  v
    Frontend requests dashboard data
                  |
                  v
    FastAPI validates the request
                  |
            +-----+-----+
            |           |
            v           v
    Athena Gold     Approved S3
    tables          risk scores
            |           |
            +-----+-----+
                  v
    Website displays cards, charts, tables, and modals

The browser never receives AWS credentials. Only the FastAPI service reads
Athena and S3.

## Dashboard pages

### 1. Overview

Route: <http://localhost:3000/overview>

The Overview page gives a citywide summary of restaurant safety. It includes:

- key grade and inspection measures
- borough safety cards
- borough sorting and filtering
- Grade A, B, and C shares by cuisine and borough
- cuisines with the largest B/C grade share
- common violations
- critical and non-critical findings by borough

Rates are used where raw totals would make large boroughs appear worse simply
because they contain more restaurants.

Common units:

- **Per 100 restaurants**: historical findings for every 100 current
  restaurants
- **Per 100 inspections**: how often a finding appeared across 100 inspections
- **Grade share**: the percentage of currently graded restaurants with a
  particular grade

### 2. Correlation

Route: <http://localhost:3000/correlation>

The Correlation page asks whether weekly changes in food-related 311 complaints
match changes in critical inspection findings after a selected delay.

Users can choose:

- NYC or one borough
- all food-related, food-establishment, food-poisoning, or rodent complaints
- 8, 12, 26, 52, or 104 weeks
- the same week or 1, 2, 4, or 8 weeks later

The page contains a weekly trend chart, correlation summary, restaurant-level
comparison, real NYC borough map, and borough comparison table.

The correlation score runs from -1 to +1:

| Absolute score | Dashboard label | Simple meaning |
|---|---|---|
| 0.00 to 0.29 | Weak | The weekly patterns have little connection. |
| 0.30 to 0.59 | Moderate | The weekly patterns match to some degree. |
| 0.60 to 1.00 | Strong | The weekly patterns match closely. |

A negative score means the patterns moved in opposite directions. Correlation
does not prove that complaints caused later findings.

The main rates are:

- **Complaints per 1,000 restaurants**: a fair weekly complaint comparison
  between boroughs of different sizes
- **Inspections with a critical finding per 100**: the percentage of
  inspections that recorded at least one critical finding

### 3. Finder

Route: <http://localhost:3000/finder>

The Finder searches restaurant locations and restaurant groups.

A restaurant can be found by name, NYC restaurant ID, address, ZIP code,
borough, cuisine, grade, or safety flag.

Selecting a restaurant opens a modal with:

- current grade and score
- days since the latest inspection
- predicted B/C risk when an approved score exists
- three-year grade history
- recent violations in simpler wording
- nearby Grade A restaurants
- a link to the full predictive-risk analysis

Nearby distances are straight-line estimates, not walking routes.

The restaurant-group tab combines locations only when the warehouse's reviewed
grouping rules identify them as the same group. Each location keeps its own
official grade and inspection history.

### 4. Predictive Risk

Route: <http://localhost:3000/risk>

This page lists restaurants with an approved XGBoost risk score. Users can
search and filter by borough, cuisine, and risk category.

Selecting a restaurant opens a modal with its estimated chance of receiving B
or C, current risk category, main driving factors, model version, and scoring
date.

| Stored category | Website label | Meaning |
|---|---|---|
| LOW | Lower risk | A lower model-estimated chance of a future B/C grade |
| MODERATE | Watch | The restaurant may deserve review |
| HIGH | Needs attention | A stronger signal for review |

The factor percentages compare each displayed factor with the strongest factor
for that restaurant. They are not additional risk probabilities.

The model is a prioritization tool, not an official inspection result. A high
score does not prove that a restaurant is unsafe.

## Frontend structure

    frontend/
    |-- app/
    |   |-- overview/page.tsx
    |   |-- correlation/page.tsx
    |   |-- finder/page.tsx
    |   |-- risk/page.tsx
    |   |-- layout.tsx
    |   +-- page.tsx
    |-- components/
    |   |-- charts/
    |   |-- layout/
    |   |-- overview/
    |   +-- ui/
    |-- lib/             API client and display helpers
    |-- public/maps/     Browser-safe NYC borough GeoJSON
    |-- types/           Shared TypeScript response types
    |-- Dockerfile
    +-- package.json

The frontend uses React Query to load and cache API responses. Shared
components provide consistent cards, filters, loading states, error messages,
charts, and modals.

## Backend structure

    api/
    |-- routers/         URLs and query parameters
    |-- schemas/         Response validation models
    |-- services/        Athena, S3, filtering, and presentation logic
    |-- tests/           API and service tests
    |-- config.py        Environment settings
    |-- dependencies.py  Shared service creation
    |-- main.py          FastAPI application
    +-- Dockerfile

The API is read-only. It validates filter values, limits page sizes, and keeps
AWS access on the server.

## Main API groups

All application endpoints begin with **/api/v1**.

| Group | Purpose |
|---|---|
| /health | Service and dependency health |
| /metadata | Boroughs, cuisines, snapshot dates, and model freshness |
| /overview/* | KPIs, grades, boroughs, cuisines, and violations |
| /correlation/* | Weekly trends, summaries, borough comparisons, and map values |
| /restaurants/* | Search, details, history, violations, and nearby options |
| /chains/* | Restaurant-group summaries and locations |
| /risk/* | Approved current risk scores and explanations |

Use <http://localhost:8000/docs> to see every endpoint and its accepted
parameters.

## Configuration

The dashboard reads these settings from **.env**:

    AWS_PROFILE=safeeats-dev
    AWS_REGION=us-east-1
    SAFEEATS_S3_BUCKET=<your-private-bucket-name>
    ATHENA_DBT_SCHEMA=safeeats_gold
    ATHENA_WORKGROUP=primary
    ATHENA_OUTPUT_LOCATION=

    SAFEEATS_API_PORT=8000
    SAFEEATS_FRONTEND_PORT=3000
    SAFEEATS_FRONTEND_ORIGIN=http://localhost:3000
    NEXT_PUBLIC_API_BASE_URL=http://localhost:8000

    RISK_SCORE_POINTER_KEY=ml/current_scores/latest.json
    ATHENA_QUERY_TIMEOUT_SECONDS=90
    API_CACHE_TTL_SECONDS=300

The API first uses the promoted risk-score pointer. The configured
**RISK_SCORE_RUN_ID** remains available as a fallback for older deployments.

## Start the dashboard

From the repository root:

    aws login --profile safeeats-dev
    docker version
    docker-compose --profile dashboard up -d api frontend

Open <http://localhost:3000>.

Check the API directly:

    Invoke-RestMethod http://localhost:8000/api/v1/health

## Restart after code changes

    docker-compose --profile dashboard restart api frontend

The source folders are mounted into the containers. A restart is enough for
most Python, TypeScript, CSS, and configuration changes. Rebuild the images
after changing a Dockerfile, dependency file, or lock file:

    docker-compose --profile dashboard up -d --build api frontend

## Run dashboard tests

Backend:

    python -m pytest api/tests -q
    python -m ruff check api

Frontend:

    Set-Location frontend
    npm run lint
    npm test
    npx tsc --noEmit --incremental false
    Set-Location ..

## Common problems

### Docker cannot connect

Start Docker Desktop and run:

    docker version

The result must show both a Client and Server section.

### A page says that a section could not load

Check both services and their recent logs:

    docker-compose ps
    docker-compose logs --tail 100 api frontend

Then check <http://localhost:8000/api/v1/health>.

### The API returns an AWS authentication error

Refresh the configured login:

    aws login --profile safeeats-dev
    aws sts get-caller-identity --profile safeeats-dev
    docker-compose --profile dashboard restart api

### A restaurant does not appear in Finder

Try its official name, NYC restaurant ID, address, or ZIP code and clear other
filters. Finder searches the current Gold warehouse snapshot, so a restaurant
added after that snapshot will appear only after the data pipeline refreshes
Silver and Gold.

### Predictive Risk has no score for a restaurant

Not every restaurant is eligible. A score requires enough usable inspection
history and an approved model output. The restaurant can still appear in
Finder without a risk score.

### The borough map does not load

Confirm that this file exists:

    frontend/public/maps/nyc_borough_boundaries.geojson

See the [static reference-data guide](README.md) before replacing it.

## Phase 7 limitations

- The dashboard shows completed warehouse snapshots, not live NYC API results.
- Athena queries can take longer on the first request; the API caches repeated
  results for a short period.
- Restaurant names and group assignments can require manual review.
- Geographic complaint matching shows proximity, not responsibility.
- Correlation shows association, not causation.
- Predictive risk is experimental and does not replace DOHMH inspections.
- The local Docker setup depends on the host computer, internet connection,
  Docker Desktop, and AWS session remaining available.

## Related guides

- [Project overview](../../README.md)
- [Static reference data](README.md)
- [Athena and dbt warehouse](phase4_warehouse.md)
- [Predictive model](phase5_predictive_model.md)
- [Automation and CI](phase6_automation_ci.md)
