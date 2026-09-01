"""Causal discrete-hazard model for running-job residual service."""

from __future__ import annotations

from dataclasses import dataclass

import lightgbm as lgb
import numpy as np
import pandas as pd
from scipy.stats import norm

from dayahead.ml.c_mass_tpp.data import AEST
from dayahead.ml.safe_flex.state_reconstruction import cutoff_for_day


FEATURES = [
    "log_gpus", "log_nodes", "log_wallclock_h", "request_full", "age_h",
    "age_wallclock_ratio", "dow_sin", "dow_cos", "partition_code", "qos_code",
]
HORIZON_SLOTS = 96
SLOT_H = 0.25


@dataclass(frozen=True)
class RunningModels:
    """Fitted SR1 log-runtime quantiles and SR2 proper discrete hazard."""

    sr1_q50: lgb.LGBMRegressor
    sr1_q90: lgb.LGBMRegressor
    sr1_log_sigma: float
    hazard: lgb.LGBMClassifier


def build_running_examples(events: pd.DataFrame, start: str, end_inclusive: str) -> pd.DataFrame:
    """Create running-state snapshots with right-censored 24-hour labels.

    Features use only events observed by cutoff. Actual END is consulted only
    to form a post-cutoff training label. Runtime units are hours.
    """

    rows: list[pd.DataFrame] = []
    partition_codes = {value: index for index, value in enumerate(sorted(events.partition.astype(str).unique()))}
    qos_codes = {value: index for index, value in enumerate(sorted(events.qos.astype(str).unique()))}
    for day in pd.date_range(start, end_inclusive, freq="D"):
        cutoff = cutoff_for_day(day)
        running = events.loc[
            events.submit_time.le(cutoff)
            & events.start_time.notna()
            & events.start_time.le(cutoff)
            & (events.end_time.isna() | events.end_time.gt(cutoff))
        ].copy()
        if running.empty:
            continue
        age = (cutoff - running.start_time).dt.total_seconds() / 3600.0
        raw_remaining = (running.end_time - cutoff).dt.total_seconds() / 3600.0
        observed = running.end_time.notna() & raw_remaining.le(HORIZON_SLOTS * SLOT_H)
        remaining = raw_remaining.where(running.end_time.notna(), HORIZON_SLOTS * SLOT_H).clip(lower=0.0, upper=HORIZON_SLOTS * SLOT_H)
        dow = day.dayofweek
        frame = pd.DataFrame(
            {
                "job_id": running.id.astype(str).to_numpy(),
                "target_day": day.strftime("%Y-%m-%d"),
                "log_gpus": np.log1p(running.gpus_requested.to_numpy(float)),
                "log_nodes": np.log1p(running.nodes_req.to_numpy(float)),
                "log_wallclock_h": np.log1p(running.wallclock_req_h.to_numpy(float)),
                "request_full": running.request_full.to_numpy(float),
                "age_h": age.to_numpy(float),
                "age_wallclock_ratio": (age / running.wallclock_req_h.clip(lower=0.25)).clip(upper=4).to_numpy(float),
                "dow_sin": np.sin(2 * np.pi * dow / 7.0),
                "dow_cos": np.cos(2 * np.pi * dow / 7.0),
                "partition_code": running.partition.astype(str).map(partition_codes).to_numpy(float),
                "qos_code": running.qos.astype(str).map(qos_codes).to_numpy(float),
                "remaining_h": remaining.to_numpy(float),
                "event_observed_24h": observed.to_numpy(bool),
                "requested_residual_h": (running.wallclock_req_h - age).clip(lower=0.0, upper=24.0).to_numpy(float),
            }
        )
        rows.append(frame)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _hazard_rows(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    base = frame[FEATURES].to_numpy(np.float32)
    durations = np.maximum(1, np.ceil(frame.remaining_h.to_numpy(float) / SLOT_H).astype(int)).clip(max=HORIZON_SLOTS)
    observed = frame.event_observed_24h.to_numpy(bool)
    counts = durations
    repeated = np.repeat(base, counts, axis=0)
    slot = np.concatenate([np.arange(1, count + 1) for count in counts]).astype(np.float32)
    time_features = np.column_stack((slot / HORIZON_SLOTS, np.log1p(slot)))
    labels = np.zeros(len(slot), dtype=np.int8)
    offsets = np.cumsum(counts) - 1
    labels[offsets[observed]] = 1
    return np.column_stack((repeated, time_features)), labels


def fit_running_models(train: pd.DataFrame, seed: int = 20260901) -> RunningModels:
    """Fit SR1 quantile baselines and SR2 proper discrete-time likelihood."""

    observed = train.loc[train.event_observed_24h].copy()
    common = dict(n_estimators=120, learning_rate=0.04, num_leaves=24, min_child_samples=40, verbosity=-1, random_state=seed, n_jobs=-1)
    q50 = lgb.LGBMRegressor(objective="quantile", alpha=0.5, **common).fit(observed[FEATURES], np.log1p(observed.remaining_h))
    q90 = lgb.LGBMRegressor(objective="quantile", alpha=0.9, **common).fit(observed[FEATURES], np.log1p(observed.remaining_h))
    residual = np.log1p(observed.remaining_h.to_numpy(float)) - q50.predict(observed[FEATURES])
    sigma = float(max(np.std(residual), 0.15))
    hx, hy = _hazard_rows(train)
    hazard = lgb.LGBMClassifier(
        objective="binary", n_estimators=100, learning_rate=0.04, num_leaves=20,
        min_child_samples=100, subsample=0.8, colsample_bytree=0.9,
        verbosity=-1, random_state=seed, n_jobs=-1,
    ).fit(hx, hy)
    return RunningModels(q50, q90, sigma, hazard)


def predict_running(models: RunningModels, frame: pd.DataFrame) -> dict[str, np.ndarray]:
    """Predict monotone conditional survival and residual duration quantiles."""

    x = frame[FEATURES]
    sr1_mu = models.sr1_q50.predict(x)
    sr1_q50 = np.expm1(sr1_mu).clip(0, 24)
    sr1_q90 = np.expm1(models.sr1_q90.predict(x)).clip(0, 24)
    grid_h = np.arange(1, HORIZON_SLOTS + 1) * SLOT_H
    z = (np.log1p(grid_h)[None, :] - sr1_mu[:, None]) / models.sr1_log_sigma
    sr1_survival = 1.0 - norm.cdf(z)

    base = frame[FEATURES].to_numpy(np.float32)
    expanded = np.repeat(base, HORIZON_SLOTS, axis=0)
    slot = np.tile(np.arange(1, HORIZON_SLOTS + 1), len(frame)).astype(np.float32)
    hx = np.column_stack((expanded, slot / HORIZON_SLOTS, np.log1p(slot)))
    hazards = models.hazard.predict_proba(hx)[:, 1].reshape(len(frame), HORIZON_SLOTS)
    hazards = np.clip(hazards, 1e-6, 1 - 1e-6)
    survival = np.cumprod(1.0 - hazards, axis=1)
    mean = SLOT_H * survival.sum(axis=1)
    cdf = 1.0 - survival
    q10 = SLOT_H * (np.argmax(cdf >= 0.1, axis=1) + 1)
    q50 = SLOT_H * (np.argmax(cdf >= 0.5, axis=1) + 1)
    q90_hit = cdf >= 0.9
    q90 = SLOT_H * (np.argmax(q90_hit, axis=1) + 1)
    q90[~q90_hit.any(axis=1)] = 24.0
    return {
        "SR1_survival": sr1_survival, "SR1_Q50_h": sr1_q50, "SR1_Q90_h": sr1_q90,
        "SAFE_survival": survival, "SAFE_mean_h": mean, "SAFE_Q10_h": q10,
        "SAFE_Q50_h": q50, "SAFE_Q90_h": q90,
    }


def survival_metrics(frame: pd.DataFrame, predictions: dict[str, np.ndarray]) -> dict[str, float]:
    """Return proper horizon Brier/NLL and residual-time accuracy metrics."""

    y_h = frame.remaining_h.to_numpy(float)
    event = frame.event_observed_24h.to_numpy(bool)
    grid_h = np.arange(1, HORIZON_SLOTS + 1) * SLOT_H
    alive = y_h[:, None] > grid_h[None, :]
    rows: dict[str, float] = {}
    for name in ("SR1", "SAFE"):
        survival = np.clip(predictions[f"{name}_survival"], 1e-6, 1 - 1e-6)
        rows[f"{name}_integrated_Brier"] = float(np.mean((survival - alive) ** 2))
        event_slot = np.maximum(1, np.ceil(y_h / SLOT_H).astype(int)).clip(max=HORIZON_SLOTS) - 1
        previous = np.where(event_slot > 0, survival[np.arange(len(frame)), np.maximum(event_slot - 1, 0)], 1.0)
        event_probability = previous - survival[np.arange(len(frame)), event_slot]
        censor_probability = survival[np.arange(len(frame)), -1]
        likelihood = np.where(event, event_probability, censor_probability)
        rows[f"{name}_NLL"] = float(-np.log(np.clip(likelihood, 1e-9, 1.0)).mean())
    rows.update(
        {
            "SR0_MAE_h": float(np.mean(np.abs(frame.requested_residual_h - y_h))),
            "SR1_Q50_MAE_h": float(np.mean(np.abs(predictions["SR1_Q50_h"] - y_h))),
            "SAFE_Q50_MAE_h": float(np.mean(np.abs(predictions["SAFE_Q50_h"] - y_h))),
            "SR1_Q90_coverage": float(np.mean(y_h <= predictions["SR1_Q90_h"])),
            "SAFE_Q90_coverage": float(np.mean(y_h <= predictions["SAFE_Q90_h"])),
            "survival_monotonicity_violations": int(np.sum(np.diff(predictions["SAFE_survival"], axis=1) > 1e-12)),
        }
    )
    return rows

