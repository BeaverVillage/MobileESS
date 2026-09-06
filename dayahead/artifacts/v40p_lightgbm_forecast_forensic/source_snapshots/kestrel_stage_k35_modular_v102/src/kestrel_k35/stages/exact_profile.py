from __future__ import annotations

import logging

from kestrel_k35.context import PipelineContext
from kestrel_k35.sql import exact_dense_query, exact_sparse_query
from kestrel_k35.utils.duckdb_utils import connect, copy_query, parquet_expr


def run(ctx: PipelineContext, logger: logging.Logger) -> None:
    classified_path = (
        ctx.output_dir / "kestrel_12idc_jobs_flexibility.parquet"
    )

    connection = connect(ctx.config)
    connection.execute(
        f"""CREATE VIEW classified_jobs AS
        SELECT * FROM {parquet_expr(classified_path)}"""
    )

    interval = int(ctx.config["time"]["interval_minutes"])
    cases = ctx.config["flexibility_cases"]
    compression = ctx.config["outputs"]["compression"]

    connection.execute(
        "CREATE VIEW exact_sparse AS "
        + exact_sparse_query(interval, cases)
    )

    copy_query(
        connection,
        "SELECT * FROM exact_sparse ORDER BY timestamp_utc, dc_id",
        ctx.output_dir / "kestrel_12idc_exact_active_5min_sparse.parquet",
        compression,
    )
    copy_query(
        connection,
        exact_dense_query(interval, cases),
        ctx.output_dir / "kestrel_12idc_exact_active_5min_dense.parquet",
        compression,
    )

    connection.close()
    logger.info("정확한 overlap 기반 5분 평균 GPU profile 생성 완료")
