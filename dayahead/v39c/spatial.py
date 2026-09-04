"""Exact site-only packing models for the frozen V39C capacity vector."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

import gurobipy as gp
from gurobipy import GRB

from dayahead.v39a.spatial import ActivityJob

from .contracts import SOLVER_SEED, SOLVER_THREADS, SLOTS


def _new_model(name: str) -> gp.Model:
    model = gp.Model(name)
    model.Params.OutputFlag = 0
    model.Params.Threads = SOLVER_THREADS
    model.Params.Seed = SOLVER_SEED
    model.Params.MIPGap = 0.0
    return model


def eligible_sites(site_capacity: Mapping[str, int], requested_gpu: int) -> tuple[str, ...]:
    return tuple(
        site for site in sorted(site_capacity)
        if int(site_capacity[site]) >= int(requested_gpu)
    )


def exact_slot_packing(
    jobs: Iterable[ActivityJob],
    site_capacity: Mapping[str, int],
    *,
    name: str,
    iis_path: Path | None = None,
) -> dict[str, Any]:
    rows = tuple(jobs)
    counts = Counter(job.requested_GPU for job in rows)
    model = _new_model(name)
    variables: dict[tuple[int, str], gp.Var] = {}
    for gpu, count in sorted(counts.items()):
        sites = eligible_sites(site_capacity, gpu)
        if not sites:
            return {
                "status": "INFEASIBLE_SLOT_LOCAL",
                "solver_status": int(GRB.INFEASIBLE),
                "reason": f"NO_AIDC_CAN_HOST_{gpu}GPU_GANG",
            }
        for site in sites:
            variables[gpu, site] = model.addVar(
                vtype=GRB.INTEGER, lb=0, ub=count,
                name=f"gang_count[{gpu},{site}]",
            )
        model.addConstr(
            gp.quicksum(variables[gpu, site] for site in sites) == count,
            name=f"all_gangs[{gpu}]",
        )
    for site in sorted(site_capacity):
        model.addConstr(
            gp.quicksum(
                gpu * variable
                for (gpu, candidate), variable in variables.items()
                if candidate == site
            ) <= site_capacity[site],
            name=f"AIDC_capacity[{site}]",
        )
    model.setObjective(0.0, GRB.MINIMIZE)
    model.optimize()
    result: dict[str, Any] = {
        "status": "FEASIBLE" if model.Status == GRB.OPTIMAL else "INFEASIBLE_SLOT_LOCAL",
        "solver_status": int(model.Status),
        "active_jobs": len(rows),
        "active_GPU": sum(job.requested_GPU for job in rows),
        "GPU_size_histogram": {
            str(gpu): count for gpu, count in sorted(counts.items())
        },
    }
    if model.Status == GRB.INFEASIBLE and iis_path is not None:
        model.computeIIS()
        iis_path.parent.mkdir(parents=True, exist_ok=True)
        model.write(str(iis_path))
        result["IIS_constraints"] = sorted(
            constraint.ConstrName
            for constraint in model.getConstrs()
            if constraint.IISConstr
        )
        result["IIS_path"] = iis_path.as_posix()
    model.dispose()
    return result


def interval_spatial_feasibility(
    jobs: Iterable[ActivityJob],
    site_capacity: Mapping[str, int],
    *,
    name: str,
    iis_path: Path | None = None,
) -> dict[str, Any]:
    rows = tuple(jobs)
    groups: dict[tuple[int, int, int], list[str]] = defaultdict(list)
    for job in rows:
        groups[(job.requested_GPU, job.active_start_slot, job.active_end_slot)].append(
            job.job_uid
        )
    keys = sorted(groups)
    model = _new_model(name)
    variables: dict[tuple[int, str], gp.Var] = {}
    eligible: dict[int, tuple[str, ...]] = {}
    for index, (gpu, start, end) in enumerate(keys):
        eligible[index] = eligible_sites(site_capacity, gpu)
        if not eligible[index]:
            return {
                "status": "INFEASIBLE",
                "solver_status": int(GRB.INFEASIBLE),
                "reason": f"NO_AIDC_CAN_HOST_{gpu}GPU_GANG",
            }
        count = len(groups[gpu, start, end])
        for site in eligible[index]:
            variables[index, site] = model.addVar(
                vtype=GRB.INTEGER, lb=0, ub=count,
                name=f"interval_count[{index},{site}]",
            )
        model.addConstr(
            gp.quicksum(variables[index, site] for site in eligible[index]) == count,
            name=f"all_intervals[{index}]",
        )
    for site in sorted(site_capacity):
        for slot in range(SLOTS):
            model.addConstr(
                gp.quicksum(
                    keys[index][0] * variables[index, site]
                    for index in range(len(keys))
                    if site in eligible[index]
                    and keys[index][1] <= slot < keys[index][2]
                ) <= site_capacity[site],
                name=f"AIDC_capacity[{site},{slot}]",
            )
    model.setObjective(0.0, GRB.MINIMIZE)
    model.optimize()
    result: dict[str, Any] = {
        "status": "OPTIMAL" if model.Status == GRB.OPTIMAL else "INFEASIBLE",
        "solver_status": int(model.Status),
        "active_job_count": len(rows),
        "cohort_count": len(keys),
    }
    if model.Status == GRB.INFEASIBLE and iis_path is not None:
        model.computeIIS()
        iis_path.parent.mkdir(parents=True, exist_ok=True)
        model.write(str(iis_path))
        result["IIS_constraints"] = sorted(
            constraint.ConstrName
            for constraint in model.getConstrs()
            if constraint.IISConstr
        )
        result["IIS_path"] = iis_path.as_posix()
    model.dispose()
    return result


def causal_day_placement(
    jobs: Iterable[ActivityJob],
    site_capacity: Mapping[str, int],
    existing_state: Mapping[str, str],
    *,
    name: str,
) -> dict[str, Any]:
    """Place one D-1-visible day while preserving supplied RUNNING state."""

    rows = tuple(jobs)
    model = _new_model(name)
    variables: dict[tuple[str, str], gp.Var] = {}
    candidates: dict[str, tuple[str, ...]] = {}
    fixed: dict[str, str] = {}
    for job in rows:
        candidates[job.job_uid] = eligible_sites(site_capacity, job.requested_GPU)
        if not candidates[job.job_uid]:
            return {"status": "INFEASIBLE", "reason": "NO_ELIGIBLE_AIDC"}
        if job.job_uid in existing_state:
            fixed[job.job_uid] = str(existing_state[job.job_uid])
            if fixed[job.job_uid] not in candidates[job.job_uid]:
                return {
                    "status": "INFEASIBLE",
                    "reason": f"CARRIED_AIDC_CANNOT_HOST_GANG:{job.job_uid}",
                }
            continue
        for site in candidates[job.job_uid]:
            variables[job.job_uid, site] = model.addVar(
                vtype=GRB.BINARY, name=f"place[{job.job_uid},{site}]"
            )
        model.addConstr(
            gp.quicksum(
                variables[job.job_uid, site] for site in candidates[job.job_uid]
            ) == 1,
            name=f"one_AIDC[{job.job_uid}]",
        )
    for site in sorted(site_capacity):
        for slot in range(SLOTS):
            fixed_gpu = sum(
                job.requested_GPU
                for job in rows
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
                load <= site_capacity[site], name=f"AIDC_capacity[{site},{slot}]"
            )
    # Stage C asks only whether a causal state chain exists.  A zero objective
    # avoids introducing a new load-balancing policy; one thread and a frozen
    # seed make the feasibility witness reproducible.
    model.setObjective(0.0, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        status = int(model.Status)
        model.dispose()
        return {"status": "INFEASIBLE", "solver_status": status}
    selected = dict(fixed)
    for job in rows:
        if job.job_uid not in selected:
            selected[job.job_uid] = next(
                site for site in candidates[job.job_uid]
                if variables[job.job_uid, site].X > 0.5
            )
    assignments = [
        {
            "job_uid": job.job_uid,
            "state_at_issue": job.state_at_issue,
            "requested_GPU": job.requested_GPU,
            "active_start_slot": job.active_start_slot,
            "active_end_slot": job.active_end_slot,
            "initial_AIDC": None if job.job_uid in fixed else selected[job.job_uid],
            "current_AIDC": selected[job.job_uid],
            "source_AIDC": selected[job.job_uid] if job.job_uid in fixed else None,
            "destination_AIDC": selected[job.job_uid],
            "migration_selected": False,
        }
        for job in rows
    ]
    result = {
        "status": "OPTIMAL",
        "solver_status": int(model.Status),
        "assignments": assignments,
        "new_initial_placements": len(rows) - len(fixed),
        "carried_placements": len(fixed),
        "daily_remap_count": 0,
        "migration_count": 0,
        "gang_split_count": 0,
    }
    model.dispose()
    return result


__all__ = [
    "causal_day_placement", "eligible_sites", "exact_slot_packing",
    "interval_spatial_feasibility",
]
