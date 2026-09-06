with restaurant_groups as (
    select
        cuisine,
        borough_key,
        count(*) as total_restaurants
    from {{ ref('dim_restaurant') }}
    where cuisine is not null and borough_key is not null
    group by cuisine, borough_key
),

graded_counts as (
    select
        restaurants.cuisine,
        restaurants.borough_key,
        count(*) as graded_restaurants,
        sum(case when latest.grade = 'A' then 1 else 0 end) as grade_a_restaurants
    from {{ ref('int_latest_graded_inspection') }} as latest
    join {{ ref('dim_restaurant') }} as restaurants
        on latest.restaurant_key = restaurants.restaurant_key
    where restaurants.cuisine is not null and restaurants.borough_key is not null
    group by restaurants.cuisine, restaurants.borough_key
)

select
    to_hex(sha256(to_utf8(concat(groups.cuisine, '||', cast(groups.borough_key as varchar))))) as cuisine_borough_key,
    groups.cuisine,
    groups.borough_key,
    boroughs.borough_name,
    groups.total_restaurants,
    coalesce(graded.graded_restaurants, 0) as graded_restaurants,
    coalesce(graded.grade_a_restaurants, 0) as grade_a_restaurants,
    100.0 * coalesce(graded.grade_a_restaurants, 0)
        / nullif(graded.graded_restaurants, 0) as grade_a_percent_of_graded,
    100.0 * coalesce(graded.grade_a_restaurants, 0)
        / nullif(groups.total_restaurants, 0) as grade_a_per_100_restaurants
from restaurant_groups as groups
join {{ ref('dim_borough') }} as boroughs
    on groups.borough_key = boroughs.borough_key
left join graded_counts as graded
    on groups.cuisine = graded.cuisine
    and groups.borough_key = graded.borough_key
