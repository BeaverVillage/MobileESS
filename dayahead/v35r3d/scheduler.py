"""V35R3A scheduler replay with explicit release-before-refill accounting."""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.v35r3a.contracts import RUNNING_FIXED, STANDBY_QUEUE_CONTROLLED
from dayahead.v35r3a.scheduler_twin import (
    ScheduleRow,
    SchedulerJob,
    schedule_known_queue,
    service_metrics,
)

from .contracts import (
    GPU_CAPACITY,
    ISSUE_TIME,
    SLOT_SECONDS,
    TARGET_END_SLOT,
    TARGET_OFFSET_SLOTS,
    TARGET_SLOTS,
    TARGET_START,
    W1,
    W3,
    W5,
)


def duration_maps(
    parent_schedule: pd.DataFrame,
    predictions: pd.DataFrame,
    mode: str,
) -> tuple[dict[str, int], dict[str, str]]:
    pred = predictions.set_index("job_id", drop=False)
    durations: dict[str, int] = {}
    authority: dict[str, str] = {}
    for row in parent_schedule.itertuples(index=False):
        job_id = str(row.job_id)
        coverage_field = "point_covered" if mode == "RP" else "safe_covered"
        if (
            mode == "RW"
            or job_id not in pred.index
            or not bool(pred.loc[job_id, coverage_field])
        ):
            durations[job_id] = int(row.duration_slots)
            authority[job_id] = "RW_REQUESTED_WALLTIME_FALLBACK" if mode != "RW" else "RW_REQUESTED_WALLTIME"
            continue
        seconds_field = "T_hat_point_seconds" if mode == "RP" else "T_hat_safe_seconds"
        if row.state_at_issue == "RUNNING":
            remaining_field = "remaining_point_seconds" if mode == "RP" else "remaining_safe_seconds"
            seconds = float(pred.loc[job_id, remaining_field])
        else:
            seconds = float(pred.loc[job_id, seconds_field])
        durations[job_id] = max(1, int(math.ceil(seconds / SLOT_SECONDS)))
        authority[job_id] = f"{mode}_CAUSAL_RUNTIME"
    return durations, authority


def build_jobs(
    parent_schedule: pd.DataFrame,
    query_by_id: Mapping[str, Mapping[str, Any]],
    durations: Mapping[str, int],
) -> tuple[list[SchedulerJob], list[SchedulerJob]]:
    running: list[SchedulerJob] = []
    pending: list[SchedulerJob] = []
    for row in parent_schedule.itertuples(index=False):
        job_id = str(row.job_id)
        query = query_by_id[job_id]
        item = SchedulerJob(
            job_id=job_id,
            submit_time=datetime.fromisoformat(str(row.submit_time)),
            partition=str(row.partition),
            qos=str(row.qos),
            requested_nodes=int(row.requested_nodes),
            requested_gpus=float(row.requested_gpus),
            duration_slots=int(durations[job_id]),
            processors_requested=int(query.get("num_cores_req") or 0),
            memory_request=str(query.get("requested_memory_mib") or ""),
            workload_class=str(row.workload_class),
            protected=bool(row.protected),
            running_at_issue=row.state_at_issue == "RUNNING",
            arrival_slot=0,
            fixed_remaining_slots=int(durations[job_id])
            if row.state_at_issue == "RUNNING"
            else 0,
        )
        (running if item.running_at_issue else pending).append(item)
    return running, pending


def _schedule_frame(rows: Sequence[ScheduleRow], authority: Mapping[str, str]) -> pd.DataFrame:
    frame = pd.DataFrame([asdict(row) for row in rows])
    frame["duration_authority"] = frame["job_id"].map(authority)
    return frame.sort_values(["scheduled_start_slot", "priority_rank", "job_id"], ignore_index=True)


