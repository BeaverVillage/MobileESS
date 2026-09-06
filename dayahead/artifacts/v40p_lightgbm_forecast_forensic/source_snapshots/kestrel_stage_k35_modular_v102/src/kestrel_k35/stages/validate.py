from __future__ import annotations

import logging

from kestrel_k35.context import PipelineContext
from kestrel_k35.sql import case_id
from kestrel_k35.utils.duckdb_utils import connect, parquet_expr
from kestrel_k35.utils.files import write_json


def scalar(connection, query: str):
    return connection.execute(query).fetchone()[0]


def run(ctx: PipelineContext, logger: logging.Logger) -> None:
    classified = parquet_expr(
        ctx.output_dir / "kestrel_12idc_jobs_flexibility.parquet"
    )
    sparse = parquet_expr(
        ctx.output_dir / "kestrel_12idc_exact_active_5min_sparse.parquet"
    )
    dense = parquet_expr(
        ctx.output_dir / "kestrel_12idc_exact_active_5min_dense.parquet"
    )

    connection = connect(ctx.config)
    interval_hours = float(ctx.config["time"]["interval_minutes"]) / 60.0
    rel_tol = float(ctx.config["validation"]["relative_tolerance"])
    abs_tol = float(ctx.config["validation"]["absolute_tolerance"])

    metrics = {
        "classified_job_rows": int(
            scalar(connection, f"SELECT count(*) FROM {classified}")
        ),
        "distinct_job_count": int(
            scalar(connection, f"SELECT count(DISTINCT id) FROM {classified}")
        ),
        "distinct_dc_count": int(
            scalar(connection, f"SELECT count(DISTINCT origin_dc) FROM {classified}")
        ),
        "job_gpu_hours": float(
            scalar(connection, f"SELECT sum(gpu_hours) FROM {classified}")
        ),
        "exact_sparse_gpu_hours": float(
            scalar(
                connection,
                f"SELECT sum(total_avg_gpus) * {interval_hours} FROM {sparse}",
            )
        ),
        "exact_dense_gpu_hours": float(
            scalar(
                connection,
                f"SELECT sum(total_avg_gpus) * {interval_hours} FROM {dense}",
            )
        ),
        "negative_profile_rows": int(
            scalar(
                connection,
                f"""SELECT count(*) FROM {dense}
                WHERE total_avg_gpus < -1e-9
                   OR total_gpu_seconds < -1e-9
                   OR active_job_equivalents < -1e-9""",
            )
        ),
        "utc_offset_nonzero_rows": int(
            scalar(
                connection,
                f"""SELECT count(*) FROM {dense}
                WHERE date_part('timezone', timestamp_utc) <> 0""",
            )
        ),
    }

    case_metrics = {}
    identity_failures = 0
    nesting_failures = 0
    cases = ctx.config["flexibility_cases"]

    for case in cases:
        identifier = case_id(case)
        flex_job_gpu_hours = float(
            scalar(
                connection,
                f"""SELECT sum(CASE WHEN is_flexible_{identifier}
                    THEN gpu_hours ELSE 0.0 END) FROM {classified}""",
            )
        )
        flex_profile_gpu_hours = float(
            scalar(
                connection,
                f"""SELECT sum(flexible_avg_gpus_{identifier})
                    * {interval_hours} FROM {dense}""",
            )
        )
        fixed_profile_gpu_hours = float(
            scalar(
                connection,
                f"""SELECT sum(fixed_avg_gpus_{identifier})
                    * {interval_hours} FROM {dense}""",
            )
        )

        case_metrics[identifier] = {
            "flexible_jobs": int(
                scalar(
                    connection,
                    f"SELECT count_if(is_flexible_{identifier}) FROM {classified}",
                )
            ),
            "flexible_gpu_hours": flex_job_gpu_hours,
            "profile_flexible_gpu_hours": flex_profile_gpu_hours,
            "profile_fixed_gpu_hours": fixed_profile_gpu_hours,
        }

        identity_failures += int(
            scalar(
                connection,
                f"""SELECT count(*) FROM {dense}
                WHERE abs(
                    total_avg_gpus
                    - flexible_avg_gpus_{identifier}
                    - fixed_avg_gpus_{identifier}
                ) > 1e-8""",
            )
        )

    for previous, current in zip(cases, cases[1:]):
        previous_id = case_id(previous)
        current_id = case_id(current)

        nesting_failures += int(
            scalar(
                connection,
                f"""SELECT count(*) FROM {classified}
                WHERE is_flexible_{current_id}
                  AND NOT is_flexible_{previous_id}""",
            )
        )
        nesting_failures += int(
            scalar(
                connection,
                f"""SELECT count(*) FROM {dense}
                WHERE flexible_avg_gpus_{current_id}
                    > flexible_avg_gpus_{previous_id} + 1e-9""",
            )
        )

    metrics["profile_identity_failures"] = identity_failures
    metrics["flex_nesting_failures"] = nesting_failures

    def close_enough(left: float, right: float) -> bool:
        return abs(left - right) <= max(
            abs_tol,
            rel_tol * max(1.0, abs(left), abs(right)),
        )

    checks = {
        "unique_job_rows": (
            metrics["classified_job_rows"] == metrics["distinct_job_count"]
        ),
        "twelve_dc_present": metrics["distinct_dc_count"] == 12,
        "sparse_gpu_hour_conservation": close_enough(
            metrics["job_gpu_hours"], metrics["exact_sparse_gpu_hours"]
        ),
        "dense_gpu_hour_conservation": close_enough(
            metrics["job_gpu_hours"], metrics["exact_dense_gpu_hours"]
        ),
        "nonnegative_exact_profile": metrics["negative_profile_rows"] == 0,
        "utc_output_normalised": metrics["utc_offset_nonzero_rows"] == 0,
        "fixed_plus_flexible_equals_total": identity_failures == 0,
        "flexibility_cases_are_nested": nesting_failures == 0,
    }

    for identifier, values in case_metrics.items():
        checks[f"{identifier}_flex_gpu_hour_conservation"] = close_enough(
            values["flexible_gpu_hours"],
            values["profile_flexible_gpu_hours"],
        )
        checks[f"{identifier}_fixed_gpu_hour_conservation"] = close_enough(
            metrics["job_gpu_hours"] - values["flexible_gpu_hours"],
            values["profile_fixed_gpu_hours"],
        )

    result = {
        "status": "success" if all(checks.values()) else "failed",
        "metrics": metrics,
        "case_metrics": case_metrics,
        "checks": checks,
    }
    write_json(ctx.report_dir / "validation.json", result)
    connection.close()

    if result["status"] != "success":
        failed = [key for key, value in checks.items() if not value]
        raise RuntimeError(f"Stage K3.5 검증 실패: {failed}")

    logger.info(
        "Stage K3.5 검증 성공: exact GPU-hour %.3f",
        metrics["exact_dense_gpu_hours"],
    )
