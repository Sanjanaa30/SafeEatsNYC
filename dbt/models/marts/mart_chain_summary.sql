select
    chains.chain_key,
    chains.chain_name,
    chains.location_count,
    chains.borough_count,
    chains.is_confirmed_fast_food,
    array_sort(array_distinct(array_agg(restaurants.cuisine))) as cuisines,
    array_sort(array_distinct(array_agg(boroughs.borough_name))) as boroughs_present,
    array_sort(
        array_distinct(
            flatten(
                array_agg(
                    coalesce(
                        restaurants.fast_food_brand_names,
                        cast(array[] as array(varchar))
                    )
                )
            )
        )
    ) as confirmed_fast_food_brands,
    count(latest.restaurant_key) as graded_location_count,
    sum(case when latest.grade = 'A' then 1 else 0 end) as grade_a_location_count,
    sum(case when latest.grade = 'B' then 1 else 0 end) as grade_b_location_count,
    sum(case when latest.grade = 'C' then 1 else 0 end) as grade_c_location_count,
    chains.location_count - count(latest.restaurant_key) as ungraded_location_count,
    100.0 * sum(case when latest.grade = 'A' then 1 else 0 end)
        / nullif(count(latest.restaurant_key), 0) as grade_a_percent_of_graded_locations,
    avg(latest.score) as average_latest_score,
    case min(case latest.grade when 'A' then 1 when 'B' then 2 when 'C' then 3 end)
        when 1 then 'A' when 2 then 'B' when 3 then 'C'
    end as best_current_grade,
    case max(case latest.grade when 'A' then 1 when 'B' then 2 when 'C' then 3 end)
        when 1 then 'A' when 2 then 'B' when 3 then 'C'
    end as worst_current_grade
from {{ ref('dim_chain') }} as chains
join {{ ref('dim_restaurant') }} as restaurants
    on chains.chain_key = restaurants.chain_key
left join {{ ref('dim_borough') }} as boroughs
    on restaurants.borough_key = boroughs.borough_key
left join {{ ref('int_latest_graded_inspection') }} as latest
    on restaurants.restaurant_key = latest.restaurant_key
group by
    chains.chain_key,
    chains.chain_name,
    chains.location_count,
    chains.borough_count,
    chains.is_confirmed_fast_food
