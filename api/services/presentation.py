"""Shared SQL fragments for dashboard-facing restaurant summaries."""

REPEATED_CRITICAL_CTES = """
critical_code_repeats as (
    select
        facts.restaurant_key,
        facts.violation_key,
        count(distinct facts.inspection_id) as repeat_inspection_count
    from fact_inspection facts
    join dim_date dates on facts.date_key = dates.date_key
    where facts.is_critical
      and facts.violation_key is not null
      and dates.calendar_date >= date_add('year', -3, current_date)
    group by facts.restaurant_key, facts.violation_key
    having count(distinct facts.inspection_id) >= 2
),
repeated_critical_summary as (
    select
        repeats.restaurant_key,
        true as has_repeated_critical_violation,
        array_sort(array_agg(violations.violation_code)) as repeated_critical_codes,
        count(*) as repeated_critical_code_count,
        max(repeats.repeat_inspection_count) as maximum_repeat_inspection_count
    from critical_code_repeats repeats
    join dim_violation violations
      on repeats.violation_key = violations.violation_key
    group by repeats.restaurant_key
)
"""


REPEATED_CRITICAL_COLUMNS = """
    coalesce(repeats.has_repeated_critical_violation, false)
        as has_repeated_critical_violation,
    coalesce(
        repeats.repeated_critical_codes,
        cast(array[] as array(varchar))
    ) as repeated_critical_codes,
    coalesce(repeats.repeated_critical_code_count, 0)
        as repeated_critical_code_count,
    coalesce(repeats.maximum_repeat_inspection_count, 0)
        as maximum_repeat_inspection_count
"""
