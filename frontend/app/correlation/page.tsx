"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BoroughMap } from "@/components/charts/borough-map";
import { CorrelationTrendChart } from "@/components/charts/correlation-trend-chart";
import { ModernSelect } from "@/components/ui/controls";
import {
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui/data-states";
import { PageHeading } from "@/components/ui/page-heading";
import { ResponsiveTable } from "@/components/ui/responsive-table";
import { fetchApi } from "@/lib/api";
import {
  confidenceIncludesZero,
  correlationDirection,
  correlationLabel,
  evidenceLabel,
} from "@/lib/correlation";
import { formatDate } from "@/lib/format";
import type {
  ApiCollection,
  ApiRecord,
  BoroughCorrelation,
  CorrelationSummary,
  Metadata,
  RestaurantCorrelation,
  WeeklyPoint,
} from "@/types/dashboard";

const boroughLabel = (value: string) =>
  value === "CITYWIDE"
    ? "New York City"
    : value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

const delayLabel = (lag: string) => {
  if (lag === "0") return "in the same week";
  return `${lag} ${lag === "1" ? "week" : "weeks"} later`;
};

const complaintLabel = (value: string) =>
  ({
    ALL: "All food-related complaints",
    FOOD_ESTABLISHMENT: "Food establishment",
    FOOD_POISONING: "Food poisoning",
    RODENT: "Rodent",
  })[value] ?? value;

export default function CorrelationPage() {
  const [borough, setBorough] = useState("");
  const [weeks, setWeeks] = useState("26");
  const [lag, setLag] = useState("2");
  const [complaintType, setComplaintType] = useState("ALL");
  const requestFilters = {
    weeks,
    complaint_type: complaintType,
    lag_weeks: lag,
  };

  const meta = useQuery({
    queryKey: ["metadata"],
    queryFn: ({ signal }) => fetchApi<Metadata>("/metadata", {}, signal),
  });
  const weekly = useQuery({
    queryKey: ["weekly", borough, weeks, complaintType],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<WeeklyPoint>>(
        "/correlation/weekly",
        { borough: borough || undefined, weeks, complaint_type: complaintType },
        signal,
      ),
  });
  const summary = useQuery({
    queryKey: ["correlation-summary", borough, weeks, lag, complaintType],
    queryFn: ({ signal }) =>
      fetchApi<CorrelationSummary>(
        "/correlation/summary",
        { borough: borough || undefined, ...requestFilters },
        signal,
      ),
  });
  const ranking = useQuery({
    queryKey: ["correlation-ranking", weeks, lag, complaintType],
    queryFn: ({ signal }) =>
      fetchApi<ApiCollection<BoroughCorrelation>>(
        "/correlation/borough-ranking",
        requestFilters,
        signal,
      ),
  });
  const restaurant = useQuery({
    queryKey: ["correlation-restaurant-level", 28],
    queryFn: ({ signal }) =>
      fetchApi<ApiRecord<RestaurantCorrelation>>(
        "/correlation/restaurant-level",
        { lookback_days: 28 },
        signal,
      ),
  });

  const strongestBorough = useMemo(
    () =>
      ranking.data?.items
        .filter((row) => row.correlation != null)
        .sort(
          (left, right) =>
            Math.abs(Number(right.correlation)) -
            Math.abs(Number(left.correlation)),
        )[0],
    [ranking.data],
  );
  const coefficient = summary.data?.coefficient;
  const selectedArea = borough ? boroughLabel(borough) : "New York City";
  const delay = delayLabel(lag);
  const absoluteCoefficient =
    coefficient == null ? null : Math.abs(coefficient);
  const relationshipLabel = correlationLabel(coefficient);
  const relationshipText =
    coefficient == null
      ? "There is not enough weekly variation to calculate a relationship for this selection."
      : absoluteCoefficient! < 0.2
        ? `For ${selectedArea}, complaint changes and critical-inspection changes ${delay} show almost no relationship.`
        : coefficient > 0
          ? `For ${selectedArea}, weeks with more complaints generally matched higher critical-inspection rates ${delay}.`
          : `For ${selectedArea}, weeks with more complaints generally matched lower critical-inspection rates ${delay}.`;
  const interval = summary.data?.confidence_interval;
  const restaurantData = restaurant.data?.data;
  const restaurantDifference =
    restaurantData?.critical_rate_difference_points == null
      ? null
      : Number(restaurantData.critical_rate_difference_points);
  const restaurantTakeaway =
    restaurantDifference == null
      ? "There is not enough matched data to compare the two groups."
      : Math.abs(restaurantDifference) < 1
        ? "The two percentages are almost the same. A matched complaint was not a strong warning of a later critical finding in this data."
        : restaurantDifference > 0
          ? `Inspections after a matched complaint had a ${restaurantDifference.toFixed(1)}-point higher critical-finding rate.`
          : `Inspections after a matched complaint had a ${Math.abs(restaurantDifference).toFixed(1)}-point lower critical-finding rate.`;

  return (
    <main id="main-content" className="shell page-shell correlation-page">
      <PageHeading
        eyebrow="Operational · Deep dive"
        title="Violations & 311 Correlation"
        description={`See if changes in food-related 311 complaints match changes in serious restaurant-safety findings ${delay}.`}
      />

      <section
        className="surface-card correlation-page-guide"
        aria-labelledby="correlation-guide-title"
      >
        <div>
          <p className="eyebrow">Start here</p>
          <h2 id="correlation-guide-title">
            What question does this page answer?
          </h2>
          <p>
            When food-related 311 complaints rise, do restaurant inspections
            find more critical food-safety problems afterward?
          </p>
        </div>
        <ol>
          <li>
            <strong>Choose a place and complaint type.</strong>
            <span>For example, rodent complaints in Brooklyn.</span>
          </li>
          <li>
            <strong>Choose a period and delay.</strong>
            <span>
              For example, compare complaints with inspections two weeks later.
            </span>
          </li>
          <li>
            <strong>Read the connection.</strong>
            <span>
              A stronger score means the two weekly patterns matched more
              closely—not that complaints caused violations.
            </span>
          </li>
        </ol>
      </section>

      <div className="correlation-filter-bar">
        <ModernSelect
          label="Borough"
          value={borough}
          onChange={setBorough}
          options={[
            { value: "", label: "All boroughs" },
            ...(meta.data?.boroughs.map((item) => ({
              value: item,
              label: boroughLabel(item),
            })) ?? []),
          ]}
        />
        <ModernSelect
          label="Complaint category"
          value={complaintType}
          onChange={setComplaintType}
          options={[
            { value: "ALL", label: "All food-related" },
            { value: "FOOD_ESTABLISHMENT", label: "Food establishment" },
            { value: "FOOD_POISONING", label: "Food poisoning" },
            { value: "RODENT", label: "Rodent" },
          ]}
        />
        <ModernSelect
          label="Time period"
          value={weeks}
          onChange={setWeeks}
          options={[
            { value: "8", label: "8 weeks" },
            { value: "12", label: "12 weeks" },
            { value: "26", label: "26 weeks" },
            { value: "52", label: "1 year" },
            { value: "104", label: "2 years" },
          ]}
        />
        <ModernSelect
          label="Compare with findings"
          value={lag}
          onChange={setLag}
          options={[
            { value: "0", label: "Same week" },
            { value: "1", label: "1 week later" },
            { value: "2", label: "2 weeks later" },
            { value: "4", label: "4 weeks later" },
            { value: "8", label: "8 weeks later" },
          ]}
        />
      </div>
      <p className="correlation-filter-explanation">
        Showing <strong>{complaintLabel(complaintType).toLowerCase()}</strong>{" "}
        in <strong>{selectedArea}</strong>, compared with inspections{" "}
        <strong>{delay}</strong>.
      </p>
      <p className="correlation-filter-help">
        <strong>Borough</strong> chooses the place ·{" "}
        <strong>Complaint category</strong> chooses the kind of 311 report ·{" "}
        <strong>Time period</strong> chooses how much history to use ·{" "}
        <strong>Compare with findings</strong> chooses how long after a
        complaint week to check inspections.
      </p>

      <section
        className="correlation-hero-grid section-block"
        aria-label="Weekly trend and correlation snapshot"
      >
        <article className="surface-card correlation-trend-card">
          <header>
            <div>
              <h2>What happened week by week?</h2>
              <p>
                Blue shows complaint rates; red shows inspections that found a
                critical violation. Compare the shape of the lines, not their
                height.
              </p>
              {weekly.data?.items.length ? (
                <small>
                  Latest {weeks} available weeks:{" "}
                  {formatDate(weekly.data.items[0].week_start_date)}–
                  {formatDate(weekly.data.items.at(-1)?.week_start_date)}
                </small>
              ) : null}
            </div>
            <span>Live warehouse data</span>
          </header>
          {weekly.isLoading ? (
            <LoadingState label="Loading weekly trends" />
          ) : weekly.isError ? (
            <ErrorState retry={() => weekly.refetch()} />
          ) : weekly.data?.items.length ? (
            <CorrelationTrendChart
              rows={weekly.data.items}
              area={selectedArea}
              lagWeeks={Number(lag)}
            />
          ) : (
            <EmptyState message="No weekly observations are available." />
          )}
        </article>
        <article className="surface-card correlation-snapshot-card">
          <header>
            <h2>How closely did the patterns match?</h2>
            <p>Complaint weeks compared with critical inspections {delay}</p>
          </header>
          <div
            className="correlation-score"
            tabIndex={0}
            data-tooltip="The score runs from −1 to +1. Connection strength is weak from 0 to 0.29, moderate from 0.30 to 0.59, and strong from 0.60 to 1. Negative scores mean the patterns moved in opposite directions."
          >
            <strong>
              {coefficient == null ? "—" : coefficient.toFixed(2)}
            </strong>
            <span>Correlation score</span>
            <b>{relationshipLabel}</b>
            <small>
              {correlationDirection(coefficient)} ·{" "}
              {evidenceLabel(summary.data?.observations ?? Number(weeks))}
            </small>
          </div>
          <div
            className="correlation-scale"
            aria-label="How to read the correlation score"
          >
            <span>
              <b>−1</b> Opposite
            </span>
            <span>
              <b>0</b> Little connection
            </span>
            <span>
              <b>+1</b> Move together
            </span>
          </div>
          <div className="correlation-summary-copy">
            <p>{relationshipText}</p>
            {!borough && strongestBorough && (
              <p>
                <strong>{boroughLabel(strongestBorough.borough_name)}</strong>{" "}
                showed the closest match among boroughs. Score:{" "}
                <strong>
                  {Number(strongestBorough.correlation).toFixed(2)}
                </strong>
                .
              </p>
            )}
            {summary.data && (
              <p className="correlation-evidence">
                This result compares{" "}
                <strong>{summary.data.observations} complaint weeks</strong>{" "}
                with their matching later inspection weeks. Evidence level:{" "}
                <strong>{evidenceLabel(summary.data.observations)}</strong>.
              </p>
            )}
          </div>
          {interval && (
            <details className="correlation-confidence-details">
              <summary>How certain is this score?</summary>
              <p>
                The likely range is{" "}
                <strong>
                  {interval[0].toFixed(2)} to {interval[1].toFixed(2)}
                </strong>
                .{" "}
                {confidenceIncludesZero(interval)
                  ? "Because the range crosses zero, the connection may not be consistent."
                  : "The range stays on one side of zero, but its width shows that the exact strength can vary."}
              </p>
            </details>
          )}
          <small>
            This shows whether two patterns move together. It does not show that
            complaints caused later findings.
          </small>
        </article>
      </section>

      <section className="section-block restaurant-check-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Restaurant-level check</p>
            <h2>What happened after a complaint linked to a restaurant?</h2>
            <p>
              A matched complaint is a 311 report connected to a specific
              restaurant location. This compares inspections with and without
              one during the previous 28 days.
            </p>
          </div>
        </div>
        {restaurant.isLoading ? (
          <LoadingState label="Loading restaurant comparison" />
        ) : restaurant.isError ? (
          <ErrorState retry={() => restaurant.refetch()} />
        ) : restaurantData ? (
          <div className="restaurant-check-card surface-card">
            <div>
              <span>Inspections analyzed</span>
              <strong>
                {Number(restaurantData.inspections_analyzed).toLocaleString()}
              </strong>
            </div>
            <div>
              <span>After a matched complaint</span>
              <strong>
                {restaurantData.critical_rate_with_prior_complaint == null
                  ? "—"
                  : `${Number(restaurantData.critical_rate_with_prior_complaint).toFixed(1)}%`}
              </strong>
              <small>had a critical finding</small>
            </div>
            <div>
              <span>Without a matched complaint</span>
              <strong>
                {restaurantData.critical_rate_without_prior_complaint == null
                  ? "—"
                  : `${Number(restaurantData.critical_rate_without_prior_complaint).toFixed(1)}%`}
              </strong>
              <small>had a critical finding</small>
            </div>
            <div>
              <span>Difference</span>
              <strong>
                {restaurantData.critical_rate_difference_points == null
                  ? "—"
                  : `${Number(restaurantData.critical_rate_difference_points) >= 0 ? "+" : ""}${Number(restaurantData.critical_rate_difference_points).toFixed(1)} pts`}
              </strong>
              <small>association, not proof of cause</small>
            </div>
          </div>
        ) : (
          <EmptyState message="No matched restaurant comparison is available." />
        )}
        {restaurantData && (
          <p className="restaurant-check-takeaway">
            <strong>Simple takeaway:</strong> {restaurantTakeaway}
          </p>
        )}
      </section>

      <section className="section-block relationship-map-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Geographic comparison</p>
            <h2>Do more complaints appear before more inspection problems?</h2>
            <p>
              The map shows how closely weekly complaints matched critical
              inspections {delay}. Green means a closer match; grey means little
              or no match.
            </p>
          </div>
        </div>
        {ranking.isLoading ? (
          <LoadingState label="Loading borough relationships" />
        ) : ranking.isError ? (
          <ErrorState retry={() => ranking.refetch()} />
        ) : (
          ranking.data && (
            <BoroughMap rows={ranking.data.items} lagWeeks={Number(lag)} />
          )
        )}
        <p className="section-reading-note">
          <strong>How to read it:</strong> Find a borough, read its connection
          label, then hover or focus it for the complaint rate,
          critical-inspection rate and evidence period. The map shows pattern
          strength—not which borough is safest.
        </p>
      </section>

      <section className="section-block borough-detail-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">Borough detail</p>
            <h2>Borough details</h2>
            <p>
              Compare the average weekly complaint rate, critical-inspection
              rate and connection for each borough.
            </p>
          </div>
          <span className="borough-period-chip">Based on {weeks} weeks</span>
        </div>
        <div
          className="borough-metric-guide"
          aria-label="How to understand the borough metrics"
        >
          <article>
            <strong>Weekly complaints</strong>
            <p>
              Average complaints each week for every 1,000 restaurants.{" "}
              <b>Lower is generally better.</b>
            </p>
          </article>
          <article>
            <strong>Critical inspections</strong>
            <p>
              Percentage of inspections that found at least one critical
              violation. <b>Lower is better.</b>
            </p>
          </article>
          <article>
            <strong>Connection</strong>
            <p>
              Simple scale: 0–.29 weak, .30–.59 moderate and .60–1 strong. A
              negative score means the patterns moved in opposite directions.
            </p>
          </article>
        </div>
        {ranking.isLoading ? (
          <LoadingState label="Loading borough comparison" />
        ) : ranking.isError ? (
          <ErrorState retry={() => ranking.refetch()} />
        ) : (
          ranking.data && (
            <ResponsiveTable
              caption={`Borough comparison based on ${weeks} weeks`}
              rows={ranking.data.items}
              rowKey={(row) => row.borough_name}
              columns={[
                {
                  key: "borough",
                  label: "Borough",
                  render: (row) => (
                    <strong>{boroughLabel(row.borough_name)}</strong>
                  ),
                },
                {
                  key: "complaints",
                  label: "Weekly complaints",
                  render: (row) =>
                    `${(Number(row.complaints_per_1000_restaurants) / Math.max(row.observations, 1)).toFixed(0)} per 1,000 restaurants`,
                },
                {
                  key: "inspections",
                  label: "Critical inspections",
                  render: (row) =>
                    `${Number(row.inspections_with_critical_per_100).toFixed(0)}% of inspections`,
                },
                {
                  key: "connection",
                  label: "Connection",
                  render: (row) => (
                    <span className="connection-cell">
                      <span className="connection-label">
                        {correlationLabel(row.correlation)}
                      </span>
                      <small>
                        {correlationDirection(row.correlation)} ·{" "}
                        {evidenceLabel(row.observations)}
                        {confidenceIncludesZero(row.confidence_interval)
                          ? " · uncertain"
                          : ""}
                      </small>
                    </span>
                  ),
                },
              ]}
            />
          )
        )}
        <p className="section-reading-note">
          <strong>Read each row from left to right:</strong> how often residents
          complained, how often inspections found a critical problem, and
          whether those two weekly patterns matched. Lower complaint and
          critical-inspection rates are generally better.
        </p>
      </section>
    </main>
  );
}
