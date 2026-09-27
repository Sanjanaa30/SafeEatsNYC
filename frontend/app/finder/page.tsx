"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  FilterSelect,
  SearchField,
  SegmentedControl,
} from "@/components/ui/controls";
import {
  EmptyState,
  ErrorState,
  LoadingCards,
  LoadingState,
} from "@/components/ui/data-states";
import { Modal } from "@/components/ui/modal";
import { PageHeading } from "@/components/ui/page-heading";
import { Pagination } from "@/components/ui/pagination";
import { fetchApi } from "@/lib/api";
import { formatNumber, formatPercent } from "@/lib/format";
import { simpleViolationName } from "@/lib/violations";
import type {
  ApiCollection,
  ApiRecord,
  Chain,
  History,
  Metadata,
  NearbyRestaurant,
  Restaurant,
  Violation,
} from "@/types/dashboard";

export default function FinderPage() {
  const [tab, setTab] = useState("restaurants");
  const [query, setQuery] = useState("");
  const [search, setSearch] = useState("");
  const [borough, setBorough] = useState("");
  const [cuisine, setCuisine] = useState("");
  const [grade, setGrade] = useState("");
  const [flag, setFlag] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Restaurant | null>(null);
  const [selectedChain, setSelectedChain] = useState<Chain | null>(null);
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(query.trim().length >= 2 ? query.trim() : "");
      setPage(1);
    }, 400);
    return () => clearTimeout(timer);
  }, [query]);
  const meta = useQuery({
    queryKey: ["metadata"],
    queryFn: ({ signal }) => fetchApi<Metadata>("/metadata", {}, signal),
  });
  const improved = useQuery({
    queryKey: ["recently-improved"],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<Restaurant>>(
        "/restaurants/recently-improved",
        { limit: 6 },
        signal,
      ),
  });
  const restaurants = useQuery({
    queryKey: ["restaurants", search, borough, cuisine, grade, flag, page],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<Restaurant>>(
        "/restaurants",
        {
          query: search || undefined,
          borough: borough || undefined,
          cuisine: cuisine || undefined,
          grade: grade || undefined,
          flag: flag || undefined,
          sort: "name",
          page,
          page_size: 12,
        },
        signal,
      ),
    enabled: tab === "restaurants",
  });
  const chains = useQuery({
    queryKey: ["chains", search, borough, page],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<Chain>>(
        "/chains",
        {
          query: search || undefined,
          borough: borough || undefined,
          confirmed_fast_food_only: false,
          sort: "average_risk",
          direction: "desc",
          page,
          page_size: 12,
        },
        signal,
      ),
    enabled: tab === "chains",
  });
  return (
    <main id="main-content" className="shell page-shell">
      <PageHeading
        eyebrow="Search and compare"
        title="Restaurant Finder & Group Explorer"
        description="Find any restaurant location in the warehouse, or open a restaurant group to compare its locations."
      />
      {improved.data?.items.length ? (
        <section className="improved-strip">
          <div>
            <p className="eyebrow">Recently improved</p>
            <h2>Moved to Grade A</h2>
          </div>
          {improved.data.items.map((item) => (
            <button
              type="button"
              key={item.restaurant_key}
              onClick={() => setSelected(item)}
            >
              <strong>{item.restaurant_name}</strong>
              <span>{item.borough_name}</span>
            </button>
          ))}
        </section>
      ) : null}
      <SegmentedControl
        label="Explorer"
        value={tab}
        onChange={(value) => {
          setTab(value);
          setPage(1);
          setFlag("");
        }}
        options={[
          { value: "restaurants", label: "Restaurant locations" },
          { value: "chains", label: "Restaurant groups" },
        ]}
      />
      <div className="filter-panel finder-filters">
        <SearchField
          label="Search Restaurants"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Enter a restaurant name, address, ZIP or ID"
        />
        <FilterSelect
          label="Borough"
          value={borough}
          onChange={(e) => {
            setBorough(e.target.value);
            setPage(1);
          }}
        >
          <option value="">All boroughs</option>
          {meta.data?.boroughs.map((item) => (
            <option key={item}>{item}</option>
          ))}
        </FilterSelect>
        {tab === "restaurants" && (
          <>
            <FilterSelect
              label="Cuisine"
              value={cuisine}
              onChange={(e) => {
                setCuisine(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All cuisines</option>
              {meta.data?.cuisines.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </FilterSelect>
            <FilterSelect
              label="Grade"
              value={grade}
              onChange={(e) => {
                setGrade(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All grades</option>
              <option>A</option>
              <option>B</option>
              <option>C</option>
            </FilterSelect>
            <FilterSelect
              label="Show"
              value={flag}
              onChange={(e) => {
                setFlag(e.target.value);
                setPage(1);
              }}
            >
              <option value="">All restaurant locations</option>
              <option value="independent">Independent restaurants</option>
              <option value="chain">Individual group locations</option>
              <option value="fast_food">Fast-food locations</option>
              <option value="recently_improved">Recently improved</option>
              <option value="repeat_critical">Repeated critical finding</option>
            </FilterSelect>
          </>
        )}
      </div>
      {tab === "restaurants" ? (
        <Results
          query={restaurants}
          page={page}
          setPage={setPage}
          onSelect={setSelected}
        />
      ) : (
        <ChainResults
          query={chains}
          page={page}
          setPage={setPage}
          onSelect={setSelectedChain}
        />
      )}
      <RestaurantDetails
        selected={selected}
        onClose={() => setSelected(null)}
      />
      <ChainDetails
        selected={selectedChain}
        onClose={() => setSelectedChain(null)}
      />
    </main>
  );
}

function Results({
  query,
  page,
  setPage,
  onSelect,
}: {
  query: ReturnType<typeof useQuery<ApiCollection<Restaurant>>>;
  page: number;
  setPage: (p: number) => void;
  onSelect: (r: Restaurant) => void;
}) {
  if (query.isLoading) return <LoadingCards count={6} />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;
  if (!query.data?.items.length)
    return (
      <EmptyState message="No restaurants match these filters. Try broadening the search." />
    );
  return (
    <>
      <p className="result-count">
        {formatNumber(query.data.total)} restaurants found
      </p>
      <div className="result-grid restaurant-result-grid">
        {query.data.items.map((item) => {
          const days =
            item.days_since_inspection ??
            daysSinceInspection(item.latest_inspection_date);
          const grade = item.current_grade || "U";
          return (
            <button
              className="restaurant-result-card"
              type="button"
              key={item.restaurant_key}
              onClick={() => onSelect(item)}
            >
              <header>
                <div>
                  <h2>{item.restaurant_name}</h2>
                  <div className="restaurant-result-tags">
                    <span>{item.cuisine || "Cuisine unavailable"}</span>
                    <span>{item.borough_name || "Borough unavailable"}</span>
                    {item.zipcode && <span>ZIP {item.zipcode}</span>}
                    {item.has_repeated_critical_violation && (
                      <span className="restaurant-repeat-tag">
                        △ Repeat critical
                      </span>
                    )}
                  </div>
                </div>
                <span
                  className={`restaurant-result-grade grade-${grade.toLowerCase()}`}
                  aria-label={`Current grade ${grade === "U" ? "not available" : grade}`}
                >
                  {grade === "U" ? "—" : grade}
                </span>
              </header>
              <div className="restaurant-grade-trend">
                <strong>3-year grade trend</strong>
                <div>
                  {item.three_year_grades?.length ? (
                    item.three_year_grades.map((yearGrade, index) => (
                      <span
                        className={`trend-grade trend-grade-${yearGrade.toLowerCase()}`}
                        key={`${yearGrade}-${index}`}
                        title={`Year ${index + 1}: Grade ${yearGrade}`}
                      />
                    ))
                  ) : (
                    <small>No three-year grade history</small>
                  )}
                </div>
              </div>
              <footer>
                <span>Score: {item.current_score ?? "—"} pts</span>
                <span>
                  {days == null
                    ? "Inspection date unavailable"
                    : `${formatNumber(days)}d since inspection`}
                </span>
              </footer>
            </button>
          );
        })}
      </div>
      <Pagination
        page={page}
        pageSize={12}
        total={query.data.total}
        onPage={setPage}
      />
    </>
  );
}

function ChainResults({
  query,
  page,
  setPage,
  onSelect,
}: {
  query: ReturnType<typeof useQuery<ApiCollection<Chain>>>;
  page: number;
  setPage: (p: number) => void;
  onSelect: (r: Chain) => void;
}) {
  if (query.isLoading) return <LoadingCards count={6} />;
  if (query.isError) return <ErrorState retry={() => query.refetch()} />;
  if (!query.data?.items.length)
    return <EmptyState message="No confirmed chains match these filters." />;
  return (
    <>
      <p className="result-count">
        {formatNumber(query.data.total)} restaurant groups found
      </p>
      <div className="result-grid chain-grid">
        {query.data.items.map((item) => {
          const locationGrades = chainLocationGrades(item);
          const shownGrades = locationGrades.slice(0, 8);
          const hiddenGradeCount = Math.max(
            0,
            locationGrades.length - shownGrades.length,
          );
          const commonGrade = mostCommonChainGrade(item);
          return (
            <button
              className="chain-card"
              type="button"
              key={item.chain_key}
              onClick={() => onSelect(item)}
            >
              <header>
                <div>
                  <h2>{item.chain_name}</h2>
                  <div className="chain-card-tags">
                    <span className="chain-identity">
                      <ChainLinkIcon /> Chain
                    </span>
                    <span>
                      {item.is_confirmed_fast_food
                        ? "Fast food"
                        : item.cuisines?.[0] || "Restaurant group"}
                    </span>
                    <span>{formatNumber(item.location_count)} locations</span>
                  </div>
                </div>
                <span
                  className={`chain-summary-grade grade-${commonGrade.toLowerCase()}`}
                  title={`Most common current location grade: ${commonGrade}`}
                >
                  {commonGrade === "U" ? "—" : commonGrade}
                </span>
              </header>
              {item.has_repeated_critical_location && (
                <span className="chain-repeat-warning">
                  Repeat critical finding at a location
                </span>
              )}
              <div
                className="chain-grade-summary"
                aria-label="Current grade at each chain location"
              >
                <strong>Grade by location</strong>
                <div>
                  {shownGrades.map((grade, index) => (
                    <span
                      className={`chain-grade-chip grade-${grade.toLowerCase()}`}
                      key={`${grade}-${index}`}
                    >
                      {grade === "U" ? "—" : grade}
                    </span>
                  ))}
                  {hiddenGradeCount > 0 && (
                    <span className="chain-grade-more">
                      +{hiddenGradeCount}
                    </span>
                  )}
                </div>
              </div>
              <footer>
                <span>
                  {formatNumber(item.borough_count)}{" "}
                  {item.borough_count === 1 ? "borough" : "boroughs"}
                </span>
                <span>
                  Avg. risk:{" "}
                  {item.average_risk_probability == null
                    ? "Not scored"
                    : formatPercent(item.average_risk_probability * 100, 0)}
                </span>
              </footer>
            </button>
          );
        })}
      </div>
      <Pagination
        page={page}
        pageSize={12}
        total={query.data.total}
        onPage={setPage}
      />
    </>
  );
}

function mostCommonChainGrade(chain: Chain) {
  const grades = [
    { grade: "A", count: chain.grade_a_location_count },
    { grade: "B", count: chain.grade_b_location_count },
    { grade: "C", count: chain.grade_c_location_count },
  ];
  grades.sort((left, right) => right.count - left.count);
  return grades[0].count > 0 ? grades[0].grade : "U";
}

function chainLocationGrades(chain: Chain) {
  return [
    ...Array(chain.grade_a_location_count).fill("A"),
    ...Array(chain.grade_b_location_count).fill("B"),
    ...Array(chain.grade_c_location_count).fill("C"),
    ...Array(chain.ungraded_location_count).fill("U"),
  ] as string[];
}

function ChainLinkIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24">
      <path d="M10.6 13.4a4 4 0 0 0 5.7 0l2.1-2.1a4 4 0 0 0-5.7-5.7l-1.2 1.2m1.9 3.8a4 4 0 0 0-5.7 0l-2.1 2.1a4 4 0 0 0 5.7 5.7l1.2-1.2" />
    </svg>
  );
}

function RestaurantDetails({
  selected,
  onClose,
}: {
  selected: Restaurant | null;
  onClose: () => void;
}) {
  const router = useRouter();
  const key = selected?.restaurant_key ?? "";
  const detail = useQuery({
    queryKey: ["restaurant-detail", key],
    queryFn: ({ signal }) =>
      fetchApi<ApiRecord<Restaurant>>(`/restaurants/${key}`, {}, signal),
    enabled: !!key,
  });
  const history = useQuery({
    queryKey: ["restaurant-history", key],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<History>>(
        `/restaurants/${key}/history`,
        {},
        signal,
      ),
    enabled: !!key,
  });
  const violations = useQuery({
    queryKey: ["restaurant-violations", key],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<Violation>>(
        `/restaurants/${key}/violations`,
        { limit: 30 },
        signal,
      ),
    enabled: !!key,
  });
  const nearby = useQuery({
    queryKey: ["restaurant-nearby", key],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<NearbyRestaurant>>(
        `/restaurants/${key}/nearby`,
        { radius_meters: 1000, limit: 8 },
        signal,
      ),
    enabled: !!key,
  });
  const row = detail.data?.data ?? selected;
  const riskProbability = row?.risk?.risk_probability ?? row?.risk_probability;
  const yearlyGrades = (() => {
    const byYear = new Map<number, History>();
    const cutoffYear = new Date().getUTCFullYear() - 2;
    for (const item of history.data?.items ?? []) {
      const year = new Date(
        `${item.inspection_date}T00:00:00Z`,
      ).getUTCFullYear();
      if (
        year >= cutoffYear &&
        ["A", "B", "C"].includes(item.grade) &&
        !byYear.has(year)
      )
        byYear.set(year, item);
    }
    return [...byYear.entries()].sort(([left], [right]) => left - right);
  })();
  const violationTypes = Array.from(
    new Map(
      (violations.data?.items ?? []).map((item) => [
        simpleViolationName(item.violation_description),
        item,
      ]),
    ).entries(),
  ).slice(0, 6);
  const openRiskAnalysis = () => {
    onClose();
    router.push(`/risk?restaurant=${encodeURIComponent(key)}`);
  };

  return (
    <Modal
      open={!!selected}
      title={row?.restaurant_name ?? "Restaurant details"}
      onClose={onClose}
    >
      {detail.isLoading ? (
        <LoadingState />
      ) : (
        row && (
          <div className="restaurant-profile">
            <section className="restaurant-profile-heading">
              <div className="restaurant-profile-tags">
                <span>{row.cuisine || "Cuisine unavailable"}</span>
                <span>{row.borough_name || "Borough unavailable"}</span>
                {row.zipcode && <span>ZIP {row.zipcode}</span>}
              </div>
              <span
                className={`restaurant-grade-mark grade-${(row.current_grade || "unknown").toLowerCase()}`}
                aria-label={`Current grade ${row.current_grade || "not available"}`}
              >
                {row.current_grade || "—"}
              </span>
              <p>{row.address || "Address unavailable"}</p>
            </section>

            <section
              className="restaurant-profile-metrics"
              aria-label="Current restaurant summary"
            >
              <article data-tooltip="The latest inspection score. Lower scores are generally better.">
                <strong>{row.current_score ?? "—"}</strong>
                <span>Inspection score</span>
              </article>
              <article data-tooltip="Days since the restaurant's latest recorded inspection.">
                <strong>
                  {row.days_since_inspection == null
                    ? "—"
                    : `${formatNumber(row.days_since_inspection)}d`}
                </strong>
                <span>Since inspection</span>
              </article>
              <article data-tooltip="An XGBoost model estimate—not an official DOHMH result—of the chance that the next graded inspection receives B or C.">
                <strong>
                  {riskProbability == null
                    ? "—"
                    : formatPercent(riskProbability * 100, 0)}
                </strong>
                <span>Predicted B/C chance</span>
              </article>
            </section>

            <section className="restaurant-profile-section">
              <div className="restaurant-profile-section-title">
                <h3>Three-year grade history</h3>
                <p>Latest recorded grade in each of the past three years.</p>
              </div>
              {history.isLoading ? (
                <LoadingState label="Loading grade history" />
              ) : yearlyGrades.length ? (
                <div className="grade-history-bars">
                  {yearlyGrades.map(([year, item]) => (
                    <article key={year}>
                      <span
                        className={`grade-history-column grade-${item.grade.toLowerCase()}`}
                        style={{
                          height:
                            item.grade === "A"
                              ? 72
                              : item.grade === "B"
                                ? 52
                                : 36,
                        }}
                      >
                        {item.grade}
                      </span>
                      <strong>{year}</strong>
                      <small>Score {item.score ?? "—"}</small>
                    </article>
                  ))}
                </div>
              ) : (
                <EmptyState
                  title="No grade history"
                  message="No A, B or C grade was recorded during the past three years."
                />
              )}
            </section>

            <section className="restaurant-profile-section">
              <div className="restaurant-profile-section-title">
                <h3>Recent violation types</h3>
                <p>Plain-language summaries from recent inspection records.</p>
              </div>
              {violations.isLoading ? (
                <LoadingState label="Loading recent violations" />
              ) : violationTypes.length ? (
                <ul className="restaurant-violation-types">
                  {violationTypes.map(([label, item]) => (
                    <li key={label}>
                      <strong>{label}</strong>
                      <span
                        className={
                          item.is_critical ? "critical" : "non-critical"
                        }
                      >
                        {item.is_critical ? "Critical" : "Non-critical"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  title="No recent violations"
                  message="No recent violation records were found."
                />
              )}
            </section>

            <section className="restaurant-profile-section">
              <div className="restaurant-profile-section-title">
                <h3>Nearby Grade A options</h3>
                <p>
                  Distances are straight-line estimates rather than walking
                  routes.
                </p>
              </div>
              {nearby.isLoading ? (
                <LoadingState label="Loading nearby restaurants" />
              ) : nearby.data?.items.length ? (
                <ul className="restaurant-nearby-list">
                  {nearby.data.items.map((item) => (
                    <li key={item.restaurant_key}>
                      <Link
                        href={`/risk?restaurant=${encodeURIComponent(item.restaurant_key)}`}
                        aria-label={`View full analysis for ${item.restaurant_name}`}
                      >
                        <strong>{item.restaurant_name}</strong>
                      </Link>
                      <span>
                        {Math.round(item.distance_meters)} m · {item.cuisine}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <EmptyState
                  title="No nearby options"
                  message="No Grade A restaurant was found within the selected distance."
                />
              )}
            </section>

            <footer className="restaurant-profile-actions">
              <button
                className="button primary"
                type="button"
                onClick={openRiskAnalysis}
                disabled={riskProbability == null}
              >
                View full risk analysis →
              </button>
              <button
                className="button secondary"
                type="button"
                onClick={onClose}
              >
                Close
              </button>
              {riskProbability == null && (
                <small>
                  No approved risk score is available for this restaurant.
                </small>
              )}
            </footer>
          </div>
        )
      )}
    </Modal>
  );
}

function ChainDetails({
  selected,
  onClose,
}: {
  selected: Chain | null;
  onClose: () => void;
}) {
  const key = selected?.chain_key ?? "";
  const locations = useQuery({
    queryKey: ["chain-locations", key],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<Restaurant>>(
        `/chains/${key}/locations`,
        {},
        signal,
      ),
    enabled: !!key,
  });
  return (
    <Modal
      open={!!selected}
      title={selected?.chain_name ?? "Chain details"}
      onClose={onClose}
    >
      {selected && (
        <div className="chain-profile">
          <div className="chain-profile-tags">
            <span className="chain-identity">
              <ChainLinkIcon /> Chain
            </span>
            <span>
              {selected.is_confirmed_fast_food
                ? "Fast food"
                : selected.cuisines?.[0] || "Restaurant group"}
            </span>
            <span>{formatNumber(selected.location_count)} NYC locations</span>
          </div>
          <div className="chain-independent-note">
            <strong>Each location is inspected and graded independently</strong>
            <p>
              The grade shown below belongs only to that restaurant location,
              not the entire chain.
            </p>
          </div>
          {locations.isLoading ? (
            <LoadingState label="Loading chain locations" />
          ) : locations.isError ? (
            <ErrorState retry={() => locations.refetch()} />
          ) : locations.data?.items.length ? (
            <ul className="chain-location-list">
              {locations.data.items.map((location) => {
                const days = daysSinceInspection(
                  location.latest_inspection_date,
                );
                const grade = location.current_grade || "U";
                return (
                  <li key={location.restaurant_key}>
                    <span
                      className={`chain-location-grade grade-${grade.toLowerCase()}`}
                      aria-label={`Current grade ${grade === "U" ? "not available" : grade}`}
                    >
                      {grade === "U" ? "—" : grade}
                    </span>
                    <div>
                      <strong>
                        {location.borough_name || "NYC"} —{" "}
                        {location.address || location.restaurant_name}
                      </strong>
                      <span>
                        Score {location.current_score ?? "—"} pts ·{" "}
                        {days == null
                          ? "Inspection date unavailable"
                          : `${formatNumber(days)}d since inspection`}
                      </span>
                    </div>
                    {location.has_repeated_critical_violation && (
                      <span className="chain-location-alert">
                        Repeat critical
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <EmptyState
              title="No locations found"
              message="No current locations were returned for this chain."
            />
          )}
        </div>
      )}
    </Modal>
  );
}

function daysSinceInspection(value: string | null) {
  if (!value) return null;
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return null;
  return Math.max(0, Math.floor((Date.now() - date.getTime()) / 86_400_000));
}
