"""Decompose realized flexible-service overlap into causal K/G/N cohorts."""

from __future__ import annotations

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import AEST
from dayahead.ml.safe_flex.state_reconstruction import cutoff_for_day


SHARE_COLUMNS = (
    "rho_K_total",
    "rho_K_schedulable",
    "rho_G",
    "rho_N",
)


def service_overlap_GPU_h(jobs: pd.DataFrame, day: pd.Timestamp | str) -> np.ndarray:
    """Return realized service overlap in GPU-hours for each job.

    Actual START/END values are used only as post-hoc labels. They are not
    causal forecast features. Source authority is completed Kestrel accounting.
    """

    start = pd.Timestamp(day)
    if start.tzinfo is None:
        start = start.tz_localize(AEST)
    else:
        start = start.tz_convert(AEST)
    start = start.normalize()
    end = start + pd.Timedelta(days=1)
    overlap_start = jobs["start_time"].where(jobs["start_time"].ge(start), start)
    overlap_end = jobs["end_time"].where(jobs["end_time"].le(end), end)
    hours = (overlap_end - overlap_start).dt.total_seconds().clip(lower=0) / 3600.0
    return jobs["gpus_requested"].to_numpy(float) * hours.to_numpy(float)


def observable_share_by_day(jobs: pd.DataFrame, start: str, end_inclusive: str) -> pd.DataFrame:
    """Compute K/G/N realized-service shares for every target day.

    K is submitted by cutoff, G in the six-hour cutoff gap, and N during
    D-day. K-pending is schedulable-known; K-running is locked in the primary
    policy. Units are GPU-hours and dimensionless shares.
    """

    rows: list[dict[str, object]] = []
    for day in pd.date_range(start, end_inclusive, freq="D"):
        day_start = day.tz_localize(AEST)
        day_end = day_start + pd.Timedelta(days=1)
        cutoff = cutoff_for_day(day)
        overlap = service_overlap_GPU_h(jobs, day)
        active = overlap > 0
        submit = jobs["submit_time"]
        k = submit.le(cutoff).to_numpy() & active
        g = submit.gt(cutoff).to_numpy() & submit.lt(day_start).to_numpy() & active
        n = submit.ge(day_start).to_numpy() & submit.lt(day_end).to_numpy() & active
        pending_at_cutoff = jobs["start_time"].gt(cutoff).to_numpy()
        running_at_cutoff = jobs["start_time"].le(cutoff).to_numpy() & jobs["end_time"].gt(cutoff).to_numpy()
        h_k = float(overlap[k].sum())
        h_k_pending = float(overlap[k & pending_at_cutoff].sum())
        h_k_running = float(overlap[k & running_at_cutoff].sum())
        h_g = float(overlap[g].sum())
        h_n = float(overlap[n].sum())
        total = h_k + h_g + h_n
        rows.append(
            {
                "target_day": day.strftime("%Y-%m-%d"),
                "cutoff_AEST": cutoff.isoformat(),
                "H_K_total_GPU_h": h_k,
                "H_K_pending_GPU_h": h_k_pending,
                "H_K_running_locked_GPU_h": h_k_running,
                "H_G_GPU_h": h_g,
                "H_N_GPU_h": h_n,
                "H_total_GPU_h": total,
                "mass_identity_error_GPU_h": total - float(overlap[k | g | n].sum()),
                "rho_K_total": h_k / total if total > 0 else np.nan,
                "rho_K_schedulable": h_k_pending / total if total > 0 else np.nan,
                "rho_G": h_g / total if total > 0 else np.nan,
                "rho_N": h_n / total if total > 0 else np.nan,
                "active_flexible_jobs": int((k | g | n).sum()),
                "K_pending_jobs": int((k & pending_at_cutoff).sum()),
                "K_running_locked_jobs": int((k & running_at_cutoff).sum()),
            }
        )
    return pd.DataFrame(rows)


def summarize_shares(by_day: pd.DataFrame) -> dict[str, object]:
    """Summarize daily and mass-weighted K/G/N shares."""

    metrics: dict[str, object] = {}
    mapping = {
        "rho_K_total": "H_K_total_GPU_h",
        "rho_K_schedulable": "H_K_pending_GPU_h",
        "rho_G": "H_G_GPU_h",
        "rho_N": "H_N_GPU_h",
    }
    total = float(by_day["H_total_GPU_h"].sum())
    for share, mass in mapping.items():
        series = by_day[share].dropna()
        metrics[share] = {
            "mean": float(series.mean()),
            "P05": float(series.quantile(0.05)),
            "P25": float(series.quantile(0.25)),
            "P50": float(series.quantile(0.50)),
            "P75": float(series.quantile(0.75)),
            "P95": float(series.quantile(0.95)),
            "mass_weighted_aggregate_share": float(by_day[mass].sum() / total) if total else None,
        }
    return {
        "days": int(len(by_day)),
        "positive_mass_days": int(by_day["H_total_GPU_h"].gt(0).sum()),
        "H_total_GPU_h": total,
        "mass_identity_max_abs_error_GPU_h": float(by_day["mass_identity_error_GPU_h"].abs().max()),
        "shares": metrics,
    }

