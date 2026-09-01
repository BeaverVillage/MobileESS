"""Causal realization probability for jobs pending at forecast cutoff."""

from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, brier_score_loss, log_loss

from dayahead.ml.c_mass_tpp.data import AEST
from dayahead.ml.safe_flex.observable_share import service_overlap_GPU_h
from dayahead.ml.safe_flex.state_reconstruction import cutoff_for_day


PENDING_FEATURES = [
    "log_gpus", "log_nodes", "log_wallclock_h", "request_full", "pending_age_h",
    "dow_sin", "dow_cos", "partition_code", "qos_code",
]


def build_pending_examples(events: pd.DataFrame, start: str, end_inclusive: str) -> pd.DataFrame:
    """Build pending snapshots; future events form labels only, never features."""

    rows = []
    partitions = {v: i for i, v in enumerate(sorted(events.partition.astype(str).unique()))}
    qos = {v: i for i, v in enumerate(sorted(events.qos.astype(str).unique()))}
    for day in pd.date_range(start, end_inclusive, freq="D"):
        cutoff = cutoff_for_day(day)
        pending = events.loc[events.submit_time.le(cutoff) & (events.start_time.isna() | events.start_time.gt(cutoff))].copy()
        if pending.empty:
            continue
        age = (cutoff - pending.submit_time).dt.total_seconds() / 3600.0
        realized = pending.start_time.notna() & pending.end_time.notna() & pending.end_time.gt(pending.start_time)
        duration = ((pending.end_time - pending.start_time).dt.total_seconds() / 3600.0).where(realized, 0.0)
        overlap = service_overlap_GPU_h(pending, day)
        frame = pd.DataFrame({
            "job_id": pending.id.astype(str).to_numpy(), "target_day": day.strftime("%Y-%m-%d"),
            "log_gpus": np.log1p(pending.gpus_requested.to_numpy(float)),
            "log_nodes": np.log1p(pending.nodes_req.to_numpy(float)),
            "log_wallclock_h": np.log1p(pending.wallclock_req_h.to_numpy(float)),
            "request_full": pending.request_full.to_numpy(float), "pending_age_h": age.to_numpy(float),
            "dow_sin": np.sin(2 * np.pi * day.dayofweek / 7.0), "dow_cos": np.cos(2 * np.pi * day.dayofweek / 7.0),
            "partition_code": pending.partition.astype(str).map(partitions).to_numpy(float),
            "qos_code": pending.qos.astype(str).map(qos).to_numpy(float),
            "realized_service": realized.to_numpy(int),
            "service_total_GPU_h": (pending.gpus_requested * duration).fillna(0).to_numpy(float),
            "service_Dday_GPU_h": overlap,
            "gpus_requested": pending.gpus_requested.to_numpy(float),
            "wallclock_req_h": pending.wallclock_req_h.to_numpy(float),
        })
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def fit_realization(train: pd.DataFrame, seed: int) -> lgb.LGBMClassifier:
    """Fit calibrated-capable LightGBM Bernoulli realization model."""

    return lgb.LGBMClassifier(
        objective="binary", n_estimators=140, learning_rate=0.035, num_leaves=20,
        min_child_samples=60, reg_lambda=1.0, verbosity=-1, random_state=seed, n_jobs=-1,
    ).fit(train[PENDING_FEATURES], train.realized_service)


def realization_metrics(y: np.ndarray, probability: np.ndarray, baseline_rate: float) -> dict[str, float]:
    """Return AUPRC, Brier skill, log loss, and calibration error."""

    p = np.clip(probability, 1e-6, 1 - 1e-6)
    brier = brier_score_loss(y, p)
    baseline_brier = brier_score_loss(y, np.full(len(y), baseline_rate))
    bins = pd.qcut(p, q=min(10, max(2, len(np.unique(p)))), duplicates="drop")
    table = pd.DataFrame({"y": y, "p": p, "bin": bins}).groupby("bin", observed=True).agg(y=("y", "mean"), p=("p", "mean"), n=("y", "size"))
    ece = float(np.average(np.abs(table.y - table.p), weights=table.n))
    skill = float(1 - brier / baseline_brier) if baseline_brier > 1e-12 else float("nan")
    return {
        "AUPRC": float(average_precision_score(y, p)), "Brier": float(brier),
        "baseline_Brier": float(baseline_brier), "Brier_skill": skill,
        "log_loss": float(log_loss(y, p, labels=[0, 1])), "ECE_10bin": ece,
        "positive_labels": int(np.sum(y == 1)), "negative_labels": int(np.sum(y == 0)),
    }
