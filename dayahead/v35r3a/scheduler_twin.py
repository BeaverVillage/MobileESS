"""Transparent event-driven public-policy relative scheduler twin."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Sequence

import numpy as np

from .contracts import (
    CRITICAL_SLOT,
    GPU_CAPACITY,
    HIGH_PROTECTED,
    ISSUE_TIME,
    NORMAL_QUEUE_CONTROLLED,
    PROTECTED_QOS,
    RUNNING_FIXED,
    SIMULATION_SLOTS,
    SLOT_MINUTES,
    STANDBY_QUEUE_CONTROLLED,
    STANDBY_QOS,
    TARGET_START,
    TEMPORAL_CONTROLLED_CLASSES,
    W1,
    W3,
    W5,
    ServiceGate,
)


@dataclass(frozen=True)
class SchedulerJob:
    job_id: str
    submit_time: datetime
    partition: str
    qos: str
    requested_nodes: int
    requested_gpus: float
    duration_slots: int
    processors_requested: int
    memory_request: str
    workload_class: str
    protected: bool
    running_at_issue: bool = False
    arrival_slot: int = 0
    fixed_remaining_slots: int = 0
    exclusion_reasons: tuple[str, ...] = ()

    @property
    def request_gpu_hours(self) -> float:
        return self.requested_gpus * self.duration_slots * SLOT_MINUTES / 60.0

    @property
    def priority_key(self) -> tuple[int, datetime, str]:
        """Documented QoS precedence, then eligible age, then stable ID.

        Numeric Kestrel weights are intentionally absent: they were not in the
        downloaded authority.  This tuple is therefore a relative-twin policy,
        not a claim of exact Kestrel composite priority.
        """

        qos = self.qos.lower()
        if qos in PROTECTED_QOS:
            tier = 0
        elif qos == "normal":
            tier = 1
        elif qos in STANDBY_QOS:
            tier = 2
        else:
            tier = 3
        return tier, self.submit_time, self.job_id

    @property
    def service_tier(self) -> int:
        return self.priority_key[0]


@dataclass(frozen=True)
class ScheduleRow:
    job_id: str
    state_at_issue: str
    workload_class: str
    protected: bool
    qos: str
    partition: str
    submit_time: str
    requested_nodes: int
    requested_gpus: float
    duration_slots: int
    scheduled_start_slot: int
    scheduled_end_slot: int
    wait_hours: float
    request_gpu_hours: float
    priority_rank: int
    sitefactor: int
    policy: str


def _ensure_length(values: list[float], size: int) -> None:
    if size > len(values):
        values.extend([0.0] * (size - len(values)))


def _fits(occupancy: Sequence[float], start: int, duration: int, gpus: float, capacity: float) -> bool:
    end = start + duration
    if end > len(occupancy):
        return True
    return all(value + gpus <= capacity + 1e-12 for value in occupancy[start:end])


def _first_fit(
    occupancy: list[float],
    earliest: int,
    duration: int,
    gpus: float,
    capacity: float,
    *,
    maximum_slot: int = 20000,
) -> int:
    start = max(0, int(earliest))
    while start <= maximum_slot:
        _ensure_length(occupancy, start + duration)
        if _fits(occupancy, start, duration, gpus, capacity):
            return start
        start += 1
    raise RuntimeError("V35R3A_SCHEDULER_HORIZON_EXHAUSTED")


def _add_occupancy(occupancy: list[float], start: int, duration: int, gpus: float) -> None:
    _ensure_length(occupancy, start + duration)
    for slot in range(start, start + duration):
        occupancy[slot] += gpus


def schedule_known_queue(
    running: Sequence[SchedulerJob],
    pending: Sequence[SchedulerJob],
    *,
    capacity: float = GPU_CAPACITY,
    policy: str = "baseline",
    rank_override: Mapping[str, int] | None = None,
    sitefactor: Mapping[str, int] | None = None,
) -> tuple[list[ScheduleRow], np.ndarray]:
    """Schedule the D-1-known queue using conservative reservations.

    Running jobs are immutable reservations.  Pending jobs are placed in the
    earliest compatible interval in priority order.  Later jobs can therefore
    occupy holes without displacing an earlier reservation, matching the
    conservative EASY-backfill property while using requested walltime.
    """

    occupancy: list[float] = [0.0] * SIMULATION_SLOTS
    rows: list[ScheduleRow] = []
    for rank, job in enumerate(sorted(running, key=lambda value: value.job_id)):
        duration = max(1, job.fixed_remaining_slots or job.duration_slots)
        _add_occupancy(occupancy, 0, duration, job.requested_gpus)
        rows.append(
            ScheduleRow(
                job_id=job.job_id,
                state_at_issue="RUNNING",
                workload_class=job.workload_class,
                protected=True,
                qos=job.qos,
                partition=job.partition,
                submit_time=job.submit_time.isoformat(),
                requested_nodes=job.requested_nodes,
                requested_gpus=job.requested_gpus,
                duration_slots=duration,
                scheduled_start_slot=0,
                scheduled_end_slot=duration,
                wait_hours=0.0,
                request_gpu_hours=job.requested_gpus * duration * SLOT_MINUTES / 60.0,
                priority_rank=rank,
                sitefactor=0,
                policy=policy,
            )
        )

    ordered = sorted(pending, key=lambda value: value.priority_key)
    if rank_override:
        natural = {job.job_id: index for index, job in enumerate(ordered)}
        # A SiteFactor may reorder only inside a service tier.  This makes it
        # impossible for standby to jump high/normal merely because of grid
        # exposure.
        ordered.sort(
            key=lambda value: (
                value.service_tier,
                rank_override.get(value.job_id, natural[value.job_id]),
                value.job_id,
            )
        )
    for rank, job in enumerate(ordered):
        start = _first_fit(
            occupancy,
            max(0, job.arrival_slot),
            job.duration_slots,
            job.requested_gpus,
            capacity,
        )
        _add_occupancy(occupancy, start, job.duration_slots, job.requested_gpus)
        absolute_start = ISSUE_TIME + timedelta(minutes=SLOT_MINUTES * start)
        wait_hours = max(0.0, (absolute_start - job.submit_time).total_seconds() / 3600.0)
        rows.append(
            ScheduleRow(
                job_id=job.job_id,
                state_at_issue="PENDING",
                workload_class=job.workload_class,
                protected=job.protected,
                qos=job.qos,
                partition=job.partition,
                submit_time=job.submit_time.isoformat(),
                requested_nodes=job.requested_nodes,
                requested_gpus=job.requested_gpus,
                duration_slots=job.duration_slots,
                scheduled_start_slot=start,
                scheduled_end_slot=start + job.duration_slots,
                wait_hours=wait_hours,
                request_gpu_hours=job.request_gpu_hours,
                priority_rank=rank,
                sitefactor=int((sitefactor or {}).get(job.job_id, 0)),
                policy=policy,
            )
        )
    if occupancy and max(occupancy) > capacity + 1e-9:
        raise AssertionError("V35R3A_GPU_CAPACITY_VIOLATION")
    return rows, np.asarray(occupancy, dtype=float)


def schedule_online_replay(
    running: Sequence[SchedulerJob],
    jobs: Sequence[SchedulerJob],
    *,
    replay_start: datetime,
    capacity: float = GPU_CAPACITY,
    maximum_slots: int = 3000,
    policy: str = "historical_relative_replay",
) -> tuple[list[ScheduleRow], np.ndarray]:
    """Causal online replay that reveals jobs only at ``arrival_slot``.

    The main loop is work-conserving within documented QoS order.  When the
    head job cannot fit, a lower-priority job starts only when it fits the
    current resource interval.  This is a transparent relative backfill
    approximation; missing reservations and topology prevent an exact label.
    """

    occupancy: list[float] = [0.0] * max(SIMULATION_SLOTS, maximum_slots)
    rows: list[ScheduleRow] = []
    for rank, job in enumerate(sorted(running, key=lambda value: value.job_id)):
        duration = max(1, job.fixed_remaining_slots or job.duration_slots)
        _add_occupancy(occupancy, 0, duration, job.requested_gpus)
        rows.append(
            ScheduleRow(
                job_id=job.job_id,
                state_at_issue="RUNNING",
                workload_class=job.workload_class,
                protected=True,
                qos=job.qos,
                partition=job.partition,
                submit_time=job.submit_time.isoformat(),
                requested_nodes=job.requested_nodes,
                requested_gpus=job.requested_gpus,
                duration_slots=duration,
                scheduled_start_slot=0,
                scheduled_end_slot=duration,
                wait_hours=0.0,
                request_gpu_hours=job.requested_gpus * duration * SLOT_MINUTES / 60.0,
                priority_rank=rank,
                sitefactor=0,
                policy=policy,
            )
        )
    arrivals = sorted(jobs, key=lambda value: (value.arrival_slot, value.priority_key))
    queue: list[SchedulerJob] = []
    cursor = 0
    scheduled_rank = 0
    for slot in range(maximum_slots + 1):
        while cursor < len(arrivals) and arrivals[cursor].arrival_slot <= slot:
            queue.append(arrivals[cursor])
            cursor += 1
        progress = True
        while queue and progress:
            progress = False
            queue.sort(key=lambda value: value.priority_key)
            for index, job in enumerate(queue):
                _ensure_length(occupancy, slot + job.duration_slots)
                if not _fits(occupancy, slot, job.duration_slots, job.requested_gpus, capacity):
                    continue
                # Standby is idle-only: it cannot jump an available normal/high
                # request.  It may fill capacity when every protected-tier job
                # is resource-blocked.
                if job.qos.lower() in STANDBY_QOS:
                    if any(
                        other.qos.lower() not in STANDBY_QOS
                        and _fits(occupancy, slot, other.duration_slots, other.requested_gpus, capacity)
                        for other in queue[:index]
                    ):
                        continue
                _add_occupancy(occupancy, slot, job.duration_slots, job.requested_gpus)
                absolute_start = replay_start + timedelta(minutes=SLOT_MINUTES * slot)
                wait_hours = max(0.0, (absolute_start - job.submit_time).total_seconds() / 3600.0)
                rows.append(
                    ScheduleRow(
                        job_id=job.job_id,
                        state_at_issue="PENDING",
                        workload_class=job.workload_class,
                        protected=job.protected,
                        qos=job.qos,
                        partition=job.partition,
                        submit_time=job.submit_time.isoformat(),
                        requested_nodes=job.requested_nodes,
                        requested_gpus=job.requested_gpus,
                        duration_slots=job.duration_slots,
                        scheduled_start_slot=slot,
                        scheduled_end_slot=slot + job.duration_slots,
                        wait_hours=wait_hours,
                        request_gpu_hours=job.request_gpu_hours,
                        priority_rank=scheduled_rank,
                        sitefactor=0,
                        policy=policy,
                    )
                )
                scheduled_rank += 1
                queue.pop(index)
                progress = True
                break
        if cursor >= len(arrivals) and not queue:
            break
    if queue:
        # Continue with reservation placement so every row receives a stable
        # predicted start without using a realized runtime.
        for job in sorted(queue, key=lambda value: value.priority_key):
            start = _first_fit(
                occupancy,
                max(maximum_slots + 1, job.arrival_slot),
                job.duration_slots,
                job.requested_gpus,
                capacity,
            )
            _add_occupancy(occupancy, start, job.duration_slots, job.requested_gpus)
            absolute_start = replay_start + timedelta(minutes=SLOT_MINUTES * start)
            rows.append(
                ScheduleRow(
                    job_id=job.job_id,
                    state_at_issue="PENDING",
                    workload_class=job.workload_class,
                    protected=job.protected,
                    qos=job.qos,
                    partition=job.partition,
                    submit_time=job.submit_time.isoformat(),
                    requested_nodes=job.requested_nodes,
                    requested_gpus=job.requested_gpus,
                    duration_slots=job.duration_slots,
                    scheduled_start_slot=start,
                    scheduled_end_slot=start + job.duration_slots,
                    wait_hours=max(0.0, (absolute_start - job.submit_time).total_seconds() / 3600.0),
                    request_gpu_hours=job.request_gpu_hours,
                    priority_rank=scheduled_rank,
                    sitefactor=0,
                    policy=policy,
                )
            )
            scheduled_rank += 1
    if occupancy and max(occupancy) > capacity + 1e-9:
        raise AssertionError("V35R3A_GPU_CAPACITY_VIOLATION")
    return rows, np.asarray(occupancy, dtype=float)


def schedule_hash(rows: Sequence[ScheduleRow]) -> str:
    payload = [asdict(row) for row in sorted(rows, key=lambda item: item.job_id)]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _tier_metrics(rows: Sequence[ScheduleRow], *, horizon_slots: int) -> dict[str, float | int]:
    complete = [row for row in rows if row.scheduled_end_slot <= horizon_slots]
    terminal = [row for row in rows if row.scheduled_start_slot >= horizon_slots]
    waits = np.asarray([row.wait_hours for row in rows], dtype=float)
    return {
        "job_count": len(rows),
        "completed_job_count": len(complete),
        "completed_GPU_hours": float(sum(row.request_gpu_hours for row in complete)),
        "terminal_pending_GPU_hours": float(sum(row.request_gpu_hours for row in terminal)),
        "wait_mean_hours": float(waits.mean()) if waits.size else 0.0,
        "wait_p50_hours": float(np.quantile(waits, 0.50)) if waits.size else 0.0,
        "wait_p95_hours": float(np.quantile(waits, 0.95)) if waits.size else 0.0,
        "wait_max_hours": float(waits.max()) if waits.size else 0.0,
    }


def service_metrics(rows: Sequence[ScheduleRow], *, horizon_slots: int = SIMULATION_SLOTS) -> dict[str, object]:
    pending = [row for row in rows if row.state_at_issue == "PENDING"]
    complete = [row for row in rows if row.scheduled_end_slot <= horizon_slots]
    terminal = [row for row in pending if row.scheduled_start_slot >= horizon_slots]
    high = [row for row in pending if row.qos.lower() in PROTECTED_QOS]
    normal = [row for row in pending if row.qos.lower() == "normal"]
    standby = [row for row in pending if row.qos.lower() in STANDBY_QOS]
    normal_metrics = _tier_metrics(normal, horizon_slots=horizon_slots)
    standby_metrics = _tier_metrics(standby, horizon_slots=horizon_slots)
    high_metrics = _tier_metrics(high, horizon_slots=horizon_slots)
    return {
        "completed_job_count": len(complete),
        "completed_GPU_hours": float(sum(row.request_gpu_hours for row in complete)),
        "terminal_pending_GPU_hours": float(sum(row.request_gpu_hours for row in terminal)),
        "normal_wait_count": normal_metrics["job_count"],
        "normal_wait_mean_hours": normal_metrics["wait_mean_hours"],
        "normal_wait_p50_hours": normal_metrics["wait_p50_hours"],
        "normal_wait_p95_hours": normal_metrics["wait_p95_hours"],
        "normal_wait_max_hours": normal_metrics["wait_max_hours"],
        "high_urgent_job_count": len(high),
        "tiers": {
            "high_protected": high_metrics,
            "normal": normal_metrics,
            "standby": standby_metrics,
        },
    }


def service_noninferiority(
    baseline_rows: Sequence[ScheduleRow],
    controlled_rows: Sequence[ScheduleRow],
) -> ServiceGate:
    base = service_metrics(baseline_rows)
    control = service_metrics(controlled_rows)
    base_tiers = base["tiers"]
    control_tiers = control["tiers"]
    base_by_id = {row.job_id: row for row in baseline_rows}
    high_delay = sum(
        row.qos.lower() in PROTECTED_QOS
        and row.scheduled_start_slot > base_by_id[row.job_id].scheduled_start_slot
        for row in controlled_rows
        if row.job_id in base_by_id
    )
    higher_tier_delay = sum(
        (row.qos.lower() in PROTECTED_QOS or row.qos.lower() == "normal")
        and row.scheduled_start_slot > base_by_id[row.job_id].scheduled_start_slot
        for row in controlled_rows
        if row.job_id in base_by_id
    )
    standby_advanced = sum(
        row.qos.lower() in STANDBY_QOS
        and row.scheduled_start_slot < base_by_id[row.job_id].scheduled_start_slot
        for row in controlled_rows
        if row.job_id in base_by_id
    )
    standby_delayed = sum(
        row.qos.lower() in STANDBY_QOS
        and row.scheduled_start_slot > base_by_id[row.job_id].scheduled_start_slot
        for row in controlled_rows
        if row.job_id in base_by_id
    )
    deltas = {
        "completed_job_count": float(control["completed_job_count"] - base["completed_job_count"]),
        "completed_GPU_hours": float(control["completed_GPU_hours"] - base["completed_GPU_hours"]),
        "terminal_pending_GPU_hours": float(control["terminal_pending_GPU_hours"] - base["terminal_pending_GPU_hours"]),
        "normal_wait_mean_hours": float(control["normal_wait_mean_hours"] - base["normal_wait_mean_hours"]),
        "normal_wait_p95_hours": float(control["normal_wait_p95_hours"] - base["normal_wait_p95_hours"]),
        "normal_wait_max_hours": float(control["normal_wait_max_hours"] - base["normal_wait_max_hours"]),
        "high_urgent_delay_count": float(high_delay),
        "high_normal_delay_count": float(higher_tier_delay),
        "normal_completed_job_count": float(
            control_tiers["normal"]["completed_job_count"] - base_tiers["normal"]["completed_job_count"]
        ),
        "normal_completed_GPU_hours": float(
            control_tiers["normal"]["completed_GPU_hours"] - base_tiers["normal"]["completed_GPU_hours"]
        ),
        "normal_terminal_pending_GPU_hours": float(
            control_tiers["normal"]["terminal_pending_GPU_hours"]
            - base_tiers["normal"]["terminal_pending_GPU_hours"]
        ),
        "standby_completed_job_count": float(
            control_tiers["standby"]["completed_job_count"] - base_tiers["standby"]["completed_job_count"]
        ),
        "standby_completed_GPU_hours": float(
            control_tiers["standby"]["completed_GPU_hours"] - base_tiers["standby"]["completed_GPU_hours"]
        ),
        "standby_terminal_pending_GPU_hours": float(
            control_tiers["standby"]["terminal_pending_GPU_hours"]
            - base_tiers["standby"]["terminal_pending_GPU_hours"]
        ),
        "standby_wait_mean_hours": float(
            control_tiers["standby"]["wait_mean_hours"] - base_tiers["standby"]["wait_mean_hours"]
        ),
        "standby_wait_p95_hours": float(
            control_tiers["standby"]["wait_p95_hours"] - base_tiers["standby"]["wait_p95_hours"]
        ),
        "standby_wait_max_hours": float(
            control_tiers["standby"]["wait_max_hours"] - base_tiers["standby"]["wait_max_hours"]
        ),
        "standby_advanced_job_count": float(standby_advanced),
        "standby_delayed_job_count": float(standby_delayed),
    }
    checks = {
        "running_unchanged": all(
            row.scheduled_start_slot == base_by_id[row.job_id].scheduled_start_slot
            and row.scheduled_end_slot == base_by_id[row.job_id].scheduled_end_slot
            for row in controlled_rows
            if row.state_at_issue == "RUNNING" and row.job_id in base_by_id
        ),
        "high_urgent_start_not_later": high_delay == 0,
        "standby_never_delays_high_or_normal": higher_tier_delay == 0,
        "normal_completed_jobs_not_lower": deltas["normal_completed_job_count"] >= 0.0,
        "normal_completed_GPU_hours_not_lower": deltas["normal_completed_GPU_hours"] >= 0.0,
        "normal_terminal_pending_GPU_hours_not_higher": deltas["normal_terminal_pending_GPU_hours"] <= 0.0,
        "mean_normal_wait_not_higher": deltas["normal_wait_mean_hours"] <= 0.0,
        "p95_normal_wait_not_higher": deltas["normal_wait_p95_hours"] <= 0.0,
        "max_normal_wait_not_higher": deltas["normal_wait_max_hours"] <= 0.0,
        "standby_completed_jobs_not_lower": deltas["standby_completed_job_count"] >= 0.0,
        "standby_completed_GPU_hours_not_lower": deltas["standby_completed_GPU_hours"] >= 0.0,
        "standby_terminal_pending_GPU_hours_not_higher": deltas["standby_terminal_pending_GPU_hours"] <= 0.0,
    }
    return ServiceGate(passed=all(checks.values()), checks=checks, deltas=deltas)


def target_gpu_profile(rows: Sequence[ScheduleRow]) -> np.ndarray:
    """Return the Apr-01 reservation GPU profile (96 15-minute slots)."""

    profile = np.zeros(96, dtype=float)
    offset = int((TARGET_START - ISSUE_TIME).total_seconds() // (SLOT_MINUTES * 60))
    for row in rows:
        left = max(row.scheduled_start_slot, offset)
        right = min(row.scheduled_end_slot, offset + 96)
        if left < right:
            profile[left - offset : right - offset] += row.requested_gpus
    return profile


def window_metrics(profile_kw: np.ndarray) -> dict[str, float]:
    values = np.asarray(profile_kw, dtype=float)
    if values.shape != (96,) or not np.isfinite(values).all():
        raise ValueError("V35R3A_POWER_PROFILE_AXIS")
    result: dict[str, float] = {}
    for name, slots in (("W1", W1), ("W3", W3), ("W5", W5)):
        selected = values[list(slots)]
        result[f"{name}_mean_kW"] = float(selected.mean())
        result[f"{name}_peak_kW"] = float(selected.max())
        result[f"{name}_energy_kWh"] = float(selected.sum() * SLOT_MINUTES / 60.0)
    return result


def minimum_sitefactor_for_pair(
    baseline_rank: Mapping[str, int],
    earlier_job: str,
    later_job: str,
) -> dict[str, int]:
    """Minimum integer L1 perturbation to put ``later_job`` first.

    Rank score is ``N-rank``.  Boosting only the later job by the score gap
    plus one is the unique deterministic minimum under lexical tie-breaking.
    """

    if earlier_job not in baseline_rank or later_job not in baseline_rank:
        raise KeyError("V35R3A_SITEFACTOR_JOB_MISSING")
    gap = int(baseline_rank[later_job]) - int(baseline_rank[earlier_job])
    if gap <= 0:
        return {earlier_job: 0, later_job: 0}
    return {earlier_job: 0, later_job: gap + 1}


def deterministic_control(
    baseline_rows: Sequence[ScheduleRow],
    running: Sequence[SchedulerJob],
    jobs: Sequence[SchedulerJob],
) -> tuple[list[ScheduleRow], list[dict[str, object]], list[dict[str, object]]]:
    """Search frozen-signal orderings without crossing service tiers.

    The electrical binding is incomplete, so the frozen Planning critical
    slot and W5 exposure are represented by aggregate requested-GPU power.
    No candidate is accepted unless this proxy improves *and* the tier-aware
    service gate passes.  Exact Planning rho remains an external limitation.
    """

    eligible = sorted(
        (
            job
            for job in jobs
            if job.workload_class in TEMPORAL_CONTROLLED_CLASSES and not job.protected
        ),
        key=lambda value: value.priority_key,
    )
    standby = [job for job in eligible if job.workload_class == STANDBY_QUEUE_CONTROLLED]
    trace: list[dict[str, object]] = []
    if len(standby) < 2:
        trace.append(
            {
                "iteration": 0,
                "candidate": "NONE",
                "accepted": False,
                "reason": "FEWER_THAN_TWO_STANDBY_QUEUE_CONTROLLED_JOBS",
                "eligible_job_count": len(eligible),
                "standby_eligible_job_count": len(standby),
                "service_gate_passed": True,
                "critical_slot_GPU": float(target_gpu_profile(baseline_rows)[CRITICAL_SLOT]),
                "W5_GPU_slots": float(target_gpu_profile(baseline_rows)[list(W5)].sum()),
            }
        )
        return [replace(row, policy="controlled") for row in baseline_rows], trace, []

    job_by_id = {job.job_id: job for job in jobs}
    baseline_standby_order = [
        row.job_id
        for row in sorted(
            (
                row
                for row in baseline_rows
                if row.state_at_issue == "PENDING"
                and row.job_id in job_by_id
                and job_by_id[row.job_id].workload_class == STANDBY_QUEUE_CONTROLLED
            ),
            key=lambda row: (row.priority_rank, row.job_id),
        )
    ]
    base_standby_rank = {
        job_id: rank for rank, job_id in enumerate(baseline_standby_order)
    }

    def objective(rows: Sequence[ScheduleRow]) -> tuple[float, float]:
        profile = target_gpu_profile(rows)
        return float(profile[CRITICAL_SLOT]), float(profile[list(W5)].sum())

    def candidate_orders(rows: Sequence[ScheduleRow]) -> list[tuple[str, list[str]]]:
        current = [
            row.job_id
            for row in sorted(
                (
                    row
                    for row in rows
                    if row.state_at_issue == "PENDING"
                    and row.job_id in job_by_id
                    and job_by_id[row.job_id].workload_class == STANDBY_QUEUE_CONTROLLED
                ),
                key=lambda row: (row.priority_rank, row.job_id),
            )
        ]
        alternatives: list[tuple[str, list[str]]] = [
            (
                "STANDBY_GPU_ASC_DURATION_ASC",
                sorted(
                    current,
                    key=lambda job_id: (
                        job_by_id[job_id].requested_gpus,
                        job_by_id[job_id].duration_slots,
                        job_by_id[job_id].submit_time,
                        job_id,
                    ),
                ),
            ),
            (
                "STANDBY_DURATION_ASC_GPU_ASC",
                sorted(
                    current,
                    key=lambda job_id: (
                        job_by_id[job_id].duration_slots,
                        job_by_id[job_id].requested_gpus,
                        job_by_id[job_id].submit_time,
                        job_id,
                    ),
                ),
            ),
            (
                "STANDBY_GPU_DESC_DURATION_DESC",
                sorted(
                    current,
                    key=lambda job_id: (
                        -job_by_id[job_id].requested_gpus,
                        -job_by_id[job_id].duration_slots,
                        job_by_id[job_id].submit_time,
                        job_id,
                    ),
                ),
            ),
        ]
        row_by_id = {row.job_id: row for row in rows}
        target_offset = int((TARGET_START - ISSUE_TIME).total_seconds() // (SLOT_MINUTES * 60))
        exposed = [
            job_id
            for job_id in current
            if row_by_id[job_id].scheduled_start_slot < target_offset + max(W5) + 1
            and row_by_id[job_id].scheduled_end_slot > target_offset + min(W5)
        ]
        later = [
            job_id
            for job_id in current
            if row_by_id[job_id].scheduled_start_slot >= target_offset + max(W5) + 1
        ]
        exposed.sort(key=lambda job_id: (-job_by_id[job_id].requested_gpus, job_id))
        later.sort(key=lambda job_id: (job_by_id[job_id].requested_gpus, job_id))
        position = {job_id: index for index, job_id in enumerate(current)}
        for left, right in zip(exposed[:24], later[:24]):
            swapped = list(current)
            a, b = position[left], position[right]
            swapped[a], swapped[b] = swapped[b], swapped[a]
            alternatives.append((f"STANDBY_W5_PAIR_SWAP:{left}:{right}", swapped))
        unique: list[tuple[str, list[str]]] = []
        seen: set[tuple[str, ...]] = set()
        for name, order in alternatives:
            key = tuple(order)
            if key != tuple(current) and key not in seen:
                seen.add(key)
                unique.append((name, order))
        return unique

    current_rows = [replace(row, policy="controlled") for row in baseline_rows]
    current_objective = objective(current_rows)
    for iteration in range(8):
        best: tuple[tuple[float, float, int, int, tuple[str, ...]], list[ScheduleRow], str, dict[str, int]] | None = None
        for name, standby_order in candidate_orders(current_rows):
            override = {job_id: rank for rank, job_id in enumerate(standby_order)}
            factors = {
                job_id: base_standby_rank[job_id] - rank
                for rank, job_id in enumerate(standby_order)
            }
            candidate_rows, _ = schedule_known_queue(
                running,
                jobs,
                policy="controlled",
                rank_override=override,
                sitefactor=factors,
            )
            gate = service_noninferiority(baseline_rows, candidate_rows)
            candidate_objective = objective(candidate_rows)
            current_standby_order = [
                row.job_id
                for row in sorted(
                    (
                        row
                        for row in current_rows
                        if row.state_at_issue == "PENDING"
                        and row.job_id in job_by_id
                        and job_by_id[row.job_id].workload_class == STANDBY_QUEUE_CONTROLLED
                    ),
                    key=lambda row: (row.priority_rank, row.job_id),
                )
            ]
            changed = sum(a != b for a, b in zip(current_standby_order, standby_order))
            l1 = sum(abs(value) for value in factors.values())
            improves = candidate_objective < current_objective
            trace.append(
                {
                    "iteration": iteration,
                    "candidate": name,
                    "accepted": False,
                    "reason": "ELIGIBLE" if gate.passed and improves else (
                        "SERVICE_GATE_FAIL" if not gate.passed else "NO_LEXICOGRAPHIC_GRID_IMPROVEMENT"
                    ),
                    "eligible_job_count": len(eligible),
                    "standby_eligible_job_count": len(standby),
                    "service_gate_passed": gate.passed,
                    "critical_slot_GPU": candidate_objective[0],
                    "W5_GPU_slots": candidate_objective[1],
                }
            )
            if not gate.passed or not improves:
                continue
            score = candidate_objective + (changed, l1, tuple(standby_order))
            if best is None or score < best[0]:
                best = score, candidate_rows, name, factors
        if best is None:
            break
        _, current_rows, accepted_name, _ = best
        current_objective = objective(current_rows)
        for row in reversed(trace):
            if row["iteration"] == iteration and row["candidate"] == accepted_name:
                row["accepted"] = True
                row["reason"] = "LEXICOGRAPHIC_IMPROVEMENT_ACCEPTED"
                break

    controlled_by_id = {row.job_id: row for row in current_rows}
    changes: list[dict[str, object]] = []
    for row in baseline_rows:
        controlled = controlled_by_id[row.job_id]
        if row.state_at_issue != "PENDING" or row.priority_rank == controlled.priority_rank:
            continue
        changes.append(
            {
                "job_id": row.job_id,
                "qos": row.qos,
                "workload_class": row.workload_class,
                "baseline_rank": row.priority_rank,
                "controlled_rank": controlled.priority_rank,
                "sitefactor": controlled.sitefactor,
                "changed_pair": f"{row.priority_rank}->{controlled.priority_rank}",
                "reason": "FROZEN_PLANNING_CRITICAL_EXPOSURE_ORDER",
            }
        )
    return current_rows, trace, changes
