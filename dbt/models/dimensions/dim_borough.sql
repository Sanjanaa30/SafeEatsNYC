with boroughs as (
    select *
    from (
        values
            (1, 'BRONX'),
            (2, 'BROOKLYN'),
            (3, 'MANHATTAN'),
            (4, 'QUEENS'),
            (5, 'STATEN ISLAND')
    ) as borough_values (borough_key, borough_name)
),

restaurant_counts as (
    select borough, count(*) as total_restaurants
    from {{ ref('stg_restaurant_current') }}
    group by borough
)

select
    boroughs.borough_key,
    boroughs.borough_name,
    coalesce(restaurant_counts.total_restaurants, 0) as total_restaurants
from boroughs
left join restaurant_counts
    on boroughs.borough_name = restaurant_counts.borough
