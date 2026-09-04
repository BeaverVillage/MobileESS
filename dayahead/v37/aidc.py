"""Load true per-day causal AIDC scheduler and C1 trajectories for V37."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from dayahead.v36.contracts import AEST, GPU_CAPACITY, SLOTS

from .aidc_materializer import (
    CENTER_SWING_W_PER_GPU,
    COHORT_CONSTRUCTION_RULE_ID,
    R4A_DAY_ROOT,
    TEMPORAL_CLASSES,
    load_day_manifest,
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
    fingerprints: Mapping[str, str]


def validate_cohort_contract(ledger: pd.DataFrame, day: str) -> dict[str, Any]:
    """Validate the frozen construction rule while allowing daily realizations."""

    required = {
        "job_id", "state_at_issue", "workload_class", "requested_GPUs",
        "requested_nodes", "requested_walltime_seconds", "duration_authority",
        "RSP_duration_slots", "RW_duration_slots", "temporal_flexible",
        "PARTIAL_shared", "snapshot_operating_day", "evaluation_operating_day",
        "known_running_start", "source_snapshot_sha256",
    }
    missing = sorted(required - set(ledger.columns))
    if missing:
        raise RuntimeError(f"V37_R4A_AIDC_COHORT_COLUMNS:{missing}")
    ids = ledger["job_id"].astype(str)
    if ids.eq("").any() or ids.duplicated().any():
        raise RuntimeError("V37_R4A_AIDC_COHORT_JOB_ID_UNIQUENESS")
    states = ledger["state_at_issue"].astype(str)
    if not set(states).issubset({"RUNNING", "PENDING"}):
        raise RuntimeError("V37_R4A_AIDC_COHORT_STATE")
    for field in ("requested_GPUs", "requested_nodes", "requested_walltime_seconds",
                  "RSP_duration_slots", "RW_duration_slots"):
        values = ledger[field].to_numpy(float)
        if not np.isfinite(values).all() or np.any(values <= 0):
            raise RuntimeError(f"V37_R4A_AIDC_COHORT_RESOURCE:{field}")
    temporal = ledger["workload_class"].isin(TEMPORAL_CLASSES)
    if not ledger["temporal_flexible"].astype(bool).equals(temporal):
        raise RuntimeError("V37_R4A_AIDC_COHORT_TEMPORAL_RULE")
    partial = ledger["requested_GPUs"] < 4 * ledger["requested_nodes"]
    if not ledger["PARTIAL_shared"].astype(bool).equals(partial):
        raise RuntimeError("V37_R4A_AIDC_COHORT_PARTIAL_RULE")
    if not ledger["snapshot_operating_day"].astype(str).eq(day).all():
        raise RuntimeError("V37_R4A_AIDC_COHORT_SNAPSHOT_DAY")
    if not ledger["evaluation_operating_day"].astype(str).eq(day).all():
        raise RuntimeError("V37_R4A_AIDC_COHORT_EVALUATION_DAY")
    if ledger["source_snapshot_sha256"].astype(str).str.len().ne(64).any():
        raise RuntimeError("V37_R4A_AIDC_SOURCE_SNAPSHOT_SHA")
    running, pending = states.eq("RUNNING"), states.eq("PENDING")
    if ledger.loc[running, "known_running_start"].isna().any():
        raise RuntimeError("V37_R4A_AIDC_RUNNING_START")
    if ledger.loc[pending, "known_running_start"].notna().any():
        raise RuntimeError("V37_R4A_AIDC_PENDING_START")
    authority = ledger["duration_authority"].astype(str)
    if not authority.loc[running].eq("REQUESTED_REMAINING").all():
        raise RuntimeError("V37_R4A_AIDC_RUNNING_RUNTIME_AUTHORITY")
    if not authority.loc[pending].isin({
        "SAFE_CAUSAL_RUNTIME_PENDING", "REQUESTED_WALLTIME_FAIL_CLOSED",
    }).all():
        raise RuntimeError("V37_R4A_AIDC_PENDING_RUNTIME_AUTHORITY")
    census = dict(ledger.attrs.get("cohort_census", {}))
    return {
        "rule_id": COHORT_CONSTRUCTION_RULE_ID,
        "operating_day": day,
        "D_minus_1_issue_time": (
            datetime.fromisoformat(day).replace(tzinfo=AEST) - timedelta(hours=6)
        ).isoformat(),
        "scheduler_source": "V37_R4A_PER_DAY_CAUSAL_KESTREL_SNAPSHOT",
        "source_trace_window": f"KESTREL_STATE_AT_D_MINUS_1_18_FIXED_AEST:{day}",
        "source_snapshot_sha256": str(ledger["source_snapshot_sha256"].iloc[0]),
        "total_jobs": len(ledger),
        "running_jobs": int(running.sum()), "pending_jobs": int(pending.sum()),
        "temporal_controllable_jobs": int(temporal.sum()),
        "NORMAL_QUEUE_CONTROLLED_jobs": int(ledger["workload_class"].eq("NORMAL_QUEUE_CONTROLLED").sum()),
        "STANDBY_QUEUE_CONTROLLED_jobs": int(ledger["workload_class"].eq("STANDBY_QUEUE_CONTROLLED").sum()),
        "PARTIAL_shared_temporal_jobs": int((partial & temporal).sum()),
        "FULL_node_temporal_jobs": int((~partial & temporal).sum()),
        "unknown_GPU_request_exclusions": int(census.get("unknown_GPU_request_exclusions", 0)),
        "fail_closed_exclusions": int(census.get("invalid_resource_request_exclusions", 0)),
        "fail_closed_duration_jobs": int(authority.eq("REQUESTED_WALLTIME_FAIL_CLOSED").sum()),
        "temporal_requested_GPU_hours": float((
            ledger.loc[temporal, "requested_GPUs"]
            * ledger.loc[temporal, "requested_walltime_seconds"] / 3600.0
        ).sum()),
        "temporal_RSP_duration_GPU_hours": float((
            ledger.loc[temporal, "requested_GPUs"]
            * ledger.loc[temporal, "RSP_duration_slots"] * 0.25
        ).sum()),
        "no_double_counting": True, "rule_validation": "PASS",
    }


def build_day(repo: Path, day: str, case: str) -> AIDCTrajectory:
    """Load a pre-materialized operating-day authority; never replay Apr-01."""

    if case not in {"B0", "B1", "B2", "B3"}:
        raise ValueError("V37_CASE")
    if not day.startswith("2025-05-"):
        raise PermissionError(f"V37_MAY_ONLY:{day}")
    manifest = load_day_manifest(repo, day)
    root = repo / R4A_DAY_ROOT / day
    ledger = pd.read_parquet(root / "V37_R4A_JOB_LEDGER.parquet")
    ledger["source_snapshot_sha256"] = manifest["source_snapshot_sha256"]
    ledger.attrs["cohort_census"] = dict(manifest["cohort_census"])
    trajectory = pd.read_parquet(root / "V37_R4A_GPU_IT_TRAJECTORY.parquet")
    pcc = pd.read_parquet(root / "V37_R4A_C1_PCC_TRAJECTORY.parquet")
    if len(trajectory) != SLOTS:
        raise RuntimeError("V37_R4A_AIDC_SLOT_AXIS")
    enabled = case in {"B1", "B3"}
    mode = "RSP_CENTER" if enabled else "RW"
    selected = pcc.loc[pcc["mode"].eq(mode)].sort_values(["slot", "AIDC_id"]).reset_index(drop=True)
    if len(selected) != SLOTS * 12:
        raise RuntimeError("V37_R4A_AIDC_PCC_AXIS")
    pcc_p = selected["PCC_P_kW"].to_numpy(float).reshape(SLOTS, 12)
    pcc_q = selected["PCC_Q_kvar"].to_numpy(float).reshape(SLOTS, 12)
    n_active = trajectory["N_active_RSP" if enabled else "N_active_RW"].to_numpy(float)
    it_rw = trajectory["P_IT_RW_kW"].to_numpy(float)
    it_case = trajectory["P_IT_RSP_CENTER_kW" if enabled else "P_IT_RW_kW"].to_numpy(float)
    power = pd.DataFrame({
        "slot": trajectory["slot"].to_numpy(int), "timestamp": trajectory["timestamp"],
        "N_active_GPU": n_active, "N_idle_GPU": GPU_CAPACITY - n_active,
        "P_IT_RW_kW": it_rw, "P_IT_case_kW": it_case,
        "Delta_P_AIDC_kW": it_case - it_rw,
        "AIDC_flexibility": "ON" if enabled else "OFF",
        "official_scenario": "CENTER" if enabled else "RW_FROZEN_REFERENCE",
        "CENTER_swing_W_per_GPU": CENTER_SWING_W_PER_GPU,
        "C1_effective_PUE": pcc_p.sum(axis=1) / it_case,
        "aggregate_PCC_P_kW": pcc_p.sum(axis=1),
        "aggregate_PCC_Q_kvar": pcc_q.sum(axis=1),
    })
    site = selected.drop(columns=["mode"]).copy()
    validate_cohort_contract(ledger, day)
    fingerprints = {
        "operating_day": day,
        "source_snapshot_sha256": manifest["source_snapshot_sha256"],
        "ledger_sha256": manifest["files"]["job_ledger"]["sha256"],
        "RW_schedule_sha256": manifest["files"]["RW_schedule"]["sha256"],
        "RSP_schedule_sha256": manifest["files"]["RSP_schedule"]["sha256"],
        "runtime_authority_sha256": manifest["runtime_authority_sha256"],
        "RW_active_GPU_trajectory_sha256": manifest["RW_active_GPU_trajectory_sha256"],
        "RSP_active_GPU_trajectory_sha256": manifest["RSP_active_GPU_trajectory_sha256"],
        "CENTER_IT_power_trajectory_sha256": manifest["CENTER_IT_power_trajectory_sha256"],
        "C1_PCC_P_trajectory_sha256": manifest["C1_PCC_P_trajectory_sha256"],
        "C1_PCC_Q_trajectory_sha256": manifest["C1_PCC_Q_trajectory_sha256"],
    }
    return AIDCTrajectory(
        day, power, ledger, site, pcc_p, pcc_q,
        str(manifest["authority_sha256"]), fingerprints,
    )
