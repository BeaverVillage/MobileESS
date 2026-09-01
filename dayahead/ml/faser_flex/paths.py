"""Causal 168-hour request-event path construction and training-only scaling."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contracts import PATH_HOURS, PATH_LOOKBACK_DAYS
from .predictability_audit import production_cutoff


PATH_CHANNELS = (
    "submitted_H100_job_count",
    "requested_GPU_sum",
    "requested_GPU_h_sum",
    "requested_node_sum",
    "FULL_requested_GPU_h",
    "PARTIAL_requested_GPU_h",
    "long_walltime_requested_GPU_h",
    "unique_account_count",
)


@dataclass(frozen=True)
class PathScaler:
    """Robust log-increment scaler fitted on outer-training paths only."""

    median: np.ndarray
    iqr: np.ndarray
    fit_date_min: str
    fit_date_max: str


def build_hourly_event_paths(events: pd.DataFrame, dates: list[str]) -> np.ndarray:
    """Build nonnegative hourly increments available before each D-1 18:00 cutoff."""

    output = np.zeros((len(dates), PATH_HOURS, len(PATH_CHANNELS)), dtype=np.float64)
    for index, date in enumerate(dates):
        cutoff = production_cutoff(date)
        lower = cutoff - pd.Timedelta(days=PATH_LOOKBACK_DAYS)
        part = events.loc[
            events.submit_AEST.ge(lower) & events.submit_AEST.lt(cutoff)
        ].copy()
        if part.empty:
            continue
        part["hour_bin"] = ((part.submit_AEST - lower).dt.total_seconds() // 3600).astype(int)
        part["full_requested"] = np.where(
            part.request_full.eq(1.0), part.requested_service_proxy_GPU_h, 0.0
        )
        part["partial_requested"] = np.where(
            part.request_full.eq(0.0), part.requested_service_proxy_GPU_h, 0.0
        )
        part["long_requested"] = np.where(
            part.wallclock_req_h.gt(8.0), part.requested_service_proxy_GPU_h, 0.0
        )
        grouped = part.groupby("hour_bin").agg(
            jobs=("id", "count"),
            gpus=("gpus_requested", "sum"),
            gpu_h=("requested_service_proxy_GPU_h", "sum"),
            nodes=("nodes_req", "sum"),
            full_gpu_h=("full_requested", "sum"),
            partial_gpu_h=("partial_requested", "sum"),
            long_gpu_h=("long_requested", "sum"),
            accounts=("account_hash", "nunique"),
        )
        for hour, row in grouped.iterrows():
            if 0 <= int(hour) < PATH_HOURS:
                output[index, int(hour)] = row.to_numpy(float)
    return output


def fit_path_scaler(paths: np.ndarray, dates: list[str]) -> PathScaler:
    """Fit robust channel parameters on outer-training paths only."""

    if paths.ndim != 3 or paths.shape[-1] != len(PATH_CHANNELS):
        raise ValueError("V24M_PATH_SHAPE_INVALID")
    transformed = np.log1p(paths).reshape(-1, paths.shape[-1])
    median = np.median(transformed, axis=0)
    q25 = np.quantile(transformed, 0.25, axis=0)
    q75 = np.quantile(transformed, 0.75, axis=0)
    iqr = np.maximum(q75 - q25, 1e-6)
    return PathScaler(median, iqr, min(dates), max(dates))


def transform_paths(paths: np.ndarray, scaler: PathScaler) -> np.ndarray:
    """Return cumulative time-augmented paths with shape [N,169,9]."""

    increments = (np.log1p(paths) - scaler.median) / scaler.iqr
    cumulative = np.cumsum(increments, axis=1)
    cumulative = np.concatenate(
        [np.zeros((len(paths), 1, paths.shape[-1])), cumulative], axis=1
    )
    time = np.linspace(0.0, 1.0, cumulative.shape[1], dtype=np.float64)
    time = np.broadcast_to(time[None, :, None], (len(paths), len(time), 1))
    return np.concatenate([time, cumulative], axis=-1)


def lead_lag_transform(paths: np.ndarray) -> np.ndarray:
    """Return the standard lead-lag lift of path points with dimension doubled."""

    if paths.ndim != 3:
        raise ValueError("V24M_LEAD_LAG_INPUT_SHAPE")
    n, length, channels = paths.shape
    lifted = np.zeros((n, 2 * length - 1, 2 * channels), dtype=np.float64)
    lifted[:, 0, :channels] = paths[:, 0]
    lifted[:, 0, channels:] = paths[:, 0]
    for index in range(1, length):
        lifted[:, 2 * index - 1, :channels] = paths[:, index]
        lifted[:, 2 * index - 1, channels:] = paths[:, index - 1]
        lifted[:, 2 * index, :channels] = paths[:, index]
        lifted[:, 2 * index, channels:] = paths[:, index]
    return lifted
