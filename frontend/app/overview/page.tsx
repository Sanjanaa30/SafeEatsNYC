"use client";

import { useState } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { FilterSelect, ModernSelect } from "@/components/ui/controls";
import { ErrorState, LoadingCards } from "@/components/ui/data-states";
import { PageHeading } from "@/components/ui/page-heading";
import { ViolationCriticalityChart } from "@/components/overview/violation-criticality-chart";
import { BoroughAttentionChart } from "@/components/overview/borough-attention-chart";
import { fetchApi } from "@/lib/api";
import { formatDate, formatNumber, formatPercent } from "@/lib/format";
import type {
  ApiCollection,
  BoroughGradeDistribution,
  BoroughSummary,
  BoroughViolationCriticality,
  CuisineHeatmapCell,
  Kpi,
  Metadata,
  ViolationSummary,
} from "@/types/dashboard";

const kpiNames: Record<string, string> = {
  active_restaurants: "Total Active Restaurants",
  grade_a_compliance_rate: "Grade A Compliance Rate",
  average_inspection_score: "Avg Inspection Score",
  critical_violation_rate: "Critical Violation Rate",
  open_311_food_complaints: "Open 311 Food Complaints",
  temporary_closures_ytd: "Temp. Closures (YTD)",
};
const kpiOrder = [
  "active_restaurants",
  "grade_a_compliance_rate",
  "average_inspection_score",
  "critical_violation_rate",
  "open_311_food_complaints",
  "temporary_closures_ytd",
];
const boroughSortDescriptions: Record<string, string> = {
  safety_rank:
    "Safety rank shows boroughs with the strongest overall latest Grade A performance first.",
  complaint_rate:
    "311 rate shows boroughs with fewer food-related complaints per 1,000 restaurants first. Lower is better.",
  critical_violation_rate:
    "Critical violation rate shows boroughs with fewer serious violations per 100 inspections first. Lower is better.",
  improvement_rate:
    "Improvement rate shows boroughs where more restaurants moved from Grade B or C to Grade A first.",
  total_restaurants:
    "Total restaurants shows boroughs with the most active restaurant locations first.",
};
const criticalityDescriptions: Record<string, string> = {
  all: "Shows critical and non-critical findings together.",
  critical:
    "Critical findings are more directly connected to foodborne-illness risk.",
  non_critical:
    "Non-critical findings cover other sanitation, maintenance, and facility requirements.",
};

function KpiIcon({ metric }: { metric: string }) {
  const paths: Record<string, React.ReactNode> = {
    active_restaurants: (
      <>
        <path d="M4 10h16" />
        <path d="M5 10v9h14v-9" />
        <path d="m3 10 2-5h14l2 5" />
        <path d="M9 19v-5h6v5" />
      </>
    ),
    grade_a_compliance_rate: (
      <>
        <path d="M12 3 5 6v5c0 4.6 3 7.8 7 10 4-2.2 7-5.4 7-10V6l-7-3Z" />
        <path d="m9 12 2 2 4-4" />
      </>
    ),
    average_inspection_score: (
      <>
        <path d="M5 18a8 8 0 1 1 14 0" />
        <path d="m12 14 4-4" />
        <path d="M7 18h10" />
      </>
    ),
    critical_violation_rate: (
      <>
        <path d="m12 3 9 16H3l9-16Z" />
        <path d="M12 9v4" />
        <path d="M12 16h.01" />
      </>
    ),
    open_311_food_complaints: (
      <>
        <path d="M4 5h16v11H8l-4 4V5Z" />
        <path d="M8 9h8" />
        <path d="M8 12h5" />
      </>
    ),
    temporary_closures_ytd: (
      <>
        <rect x="5" y="4" width="14" height="16" rx="2" />
        <path d="M9 4v16" />
        <path d="M14 12h.01" />
        <path d="m15 7 3 3" />
      </>
    ),
  };
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true">
      {paths[metric] ?? paths.average_inspection_score}
    </svg>
  );
}

const boroughLabel = (value: string) =>
  value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
