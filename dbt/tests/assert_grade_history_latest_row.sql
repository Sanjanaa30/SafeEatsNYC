select restaurant_key
from {{ ref('mart_restaurant_grade_history') }}
group by restaurant_key
having sum(case when is_latest_graded_inspection then 1 else 0 end) <> 1
