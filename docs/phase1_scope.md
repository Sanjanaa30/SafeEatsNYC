# SafeEats NYC — Phase 1 MVP Scope

## Purpose

SafeEats NYC combines NYC restaurant inspections and relevant 311 complaints
to support restaurant safety lookup, borough comparisons, complaint/inspection
analysis, and one predictive B/C-grade risk model.

## Included in the MVP

- Restaurant lookup by name and ZIP/neighborhood
- Borough, cuisine, grade, and distance filters
- Current grade, score, inspection date, and violation details
- Three-year restaurant grade history and consistency indicators
- Repeat-critical-violation and recently-improved-to-A indicators
- Nearby Grade A restaurant discovery
- Citywide and borough-level grade, cuisine, and violation summaries
- Weekly 311 complaint versus critical-inspection correlation
- Approximate complaint-to-restaurant matching within 100 meters
- Three-location chain detection plus reviewed fast-food/QSR confirmation
- One B/C-grade risk classifier with explanatory factors

## Intentionally excluded

| Feature | Reason |
|---|---|
| Price or budget filters | The selected NYC datasets contain no price tier |
| Dietary labels | Vegan, halal, and gluten-free attributes are not available reliably |
| Open-now or operating-hours status | DOHMH does not provide real-time hours |
| Walking routes or navigation | Requires a routing or places service outside the MVP |
| Survey-based recommendations | No real survey dataset is included |
| Live GPS-based discovery | Requires additional live-location functionality |
| Type 2 restaurant history | The MVP uses current restaurant attributes and inspection history |
| Multiple ML models | The MVP intentionally contains one risk classifier |

## Datasets

| Dataset | Role | Phase 1 material |
|---|---|---|
| DOHMH Restaurant Inspection Results (`43nn-pn8j`) | Inspection, violation, grade, restaurant, and location data | 1,000-row local sample plus a live full-population name profile |
| NYC 311 Service Requests (`erm2-nwe9`) | Food, establishment, and rodent complaints | 1,000-row filtered local sample |
| NYC Borough Boundaries (`gthc-hcne`) | Borough map geometry | Static GeoJSON, 5 features |
| NYC ZCTA Boundaries (`35j5-n34v`) | ZIP-level map/navigation geometry | Static GeoJSON, 221 features |
| NYC 2020 NTA Boundaries (`9nt8-h7nd`) | Neighborhood assignment source | Used to build the ZIP-to-NTA lookup |
| ZIP-to-NTA lookup | Dominant neighborhood and borough per ZIP | Static CSV, 221 ZIP rows |
| OSM fast-food brands plus reviewed overrides | Fast-food/QSR confirmation | 109 canonical brands |
| Brand aliases and co-brand associations | Shared canonicalization and multi-brand preservation | Reviewed static CSV files |

At the final Phase 1 audit on August 28, 2026, the live DOHMH source contained
296,188 inspection/violation rows and 31,387 distinct CAMIS identifiers. The
name profile covered 31,386 CAMIS/DBA pairs; one source record had no DBA. Phase 1 did not download
all 296,188 rows locally. Full row-level ingestion begins in the pipeline phase.

## Dataset grain

| Dataset or artifact | Grain |
|---|---|
| DOHMH source | One row per cited violation within an inspection; inspections can therefore span multiple rows |
| DOHMH name profile | One distinct `camis` and `dba` pair returned by the live source |
| 311 source | One row per service request, keyed by `unique_key` |
| Borough boundaries | One feature per NYC borough |
| ZCTA boundaries | One feature per NYC ZCTA |
| ZIP-to-NTA lookup | One dominant NTA assignment per ZIP/ZCTA |
| Fast-food registry | One canonical brand per row |
| Brand aliases | One reviewed alternate name to canonical brand mapping per row |
| Co-brand associations | One composite location name and constituent brand per row |

## Important assumptions

- `camis` is the natural restaurant identifier in DOHMH.
- Source JSON is preserved unchanged in Bronze; cleaning occurs downstream.
- `1900-01-01` is treated as a not-yet-inspected sentinel rather than a real
  inspection date.
- Source grades such as N, Z, and P remain available in Silver; graded Gold
  metrics apply documented A/B/C rules.
- A chain has at least three distinct CAMIS values sharing a canonical name.
- Fast-food/QSR confirmation is independent of the three-location heuristic.
- DOHMH names and brand references use the same syntax normalization and alias
  rules. Co-brands produce multiple exact-match candidates without replacing
  the original DBA.
- New alias and co-brand candidates enter review queues and are never accepted
  solely because of punctuation or substring detection.
- A 311 complaint is associated with the nearest restaurant only when it is
  within approximately 100 meters. Proximity does not prove responsibility.
- ZIP-to-NTA assignment uses the largest polygon overlap and is an
  approximation because ZIP and NTA boundaries are not one-to-one.
- Correlation between complaints and inspections is descriptive, not causal.
- The three-location chain threshold and 100-meter distance are tunable MVP
  parameters, not universal facts.

## Known limitations

- Phase 1 field-quality findings come from recent 1,000-row samples; only the
  restaurant-name profile queried the full live DOHMH population.
- The live source changes as NYC updates restaurant and inspection records.
- Missing, zero, or out-of-NYC coordinates cannot be geospatially matched.
- Similar restaurant names can belong to unrelated businesses; ambiguous
  aliases remain unmatched until reviewed.
- Brand coverage depends on OpenStreetMap tagging plus documented inclusion and
  exclusion overrides.
- ZIP-to-NTA labels represent dominant geographic overlap, not exact address
  containment.
- DOHMH does not provide price, dietary, hours, or walking-route data.

## Expected dashboard pages

1. **City & Borough Safety Overview** — KPIs, grade distribution, cuisine
   performance, and common violations.
2. **Violations & 311 Correlation** — weekly trends, correlation summary, and
   geospatial overlap.
3. **SafeEats Restaurant Finder** — restaurant search, filters, history,
   nearby Grade A options, and fast-food chain summaries.
4. **Predictive Risk** — B/C-grade risk, contributing factors, and a citywide
   high-risk list.

## Phase 1 completion checklist

- [x] Repository folders separate ingestion, orchestration, transformation,
  geospatial, ML, dashboard, data, documentation, and tests.
- [x] Python is usable (`Python 3.13.3` in the project virtual environment).
- [x] Docker is usable (`Docker 29.5.3`); this machine uses the standalone
  `docker-compose` command (`v5.1.4`).
- [x] Both NYC APIs return and save validated 1,000-row samples.
- [x] Dataset fields, missingness, dates, coordinates, duplicates, and grain
  have been profiled and documented.
- [x] Static geographic and brand reference files are downloaded and validated.
- [x] Shared restaurant/brand normalization, aliases, co-brands, and review
  queues are documented and tested.
- [x] MVP scope, assumptions, exclusions, grain, limitations, and dashboard
  pages are documented here.

Phase 1 is complete. The next build step is incremental ingestion to S3 Bronze.
