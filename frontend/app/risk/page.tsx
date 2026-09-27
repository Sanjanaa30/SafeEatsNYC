"use client";

import { Suspense, useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "next/navigation";
import { GradeBadge, RiskBadge } from "@/components/ui/badges";
import { FilterSelect, SearchField } from "@/components/ui/controls";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui/data-states";
import { Modal } from "@/components/ui/modal";
import { PageHeading } from "@/components/ui/page-heading";
import { Pagination } from "@/components/ui/pagination";
import { ResponsiveTable } from "@/components/ui/responsive-table";
import { fetchApi } from "@/lib/api";
import { formatDate, formatPercent, titleCase } from "@/lib/format";
import type {
  ApiCollection,
  ApiRecord,
  Metadata,
  RiskFactor,
  RiskRecord,
} from "@/types/dashboard";

export default function RiskPage() {
  return (
    <Suspense
      fallback={
        <main id="main-content" className="shell page-shell">
          <LoadingState label="Opening risk analysis" />
        </main>
      }
    >
      <RiskPageContent />
    </Suspense>
  );
}

function RiskPageContent() {
  const searchParams = useSearchParams();
  const linkedRestaurant = searchParams.get("restaurant") ?? "";
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [borough, setBorough] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [category, setCategory] = useState("");
  const [sort, setSort] = useState("risk");
  const [direction, setDirection] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);
  const [selectedKey, setSelectedKey] = useState(linkedRestaurant);
  useEffect(() => {
    const timer = setTimeout(
      () => setSearch(query.trim().length >= 2 ? query.trim() : ""),
      400,
    );
    return () => clearTimeout(timer);
  }, [query]);
  const meta = useQuery({
    queryKey: ["metadata"],
    queryFn: ({ signal }) => fetchApi<Metadata>("/metadata", {}, signal),
  });
  const risks = useQuery({
    queryKey: [
      "risk-list",
      search,
      borough,
      cuisine,
      category,
      sort,
      direction,
      page,
    ],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<RiskRecord>>(
        "/risk/restaurants",
        {
          query: search || undefined,
          borough: borough || undefined,
          cuisine: cuisine || undefined,
          category: category || undefined,
          sort,
          direction,
          page,
          page_size: 20,
        },
        signal,
      ),
  });
  const effectiveKey = selectedKey;
  const detail = useQuery({
    queryKey: ["risk-detail", effectiveKey],
    queryFn: ({ signal }) =>
      fetchApi<ApiRecord<RiskRecord>>(
        `/risk/restaurants/${effectiveKey}`,
        {},
        signal,
      ),
    enabled: !!effectiveKey,
  });
  const selected =
    detail.data?.data ??
    risks.data?.items.find((x) => x.restaurant_key === effectiveKey);
  const changeSort = (key: string) => {
    if (sort === key)
      setDirection((value) => (value === "asc" ? "desc" : "asc"));
    else {
      setSort(key);
      setDirection(key === "name" ? "asc" : "desc");
    }
  };
  return (
    <main id="main-content" className="shell page-shell">
      <PageHeading
        eyebrow="Experimental prediction"
        title="Predictive Risk"
        description="Review the estimated probability that a restaurant’s next graded inspection will be B or C, using information known before that inspection."
      />
      <aside className="model-notice">
        <strong>Experimental prediction</strong>
        <span>
          This experimental model estimates the probability of a B/C result at
          the next graded inspection. It is not an official NYC grade and does
          not establish that a restaurant is unsafe.
        </span>
      </aside>
      <div className="filter-panel">
        <SearchField
          label="Restaurant name or ID"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search restaurants"
        />
        <FilterSelect
          label="Borough"
          value={borough}
          onChange={(e) => setBorough(e.target.value)}
        >
          <option value="">All boroughs</option>
          {meta.data?.boroughs.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </FilterSelect>
        <FilterSelect
          label="Cuisine"
          value={cuisine}
          onChange={(e) => setCuisine(e.target.value)}
        >
          <option value="">All cuisines</option>
          {meta.data?.cuisines.map((x) => (
            <option key={x}>{x}</option>
          ))}
        </FilterSelect>
        <FilterSelect
          label="Risk category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
        >
          <option value="">All categories</option>
          <option value="LOW">Lower risk</option>
          <option value="MODERATE">Watch</option>
          <option value="HIGH">Needs attention</option>
        </FilterSelect>
      </div>
      <section className="section-block">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Current scores</p>
            <h2>Restaurant risk table</h2>
          </div>
          <p>Select a row to explain its score.</p>
        </div>
        {risks.isLoading ? (
          <LoadingState />
        ) : risks.isError ? (
          <ErrorState retry={() => risks.refetch()} />
        ) : risks.data?.items.length ? (
          <>
            <ResponsiveTable
              caption="Current restaurant risk scores"
              rows={risks.data.items}
              rowKey={(x) => x.restaurant_key}
              onRow={(x) => setSelectedKey(x.restaurant_key)}
              sort={sort}
              direction={direction}
              onSort={changeSort}
              columns={[
                {
                  key: "name",
                  label: "Restaurant",
                  sortKey: "name",
                  render: (x) => (
                    <>
                      <strong>{x.restaurant_name}</strong>
                      <br />
                      <small>
                        {x.borough_name} · {x.cuisine}
                      </small>
                    </>
                  ),
                },
                {
                  key: "grade",
                  label: "Current grade",
                  render: (x) => <GradeBadge grade={x.current_grade} />,
                },
                {
                  key: "date",
                  label: "Latest inspection",
                  sortKey: "inspection_date",
                  render: (x) => formatDate(x.latest_inspection_date),
                },
                {
                  key: "risk",
                  label: "Risk probability",
                  sortKey: "risk",
                  render: (x) => (
                    <RiskBadge
                      category={x.risk_category}
                      probability={x.risk_probability}
                    />
                  ),
                },
              ]}
            />
            <Pagination
              page={page}
              pageSize={20}
              total={risks.data.total}
              onPage={setPage}
            />
          </>
        ) : (
          <EmptyState message="No scored restaurants match these filters." />
        )}
      </section>
      <RiskAnalysisModal
        selected={selected}
        loading={detail.isLoading}
        error={detail.isError}
        retry={() => detail.refetch()}
        open={!!selectedKey}
        onClose={() => setSelectedKey("")}
      />
    </main>
  );
}

function RiskAnalysisModal({
  selected,
  loading,
  error,
  retry,
  open,
  onClose,
}: {
  selected?: RiskRecord;
  loading: boolean;
  error: boolean;
  retry: () => void;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      title={selected?.restaurant_name ?? "Restaurant risk analysis"}
      onClose={onClose}
    >
      {loading ? (
        <LoadingState label="Loading risk analysis" />
      ) : error ? (
        <ErrorState retry={retry} />
      ) : selected ? (
        <div className="risk-modal-content">
          <header>
            <div>
              <span>{selected.cuisine || "Cuisine unavailable"}</span>
              <span>{selected.borough_name || "Borough unavailable"}</span>
            </div>
            <p>{selected.address || "Address unavailable"}</p>
          </header>
          <div className="risk-visuals">
            <div className="risk-score-panel">
              <RiskGauge
                probability={selected.risk_probability}
                category={selected.risk_category}
              />
              <div className="badge-row">
                <GradeBadge grade={selected.current_grade} />
                <RiskBadge category={selected.risk_category} />
              </div>
            </div>
            <DrivingFactors factors={selected.main_contributing_factors} />
          </div>
          <section className="risk-guide">
            <h2>How to read the score</h2>
            <div>
              <div className="risk-scale">
                <span>
                  <i className="low" />
                  Lower risk
                </span>
                <span>
                  <i className="moderate" />
                  Watch
                </span>
                <span>
                  <i className="high" />
                  Needs attention
                </span>
              </div>
              <p>
                <strong>Needs attention</strong> is the stricter alert.{" "}
                <strong>Watch</strong> means the restaurant may deserve review;
                it does not mean the restaurant is unsafe.
              </p>
              <p>
                This XGBoost estimate predicts a possible future B or C grade.
                Official DOHMH inspection results remain the trusted source.
              </p>
            </div>
          </section>
          <p className="fine-print">
            Model {selected.model_version} · scored{" "}
            {formatDate(selected.scoring_timestamp)}
          </p>
        </div>
      ) : (
        <EmptyState message="No risk analysis is available for this restaurant." />
      )}
    </Modal>
  );
}

function RiskGauge({
  probability,
  category,
}: {
  probability: number;
  category: string;
}) {
  const percent = Math.max(0, Math.min(100, probability * 100));
  return (
    <div
      className="risk-gauge"
      role="img"
      aria-label={`${percent.toFixed(1)} percent probability, ${category} risk`}
      style={{ "--risk-percent": `${percent}%` } as React.CSSProperties}
    >
      <div>
        <strong>{formatPercent(percent)}</strong>
        <span>{titleCase(category)} risk</span>
      </div>
    </div>
  );
}

function DrivingFactors({ factors }: { factors: RiskFactor[] }) {
  const [order, setOrder] = useState<"highest" | "lowest">("highest");
  const sorted = [...factors].sort((left, right) => {
    const difference =
      Math.abs(right.contribution) - Math.abs(left.contribution);
    return order === "highest" ? difference : -difference;
  });
  const strongest = Math.max(
    ...factors.map((factor) => Math.abs(factor.contribution)),
    0.0001,
  );

  return (
    <section
      className="driving-factors"
      aria-labelledby="driving-factors-title"
    >
      <header>
        <div>
          <h3 id="driving-factors-title">Top Driving Factors</h3>
          <p>What most influenced the prediction for this restaurant</p>
        </div>
        <div className="factor-sort" aria-label="Sort driving factors">
          <button
            type="button"
            className={order === "highest" ? "active" : ""}
            aria-pressed={order === "highest"}
            onClick={() => setOrder("highest")}
          >
            Highest impact
          </button>
          <button
            type="button"
            className={order === "lowest" ? "active" : ""}
            aria-pressed={order === "lowest"}
            onClick={() => setOrder("lowest")}
          >
            Lowest impact
          </button>
        </div>
      </header>
      {sorted.length ? (
        <ol className="factor-bars">
          {sorted.map((factor) => {
            const impact = Math.round(
              (Math.abs(factor.contribution) / strongest) * 100,
            );
            const raisesRisk = factor.direction
              ? factor.direction.toLowerCase() !== "lowers"
              : factor.contribution >= 0;
            return (
              <li key={factor.feature}>
                <div className="factor-name">
                  <strong>{friendlyFactorName(factor.feature)}</strong>
                  <small className={raisesRisk ? "raises" : "lowers"}>
                    {raisesRisk ? "Raises risk" : "Lowers risk"}
                  </small>
                </div>
                <span className="factor-track" aria-hidden="true">
                  <i
                    className={raisesRisk ? "raises" : "lowers"}
                    style={{ width: `${impact}%` }}
                  />
                </span>
                <b aria-label={`${impact} percent relative impact`}>
                  {impact}%
                </b>
              </li>
            );
          })}
        </ol>
      ) : (
        <EmptyState
          title="No factors available"
          message="The model did not provide factor details for this restaurant."
        />
      )}
      {sorted.length ? (
        <p className="factor-note">
          The percentages compare these factors with the strongest one shown.
          They are not the predicted risk.
        </p>
      ) : null}
    </section>
  );
}

function friendlyFactorName(feature: string) {
  const normalized = feature.trim().toLowerCase();
  const labels: Record<string, string> = {
    "historical grade a rate": "Past Grade A record",
    "recent 3 inspection avg score": "Recent inspection scores",
    "previous grade a": "Previous inspection grade",
    "days since last inspection": "Time since last inspection",
    "prior critical violations": "Previous critical violations",
  };
  if (labels[normalized]) return labels[normalized];
  if (normalized.startsWith("cuisine "))
    return `${titleCase(normalized.slice(8))} cuisine pattern`;
  if (normalized.startsWith("borough "))
    return `${titleCase(normalized.slice(8))} borough pattern`;
  return titleCase(feature);
}
