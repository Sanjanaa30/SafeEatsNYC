export type CorrelationStrength = "Weak" | "Moderate" | "Strong";

export function correlationStrength(
  value: number | null | undefined,
): CorrelationStrength | "Not available" {
  if (value == null) return "Not available";
  const magnitude = Math.abs(value);
  if (magnitude < 0.3) return "Weak";
  if (magnitude < 0.6) return "Moderate";
  return "Strong";
}

export function correlationDirection(value: number | null | undefined) {
  if (value == null || value === 0) return "No direction";
  return value > 0 ? "Moved together" : "Moved in opposite directions";
}

export function correlationLabel(value: number | null | undefined) {
  const strength = correlationStrength(value);
  if (strength === "Not available") return "Not enough data";
  return value! < 0
    ? `${strength} opposite connection`
    : `${strength} connection`;
}

export function evidenceLabel(weeks: number) {
  if (weeks <= 12) return "Short-term result";
  if (weeks < 52) return "Moderate evidence";
  return "More stable evidence";
}

export function confidenceIncludesZero(
  interval: [number, number] | null | undefined,
) {
  return interval != null && interval[0] <= 0 && interval[1] >= 0;
}
