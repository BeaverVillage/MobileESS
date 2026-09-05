"""V39E fixed-temporal AIDC placement under non-additive Rack semantics."""

from __future__ import annotations

from collections import defaultdict
from collections import Counter
import hashlib
from pathlib import Path
from typing import Any, Iterable, Mapping

import gurobipy as gp
from gurobipy import GRB
import numpy as np
import pandas as pd

from dayahead.v28r2.c1_affine import exact_c1_pcc_kw, load_c1
from dayahead.v28r2.source_cache import day_root
from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY
from dayahead.v38.authority import CapacityAuthority, canonical_sha256
from dayahead.v37.context import load_day_context
from dayahead.v37r3.voltage_authority import joint_repaired_coefficients
from dayahead.v39a.power import site_it_power_kw
from dayahead.v39a.spatial import ActivityJob

from .contracts import GUROBI_THREADS_PER_MODEL, SLOTS, SOLVER_SEED


def _site_number(site: str) -> int:
    return int(site.removeprefix("AIDC"))


def _compatible_sites(
    capacity: CapacityAuthority, gpu: int, fixed_site: str | None = None,
) -> tuple[str, ...]:
    return tuple(
        site for site in capacity.aidc_ids
        if (fixed_site is None or site == fixed_site)
        and int(capacity.site_capacity[site]) >= gpu
        and bool(capacity.eligible_racks(site, gpu))
    )


def _add_frozen_planning_voltage_constraints(
    model: gp.Model,
    active_gpu_expressions: Mapping[tuple[int, str], gp.LinExpr],
    capacity: CapacityAuthority,
    repo: Path,
    operating_day: str,
) -> None:
    """Wire the accepted D-1 planning-voltage authority into AIDC placement.

    C1 is represented exactly at every integer active-GPU value with a PWL
    equality. Since every cohort variable is integer, no scientific
    approximation is introduced at any feasible placement.
    """

    _data, electrical = load_day_context(repo, operating_day)
    try:
        coefficients = joint_repaired_coefficients(repo, electrical)
        controls = tuple(map(str, electrical.voltage["control_names"]))
    finally:
        electrical.voltage.close()
        electrical.current.close()
    sites = tuple(capacity.aidc_ids)
    if controls[:len(sites)] != tuple(f"aidc_load_kw[{site}]" for site in sites):
        raise RuntimeError("V39E_PLANNING_AIDC_CONTROL_AXIS")
    if len(coefficients) != SLOTS:
        raise RuntimeError("V39E_PLANNING_VOLTAGE_SLOT_AXIS")

    weather = pd.read_parquet(
        day_root(SOURCE_DATA_REPOSITORY, operating_day) / "gfs_d1_weather.parquet"
    )
    if len(weather) != SLOTS:
        raise RuntimeError("V39E_PLANNING_WEATHER_SLOT_AXIS")
    c1 = load_c1(
        repo / "dayahead/artifacts/v24t_thermal_aware_aidc/"
        "V24T_C1_QUASISTATIC_MODEL.json"
    )
    pcc: dict[tuple[int, str], gp.Var] = {}
    for slot in range(SLOTS):
        wetbulb = float(weather.iloc[slot]["t_wb_c"])
        humidity = float(weather.iloc[slot]["rh_pct"])
        for site in sites:
            site_capacity = int(capacity.site_capacity[site])
            active = model.addVar(
                vtype=GRB.INTEGER, lb=0, ub=site_capacity,
                name=f"planning_active_GPU[{site},{slot}]",
            )
            model.addConstr(
                active == active_gpu_expressions[slot, site],
                name=f"planning_active_GPU_link[{site},{slot}]",
            )
            x_values = list(range(site_capacity + 1))
            it_values = np.asarray([
                float(site_it_power_kw(site_capacity, gpu)) for gpu in x_values
            ])
            p_values = np.asarray(
                exact_c1_pcc_kw(it_values, wetbulb, humidity, c1), dtype=float
            )
            pcc[slot, site] = model.addVar(
                lb=float(p_values.min()), ub=float(p_values.max()),
                name=f"planning_PCC_P_kW[{site},{slot}]",
            )
            model.addGenConstrPWL(
                active, pcc[slot, site], x_values, p_values.tolist(),
                name=f"frozen_C1_integer_exact[{site},{slot}]",
            )

    lower = (0.95 - 1.0e-7) ** 2
    upper = (1.05 + 1.0e-7) ** 2
    for slot, coefficient in enumerate(coefficients):
        constant = np.asarray(coefficient.voltage_constant, dtype=float)
        matrix = np.asarray(coefficient.voltage_matrix, dtype=float)
        if matrix.shape[0] < len(sites) or matrix.shape[1] != len(constant):
            raise RuntimeError("V39E_PLANNING_VOLTAGE_MATRIX_AXIS")
        for node in range(len(constant)):
            voltage_squared = float(constant[node]) + gp.quicksum(
                float(matrix[site_index, node]) * pcc[slot, site]
                for site_index, site in enumerate(sites)
            )
            model.addRange(
                voltage_squared, lower, upper,
                name=f"frozen_planning_voltage[{slot},{node}]",
            )


