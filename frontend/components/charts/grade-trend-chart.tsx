import { formatNumber, formatPercent } from "@/lib/format";
import type { GradeTrendPoint } from "@/types/dashboard";

const width = 820;
const height = 330;
const margin = { top: 24, right: 28, bottom: 48, left: 58 };
const plotWidth = width - margin.left - margin.right;
const plotHeight = height - margin.top - margin.bottom;
const grades = ["A", "B", "C"] as const;

function yearPoint(
  rows: GradeTrendPoint[],
  year: number,
  grade: (typeof grades)[number],
) {
  return rows.find((row) => row.year === year && row.grade === grade);
}

export function GradeTrendChart({ rows }: { rows: GradeTrendPoint[] }) {
  const years = [...new Set(rows.map((row) => Number(row.year)))].sort();
  const x = (index: number) =>
    margin.left + (index * plotWidth) / Math.max(years.length - 1, 1);
  const y = (percent: number) =>
    margin.top + plotHeight - (percent / 100) * plotHeight;

  return (
    <div className="grade-trend-chart-wrap">
      <svg
        className="grade-trend-chart"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-labelledby="grade-trend-title grade-trend-description"
      >
        <title id="grade-trend-title">Grade percentages by year</title>
        <desc id="grade-trend-description">
          Lines compare the percentage of restaurants receiving grades A, B,
          and C. Each restaurant is counted once per year using its latest
          graded inspection in that year.
        </desc>

        {[0, 25, 50, 75, 100].map((percent) => {
          const gridY = y(percent);
          return (
            <g key={percent}>
              <line
                className="grade-trend-gridline"
                x1={margin.left}
                y1={gridY}
                x2={width - margin.right}
                y2={gridY}
              />
              <text
                className="grade-trend-axis-label"
                x={margin.left - 10}
                y={gridY + 4}
                textAnchor="end"
              >
                {percent}%
              </text>
            </g>
          );
        })}
        <text
          className="grade-trend-axis-title"
          x="15"
          y={height / 2}
          textAnchor="middle"
          transform={`rotate(-90 15 ${height / 2})`}
        >
          Share of graded restaurants
        </text>

        {years.map((year, index) => (
          <text
            className="grade-trend-year-label"
            key={year}
            x={x(index)}
            y={height - 18}
            textAnchor="middle"
          >
            {year}
          </text>
        ))}

        {grades.map((grade) => {
          const points = years.map((year, index) => {
            const point = yearPoint(rows, year, grade);
            return {
              point,
              x: x(index),
              y: y(Number(point?.grade_percent ?? 0)),
            };
          });
          return (
            <g className={`grade-trend-series grade-${grade.toLowerCase()}`} key={grade}>
              <polyline
                className="grade-trend-line"
                points={points.map((point) => `${point.x},${point.y}`).join(" ")}
              />
              {points.map(({ point, x: pointX, y: pointY }, index) => {
                if (!point) return null;
                const tooltip = `${point.year} Grade ${grade}: ${formatPercent(point.grade_percent, 1)} (${formatNumber(point.restaurant_count)} of ${formatNumber(point.graded_restaurants)} restaurants). Each restaurant is counted once using its latest graded inspection that year.`;
                return (
                  <circle
                    className="grade-trend-point"
                    key={`${point.year}-${grade}`}
                    cx={pointX}
                    cy={pointY}
                    r="7"
                    tabIndex={0}
                    role="img"
                    aria-label={tooltip}
                    data-tooltip={tooltip}
                    data-tooltip-placement={index === 0 ? "bottom" : undefined}
                  >
                    <title>{tooltip}</title>
                  </circle>
                );
              })}
            </g>
          );
        })}
      </svg>

      <div className="grade-trend-legend" aria-label="Grade legend">
        {grades.map((grade) => (
          <span key={grade}>
            <i className={`grade-${grade.toLowerCase()}`} /> Grade {grade}
          </span>
        ))}
      </div>
    </div>
  );
}
