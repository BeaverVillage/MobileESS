"""RW-anchored common synthetic initial AIDC state construction."""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

import gurobipy as gp
from gurobipy import GRB

from dayahead.v38.authority import CapacityAuthority, canonical_sha256
from dayahead.v39a.spatial import ActivityJob

from .contracts import SLOTS, SOLVER_SEED, SOLVER_THREADS


def _eligible_sites(
    capacity: CapacityAuthority, requested_gpu: int,
) -> tuple[str, ...]:
    return tuple(
        site for site in capacity.aidc_ids
        if int(capacity.site_capacity[site]) >= requested_gpu
        and capacity.eligible_racks(site, requested_gpu)
    )


def build_rw_anchored_initial_state(
    running_jobs: Iterable[tuple[str, int]],
    rw_jobs: Iterable[ActivityJob],
    capacity: CapacityAuthority,
    *,
    name: str,
) -> dict[str, Any]:
    """Create one common state from the causal RW reference feasibility set.

    Every D-1-visible RUNNING job participates in the snapshot-capacity gate.
    Every active RW job participates in the 96-slot site-capacity gate.  Rack
    rows are used only as single-gang compatibility labels and are never
    summed as physical site inventory.
    """

    running = tuple(sorted(
        ((str(job_uid), int(gpu)) for job_uid, gpu in running_jobs),
        key=lambda row: row[0],
    ))
    active = tuple(sorted(rw_jobs, key=lambda row: row.job_uid))
    running_gpu = dict(running)
    if len(running_gpu) != len(running):
        raise ValueError("V39E_DUPLICATE_RUNNING_JOB")
    if any(gpu <= 0 for gpu in running_gpu.values()):
        raise ValueError("V39E_INVALID_RUNNING_GPU")
    active_by_uid = {job.job_uid: job for job in active}
    if len(active_by_uid) != len(active):
        raise ValueError("V39E_DUPLICATE_RW_JOB")
    for job in active:
        if job.state_at_issue == "RUNNING":
            if job.job_uid not in running_gpu:
                raise ValueError(f"V39E_RW_RUNNING_NOT_D1_VISIBLE:{job.job_uid}")
            if running_gpu[job.job_uid] != job.requested_GPU:
                raise ValueError(f"V39E_RW_RUNNING_GPU_MISMATCH:{job.job_uid}")

    # D-1 RUNNING jobs outside the D-day production horizon remain part of the
    # snapshot state but impose no D-day active-slot load.
    records: list[tuple[str, str, int, int | None, int | None]] = [
        (
            job_uid,
            "RUNNING",
            gpu,
            active_by_uid[job_uid].active_start_slot if job_uid in active_by_uid else None,
            active_by_uid[job_uid].active_end_slot if job_uid in active_by_uid else None,
        )
        for job_uid, gpu in running
    ]
    records.extend(
        (
            job.job_uid,
            "PENDING",
            job.requested_GPU,
            job.active_start_slot,
            job.active_end_slot,
        )
        for job in active if job.state_at_issue == "PENDING"
    )
    if len({row[0] for row in records}) != len(records):
        raise ValueError("V39E_RW_RECORD_DUPLICATE")

    cohorts: dict[tuple[str, int, int | None, int | None], list[str]] = defaultdict(list)
    for uid, state, gpu, start, end in records:
        cohorts[state, gpu, start, end].append(uid)
    keys = tuple(sorted(
        cohorts,
        key=lambda key: (
            key[0], key[1], -1 if key[2] is None else key[2],
            -1 if key[3] is None else key[3],
        ),
    ))

    model = gp.Model(name)
    model.Params.OutputFlag = 0
    model.Params.Threads = SOLVER_THREADS
    model.Params.Seed = SOLVER_SEED
    model.Params.MIPGap = 0.0
    variables: dict[tuple[int, str], gp.Var] = {}
    candidates: dict[int, tuple[str, ...]] = {}
    for index, key in enumerate(keys):
        candidates[index] = _eligible_sites(capacity, key[1])
        if not candidates[index]:
            model.dispose()
            return {
                "status": "INFEASIBLE",
                "reason": f"NO_COMPATIBLE_AIDC_FOR_{key[1]}GPU_GANG",
            }
        for site in candidates[index]:
            variables[index, site] = model.addVar(
                vtype=GRB.INTEGER,
                lb=0,
                ub=len(cohorts[key]),
                name=f"cohort[{index},{site}]",
            )
        model.addConstr(
            gp.quicksum(variables[index, site] for site in candidates[index])
            == len(cohorts[key]),
            name=f"all_jobs[{index}]",
        )

    for site in capacity.aidc_ids:
        model.addConstr(
            gp.quicksum(
                keys[index][1] * variables[index, site]
                for index in range(len(keys))
                if keys[index][0] == "RUNNING" and site in candidates[index]
            ) <= int(capacity.site_capacity[site]),
            name=f"D1_snapshot_capacity[{site}]",
        )
        for slot in range(SLOTS):
            model.addConstr(
                gp.quicksum(
                    keys[index][1] * variables[index, site]
                    for index in range(len(keys))
                    if site in candidates[index]
                    and keys[index][2] is not None
                    and int(keys[index][2]) <= slot < int(keys[index][3])
                ) <= int(capacity.site_capacity[site]),
                name=f"RW_site_capacity[{site},{slot}]",
            )

    model.setObjective(0.0, GRB.MINIMIZE)
    model.optimize()
    feasibility_status = int(model.Status)
    if feasibility_status != GRB.OPTIMAL:
        model.dispose()
        return {
            "status": "INFEASIBLE",
            "solver_status": feasibility_status,
            "reason": "RW_ANCHORED_SITE_RACK_FEASIBILITY_FAILED",
        }

    assignment: dict[str, str] = {}
    for index, key in enumerate(keys):
        available: list[str] = []
        for site in candidates[index]:
            available.extend([site] * int(round(variables[index, site].X)))
        members = sorted(cohorts[key])
        if len(available) != len(members):
            raise RuntimeError("V39E_COHORT_MATERIALIZATION_COUNT")
        for uid, site in zip(members, available, strict=True):
            assignment[uid] = site
    model.dispose()

    witness = []
    snapshot_load = {site: 0 for site in capacity.aidc_ids}
    slot_load = {site: [0] * SLOTS for site in capacity.aidc_ids}
    for uid, state, gpu, start, end in records:
        site = assignment[uid]
        rack = sorted(
            pool.rack_pool_id for pool in capacity.eligible_racks(site, gpu)
        )[0]
        if state == "RUNNING":
            snapshot_load[site] += gpu
        if start is not None and end is not None:
            for slot in range(start, end):
                slot_load[site][slot] += gpu
        witness.append({
            "job_uid": uid,
            "state_at_issue": state,
            "requested_GPU": gpu,
            "destination_AIDC": site,
            "compatible_logical_Rack_label": rack,
            "active_start_slot": start,
            "active_end_slot": end,
        })
    site_violations = sum(
        snapshot_load[site] > int(capacity.site_capacity[site])
        for site in capacity.aidc_ids
    ) + sum(
        value > int(capacity.site_capacity[site])
        for site in capacity.aidc_ids for value in slot_load[site]
    )
    if site_violations:
        raise RuntimeError("V39E_POSTMATERIALIZATION_SITE_CAPACITY_VIOLATION")
    witness.sort(key=lambda row: row["job_uid"])
    initial_state = {
        uid: assignment[uid] for uid in sorted(running_gpu)
    }
    return {
        "status": "PASS",
        "feasibility_objective": "ZERO",
        "deterministic_materialization": (
            "ZERO_OBJECTIVE_FIXED_ORDER_SINGLE_THREAD_FIXED_SEED_THEN_JOB_UID"
        ),
        "initial_state": initial_state,
        "initial_state_SHA256": canonical_sha256(initial_state),
        "RW_witness": witness,
        "RW_witness_SHA256": canonical_sha256(witness),
        "D1_snapshot_load_GPU": snapshot_load,
        "maximum_RW_load_GPU_by_AIDC": {
            site: max(values) for site, values in slot_load.items()
        },
        "site_capacity_violations": 0,
        "rack_compatibility_failures": 0,
        "gang_split_count": 0,
        "rack_capacity_summed_as_site_capacity": False,
        "RW_schedule_mutation_count": 0,
        "RSP_reads": 0,
        "Actual_reads": 0,
        "Fresh_reads": 0,
        "grid_Actual_reads": 0,
        "migration_result_reads": 0,
        "previous_simulated_day_reads": 0,
    }


__all__ = ["build_rw_anchored_initial_state"]
