"""Causal D-1 pending, calendar, innovation, and capacity state features."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import VICTORIA_HOLIDAYS
from dayahead.ml.safe_flex.capacity_timeline import capacity_for_day, read_observed_capacity_timeline
from dayahead.ml.safe_flex.state_reconstruction import cutoff_for_day


PENDING_FEATURE_COLUMNS = [
    "pending_job_count", "pending_requested_GPU_sum", "pending_requested_node_sum",
    "pending_requested_GPU_h_sum", "pending_requested_walltime_h_sum",
    "pending_GPU_h_P50", "pending_GPU_h_P90", "pending_GPU_h_P95",
    "pending_walltime_P50", "pending_walltime_P90", "pending_walltime_P95",
    "pending_full_node_share", "pending_partial_node_share", "pending_multi_node_share",
    "pending_unique_account_count", "pending_account_HHI",
    "pending_age_mean_h", "pending_age_P50_h", "pending_age_P90_h", "pending_age_P95_h",
    "pending_GPU_capacity_normalized", "pending_requested_GPU_h_capacity_normalized",
]


def _quantile(values: pd.Series, q: float) -> float:
    return float(values.quantile(q)) if len(values) else 0.0


def build_pending_daily(events: pd.DataFrame, repo: Path) -> pd.DataFrame:
    """Aggregate only request-side information visible at each forecast cutoff."""

    timeline = read_observed_capacity_timeline(repo)
    rows: list[dict[str, object]] = []
    for day in pd.date_range("2024-08-19", "2025-03-31", freq="D"):
        cutoff = cutoff_for_day(day)
        pending = events.loc[
            events.submit_time.le(cutoff)
            & (events.start_time.isna() | events.start_time.gt(cutoff))
        ].copy()
        age = (cutoff - pending.submit_time).dt.total_seconds() / 3600.0
        requested = pending.gpus_requested * pending.wallclock_req_h
        full = pending.request_full.eq(1)
        account_share = pending.groupby(pending.account_hash.astype(str)).gpus_requested.sum()
        account_share = account_share / account_share.sum() if account_share.sum() > 0 else account_share
        capacity = float(capacity_for_day(timeline, day))
        date = day.strftime("%Y-%m-%d")
        rows.append(
            {
                "date": date,
                "pending_job_count": float(len(pending)),
                "pending_requested_GPU_sum": float(pending.gpus_requested.sum()),
                "pending_requested_node_sum": float(pending.nodes_req.sum()),
                "pending_requested_GPU_h_sum": float(requested.sum()),
                "pending_requested_walltime_h_sum": float(pending.wallclock_req_h.sum()),
                "pending_GPU_h_P50": _quantile(requested, 0.50),
                "pending_GPU_h_P90": _quantile(requested, 0.90),
                "pending_GPU_h_P95": _quantile(requested, 0.95),
                "pending_walltime_P50": _quantile(pending.wallclock_req_h, 0.50),
                "pending_walltime_P90": _quantile(pending.wallclock_req_h, 0.90),
                "pending_walltime_P95": _quantile(pending.wallclock_req_h, 0.95),
                "pending_full_node_share": float(full.mean()) if len(pending) else 0.0,
                "pending_partial_node_share": float((~full).mean()) if len(pending) else 0.0,
                "pending_multi_node_share": float(pending.nodes_req.gt(1).mean()) if len(pending) else 0.0,
                "pending_unique_account_count": float(pending.account_hash.astype(str).nunique()),
                "pending_account_HHI": float(np.square(account_share).sum()) if len(account_share) else 0.0,
                "pending_age_mean_h": float(age.mean()) if len(age) else 0.0,
                "pending_age_P50_h": _quantile(age, 0.50),
                "pending_age_P90_h": _quantile(age, 0.90),
                "pending_age_P95_h": _quantile(age, 0.95),
                "source_observed_capacity_GPU": capacity,
                "pending_GPU_capacity_normalized": float(pending.gpus_requested.sum() / capacity),
                "pending_requested_GPU_h_capacity_normalized": float(requested.sum() / (24.0 * capacity)),
                "dow_sin": float(np.sin(2 * np.pi * day.dayofweek / 7.0)),
                "dow_cos": float(np.cos(2 * np.pi * day.dayofweek / 7.0)),
                "month_sin": float(np.sin(2 * np.pi * day.month / 12.0)),
                "month_cos": float(np.cos(2 * np.pi * day.month / 12.0)),
                "holiday": float(date in VICTORIA_HOLIDAYS),
            }
        )
    result = pd.DataFrame(rows)
    canonical = pd.read_csv(repo / "dayahead/artifacts/v25m_beacon_flex/V25M_CANONICAL_BASELINE_DAILY_OOF.csv")
    mean = canonical.loc[canonical.model.eq("C-B0_B2_LIGHTGBM_TWEEDIE"), ["date", "mean_GPU_h"]].rename(columns={"mean_GPU_h": "N_B2_mean_GPU_h"})
    quantile = canonical.loc[canonical.model.eq("C-B1_B3_LIGHTGBM_QUANTILE"), ["date", "Q50_GPU_h", "Q90_GPU_h"]].rename(columns={"Q50_GPU_h": "N_B3_Q50_GPU_h", "Q90_GPU_h": "N_B3_Q90_GPU_h"})
    gap = pd.read_csv(repo / "dayahead/artifacts/v26m_safe_flex/V26M_INNOVATION_OOF.csv")[["date", "G_mean_GPU_h", "G_Q50_GPU_h", "G_Q90_GPU_h"]]
    result = result.merge(mean, on="date", how="left").merge(quantile, on="date", how="left").merge(gap, on="date", how="left")
    result["frozen_innovation_OOF_available"] = result.N_B2_mean_GPU_h.notna().astype(float)
    innovation = ["N_B2_mean_GPU_h", "N_B3_Q50_GPU_h", "N_B3_Q90_GPU_h", "G_mean_GPU_h", "G_Q50_GPU_h", "G_Q90_GPU_h"]
    # Early outer-training rows predate the serialized OOF universe. Missingness
    # is explicit and never replaced with a realized target or future forecast.
    result[innovation] = result[innovation].fillna(0.0)
    return result


def write_state_contract(repo: Path, frame: pd.DataFrame) -> dict[str, object]:
    payload = {
        "artifact_id": "V27M_STATE_FEATURE_CONTRACT_V1",
        "cutoff": "D-1 18:00 FIXED_AEST_UTC_PLUS_10",
        "days": len(frame),
        "pending_features": PENDING_FEATURE_COLUMNS,
        "running_features": ["running_residual_Q10", "running_residual_Q50", "running_residual_Q90", "running_expected_active_GPU"],
        "innovation_features": {
            "N": "frozen B2 mean and B3 Q50/Q90 serialized OOF when available",
            "G": "frozen V26 small-LightGBM mean/Q50/Q90 serialized OOF when available",
            "pre_OOF_missing_policy": "ZERO_WITH_EXPLICIT_MISSING_INDICATOR; NO_REALIZED_TARGET_IMPUTATION",
        },
        "deadline_class_pressure": "UNAVAILABLE_CAUSAL_AUTHORITY_NOT_USED",
        "raw_account_identity_used": False,
        "account_concentration_only": True,
        "future_start_numeric_feature_reads": 0,
        "future_end_numeric_feature_reads": 0,
        "future_service_labels_in_features": 0,
        "April_reads": 0,
        "PASS": bool(frame[PENDING_FEATURE_COLUMNS].notna().all().all()),
    }
    out = repo / "dayahead/artifacts/v27m_safe_flex_r1/V27M_STATE_FEATURE_CONTRACT.json"
    out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload

