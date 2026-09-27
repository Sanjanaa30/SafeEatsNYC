import type {
  ApiCollection,
  ApiRecord,
  BoroughCorrelation,
  CorrelationSummary,
  History,
  NearbyRestaurant,
  Restaurant,
  RiskRecord,
  Violation,
  WeeklyPoint,
} from "@/types/dashboard";

type Params = Record<
  string,
  string | number | boolean | null | undefined
>;

type SnapshotMetadata = {
  metadata: unknown;
  freshness: unknown;
};

type OverviewSnapshot = {
  kpis: unknown[];
  boroughs: Array<Record<string, unknown>>;
  grade_distribution: unknown[];
  cuisine_heatmap: unknown[];
  violations: Record<string, Array<Record<string, unknown>>>;
  violation_criticality_by_borough: unknown[];
};

type CorrelationSnapshot = {
  weekly: Record<string, WeeklyPoint[]>;
  restaurant_level: unknown;
};

const cache = new Map<string, Promise<unknown>>();
const stopWords = new Set(["AT", "IN", "NY", "NYC", "ON"]);

// Load and reuse one published JSON file for the current browser session.
function loadJson<T>(file: string): Promise<T> {
  if (!cache.has(file)) {
    cache.set(
      file,
      fetch(`/data/snapshot/${file}`).then((response) => {
        if (!response.ok) throw new Error("Published safety data is unavailable.");
        return response.json() as Promise<T>;
      }),
    );
  }
  return cache.get(file) as Promise<T>;
}

function collection<T>(items: T[], total = items.length, page?: number, pageSize?: number) {
  return { items, total, page, page_size: pageSize } satisfies ApiCollection<T>;
}

function value(params: Params, key: string) {
  const item = params[key];
  return item == null ? "" : String(item);
}

function paginate<T>(items: T[], params: Params, defaultSize: number) {
  const page = Math.max(1, Number(params.page) || 1);
  const pageSize = Math.max(1, Number(params.page_size) || defaultSize);
  const start = (page - 1) * pageSize;
  return collection(items.slice(start, start + pageSize), items.length, page, pageSize);
}

function searchTerms(query: string) {
  return (query.toUpperCase().match(/[A-Z0-9]+/g) ?? []).filter(
    (term) => term.length > 1 && !stopWords.has(term),
  );
}

function restaurantText(row: Restaurant & { restaurant_name_normalized?: string }) {
  return [
    row.restaurant_name,
    row.restaurant_name_normalized,
    row.restaurant_id,
    row.address,
    row.zipcode,
    row.borough_name,
    row.cuisine,
  ]
    .filter(Boolean)
    .join(" ")
    .toUpperCase();
}

function sortRestaurants(rows: Restaurant[], sort: string, direction: string) {
  const result = [...rows];
  const gradeOrder: Record<string, number> = { A: 1, B: 2, C: 3 };
  result.sort((left, right) => {
    let comparison = 0;
    if (sort === "grade")
      comparison =
        (gradeOrder[left.current_grade ?? ""] ?? 9) -
        (gradeOrder[right.current_grade ?? ""] ?? 9);
    else if (sort === "score")
      comparison = (left.current_score ?? Number.MAX_VALUE) - (right.current_score ?? Number.MAX_VALUE);
    else if (sort === "inspection_date")
      comparison = String(left.latest_inspection_date ?? "").localeCompare(
        String(right.latest_inspection_date ?? ""),
      );
    else if (sort === "days_since_inspection")
      comparison = (left.days_since_inspection ?? Number.MAX_VALUE) - (right.days_since_inspection ?? Number.MAX_VALUE);
    else comparison = left.restaurant_name.localeCompare(right.restaurant_name);
    if (comparison === 0) comparison = left.restaurant_key.localeCompare(right.restaurant_key);
    return direction === "desc" ? -comparison : comparison;
  });
  return result;
}

