"""Causal 168-hour request-pressure paths and explicit pressure summaries."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .data import production_cutoff


PATH_CHANNELS = (
    "submitted_H100_job_count", "requested_GPU_sum", "requested_GPU_h_sum",
    "requested_node_sum", "FULL_node_requested_GPU_h", "PARTIAL_node_requested_GPU_h",
    "long_walltime_requested_GPU_h", "large_job_requested_GPU_h",
    "unique_account_count", "account_HHI", "median_interarrival_minutes",
    "P10_interarrival_minutes",
)
EXPLICIT_FEATURES = (
    "A6", "A24", "ArrivalCompression", "TailPressure6h", "TailPressure24h",
    "LongWalltimeShare6h", "MultiNodeShare6h", "FullNodeShare6h",
    "UniqueAccountAcceleration", "DeltaHHI", "GPU_P90_shift",
    "walltime_P90_shift", "one_sided_EWMA_workload_z", "one_sided_CUSUM_pressure",
)


@dataclass(frozen=True)
class PressureFitter:
    """Outer-training-only thresholds and robust path normalization statistics."""

    large_job_GPU_h_threshold: float
    long_walltime_h_threshold: float
    requested_GPU_P90: float
    walltime_P90_h: float
    path_log_median: np.ndarray
    path_log_IQR: np.ndarray
    hourly_GPU_h_median: float
    hourly_GPU_h_IQR: float
    fit_date_min: str
    fit_date_max: str


def _hhi(frame: pd.DataFrame) -> float:
    """Return request-mass HHI without exposing account identity to a model."""

    if frame.empty:
        return 0.0
    mass = frame.groupby("account_hash").requested_service_proxy_GPU_h.sum().to_numpy(float)
    total = mass.sum()
    return float(np.square(mass / total).sum()) if total > 0 else 0.0


def _interval_minutes(times: pd.Series) -> np.ndarray:
    values = times.sort_values().astype("int64").to_numpy()
    if len(values) < 2:
        return np.zeros(0, dtype=float)
    return np.diff(values) / 60e9


def _raw_paths(events: pd.DataFrame, dates: list[str], large: float, long: float) -> np.ndarray:
    output = np.zeros((len(dates), 168, len(PATH_CHANNELS)), dtype=np.float64)
    for day_index, date in enumerate(dates):
        cutoff = production_cutoff(date)
        lower = cutoff - pd.Timedelta(hours=168)
        part = events.loc[events.submit_AEST.ge(lower) & events.submit_AEST.lt(cutoff)].copy()
        if part.empty:
            continue
        part["hour_bin"] = ((part.submit_AEST - lower).dt.total_seconds() // 3600).astype(int)
        mass = part.requested_service_proxy_GPU_h.to_numpy(float)
        part["full_mass"] = np.where(part.request_full.eq(1.0), mass, 0.0)
        part["partial_mass"] = np.where(part.request_full.eq(0.0), mass, 0.0)
        part["long_mass"] = np.where(part.wallclock_req_h.ge(long), mass, 0.0)
        part["large_mass"] = np.where(part.requested_service_proxy_GPU_h.ge(large), mass, 0.0)
        for hour, group in part.groupby("hour_bin"):
            hour = int(hour)
            if not 0 <= hour < 168:
                continue
            intervals = _interval_minutes(group.submit_AEST)
            output[day_index, hour] = (
                len(group), group.gpus_requested.sum(), group.requested_service_proxy_GPU_h.sum(),
                group.nodes_req.sum(), group.full_mass.sum(), group.partial_mass.sum(),
                group.long_mass.sum(), group.large_mass.sum(), group.account_hash.nunique(),
                _hhi(group), np.median(intervals) if len(intervals) else 0.0,
                np.quantile(intervals, 0.10) if len(intervals) else 0.0,
            )
    return output


def fit_pressure_fitter(events: pd.DataFrame, train_dates: list[str]) -> PressureFitter:
    """Fit every threshold and normalizer using only causal outer-training events."""

    if not train_dates:
        raise ValueError("V25M_EMPTY_PRESSURE_FIT_DATES")
    maximum_cutoff = production_cutoff(max(train_dates))
    minimum_cutoff = production_cutoff(min(train_dates)) - pd.Timedelta(days=28)
    fit_events = events.loc[
        events.submit_AEST.ge(minimum_cutoff) & events.submit_AEST.lt(maximum_cutoff)
    ]
    requested_mass = fit_events.requested_service_proxy_GPU_h.to_numpy(float)
    walltime = fit_events.wallclock_req_h.to_numpy(float)
    large = float(np.quantile(requested_mass, 0.90))
    long = float(np.quantile(walltime, 0.90))
    paths = _raw_paths(events, train_dates, large, long)
    transformed = np.log1p(paths).reshape(-1, len(PATH_CHANNELS))
    median = np.median(transformed, axis=0)
    iqr = np.maximum(np.quantile(transformed, .75, axis=0) - np.quantile(transformed, .25, axis=0), 1e-6)
    hourly = paths[:, :, 2].reshape(-1)
    hourly_iqr = max(float(np.quantile(hourly, .75) - np.quantile(hourly, .25)), 1e-6)
    return PressureFitter(
        large, long, float(np.quantile(fit_events.gpus_requested, .90)),
        float(np.quantile(walltime, .90)), median, iqr, float(np.median(hourly)),
        hourly_iqr, min(train_dates), max(train_dates),
    )


def build_pressure_paths(events: pd.DataFrame, dates: list[str], fitter: PressureFitter) -> tuple[np.ndarray, np.ndarray]:
    """Return raw and training-normalized causal paths with shape ``[N,168,12]``."""

    raw = _raw_paths(events, dates, fitter.large_job_GPU_h_threshold, fitter.long_walltime_h_threshold)
    normalized = (np.log1p(raw) - fitter.path_log_median) / fitter.path_log_IQR
    return raw, normalized


def _weighted_hhi_slice(path: np.ndarray) -> float:
    weights = path[:, 2]
    return float(np.average(path[:, 9], weights=weights)) if weights.sum() > 0 else 0.0


def explicit_pressure_features(raw: np.ndarray, fitter: PressureFitter) -> np.ndarray:
    """Compute the preregistered 14 request-pressure statistics from causal paths."""

    eps = 1e-9
    rows = []
    for path in raw:
        r6, prev6 = path[-6:, 2].sum(), path[-12:-6, 2].sum()
        r24, prev24 = path[-24:, 2].sum(), path[-48:-24, 2].sum()
        inter7 = path[:, 10][path[:, 10] > 0]
        inter6 = path[-6:, 10][path[-6:, 10] > 0]
        accounts6, accounts_prev = path[-6:, 8].sum(), path[-12:-6, 8].sum()
        recent_gpu = path[-6:, 1]
        past_gpu = path[:-6, 1]
        recent_wall = path[-6:, 6]
        past_wall = path[:-6, 6]
        z = (path[:, 2] - fitter.hourly_GPU_h_median) / fitter.hourly_GPU_h_IQR
        alpha = 2.0 / (24.0 + 1.0)
        ewma = 0.0
        cusum = 0.0
        for value in z:
            ewma = max(0.0, alpha * value + (1.0 - alpha) * ewma)
            cusum = max(0.0, cusum + value - 0.5)
        rows.append((
            (r6 - prev6) / (prev6 + eps), (r24 - prev24) / (prev24 + eps),
            (np.median(inter7) if len(inter7) else 0.0) / ((np.median(inter6) if len(inter6) else 0.0) + eps),
            path[-6:, 7].sum() / (r6 + eps), path[-24:, 7].sum() / (r24 + eps),
            path[-6:, 6].sum() / (r6 + eps),
            path[-6:, 2][path[-6:, 3] > path[-6:, 0]].sum() / (r6 + eps),
            path[-6:, 4].sum() / (r6 + eps),
            (accounts6 - accounts_prev) / (accounts_prev + eps),
            _weighted_hhi_slice(path[-6:]) - _weighted_hhi_slice(path),
            (np.quantile(recent_gpu, .90) if len(recent_gpu) else 0.0) - (np.quantile(past_gpu, .90) if len(past_gpu) else 0.0),
            (np.quantile(recent_wall, .90) if len(recent_wall) else 0.0) - (np.quantile(past_wall, .90) if len(past_wall) else 0.0),
            ewma, cusum,
        ))
    return np.nan_to_num(np.asarray(rows, float), nan=0.0, posinf=1e6, neginf=-1e6)

