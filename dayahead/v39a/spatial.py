"""Causal AIDC state contracts and fail-closed spatial feasibility models.

The May feasibility proof deliberately begins with a relaxation: every job may
select a new AIDC for each day and temporal mode, while remaining an
indivisible gang during its contiguous execution interval.  This relaxation
removes all cross-day carry and WAN restrictions.  Infeasibility of the
relaxation therefore proves infeasibility of the stricter causal V39A model.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping

import gurobipy as gp
from gurobipy import GRB
import numpy as np
import pandas as pd

from dayahead.v38.authority import CapacityAuthority, load_capacity_authority

from .contracts import (
    ARTIFACT_ROOT,
    EXPECTED_DATES,
    GPU_CAPACITY,
    SITE_CAPACITY,
    SLOTS,
    TARGET_OFFSET_SLOTS,
    TEMPORAL_MODES,
    V37_DAY_ROOT,
)


@dataclass(frozen=True)
class ActivityJob:
    job_uid: str
    state_at_issue: str
    requested_GPU: int
    active_start_slot: int
    active_end_slot: int


@dataclass(frozen=True)
class PlacementDecision:
    job_uid: str
    state_at_issue: str
    requested_GPU: int
    initial_AIDC: str | None
    current_AIDC: str
    source_AIDC: str | None
    destination_AIDC: str
    migration_selected: bool


@dataclass(frozen=True)
class CausalDayPlan:
    status: str
    decisions: tuple[PlacementDecision, ...]
    next_running_state: Mapping[str, str]
    daily_remap_count: int
    migration_count: int


def _rank(job_uid: str, aidc: str) -> int:
    raw = hashlib.sha256(f"V39A:{job_uid}:{aidc}".encode()).hexdigest()
    return int(raw[:12], 16)


def production_activity(schedule: pd.DataFrame) -> tuple[ActivityJob, ...]:
    """Map frozen V37 120-slot schedule coordinates to production slots."""

    required = {
        "job_id", "state_at_issue", "requested_gpus",
        "scheduled_start_slot", "scheduled_end_slot",
    }
    missing = sorted(required - set(schedule.columns))
    if missing:
        raise RuntimeError(f"V39A_V37_SCHEDULE_COLUMNS:{missing}")
    jobs: list[ActivityJob] = []
    for row in schedule.itertuples(index=False):
        start = max(TARGET_OFFSET_SLOTS, int(row.scheduled_start_slot))
        end = min(TARGET_OFFSET_SLOTS + SLOTS, int(row.scheduled_end_slot))
        if start >= end:
            continue
        gpu_float = float(row.requested_gpus)
        gpu = int(round(gpu_float))
        if gpu <= 0 or abs(gpu_float - gpu) > 1e-9:
            raise RuntimeError(f"V39A_NONINTEGER_GPU_GANG:{row.job_id}")
        state = str(row.state_at_issue)
        if state not in {"RUNNING", "PENDING"}:
            raise RuntimeError(f"V39A_JOB_STATE:{row.job_id}:{state}")
        jobs.append(ActivityJob(
            str(row.job_id), state, gpu,
            start - TARGET_OFFSET_SLOTS, end - TARGET_OFFSET_SLOTS,
        ))
    if len({job.job_uid for job in jobs}) != len(jobs):
        raise RuntimeError("V39A_DUPLICATE_ACTIVE_JOB")
    return tuple(jobs)


def active_gpu_profile(jobs: Iterable[ActivityJob]) -> np.ndarray:
    profile = np.zeros(SLOTS, dtype=np.int64)
    for job in jobs:
        profile[job.active_start_slot:job.active_end_slot] += job.requested_GPU
    if np.any(profile < 0) or np.any(profile > GPU_CAPACITY):
        raise RuntimeError("V39A_V37_AGGREGATE_GPU_PROFILE")
    return profile


def _eligible_sites(
    capacity: CapacityAuthority, requested_gpu: int,
) -> tuple[str, ...]:
    return tuple(
        site for site in capacity.aidc_ids
        if capacity.site_capacity[site] >= requested_gpu
        and capacity.eligible_racks(site, requested_gpu)
    )


def plan_causal_day(
    jobs: Iterable[ActivityJob],
    capacity: CapacityAuthority,
    previous_running_state: Mapping[str, str],
) -> CausalDayPlan:
    """Plan one synthetic day without changing a carried RUNNING location.

    PENDING jobs receive an initial placement with no source and no WAN move.
    A RUNNING job present in ``previous_running_state`` is fixed at its
    ``current_AIDC``.  A newly observed RUNNING job is explicitly initialized
    from the current cutoff only; it is never represented as measured site
    provenance.
    """

    rows = tuple(jobs)
    model = gp.Model("V39A_CAUSAL_DAY_PLACEMENT")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 20260904
    variables: dict[tuple[str, str], gp.Var] = {}
    eligible: dict[str, tuple[str, ...]] = {}
    fixed: dict[str, str] = {}
    for job in rows:
        candidates = _eligible_sites(capacity, job.requested_GPU)
        if not candidates:
            raise RuntimeError(f"V39A_NO_RACK_GANG_FIT:{job.job_uid}")
        eligible[job.job_uid] = candidates
        if job.state_at_issue == "RUNNING" and job.job_uid in previous_running_state:
            site = str(previous_running_state[job.job_uid])
            if site not in candidates:
                raise RuntimeError(f"V39A_CARRIED_AIDC_GANG_FIT:{job.job_uid}")
            fixed[job.job_uid] = site
            continue
        for site in candidates:
            variables[job.job_uid, site] = model.addVar(
                vtype=GRB.BINARY, name=f"place[{job.job_uid},{site}]"
            )
        model.addConstr(
            gp.quicksum(variables[job.job_uid, site] for site in candidates) == 1,
            name=f"one_AIDC[{job.job_uid}]",
        )
    peak = model.addVar(lb=0.0, name="peak_normalized_site_utilization")
    for site in capacity.aidc_ids:
        for slot in range(SLOTS):
            fixed_gpu = sum(
                job.requested_GPU for job in rows
                if fixed.get(job.job_uid) == site
                and job.active_start_slot <= slot < job.active_end_slot
            )
            selected_gpu = gp.quicksum(
                job.requested_GPU * variables[job.job_uid, site]
                for job in rows
                if (job.job_uid, site) in variables
                and job.active_start_slot <= slot < job.active_end_slot
            )
            load = fixed_gpu + selected_gpu
            model.addConstr(
                load <= capacity.site_capacity[site],
                name=f"site_capacity[{site},{slot}]",
            )
            model.addConstr(load <= peak * capacity.site_capacity[site])
    model.setObjectiveN(peak, 0, priority=2)
    model.setObjectiveN(gp.quicksum(
        ((_rank(uid, site) % 1_000_003) + 1) * variable
        for (uid, site), variable in variables.items()
    ), 1, priority=1)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        return CausalDayPlan("INFEASIBLE", (), dict(previous_running_state), 0, 0)
    selected: dict[str, str] = dict(fixed)
    for job in rows:
        if job.job_uid not in selected:
            selected[job.job_uid] = next(
                site for site in eligible[job.job_uid]
                if variables[job.job_uid, site].X > 0.5
            )
    decisions: list[PlacementDecision] = []
    for job in rows:
        carried = job.state_at_issue == "RUNNING" and job.job_uid in fixed
        site = selected[job.job_uid]
        decisions.append(PlacementDecision(
            job_uid=job.job_uid,
            state_at_issue=job.state_at_issue,
            requested_GPU=job.requested_GPU,
            initial_AIDC=site if not carried else None,
            current_AIDC=site,
            source_AIDC=site if carried else None,
            destination_AIDC=site,
            migration_selected=False,
        ))
    next_state = {
        job.job_uid: selected[job.job_uid]
        for job in rows if job.state_at_issue == "RUNNING"
    }
    return CausalDayPlan("OPTIMAL", tuple(decisions), next_state, 0, 0)


def _build_relaxed_interval_model(
    jobs: tuple[ActivityJob, ...],
    capacity: CapacityAuthority,
    model_name: str,
) -> tuple[gp.Model, list[tuple[int, int, int]], Mapping[int, tuple[str, ...]]]:
    groups: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    for job in jobs:
        groups[(job.requested_GPU, job.active_start_slot, job.active_end_slot)].append(
            job.job_uid
        )
    keys = sorted(groups)
    model = gp.Model(model_name)
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 20260904
    model.Params.MIPGap = 0.0
    variables: dict[tuple[int, str], gp.Var] = {}
    eligible: dict[int, tuple[str, ...]] = {}
    for index, (gpu, start, end) in enumerate(keys):
        eligible[index] = _eligible_sites(capacity, gpu)
        if not eligible[index]:
            raise RuntimeError(f"V39A_NO_RACK_GANG_FIT:{gpu}")
        for site in eligible[index]:
            variables[index, site] = model.addVar(
                vtype=GRB.INTEGER,
                lb=0,
                ub=len(groups[gpu, start, end]),
                name=f"gang_count[{index},{site}]",
            )
        model.addConstr(
            gp.quicksum(variables[index, site] for site in eligible[index])
            == len(groups[gpu, start, end]),
            name=f"gang_interval[{index}]",
        )
    for site in capacity.aidc_ids:
        for slot in range(SLOTS):
            model.addConstr(gp.quicksum(
                keys[index][0] * variables[index, site]
                for index in range(len(keys))
                if site in eligible[index]
                and keys[index][1] <= slot < keys[index][2]
            ) <= capacity.site_capacity[site], name=f"site_capacity[{site},{slot}]")
    model.setObjective(0.0, GRB.MINIMIZE)
    return model, keys, eligible


def solve_relaxed_interval_day(
    jobs: tuple[ActivityJob, ...],
    capacity: CapacityAuthority,
    *,
    operating_day: str,
    temporal_mode: str,
    iis_path: Path | None = None,
) -> dict[str, Any]:
    """Solve a per-day relaxation; optionally persist its exact Gurobi IIS."""

    model, keys, _eligible = _build_relaxed_interval_model(
        jobs, capacity, f"V39A_RELAXED_{operating_day}_{temporal_mode}"
    )
    model.optimize()
    payload: dict[str, Any] = {
        "operating_day": operating_day,
        "temporal_mode": temporal_mode,
        "active_job_count": len(jobs),
        "cohort_count": len(keys),
        "solver_status": int(model.Status),
        "solver_status_name": (
            "OPTIMAL" if model.Status == GRB.OPTIMAL
            else "INFEASIBLE" if model.Status == GRB.INFEASIBLE
            else f"STATUS_{model.Status}"
        ),
        "relaxation": (
            "DAY_AND_MODE_INDEPENDENT_AIDC_SELECTION; NO_CROSS_DAY_CARRY; "
            "NO_WAN_LIMIT; ONE_AIDC_PER_CONTIGUOUS_EXECUTION_INTERVAL"
        ),
    }
    if model.Status == GRB.INFEASIBLE and iis_path is not None:
        model.computeIIS()
        iis_path.parent.mkdir(parents=True, exist_ok=True)
        model.write(str(iis_path))
        text = iis_path.read_text(encoding="utf-8")
        iis_path.write_text(
            "\n".join(line.rstrip() for line in text.splitlines()) + "\n",
            encoding="utf-8", newline="\n",
        )
        constraints = sorted(
            constraint.ConstrName for constraint in model.getConstrs()
            if constraint.IISConstr
        )
        group_rows = []
        for name in constraints:
            if name.startswith("gang_interval["):
                index = int(name.split("[", 1)[1].split("]", 1)[0])
                gpu, start, end = keys[index]
                group_rows.append({
                    "constraint": name,
                    "requested_GPU": gpu,
                    "active_start_slot": start,
                    "active_end_slot": end,
                })
        payload.update({
            "IIS_path": str(iis_path),
            "IIS_constraint_count": len(constraints),
            "IIS_constraints": constraints,
            "IIS_gang_intervals": group_rows,
        })
    return payload


def hard_gang_cardinality_conflicts(
    jobs: tuple[ActivityJob, ...], capacity: CapacityAuthority,
) -> list[dict[str, Any]]:
    """Find slot-local contradictions that survive arbitrary per-slot remap."""

    result: list[dict[str, Any]] = []
    sizes = sorted({job.requested_GPU for job in jobs})
    for slot in range(SLOTS):
        active = [
            job for job in jobs
            if job.active_start_slot <= slot < job.active_end_slot
        ]
        counts = Counter(job.requested_GPU for job in active)
        for gang in sizes:
            hostable = sum(
                capacity.site_capacity[site] // gang
                for site in _eligible_sites(capacity, gang)
            )
            if counts[gang] > hostable:
                result.append({
                    "slot": slot,
                    "requested_GPU": gang,
                    "active_gang_count": counts[gang],
                    "maximum_hostable_gang_count": hostable,
                    "excess_gang_count": counts[gang] - hostable,
                    "eligible_AIDCs": list(_eligible_sites(capacity, gang)),
                })
    return result


def scan_may_relaxation(repo: Path) -> dict[str, Any]:
    """Validate all V37 inputs and solve all 62 relaxed day/mode models."""

    capacity = load_capacity_authority(repo)
    if dict(capacity.site_capacity) != SITE_CAPACITY:
        raise RuntimeError("V39A_SITE_CAPACITY_AUTHORITY_DRIFT")
    records: list[dict[str, Any]] = []
    hard_conflicts: list[dict[str, Any]] = []
    iis_written = False
    iis_path = repo / ARTIFACT_ROOT / "V39A_SPATIAL_FEASIBILITY_IIS.ilp"
    for day in EXPECTED_DATES:
        trajectory = pd.read_parquet(
            repo / V37_DAY_ROOT / day / "V37_R4A_GPU_IT_TRAJECTORY.parquet"
        )
        for mode in TEMPORAL_MODES:
            schedule = pd.read_parquet(
                repo / V37_DAY_ROOT / day / f"V37_R4A_{mode}_SCHEDULE.parquet"
            )
            jobs = production_activity(schedule)
            profile = active_gpu_profile(jobs)
            expected = trajectory[
                "N_active_RW" if mode == "RW" else "N_active_RSP"
            ].to_numpy(dtype=np.int64)
            if not np.array_equal(profile, expected):
                raise RuntimeError(f"V39A_V37_SCHEDULE_PROFILE_DRIFT:{day}:{mode}")
            conflicts = hard_gang_cardinality_conflicts(jobs, capacity)
            for row in conflicts:
                hard_conflicts.append({
                    "operating_day": day, "temporal_mode": mode, **row,
                })
            result = solve_relaxed_interval_day(
                jobs, capacity, operating_day=day, temporal_mode=mode,
                iis_path=iis_path if not iis_written else None,
            )
            if result["solver_status_name"] == "INFEASIBLE" and not iis_written:
                iis_written = True
            records.append(result)
    infeasible = [
        row for row in records if row["solver_status_name"] == "INFEASIBLE"
    ]
    return {
        "status": "FAIL" if infeasible else "PASS",
        "solver": "GUROBI",
        "solver_threads": 1,
        "solver_seed": 20260904,
        "models_built": len(records),
        "models_optimal": len(records) - len(infeasible),
        "models_infeasible": len(infeasible),
        "infeasible_day_modes": [
            {key: row[key] for key in (
                "operating_day", "temporal_mode", "solver_status",
                "solver_status_name", "active_job_count", "cohort_count",
            )}
            for row in infeasible
        ],
        "first_IIS": next(
            (row for row in records if "IIS_constraint_count" in row), None
        ),
        "hard_slot_local_gang_cardinality_conflicts": hard_conflicts,
        "hard_conflict_count": len(hard_conflicts),
        "hard_conflict_days": sorted({row["operating_day"] for row in hard_conflicts}),
        "model_results": records,
    }


__all__ = [
    "ActivityJob", "CausalDayPlan", "PlacementDecision", "active_gpu_profile",
    "hard_gang_cardinality_conflicts", "plan_causal_day", "production_activity",
    "scan_may_relaxation", "solve_relaxed_interval_day",
]
