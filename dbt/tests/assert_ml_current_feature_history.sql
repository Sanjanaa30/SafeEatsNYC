select restaurant_key
from {{ ref('ml_current_features') }}
where prediction_anchor_date > scoring_date
   or known_graded_inspection_count < 1
   or historical_violation_count < previous_inspection_violation_count
   or historical_critical_violation_count < previous_inspection_critical_violation_count
   or historical_grade_a_count
      + historical_grade_b_count
      + historical_grade_c_count <> known_graded_inspection_count
   or prior_90d_rodent_complaint_count
      + prior_90d_food_poisoning_complaint_count
      + prior_90d_food_establishment_complaint_count
      <> prior_90d_nearby_complaint_count
