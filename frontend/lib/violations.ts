export function simpleViolationName(description: string | null | undefined) {
  if (!description) return "Violation details unavailable";
  const normalized = description.toLowerCase();
  const labels: Array<[string, string]> = [
    ["non-food contact surface", "Equipment or surfaces difficult to clean"],
    ["harborage", "Conditions that may attract pests"],
    ["anti-siphonage", "Drainage or backflow problem"],
    ["back-flow", "Drainage or backflow problem"],
    [
      "not protected from potential source of contamination",
      "Food or equipment exposed to contamination",
    ],
    ["cold tcs", "Cold food stored too warm"],
    ["hot tcs", "Hot food stored too cool"],
    ["food contact surface", "Food-contact surfaces not cleaned properly"],
    ["hand washing", "Handwashing facilities or practices"],
    ["handwash", "Handwashing facilities or practices"],
    ["wiping cloth", "Wiping cloths not stored properly"],
    ["rodent", "Rodent activity or prevention"],
    ["vermin", "Pest activity or prevention"],
  ];
  for (const [phrase, label] of labels) {
    if (normalized.includes(phrase)) return label;
  }
  const firstClause = description.split(";")[0].split(".")[0].trim();
  return firstClause.length <= 72
    ? firstClause
    : `${firstClause.slice(0, 69).replace(/\s+\S*$/, "")}…`;
}
