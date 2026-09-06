with weeks as (
    select distinct cast(date_trunc('week', calendar_date) as date) as week_start_date
    from {{ ref('dim_date') }}
),

areas as (
    select borough_key, borough_name, total_restaurants
    from {{ ref('dim_borough') }}

    union all

    select 0, 'CITYWIDE', sum(total_restaurants)
    from {{ ref('dim_borough') }}
),

complaints_by_area as (
    select
        cast(date_trunc('week', dates.calendar_date) as date) as week_start_date,
        complaints.borough_key,
        count(*) as complaint_count
    from {{ ref('fact_311_complaint') }} as complaints
    join {{ ref('dim_date') }} as dates on complaints.date_key = dates.date_key
    where complaints.borough_key is not null
    group by 1, 2

    union all

    select
        cast(date_trunc('week', dates.calendar_date) as date) as week_start_date,
        0 as borough_key,
        count(*) as complaint_count
    from {{ ref('fact_311_complaint') }} as complaints
    join {{ ref('dim_date') }} as dates on complaints.date_key = dates.date_key
    group by 1
),

inspections_by_area as (
    select
        cast(date_trunc('week', dates.calendar_date) as date) as week_start_date,
        inspections.borough_key,
        sum(inspections.critical_violation_count) as critical_violation_count,
        sum(case when inspections.has_critical_violation then 1 else 0 end) as inspections_with_critical_violation
    from {{ ref('int_inspection_events') }} as inspections
    join {{ ref('dim_date') }} as dates on inspections.date_key = dates.date_key
    where inspections.borough_key is not null
    group by 1, 2

    union all

    select
        cast(date_trunc('week', dates.calendar_date) as date) as week_start_date,
        0 as borough_key,
        sum(inspections.critical_violation_count) as critical_violation_count,
        sum(case when inspections.has_critical_violation then 1 else 0 end) as inspections_with_critical_violation
    from {{ ref('int_inspection_events') }} as inspections
    join {{ ref('dim_date') }} as dates on inspections.date_key = dates.date_key
    group by 1
),

weekly_counts as (
    select
        to_hex(sha256(to_utf8(concat(cast(areas.borough_key as varchar), '||', cast(weeks.week_start_date as varchar))))) as weekly_area_key,
        case when areas.borough_key = 0 then 'CITYWIDE' else 'BOROUGH' end as area_level,
        areas.borough_key,
        areas.borough_name,
        weeks.week_start_date,
        areas.total_restaurants,
        coalesce(complaints.complaint_count, 0) as complaint_count,
        coalesce(inspections.critical_violation_count, 0) as critical_violation_count,
        coalesce(inspections.inspections_with_critical_violation, 0) as inspections_with_critical_violation
    from weeks
    cross join areas
    left join complaints_by_area as complaints
        on weeks.week_start_date = complaints.week_start_date
        and areas.borough_key = complaints.borough_key
    left join inspections_by_area as inspections
        on weeks.week_start_date = inspections.week_start_date
        and areas.borough_key = inspections.borough_key
)

select
    *,
    100.0 * complaint_count / nullif(total_restaurants, 0) as complaints_per_100_restaurants,
    100.0 * critical_violation_count / nullif(total_restaurants, 0) as critical_violations_per_100_restaurants,
    corr(
        cast(complaint_count as double),
        cast(critical_violation_count as double)
    ) over (partition by borough_key) as complaint_critical_violation_correlation
from weekly_counts
