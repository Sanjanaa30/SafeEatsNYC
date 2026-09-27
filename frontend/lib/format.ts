export const formatNumber = (value: number | null | undefined, digits = 0) =>
  value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat("en-US", {
        maximumFractionDigits: digits,
        minimumFractionDigits: digits,
      }).format(value);

export const formatPercent = (value: number | null | undefined, digits = 1) =>
  value === null || value === undefined
    ? "—"
    : `${formatNumber(value, digits)}%`;

export const formatDate = (value: string | null | undefined) => {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(value));
};

export const titleCase = (value: string) =>
  value
    .toLowerCase()
    .replace(
      /(^|\s|_)(\w)/g,
      (_, space, letter) =>
        `${space === "_" ? " " : space}${letter.toUpperCase()}`,
    );
