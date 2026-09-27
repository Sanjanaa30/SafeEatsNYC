import { formatNumber } from "@/lib/format";
import type { BoroughViolationCriticality } from "@/types/dashboard";

const boroughLabel = (value: string) =>
  value.toLowerCase().replace(/\b\w/g, (letter) => letter.toUpperCase());

export function ViolationCriticalityChart({
  rows,
  loading,
}: {
  rows: BoroughViolationCriticality[];
  loading: boolean;
}) {
  const maximum = Math.max(
    1,
    ...rows.flatMap((row) => [
      Number(row.critical_findings_per_inspection) || 0,
      Number(row.non_critical_findings_per_inspection) || 0,
    ]),
  );
  const scaleMaximum = Math.ceil((maximum * 100) / 50) * 50;

  return (
    <section
      className="surface-card violation-criticality-chart"
      aria-labelledby="criticality-chart-title"
    >
      <header>
        <div>
          <p className="eyebrow">Borough comparison</p>
          <h3 id="criticality-chart-title">Findings per 100 inspections</h3>
          <p>
            Compare serious (critical) and other findings across each
            borough&apos;s inspection history.
          </p>
        </div>
        <div className="criticality-legend" aria-label="Chart legend">
          <span>
            <i className="critical" />
            Critical
          </span>
          <span>
            <i className="non-critical" />
            Non-critical
          </span>
        </div>
      </header>
      {rows.length > 0 ? (
        <div
          className="criticality-vertical-chart"
          role="group"
          aria-label="Grouped bar chart of critical and non-critical findings per 100 inspections by borough"
        >
          <div className="criticality-y-axis" aria-hidden="true">
            {[1, 0.75, 0.5, 0.25, 0].map((fraction) => (
              <span key={fraction}>
                {formatNumber(scaleMaximum * fraction, 0)}
              </span>
            ))}
          </div>
          <div className="criticality-plot">
            {rows.map((row) => (
              <div className="criticality-column" key={row.borough_name}>
                <div className="criticality-column-bars">
                  {(
                    [
                      [
                        "Critical",
                        row.critical_findings_per_inspection,
                        "critical",
                        row.critical_findings,
                      ],
                      [
                        "Non-critical",
                        row.non_critical_findings_per_inspection,
                        "non-critical",
                        row.non_critical_findings,
                      ],
                    ] as const
                  ).map(([label, value, kind, findings]) => (
                    <div
                      className={`criticality-vertical-bar ${kind}`}
                      key={kind}
                      tabIndex={0}
                      role="img"
                      aria-label={`${boroughLabel(row.borough_name)}: ${label}, ${value == null ? "unavailable" : formatNumber(Number(value) * 100, 0)} findings for every 100 inspections. ${formatNumber(findings)} findings across ${formatNumber(row.inspection_count)} inspections in total.`}
                      title={`${boroughLabel(row.borough_name)}: about ${value == null ? "unavailable" : formatNumber(Number(value) * 100, 0)} ${label.toLowerCase()} findings for every 100 inspections. One inspection can have more than one finding.`}
                      style={{
                        height: `${Math.max(0, Math.min(100, (((Number(value) || 0) * 100) / scaleMaximum) * 100))}%`,
                      }}
                    >
                      <b aria-hidden="true">
                        {value == null
                          ? "—"
                          : formatNumber(Number(value) * 100, 0)}
                      </b>
                    </div>
                  ))}
                </div>
                <strong>{boroughLabel(row.borough_name)}</strong>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <p className="criticality-chart-note">
          {loading
            ? "Loading borough comparisons…"
            : "Borough comparisons are unavailable."}
        </p>
      )}
      {rows.length > 0 && (
        <p className="criticality-chart-note">
          Example: 172 means about 172 findings were recorded for every 100
          inspections. One inspection can have multiple findings, so the number
          can be over 100. This chart is independent of the list filter above.
        </p>
      )}
    </section>
  );
}
