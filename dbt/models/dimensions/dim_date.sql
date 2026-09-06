with event_dates as (
    select cast(inspection_date as date) as event_date
    from {{ ref('stg_inspections') }}
    where inspection_date is not null

    union all

    select cast(created_date as date) as event_date
    from {{ ref('stg_complaints') }}
    where created_date is not null
),

date_bounds as (
    select min(event_date) as first_date, max(event_date) as last_date
    from event_dates
),

calendar as (
    select calendar_date
    from date_bounds
    cross join unnest(sequence(first_date, last_date, interval '1' day)) as dates(calendar_date)
)

select
    cast(date_format(calendar_date, '%Y%m%d') as integer) as date_key,
    cast(calendar_date as date) as calendar_date,
    year(calendar_date) as year_number,
    quarter(calendar_date) as quarter_number,
    month(calendar_date) as month_number,
    date_format(calendar_date, '%M') as month_name,
    week(calendar_date) as week_number,
    day(calendar_date) as day_of_month,
    day_of_week(calendar_date) as day_of_week_number,
    date_format(calendar_date, '%W') as day_name,
    day_of_week(calendar_date) in (6, 7) as is_weekend
from calendar