function displayKpi(item: Kpi) {
  if (item.value == null) return "-";
  if (item.unit === "percent") return formatPercent(item.value);
  if (item.unit === "points") return `${formatNumber(item.value, 1)} pts`;
  if (item.unit === "per_100") return `${formatNumber(item.value, 1)}/100`;
  return formatNumber(item.value);
}
export default function OverviewPage() {
  const [boroughFilter, setBoroughFilter] = useState("");
  const [boroughSort, setBoroughSort] = useState("safety_rank");
  const [activeCuisineCell, setActiveCuisineCell] = useState<string | null>(
    null,
  );
  const [criticality, setCriticality] = useState("all");
  const meta = useQuery({
    queryKey: ["metadata"],
    queryFn: ({ signal }) => fetchApi<Metadata>("/metadata", {}, signal),
  });
  const kpis = useQuery({
    queryKey: ["overview-kpis"],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<Kpi>>("/overview/kpis", {}, signal),
  });
  const boroughs = useQuery({
    queryKey: ["overview-boroughs", boroughSort],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<BoroughSummary>>(
        "/overview/boroughs",
        { sort: boroughSort },
        signal,
      ),
  });
  const distributions = useQuery({
    queryKey: ["overview-grade-distribution"],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<BoroughGradeDistribution>>(
        "/overview/grade-distribution",
        {},
        signal,
      ),
  });
  const heatmap = useQuery({
    queryKey: ["overview-cuisine-heatmap"],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<CuisineHeatmapCell>>(
        "/overview/cuisine-heatmap",
        {},
        signal,
      ),
  });
  const violations = useQuery({
    queryKey: ["overview-violations", criticality],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<ViolationSummary>>(
        "/overview/violations",
        { criticality, limit: 5 },
        signal,
      ),
  });
  const violationCriticality = useQuery({
    queryKey: ["overview-violation-criticality-by-borough"],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<BoroughViolationCriticality>>(
        "/overview/violation-criticality-by-borough",
        {},
        signal,
      ),
  });
  const queries = [
    kpis,
    boroughs,
    distributions,
    heatmap,
    violations,
    violationCriticality,
  ];
  const visibleBoroughs = boroughFilter
    ? boroughs.data?.items.filter((item) => item.borough_name === boroughFilter)
    : boroughs.data?.items;
  const violationCriticalityRows = [
    ...(violationCriticality.data?.items ?? []),
  ].sort((a, b) => {
    const rankA =
      boroughs.data?.items.find(
        (borough) => borough.borough_name === a.borough_name,
      )?.safety_rank ?? 99;
    const rankB =
      boroughs.data?.items.find(
        (borough) => borough.borough_name === b.borough_name,
      )?.safety_rank ?? 99;
    return rankA - rankB;
  });
  const cuisineNames = [
    ...new Set(heatmap.data?.items.map((item) => item.cuisine) ?? []),
  ];
  const heatmapRows = Object.values(
    (heatmap.data?.items ?? []).reduce<
      Record<
        string,
        {
          borough: string;
          safety: number;
          values: Record<
            string,
            { a: number; b: number | null; c: number | null }
          >;
        }
      >
    >((rows, item) => {
      const row = rows[item.borough_name] ?? {
        borough: item.borough_name,
        safety: item.borough_grade_a_percent,
        values: {},
      };
      row.values[item.cuisine] = {
        a: item.average_grade_a_percent,
        b: item.grade_b_percent,
        c: item.grade_c_percent,
      };
      rows[item.borough_name] = row;
      return rows;
    }, {}),
  ).sort((a, b) => b.safety - a.safety);
  const activeCuisine = activeCuisineCell
    ? (() => {
        const [borough, cuisine] = activeCuisineCell.split("|");
        const value = heatmapRows.find((row) => row.borough === borough)
          ?.values[cuisine];
        return value ? { borough, cuisine, ...value } : null;
      })()
    : (() => {
        const row = heatmapRows[0];
        const cuisine = cuisineNames[0];
        const value = row?.values[cuisine];
        return row && cuisine && value
          ? { borough: row.borough, cuisine, ...value }
          : null;
      })();
  const highestBcBorough = [...(distributions.data?.items ?? [])].sort(
    (a, b) =>
      Number(b.grade_b_percent || 0) +
      Number(b.grade_c_percent || 0) -
      (Number(a.grade_b_percent || 0) + Number(a.grade_c_percent || 0)),
  )[0];
  const highestBcCuisine = [
    ...new Map(
      (heatmap.data?.items ?? []).map((item) => [item.cuisine, item]),
    ).values(),
  ]
    .filter((item) => item.cuisine_citywide_grade_a_percent != null)
    .sort(
      (a, b) =>
        a.cuisine_citywide_grade_a_percent - b.cuisine_citywide_grade_a_percent,
    )[0];
  const highestCriticalBorough = [...violationCriticalityRows].sort(
    (a, b) =>
      Number(b.critical_findings_per_inspection || 0) -
      Number(a.critical_findings_per_inspection || 0),
  )[0];
  const activeRestaurantCount = Number(
    kpis.data?.items.find((item) => item.metric === "active_restaurants")
      ?.value || 0,
  );
  const snapshotStatus = meta.data
    ? "Warehouse snapshot"
    : meta.isError
      ? "Data unavailable"
      : "Loading snapshot";
  const retry = () => queries.forEach((query) => query.refetch());

  return (
    <main id="main-content" className="shell page-shell overview-page">
      <PageHeading
        eyebrow={`Citywide - ${snapshotStatus}`}
        title="NYC Restaurant Safety Overview"
        description="A closer look at NYC’s restaurants: inspections, complaints, and the stories behind the grades."
      />
      <div
        className="overview-source-strip"
        aria-label="Data sources and coverage"
      >
        <span>Sources: NYC DOHMH inspections and NYC 311 complaints</span>
        {meta.data ? (
          <>
            <span>
              Inspections:{" "}
              {formatDate(meta.data.data_freshness.earliest_inspection_date)}–
              {formatDate(meta.data.data_freshness.latest_inspection_date)}
            </span>
            <span>
              311 through{" "}
              {formatDate(meta.data.data_freshness.latest_complaint_date)}
            </span>
          </>
        ) : (
          <span>
            {meta.isError
              ? "Coverage dates unavailable"
              : "Loading coverage dates…"}
          </span>
        )}
        <strong>Completed snapshot, not real-time</strong>
      </div>
      {queries.some((query) => query.isError) && <ErrorState retry={retry} />}
      {kpis.isLoading ? (
        <LoadingCards count={6} />
      ) : (
        <section className="kpi-grid" aria-label="Key safety measures">
          {[...(kpis.data?.items ?? [])]
            .sort(
              (a, b) => kpiOrder.indexOf(a.metric) - kpiOrder.indexOf(b.metric),
            )
            .map((item) => (
              <article
                className={`metric-card metric-${item.metric}`}
                key={item.metric}
                tabIndex={0}
                data-explanation={item.explanation}
                aria-label={`${kpiNames[item.metric]}: ${displayKpi(item)}. ${item.trend}. ${item.explanation}`}
              >
                <span className="metric-icon">
                  <KpiIcon metric={item.metric} />
                </span>
                <div className="metric-copy">
                  <strong>{displayKpi(item)}</strong>
                  <span className="metric-label">
                    {kpiNames[item.metric] ?? item.metric}
                  </span>
                  <small className={`metric-trend ${item.trend_tone}`}>
                    {item.trend_tone === "positive"
                      ? "▲"
                      : item.trend_tone === "negative"
                        ? "▼"
                        : "•"}{" "}
                    {item.trend}
                  </small>
                </div>
              </article>
            ))}
        </section>
      )}
      <section className="section-block borough-comparison">
        <h2 className="sr-only">Borough comparison</h2>
        <div className="borough-filter-bar">
          <ModernSelect
            label="Borough"
            value={boroughFilter}
            onChange={setBoroughFilter}
            options={[
              { value: "", label: "All boroughs" },
              ...(meta.data?.boroughs.map((item) => ({
                value: item,
                label: boroughLabel(item),
              })) ?? []),
            ]}
          />
          <ModernSelect
            label="Sort boroughs by"
            value={boroughSort}
            onChange={setBoroughSort}
            options={[
              { value: "safety_rank", label: "Safety rank" },
              { value: "complaint_rate", label: "311 rate" },
              {
                value: "critical_violation_rate",
                label: "Critical violation rate",
              },
              { value: "improvement_rate", label: "Improvement rate" },
              { value: "total_restaurants", label: "Total restaurants" },
            ]}
          />
        </div>
        <p className="borough-rate-note">
          {boroughSortDescriptions[boroughSort]}
        </p>
        <div className="borough-grid">
          {visibleBoroughs?.map((item) => (
            <button
              type="button"
              className={`borough-card borough-rank-${Math.min(item.safety_rank, 5)}`}
              key={item.borough_name}
              onClick={() => setBoroughFilter(item.borough_name)}
            >
              <header>
                <div>
                  <h3>{boroughLabel(item.borough_name)}</h3>
                  <small>
                    {formatNumber(item.total_restaurants)} restaurants
                  </small>
                </div>
                <b>#{item.safety_rank} in NYC</b>
              </header>
              <div className="borough-grade">
                <strong>{formatPercent(item.grade_a_percent, 0)}</strong>
                <span>Grade A</span>
              </div>
              <i>
                <span style={{ width: `${item.grade_a_percent}%` }} />
              </i>
              <p
                className="borough-critical-issue"
                title={item.top_issue ?? undefined}
              >
                <strong>
                  <span aria-hidden="true">!</span> Top critical issue
                </strong>
                <span>{item.top_issue_summary}</span>
              </p>
              <footer>
                <span>
                  311 rate:{" "}
                  {item.complaint_rate_per_1000 == null
                    ? "-"
                    : `${formatNumber(item.complaint_rate_per_1000, 1)}/1k`}
                </span>
                <span title="Serious violations per 100 inspections; lower is better.">
                  Critical:{" "}
                  {item.critical_violation_rate_per_100 == null
                    ? "-"
                    : `${formatNumber(item.critical_violation_rate_per_100, 1)}/100`}
                </span>
              </footer>
              <small className="borough-improvement">
                Improved to A: {formatPercent(item.improvement_rate, 0)} of
                recent B/C grades
              </small>
            </button>
          ))}
        </div>
      </section>
      <section
        className="analytics-grid section-block"
        aria-label="Borough grade and cuisine analysis"
      >
        <BoroughAttentionChart
          rows={distributions.data?.items ?? []}
          loading={distributions.isLoading}
        />
        <article className="surface-card analytics-card cuisine-card">
          <header>
            <div>
              <h2>Cuisines Needing the Most Attention by Borough</h2>
              <p>Familiar cuisines ranked by citywide Grade B + C share</p>
            </div>
            <span className="cuisine-sort-note">
              Boroughs ordered by safety rank
            </span>
          </header>
          {heatmapRows.length && cuisineNames.length ? (
            <>
              <div
                className="cuisine-matrix"
                role="table"
                aria-label="Hover or focus a cuisine cell to inspect its live Grade A, B, and C shares."
              >
                <div role="row" className="matrix-header">
                  <span />
                  {cuisineNames.map((cuisine) => (
                    <strong role="columnheader" title={cuisine} key={cuisine}>
                      {cuisine}
                    </strong>
                  ))}
                </div>
                {heatmapRows.map((row) => (
                  <div role="row" className="matrix-row" key={row.borough}>
                    <strong role="rowheader">
                      {boroughLabel(row.borough)}
                    </strong>
                    {cuisineNames.map((cuisine) => {
                      const value = row.values[cuisine];
                      return (
                        <span
                          role="cell"
                          tabIndex={value ? 0 : undefined}
                          onMouseEnter={() =>
                            value &&
                            setActiveCuisineCell(`${row.borough}|${cuisine}`)
                          }
                          onFocus={() =>
                            value &&
                            setActiveCuisineCell(`${row.borough}|${cuisine}`)
                          }
                          className={`cuisine-cell ${activeCuisine?.borough === row.borough && activeCuisine?.cuisine === cuisine ? "is-active" : ""}`}
                          key={cuisine}
                          title={`${boroughLabel(row.borough)}, ${cuisine}: ${value == null ? "no current grade data" : `${formatPercent(value.a)} Grade A, ${formatPercent(value.b)} Grade B, ${formatPercent(value.c)} Grade C`}`}
                        >
                          {value == null ? (
                            "-"
                          ) : (
                            <>
                              <span className="grade-line grade-a">
                                <b>A</b>
                                <em>{formatPercent(value.a, 0)}</em>
                              </span>
                              <span className="grade-line grade-b">
                                <b>B</b>
                                <em>{formatPercent(value.b, 0)}</em>
                              </span>
                              <span className="grade-line grade-c">
                                <b>C</b>
                                <em>{formatPercent(value.c, 0)}</em>
                              </span>
                            </>
                          )}
                        </span>
                      );
                    })}
                  </div>
                ))}
              </div>
              {activeCuisine && (
                <div className="chart-insight" aria-live="polite">
                  <strong>
                    {boroughLabel(activeCuisine.borough)} -{" "}
                    {activeCuisine.cuisine}
                  </strong>
                  <span>
                    <b>{formatPercent(activeCuisine.a)}</b> Grade A;{" "}
                    <b>{formatPercent(activeCuisine.b)}</b> Grade B;{" "}
                    <b>{formatPercent(activeCuisine.c)}</b> Grade C.
                  </span>
                  <small>
                    {(activeCuisine.b ?? 0) + (activeCuisine.c ?? 0) >= 15
                      ? "This cuisine-borough combination has a comparatively larger B/C share."
                      : "Most current grades here are A."}
                  </small>
                </div>
              )}
            </>
          ) : (
            <p className="analytics-empty">Cuisine comparison is loading.</p>
          )}
        </article>
      </section>
      <aside className="surface-card analysis-explainer">
        <h2>How to read these views</h2>
        <div>
          <article>
            <strong>B/C grade share</strong>
            <p>
              Each borough bar shows the share of latest graded restaurants with
              a B or C. A longer bar means a larger B/C share; the orange and
              red parts show B and C separately.
            </p>
          </article>
          <article>
            <strong>Cuisine attention view</strong>
            <p>
              The familiar cuisines are ordered by their citywide combined Grade
              B + C percentage. Each cell shows the Grade A, B, and C
              percentages using green, orange, and red, making areas needing
              attention easy to identify.
            </p>
          </article>
        </div>
        <p className="analysis-takeaway">
          Use both together: the first view highlights boroughs with more B/C
          grades; the second shows the grade mix for six familiar cuisines.
        </p>
      </aside>
      <section className="section-block violation-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Recurring findings</p>
            <h2>Most frequent violations</h2>
            <p>
              Top five violations by the number of restaurants affected across
              the recorded inspection history. Each restaurant is counted once
              for each violation type.
            </p>
          </div>
          <div className="violation-filter-control">
            <FilterSelect
              label="Show"
              value={criticality}
              onChange={(event) => setCriticality(event.target.value)}
            >
              <option value="all">All findings</option>
              <option value="critical">Critical findings</option>
              <option value="non_critical">Non-critical findings</option>
            </FilterSelect>
            <p>{criticalityDescriptions[criticality]}</p>
          </div>
        </div>
        <div className="violation-rate-heading">
          Restaurants affected out of every 100 current restaurants
          <span>This is a restaurant rate, not a count of repeat findings.</span>
        </div>
        <div className="rank-list violation-list">
          {violations.data?.items.map((item, index) => {
            const affectedRate = activeRestaurantCount
              ? (100 * Number(item.affected_restaurant_count)) /
                activeRestaurantCount
              : null;
            return (
              <article key={item.violation_key}>
                <span className="rank">{index + 1}</span>
                <div className="violation-details">
                  <strong>{item.short_label}</strong>
                  <small>
                    {formatNumber(item.affected_restaurant_count)} unique
                    restaurants had this violation
                  </small>
                  <details className="violation-official">
                    <summary>Read full DOHMH wording</summary>
                    <p>{item.violation_description}</p>
                  </details>
                  <span className="violation-track" aria-hidden="true">
                    <span
                      style={{
                        width: `${Math.min(100, affectedRate ?? 0)}%`,
                      }}
                    />
                  </span>
                </div>
                <b
                  className="violation-rate"
                  aria-label={
                    affectedRate == null
                      ? "Affected restaurant rate unavailable"
                      : `${formatNumber(affectedRate, 0)} out of every 100 current restaurants had this violation`
                  }
                >
                  {affectedRate == null
                    ? "—"
                    : formatNumber(affectedRate, 0)}{" "}
                  <span>of every 100 restaurants</span>
                </b>
              </article>
            );
          })}
        </div>
      </section>
      <ViolationCriticalityChart
        rows={violationCriticalityRows}
        loading={violationCriticality.isLoading}
      />
      <aside
        className="surface-card overview-takeaways"
        aria-labelledby="takeaways-title"
      >
        <div>
          <p className="eyebrow">At a glance</p>
          <h2 id="takeaways-title">What stands out</h2>
        </div>
        <ul>
          {highestBcBorough && (
            <li>
              <strong>{boroughLabel(highestBcBorough.borough_name)}</strong> has
              the largest latest B/C share:{" "}
              <b>
                {formatPercent(
                  Number(highestBcBorough.grade_b_percent || 0) +
                    Number(highestBcBorough.grade_c_percent || 0),
                )}
              </b>
              .
            </li>
          )}
          {highestBcCuisine && (
            <li>
              <strong>{highestBcCuisine.cuisine}</strong> has the largest
              citywide B/C share among the six cuisines shown:{" "}
              <b>
                {formatPercent(
                  100 - highestBcCuisine.cuisine_citywide_grade_a_percent,
                )}
              </b>
              .
            </li>
          )}
          {highestCriticalBorough && (
            <li>
              <strong>
                {boroughLabel(highestCriticalBorough.borough_name)}
              </strong>{" "}
              averaged the most critical findings per inspection across the
              recorded history:{" "}
              <b>
                {formatNumber(
                  highestCriticalBorough.critical_findings_per_inspection,
                  2,
                )}
              </b>
              .
            </li>
          )}
        </ul>
        <nav aria-label="Explore these findings">
          <Link href="/finder">Explore restaurants</Link>
          <Link href="/correlation">Explore 311 patterns</Link>
        </nav>
      </aside>
    </main>
  );
}
