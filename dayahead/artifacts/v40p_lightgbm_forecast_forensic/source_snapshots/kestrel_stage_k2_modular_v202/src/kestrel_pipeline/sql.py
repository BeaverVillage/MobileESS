from __future__ import annotations


def create_jobs_views_sql(read_expression: str, h100_regex: str, standby_marker: str) -> str:
    return f"""
    CREATE OR REPLACE VIEW jobs_base AS
    SELECT
        *,
        replace(lower(coalesce(partition, '')), ' ', '') AS partition_norm
    FROM {read_expression};

    CREATE OR REPLACE VIEW jobs AS
    SELECT
        *,
        regexp_matches(partition_norm, '{h100_regex}') AS is_h100_related,
        contains(partition_norm, '{standby_marker}') AS is_standby_partition
    FROM jobs_base;
    """


def create_h100_views_sql(
    completed_state: str,
    source_timezone: str,
    exclude_standby: bool,
    deduplicate_by_id: bool,
) -> str:
    standby_clause = "NOT is_standby_partition" if exclude_standby else "TRUE"
    duplicate_clause = "duplicate_rank = 1" if deduplicate_by_id else "TRUE"

    return f"""
    CREATE OR REPLACE VIEW h100_candidates_pre AS
    SELECT
        *,
        row_number() OVER (
            PARTITION BY id
            ORDER BY submit_time, start_time, end_time
        ) AS duplicate_rank,
        count(*) OVER (PARTITION BY id) AS duplicate_id_count,
        submit_time AS submit_time_utc,
        start_time AS start_time_utc,
        end_time AS end_time_utc,
        timezone('{source_timezone}', submit_time) AS submit_time_source_local,
        timezone('{source_timezone}', start_time) AS start_time_source_local,
        timezone('{source_timezone}', end_time) AS end_time_source_local,
        epoch(end_time - start_time) AS runtime_s,
        epoch(start_time - submit_time) AS queue_wait_s_calc,
        coalesce(gpus_requested, 0.0)
            * epoch(end_time - start_time) / 3600.0 AS gpu_hours,
        CASE
            WHEN consumed_energy_raw_watt_hours > 0
            THEN consumed_energy_raw_watt_hours / 1000.0
            ELSE NULL
        END AS energy_raw_kwh,
        CASE
            WHEN cpu_energy_tdp_estimated_used_watt_hours > 0
            THEN cpu_energy_tdp_estimated_used_watt_hours / 1000.0
            ELSE NULL
        END AS cpu_tdp_energy_kwh,
        CASE
            WHEN consumed_energy_raw_watt_hours > 0
                 AND epoch(end_time - start_time) > 0
            THEN (consumed_energy_raw_watt_hours / 1000.0)
                 / (epoch(end_time - start_time) / 3600.0)
            ELSE NULL
        END AS mean_power_raw_kw,
        CASE
            WHEN regexp_matches(partition_norm, '(^|,)gpu-h100l(-stdby)?($|,)')
                THEN 'h100_long'
            WHEN regexp_matches(partition_norm, '(^|,)gpu-h100s(-stdby)?($|,)')
                THEN 'h100_short'
            WHEN regexp_matches(partition_norm, '(^|,)gpu-h100(-stdby)?($|,)')
                THEN 'h100_base'
            ELSE 'h100_other'
        END AS h100_partition_class,
        submit_time IS NOT NULL AS q_submit_present,
        start_time IS NOT NULL AS q_start_present,
        end_time IS NOT NULL AS q_end_present,
        end_time > start_time AS q_runtime_positive,
        start_time >= submit_time AS q_queue_nonnegative,
        gpus_requested > 0 AS q_gpu_positive,
        abs(gpus_requested - round(gpus_requested)) < 1e-9 AS q_gpu_integer_like,
        consumed_energy_raw_watt_hours > 0 AS q_raw_energy_positive,
        coalesce(shared_job_count, 1) <= 1 AS q_not_shared_job
    FROM jobs
    WHERE
        is_h100_related
        AND state_simple = '{completed_state}'
        AND gpus_requested > 0;

    CREATE OR REPLACE VIEW h100_all_candidates AS
    SELECT
        *,
        CASE
            WHEN NOT q_submit_present THEN 'missing_submit'
            WHEN NOT q_start_present THEN 'missing_start'
            WHEN NOT q_end_present THEN 'missing_end'
            WHEN NOT q_runtime_positive THEN 'nonpositive_runtime'
            WHEN NOT q_queue_nonnegative THEN 'negative_queue_wait'
            WHEN NOT q_gpu_positive THEN 'nonpositive_gpu'
            WHEN duplicate_id_count > 1 THEN 'duplicate_id'
            WHEN is_standby_partition THEN 'standby_partition'
            ELSE 'basic_pass'
        END AS quality_status
    FROM h100_candidates_pre;

    CREATE OR REPLACE VIEW h100_primary_clean AS
    SELECT *
    FROM h100_all_candidates
    WHERE
        {standby_clause}
        AND q_submit_present
        AND q_start_present
        AND q_end_present
        AND q_runtime_positive
        AND q_queue_nonnegative
        AND q_gpu_positive
        AND {duplicate_clause};
    """


