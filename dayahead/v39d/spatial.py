"""Feasibility-only Rack-aware spatial models for V39D.

The model never changes a temporal interval.  Logical Rack variables are an
exact feasibility oracle; only the selected AIDC is exposed to the DA freeze.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import math
from typing import Any, Iterable, Mapping

import gurobipy as gp
from gurobipy import GRB

from dayahead.v38.authority import CapacityAuthority
from dayahead.v39a.spatial import ActivityJob

from .contracts import SLOTS, SOLVER_SEED, SOLVER_THREADS


def _model(name: str) -> gp.Model:
    model = gp.Model(name)
    model.Params.OutputFlag = 0
    model.Params.Threads = SOLVER_THREADS
    model.Params.Seed = SOLVER_SEED
    model.Params.MIPGap = 0.0
    return model


def _site_number(site: str) -> int:
    return int(site.removeprefix("AIDC"))


def _compatible_pools(
    capacity: CapacityAuthority, gpu: int, site: str | None = None,
) -> tuple[str, ...]:
    rows = (
        pool for pool in capacity.rack_pools
        if pool.historical_gpu_capacity + 1e-9 >= gpu
        and capacity.site_capacity[pool.aidc_id] >= gpu
        and (site is None or pool.aidc_id == site)
    )
    return tuple(sorted(pool.rack_pool_id for pool in rows))


def build_common_initial_state(
    running_jobs: Iterable[tuple[str, int]],
    site_capacity: Mapping[str, int],
    site_prior: Mapping[str, float],
    *,
    name: str,
) -> dict[str, Any]:
    """Build one policy-blind synthetic RUNNING state before DA evaluation.

    Stable weighted rendezvous home preferences use only job UID and the frozen
    V22SR1 prior.  A deterministic large-gang-first repair enforces the frozen
    site capacities.  No RW/RSP schedule or electrical result is accepted by
    this interface.
    """

    running = tuple(sorted(
        ((str(job_uid), int(gpu)) for job_uid, gpu in running_jobs),
        key=lambda row: row[0],
    ))
    if len({row[0] for row in running}) != len(running):
        raise ValueError("V39D_INITIAL_RUNNING_DUPLICATE")
    if set(site_prior) != set(site_capacity):
        raise ValueError("V39D_INITIAL_PRIOR_AXIS")
    if any(gpu <= 0 for _job_uid, gpu in running):
        raise ValueError("V39D_INITIAL_GPU")

    version = "V39D_STABLE_HOME_V22SR1_PRIOR_V1"

    def preference(job_uid: str, gpu: int) -> tuple[str, ...]:
        eligible = tuple(
            site for site in sorted(site_capacity)
            if int(site_capacity[site]) >= gpu
        )
        scored: list[tuple[float, int, str]] = []
        for site in eligible:
            digest = hashlib.sha256(
                f"{version}:{job_uid}:{site}".encode("utf-8")
            ).digest()
            integer = int.from_bytes(digest[:8], "big")
            uniform = (integer + 1) / (2**64 + 1)
            score = -math.log(uniform) / float(site_prior[site])
            scored.append((score, _site_number(site), site))
        return tuple(row[2] for row in sorted(scored))

    preferences = {
        job_uid: preference(job_uid, gpu) for job_uid, gpu in running
    }
    remaining = {site: int(value) for site, value in site_capacity.items()}
    state: dict[str, str] = {}
    initialization_class: dict[str, str] = {}
    # Large gangs are reserved first so the deterministic repair cannot create
    # a false infeasibility through small-job fragmentation.  UID is the stable
    # tie-break within a gang size and numeric AIDC breaks equal preferences.
    for job_uid, gpu in sorted(running, key=lambda row: (-row[1], row[0])):
        selected = next(
            (site for site in preferences[job_uid] if remaining[site] >= gpu),
            None,
        )
        if selected is None:
            return {
                "status": "INFEASIBLE",
                "reason": f"POLICY_BLIND_CAPACITY_REPAIR_FAILED:{job_uid}:{gpu}",
            }
        state[job_uid] = selected
        remaining[selected] -= gpu
        initialization_class[job_uid] = (
            "STABLE_HOME_PREFERENCE"
            if selected == preferences[job_uid][0]
            else "DETERMINISTIC_CAPACITY_REPAIR"
        )
    return {
        "status": "OPTIMAL",
        "state": state,
        "initialization_class": initialization_class,
        "method": "STABLE_WEIGHTED_HOME_PREFERENCE_THEN_DETERMINISTIC_CAPACITY_REPAIR",
        "home_preference_version": version,
        "deterministic_tie_break": "LARGE_GANG_FIRST_THEN_JOB_UID_ASCENDING;AIDC_NUMERIC_ON_EQUAL_SCORE",
        "optimization_objective_used": False,
        "peak_utilization_objective_used": False,
        "grid_reads": 0,
        "Fresh_reads": 0,
        "RW_future_schedule_reads": 0,
        "RSP_future_schedule_reads": 0,
        "previous_day_result_reads": 0,
        "remaining_capacity_GPU": remaining,
    }


def plan_fixed_temporal_schedule(
    jobs: Iterable[ActivityJob],
    capacity: CapacityAuthority,
    initial_state: Mapping[str, str],
    *,
    name: str,
    allow_running_migration: bool,
    wan_authority: Any | None = None,
) -> dict[str, Any]:
    """Place a frozen schedule with exact site/Rack feasibility.

    When migration is enabled, the sole primary objective is the count of
    RUNNING jobs whose destination AIDC differs from the common source state.
    """

    if allow_running_migration and wan_authority is None:
        raise ValueError("V39D_WAN_REQUIRED_FOR_MIGRATION")
    rows = tuple(jobs)
    missing = sorted(
        job.job_uid for job in rows
        if job.state_at_issue == "RUNNING" and job.job_uid not in initial_state
    )
    if missing:
        return {"status": "INFEASIBLE", "reason": f"MISSING_INITIAL_STATE:{missing[0]}"}

    pool_site = {pool.rack_pool_id: pool.aidc_id for pool in capacity.rack_pools}
    pool_cap = {
        pool.rack_pool_id: float(pool.historical_gpu_capacity)
        for pool in capacity.rack_pools
    }
    cohorts: dict[tuple[str, str | None, int, int, int], list[ActivityJob]] = defaultdict(list)
    for job in rows:
        source = (
            str(initial_state[job.job_uid])
            if job.state_at_issue == "RUNNING" else None
        )
        cohorts[(
            job.state_at_issue, source, job.requested_GPU,
            job.active_start_slot, job.active_end_slot,
        )].append(job)
    keys = tuple(sorted(cohorts, key=lambda k: (k[0], k[1] or "", k[2], k[3], k[4])))
    model = _model(name)
    variables: dict[tuple[tuple[str, str | None, int, int, int], str], gp.Var] = {}
    candidates: dict[tuple[str, str | None, int, int, int], tuple[str, ...]] = {}
    for index, key in enumerate(keys):
        _state, source, gpu, _start, _end = key
        fixed_site = None if allow_running_migration or source is None else source
        candidates[key] = _compatible_pools(capacity, gpu, fixed_site)
        if not candidates[key]:
            model.dispose()
            return {"status": "INFEASIBLE", "reason": f"NO_COMPATIBLE_RACK:{key}"}
        for rack in candidates[key]:
            variables[key, rack] = model.addVar(
                vtype=GRB.INTEGER, lb=0, ub=len(cohorts[key]),
                name=f"cohort[{index},{rack}]",
            )
        model.addConstr(
            gp.quicksum(variables[key, rack] for rack in candidates[key])
            == len(cohorts[key]),
            name=f"all_cohort[{index}]",
        )
    for site, site_cap in sorted(capacity.site_capacity.items()):
        for slot in range(SLOTS):
            model.addConstr(
                gp.quicksum(
                    key[2] * variables[key, rack]
                    for key in keys for rack in candidates[key]
                    if pool_site[rack] == site and key[3] <= slot < key[4]
                ) <= site_cap,
                name=f"site_capacity[{site},{slot}]",
            )
    for rack, rack_cap in sorted(pool_cap.items()):
        for slot in range(SLOTS):
            model.addConstr(
                gp.quicksum(
                    key[2] * variables[key, rack]
                    for key in keys if (key, rack) in variables
                    and key[3] <= slot < key[4]
                ) <= rack_cap,
                name=f"rack_capacity[{rack},{slot}]",
            )

    migration_terms: list[gp.LinExpr | gp.Var] = []
    transfer_terms: list[gp.LinExpr | gp.Var] = []
    if allow_running_migration:
        for key in keys:
            _state, source, gpu, _start, _end = key
            if source is None:
                continue
            stay = gp.quicksum(
                variables[key, rack] for rack in candidates[key]
                if pool_site[rack] == source
            )
            migration_terms.append(len(cohorts[key]) - stay)
            for rack in candidates[key]:
                destination = pool_site[rack]
                if destination == source:
                    continue
                payload = int(wan_authority.payload_bytes(gpu))
                capacity_bytes = int(
                    wan_authority.path_capacity_bytes(source, destination, 2)
                )
                slots = (payload + capacity_bytes - 1) // capacity_bytes
                transfer_terms.append(slots * variables[key, rack])
        model.addConstr(
            gp.quicksum(transfer_terms) <= 93,
            name="serialized_fixed_path_WAN_slot_budget",
        )
    migration_objective = gp.quicksum(migration_terms)
    destination_tie_break = gp.quicksum(
        _site_number(pool_site[rack]) * variables[key, rack]
        for key in keys for rack in candidates[key]
    )
    if allow_running_migration:
        model.setObjectiveN(migration_objective, 0, priority=2, name="minimum_RUNNING_migrations")
        model.setObjectiveN(destination_tie_break, 1, priority=1, name="numeric_AIDC_tie_break")
    else:
        model.setObjective(destination_tie_break, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        status = int(model.Status)
        model.dispose()
        return {"status": "INFEASIBLE", "solver_status": status}

    assignments: list[dict[str, Any]] = []
    for key in keys:
        available: list[str] = []
        for rack in sorted(candidates[key], key=lambda r: (pool_site[r], r)):
            available.extend([rack] * int(round(variables[key, rack].X)))
        members = sorted(cohorts[key], key=lambda job: job.job_uid)
        if len(available) != len(members):
            raise RuntimeError("V39D_COHORT_MATERIALIZATION")
        for job, rack in zip(members, available, strict=True):
            source = key[1]
            destination = pool_site[rack]
            migrated = source is not None and destination != source
            assignments.append({
                "job_uid": job.job_uid,
                "state_at_issue": job.state_at_issue,
                "requested_GPU": job.requested_GPU,
                "active_start_slot": job.active_start_slot,
                "active_end_slot": job.active_end_slot,
                "initial_AIDC": destination if source is None else source,
                "current_AIDC": destination,
                "source_AIDC": source,
                "destination_AIDC": destination,
                "migration_selected": migrated,
                "oracle_rack_pool_id": rack,
            })
    assignments.sort(key=lambda row: row["job_uid"])
    migration_count = sum(bool(row["migration_selected"]) for row in assignments)
    primary_value = float(model.ObjNVal) if allow_running_migration else 0.0
    model.dispose()
    return {
        "status": "OPTIMAL",
        "solver_status": int(GRB.OPTIMAL),
        "assignments": assignments,
        "minimum_running_migrations": migration_count,
        "PENDING_initial_placements": sum(
            row["state_at_issue"] == "PENDING" for row in assignments
        ),
        "objective": (
            "MINIMIZE_NUMBER_OF_RUNNING_MIGRATIONS"
            if allow_running_migration else "ZERO_FEASIBILITY_WITH_DETERMINISTIC_TIE_BREAK"
        ),
        "solver_proven_optimum": True,
        "primary_objective_value": primary_value,
        "RSP_schedule_mutation_inside_migration_stage": 0,
        "gang_split_count": 0,
        "rack_compatibility_oracle": "PASS",
    }


__all__ = ["build_common_initial_state", "plan_fixed_temporal_schedule"]
