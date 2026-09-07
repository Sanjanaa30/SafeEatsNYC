select prediction_anchor_key
from {{ ref('ml_training_features') }}
where known_graded_inspection_count < 1
   or days_since_last_graded_inspection <= 0
   or historical_violation_count < previous_inspection_violation_count
   or historical_critical_violation_count < previous_inspection_critical_violation_count
   or historical_grade_a_count
      + historical_grade_b_count
      + historical_grade_c_count <> known_graded_inspection_count
   or abs(
        historical_grade_a_rate
        - (1.0 * historical_grade_a_count / known_graded_inspection_count)
   ) > 0.000001
   or prior_90d_nearby_complaint_count < 0
   or prior_90d_rodent_complaint_count
      + prior_90d_food_poisoning_complaint_count
      + prior_90d_food_establishment_complaint_count
      <> prior_90d_nearby_complaint_count