def plan_fixed_temporal_schedule(
    jobs: Iterable[ActivityJob],
    capacity: CapacityAuthority,
    initial_state: Mapping[str, str],
    *,
    name: str,
    allow_running_migration: bool,
    wan_authority: Any | None = None,
    planning_repo: Path | None = None,
    operating_day: str | None = None,
    compute_iis: bool = False,
) -> dict[str, Any]:
    """Place fixed intervals while treating Rack rows as labels, not inventory."""

    if allow_running_migration and wan_authority is None:
        raise ValueError("V39E_WAN_REQUIRED_FOR_MIGRATION")
    if (planning_repo is None) != (operating_day is None):
        raise ValueError("V39E_PLANNING_AUTHORITY_ARGUMENT_PAIR")
    rows = tuple(jobs)
    missing = sorted(
        job.job_uid for job in rows
        if job.state_at_issue == "RUNNING" and job.job_uid not in initial_state
    )
    if missing:
        return {"status": "INFEASIBLE", "reason": f"MISSING_INITIAL_STATE:{missing[0]}"}

    cohorts: dict[
        tuple[str, str | None, int, int, int], list[ActivityJob]
    ] = defaultdict(list)
    for job in rows:
        source = str(initial_state[job.job_uid]) if job.state_at_issue == "RUNNING" else None
        cohorts[(
            job.state_at_issue, source, job.requested_GPU,
            job.active_start_slot, job.active_end_slot,
        )].append(job)
    keys = tuple(sorted(
        cohorts, key=lambda key: (key[0], key[1] or "", key[2], key[3], key[4])
    ))

    model = gp.Model(name)
    model.Params.OutputFlag = 0
    model.Params.Threads = GUROBI_THREADS_PER_MODEL
    model.Params.Seed = SOLVER_SEED
    model.Params.MIPGap = 0.0
    variables: dict[tuple[int, str], gp.Var] = {}
    candidates: dict[int, tuple[str, ...]] = {}
    for index, key in enumerate(keys):
        _state, source, gpu, _start, _end = key
        fixed = None if allow_running_migration or source is None else source
        candidates[index] = _compatible_sites(capacity, gpu, fixed)
        if not candidates[index]:
            model.dispose()
            return {
                "status": "INFEASIBLE",
                "reason": f"NO_COMPATIBLE_AIDC:{key}",
            }
        for site in candidates[index]:
            variables[index, site] = model.addVar(
                vtype=GRB.INTEGER, lb=0, ub=len(cohorts[key]),
                name=f"cohort[{index},{site}]",
            )
        model.addConstr(
            gp.quicksum(variables[index, site] for site in candidates[index])
            == len(cohorts[key]),
            name=f"all_cohort[{index}]",
        )

    # The frozen V39C site capacity is the sole additive GPU ceiling.
    for site in capacity.aidc_ids:
        for slot in range(SLOTS):
            model.addConstr(
                gp.quicksum(
                    keys[index][2] * variables[index, site]
                    for index in range(len(keys))
                    if site in candidates[index]
                    and keys[index][3] <= slot < keys[index][4]
                ) <= int(capacity.site_capacity[site]),
                name=f"site_capacity[{site},{slot}]",
            )

    if planning_repo is not None and operating_day is not None:
        active_gpu_expressions = {
            (slot, site): gp.quicksum(
                keys[index][2] * variables[index, site]
                for index in range(len(keys))
                if site in candidates[index]
                and keys[index][3] <= slot < keys[index][4]
            )
            for slot in range(SLOTS) for site in capacity.aidc_ids
        }
        _add_frozen_planning_voltage_constraints(
            model, active_gpu_expressions, capacity,
            planning_repo.resolve(), operating_day,
        )

    migration_terms: list[gp.LinExpr | gp.Var] = []
    transfer_terms: list[gp.LinExpr | gp.Var] = []
    if allow_running_migration:
        for index, key in enumerate(keys):
            _state, source, gpu, _start, _end = key
            if source is None:
                continue
            stay = gp.quicksum(
                variables[index, site] for site in candidates[index] if site == source
            )
            migration_terms.append(len(cohorts[key]) - stay)
            for site in candidates[index]:
                if site == source:
                    continue
                payload = int(wan_authority.payload_bytes(gpu))
                capacity_bytes = int(wan_authority.path_capacity_bytes(source, site, 2))
                slots = (payload + capacity_bytes - 1) // capacity_bytes
                transfer_terms.append(slots * variables[index, site])
        model.addConstr(
            gp.quicksum(transfer_terms) <= 93,
            name="serialized_fixed_path_WAN_slot_budget",
        )

    if allow_running_migration:
        model.setObjectiveN(
            gp.quicksum(migration_terms), 0, priority=2,
            name="minimum_RUNNING_migrations",
        )
        model.setObjectiveN(
            gp.quicksum(
                _site_number(site) * variables[index, site]
                for index in range(len(keys)) for site in candidates[index]
            ),
            1, priority=1, name="numeric_AIDC_tie_break",
        )
    else:
        model.setObjective(0.0, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        status = int(model.Status)
        diagnostics: dict[str, Any] = {}
        if status == GRB.INFEASIBLE and planning_repo is not None and compute_iis:
            model.computeIIS()
            constraint_names = sorted(
                constraint.ConstrName for constraint in model.getConstrs()
                if constraint.IISConstr
            )
            general_names = sorted(
                constraint.GenConstrName for constraint in model.getGenConstrs()
                if constraint.IISGenConstr
            )
            families = Counter(
                value.split("[", 1)[0]
                for value in (*constraint_names, *general_names)
            )
            diagnostic_root = (
                planning_repo / "dayahead/artifacts/v39e_full_may_2025/diagnostics"
            )
            diagnostic_root.mkdir(parents=True, exist_ok=True)
            iis_path = diagnostic_root / f"{name}_IIS.ilp"
            model.write(str(iis_path))
            digest = hashlib.sha256(iis_path.read_bytes()).hexdigest()
            diagnostics = {
                "IIS_path": str(iis_path.relative_to(planning_repo)).replace("\\", "/"),
                "IIS_SHA256": digest,
                "IIS_linear_constraint_count": len(constraint_names),
                "IIS_general_constraint_count": len(general_names),
                "IIS_constraint_families": dict(sorted(families.items())),
                "IIS_linear_constraints": constraint_names,
                "IIS_general_constraints": general_names,
            }
        model.dispose()
        return {
            "status": "INFEASIBLE", "solver_status": status,
            **diagnostics,
        }

    assignments: list[dict[str, Any]] = []
    for index, key in enumerate(keys):
        available: list[str] = []
        for site in candidates[index]:
            available.extend([site] * int(round(variables[index, site].X)))
        members = sorted(cohorts[key], key=lambda job: job.job_uid)
        if len(available) != len(members):
            raise RuntimeError("V39E_COHORT_MATERIALIZATION")
        for job, site in zip(members, available, strict=True):
            source = key[1]
            rack_label = sorted(
                pool.rack_pool_id
                for pool in capacity.eligible_racks(site, job.requested_GPU)
            )[0]
            assignments.append({
                "job_uid": job.job_uid,
                "state_at_issue": job.state_at_issue,
                "requested_GPU": job.requested_GPU,
                "active_start_slot": job.active_start_slot,
                "active_end_slot": job.active_end_slot,
                "initial_AIDC": site if source is None else source,
                "current_AIDC": site,
                "source_AIDC": source,
                "destination_AIDC": site,
                "migration_selected": source is not None and site != source,
                "logical_Rack_compatibility_label": rack_label,
            })
    assignments.sort(key=lambda row: row["job_uid"])
    migration_count = sum(bool(row["migration_selected"]) for row in assignments)
    model.dispose()
    return {
        "status": "OPTIMAL",
        "solver_status": int(GRB.OPTIMAL),
        "assignments": assignments,
        "assignment_SHA256": canonical_sha256(assignments),
        "minimum_running_migrations": migration_count,
        "PENDING_initial_placements": sum(
            row["state_at_issue"] == "PENDING" for row in assignments
        ),
        "objective": (
            "MINIMIZE_NUMBER_OF_RUNNING_MIGRATIONS"
            if allow_running_migration else "ZERO_FEASIBILITY"
        ),
        "secondary_tie_break": (
            "DETERMINISTIC_AIDC_NUMERIC_ID" if allow_running_migration
            else "FIXED_ORDER_FIXED_SEED_DETERMINISTIC_GUROBI"
        ),
        "solver_proven_optimum": True,
        "RSP_schedule_mutation_inside_migration_stage": 0,
        "gang_split_count": 0,
        "rack_authority_semantics": (
            "SYNTHETIC_NON_ADDITIVE_LOGICAL_RACK_COMPATIBILITY_ENVELOPE"
        ),
        "rack_capacity_summed_as_site_capacity": False,
        "capacity_created_by_rack_layer_GPU": 0,
        "frozen_planning_voltage_constraints": planning_repo is not None,
    }


def deterministic_rack_labels(
    assignments: Iterable[Mapping[str, Any]], capacity: CapacityAuthority,
) -> dict[str, Any]:
    """Materialize stable compatibility labels without additive Rack loads."""

    output: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in sorted(assignments, key=lambda item: str(item["job_uid"])):
        site = str(row["destination_AIDC"])
        gpu = int(row["requested_GPU"])
        candidates = sorted(
            pool.rack_pool_id for pool in capacity.eligible_racks(site, gpu)
        )
        if not candidates:
            failures.append({
                "job_uid": str(row["job_uid"]),
                "frozen_AIDC": site,
                "requested_GPU": gpu,
                "reason": "NO_COMPATIBLE_LOGICAL_RACK_LABEL",
            })
            continue
        output.append({
            "job_uid": str(row["job_uid"]),
            "destination_AIDC": site,
            "rack_pool_id": candidates[0],
            "requested_GPU": gpu,
            "active_start_slot": int(row["active_start_slot"]),
            "active_end_slot": int(row["active_end_slot"]),
            "assignment_method": "STABLE_FIRST_COMPATIBLE_LOGICAL_RACK_LABEL",
        })
    return {
        "status": "PASS" if not failures else "FAIL_CLOSED",
        "method": "STABLE_FIRST_COMPATIBLE_LOGICAL_RACK_LABEL",
        "assignments": output,
        "assignment_SHA256": canonical_sha256(output),
        "failures": failures,
        "failure_count": len(failures),
        "rack_capacity_summed_as_site_capacity": False,
        "capacity_created_by_rack_layer_GPU": 0,
        "DA_selected_AIDC_mutation_count": 0,
        "DA_selected_time_mutation_count": 0,
    }


__all__ = ["deterministic_rack_labels", "plan_fixed_temporal_schedule"]
