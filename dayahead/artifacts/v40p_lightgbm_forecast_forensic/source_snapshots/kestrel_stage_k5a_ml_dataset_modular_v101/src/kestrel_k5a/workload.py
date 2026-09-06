from __future__ import annotations

import logging
from pathlib import Path

from .context import PipelineContext
from .db import connect, copy_query, parquet_expr, quote_path
from .lineage import AnalysisBounds


def _ts(timestamp) -> str:
    return timestamp.strftime("%Y-%m-%d %H:%M:%S%z")


def _ceil_bucket(expression: str, interval_minutes: int) -> str:
    interval = f"INTERVAL '{interval_minutes} minutes'"
    bucket = f"time_bucket({interval}, {expression})"
    return (
        f"CASE WHEN {expression} = {bucket} THEN {bucket} "
        f"ELSE {bucket} + {interval} END"
    )


def build_workload_tables(
    ctx: PipelineContext,
    bounds: AnalysisBounds,
    logger: logging.Logger,
) -> tuple[Path, Path]:
    interval_minutes = int(ctx.config["analysis"]["interval_minutes"])
    interval_hours = interval_minutes / 60.0
    timezone = str(ctx.config["analysis"]["local_timezone"])
    small_max = int(ctx.config["job_size_classes"]["small_max_gpus"])
    medium_max = int(ctx.config["job_size_classes"]["medium_max_gpus"])
    cases = [str(value) for value in ctx.config["analysis"]["flexibility_cases"]]
    compression = str(ctx.config["resources"]["parquet_compression"])
    start = _ts(bounds.analysis_start_utc)
    end = _ts(bounds.analysis_end_utc)

    con = connect(ctx.config)
    try:
        jobs_expr = parquet_expr(ctx.jobs_path)
        dense_expr = parquet_expr(ctx.dense_path)

        con.execute(
            f"""
            CREATE VIEW jobs AS
            SELECT
                CAST(id AS VARCHAR) AS job_uid,
                CAST(origin_dc AS VARCHAR) AS idc_id,
                CAST(submit_time_utc AS TIMESTAMPTZ) AS submit_time_utc,
                CAST(start_time_utc AS TIMESTAMPTZ) AS start_time_utc,
                CAST(end_time_utc AS TIMESTAMPTZ) AS end_time_utc,
                CAST(gpus_requested AS DOUBLE) AS gpus_requested,
                CAST(gpu_hours AS DOUBLE) AS gpu_hours,
                CAST(runtime_s AS DOUBLE) AS runtime_s,
                CAST(queue_wait_s_calc AS DOUBLE) AS queue_wait_s,
                {', '.join(f'CAST(is_flexible_{case} AS BOOLEAN) AS is_flexible_{case}' for case in cases)}
            FROM {jobs_expr}
            WHERE
                submit_time_utc IS NOT NULL
                AND start_time_utc IS NOT NULL
                AND end_time_utc IS NOT NULL
                AND gpus_requested > 0
                AND runtime_s > 0
            """
        )

        con.execute(
            f"""
            CREATE VIEW dense_cropped AS
            SELECT
                CAST(timestamp_utc AS TIMESTAMPTZ) AS timestamp_utc,
                CAST(timestamp_melbourne AS TIMESTAMP) AS timestamp_melbourne,
                CAST(dc_id AS VARCHAR) AS idc_id,
                CAST(total_avg_gpus AS DOUBLE) AS total_avg_active_gpus,
                CAST(total_gpu_seconds AS DOUBLE) AS total_gpu_seconds,
                CAST(active_job_equivalents AS DOUBLE) AS running_job_equivalents,
                CAST(overlapping_job_segments AS BIGINT) AS overlapping_job_segments,
                {', '.join(f'CAST(flexible_avg_gpus_{case} AS DOUBLE) AS flexible_avg_active_gpus_{case}, CAST(fixed_avg_gpus_{case} AS DOUBLE) AS fixed_avg_active_gpus_{case}' for case in cases)}
            FROM {dense_expr}
            WHERE timestamp_utc BETWEEN TIMESTAMPTZ '{start}' AND TIMESTAMPTZ '{end}'
            """
        )

        arrival_case_columns = []
        for case in cases:
            arrival_case_columns.extend(
                [
                    f"count_if(is_flexible_{case}) AS arriving_flexible_job_count_{case}",
                    f"sum(CASE WHEN is_flexible_{case} THEN gpus_requested ELSE 0 END) AS arriving_flexible_requested_gpus_{case}",
                    f"sum(CASE WHEN is_flexible_{case} THEN gpu_hours ELSE 0 END) AS arriving_flexible_gpu_hours_{case}",
                    f"count_if(NOT is_flexible_{case}) AS arriving_fixed_job_count_{case}",
                    f"sum(CASE WHEN NOT is_flexible_{case} THEN gpus_requested ELSE 0 END) AS arriving_fixed_requested_gpus_{case}",
                    f"sum(CASE WHEN NOT is_flexible_{case} THEN gpu_hours ELSE 0 END) AS arriving_fixed_gpu_hours_{case}",
                ]
            )

        common_arrival_columns = [
            "count(*) AS arriving_job_count",
            "sum(gpus_requested) AS arriving_requested_gpus",
            "sum(gpu_hours) AS arriving_gpu_hours",
            "avg(queue_wait_s) AS arriving_mean_queue_wait_s",
            "quantile_cont(queue_wait_s, 0.95) AS arriving_p95_queue_wait_s",
            "avg(runtime_s) AS arriving_mean_runtime_s",
            "quantile_cont(runtime_s, 0.95) AS arriving_p95_runtime_s",
            f"count_if(gpus_requested <= {small_max}) AS arriving_small_job_count",
            f"count_if(gpus_requested > {small_max} AND gpus_requested <= {medium_max}) AS arriving_medium_job_count",
            f"count_if(gpus_requested > {medium_max}) AS arriving_large_job_count",
        ]

        con.execute(
            f"""
            CREATE VIEW arrivals_site AS
            SELECT
                time_bucket(INTERVAL '{interval_minutes} minutes', submit_time_utc)
                    AS timestamp_utc,
                idc_id,
                {', '.join(common_arrival_columns + arrival_case_columns)}
            FROM jobs
            WHERE submit_time_utc BETWEEN TIMESTAMPTZ '{start}' AND TIMESTAMPTZ '{end}'
            GROUP BY 1, 2
            """
        )

        con.execute(
            f"""
            CREATE VIEW arrivals_global AS
            SELECT
                time_bucket(INTERVAL '{interval_minutes} minutes', submit_time_utc)
                    AS timestamp_utc,
                {', '.join(common_arrival_columns + arrival_case_columns)}
            FROM jobs
            WHERE submit_time_utc BETWEEN TIMESTAMPTZ '{start}' AND TIMESTAMPTZ '{end}'
            GROUP BY 1
            """
        )

        submit_event_slot = _ceil_bucket("submit_time_utc", interval_minutes)
        start_event_slot = _ceil_bucket("start_time_utc", interval_minutes)
        con.execute(
            f"""
            CREATE VIEW queue_events AS
            SELECT
                event_slot_utc AS timestamp_utc,
                idc_id,
                sum(delta_jobs) AS delta_jobs,
                sum(delta_gpus) AS delta_gpus
            FROM (
                SELECT
                    {submit_event_slot} AS event_slot_utc,
                    idc_id,
                    1.0 AS delta_jobs,
                    gpus_requested AS delta_gpus
                FROM jobs
                WHERE submit_time_utc < start_time_utc
                UNION ALL
                SELECT
                    {start_event_slot} AS event_slot_utc,
                    idc_id,
                    -1.0 AS delta_jobs,
                    -gpus_requested AS delta_gpus
                FROM jobs
                WHERE submit_time_utc < start_time_utc
            ) events
            GROUP BY 1, 2
            """
        )

        con.execute(
            f"""
            CREATE VIEW queue_bounds AS
            SELECT
                least(
                    TIMESTAMPTZ '{start}',
                    coalesce(min(timestamp_utc), TIMESTAMPTZ '{start}')
                ) AS queue_start_utc
            FROM queue_events
            """
        )
        con.execute(
            f"""
            CREATE VIEW queue_grid AS
            SELECT
                generated_timestamp AS timestamp_utc,
                idc_id
            FROM queue_bounds,
            generate_series(
                queue_start_utc,
                TIMESTAMPTZ '{end}',
                INTERVAL '{interval_minutes} minutes'
            ) AS series(generated_timestamp)
            CROSS JOIN (SELECT DISTINCT idc_id FROM jobs) sites
            """
        )
        con.execute(
            """
            CREATE VIEW queue_state_full AS
            SELECT
                grid.timestamp_utc,
                grid.idc_id,
                greatest(
                    sum(coalesce(events.delta_jobs, 0.0)) OVER (
                        PARTITION BY grid.idc_id
                        ORDER BY grid.timestamp_utc
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ),
                    0.0
                ) AS queued_job_count,
                greatest(
                    sum(coalesce(events.delta_gpus, 0.0)) OVER (
                        PARTITION BY grid.idc_id
                        ORDER BY grid.timestamp_utc
                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                    ),
                    0.0
                ) AS queued_requested_gpus
            FROM queue_grid grid
            LEFT JOIN queue_events events
                USING (timestamp_utc, idc_id)
            """
        )
        con.execute(
            f"""
            CREATE VIEW queue_state AS
            SELECT *
            FROM queue_state_full
            WHERE timestamp_utc BETWEEN TIMESTAMPTZ '{start}' AND TIMESTAMPTZ '{end}'
            """
        )

        site_select = [
            "dense.timestamp_utc",
            f"timezone('{timezone}', dense.timestamp_utc) AS timestamp_melbourne",
            "dense.idc_id",
            "dense.total_avg_active_gpus",
            "dense.total_gpu_seconds",
            "dense.running_job_equivalents",
            "dense.overlapping_job_segments",
        ]
        for case in cases:
            site_select.extend(
                [
                    f"dense.flexible_avg_active_gpus_{case}",
                    f"dense.fixed_avg_active_gpus_{case}",
                ]
            )
        zero_arrival_columns = [
            "arriving_job_count",
            "arriving_requested_gpus",
            "arriving_gpu_hours",
            "arriving_mean_queue_wait_s",
            "arriving_p95_queue_wait_s",
            "arriving_mean_runtime_s",
            "arriving_p95_runtime_s",
            "arriving_small_job_count",
            "arriving_medium_job_count",
            "arriving_large_job_count",
        ]
        for case in cases:
            zero_arrival_columns.extend(
                [
                    f"arriving_flexible_job_count_{case}",
                    f"arriving_flexible_requested_gpus_{case}",
                    f"arriving_flexible_gpu_hours_{case}",
                    f"arriving_fixed_job_count_{case}",
                    f"arriving_fixed_requested_gpus_{case}",
                    f"arriving_fixed_gpu_hours_{case}",
                ]
            )
        for column in zero_arrival_columns:
            site_select.append(f"coalesce(arrivals.{column}, 0.0) AS {column}")
        site_select.extend(
            [
                "coalesce(queue.queued_job_count, 0.0) AS queued_job_count",
                "coalesce(queue.queued_requested_gpus, 0.0) AS queued_requested_gpus",
            ]
        )

        site_query = f"""
            SELECT
                {', '.join(site_select)}
            FROM dense_cropped dense
            LEFT JOIN arrivals_site arrivals
                USING (timestamp_utc, idc_id)
            LEFT JOIN queue_state queue
                USING (timestamp_utc, idc_id)
            ORDER BY dense.timestamp_utc, dense.idc_id
        """
        site_path = ctx.output_dir / "kestrel_12idc_5min_workload.parquet"
        copy_query(con, site_query, site_path, compression)
        con.execute(
            f"CREATE VIEW site_workload AS SELECT * FROM read_parquet('{quote_path(site_path)}')"
        )

        sum_columns = [
            "total_avg_active_gpus",
            "total_gpu_seconds",
            "running_job_equivalents",
            "overlapping_job_segments",
            "queued_job_count",
            "queued_requested_gpus",
        ]
        for case in cases:
            sum_columns.extend(
                [
                    f"flexible_avg_active_gpus_{case}",
                    f"fixed_avg_active_gpus_{case}",
                ]
            )
        global_site_select = [
            "timestamp_utc",
            f"timezone('{timezone}', timestamp_utc) AS timestamp_melbourne",
        ] + [f"sum({column}) AS {column}" for column in sum_columns]

        con.execute(
            f"""
            CREATE VIEW global_site_state AS
            SELECT
                {', '.join(global_site_select)}
            FROM site_workload
            GROUP BY timestamp_utc
            """
        )

        global_select = [
            "state.timestamp_utc",
            "state.timestamp_melbourne",
        ] + [f"state.{column}" for column in sum_columns]
        for column in zero_arrival_columns:
            global_select.append(f"coalesce(arrivals.{column}, 0.0) AS {column}")

        global_query = f"""
            SELECT
                {', '.join(global_select)}
            FROM global_site_state state
            LEFT JOIN arrivals_global arrivals
                USING (timestamp_utc)
            ORDER BY state.timestamp_utc
        """
        global_path = ctx.output_dir / "kestrel_global_5min_workload.parquet"
        copy_query(con, global_query, global_path, compression)

        logger.info("Site workload table: %s", site_path)
        logger.info("Global workload table: %s", global_path)
        return global_path, site_path
    finally:
        con.close()
