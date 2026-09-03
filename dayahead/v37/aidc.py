"""Apply the frozen V36 96-slot CENTER/RW template to each May weather day."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from dayahead.v28r2.c1_affine import exact_c1_pcc_kw, load_c1
from dayahead.v28r2.formulation import PF_TAN
from dayahead.v28r2.source_cache import day_root
from dayahead.v36.aidc import (
    AIDCTrajectory, _apr01_ledger, _apr01_power, _rsp_schedule, _site_weights,
)
from dayahead.v36.contracts import AEST, GPU_CAPACITY, PF, RW_IT_REFERENCE_KW, SCIENCE_AUTHORITIES, SLOTS

from .contracts import (
    CENTER_SWING_W_PER_GPU, EXPANDED_TEMPORAL_JOBS,
    PARTIAL_SHARED_TEMPORAL_JOBS, SOURCE_DATA_REPOSITORY,
)


def build_day(repo: Path, day: str, case: str) -> AIDCTrajectory:
    if case not in {"B0", "B1", "B2", "B3"}:
        raise ValueError("V37_CASE")
    if not day.startswith("2025-05-"):
        raise PermissionError(f"V37_MAY_ONLY:{day}")
    enabled = case in {"B1", "B3"}
    frozen = _apr01_power()
    n_rw = frozen["N_active_RW"].to_numpy(float)
    n_rsp = frozen["N_active_RSP"].to_numpy(float)
    it_rw = frozen["P_IT_RW_FROZEN_kW"].to_numpy(float)
    it_case = frozen["P_IT_RSP_CENTER_kW" if enabled else "P_IT_RW_FROZEN_kW"].to_numpy(float)
    expected = it_rw + (n_rsp - n_rw) * CENTER_SWING_W_PER_GPU / 1000.0 if enabled else it_rw
    if not np.allclose(it_case, expected, rtol=0.0, atol=1e-12):
        raise RuntimeError("V37_AIDC_CENTER_FORMULA")
    if not np.allclose(it_rw, RW_IT_REFERENCE_KW) or np.max(n_rw) > GPU_CAPACITY:
        raise RuntimeError("V37_AIDC_REFERENCE_OR_CAPACITY")

    aidc_ids, weights, pcc_ids = _site_weights(repo)
    site_it = it_case[:, None] * weights[None, :]
    weather = pd.read_parquet(day_root(SOURCE_DATA_REPOSITORY, day) / "gfs_d1_weather.parquet")
    if len(weather) != SLOTS:
        raise RuntimeError("V37_GFS_AXIS")
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
    start = datetime.fromisoformat(day).replace(tzinfo=AEST)
    power = pd.DataFrame({
        "slot": np.arange(SLOTS, dtype=int),
        "timestamp": [(start + timedelta(minutes=15 * slot)).isoformat() for slot in range(SLOTS)],
        "N_active_GPU": n_rsp if enabled else n_rw,
        "N_idle_GPU": GPU_CAPACITY - (n_rsp if enabled else n_rw),
        "P_IT_RW_kW": it_rw, "P_IT_case_kW": it_case,
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
                "PCC_P_kW": float(pcc_p[slot, index]), "PCC_Q_kvar": float(pcc_q[slot, index]),
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
    ledger["template_operating_day"] = "2025-04-01"
    ledger["evaluation_operating_day"] = day
    ledger["known_running_start"] = pd.NA
    issue = start - timedelta(hours=6)
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
    ledger["temporal_flexible"] = ledger["workload_class"].isin(["NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"])
    ledger["PARTIAL_shared"] = ledger["requested_GPUs"] < 4 * ledger["requested_nodes"]
    ledger["coverage_fallback_status"] = np.where(
        ledger["duration_authority"].eq("REQUESTED_WALLTIME_FAIL_CLOSED"), "FALLBACK", "COVERED"
    )
    if int(ledger["temporal_flexible"].sum()) != EXPANDED_TEMPORAL_JOBS:
        raise RuntimeError("V37_EXPANDED_JOB_COUNT")
    if int((ledger["PARTIAL_shared"] & ledger["temporal_flexible"]).sum()) != PARTIAL_SHARED_TEMPORAL_JOBS:
        raise RuntimeError("V37_PARTIAL_SHARED_JOB_COUNT")
    return AIDCTrajectory(
        day, power, ledger, pd.DataFrame(rows), pcc_p, pcc_q,
        str(SCIENCE_AUTHORITIES["AIDC"]["sha256"]),
    )
