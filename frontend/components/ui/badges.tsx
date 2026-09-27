export function GradeBadge({ grade }: { grade: string | null | undefined }) {
  const value = grade && ["A", "B", "C"].includes(grade) ? grade : "—";
  return (
    <span className={`badge grade grade-${value.toLowerCase()}`}>
      Grade {value}
    </span>
  );
}

export function RiskBadge({
  category,
  probability,
}: {
  category?: string | null;
  probability?: number | null;
}) {
  const value = category?.toUpperCase() ?? "NOT SCORED";
  const label =
    value === "HIGH"
      ? "Needs attention"
      : value === "MODERATE"
        ? "Watch"
        : value === "LOW"
          ? "Lower risk"
          : "Not scored";
  return (
    <span
      className={`badge risk risk-${value.toLowerCase().replace(" ", "-")}`}
    >
      {label}
      {probability !== null && probability !== undefined
        ? ` · ${(probability * 100).toFixed(1)}%`
        : ""}
    </span>
  );
}

export function DataFreshnessBadge({
  value,
}: {
  value: string | null | undefined;
}) {
  return (
    <span className="freshness-badge">
      <span aria-hidden="true" /> Data through{" "}
      {value
        ? new Date(value).toLocaleDateString("en-US", {
            month: "short",
            day: "numeric",
            year: "numeric",
            timeZone: "UTC",
          })
        : "latest snapshot"}
    </span>
  );
}
