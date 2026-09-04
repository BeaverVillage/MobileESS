"""Cohort-by-Rack Actual workload materialization and fixed-command replay."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.source_cache import day_root


AEST = timezone(timedelta(hours=10), name="AEST_FIXED_UTC_PLUS_10")
DT_HOURS = 0.25


def _add_interval_average(
    difference: np.ndarray, partial: np.ndarray, start_seconds: float,
    end_seconds: float, magnitude: float,
) -> None:
    start_seconds = max(0.0, start_seconds)
    end_seconds = min(len(partial) * 900.0, end_seconds)
    if end_seconds <= start_seconds:
        return
    first = int(start_seconds // 900)
    last = int(math.nextafter(end_seconds, -math.inf) // 900)
    if first == last:
        partial[first] += magnitude * (end_seconds - start_seconds) / 900.0
        return
    partial[first] += magnitude * ((first + 1) * 900.0 - start_seconds) / 900.0
    partial[last] += magnitude * (end_seconds - last * 900.0) / 900.0
    if last > first + 1:
        difference[first + 1] += magnitude
        difference[last] -= magnitude


def _cohort_bins(repo: Path) -> dict[int, tuple[float, float]]:
    payload = json.loads((repo / "dayahead/artifacts/v16/AIDC_COHORT_CONTRACT.json").read_text(encoding="utf-8"))
    if tuple(payload["cohort_ids"]) != COHORT_IDS:
        raise RuntimeError("V28R2_ACTUAL_COHORT_AXIS")
    return {
        int(nodes): (float(row["q33_hours"]), float(row["q67_hours"]))
        for nodes, row in payload["runtime_bins_hours_by_node_class"].items()
    }


def _cohort_id(nodes: int, runtime_hours: float, bins: dict[int, tuple[float, float]]) -> str:
    q33, q67 = bins[nodes]
    runtime_class = 0 if runtime_hours <= q33 else 1 if runtime_hours <= q67 else 2
    return f"N{nodes:02d}_R{runtime_class:02d}"


def _exact_source(filename: str, expected_sha256: str) -> Path:
    matches = sorted(
        path for path in DEFAULT_RAW_ROOT.rglob(filename)
        if path.is_file() and sha256_file(path) == expected_sha256
    )
    if not matches:
        raise FileNotFoundError(f"V28R2_ACTUAL_SOURCE:{filename}")
    return matches[0]


@dataclass(frozen=True)
class ActualWorkload:
    day: str
    cohort_ids: tuple[str, ...]
    arrivals_nodeh: np.ndarray
    total_it_kw: np.ndarray
    total_h100_gpu: np.ndarray
    flexible_natural_it_kw: np.ndarray
    flexible_natural_gpu: np.ndarray
    source_sha256: dict[str, str]

    def validate(self) -> None:
        arrays = (
            (self.arrivals_nodeh, (96, 15)), (self.total_it_kw, (96,)),
            (self.total_h100_gpu, (96,)), (self.flexible_natural_it_kw, (96,)),
            (self.flexible_natural_gpu, (96,)),
        )
        if self.cohort_ids != COHORT_IDS or any(
            np.asarray(array).shape != shape or not np.isfinite(array).all() or np.any(array < -1e-10)
            for array, shape in arrays
        ):
            raise ValueError("V28R2_ACTUAL_WORKLOAD_AXIS_OR_VALUE")
        if np.any(self.flexible_natural_gpu > self.total_h100_gpu + 1e-8):
            raise ValueError("V28R2_ACTUAL_FLEX_EXCEEDS_TOTAL_GPU")


def materialize_actual_workload(repo: Path, day: str) -> ActualWorkload:
    """Open D-day sources only for Actual/PI, never for Day-Ahead."""

    jobs_path = day_root(repo, day) / "kestrel_realized_jobs.parquet"
    jobs = pd.read_parquet(jobs_path)
    start = pd.to_datetime(jobs["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(jobs["end_time"], utc=True, errors="coerce", format="mixed")
    submit = pd.to_datetime(jobs["submit_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(jobs["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(jobs["gpus_requested"], errors="coerce")
    eligible = jobs["v28r2_strict_fullnode_eligible"].astype(bool)
    valid = start.notna() & end.notna() & end.gt(start) & nodes.gt(0) & gpus.gt(0)
    day_start = pd.Timestamp(day, tz=AEST).tz_convert("UTC")
    axis_start = day_start.timestamp()
    total_difference = np.zeros(97); total_partial = np.zeros(96)
    flex_gpu_difference = np.zeros(97); flex_gpu_partial = np.zeros(96)
    flex_p_difference = np.zeros(97); flex_p_partial = np.zeros(96)
    arrivals = np.zeros((96, len(COHORT_IDS)), dtype=float)
    bins = _cohort_bins(repo); cohort_index = {value: index for index, value in enumerate(COHORT_IDS)}
    for index in np.flatnonzero(valid.to_numpy()):
        _add_interval_average(
            total_difference, total_partial,
            start.iloc[index].timestamp() - axis_start,
            end.iloc[index].timestamp() - axis_start, float(gpus.iloc[index]),
        )
        if not bool(eligible.iloc[index]):
            continue
        node_count = int(nodes.iloc[index])
        runtime_hours = (end.iloc[index] - start.iloc[index]).total_seconds() / 3600.0
        _add_interval_average(
            flex_gpu_difference, flex_gpu_partial,
            start.iloc[index].timestamp() - axis_start,
            end.iloc[index].timestamp() - axis_start, 4.0 * node_count,
        )
        _add_interval_average(
            flex_p_difference, flex_p_partial,
            start.iloc[index].timestamp() - axis_start,
            end.iloc[index].timestamp() - axis_start,
            KAPPA_KW_PER_ACTIVE_H100_NODE[node_count] * node_count,
        )
        slot = int((submit.iloc[index].timestamp() - axis_start) // 900)
        if 0 <= slot < 96:
            cohort = _cohort_id(node_count, runtime_hours, bins)
            arrivals[slot, cohort_index[cohort]] += node_count * runtime_hours

    esif_path = _exact_source(
        "esif.influx.buildingData.PUE.combined.parquet", NLR_SOURCE_SHA256["esif_parquet"],
    )
    import pyarrow.parquet as pq

    lower = day_start.tz_localize(None).to_pydatetime()
    upper = (day_start + pd.Timedelta(days=1)).tz_localize(None).to_pydatetime()
    esif = pq.read_table(
        esif_path, columns=["ts", "it_power_kw"],
        filters=[("ts", ">=", lower), ("ts", "<", upper)],
    ).to_pandas()
    timestamps = pd.to_datetime(esif["ts"], utc=True, errors="coerce", format="mixed").dt.tz_convert(AEST)
    values = pd.to_numeric(esif["it_power_kw"], errors="coerce")
    series = pd.Series(np.asarray(values, dtype=float), index=pd.DatetimeIndex(timestamps)).dropna()
    quarter = series.groupby(series.index.floor("15min")).mean()
    target = pd.date_range(pd.Timestamp(day, tz=AEST), periods=96, freq="15min")
    quarter = quarter.reindex(target)
    if quarter.isna().any() or np.any(quarter.to_numpy() < 0):
        raise RuntimeError(f"V28R2_ESIF_ACTUAL_GAP:{day}")
    p_authority = json.loads((
        repo / "dayahead/artifacts/v28r2_heavy_backend/V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json"
    ).read_text(encoding="utf-8"))
    alpha = float(p_authority["scale_binding"]["alpha_IT"])
    result = ActualWorkload(
        day, COHORT_IDS, arrivals, quarter.to_numpy(dtype=float) * alpha,
        total_partial + np.cumsum(total_difference[:-1]),
        flex_p_partial + np.cumsum(flex_p_difference[:-1]),
        flex_gpu_partial + np.cumsum(flex_gpu_difference[:-1]),
        {"kestrel_day": sha256_file(jobs_path), "esif_raw": sha256_file(esif_path)},
    )
    result.validate()
    return result


@dataclass(frozen=True)
class WorkloadReplay:
    executed_nodeh: np.ndarray
    backlog_nodeh: np.ndarray
    unexecuted_da_nodeh: np.ndarray
    maximum_command_excess_nodeh: float
    mass_error_nodeh: float

    def validate(self, da_service: np.ndarray, arrivals: np.ndarray) -> None:
        if self.executed_nodeh.shape != (15, 48, 96) or self.backlog_nodeh.shape != (97, 15):
            raise ValueError("V28R2_WORKLOAD_REPLAY_AXIS")
        if np.any(self.executed_nodeh < -1e-12) or np.any(self.executed_nodeh > da_service + 1e-10):
            raise ValueError("V28R2_WORKLOAD_REPLAY_COMMAND_BOUND")
        balance = self.backlog_nodeh[1:] - self.backlog_nodeh[:-1] - arrivals + self.executed_nodeh.sum(axis=1).T
        if np.max(np.abs(balance)) > 1e-9 or abs(self.mass_error_nodeh) > 1e-9:
            raise ValueError("V28R2_WORKLOAD_REPLAY_MASS")


def replay_workload(
    da_service_nodeh: np.ndarray, actual_arrivals_nodeh: np.ndarray,
    authorized_capacity_nodeh: np.ndarray,
) -> WorkloadReplay:
    da = np.asarray(da_service_nodeh, dtype=float)
    arrivals = np.asarray(actual_arrivals_nodeh, dtype=float)
    capacity = np.asarray(authorized_capacity_nodeh, dtype=float)
    if da.shape != (15, 48, 96) or arrivals.shape != (96, 15) or capacity.shape != (96, 48):
        raise ValueError("V28R2_WORKLOAD_REPLAY_INPUT_AXIS")
    if np.any(da < 0) or np.any(arrivals < 0) or np.any(capacity < 0):
        raise ValueError("V28R2_WORKLOAD_REPLAY_NEGATIVE_INPUT")
    executed = np.zeros_like(da); backlog = np.zeros((97, 15), dtype=float)
    for slot in range(96):
        backlog[slot + 1] = backlog[slot] + arrivals[slot]
        remaining = capacity[slot].copy()
        for cohort in range(15):
            for rack in range(48):
                amount = min(float(da[cohort, rack, slot]), float(backlog[slot + 1, cohort]), float(remaining[rack]))
                executed[cohort, rack, slot] = amount
                backlog[slot + 1, cohort] -= amount
                remaining[rack] -= amount
    unexecuted = da - executed
    mass_error = float(arrivals.sum() - executed.sum() - backlog[-1].sum())
    result = WorkloadReplay(
        executed, backlog, unexecuted,
        float(max(0.0, np.max(executed - da))), mass_error,
    )
    result.validate(da, arrivals)
    return result
