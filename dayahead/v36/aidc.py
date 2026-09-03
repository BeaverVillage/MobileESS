"""Frozen expanded CENTER AIDC trajectory and unchanged IDC/C1 binding."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dayahead.v28r2.c1_affine import exact_c1_pcc_kw, load_c1
from dayahead.v28r2.formulation import PF_TAN
from dayahead.v28r2.source_cache import day_root

from .contracts import (
    AEST, AIDC_HEAD, APR01_RUNTIME_CACHE, CENTER_SWING_W_PER_GPU, GPU_CAPACITY, PF,
    RW_IT_REFERENCE_KW, SCIENCE_AUTHORITIES, SLOTS, SOURCE_DATA_REPOSITORY,
)
from .science import git_bytes, source_json


APR01_POWER_PATH = (
    "dayahead/artifacts/v35r3j_aidc_it_scale_consistency_freeze/"
    "V35R3J_RW_RSP_FINAL_AIDC_IT.csv"
)
APR01_LEDGER_PATH = (
    "dayahead/artifacts/v35r3d_r1_running_residual_accounting/"
    "V35R3D_R1_RSP_DURATION_AUTHORITY.parquet"
)


@dataclass(frozen=True)
class AIDCTrajectory:
    day: str
    power: pd.DataFrame
    ledger: pd.DataFrame
    site: pd.DataFrame
    pcc_p_kw: np.ndarray
    pcc_q_kvar: np.ndarray
    contract_sha256: str


def _apr01_power() -> pd.DataFrame:
    frame = pd.read_csv(BytesIO(git_bytes(AIDC_HEAD, APR01_POWER_PATH)))
    if len(frame) != SLOTS:
        raise RuntimeError("V36_APR01_AIDC_SLOT_AXIS")
    return frame


def _apr01_ledger() -> pd.DataFrame:
    frame = pd.read_parquet(BytesIO(git_bytes(AIDC_HEAD, APR01_LEDGER_PATH)))
    frame["job_id"] = frame["job_id"].astype(str)
    return frame


def _first_fit(occupancy: list[float], duration: int, gpus: float) -> int:
    start = 0
    while start <= 20000:
        end = start + duration
        if end > len(occupancy):
            occupancy.extend([0.0] * (end - len(occupancy)))
        if all(value + gpus <= GPU_CAPACITY + 1e-12 for value in occupancy[start:end]):
            return start
        start += 1
    raise RuntimeError("V36_AIDC_SCHEDULER_HORIZON_EXHAUSTED")


def _rsp_schedule(authority: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Reconstruct the frozen tier/FIFO first-fit RW and RSP schedules."""

    rw = pd.read_parquet(APR01_RUNTIME_CACHE / "schedule_RW.parquet")
    rw["job_id"] = rw["job_id"].astype(str)
    durations = authority.set_index("job_id")["RSP_duration_slots"].astype(int).to_dict()
    rows: list[dict[str, Any]] = []
    occupancy: list[float] = [0.0] * 120
    running = rw.loc[rw["state_at_issue"].eq("RUNNING")].sort_values("job_id")
    pending = rw.loc[rw["state_at_issue"].eq("PENDING")].copy()
    tier = pending["qos"].astype(str).str.lower().map(
        {"high": 0, "urgent": 0, "normal": 1, "standby": 2}
    ).fillna(3)
    pending = pending.assign(_tier=tier).sort_values(["_tier", "submit_time", "job_id"])
    for source in running.itertuples(index=False):
        duration = max(1, int(durations[str(source.job_id)]))
        for slot in range(duration):
            if slot >= len(occupancy):
                occupancy.append(0.0)
            occupancy[slot] += float(source.requested_gpus)
        rows.append({"job_id": str(source.job_id), "scheduled_start_slot": 0, "scheduled_end_slot": duration})
    for source in pending.itertuples(index=False):
        duration = max(1, int(durations[str(source.job_id)]))
        start = _first_fit(occupancy, duration, float(source.requested_gpus))
        for slot in range(start, start + duration):
            occupancy[slot] += float(source.requested_gpus)
        rows.append({"job_id": str(source.job_id), "scheduled_start_slot": start, "scheduled_end_slot": start + duration})
    return rw, pd.DataFrame(rows)


