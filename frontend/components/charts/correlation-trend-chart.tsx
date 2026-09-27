"use client";

import { useState } from "react";
import { formatNumber } from "@/lib/format";
import type { WeeklyPoint } from "@/types/dashboard";

const width = 760;
const height = 310;
const margin = { top: 24, right: 58, bottom: 48, left: 58 };
const plotWidth = width - margin.left - margin.right;
const plotHeight = height - margin.top - margin.bottom;

const niceMaximum = (values: number[]) => {
  const maximum = Math.max(...values, 1);
  const magnitude = 10 ** Math.floor(Math.log10(maximum));
  return Math.ceil(maximum / magnitude) * magnitude;
};

const weekLabel = (value: string) =>
  new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${value}T00:00:00Z`));

export function CorrelationTrendChart({
  rows,
  area,
  lagWeeks,
}: {
  rows: WeeklyPoint[];
  area: string;
  lagWeeks: number;
}) {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const complaints = rows.map(
    (row) => Number(row.complaints_per_1000_restaurants) || 0,
  );
  const violations = rows.map(
    (row) => Number(row.inspections_with_critical_per_100) || 0,
  );
  const complaintMaximum = niceMaximum(complaints);
  const violationMaximum = niceMaximum(violations);
  const x = (index: number) =>
    margin.left + (index * plotWidth) / Math.max(rows.length - 1, 1);
  const y = (value: number, maximum: number) =>
    margin.top + plotHeight - (value / maximum) * plotHeight;
  const points = (values: number[], maximum: number) =>
    values.map((value, index) => `${x(index)},${y(value, maximum)}`).join(" ");
  const active = activeIndex == null ? null : rows[activeIndex];

  return (
    <div className="correlation-chart-wrap">
      <svg
        className="correlation-trend-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby="correlation-trend-title correlation-trend-desc"
      >
        <title id="correlation-trend-title">
          Weekly 311 complaints and critical violations
        </title>
        <desc id="correlation-trend-desc">
          Dual-axis trend chart for {area}. Blue shows 311 food complaints per
          1,000 restaurants and red shows inspections with critical findings per
          100 inspections. Use the points for exact weekly values.
        </desc>
        {[0, 0.25, 0.5, 0.75, 1].map((fraction) => {
          const gridY = margin.top + plotHeight * (1 - fraction);
          return (
            <g key={fraction}>
              <line
                x1={margin.left}
                y1={gridY}
                x2={width - margin.right}
                y2={gridY}
                className="correlation-gridline"
              />
              <text
                x={margin.left - 10}
                y={gridY + 4}
                textAnchor="end"
                className="correlation-axis-label"
              >
                {formatNumber(complaintMaximum * fraction, 0)}
              </text>
              <text
                x={width - margin.right + 10}
                y={gridY + 4}
                textAnchor="start"
                className="correlation-axis-label"
              >
                {formatNumber(violationMaximum * fraction, 0)}
              </text>
            </g>
          );
        })}
        <text
          x="16"
          y={height / 2}
          textAnchor="middle"
          className="correlation-axis-title"
          transform={`rotate(-90 16 ${height / 2})`}
        >
          Complaints / 1k restaurants
        </text>
        <text
          x={width - 12}
          y={height / 2}
          textAnchor="middle"
          className="correlation-axis-title"
          transform={`rotate(90 ${width - 12} ${height / 2})`}
        >
          Critical inspections / 100
        </text>
        <polygon
          points={`${margin.left},${margin.top + plotHeight} ${points(complaints, complaintMaximum)} ${width - margin.right},${margin.top + plotHeight}`}
          className="complaint-area"
        />
        <polyline
          points={points(complaints, complaintMaximum)}
          className="complaint-line"
        />
        <polyline
          points={points(violations, violationMaximum)}
          className="violation-line"
        />
        {rows.map((row, index) => (
          <g key={row.week_start_date}>
            <line
              x1={x(index)}
              y1={margin.top}
              x2={x(index)}
              y2={margin.top + plotHeight}
              className={
                activeIndex === index
                  ? "correlation-hover-line active"
                  : "correlation-hover-line"
              }
            />
            <circle
              aria-hidden="true"
              cx={x(index)}
              cy={y(complaints[index], complaintMaximum)}
              r="6"
              className="complaint-point"
            />
            <circle
              aria-hidden="true"
              cx={x(index)}
              cy={y(violations[index], violationMaximum)}
              r="6"
              className="violation-point"
            />
            {(index % Math.ceil(rows.length / 7) === 0 ||
              index === rows.length - 1) && (
              <text
                x={x(index)}
                y={height - 18}
                textAnchor="middle"
                className="correlation-week-label"
              >
                {weekLabel(row.week_start_date)}
              </text>
            )}
            <rect
              x={index === 0 ? margin.left : (x(index - 1) + x(index)) / 2}
              y={margin.top}
              width={
                (index === rows.length - 1
                  ? width - margin.right
                  : (x(index) + x(index + 1)) / 2) -
                (index === 0 ? margin.left : (x(index - 1) + x(index)) / 2)
              }
              height={plotHeight}
              className="correlation-interaction-zone"
              tabIndex={0}
              role="img"
              aria-label={`${weekLabel(row.week_start_date)}: ${formatNumber(row.complaints_per_1000_restaurants, 1)} complaints per 1,000 restaurants and ${formatNumber(row.inspections_with_critical_per_100, 1)} of every 100 inspections with a critical finding`}
              data-tooltip={`Week of ${weekLabel(row.week_start_date)}: ${formatNumber(row.complaints_per_1000_restaurants, 1)} complaints per 1,000 restaurants (${formatNumber(row.complaint_count)} total). ${formatNumber(row.inspections_with_critical_per_100, 1)} of every 100 inspections had a critical finding (${formatNumber(row.inspection_count)} inspections).`}
              onMouseEnter={() => setActiveIndex(index)}
              onFocus={() => setActiveIndex(index)}
            />
          </g>
        ))}
      </svg>
      <div className="correlation-chart-legend" aria-label="Chart legend">
        <span>
          <i className="complaints" />
          Complaints / 1,000 restaurants
        </span>
        <span>
          <i className="violations" />
          Critical inspections / 100
        </span>
      </div>
      <p className="correlation-lag-note">
        The correlation score compares each week&apos;s complaint rate with the
        critical-inspection rate{" "}
        {lagWeeks === 0
          ? "in the same week"
          : `${lagWeeks} week${lagWeeks === 1 ? "" : "s"} later`}
        .
      </p>
      <div className="correlation-chart-insight" aria-live="polite">
        {active ? (
          <>
            <strong>Week of {weekLabel(active.week_start_date)}</strong>
            <span>
              <b>{formatNumber(active.complaints_per_1000_restaurants, 1)}</b>{" "}
              complaints / 1k restaurants
            </span>
            <span>
              <b>{formatNumber(active.inspections_with_critical_per_100, 1)}</b>{" "}
              critical inspections / 100
            </span>
          </>
        ) : (
          <span>
            Hover over or focus a point to see that week&apos;s rates and
            totals.
          </span>
        )}
      </div>
    </div>
  );
}
