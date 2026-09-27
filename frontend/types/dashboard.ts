export interface ApiCollection<T> {
  items: T[];
  total: number;
  page?: number;
  page_size?: number;
}
export interface ApiRecord<T> {
  data: T;
}
export interface Freshness {
  earliest_inspection_date?: string | null;
  latest_inspection_date: string | null;
  latest_complaint_date: string | null;
  latest_ml_scoring_timestamp: string | null;
  risk_score_run_id: string;
  refresh_description: string;
}
export interface Metadata {
  status: "ok";
  boroughs: string[];
  cuisines: string[];
  model_version: string | null;
  data_freshness: Freshness;
}
export interface Kpi {
  metric: string;
  value: number | null;
  comparison: number | null;
  unit: string;
  period: string;
  definition: string;
  explanation: string;
  trend: string;
  trend_tone: "positive" | "negative" | "neutral";
}
export interface BoroughSummary {
  borough_key: number;
  borough_name: string;
  total_restaurants: number;
  graded_restaurants: number;
  grade_a_count: number;
  grade_a_percent: number;
  safety_rank: number;
  top_issue: string | null;
  top_issue_summary: string;
  complaint_rate_per_1000: number | null;
  critical_violation_rate_per_100: number | null;
  improvement_rate: number | null;
}
export interface GradeSummary {
  grade: "A" | "B" | "C";
  restaurant_count: number;
  graded_restaurants: number;
  total_restaurants: number;
  grade_percent_of_graded: number;
}
export interface CuisineSummary {
  cuisine: string;
  total_restaurants: number;
  graded_restaurants: number;
  grade_a_restaurants: number;
  average_grade_a_percent: number;
}
export interface BoroughGradeDistribution {
  borough_key: number;
  borough_name: string;
  total_restaurants: number;
  graded_restaurants: number;
  grade_a_percent: number;
  grade_b_percent: number;
  grade_c_percent: number;
}
export interface CuisineHeatmapCell {
  borough_key: number;
  borough_name: string;
  cuisine: string;
  total_restaurants: number;
  graded_restaurants: number;
  average_grade_a_percent: number;
  grade_b_percent: number | null;
  grade_c_percent: number | null;
  borough_grade_a_percent: number;
  cuisine_citywide_grade_a_percent: number;
}
export interface ViolationSummary {
  violation_key: string;
  violation_code: string;
  violation_description: string;
  short_label: string;
  is_critical: boolean;
  criticality: string;
  violation_count: number;
  affected_restaurant_count: number;
  violations_per_100_restaurants: number;
}
export interface BoroughViolationCriticality {
  borough_name: string;
  inspection_count: number;
  critical_findings: number;
  non_critical_findings: number;
  critical_findings_per_inspection: number | null;
  non_critical_findings_per_inspection: number | null;
}
export interface WeeklyPoint {
  week_start_date: string;
  borough_name: string;
  total_restaurants: number;
  complaint_count: number;
  inspection_count: number;
  critical_violation_count: number;
  inspections_with_critical_violation: number;
  complaints_per_1000_restaurants: number;
  critical_findings_per_100_inspections: number;
  inspections_with_critical_per_100: number;
}
export interface CorrelationSummary {
  borough: string;
  weeks: number;
  lag_weeks: number;
  observations: number;
  coefficient: number | null;
  confidence_interval: [number, number] | null;
  complaint_type: string;
  direction: string;
  strength: "weak" | "moderate" | "strong" | "not calculable";
  is_calculable: boolean;
}
export interface BoroughCorrelation {
  borough_name: string;
  complaint_count: number;
  complaints_per_1000_restaurants: number;
  inspection_count: number;
  critical_violation_count: number;
  critical_findings_per_100_inspections: number;
  inspections_with_critical_per_100: number;
  correlation: number | null;
  observations: number;
  confidence_interval?: [number, number] | null;
  metric?: string;
  metric_value?: number;
}
export interface RestaurantCorrelation {
  inspections_analyzed: number;
  inspections_with_prior_complaint: number;
  critical_rate_with_prior_complaint: number | null;
  critical_rate_without_prior_complaint: number | null;
  complaint_critical_correlation: number | null;
  critical_rate_difference_points: number | null;
  lookback_days: number;
}
export interface Restaurant {
  restaurant_key: string;
  restaurant_id: string;
  restaurant_name: string;
  address: string | null;
  zipcode: string | null;
  nta_name: string | null;
  borough_name: string | null;
  cuisine: string | null;
  latitude?: number | null;
  longitude?: number | null;
  current_grade: "A" | "B" | "C" | null;
  current_score: number | null;
  latest_inspection_date: string | null;
  days_since_inspection?: number | null;
  three_year_grades?: Array<"A" | "B" | "C">;
  is_grade_consistent?: boolean | null;
  improved_to_a?: boolean | null;
  is_chain?: boolean;
  is_confirmed_fast_food?: boolean;
  chain_key?: string | null;
  has_repeated_critical_violation?: boolean;
  repeated_critical_codes?: string[];
  maximum_repeat_inspection_count?: number;
  risk_probability?: number | null;
  risk_category?: "LOW" | "MODERATE" | "HIGH" | null;
  risk?: RiskRecord;
}
export interface History {
  inspection_id: string;
  inspection_date: string;
  grade: string;
  previous_grade: string | null;
  score: number | null;
  violation_count: number;
  critical_violation_count: number;
  has_critical_violation: boolean;
  improved_to_a: boolean;
}
export interface Violation {
  inspection_id: string;
  inspection_date: string;
  violation_code: string;
  violation_description: string;
  is_critical: boolean;
}
export interface NearbyRestaurant extends Restaurant {
  distance_meters: number;
}
export interface Chain {
  chain_key: string;
  chain_name: string;
  location_count: number;
  borough_count: number;
  is_confirmed_fast_food: boolean;
  cuisines: string[];
  boroughs_present: string[];
  confirmed_fast_food_brands: string[];
  grade_a_location_count: number;
  grade_b_location_count: number;
  grade_c_location_count: number;
  ungraded_location_count: number;
  average_latest_score: number | null;
  best_current_grade: string | null;
  worst_current_grade: string | null;
  average_risk_probability: number | null;
  high_risk_location_count: number;
  has_repeated_critical_location: boolean;
  highest_risk_location: {
    restaurant_key: string;
    restaurant_name: string;
    risk_probability: number;
    risk_category: string;
  } | null;
}
export interface RiskFactor {
  feature: string;
  contribution: number;
  direction?: string;
}
export interface RiskRecord {
  restaurant_key: string;
  restaurant_id: string | null;
  restaurant_name: string | null;
  address: string | null;
  borough_name: string | null;
  cuisine: string | null;
  current_grade: string | null;
  latest_inspection_date: string | null;
  risk_probability: number;
  risk_category: "LOW" | "MODERATE" | "HIGH";
  main_contributing_factors: RiskFactor[];
  model_version: string;
  scoring_timestamp: string;
}
