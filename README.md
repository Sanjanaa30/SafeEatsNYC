# SafeEats NYC

NYC restaurant safety and consumer intelligence platform.

## Problem

NYC restaurant inspection results and relevant 311 complaints are published
in separate systems. SafeEats NYC combines them to make restaurant safety
history, borough-level patterns, and future B/C-grade risk easier to understand.

## MVP outcomes

1. Look up a restaurant's current grade and safety history.
2. Compare restaurant-safety patterns across NYC boroughs.
3. Examine the relationship between relevant 311 complaints and inspection failures.
4. Estimate which restaurants are at risk of receiving a B or C grade.

## Dashboard

The Streamlit application contains four pages:

1. City & Borough Safety Overview
2. Violations & 311 Correlation
3. SafeEats Restaurant Finder
4. Predictive Risk

The visual and interaction reference is `safeeats_dashboard_mockup.html`.

## Data sources

- NYC DOHMH Restaurant Inspection Results: `43nn-pn8j`
- NYC 311 Service Requests: `erm2-nwe9`
- NYC geographic boundary reference data
- ZIP-to-neighborhood/NTA reference data
- Fast-food brand reference data

## Planned architecture

NYC APIs → S3 Bronze JSON → PySpark Silver Parquet → dbt Gold models →
Amazon Athena → Streamlit

Airflow runs locally through Docker Compose.

## Current status

Phase 1: project setup and data exploration.

## MVP exclusions

The MVP does not include price tiers, open-now status, dietary tags,
survey-based recommendations, walking-distance navigation, or Type 2
restaurant history.