def _site_weights(repo: Path) -> tuple[tuple[str, ...], np.ndarray, tuple[str, ...]]:
    mapping = source_json("IDC_LOCATION")
    racks = mapping["racks"]
    aidc_ids = tuple(dict.fromkeys(str(row["aidc_id"]) for row in racks))
    weights = np.asarray([
        sum(float(mapping["power_weights"][index]) for index, row in enumerate(racks) if row["aidc_id"] == aidc)
        for aidc in aidc_ids
    ])
    pcc = tuple(
        next(str(row["source_idc_id"]) for row in racks if row["aidc_id"] == aidc)
        for aidc in aidc_ids
    )
    if len(aidc_ids) != 12 or not np.isclose(weights.sum(), 1.0):
        raise RuntimeError("V36_IDC_MAPPING_AXIS")
    return aidc_ids, weights, pcc


def build_apr01(repo: Path, case: str) -> AIDCTrajectory:
    if case not in {"B0", "B1", "B2", "B3"}:
        raise ValueError("V36_CASE")
    enabled = case in {"B1", "B3"}
    frozen = _apr01_power()
    n_rw = frozen["N_active_RW"].to_numpy(float)
    n_rsp = frozen["N_active_RSP"].to_numpy(float)
    it_rw = frozen["P_IT_RW_FROZEN_kW"].to_numpy(float)
    it_case = frozen["P_IT_RSP_CENTER_kW" if enabled else "P_IT_RW_FROZEN_kW"].to_numpy(float)
    if not np.allclose(it_case, it_rw + (n_rsp - n_rw) * CENTER_SWING_W_PER_GPU / 1000.0 if enabled else it_rw):
        raise RuntimeError("V36_AIDC_CENTER_FORMULA")
    if not np.allclose(it_rw, RW_IT_REFERENCE_KW) or np.max(n_rw) > GPU_CAPACITY:
        raise RuntimeError("V36_AIDC_REFERENCE_OR_CAPACITY")

    aidc_ids, weights, pcc_ids = _site_weights(repo)
    site_it = it_case[:, None] * weights[None, :]
    weather = pd.read_parquet(day_root(SOURCE_DATA_REPOSITORY, "2025-04-01") / "gfs_d1_weather.parquet")
    if len(weather) != SLOTS:
        raise RuntimeError("V36_GFS_AXIS")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    pcc_p = np.asarray([
        [
            float(exact_c1_pcc_kw(
                site_it[slot, index], float(weather.iloc[slot]["t_wb_c"]),
                float(weather.iloc[slot]["rh_pct"]), parameters,
            ))
            for index in range(12)
        ]
        for slot in range(SLOTS)
    ])
    pcc_q = pcc_p * PF_TAN
    start = datetime(2025, 4, 1, tzinfo=AEST)
    power = pd.DataFrame({
        "slot": np.arange(SLOTS, dtype=int),
        "timestamp": [(start + timedelta(minutes=15 * slot)).isoformat() for slot in range(SLOTS)],
        "N_active_GPU": n_rsp if enabled else n_rw,
        "N_idle_GPU": GPU_CAPACITY - (n_rsp if enabled else n_rw),
        "P_IT_RW_kW": it_rw,
        "P_IT_case_kW": it_case,
        "Delta_P_AIDC_kW": it_case - it_rw,
        "AIDC_flexibility": "ON" if enabled else "OFF",
        "official_scenario": "CENTER" if enabled else "RW_FROZEN_REFERENCE",
        "CENTER_swing_W_per_GPU": CENTER_SWING_W_PER_GPU,
        "C1_effective_PUE": pcc_p.sum(axis=1) / it_case,
        "aggregate_PCC_P_kW": pcc_p.sum(axis=1),
        "aggregate_PCC_Q_kvar": pcc_q.sum(axis=1),
    })
    rows: list[dict[str, Any]] = []
    for slot in range(SLOTS):
        for index, aidc_id in enumerate(aidc_ids):
            pue = float(pcc_p[slot, index] / site_it[slot, index]) if site_it[slot, index] > 0 else 1.0
            rows.append({
                "slot": slot, "timestamp": power.iloc[slot]["timestamp"],
                "IDC_id": pcc_ids[index], "AIDC_id": aidc_id,
                "existing_feeder_PCC_node": pcc_ids[index],
                "IT_power_kW": float(site_it[slot, index]), "PUE": pue,
                "cooling_facility_auxiliary_kW": float(pcc_p[slot, index] - site_it[slot, index]),
                "PCC_P_kW": float(pcc_p[slot, index]),
                "PCC_Q_kvar": float(pcc_q[slot, index]),
                "total_facility_power_kW": float(pcc_p[slot, index]),
                "IDC_LOCATION_CHANGED": "NO", "PF": PF,
            })
    authority = _apr01_ledger().copy()
    rw_schedule, rsp_schedule = _rsp_schedule(authority)
    ledger = authority.merge(
        rw_schedule[["job_id", "qos", "partition", "submit_time", "requested_nodes",
                     "requested_gpus", "scheduled_start_slot", "scheduled_end_slot"]],
        on="job_id", how="left", validate="one_to_one", suffixes=("", "_rw"),
    ).merge(rsp_schedule, on="job_id", how="left", validate="one_to_one", suffixes=("_rw", "_rsp"))
    issue = datetime(2025, 3, 31, 18, tzinfo=AEST)
    ledger["known_running_start"] = pd.NA
    running_mask = ledger["state_at_issue"].eq("RUNNING")
    ledger.loc[running_mask, "known_running_start"] = [
        (issue - timedelta(seconds=float(value))).isoformat()
        for value in ledger.loc[running_mask, "elapsed_seconds_at_issue"]
    ]
    ledger["RW_scheduled_start"] = ledger["scheduled_start_slot_rw"].astype(int)
    ledger["RW_scheduled_completion"] = ledger["scheduled_end_slot_rw"].astype(int)
    ledger["RSP_scheduled_start"] = ledger["scheduled_start_slot_rsp"].astype(int)
    ledger["RSP_scheduled_completion"] = ledger["scheduled_end_slot_rsp"].astype(int)
    ledger["requested_GPUs"] = ledger["requested_gpus"].astype(float)
    ledger["safe_runtime_authority"] = ledger["duration_authority"]
    ledger["temporal_flexible"] = ledger["workload_class"].isin(
        ["NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"]
    )
    ledger["PARTIAL_shared"] = ledger["requested_GPUs"] < 4 * ledger["requested_nodes"]
    ledger["coverage_fallback_status"] = np.where(
        ledger["duration_authority"].eq("REQUESTED_WALLTIME_FAIL_CLOSED"), "FALLBACK", "COVERED"
    )
    rw_profile = np.zeros(SLOTS)
    rsp_profile = np.zeros(SLOTS)
    for row in ledger.itertuples(index=False):
        for profile, left, right in (
            (rw_profile, row.RW_scheduled_start, row.RW_scheduled_completion),
            (rsp_profile, row.RSP_scheduled_start, row.RSP_scheduled_completion),
        ):
            lo, hi = max(24, int(left)), min(120, int(right))
            if lo < hi:
                profile[lo - 24:hi - 24] += float(row.requested_GPUs)
    if not np.allclose(rw_profile, n_rw) or not np.allclose(rsp_profile, n_rsp):
        raise RuntimeError("V36_APR01_SCHEDULER_OCCUPANCY_REGRESSION")
    return AIDCTrajectory(
        "2025-04-01", power, ledger, pd.DataFrame(rows), pcc_p, pcc_q,
        str(SCIENCE_AUTHORITIES["AIDC"]["sha256"]),
    )
