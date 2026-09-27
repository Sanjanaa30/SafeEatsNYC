"""Athena queries used by the city and borough overview page."""

from typing import Any

from api.services.athena import AthenaQueryService
from api.services.sql import normalized_borough, sql_string


class OverviewService:
    def __init__(self, athena: AthenaQueryService) -> None:
        self.athena = athena

    def kpis(self, borough: str | None = None) -> list[dict[str, Any]]:
        borough = normalized_borough(borough)
        borough_filter = (
            f"and b.borough_name = {sql_string(borough)}" if borough else ""
        )
        history_filter = (
            f"and h.borough_name = {sql_string(borough)}" if borough else ""
        )
        fact_filter = f"and b.borough_name = {sql_string(borough)}" if borough else ""
        sql = f"""
        with anchors as (
            select
                (select max(d.calendar_date)
                 from fact_inspection f join dim_date d on f.date_key = d.date_key)
                    as inspection_date,
                (select cast(max(created_date) as date) from fact_311_complaint)
                    as complaint_date
        ), restaurants as (
            select count(*) as value
            from dim_restaurant r
            left join dim_borough b on r.borough_key = b.borough_key
            where 1 = 1 {borough_filter}
        ), current_grades as (
            select
                100.0 * count_if(h.grade = 'A') / nullif(count(*), 0) as grade_a_rate,
                avg(cast(h.score as double)) as average_score
            from mart_restaurant_grade_history h
            where h.is_latest_graded_inspection and h.grade in ('A', 'B', 'C')
            {history_filter}
        ), previous_grade_rows as (
            select h.*, row_number() over (
                partition by h.restaurant_key order by h.inspection_date desc, h.inspection_id desc
            ) as recency
            from mart_restaurant_grade_history h
            cross join anchors a
            where h.inspection_date <= date_add('month', -1, a.inspection_date)
              and h.grade in ('A', 'B', 'C')
            {history_filter}
        ), previous_grades as (
            select
                100.0 * count_if(grade = 'A') / nullif(count(*), 0) as grade_a_rate,
                avg(cast(score as double)) as average_score
            from previous_grade_rows where recency = 1
        ), inspection_flags as (
            select f.inspection_id, d.calendar_date,
                   max(case when f.is_critical then 1 else 0 end) as has_critical
            from fact_inspection f
            join dim_date d on f.date_key = d.date_key
            left join dim_borough b on f.borough_key = b.borough_key
            where 1 = 1 {fact_filter}
            group by f.inspection_id, d.calendar_date
        ), critical_rates as (
            select
                100.0 * count_if(has_critical = 1 and calendar_date > date_add('year', -1, a.inspection_date))
                    / nullif(count_if(calendar_date > date_add('year', -1, a.inspection_date)), 0) as current_rate,
                100.0 * count_if(has_critical = 1 and calendar_date > date_add('year', -2, a.inspection_date) and calendar_date <= date_add('year', -1, a.inspection_date))
                    / nullif(count_if(calendar_date > date_add('year', -2, a.inspection_date) and calendar_date <= date_add('year', -1, a.inspection_date)), 0) as previous_rate
            from inspection_flags cross join anchors a
            group by a.inspection_date
        ), food_complaints as (
            select f.created_date, f.closed_date
            from fact_311_complaint f
            join dim_complaint_type t on f.complaint_type_key = t.complaint_type_key
            left join dim_borough b on f.borough_key = b.borough_key
            where t.complaint_type in ('FOOD ESTABLISHMENT', 'FOOD POISONING')
            {fact_filter}
        ), open_complaints as (
            select
                count_if(created_date < date_add('day', 1, cast(a.complaint_date as timestamp)) and (closed_date is null or closed_date >= date_add('day', 1, cast(a.complaint_date as timestamp)))) as current_count,
                count_if(created_date < date_add('day', -6, cast(a.complaint_date as timestamp)) and (closed_date is null or closed_date >= date_add('day', -6, cast(a.complaint_date as timestamp)))) as previous_count
            from food_complaints cross join anchors a
            group by a.complaint_date
        ), closures as (
            select
                count(distinct case when year(d.calendar_date) = year(a.inspection_date) then f.inspection_id end) as ytd_count,
                count(distinct case when year(d.calendar_date) = year(a.inspection_date) and month(d.calendar_date) = month(a.inspection_date) then f.inspection_id end) as month_count
            from fact_inspection f
            join dim_date d on f.date_key = d.date_key
            left join dim_borough b on f.borough_key = b.borough_key
            cross join anchors a
            where (lower(coalesce(f.inspection_action, '')) like 'establishment closed by dohmh%'
               or lower(coalesce(f.inspection_action, '')) like 'establishment re-closed by dohmh%')
            {fact_filter}
        )
        select 'active_restaurants' as metric, cast(r.value as double) as value, cast(null as double) as comparison from restaurants r
        union all select 'grade_a_compliance_rate', c.grade_a_rate, p.grade_a_rate from current_grades c cross join previous_grades p
        union all select 'average_inspection_score', c.average_score, p.average_score from current_grades c cross join previous_grades p
        union all select 'critical_violation_rate', current_rate, previous_rate from critical_rates
        union all select 'open_311_food_complaints', cast(current_count as double), cast(previous_count as double) from open_complaints
        union all select 'temporary_closures_ytd', cast(ytd_count as double), cast(month_count as double) from closures
        """
        rows = self.athena.query(sql)
        definitions = {
            "active_restaurants": {
                "unit": "restaurants",
                "period": "current warehouse snapshot",
                "definition": "Distinct current DOHMH restaurant locations in the selected area.",
            },
            "grade_a_compliance_rate": {
                "unit": "percent",
                "period": "latest grade; compared with one month earlier",
                "definition": "Share of currently graded restaurants whose latest grade is A.",
            },
            "average_inspection_score": {
                "unit": "points",
                "period": "latest grade; compared with one month earlier",
                "definition": "Average score from each restaurant's latest graded inspection; lower is generally better.",
            },
            "critical_violation_rate": {
                "unit": "per_100",
                "period": "trailing year compared with the preceding year",
                "definition": "Inspections with at least one critical finding per 100 inspections.",
            },
            "open_311_food_complaints": {
                "unit": "complaints",
                "period": "open at the latest complaint snapshot; compared with one week earlier",
                "definition": "Food Establishment and Food Poisoning complaints that had not yet closed.",
            },
            "temporary_closures_ytd": {
                "unit": "closures",
                "period": "calendar year through the latest inspection snapshot",
                "definition": "Distinct inspections whose DOHMH action closed or re-closed the establishment.",
            },
        }
        for row in rows:
            row.update(definitions[row["metric"]])
            row.update(
                self.kpi_trend(row["metric"], row.get("value"), row.get("comparison"))
            )
            row["explanation"] = self.kpi_explanation(
                row["metric"], row.get("value"), row.get("comparison")
            )
        return rows

    @staticmethod
    def kpi_explanation(
        metric: str, value: float | None, comparison: float | None
    ) -> str:
        """Give the dashboard a short live-data explanation for every KPI."""
        if value is None:
            return (
                "This measure is temporarily unavailable in the latest data snapshot."
            )
        if metric == "active_restaurants":
            return f"{value:,.0f} restaurant locations are currently in the data. Current snapshot means this is the latest total, not a change."
        if metric == "grade_a_compliance_rate":
            change = value - comparison if comparison is not None else None
            change_text = (
                f" That is {abs(change):.1f} percentage points {'higher' if change >= 0 else 'lower'} than one month earlier."
                if change is not None
                else " The month-to-month comparison is not available."
            )
            return f"{value:.1f}% of restaurants' latest grade is A.{change_text}"
        if metric == "average_inspection_score":
            change = value - comparison if comparison is not None else None
            change_text = (
                " It is unchanged from one month earlier."
                if change is not None and round(change, 1) == 0
                else f" It is {abs(change):.1f} points {'higher' if change is not None and change > 0 else 'lower'} than one month earlier."
                if change is not None
                else " The month-to-month comparison is not available."
            )
            return f"The average inspection score is {value:.1f}; lower is generally better.{change_text}"
        if metric == "critical_violation_rate":
            change = value - comparison if comparison is not None else None
            change_text = (
                f" That is {abs(change):.1f} {'more' if change >= 0 else 'fewer'} inspections per 100 than the previous year."
                if change is not None
                else " The year-over-year comparison is not available."
            )
            return f"In the past year, about {value:.0f} out of every 100 inspections found at least one serious food-safety violation.{change_text}"
        if metric == "open_311_food_complaints":
            change = value - comparison if comparison is not None else None
            percent = (
                100.0 * change / comparison
                if change is not None and comparison
                else None
            )
            change_text = (
                f" This is {abs(percent):.1f}% {'more' if percent >= 0 else 'fewer'} than one week earlier."
                if percent is not None
                else " The week-to-week comparison is not available."
            )
            return f"{value:,.0f} food-related 311 complaints were still open at the latest data snapshot.{change_text}"
        if metric == "temporary_closures_ytd":
            month_count = int(comparison or 0)
            return f"{value:,.0f} temporary closures were recorded by DOHMH so far this year. {month_count} were recorded this month."
        return "This measure is calculated from the latest SafeEats data snapshot."

    @staticmethod
    def kpi_trend(
        metric: str, value: float | None, comparison: float | None
    ) -> dict[str, str]:
        """Create honest display text from real prior-period KPI values."""

        if metric == "active_restaurants":
            return {"trend": "Current snapshot", "trend_tone": "neutral"}
        if metric == "temporary_closures_ytd":
            month_count = int(comparison or 0)
            return {
                "trend": f"{'+' if month_count else ''}{month_count} this month",
                "trend_tone": "negative" if month_count else "positive",
            }
        if value is None or comparison is None:
            return {"trend": "Comparison unavailable", "trend_tone": "neutral"}

        delta = value - comparison
        displayed_delta = round(delta, 1)
        if displayed_delta == 0:
            displayed_delta = 0.0
        sign = "+" if displayed_delta > 0 else ""
        if displayed_delta == 0:
            tone = "neutral"
        else:
            tone = "positive" if displayed_delta > 0 else "negative"
        if metric == "grade_a_compliance_rate":
            return {"trend": f"{sign}{displayed_delta:.1f}pt MoM", "trend_tone": tone}
        if metric == "average_inspection_score":
            score_tone = (
                "neutral"
                if displayed_delta == 0
                else "positive"
                if displayed_delta < 0
                else "negative"
            )
            return {
                "trend": f"{sign}{displayed_delta:.1f}pt MoM{' (better)' if displayed_delta < 0 else ''}",
                "trend_tone": score_tone,
            }
        if metric == "critical_violation_rate":
            rate_tone = (
                "neutral"
                if displayed_delta == 0
                else "positive"
                if displayed_delta < 0
                else "negative"
            )
            return {
                "trend": f"{sign}{displayed_delta:.1f}/100 YoY",
                "trend_tone": rate_tone,
            }
        if metric == "open_311_food_complaints":
            percent = 100.0 * delta / comparison if comparison else 0.0
            return {
                "trend": f"{'+' if percent > 0 else ''}{percent:.1f}% WoW",
                "trend_tone": "positive" if percent <= 0 else "negative",
            }
        return {"trend": "", "trend_tone": "neutral"}

    def boroughs(self, sort: str) -> list[dict[str, Any]]:
        order_columns = {
            "safety_rank": "grade_a_percent desc",
            "name": "borough_name asc",
            "grade_a_percent": "grade_a_percent desc",
            "complaint_rate": "complaint_rate_per_1000 asc nulls last",
            "critical_violation_rate": "critical_violation_rate_per_100 asc nulls last",
            "improvement_rate": "improvement_rate desc nulls last",
            "total_restaurants": "total_restaurants desc",
        }
        order = order_columns[sort]
        sql = f"""
        with grade_summary as (
            select
                borough_key,
                borough_name,
                max(total_restaurants) as total_restaurants,
                max(graded_restaurants) as graded_restaurants,
                sum(case when grade = 'A' then restaurant_count else 0 end) as grade_a_count,
                max(case when grade = 'A' then grade_percent_of_graded end) as grade_a_percent
            from mart_borough_grade_summary
            where area_level = 'BOROUGH'
            group by borough_key, borough_name
        ), top_issues as (
            select borough_key, violation_description,
                   row_number() over (
                       partition by borough_key
                       order by violation_count desc, violation_description
                   ) as issue_rank
            from mart_violation_by_borough
            where is_critical
        ), complaint_rates as (
            select
                borough_key,
                1000.0 * sum(complaint_count) / nullif(max(total_restaurants), 0)
                    as complaint_rate_per_1000
            from mart_weekly_311_vs_inspection
            where area_level = 'BOROUGH'
              and week_start_date > date_add(
                  'week',
                  -12,
                  (select max(week_start_date) from mart_weekly_311_vs_inspection)
              )
            group by borough_key
        ), critical_violation_rates as (
            select
                borough_key,
                100.0 * count(distinct case when is_critical then inspection_id end)
                    / nullif(count(distinct inspection_id), 0) as critical_violation_rate_per_100
            from fact_inspection
            group by borough_key
        ), improvements as (
            select
                history.borough_key,
                100.0 * count_if(history.improved_to_a)
                    / nullif(count_if(history.previous_grade in ('B', 'C')), 0)
                    as improvement_rate
            from mart_restaurant_grade_history as history
            where history.inspection_date > date_add(
                'year',
                -1,
                (select max(inspection_date) from mart_restaurant_grade_history)
            )
            group by history.borough_key
        )
        select
            grades.*,
            issues.violation_description as top_issue,
            complaints.complaint_rate_per_1000,
            critical_rates.critical_violation_rate_per_100,
            improvements.improvement_rate
        from grade_summary as grades
        left join top_issues as issues
            on grades.borough_key = issues.borough_key and issues.issue_rank = 1
        left join complaint_rates as complaints
            on grades.borough_key = complaints.borough_key
        left join critical_violation_rates as critical_rates
            on grades.borough_key = critical_rates.borough_key
        left join improvements
            on grades.borough_key = improvements.borough_key
        order by {order}
        """
        rows = self.athena.query(sql)
        for index, row in enumerate(rows, start=1):
            row["safety_rank"] = index
            row["top_issue_summary"] = self.top_issue_summary(row.get("top_issue"))
        return rows

    @staticmethod
    def top_issue_summary(description: str | None) -> str:
        """Translate common DOHMH violation text into a readable card label."""
        if not description:
            return "No critical issue available"
        normalized = description.lower()
        if "cold tcs" in normalized or "above 41" in normalized:
            return "Cold food not kept cold enough"
        if "hot tcs" in normalized or "above 140" in normalized:
            return "Hot food not kept hot enough"
        if "food contact surface" in normalized:
            return "Food-contact surfaces not properly cleaned"
        if "not protected from potential source of contamination" in normalized:
            return "Food or equipment contamination risk"
        if "hand washing" in normalized or "handwash" in normalized:
            return "Handwashing rules were not followed"
        if "pest" in normalized or "rodent" in normalized:
            return "Pest or rodent activity"
        if "unapproved source" in normalized:
            return "Food from an unapproved source"
        return "Serious food-safety issue recorded"

    def grades(self, borough: str | None) -> list[dict[str, Any]]:
        borough = normalized_borough(borough)
        if borough:
            where = f"area_level = 'BOROUGH' and borough_name = {sql_string(borough)}"
        else:
            where = "area_level = 'CITYWIDE'"
        return self.athena.query(
            f"""
            select grade, restaurant_count, graded_restaurants,
                   total_restaurants, grade_percent_of_graded
            from mart_borough_grade_summary
            where {where}
            order by grade
            """
        )

    def grade_distribution_by_borough(self) -> list[dict[str, Any]]:
        """Return the A/B/C split of latest grades for every borough."""
        return self.athena.query(
            """
            select
                borough_key,
                borough_name,
                max(total_restaurants) as total_restaurants,
                max(graded_restaurants) as graded_restaurants,
                max(case when grade = 'A' then grade_percent_of_graded end) as grade_a_percent,
                max(case when grade = 'B' then grade_percent_of_graded end) as grade_b_percent,
                max(case when grade = 'C' then grade_percent_of_graded end) as grade_c_percent
            from mart_borough_grade_summary
            where area_level = 'BOROUGH'
            group by borough_key, borough_name
            order by grade_a_percent desc, borough_name
            """
        )

    def cuisine_heatmap(self) -> list[dict[str, Any]]:
        """Return a robust, live six-cuisine by borough Grade A matrix.

        The six familiar cuisine categories are ranked by their citywide
        Grade B + C share, so the first columns surface the clearest
        attention areas rather than a tiny or unfamiliar sample.
        """
        return self.athena.query(
            """
            with familiar_cuisines as (
                select * from (
                    values
                        ('AMERICAN', 'American'),
                        ('CHINESE', 'Chinese'),
                        ('ITALIAN', 'Italian'),
                        ('MEXICAN', 'Mexican'),
                        ('PIZZA', 'Pizza'),
                        ('SPANISH', 'Spanish')
                ) as cuisines(cuisine_key, cuisine)
            ), eligible_cuisines as (
                select
                    familiar.cuisine_key,
                    familiar.cuisine,
                    count(*) as citywide_restaurants,
                    100.0 * count_if(latest.grade = 'A') / nullif(count(*), 0) as citywide_grade_a_percent,
                    100.0 * count_if(latest.grade in ('B', 'C')) / nullif(count(*), 0) as citywide_attention_percent
                from int_latest_graded_inspection as latest
                join dim_restaurant as restaurants
                    on latest.restaurant_key = restaurants.restaurant_key
                join familiar_cuisines as familiar
                    on upper(restaurants.cuisine) = familiar.cuisine_key
                group by familiar.cuisine_key, familiar.cuisine
                having count(*) >= 250
                order by citywide_attention_percent desc, citywide_restaurants desc, familiar.cuisine
            ), borough_grades as (
                select borough_key,
                       max(case when grade = 'A' then grade_percent_of_graded end) as borough_grade_a_percent
                from mart_borough_grade_summary
                where area_level = 'BOROUGH'
                group by borough_key
            ), restaurant_groups as (
                select
                    familiar.cuisine_key,
                    familiar.cuisine,
                    restaurants.borough_key,
                    count(*) as total_restaurants
                from dim_restaurant as restaurants
                join familiar_cuisines as familiar
                    on upper(restaurants.cuisine) = familiar.cuisine_key
                group by familiar.cuisine_key, familiar.cuisine, restaurants.borough_key
            ), cuisine_grade_mix as (
                select
                    familiar.cuisine_key,
                    restaurants.borough_key,
                    count(*) as graded_restaurants,
                    100.0 * count_if(latest.grade = 'A') / nullif(count(*), 0) as grade_a_percent,
                    100.0 * count_if(latest.grade = 'B') / nullif(count(*), 0) as grade_b_percent,
                    100.0 * count_if(latest.grade = 'C') / nullif(count(*), 0) as grade_c_percent
                from int_latest_graded_inspection as latest
                join dim_restaurant as restaurants
                    on latest.restaurant_key = restaurants.restaurant_key
                join familiar_cuisines as familiar
                    on upper(restaurants.cuisine) = familiar.cuisine_key
                join eligible_cuisines as eligible
                    on familiar.cuisine_key = eligible.cuisine_key
                group by familiar.cuisine_key, restaurants.borough_key
            )
            select
                groups.borough_key,
                boroughs.borough_name,
                eligible.cuisine,
                groups.total_restaurants,
                coalesce(mix.graded_restaurants, 0) as graded_restaurants,
                mix.grade_a_percent as average_grade_a_percent,
                mix.grade_b_percent,
                mix.grade_c_percent,
                borough_grades.borough_grade_a_percent,
                eligible.citywide_grade_a_percent as cuisine_citywide_grade_a_percent
            from restaurant_groups as groups
            join eligible_cuisines as eligible
                on groups.cuisine_key = eligible.cuisine_key
            join dim_borough as boroughs on groups.borough_key = boroughs.borough_key
            join borough_grades on groups.borough_key = borough_grades.borough_key
            left join cuisine_grade_mix as mix
                on groups.cuisine_key = mix.cuisine_key and groups.borough_key = mix.borough_key
            order by eligible.citywide_attention_percent desc, boroughs.borough_name
            """
        )

    def cuisines(
        self,
        borough: str | None,
        sort: str,
        limit: int,
        minimum_restaurants: int,
    ) -> list[dict[str, Any]]:
        borough = normalized_borough(borough)
        order = {
            "name": "cuisine asc",
            "grade_a_percent": "average_grade_a_percent desc",
            "total_restaurants": "total_restaurants desc",
        }[sort]
        where = f"and borough_name = {sql_string(borough)}" if borough else ""
        return self.athena.query(
            f"""
            select cuisine,
                   sum(total_restaurants) as total_restaurants,
                   sum(graded_restaurants) as graded_restaurants,
                   sum(grade_a_restaurants) as grade_a_restaurants,
                   100.0 * sum(grade_a_restaurants)
                       / nullif(sum(graded_restaurants), 0) as average_grade_a_percent
            from mart_cuisine_borough_heatmap
            where 1 = 1 {where}
            group by cuisine
            having sum(total_restaurants) >= {minimum_restaurants}
            order by {order}
            limit {limit}
            """
        )

    def violations(
        self,
        borough: str | None,
        criticality: str,
        sort: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        borough = normalized_borough(borough)
        filters = []
        if borough:
            filters.append(f"borough_name = {sql_string(borough)}")
        if criticality != "all":
            filters.append(f"criticality = {sql_string(criticality.upper())}")
        where = " and ".join(filters) if filters else "1 = 1"
        order = {
            "frequency": "violation_count desc",
            "critical_first": "criticality asc, violation_count desc",
            "name": "violation_description asc",
        }[sort]
        rows = self.athena.query(
            f"""
            with aggregated as (
                select violation_key, violation_code, violation_description,
                       is_critical, criticality,
                       sum(violation_count) as violation_count,
                       sum(affected_restaurant_count) as affected_restaurant_count,
                       100.0 * sum(violation_count)
                           / nullif(sum(total_restaurants), 0) as violations_per_100_restaurants
                from mart_violation_by_borough
                where {where}
                group by violation_key, violation_code, violation_description,
                         is_critical, criticality
            )
            select * from aggregated
            order by {order}
            limit {limit}
            """
        )
        for row in rows:
            row["short_label"] = self.violation_short_label(
                row.get("violation_description")
            )
        return rows

    @staticmethod
    def violation_short_label(description: str | None) -> str:
        """Make official violation wording scannable without changing its meaning."""
        if not description:
            return "Violation details unavailable"
        normalized = description.lower()
        labels = (
            ("non-food contact surface", "Equipment or surfaces hard to clean"),
            ("harborage", "Conditions that attract pests"),
            ("anti-siphonage", "Drainage or backflow problems"),
            ("back-flow", "Drainage or backflow problems"),
            (
                "not protected from potential source of contamination",
                "Food or equipment exposed to contamination",
            ),
            ("cold tcs", "Cold food held too warm"),
            ("hot tcs", "Hot food held too cool"),
            ("food contact surface", "Food-contact surfaces not properly cleaned"),
            ("hand washing", "Handwashing facilities or practices"),
            ("handwash", "Handwashing facilities or practices"),
            ("wiping cloth", "Wiping cloth storage or cleaning"),
            ("rodent", "Rodent activity or prevention"),
            ("vermin", "Pest activity or prevention"),
        )
        for phrase, label in labels:
            if phrase in normalized:
                return label
        first_clause = description.split(";")[0].split(".")[0].strip()
        if len(first_clause) <= 80:
            return first_clause
        return first_clause[:77].rsplit(" ", 1)[0] + "…"

    def violation_criticality_by_borough(self) -> list[dict[str, Any]]:
        """Compare average findings per distinct inspection in each borough."""
        return self.athena.query(
            """
            with inspection_counts as (
                select boroughs.borough_name,
                       count(distinct facts.inspection_id) as inspection_count
                from fact_inspection as facts
                join dim_borough as boroughs
                  on facts.borough_key = boroughs.borough_key
                group by boroughs.borough_name
            ), finding_counts as (
                select borough_name,
                       sum(case when is_critical then violation_count else 0 end)
                           as critical_findings,
                       sum(case when not is_critical then violation_count else 0 end)
                           as non_critical_findings
                from mart_violation_by_borough
                group by borough_name
            )
            select findings.borough_name,
                   inspections.inspection_count,
                   findings.critical_findings,
                   findings.non_critical_findings,
                   cast(findings.critical_findings as double)
                       / nullif(inspections.inspection_count, 0)
                       as critical_findings_per_inspection,
                   cast(findings.non_critical_findings as double)
                       / nullif(inspections.inspection_count, 0)
                       as non_critical_findings_per_inspection
            from finding_counts as findings
            join inspection_counts as inspections
              on findings.borough_name = inspections.borough_name
            order by findings.borough_name
            """
        )