async function restaurantsEndpoint(params: Params) {
  const rows = await loadJson<Restaurant[]>("restaurants.json");
  const terms = searchTerms(value(params, "query"));
  const borough = value(params, "borough");
  const cuisine = value(params, "cuisine");
  const grade = value(params, "grade");
  const flag = value(params, "flag");
  const improved = new Set(
    (await loadJson<Restaurant[]>("recently-improved.json")).map(
      (row) => row.restaurant_key,
    ),
  );
  const filtered = rows.filter((row) => {
    const text = restaurantText(row);
    if (terms.some((term) => !text.includes(term))) return false;
    if (borough && row.borough_name !== borough) return false;
    if (cuisine && row.cuisine !== cuisine) return false;
    if (grade && row.current_grade !== grade) return false;
    if (flag === "chain" && !row.is_chain) return false;
    if (flag === "independent" && row.is_chain) return false;
    if (flag === "fast_food" && !row.is_confirmed_fast_food) return false;
    if (flag === "recently_improved" && !improved.has(row.restaurant_key)) return false;
    if (
      flag === "repeat_critical" &&
      (row.is_chain || !row.has_repeated_critical_violation)
    )
      return false;
    return true;
  });
  return paginate(
    sortRestaurants(filtered, value(params, "sort") || "name", value(params, "direction") || "asc"),
    params,
    20,
  );
}

function chunkName(key: string) {
  return key.toLowerCase().slice(0, 1) || "other";
}

async function restaurantHistory(key: string) {
  const rows = await loadJson<Array<History & { restaurant_key: string }>>(
    `history/${chunkName(key)}.json`,
  );
  return rows.filter((row) => row.restaurant_key === key);
}

async function restaurantViolations(key: string) {
  const rows = await loadJson<Array<Violation & { restaurant_key: string }>>(
    `violations/${chunkName(key)}.json`,
  );
  return rows.filter((row) => row.restaurant_key === key);
}

