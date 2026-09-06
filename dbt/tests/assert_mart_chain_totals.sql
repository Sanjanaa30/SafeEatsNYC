select chain_key
from {{ ref('mart_chain_summary') }}
where location_count < 3
   or grade_a_location_count
      + grade_b_location_count
      + grade_c_location_count
      + ungraded_location_count <> location_count
   or grade_a_percent_of_graded_locations < 0
   or grade_a_percent_of_graded_locations > 100