def global_summary_query() -> str:
    return """
    SELECT
        count(*) AS total_rows,
        min(submit_time) AS min_submit_time_utc,
        max(submit_time) AS max_submit_time_utc,
        count_if(is_h100_related) AS h100_related_rows,
        count_if(
            is_h100_related AND state_simple = 'COMPLETED' AND gpus_requested > 0
        ) AS h100_completed_gpu_rows,
        count_if(submit_time IS NULL) AS null_submit_time,
        count_if(start_time IS NULL) AS null_start_time,
        count_if(end_time IS NULL) AS null_end_time
    FROM jobs
    """


def quality_summary_query() -> str:
    return """
    SELECT
        count(*) AS h100_all_candidates,
        count_if(is_standby_partition) AS standby_rows,
        count_if(NOT q_start_present) AS missing_start_rows,
        count_if(NOT q_runtime_positive) AS nonpositive_runtime_rows,
        count_if(NOT q_queue_nonnegative) AS negative_queue_rows,
        count_if(NOT q_gpu_integer_like) AS noninteger_gpu_rows,
        count_if(q_raw_energy_positive) AS raw_energy_positive_rows,
        count_if(q_raw_energy_positive AND q_not_shared_job)
            AS raw_energy_unshared_rows,
        count_if(duplicate_id_count > 1) AS duplicate_rows,
        count_if(quality_status = 'basic_pass') AS basic_pass_rows
    FROM h100_all_candidates
    """


def sparse_arrival_query(interval_minutes: int) -> str:
    return f"""
    SELECT
        time_bucket(INTERVAL '{interval_minutes} minutes', submit_time_utc)
            AS timestamp_utc,
        count(*) AS job_count,
        sum(gpus_requested) AS gpu_requested_sum,
        sum(gpu_hours) AS gpu_hours_arrived,
        sum(CASE WHEN q_raw_energy_positive AND q_not_shared_job
                 THEN energy_raw_kwh ELSE NULL END)
            AS reliable_raw_energy_kwh,
        count(DISTINCT user_hash) AS unique_user_count,
        count(DISTINCT account_hash) AS unique_account_count,
        avg(runtime_s) AS runtime_mean_s,
        approx_quantile(runtime_s, 0.50) AS runtime_p50_s,
        approx_quantile(runtime_s, 0.95) AS runtime_p95_s,
        max(gpus_requested) AS gpu_request_max,
        count_if(h100_partition_class = 'h100_short') AS short_partition_jobs,
        count_if(h100_partition_class = 'h100_base') AS base_partition_jobs,
        count_if(h100_partition_class = 'h100_long') AS long_partition_jobs
    FROM h100_primary_clean
    GROUP BY 1
    ORDER BY 1
    """


def dense_arrival_query(interval_minutes: int) -> str:
    sparse = sparse_arrival_query(interval_minutes)
    return f"""
    WITH sparse AS ({sparse}),
    bounds AS (
        SELECT min(timestamp_utc) AS min_ts, max(timestamp_utc) AS max_ts
        FROM sparse
    ),
    grid AS (
        SELECT generate_series AS timestamp_utc
        FROM bounds,
        generate_series(min_ts, max_ts, INTERVAL '{interval_minutes} minutes')
    )
    SELECT
        grid.timestamp_utc,
        coalesce(sparse.job_count, 0) AS job_count,
        coalesce(sparse.gpu_requested_sum, 0.0) AS gpu_requested_sum,
        coalesce(sparse.gpu_hours_arrived, 0.0) AS gpu_hours_arrived,
        coalesce(sparse.reliable_raw_energy_kwh, 0.0) AS reliable_raw_energy_kwh,
        coalesce(sparse.unique_user_count, 0) AS unique_user_count,
        coalesce(sparse.unique_account_count, 0) AS unique_account_count,
        sparse.runtime_mean_s,
        sparse.runtime_p50_s,
        sparse.runtime_p95_s,
        coalesce(sparse.gpu_request_max, 0.0) AS gpu_request_max,
        coalesce(sparse.short_partition_jobs, 0) AS short_partition_jobs,
        coalesce(sparse.base_partition_jobs, 0) AS base_partition_jobs,
        coalesce(sparse.long_partition_jobs, 0) AS long_partition_jobs
    FROM grid
    LEFT JOIN sparse USING (timestamp_utc)
    ORDER BY timestamp_utc
    """