function distanceMeters(left: Restaurant, right: Restaurant) {
  const lat1 = Number(left.latitude);
  const lon1 = Number(left.longitude);
  const lat2 = Number(right.latitude);
  const lon2 = Number(right.longitude);
  const radians = (degrees: number) => (degrees * Math.PI) / 180;
  const latDelta = radians(lat2 - lat1);
  const lonDelta = radians(lon2 - lon1);
  const a =
    Math.sin(latDelta / 2) ** 2 +
    Math.cos(radians(lat1)) *
      Math.cos(radians(lat2)) *
      Math.sin(lonDelta / 2) ** 2;
  return 6_371_000 * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

async function nearbyRestaurants(key: string, params: Params) {
  const rows = await loadJson<Restaurant[]>("restaurants.json");
  const selected = rows.find((row) => row.restaurant_key === key);
  if (!selected || selected.latitude == null || selected.longitude == null)
    return collection<NearbyRestaurant>([]);
  const radius = Number(params.radius_meters) || 1000;
  const limit = Number(params.limit) || 10;
  const sameCuisine = String(params.same_cuisine).toLowerCase() === "true";
  const independentOnly = String(params.independent_only).toLowerCase() === "true";
  const nearby = rows
    .filter(
      (row) =>
        row.restaurant_key !== key &&
        row.current_grade === "A" &&
        row.latitude != null &&
        row.longitude != null &&
        (!sameCuisine || row.cuisine === selected.cuisine) &&
        (!independentOnly || !row.is_chain),
    )
    .map((row) => ({ ...row, distance_meters: distanceMeters(selected, row) }))
    .filter((row) => row.distance_meters <= radius)
    .sort((left, right) => left.distance_meters - right.distance_meters)
    .slice(0, limit);
  return collection(nearby);
}

async function restaurantDetail(key: string): Promise<ApiRecord<Restaurant>> {
  const [restaurants, risks] = await Promise.all([
    loadJson<Restaurant[]>("restaurants.json"),
    loadJson<RiskRecord[]>("risk.json"),
  ]);
  const restaurant = restaurants.find((row) => row.restaurant_key === key);
  if (!restaurant) throw new Error("Restaurant not found.");
  const risk = risks.find((row) => row.restaurant_key === key);
  return { data: risk ? { ...restaurant, risk } : restaurant };
}

async function chainsEndpoint(params: Params) {
  const chains = await loadJson<Array<Record<string, unknown>>>("chains.json");
  const query = value(params, "query").toUpperCase();
  const borough = value(params, "borough");
  const confirmedOnly = String(params.confirmed_fast_food_only).toLowerCase() === "true";
  const sort = value(params, "sort") || "name";
  const direction = value(params, "direction") || "asc";
  const filtered = chains.filter((chain) => {
    if (query && !String(chain.chain_name ?? "").toUpperCase().includes(query)) return false;
    if (borough && !(chain.boroughs_present as string[] | undefined)?.includes(borough)) return false;
    if (confirmedOnly && !chain.is_confirmed_fast_food) return false;
    return true;
  });
  const field: Record<string, string> = {
    name: "chain_name",
    location_count: "location_count",
    worst_grade: "worst_current_grade",
    average_score: "average_latest_score",
    average_risk: "average_risk_probability",
  };
  filtered.sort((left, right) => {
    const a = left[field[sort]] ?? "";
    const b = right[field[sort]] ?? "";
    const comparison =
      typeof a === "number" && typeof b === "number"
        ? a - b
        : String(a).localeCompare(String(b));
    return direction === "desc" ? -comparison : comparison;
  });
  return paginate(filtered, params, 20);
}

async function riskEndpoint(params: Params) {
  const rows = await loadJson<RiskRecord[]>("risk.json");
  const query = value(params, "query").toUpperCase();
  const borough = value(params, "borough");
  const cuisine = value(params, "cuisine");
  const category = value(params, "category");
  const sort = value(params, "sort") || "risk";
  const direction = value(params, "direction") || "desc";
  const filtered = rows.filter((row) => {
    if (
      query &&
      !String(row.restaurant_name ?? "").toUpperCase().includes(query) &&
      !String(row.restaurant_id ?? "").includes(query)
    )
      return false;
    if (borough && row.borough_name !== borough) return false;
    if (cuisine && row.cuisine !== cuisine) return false;
    if (category && row.risk_category !== category) return false;
    return true;
  });
  filtered.sort((left, right) => {
    let comparison = 0;
    if (sort === "name")
      comparison = String(left.restaurant_name ?? "").localeCompare(
        String(right.restaurant_name ?? ""),
      );
    else if (sort === "inspection_date")
      comparison = String(left.latest_inspection_date ?? "").localeCompare(
        String(right.latest_inspection_date ?? ""),
      );
    else comparison = left.risk_probability - right.risk_probability;
    return direction === "desc" ? -comparison : comparison;
  });
  return paginate(filtered, params, 20);
}

function normalizedComplaintType(params: Params) {
  const requested = value(params, "complaint_type") || "ALL";
  return requested.toUpperCase().replaceAll(" ", "_");
}

function selectedWeeklyRows(snapshot: CorrelationSnapshot, params: Params, extraWeeks = 0) {
  const complaintType = normalizedComplaintType(params);
  const borough = value(params, "borough") || "CITYWIDE";
  const weeks = (Number(params.weeks) || 12) + extraWeeks;
  const rows = (snapshot.weekly[complaintType] ?? snapshot.weekly.ALL).filter(
    (row) => row.borough_name === borough,
  );
  return rows.slice(-weeks);
}

function pearson(left: number[], right: number[]) {
  if (left.length < 3 || left.length !== right.length) return null;
  const leftMean = left.reduce((sum, item) => sum + item, 0) / left.length;
  const rightMean = right.reduce((sum, item) => sum + item, 0) / right.length;
  const leftDelta = left.map((item) => item - leftMean);
  const rightDelta = right.map((item) => item - rightMean);
  const denominator = Math.sqrt(
    leftDelta.reduce((sum, item) => sum + item * item, 0) *
      rightDelta.reduce((sum, item) => sum + item * item, 0),
  );
  if (!denominator) return null;
  return leftDelta.reduce(
    (sum, item, index) => sum + item * rightDelta[index],
    0,
  ) / denominator;
}

function confidenceInterval(coefficient: number | null, observations: number) {
  if (coefficient == null || observations <= 3 || Math.abs(coefficient) >= 1)
    return null;
  const transformed = Math.atanh(coefficient);
  const margin = 1.96 / Math.sqrt(observations - 3);
  return [
    Number(Math.tanh(transformed - margin).toFixed(6)),
    Number(Math.tanh(transformed + margin).toFixed(6)),
  ] as [number, number];
}

function describeCorrelation(params: Params, coefficient: number | null, observations: number): CorrelationSummary {
  const borough = value(params, "borough") || "CITYWIDE";
  const weeks = Number(params.weeks) || 12;
  const lagWeeks = Number(params.lag_weeks) || 0;
  const absolute = coefficient == null ? null : Math.abs(coefficient);
  const strength =
    absolute == null
      ? "not calculable"
      : absolute < 0.3
        ? "weak"
        : absolute < 0.6
          ? "moderate"
          : "strong";
  return {
    borough,
    weeks,
    lag_weeks: lagWeeks,
    observations,
    coefficient: coefficient == null ? null : Number(coefficient.toFixed(6)),
    confidence_interval: confidenceInterval(coefficient, observations),
    complaint_type: normalizedComplaintType(params).replaceAll("_", " "),
    direction:
      coefficient == null
        ? "not_calculable"
        : coefficient > 0
          ? "positive"
          : coefficient < 0
            ? "negative"
            : "none",
    strength,
    is_calculable: coefficient != null,
  };
}

function laggedValues(rows: WeeklyPoint[], lag: number) {
  const complaints = rows.map((row) => Number(row.complaints_per_1000_restaurants || 0));
  const findings = rows.map((row) => Number(row.inspections_with_critical_per_100 || 0));
  return {
    complaints: lag ? complaints.slice(0, -lag) : complaints,
    findings: lag ? findings.slice(lag) : findings,
  };
}

async function correlationSummary(params: Params) {
  const snapshot = await loadJson<CorrelationSnapshot>("correlation.json");
  const lag = Number(params.lag_weeks) || 0;
  const rows = selectedWeeklyRows(snapshot, params, lag);
  const values = laggedValues(rows, lag);
  return describeCorrelation(
    params,
    pearson(values.complaints, values.findings),
    values.complaints.length,
  );
}

async function boroughRanking(params: Params) {
  const snapshot = await loadJson<CorrelationSnapshot>("correlation.json");
  const complaintType = normalizedComplaintType(params);
  const lag = Number(params.lag_weeks) || 0;
  const weeks = Number(params.weeks) || 12;
  const rows = snapshot.weekly[complaintType] ?? snapshot.weekly.ALL;
  const boroughs = [...new Set(rows.map((row) => row.borough_name))].filter(
    (borough) => borough !== "CITYWIDE",
  );
  const result: BoroughCorrelation[] = boroughs.map((borough) => {
    const selected = rows.filter((row) => row.borough_name === borough).slice(-(weeks + lag));
    const values = laggedValues(selected, lag);
    const complaintRows = lag ? selected.slice(0, -lag) : selected;
    const inspectionRows = lag ? selected.slice(lag) : selected;
    const complaintCount = complaintRows.reduce((sum, row) => sum + Number(row.complaint_count), 0);
    const inspectionCount = inspectionRows.reduce((sum, row) => sum + Number(row.inspection_count), 0);
    const criticalCount = inspectionRows.reduce((sum, row) => sum + Number(row.critical_violation_count), 0);
    const inspectionsWithCritical = inspectionRows.reduce(
      (sum, row) => sum + Number(row.inspections_with_critical_violation),
      0,
    );
    const totalRestaurants = Number(selected.at(-1)?.total_restaurants || 0);
    const coefficient = pearson(values.complaints, values.findings);
    return {
      borough_name: borough,
      complaint_count: complaintCount,
      complaints_per_1000_restaurants: totalRestaurants
        ? (1000 * complaintCount) / totalRestaurants
        : 0,
      inspection_count: inspectionCount,
      critical_violation_count: criticalCount,
      critical_findings_per_100_inspections: inspectionCount
        ? (100 * criticalCount) / inspectionCount
        : 0,
      inspections_with_critical_per_100: inspectionCount
        ? (100 * inspectionsWithCritical) / inspectionCount
        : 0,
      correlation: coefficient,
      observations: values.complaints.length,
      confidence_interval: confidenceInterval(coefficient, values.complaints.length),
    };
  });
  result.sort(
    (left, right) =>
      right.complaints_per_1000_restaurants -
      left.complaints_per_1000_restaurants,
  );
  return collection(result);
}

async function overviewEndpoint(path: string, params: Params) {
  const snapshot = await loadJson<OverviewSnapshot>("overview.json");
  if (path === "/overview/kpis") return collection(snapshot.kpis);
  if (path === "/overview/grade-distribution")
    return collection(snapshot.grade_distribution);
  if (path === "/overview/cuisine-heatmap")
    return collection(snapshot.cuisine_heatmap);
  if (path === "/overview/violation-criticality-by-borough")
    return collection(snapshot.violation_criticality_by_borough);
  if (path === "/overview/violations") {
    const criticality = value(params, "criticality") || "all";
    const limit = Number(params.limit) || 15;
    return collection((snapshot.violations[criticality] ?? snapshot.violations.all).slice(0, limit));
  }
  if (path === "/overview/boroughs") {
    const rows = [...snapshot.boroughs];
    const sort = value(params, "sort") || "safety_rank";
    const rules: Record<string, [string, number]> = {
      safety_rank: ["safety_rank", 1],
      name: ["borough_name", 1],
      grade_a_percent: ["grade_a_percent", -1],
      complaint_rate: ["complaint_rate_per_1000", 1],
      critical_violation_rate: ["critical_violation_rate_per_100", 1],
      improvement_rate: ["improvement_rate", -1],
      total_restaurants: ["total_restaurants", -1],
    };
    const [field, direction] = rules[sort] ?? rules.safety_rank;
    rows.sort((left, right) => {
      const a = left[field] ?? Number.MAX_VALUE;
      const b = right[field] ?? Number.MAX_VALUE;
      const comparison =
        typeof a === "number" && typeof b === "number"
          ? a - b
          : String(a).localeCompare(String(b));
      return comparison * direction;
    });
    return collection(rows);
  }
  throw new Error(`Snapshot endpoint is not available: ${path}`);
}

// Reproduce the FastAPI reads from immutable deployment files.
export async function fetchSnapshot<T>(path: string, params: Params = {}): Promise<T> {
  if (path === "/health")
    return { status: "ok", service: "published data snapshot", environment: "static" } as T;
  if (path === "/metadata" || path === "/data-freshness") {
    const snapshot = await loadJson<SnapshotMetadata>("metadata.json");
    return (path === "/metadata" ? snapshot.metadata : snapshot.freshness) as T;
  }
  if (path.startsWith("/overview/"))
    return (await overviewEndpoint(path, params)) as T;
  if (path === "/restaurants/recently-improved") {
    const rows = await loadJson<Restaurant[]>("recently-improved.json");
    return collection(rows.slice(0, Number(params.limit) || 10)) as T;
  }
  if (path === "/restaurants") return (await restaurantsEndpoint(params)) as T;

  const restaurantMatch = path.match(/^\/restaurants\/([^/]+)(?:\/(history|violations|nearby))?$/);
  if (restaurantMatch) {
    const [, key, section] = restaurantMatch;
    if (section === "history") return collection(await restaurantHistory(key)) as T;
    if (section === "violations") return collection(await restaurantViolations(key)) as T;
    if (section === "nearby") return (await nearbyRestaurants(key, params)) as T;
    return (await restaurantDetail(key)) as T;
  }

  if (path === "/chains") return (await chainsEndpoint(params)) as T;
  const chainMatch = path.match(/^\/chains\/([^/]+)(?:\/(locations))?$/);
  if (chainMatch) {
    const [, key, section] = chainMatch;
    const chains = await loadJson<Array<Record<string, unknown>>>("chains.json");
    if (!section) return { data: chains.find((row) => row.chain_key === key) } as T;
    const restaurants = await loadJson<Restaurant[]>("restaurants.json");
    const borough = value(params, "borough");
    return collection(
      restaurants.filter(
        (row) => row.chain_key === key && (!borough || row.borough_name === borough),
      ),
    ) as T;
  }

  if (path === "/risk/restaurants") return (await riskEndpoint(params)) as T;
  const riskMatch = path.match(/^\/risk\/restaurants\/([^/]+)$/);
  if (riskMatch) {
    const rows = await loadJson<RiskRecord[]>("risk.json");
    const row = rows.find((item) => item.restaurant_key === riskMatch[1]);
    if (!row) throw new Error("No risk score is available for this restaurant.");
    return { data: row } as T;
  }

  if (path === "/correlation/weekly") {
    const snapshot = await loadJson<CorrelationSnapshot>("correlation.json");
    return collection(selectedWeeklyRows(snapshot, params)) as T;
  }
  if (path === "/correlation/summary")
    return (await correlationSummary(params)) as T;
  if (path === "/correlation/borough-ranking")
    return (await boroughRanking(params)) as T;
  if (path === "/correlation/restaurant-level") {
    const snapshot = await loadJson<CorrelationSnapshot>("correlation.json");
    return { data: snapshot.restaurant_level } as T;
  }

  throw new Error(`Snapshot endpoint is not available: ${path}`);
}
