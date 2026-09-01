"""Exact R_ALL × PI_F × KAPPA_F target factorization in GPU-h units."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DailyFactorTarget:
    """One daily physical factor target; masses are GPU-h-requested or GPU-h-actual."""

    date: str
    R_ALL_GPU_h_requested: float
    R_F_GPU_h_requested: float
    PI_F: float
    KAPPA_DEFINED: bool
    KAPPA_F: float | None
    H_F_GPU_h_actual: float
    identity_error_GPU_h: float
    all_job_count: int
    flexible_job_count: int


def build_daily_factor_targets(
    target_window_events: pd.DataFrame,
    flexible_targets: pd.DataFrame,
    dates: list[str],
) -> list[DailyFactorTarget]:
    """Build exact daily factors without clipping or undefined-KAPPA imputation."""

    all_jobs = target_window_events.copy()
    all_jobs["target_day"] = all_jobs.submit_AEST.dt.strftime("%Y-%m-%d")
    all_jobs["requested_GPU_h"] = all_jobs.requested_service_proxy_GPU_h.astype(float)
    flex = flexible_targets.copy()
    flex["requested_GPU_h"] = (
        flex.gpus_requested.astype(float) * flex.wallclock_req_h.astype(float)
    )
    all_group = all_jobs.groupby("target_day").agg(
        R_ALL=("requested_GPU_h", "sum"), all_jobs=("id", "count")
    )
    flex_group = flex.groupby("target_day").agg(
        R_F=("requested_GPU_h", "sum"),
        H_F=("service_GPU_h", "sum"),
        flexible_jobs=("id", "count"),
    )
    result: list[DailyFactorTarget] = []
    for date in dates:
        r_all = float(all_group.loc[date, "R_ALL"]) if date in all_group.index else 0.0
        r_f = float(flex_group.loc[date, "R_F"]) if date in flex_group.index else 0.0
        h_f = float(flex_group.loc[date, "H_F"]) if date in flex_group.index else 0.0
        all_count = int(all_group.loc[date, "all_jobs"]) if date in all_group.index else 0
        flex_count = (
            int(flex_group.loc[date, "flexible_jobs"])
            if date in flex_group.index
            else 0
        )
        if r_all <= 0.0:
            if r_f > 0.0 or h_f > 0.0:
                raise RuntimeError(f"V24M_ZERO_ALL_WITH_FLEX:{date}")
            pi_f = 0.0
        else:
            pi_f = r_f / r_all
        if pi_f < -1e-15 or pi_f > 1.0 + 1e-12:
            raise RuntimeError(f"V24M_PI_SUPPORT:{date}:{pi_f}")
        kappa_defined = r_f > 0.0
        kappa = h_f / r_f if kappa_defined else None
        reconstructed = r_all * pi_f * kappa if kappa_defined else 0.0
        error = abs(reconstructed - h_f)
        if error > 1e-9:
            raise RuntimeError(f"FAIL_FACTORIZED_TARGET_IDENTITY:{date}:{error}")
        result.append(
            DailyFactorTarget(
                date=date,
                R_ALL_GPU_h_requested=r_all,
                R_F_GPU_h_requested=r_f,
                PI_F=float(np.clip(pi_f, 0.0, 1.0)),
                KAPPA_DEFINED=kappa_defined,
                KAPPA_F=float(kappa) if kappa_defined else None,
                H_F_GPU_h_actual=h_f,
                identity_error_GPU_h=error,
                all_job_count=all_count,
                flexible_job_count=flex_count,
            )
        )
    return result


def factor_targets_frame(targets: list[DailyFactorTarget]) -> pd.DataFrame:
    """Convert factor records to a stable tabular representation."""

    return pd.DataFrame([asdict(target) for target in targets])
