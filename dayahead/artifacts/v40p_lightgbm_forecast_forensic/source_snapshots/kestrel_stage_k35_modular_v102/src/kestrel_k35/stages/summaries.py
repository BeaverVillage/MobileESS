from __future__ import annotations

import logging

from kestrel_k35.context import PipelineContext
from kestrel_k35.sql import (
    capacity_query,
    conservative_comparison_query,
    flexibility_summary_query,
    temporal_query,
)
from kestrel_k35.utils.duckdb_utils import connect, parquet_expr


def run(ctx: PipelineContext, logger: logging.Logger) -> None:
    if ctx.conservative_local is None:
        raise RuntimeError("Conservative profile이 없습니다.")

    classified_path = (
        ctx.output_dir / "kestrel_12idc_jobs_flexibility.parquet"
    )
    exact_path = (
        ctx.output_dir / "kestrel_12idc_exact_active_5min_dense.parquet"
    )

    connection = connect(ctx.config)
    connection.execute(
        f"CREATE VIEW classified_jobs AS SELECT * FROM {parquet_expr(classified_path)}"
    )
    connection.execute(
        f"CREATE VIEW exact_dense AS SELECT * FROM {parquet_expr(exact_path)}"
    )
    connection.execute(
        f"CREATE VIEW conservative_profile AS "
        f"SELECT * FROM {parquet_expr(ctx.conservative_local)}"
    )

    cases = ctx.config["flexibility_cases"]

    connection.execute(
        flexibility_summary_query(cases, by_dc=False)
    ).fetchdf().to_csv(
        ctx.output_dir / "flexibility_summary_by_case.csv",
        index=False,
        encoding="utf-8-sig",
    )
    connection.execute(
        flexibility_summary_query(cases, by_dc=True)
    ).fetchdf().to_csv(
        ctx.output_dir / "flexibility_summary_by_case_dc.csv",
        index=False,
        encoding="utf-8-sig",
    )
    connection.execute(
        capacity_query(
            [float(x) for x in ctx.config["capacity_reference"]["headroom_factors"]]
        )
    ).fetchdf().to_csv(
        ctx.output_dir / "dc_capacity_reference_exact.csv",
        index=False,
        encoding="utf-8-sig",
    )
    connection.execute(
        temporal_query(cases)
    ).fetchdf().to_csv(
        ctx.output_dir / "hour_of_week_temporal_audit.csv",
        index=False,
        encoding="utf-8-sig",
    )
    connection.execute(
        conservative_comparison_query(
            int(ctx.config["time"]["interval_minutes"])
        )
    ).fetchdf().to_csv(
        ctx.output_dir / "exact_vs_conservative_comparison.csv",
        index=False,
        encoding="utf-8-sig",
    )

    connection.close()
    logger.info("유연성·용량·시간대·conservative 비교 요약 완료")
