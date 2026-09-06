select borough_key
from {{ ref('mart_borough_grade_summary') }}
group by borough_key
having abs(sum(grade_percent_of_graded) - 100.0) > 0.000001

union all

select borough_key
from {{ ref('mart_cuisine_borough_heatmap') }}
where grade_a_percent_of_graded < 0 or grade_a_percent_of_graded > 100
