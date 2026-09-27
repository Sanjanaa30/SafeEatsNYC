# Phase 8: Documentation and portfolio readiness

## Scope of this document

This guide completes the documentation portion of Phase 8.

At the project owner's request, this version does not cover:

- external deployment
- screenshots
- a recorded or scripted demo
- resume bullets

Those items remain separate future deliverables. The code, data, architecture,
setup, methodology, quality, security, and operating documentation are covered
here and in the linked guides.

## Goal

Make the working project understandable and reproducible for another technical
reader.

A new reader should be able to understand:

1. the problem SafeEats NYC solves
2. where the data comes from
3. how data moves through all seven implementation phases
4. why the major design decisions were made
5. how the warehouse tables and metrics are defined
6. how the model was trained and evaluated
7. how to start and test the local application
8. what the results do and do not mean

## Documentation map

| Need | Primary document |
|---|---|
| Project purpose, phases, and quick start | [Main README](../../README.md) |
| System and data-flow diagrams | [Architecture](architecture.md) |
| Field, table, grain, and metric meanings | [Data dictionary](data_dictionary.md) |
| Assumptions and known quality issues | [Data quality and limitations](data_quality_and_limitations.md) |
| Source discovery and original scope | [Phase 1](phase1_scope.md) |
| Bronze ingestion and audit behavior | [Phase 2](phase2_ingestion.md) |
| Silver cleaning and matching | [Phase 3](phase3_silver.md) |
| Athena and dbt warehouse | [Phase 4](phase4_warehouse.md) |
| Model methodology and evaluation | [Phase 5](phase5_predictive_model.md) |
| Airflow, retries, reconciliation, and CI | [Phase 6](phase6_automation_ci.md) |
| FastAPI and Next.js application | [Phase 7](phase7_dashboard.md) |
| Static geography and brand files | [Reference-data guide](README.md) |

## Important design decisions

### Preserve raw source responses

Bronze stores unchanged API pages. Cleaning begins in Silver. This preserves
traceability and allows transformation rules to change without losing the
original response.

### Keep data grains explicit

An inspection with several violations produces several source rows. The
warehouse keeps that violation-level fact and creates a separate
inspection-event model for inspection-level rates.

### Use immutable run outputs

Bronze, Silver, and model outputs use run IDs. A retry cannot silently replace
a previous successful run.

### Use overlap and deduplication together

Incremental ingestion moves back two days to catch recent source corrections.
Silver removes the intentional overlap.

### Preserve unmatched complaints

Complaints without coordinates or without a restaurant inside 100 meters are
kept. Dropping them would make match rates and totals look better than they are.

### Separate proximity from responsibility

The project uses nearby complaint matches for aggregate analysis but never
claims that a restaurant caused a complaint.

### Separate restaurant groups from brand classification

A repeated restaurant name can form a group without being fast food. A
confirmed fast-food brand comes from a separate reviewed reference policy.

### Normalize for matching, not display

The official DOHMH restaurant name is preserved for users. A separate
normalized value supports group and brand matching.

### Compare groups with rates

Raw counts favor large boroughs and cuisines. The dashboard uses per-restaurant
or per-inspection rates for fairer comparison and keeps supporting counts
available.

### Prevent model leakage

Training features contain only information known before the inspection being
predicted. Train, calibration, threshold, and test periods follow time order.

### Keep prediction separate from official truth

Risk scores are presented as experimental review signals. Official DOHMH grades
remain the authoritative result.

### Keep AWS access on the server

The browser calls FastAPI. FastAPI reads Athena and S3, validates requests, and
returns only the fields needed by the website.

### Fail safely

Internal failures are logged for developers. Users receive a generic temporary
unavailability message that does not expose credentials, SQL internals, or
private storage details.

## Reproduce the local project

The shortest path for a reader is:

1. Read the main README for the seven-phase overview.
2. Install Docker Desktop, Python 3.13, and the AWS CLI.
3. Copy **.env.example** to **.env**.
4. add the private bucket and AWS profile values.
5. sign in with the configured AWS profile.
6. start the API and frontend with the dashboard Docker profile.
7. open the website and API health endpoint.
8. run the documented backend and frontend checks.

Exact commands are maintained in the
[Run the application](../../README.md#run-the-application) section.

Refreshing the underlying data is a separate operation. The Phase 2, Phase 3,
Phase 4, and Phase 6 guides explain the full pipeline and its checks.

## AWS and secret handling

Documented safeguards:

- **.env** is ignored by Git.
- AWS credential directories are ignored by Git.
- certificate and private-key file patterns are ignored.
- credentials are mounted into containers rather than copied into images.
- the main AWS configuration directory is mounted read-only.
- GitHub Actions does not receive production AWS credentials.
- the dashboard exposes only GET routes.
- the frontend receives no AWS credentials.
- API errors return safe public messages.

Least-privilege IAM remains an account-level responsibility. A local dashboard
identity should have only:

- read access to the approved S3 data it needs
- permission to run controlled Athena queries
- access to the configured Athena workgroup
- the minimum S3 write access required for Athena query results

Pipeline and model identities need additional write permissions for their
specific prefixes. They should be separate from a dashboard-only identity when
the environment supports it.

## Controlled Athena access

The API controls Athena use through:

- fixed server-side query templates
- validated borough, cuisine, grade, sort, page, and time-range values
- normalized identifiers
- bounded page sizes
- a query timeout
- a short result cache
- read-only public API methods

Users cannot send arbitrary SQL through a dashboard endpoint.

## Unavailable-data behavior

The application is designed to fail clearly:

- health endpoints report dependency availability
- service errors become HTTP 503 responses
- public error text does not expose credentials or internal exceptions
- pages show reusable error panels
- users can retry failed sections
- missing optional restaurant data receives an explicit unavailable label
- the borough map has its own loading and error state

Backend tests verify that credential details are not returned in health errors.

## Model evaluation summary

The selected model is XGBoost, compared against a calibrated logistic
regression baseline.

The evaluation:

- uses a chronological split
- excludes immature recent outcomes
- prevents target and future data from entering features
- reports precision, recall, F1, ROC-AUC, average precision, and Brier score
- checks probability calibration
- compares actionable Watch-or-higher and Needs-attention tiers
- retains the baseline and comparison reports
- checks subgroup behavior and score drift during refreshes
- blocks promotion when required monitoring gates fail

Exact values, periods, thresholds, and artifacts are documented in the
[Phase 5 model guide](phase5_predictive_model.md).

## Documentation verification checklist

- [x] Problem and users are explained.
- [x] All seven implementation phases are connected.
- [x] Architecture and runtime flows are documented.
- [x] Data sources and dataset grains are documented.
- [x] Important design decisions are explained.
- [x] Local Python and Docker setup are documented.
- [x] AWS login and required settings are documented.
- [x] Pipeline commands and schedules are documented.
- [x] Dashboard startup, restart, health, and test commands are documented.
- [x] Warehouse dimensions, facts, marts, and important fields are documented.
- [x] Model methodology and evaluation are documented.
- [x] Assumptions, known data-quality issues, and limitations are consolidated.
- [x] Security boundaries and safe error behavior are documented.
- [x] Possible future product and analytics features are listed in the main
  README.
- [ ] External deployment is intentionally deferred.
- [ ] Screenshots are intentionally deferred.
- [ ] Demo material is intentionally deferred.
- [ ] Resume bullets are intentionally deferred.

## Documentation maintenance

Update the documentation when:

- a source dataset or filter changes
- a table grain or business metric changes
- a new dbt model or API endpoint is added
- matching thresholds or group rules change
- model features, evaluation periods, or quality gates change
- environment variables or startup commands change
- a known limitation is resolved or a new one is discovered

The main README should remain the entry point. Detailed implementation evidence
belongs in the relevant phase guide rather than being duplicated everywhere.
