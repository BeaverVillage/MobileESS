"""RSP construction and three-horizon release/refill accounting."""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.v35r3a.scheduler_twin import ScheduleRow, SchedulerJob, schedule_known_queue
from dayahead.v35r3d.contracts import (
    GPU_CAPACITY,
    ISSUE_TIME,
    SLOT_SECONDS,
    TARGET_END_SLOT,
    TARGET_OFFSET_SLOTS,
    W1,
    W3,
    W5,
)


def rsp_duration_authority(
    parent_schedule: pd.DataFrame,
    predictions: pd.DataFrame,
    q_selected: float,
) -> pd.DataFrame:
    """Use requested remaining life for running and conformal-safe life for pending."""

    base = parent_schedule.copy()
    base["job_id"] = base["job_id"].astype(str)
    pred = predictions.copy()
    pred["job_id"] = pred["job_id"].astype(str)
    joined = base.merge(pred, on=["job_id", "state_at_issue", "workload_class"], validate="one_to_one")
    records: list[dict[str, Any]] = []
    for row in joined.itertuples(index=False):
        requested = float(row.requested_walltime_seconds)
        elapsed = float(row.elapsed_seconds_at_issue) if row.state_at_issue == "RUNNING" else 0.0
        if row.state_at_issue == "RUNNING":
            seconds = max(requested - elapsed, float(SLOT_SECONDS))
            authority = "REQUESTED_REMAINING"
            exceeds = elapsed > requested
        elif bool(row.safe_covered):
            seconds = min(
                requested,
                max(float(row.T_hat_point_seconds) + float(q_selected), float(SLOT_SECONDS)),
            )
            authority = "SAFE_CAUSAL_RUNTIME_PENDING"
            exceeds = False
        else:
            seconds = float(row.duration_slots) * SLOT_SECONDS
            authority = "REQUESTED_WALLTIME_FAIL_CLOSED"
            exceeds = False
        records.append(
            {
                "job_id": str(row.job_id),
                "state_at_issue": row.state_at_issue,
                "workload_class": row.workload_class,
                "requested_GPUs": float(row.requested_gpus),
                "requested_walltime_seconds": requested,
                "elapsed_seconds_at_issue": elapsed if row.state_at_issue == "RUNNING" else None,
                "diagnostic_point_total_seconds": float(row.T_hat_point_seconds),
                "diagnostic_safe_total_seconds": float(row.T_hat_safe_seconds),
                "RSP_duration_seconds": seconds,
                "RSP_duration_slots": max(1, int(math.ceil(seconds / SLOT_SECONDS))),
                "duration_authority": authority,
                "RUNNING_ELAPSED_EXCEEDS_REQUESTED_WALLTIME": exceeds,
                "q_selected_seconds": float(q_selected) if row.state_at_issue == "PENDING" else None,
            }
        )
    return pd.DataFrame(records)


def build_rsp_jobs(
    parent_schedule: pd.DataFrame, authority: pd.DataFrame
) -> tuple[list[SchedulerJob], list[SchedulerJob]]:
    duration = authority.set_index("job_id")["RSP_duration_slots"].to_dict()
    running: list[SchedulerJob] = []
    pending: list[SchedulerJob] = []
    for row in parent_schedule.itertuples(index=False):
        job_id = str(row.job_id)
        slots = int(duration[job_id])
        job = SchedulerJob(
            job_id=job_id,
            submit_time=datetime.fromisoformat(str(row.submit_time)),
            partition=str(row.partition),
            qos=str(row.qos),
            requested_nodes=int(row.requested_nodes),
            requested_gpus=float(row.requested_gpus),
            duration_slots=slots,
            processors_requested=0,
            memory_request="",
            workload_class=str(row.workload_class),
            protected=bool(row.protected),
            running_at_issue=row.state_at_issue == "RUNNING",
            arrival_slot=0,
            fixed_remaining_slots=slots if row.state_at_issue == "RUNNING" else 0,
        )
        (running if job.running_at_issue else pending).append(job)
    return running, pending


