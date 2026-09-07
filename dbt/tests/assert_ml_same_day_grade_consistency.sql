select restaurant_key, date_key
from {{ ref('int_inspection_events') }}
where grade in ('A', 'B', 'C')
group by restaurant_key, date_key
having count(distinct grade) > 1
