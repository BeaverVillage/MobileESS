"""Exact site-only packing models for the frozen V39C capacity vector."""

from __future__ import annotations

from collections import Counter, defaultdict
import math
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
    stay_only: bool = True,
    objective: str = "ZERO",
    wan_authority: Any | None = None,
    migration_slot_budget: int = 93,
) -> dict[str, Any]:
    """Place one D-1-visible day under STAY-only or migration-enabled state.

    The migration-enabled feasibility solve retains a literal zero objective.
    A separate witness solve may minimize RUNNING moves.  The WAN budget is an
    exact conservative serialization bound for the frozen V38 contract: all
    transfers wait until slot 2, use immutable OD paths, and finish by slot 95
    so READY plus the one-slot restart completes at the horizon boundary.
    """

    if objective not in {"ZERO", "MIN_RUNNING_MIGRATIONS"}:
        raise ValueError(f"V39C_UNKNOWN_STAGE_C_OBJECTIVE:{objective}")
    if not stay_only and wan_authority is None:
        raise ValueError("V39C_MIGRATION_ENABLED_REQUIRES_WAN_AUTHORITY")

    rows = tuple(jobs)
    # Jobs are exactly exchangeable inside one causal cohort.  Aggregating by
    # state/source/gang/interval removes binary symmetry while preserving every
    # site-capacity, migration-count, and WAN-budget equation.  Job identities
    # are restored deterministically after optimization.
    cohort_members: dict[
        tuple[str, str | None, int, int, int], list[ActivityJob]
    ] = defaultdict(list)
    for job in rows:
        source = (
            str(existing_state[job.job_uid])
            if job.state_at_issue == "RUNNING" and job.job_uid in existing_state
            else None
        )
        cohort_members[
            (
                job.state_at_issue,
                source,
                job.requested_GPU,
                job.active_start_slot,
                job.active_end_slot,
            )
        ].append(job)
    cohort_keys = sorted(
        cohort_members,
        key=lambda key: (key[0], key[1] or "", key[2], key[3], key[4]),
    )
    model = _new_model(name)
    variables: dict[tuple[tuple[str, str | None, int, int, int], str], gp.Var] = {}
    candidates: dict[tuple[str, str | None, int, int, int], tuple[str, ...]] = {}
    fixed_cohorts: dict[tuple[str, str | None, int, int, int], str] = {}
    for index, key in enumerate(cohort_keys):
        _state, source, gpu, _start, _end = key
        candidates[key] = eligible_sites(site_capacity, gpu)
        if not candidates[key]:
            return {"status": "INFEASIBLE", "reason": "NO_ELIGIBLE_AIDC"}
        if source is not None and source not in candidates[key]:
            return {
                "status": "INFEASIBLE",
                "reason": f"CARRIED_AIDC_CANNOT_HOST_GANG:{source}:{gpu}",
            }
        if stay_only and source is not None:
            fixed_cohorts[key] = source
            continue
        count = len(cohort_members[key])
        for site in candidates[key]:
            variables[key, site] = model.addVar(
                vtype=GRB.INTEGER,
                lb=0,
                ub=count,
                name=f"causal_cohort[{index},{site}]",
            )
            if source is not None:
                variables[key, site].Start = float(count if site == source else 0)
        model.addConstr(
            gp.quicksum(variables[key, site] for site in candidates[key]) == count,
            name=f"all_causal_cohort[{index}]",
        )
    for site in sorted(site_capacity):
        for slot in range(SLOTS):
            fixed_gpu = sum(
                key[2] * len(cohort_members[key])
                for key, fixed_site in fixed_cohorts.items()
                if fixed_site == site and key[3] <= slot < key[4]
            )
            selected_gpu = gp.quicksum(
                key[2] * variables[key, site]
                for key in cohort_keys
                if (key, site) in variables and key[3] <= slot < key[4]
            )
            model.addConstr(
                fixed_gpu + selected_gpu <= site_capacity[site],
                name=f"AIDC_capacity[{site},{slot}]",
            )
    migration_terms: list[gp.LinExpr | gp.Var] = []
    migration_slot_terms: list[gp.LinExpr | gp.Var] = []
    if not stay_only:
        for key in cohort_keys:
            _state, source, gpu, _start, _end = key
            if source is None:
                continue
            migration_terms.append(
                len(cohort_members[key]) - variables[key, source]
            )
            payload = int(wan_authority.payload_bytes(gpu))
            for destination in candidates[key]:
                if destination == source:
                    continue
                required_slots = math.ceil(
                    payload
                    / int(wan_authority.path_capacity_bytes(source, destination, 2))
                )
                migration_slot_terms.append(
                    required_slots * variables[key, destination]
                )
        model.addConstr(
            gp.quicksum(migration_slot_terms) <= migration_slot_budget,
            name="serialized_fixed_path_WAN_slot_budget",
        )
    migration_objective = gp.quicksum(migration_terms)
    if objective == "ZERO":
        # C1 is a pure feasibility gate.  Start hints prefer the carried source
        # but are not an objective and do not force migration variables to 0.
        model.setObjective(0.0, GRB.MINIMIZE)
    else:
        # The first objective is a solver-proven RUNNING-migration minimum.
        # PENDING/newly observed initial placements have no migration term.
        model.setObjective(migration_objective, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        status = int(model.Status)
        model.dispose()
        return {"status": "INFEASIBLE", "solver_status": status}
    selected: dict[str, str] = {}
    for key in cohort_keys:
        if key in fixed_cohorts:
            available_sites = [fixed_cohorts[key]] * len(cohort_members[key])
        else:
            available_sites = []
            for site in candidates[key]:
                available_sites.extend(
                    [site] * int(round(variables[key, site].X))
                )
        members = sorted(cohort_members[key], key=lambda job: job.job_uid)
        if len(available_sites) != len(members):
            raise RuntimeError(f"V39C_CAUSAL_COHORT_MATERIALIZATION:{key}")
        for job, site in zip(members, available_sites, strict=True):
            selected[job.job_uid] = site
    assignments = []
    for job in rows:
        source = (
            str(existing_state[job.job_uid])
            if job.state_at_issue == "RUNNING" and job.job_uid in existing_state
            else None
        )
        destination = selected[job.job_uid]
        migrated = source is not None and source != destination
        transfer_slots = 0
        if migrated:
            transfer_slots = math.ceil(
                int(wan_authority.payload_bytes(job.requested_GPU))
                / int(wan_authority.path_capacity_bytes(source, destination, 2))
            )
        assignments.append({
            "job_uid": job.job_uid,
            "state_at_issue": job.state_at_issue,
            "requested_GPU": job.requested_GPU,
            "active_start_slot": job.active_start_slot,
            "active_end_slot": job.active_end_slot,
            "initial_AIDC": destination if source is None else None,
            "current_AIDC": destination,
            "source_AIDC": source,
            "destination_AIDC": destination,
            "migration_selected": migrated,
            "migration_transfer_slots_required": transfer_slots,
        })
    migration_count = sum(row["migration_selected"] for row in assignments)
    result = {
        "status": "OPTIMAL",
        "solver_status": int(model.Status),
        "assignments": assignments,
        "new_initial_placements": sum(row["source_AIDC"] is None for row in assignments),
        "carried_placements": sum(row["source_AIDC"] is not None for row in assignments),
        "daily_remap_count": 0,
        "migration_count": migration_count,
        "migration_transfer_slots_required": sum(
            row["migration_transfer_slots_required"] for row in assignments
        ),
        "migration_allowed": not stay_only,
        "migration_forced": False,
        "objective": objective,
        "gang_split_count": 0,
    }
    model.dispose()
    return result


__all__ = [
    "causal_day_placement", "eligible_sites", "exact_slot_packing",
    "interval_spatial_feasibility",
]