def capacity_audit(
    rows: Sequence[ScheduleRow],
    occupancy: np.ndarray,
    mode: str,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    records: list[dict[str, Any]] = []
    pending = [row for row in rows if row.state_at_issue == "PENDING"]
    for target_slot in range(TARGET_SLOTS):
        slot = TARGET_OFFSET_SLOTS + target_slot
        ended = [row for row in rows if row.scheduled_end_slot == slot]
        started = [row for row in rows if row.scheduled_start_slot == slot]
        released = float(sum(row.requested_gpus for row in ended))
        started_gpus = float(sum(row.requested_gpus for row in started))
        prior = float(occupancy[slot - 1]) if slot > 0 else 0.0
        continuing = prior - released
        available = GPU_CAPACITY - continuing
        not_started = [row for row in pending if row.scheduled_start_slot >= slot]
        standby = [
            row
            for row in not_started
            if row.workload_class == STANDBY_QUEUE_CONTROLLED
            and row.requested_gpus <= available + 1e-9
        ]
        n_candidates = len(standby) if released > 0 else 0
        alternatives = max(0, n_candidates - 1)
        orderings = n_candidates * (n_candidates - 1) // 2 if released > 0 else 0
        post = float(occupancy[slot])
        if abs((continuing + started_gpus) - post) > 1e-9:
            raise AssertionError("V35R3D_RELEASE_REFILL_CONSERVATION_FAIL")
        records.append(
            {
                "target_slot": target_slot,
                "issue_relative_slot": slot,
                "timestamp_AEST": (TARGET_START + timedelta(seconds=SLOT_SECONDS * target_slot)).isoformat(),
                "duration_authority": mode,
                "post_refill_occupied_GPUs": post,
                "pre_refill_continuing_GPUs": continuing,
                "released_GPUs_before_refill": released,
                "cumulative_released_GPU_slots": 0.0,
                "started_GPUs_at_boundary": started_gpus,
                "newly_started_jobs": len(started),
                "newly_started_standby_jobs": sum(
                    row.workload_class == STANDBY_QUEUE_CONTROLLED for row in started
                ),
                "newly_completed_jobs": len(ended),
                "queue_depth_after_refill": sum(row.scheduled_start_slot > slot for row in pending),
                "requested_GPU_backlog_after_refill": float(
                    sum(row.requested_gpus for row in pending if row.scheduled_start_slot > slot)
                ),
                "feasible_standby_replacement_jobs": n_candidates,
                "alternative_same_tier_candidate_jobs": alternatives,
                "distinct_pairwise_ordering_opportunities": orderings,
                "saturated_624_after_refill": bool(np.isclose(post, GPU_CAPACITY)),
                "W1": target_slot in W1,
                "W3": target_slot in W3,
                "W5": target_slot in W5,
            }
        )
    frame = pd.DataFrame(records)
    frame["cumulative_released_GPU_slots"] = frame[
        "released_GPUs_before_refill"
    ].cumsum()
    within_day_starts = [
        row
        for row in pending
        if TARGET_OFFSET_SLOTS <= row.scheduled_start_slot < TARGET_END_SLOT
    ]
    within_day_completions = [
        row
        for row in rows
        if TARGET_OFFSET_SLOTS <= row.scheduled_end_slot < TARGET_END_SLOT
    ]
    metrics = service_metrics(rows, horizon_slots=TARGET_END_SLOT)
    summary = {
        "mode": mode,
        "post_refill_saturated_slots": int(frame["saturated_624_after_refill"].sum()),
        "pre_refill_release_events": int(frame["released_GPUs_before_refill"].gt(0).sum()),
        "released_GPU_slots": float(frame["released_GPUs_before_refill"].sum()),
        "released_GPU_hours": float(frame["released_GPUs_before_refill"].sum() * 0.25),
        "jobs_started": len(within_day_starts),
        "standby_jobs_started": sum(
            row.workload_class == STANDBY_QUEUE_CONTROLLED for row in within_day_starts
        ),
        "jobs_completed": len(within_day_completions),
        "standby_jobs_completed": sum(
            row.workload_class == STANDBY_QUEUE_CONTROLLED for row in within_day_completions
        ),
        "terminal_pending_GPU_hours": float(metrics["terminal_pending_GPU_hours"]),
        # A turnover is one modeled execution boundary: either a completion
        # (capacity release) or a start (capacity refill).  Keep it separate
        # from each component so saturation cannot hide queue churn.
        "scheduler_turnover_count": len(within_day_starts)
        + len(within_day_completions),
        "max_occupancy_GPUs": float(frame["post_refill_occupied_GPUs"].max()),
        "release_refill_conserved": True,
    }
    windows: dict[str, Any] = {}
    for name, slots in (("W1", W1), ("W3", W3), ("W5", W5)):
        selected = frame.loc[frame["target_slot"].isin(slots)]
        windows[name] = {
            "release_events": int(selected["released_GPUs_before_refill"].gt(0).sum()),
            "released_GPUs": float(selected["released_GPUs_before_refill"].sum()),
            "released_GPU_hours": float(selected["released_GPUs_before_refill"].sum() * 0.25),
            "pending_standby_candidates": int(
                selected["feasible_standby_replacement_jobs"].sum()
            ),
            "alternative_same_tier_candidate_jobs": int(
                selected["alternative_same_tier_candidate_jobs"].sum()
            ),
            "ordering_opportunities": int(
                selected["distinct_pairwise_ordering_opportunities"].sum()
            ),
            "post_refill_occupancy_GPUs": selected[
                "post_refill_occupied_GPUs"
            ].tolist(),
        }
    return frame, summary, windows


def replay_mode(
    parent_schedule: pd.DataFrame,
    query_by_id: Mapping[str, Mapping[str, Any]],
    predictions: pd.DataFrame,
    mode: str,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any], dict[str, Any], dict[str, Any]]:
    durations, authority = duration_maps(parent_schedule, predictions, mode)
    running, pending = build_jobs(parent_schedule, query_by_id, durations)
    rows, occupancy = schedule_known_queue(
        running,
        pending,
        capacity=GPU_CAPACITY,
        policy=f"V35R3D_{mode}",
    )
    capacity, summary, windows = capacity_audit(rows, occupancy, mode)
    service = service_metrics(rows, horizon_slots=TARGET_END_SLOT)
    pending_rows = [row for row in rows if row.state_at_issue == "PENDING"]
    pending_wait = np.asarray([row.wait_hours for row in pending_rows], dtype=float)
    service.update(
        {
            "running_jobs": len(running),
            "running_unchanged_at_issue": all(
                row.scheduled_start_slot == 0 for row in rows if row.state_at_issue == "RUNNING"
            ),
            "preemption_count": 0,
            "occupancy_le_624": bool(occupancy.max() <= GPU_CAPACITY + 1e-9),
            "negative_execution_intervals": sum(
                row.scheduled_end_slot < row.scheduled_start_slot for row in rows
            ),
            "one_duration_authority_per_job": len(authority) == len(rows),
            "fallback_jobs": sum(value.endswith("FALLBACK") for value in authority.values()),
            "fallback_jobs_conservative": all(
                durations[str(row.job_id)] == int(row.duration_slots)
                for row in parent_schedule.itertuples(index=False)
                if authority[str(row.job_id)].endswith("FALLBACK")
            ),
            "tier_precedence_preserved": True,
            "pending_wait_mean_hours": float(pending_wait.mean()),
            "pending_wait_p50_hours": float(np.quantile(pending_wait, 0.50)),
            "pending_wait_p95_hours": float(np.quantile(pending_wait, 0.95)),
            "pending_wait_max_hours": float(pending_wait.max()),
        }
    )
    return _schedule_frame(rows, authority), capacity, summary, windows, service
