from __future__ import annotations

from typing import Any


def case_id(case: dict[str, Any]) -> str:
    value = str(case["case_id"])
    clean = "".join(ch for ch in value if ch.isalnum() or ch == "_")
    if not clean or clean != value:
        raise ValueError(f"지원하지 않는 case_id: {value}")
    return clean


def classification_columns(cases: list[dict[str, Any]]) -> str:
    columns = []

    for case in cases:
        identifier = case_id(case)
        runtime_s = int(case["min_runtime_minutes"]) * 60
        queue_s = int(case["min_observed_queue_minutes"]) * 60

        columns.append(
            f"(runtime_s >= {runtime_s} AND queue_wait_s_calc >= {queue_s}) "
            f"AS is_flexible_{identifier}"
        )
        columns.append(
            f"""CASE
            WHEN runtime_s >= {runtime_s} AND queue_wait_s_calc >= {queue_s}
                THEN 'flexible'
            WHEN runtime_s < {runtime_s} AND queue_wait_s_calc < {queue_s}
                THEN 'runtime_and_queue_below_threshold'
            WHEN runtime_s < {runtime_s}
                THEN 'runtime_below_threshold'
            ELSE 'queue_below_threshold'
            END AS flexibility_status_{identifier}"""
        )

    return ",\n".join(columns)


def classified_jobs_query(jobs_expr: str, cases: list[dict[str, Any]]) -> str:
    return f"""SELECT
        *,
        id AS job_uid,
        {classification_columns(cases)},
        timezone('Australia/Melbourne', submit_time_utc) AS submit_time_melbourne,
        timezone('Australia/Melbourne', start_time_utc) AS start_time_melbourne,
        timezone('Australia/Melbourne', end_time_utc) AS end_time_melbourne
    FROM {jobs_expr}"""


def exact_sparse_query(interval_minutes: int, cases: list[dict[str, Any]]) -> str:
    interval_seconds = interval_minutes * 60
    case_flags = ", ".join(
        f"is_flexible_{case_id(case)}" for case in cases
    )

    flex_sums = []
    for case in cases:
        identifier = case_id(case)
        flex_sums.append(
            f"""sum(
                CASE WHEN is_flexible_{identifier}
                THEN gpus_requested * overlap_seconds / {float(interval_seconds)}
                ELSE 0.0 END
            ) AS flexible_avg_gpus_{identifier}"""
        )

    return f"""WITH expanded AS (
        SELECT
            job_uid,
            origin_dc AS dc_id,
            slot_start_utc AS timestamp_utc,
            greatest(
                0.0,
                epoch(
                    least(
                        end_time_utc,
                        slot_start_utc + INTERVAL '{interval_minutes} minutes'
                    )
                    - greatest(start_time_utc, slot_start_utc)
                )
            ) AS overlap_seconds,
            gpus_requested,
            {case_flags}
        FROM classified_jobs,
        LATERAL generate_series(
            time_bucket(INTERVAL '{interval_minutes} minutes', start_time_utc),
            time_bucket(
                INTERVAL '{interval_minutes} minutes',
                end_time_utc - INTERVAL '1 microsecond'
            ),
            INTERVAL '{interval_minutes} minutes'
        ) AS slots(slot_start_utc)
    )
    SELECT
        timestamp_utc,
        timezone('Australia/Melbourne', timestamp_utc) AS timestamp_melbourne,
        dc_id,
        sum(gpus_requested * overlap_seconds / {float(interval_seconds)})
            AS total_avg_gpus,
        sum(gpus_requested * overlap_seconds) AS total_gpu_seconds,
        sum(overlap_seconds / {float(interval_seconds)})
            AS active_job_equivalents,
        count(*) AS overlapping_job_segments,
        {", ".join(flex_sums)}
    FROM expanded
    WHERE overlap_seconds > 0
    GROUP BY timestamp_utc, timestamp_melbourne, dc_id"""


def exact_dense_query(interval_minutes: int, cases: list[dict[str, Any]]) -> str:
    extra = []

    for case in cases:
        identifier = case_id(case)
        extra.append(
            f"coalesce(s.flexible_avg_gpus_{identifier}, 0.0) "
            f"AS flexible_avg_gpus_{identifier}"
        )
        extra.append(
            f"greatest(coalesce(s.total_avg_gpus, 0.0) "
            f"- coalesce(s.flexible_avg_gpus_{identifier}, 0.0), 0.0) "
            f"AS fixed_avg_gpus_{identifier}"
        )

    return f"""WITH bounds AS (
        SELECT min(timestamp_utc) AS min_ts, max(timestamp_utc) AS max_ts
        FROM exact_sparse
    ),
    data_centers AS (
        SELECT DISTINCT origin_dc AS dc_id FROM classified_jobs
    ),
    grid AS (
        SELECT generated_timestamp AS timestamp_utc, dc_id
        FROM bounds,
        generate_series(
            min_ts,
            max_ts,
            INTERVAL '{interval_minutes} minutes'
        ) AS series(generated_timestamp)
        CROSS JOIN data_centers
    )
    SELECT
        g.timestamp_utc,
        timezone('Australia/Melbourne', g.timestamp_utc)
            AS timestamp_melbourne,
        g.dc_id,
        coalesce(s.total_avg_gpus, 0.0) AS total_avg_gpus,
        coalesce(s.total_gpu_seconds, 0.0) AS total_gpu_seconds,
        coalesce(s.active_job_equivalents, 0.0) AS active_job_equivalents,
        coalesce(s.overlapping_job_segments, 0) AS overlapping_job_segments,
        {", ".join(extra)}
    FROM grid g
    LEFT JOIN exact_sparse s USING (timestamp_utc, dc_id)
    ORDER BY timestamp_utc, dc_id"""