def schedule_rsp(
    parent_schedule: pd.DataFrame, authority: pd.DataFrame
) -> tuple[pd.DataFrame, np.ndarray]:
    running, pending = build_rsp_jobs(parent_schedule, authority)
    rows, occupancy = schedule_known_queue(
        running, pending, capacity=GPU_CAPACITY, policy="V35R3D_R1_RSP"
    )
    frame = pd.DataFrame([asdict(row) for row in rows])
    frame["duration_authority"] = frame["job_id"].map(
        authority.set_index("job_id")["duration_authority"]
    )
    return frame.sort_values(["scheduled_start_slot", "priority_rank", "job_id"], ignore_index=True), occupancy


def occupancy_from_schedule(schedule: pd.DataFrame, slots: int = TARGET_END_SLOT) -> np.ndarray:
    result = np.zeros(slots, dtype=float)
    for row in schedule.itertuples(index=False):
        left = max(0, int(row.scheduled_start_slot))
        right = min(slots, int(row.scheduled_end_slot))
        if left < right:
            result[left:right] += float(row.requested_gpus)
    return result


def capacity_horizon(schedule: pd.DataFrame, mode: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Audit boundaries on [T0,T2), treating running occupancy as initial state."""

    occupancy = occupancy_from_schedule(schedule)
    running = schedule.loc[schedule["state_at_issue"].eq("RUNNING")]
    pending = schedule.loc[schedule["state_at_issue"].eq("PENDING")]
    terminal = pending.loc[pending["scheduled_start_slot"].ge(TARGET_END_SLOT)]
    requested_gpu_hour_field = (
        "original_requested_GPU_hours"
        if "original_requested_GPU_hours" in terminal.columns
        else "request_gpu_hours"
    )
    terminal_requested_gpu_hours = float(terminal[requested_gpu_hour_field].sum())
    initial_running = float(running["requested_gpus"].sum())
    records: list[dict[str, Any]] = []
    for slot in range(TARGET_END_SLOT):
        ended = schedule.loc[schedule["scheduled_end_slot"].eq(slot)]
        admitted = pending.loc[pending["scheduled_start_slot"].eq(slot)]
        before = initial_running if slot == 0 else float(occupancy[slot - 1])
        released = float(ended["requested_gpus"].sum())
        admitted_gpu = float(admitted["requested_gpus"].sum())
        after = float(occupancy[slot])
        continuing = before - released
        available = GPU_CAPACITY - continuing
        waiting = pending.loc[pending["scheduled_start_slot"].ge(slot)]
        standby_candidates = waiting.loc[
            waiting["workload_class"].eq("STANDBY_QUEUE_CONTROLLED")
            & waiting["requested_gpus"].le(available + 1e-9)
        ]
        decision_boundary = released > 0 or len(admitted) > 0
        n_candidates = len(standby_candidates) if decision_boundary else 0
        if continuing < -1e-9 or abs(continuing + admitted_gpu - after) > 1e-9:
            raise AssertionError("V35R3D_R1_RELEASE_REFILL_CONSERVATION_FAIL")
        if after < -1e-9 or after > GPU_CAPACITY + 1e-9:
            raise AssertionError("V35R3D_R1_OCCUPANCY_BOUND_FAIL")
        records.append(
            {
                "issue_relative_slot": slot,
                "timestamp_AEST": (ISSUE_TIME + timedelta(seconds=slot * SLOT_SECONDS)).isoformat(),
                "interval": "PRE_DAY" if slot < TARGET_OFFSET_SLOTS else "APR01",
                "mode": mode,
                "occupancy_before_GPUs": before,
                "jobs_completing_at_boundary": len(ended),
                "released_GPUs_before_refill": released,
                "pending_candidate_jobs": len(waiting),
                "feasible_standby_candidate_jobs": n_candidates,
                "same_tier_pairwise_ordering_opportunities": n_candidates * (n_candidates - 1) // 2,
                "jobs_admitted_at_refill": len(admitted),
                "standby_jobs_admitted_at_refill": int(admitted["workload_class"].eq("STANDBY_QUEUE_CONTROLLED").sum()),
                "GPUs_admitted_at_refill": admitted_gpu,
                "post_refill_GPU_occupancy": after,
                "queue_depth_after_refill": int(pending["scheduled_start_slot"].gt(slot).sum()),
                "requested_GPU_backlog_after_refill": float(
                    pending.loc[pending["scheduled_start_slot"].gt(slot), "requested_gpus"].sum()
                ),
                "terminal_pending_jobs_at_T2": len(terminal),
                "terminal_pending_requested_GPU_hours_at_T2": terminal_requested_gpu_hours,
                "conservation_residual_GPUs": continuing + admitted_gpu - after,
                "saturated_624": bool(np.isclose(after, GPU_CAPACITY)),
            }
        )
    frame = pd.DataFrame(records)

    def interval_metrics(left: int, right: int) -> dict[str, Any]:
        cap = frame.loc[frame["issue_relative_slot"].between(left, right - 1)]
        starts = pending.loc[pending["scheduled_start_slot"].between(left, right - 1)]
        completed = schedule.loc[schedule["scheduled_end_slot"].between(left, right - 1)]
        return {
            "slots": right - left,
            "post_refill_saturated_slots": int(cap["saturated_624"].sum()),
            "release_events": int(cap["released_GPUs_before_refill"].gt(0).sum()),
            "released_GPU_hours": float(cap["released_GPUs_before_refill"].sum() * 0.25),
            "jobs_started": len(starts),
            "standby_jobs_started": int(starts["workload_class"].eq("STANDBY_QUEUE_CONTROLLED").sum()),
            "normal_jobs_started": int(starts["workload_class"].eq("NORMAL_QUEUE_CONTROLLED").sum()),
            "jobs_completed": len(completed),
            "turnover": len(starts) + len(completed),
            "queue_depth_mean": float(cap["queue_depth_after_refill"].mean()),
            "queue_depth_max": int(cap["queue_depth_after_refill"].max()),
            "same_tier_ordering_opportunities": int(cap["same_tier_pairwise_ordering_opportunities"].sum()),
        }

    summary = {
        "mode": mode,
        "PRE_DAY": interval_metrics(0, TARGET_OFFSET_SLOTS),
        "APR01": interval_metrics(TARGET_OFFSET_SLOTS, TARGET_END_SLOT),
        "TOTAL_T0_T2": interval_metrics(0, TARGET_END_SLOT),
        "terminal_pending_jobs": len(terminal),
        "terminal_pending_requested_GPU_hours": terminal_requested_gpu_hours,
        "initial_pending_jobs": len(pending),
        "started_by_T2": int(pending["scheduled_start_slot"].lt(TARGET_END_SLOT).sum()),
        "conservation_PASS": bool(
            len(pending)
            == int(pending["scheduled_start_slot"].lt(TARGET_END_SLOT).sum()) + len(terminal)
        ),
        "max_occupancy_GPUs": float(occupancy.max()),
        "min_occupancy_GPUs": float(occupancy.min()),
        "slot_conservation_PASS": bool(np.allclose(frame["conservation_residual_GPUs"], 0.0)),
    }
    return frame, summary


def critical_windows(capacity: pd.DataFrame) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, slots in (("W1", W1), ("W3", W3), ("W5", W5)):
        issue_slots = [TARGET_OFFSET_SLOTS + value for value in slots]
        selected = capacity.loc[capacity["issue_relative_slot"].isin(issue_slots)]
        result[name] = {
            "release_events": int(selected["released_GPUs_before_refill"].gt(0).sum()),
            "released_GPUs": float(selected["released_GPUs_before_refill"].sum()),
            "direct_ordering_opportunities": int(selected["same_tier_pairwise_ordering_opportunities"].sum()),
            "post_refill_occupancy_GPUs": selected["post_refill_GPU_occupancy"].tolist(),
        }
    return result


def pre_w5_consequence(schedule: pd.DataFrame) -> dict[str, Any]:
    w5_start = TARGET_OFFSET_SLOTS + min(W5)
    w5_end = TARGET_OFFSET_SLOTS + max(W5) + 1
    decisions = schedule.loc[
        schedule["state_at_issue"].eq("PENDING")
        & schedule["scheduled_start_slot"].lt(w5_start)
    ]
    consequential = decisions.loc[
        decisions["scheduled_end_slot"].gt(w5_start)
        & decisions["scheduled_start_slot"].lt(w5_end)
    ]
    return {
        "PRE_W5_DECISION_COUNT": len(decisions),
        "PRE_W5_DECISION_BOUNDARY_COUNT": int(decisions["scheduled_start_slot"].nunique()),
        "PRE_W5_DECISIONS_WITH_W5_ACTIVE_CONSEQUENCE": len(consequential),
        "consequential_job_ids": consequential["job_id"].astype(str).tolist(),
        "definition": "Pending admission decisions before W5; consequence means admitted job remains active in at least one W5 slot.",
    }
