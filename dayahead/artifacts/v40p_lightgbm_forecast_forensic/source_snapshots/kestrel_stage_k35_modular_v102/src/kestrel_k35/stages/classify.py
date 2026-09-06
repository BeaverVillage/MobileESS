from __future__ import annotations

import logging

from kestrel_k35.context import PipelineContext
from kestrel_k35.sql import classified_jobs_query
from kestrel_k35.utils.duckdb_utils import connect, copy_query, parquet_expr


REQUIRED_COLUMNS = {
    "id",
    "origin_dc",
    "submit_time_utc",
    "start_time_utc",
    "end_time_utc",
    "runtime_s",
    "queue_wait_s_calc",
    "gpus_requested",
    "gpu_hours",
}


def run(ctx: PipelineContext, logger: logging.Logger) -> None:
    if ctx.jobs_local is None:
        raise RuntimeError("Stage K3 job input이 없습니다.")

    connection = connect(ctx.config)
    expression = parquet_expr(ctx.jobs_local)
    schema = connection.execute(f"DESCRIBE SELECT * FROM {expression}").fetchdf()
    schema.to_csv(
        ctx.report_dir / "jobs_input_schema.csv",
        index=False,
        encoding="utf-8-sig",
    )

    missing = REQUIRED_COLUMNS - set(schema["column_name"].astype(str))
    if missing:
        raise ValueError(f"Stage K3 job table 필수 컬럼 누락: {sorted(missing)}")

    query = classified_jobs_query(
        expression,
        ctx.config["flexibility_cases"],
    )

    copy_query(
        connection,
        query,
        ctx.output_dir / "kestrel_12idc_jobs_flexibility.parquet",
        ctx.config["outputs"]["compression"],
    )

    summary = connection.execute(
        f"""SELECT
            count(*) AS row_count,
            count(DISTINCT id) AS distinct_job_count,
            count(DISTINCT origin_dc) AS distinct_dc_count,
            sum(gpu_hours) AS total_gpu_hours,
            min(start_time_utc) AS min_start_utc,
            max(end_time_utc) AS max_end_utc
        FROM ({query})"""
    ).fetchdf()
    summary.to_csv(
        ctx.report_dir / "classified_job_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )

    connection.close()
    logger.info("F15/F30/F60 job 분류 완료")