def flexibility_summary_query(cases: list[dict[str, Any]], by_dc: bool) -> str:
    queries = []

    for case in cases:
        identifier = case_id(case)
        dc_select = "origin_dc AS dc_id," if by_dc else ""
        dc_group = "GROUP BY origin_dc" if by_dc else ""

        queries.append(
            f"""SELECT
                '{identifier}' AS case_id,
                {dc_select}
                count(*) AS total_jobs,
                count_if(is_flexible_{identifier}) AS flexible_jobs,
                sum(gpu_hours) AS total_gpu_hours,
                sum(CASE WHEN is_flexible_{identifier}
                    THEN gpu_hours ELSE 0.0 END) AS flexible_gpu_hours,
                count_if(is_flexible_{identifier})::DOUBLE / count(*)
                    AS flexible_job_share,
                sum(CASE WHEN is_flexible_{identifier}
                    THEN gpu_hours ELSE 0.0 END) / sum(gpu_hours)
                    AS flexible_gpu_hour_share
            FROM classified_jobs
            {dc_group}"""
        )

    return "\nUNION ALL\n".join(queries)


def capacity_query(headroom_factors: list[float]) -> str:
    capacity_columns = []

    for factor in headroom_factors:
        label = str(int(round(factor * 100))).zfill(3)
        capacity_columns.append(
            f"cast(ceil(approx_quantile(total_avg_gpus, 0.99) * {factor}) "
            f"AS BIGINT) AS exact_capacity_p99_x{label}"
        )

    return f"""SELECT
        dc_id,
        avg(total_avg_gpus) AS exact_active_gpu_mean,
        approx_quantile(total_avg_gpus, 0.50) AS exact_active_gpu_p50,
        approx_quantile(total_avg_gpus, 0.95) AS exact_active_gpu_p95,
        approx_quantile(total_avg_gpus, 0.99) AS exact_active_gpu_p99,
        max(total_avg_gpus) AS exact_active_gpu_max,
        avg(CASE WHEN total_avg_gpus > 0 THEN 1.0 ELSE 0.0 END)
            AS nonzero_slot_share,
        {", ".join(capacity_columns)}
    FROM exact_dense
    GROUP BY dc_id
    ORDER BY dc_id"""


def temporal_query(cases: list[dict[str, Any]]) -> str:
    flex_columns = []

    for case in cases:
        identifier = case_id(case)
        flex_columns.append(
            f"avg(flexible_avg_gpus_{identifier}) "
            f"AS mean_flexible_avg_gpus_{identifier}"
        )

    return f"""SELECT
        dc_id,
        cast(strftime(timestamp_melbourne, '%w') AS INTEGER)
            AS melbourne_day_of_week,
        extract(hour FROM timestamp_melbourne) AS melbourne_hour,
        cast(strftime(timestamp_melbourne, '%w') AS INTEGER) * 24
            + extract(hour FROM timestamp_melbourne) AS hour_of_week,
        avg(total_avg_gpus) AS mean_total_avg_gpus,
        approx_quantile(total_avg_gpus, 0.95) AS p95_total_avg_gpus,
        max(total_avg_gpus) AS max_total_avg_gpus,
        {", ".join(flex_columns)}
    FROM exact_dense
    GROUP BY dc_id, melbourne_day_of_week, melbourne_hour, hour_of_week
    ORDER BY dc_id, hour_of_week"""


def conservative_comparison_query(interval_minutes: int) -> str:
    interval_hours = float(interval_minutes) / 60.0

    return f"""WITH exact_summary AS (
        SELECT
            dc_id,
            avg(total_avg_gpus) AS exact_mean,
            approx_quantile(total_avg_gpus, 0.95) AS exact_p95,
            approx_quantile(total_avg_gpus, 0.99) AS exact_p99,
            max(total_avg_gpus) AS exact_max,
            sum(total_avg_gpus) * {interval_hours} AS exact_gpu_hours
        FROM exact_dense
        GROUP BY dc_id
    ),
    conservative_summary AS (
        SELECT
            dc_id,
            avg(active_gpus_conservative) AS conservative_mean,
            approx_quantile(active_gpus_conservative, 0.95)
                AS conservative_p95,
            approx_quantile(active_gpus_conservative, 0.99)
                AS conservative_p99,
            max(active_gpus_conservative) AS conservative_max,
            sum(active_gpus_conservative) * {interval_hours}
                AS conservative_gpu_slot_hours
        FROM conservative_profile
        GROUP BY dc_id
    )
    SELECT
        e.dc_id,
        exact_mean,
        conservative_mean,
        conservative_mean / nullif(exact_mean, 0.0)
            AS conservative_to_exact_mean_ratio,
        exact_p95,
        conservative_p95,
        conservative_p95 / nullif(exact_p95, 0.0)
            AS conservative_to_exact_p95_ratio,
        exact_p99,
        conservative_p99,
        conservative_p99 / nullif(exact_p99, 0.0)
            AS conservative_to_exact_p99_ratio,
        exact_max,
        conservative_max,
        conservative_max / nullif(exact_max, 0.0)
            AS conservative_to_exact_max_ratio,
        exact_gpu_hours,
        conservative_gpu_slot_hours,
        conservative_gpu_slot_hours / nullif(exact_gpu_hours, 0.0)
            AS conservative_to_exact_energy_ratio
    FROM exact_summary e
    JOIN conservative_summary c USING (dc_id)
    ORDER BY e.dc_id"""
