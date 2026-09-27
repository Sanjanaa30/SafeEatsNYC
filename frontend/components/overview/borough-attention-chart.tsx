"use client";

import { useState } from "react";
import { formatPercent } from "@/lib/format";
import type { BoroughGradeDistribution } from "@/types/dashboard";

const boroughLabel = (value: string) =>
  value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());
const attentionRate = (row: BoroughGradeDistribution) =>
  Number(row.grade_b_percent || 0) + Number(row.grade_c_percent || 0);

export function BoroughAttentionChart({
  rows,
  loading,
}: {
  rows: BoroughGradeDistribution[];
  loading: boolean;
}) {
  const [activeBorough, setActiveBorough] = useState<string | null>(null);
  const ranked = [...rows].sort((a, b) => attentionRate(b) - attentionRate(a));
  const maximum = Math.max(
    5,
    Math.ceil(Math.max(0, ...ranked.map(attentionRate)) / 5) * 5,
  );
  const active =
    ranked.find((row) => row.borough_name === activeBorough) ?? ranked[0];

  return (
    <article className="surface-card analytics-card distribution-card attention-card">
      <header>
        <div>
          <h2>B/C Grade Share by Borough</h2>
          <p>Latest graded restaurants that received B or C</p>
        </div>
      </header>
      {ranked.length ? (
        <>
          <div
            className="distribution-chart"
            role="group"
            aria-label="Grade B and C shares by borough; higher combined share means more restaurants need attention"
          >
            {ranked.map((row) => (
              <div
                className={`distribution-row ${active?.borough_name === row.borough_name ? "is-active" : ""}`}
                key={row.borough_name}
                tabIndex={0}
                onMouseEnter={() => setActiveBorough(row.borough_name)}
                onFocus={() => setActiveBorough(row.borough_name)}
                title={`${boroughLabel(row.borough_name)}: ${formatPercent(row.grade_b_percent)} Grade B, ${formatPercent(row.grade_c_percent)} Grade C; ${formatPercent(attentionRate(row))} combined`}
              >
                <span>{boroughLabel(row.borough_name)}</span>
                <div className="stacked-bar" aria-hidden="true">
                  <i
                    className="grade-b"
                    style={{
                      width: `${(100 * Number(row.grade_b_percent || 0)) / maximum}%`,
                    }}
                  />
                  <i
                    className="grade-c"
                    style={{
                      width: `${(100 * Number(row.grade_c_percent || 0)) / maximum}%`,
                    }}
                  />
                </div>
                <b className="attention-total">
                  {formatPercent(attentionRate(row), 1)}
                </b>
              </div>
            ))}
            <div className="distribution-axis" aria-hidden="true">
              {[0, 0.25, 0.5, 0.75, 1].map((fraction) => (
                <span key={fraction}>
                  {formatPercent(maximum * fraction, 0)}
                </span>
              ))}
            </div>
            <div className="grade-legend">
              <span>
                <i className="grade-b" />
                Grade B
              </span>
              <span>
                <i className="grade-c" />
                Grade C
              </span>
            </div>
          </div>
          {active && (
            <div className="chart-insight" aria-live="polite">
              <strong>{boroughLabel(active.borough_name)}</strong>
              <span>
                <b>{formatPercent(active.grade_b_percent)}</b> Grade B and{" "}
                <b>{formatPercent(active.grade_c_percent)}</b> Grade C.
              </span>
              <small>
                Combined B/C share: {formatPercent(attentionRate(active))} of
                restaurants with a latest A, B, or C grade.
              </small>
            </div>
          )}
        </>
      ) : (
        <p className="analytics-empty">
          {loading
            ? "Grade comparison is loading."
            : "Grade comparison is unavailable."}
        </p>
      )}
    </article>
  );
}
