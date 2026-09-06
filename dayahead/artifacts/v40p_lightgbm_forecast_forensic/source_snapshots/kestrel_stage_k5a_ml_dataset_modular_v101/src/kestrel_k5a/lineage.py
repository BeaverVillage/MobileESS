from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from .context import PipelineContext
from .db import connect, parquet_expr


@dataclass
class AnalysisBounds:
    analysis_start_utc: pd.Timestamp
    analysis_end_utc: pd.Timestamp
    first_job_submit_utc: pd.Timestamp
    first_job_start_utc: pd.Timestamp
    last_job_end_utc: pd.Timestamp
    dense_start_utc: pd.Timestamp
    dense_end_utc: pd.Timestamp


def _utc(value) -> pd.Timestamp:
    result = pd.Timestamp(value)
    if result.tzinfo is None:
        return result.tz_localize("UTC")
    return result.tz_convert("UTC")


def audit_lineage(
    ctx: PipelineContext, logger: logging.Logger
) -> tuple[AnalysisBounds, pd.DataFrame]:
    con = connect(ctx.config)
    try:
        jobs = parquet_expr(ctx.jobs_path)
        dense = parquet_expr(ctx.dense_path)
        job_row = con.execute(
            f"""
            SELECT
                count(*) AS job_rows,
                min(submit_time_utc) AS min_submit_utc,
                min(start_time_utc) AS min_start_utc,
                max(end_time_utc) AS max_end_utc,
                count(DISTINCT origin_dc) AS idc_count,
                sum(gpu_hours) AS job_gpu_hours
            FROM {jobs}
            """
        ).fetchdf().iloc[0]
        dense_row = con.execute(
            f"""
            SELECT
                count(*) AS dense_rows,
                min(timestamp_utc) AS min_dense_utc,
                max(timestamp_utc) AS max_dense_utc,
                count(DISTINCT dc_id) AS idc_count,
                sum(total_avg_gpus)
                    * {int(ctx.config['analysis']['interval_minutes']) / 60.0}
                    AS dense_gpu_hours
            FROM {dense}
            """
        ).fetchdf().iloc[0]

        first_submit = _utc(job_row["min_submit_utc"])
        first_start = _utc(job_row["min_start_utc"])
        last_end = _utc(job_row["max_end_utc"])
        dense_start = _utc(dense_row["min_dense_utc"])
        dense_end = _utc(dense_row["max_dense_utc"])
        interval = f"{int(ctx.config['analysis']['interval_minutes'])}min"
        analysis_start = first_start.floor(interval)
        last_valid_slot = (last_end - pd.Timedelta(microseconds=1)).floor(interval)
        hard_end = _utc(ctx.config["analysis"]["hard_end_utc"])
        analysis_end = min(last_valid_slot, hard_end)
        if analysis_end < analysis_start:
            raise ValueError("Analysis end precedes analysis start")

        rows = [
            {
                "source": "kestrel_jobs",
                "row_count": int(job_row["job_rows"]),
                "idc_count": int(job_row["idc_count"]),
                "minimum_timestamp_utc": first_submit,
                "minimum_start_utc": first_start,
                "maximum_timestamp_utc": last_end,
                "gpu_hours": float(job_row["job_gpu_hours"]),
            },
            {
                "source": "k35_exact_dense",
                "row_count": int(dense_row["dense_rows"]),
                "idc_count": int(dense_row["idc_count"]),
                "minimum_timestamp_utc": dense_start,
                "minimum_start_utc": dense_start,
                "maximum_timestamp_utc": dense_end,
                "gpu_hours": float(dense_row["dense_gpu_hours"]),
            },
        ]

        if ctx.k4b_training_power_path is not None:
            power = parquet_expr(ctx.k4b_training_power_path)
            columns = (
                con.execute(f"DESCRIBE SELECT * FROM {power}")
                .fetchdf()["column_name"]
                .astype(str)
                .tolist()
            )
            time_col = next(
                (
                    col
                    for col in ["timestamp_utc", "slot_start_utc", "time_utc"]
                    if col in columns
                ),
                None,
            )
            site_col = next(
                (
                    col
                    for col in ["dc_id", "idc_id", "site_id"]
                    if col in columns
                ),
                None,
            )
            if time_col and site_col:
                row = con.execute(
                    f'''SELECT
                        count(*) AS n,
                        min("{time_col}") AS min_ts,
                        max("{time_col}") AS max_ts,
                        count(DISTINCT "{site_col}") AS sites
                    FROM {power}'''
                ).fetchdf().iloc[0]
                rows.append(
                    {
                        "source": "k4b_training_power",
                        "row_count": int(row["n"]),
                        "idc_count": int(row["sites"]),
                        "minimum_timestamp_utc": _utc(row["min_ts"]),
                        "minimum_start_utc": _utc(row["min_ts"]),
                        "maximum_timestamp_utc": _utc(row["max_ts"]),
                        "gpu_hours": None,
                    }
                )

        rows.append(
            {
                "source": "k5a_selected_analysis_window",
                "row_count": None,
                "idc_count": int(dense_row["idc_count"]),
                "minimum_timestamp_utc": analysis_start,
                "minimum_start_utc": analysis_start,
                "maximum_timestamp_utc": analysis_end,
                "gpu_hours": None,
            }
        )
        audit = pd.DataFrame(rows)
        audit.to_csv(
            ctx.output_dir / "timestamp_lineage_audit.csv",
            index=False,
            encoding="utf-8-sig",
        )
        bounds = AnalysisBounds(
            analysis_start,
            analysis_end,
            first_submit,
            first_start,
            last_end,
            dense_start,
            dense_end,
        )
        logger.info("Analysis window: %s to %s", analysis_start, analysis_end)
        return bounds, audit
    finally:
        con.close()
