"""Experimental E2 Stage-1 with endogenous grid-effective headroom.

Only frozen planning sensitivities are used.  This module contains no Actual or
Fresh/OpenDSS dependency.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row
from dayahead.v28r2.schedule_freeze import _schedule
from dayahead.v28r2.solver_payload import payload_from_registry
from dayahead.v28r2.solver_runner import add_grid_rows
from dayahead.v28r2.variable_registry import build_resource_model, value


PRIMARY_TOL = 1e-6
SERVICE_TOL = 1e-7
LEVERAGE_TOL = 1e-9


@dataclass(frozen=True)
class E2Stage1Result:
    schedule: Mapping[str, object]
    rack_headroom_96x48: np.ndarray
    site_headroom_96x12: np.ndarray
    primary_objective: float
    leverage_objective: float
    displacement_nodeh: float
    service_parity_max_shortfall_nodeh: float
    terminal_backlog_worsening_max_nodeh: float
    solver_iterations: int
    runtime_seconds: float


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def frozen_leverage_map(current: object, voltage: object, current_path: Path, voltage_path: Path) -> dict[str, object]:
    branch_names = tuple(map(str, current["branch_names"]))
    controls = tuple(map(str, current["control_names"]))
    expected = tuple(f"aidc_load_kw[AIDC{i:02d}]" for i in range(1, 13))
    if controls[:12] != expected or controls != tuple(map(str, voltage["control_names"])):
        raise RuntimeError("V33X_LEVERAGE_CONTROL_AXIS")
    monitored = np.asarray([not is_dominated_mess_current_row(name) for name in branch_names])
    sensitivity = np.asarray(current["current_sensitivity_pu_per_control"], dtype=float)[:, :12, :]
    leverage = np.max(np.abs(sensitivity[:, :, monitored]), axis=2).T
    voltage_sensitivity = np.asarray(voltage["sensitivity"], dtype=float)[:, :12, :]
    voltage_leverage = np.max(np.abs(voltage_sensitivity), axis=2).T
    if leverage.shape != (12, 96) or np.any(leverage <= 0):
        raise RuntimeError("V33X_LEVERAGE_AXIS_OR_SIGN")
    payload = {
        "artifact_id": "V33X_E2_LEVERAGE_MAP_V1",
        "status": "FROZEN_BEFORE_E2_AND_FRESH",
        "shape": [12, 96],
        "site_order": list(expected),
        "slot_order": list(range(96)),
        "formula": "max_over_supported_line_phase(abs(d_normalized_current_loading/d_P_AIDC_i))",
        "fresh_inputs": 0,
        "current_sensitivity_source_sha256": sha256_file(current_path),
        "voltage_sensitivity_source_sha256": sha256_file(voltage_path),
        "supported_line_phase_count": int(monitored.sum()),
        "excluded_dominated_MESS_transformer_rows": int((~monitored).sum()),
        "line_phase_set": [name for name, keep in zip(branch_names, monitored, strict=True) if keep],
        "L_site_slot": leverage.tolist(),
        "voltage_headroom_reporting_metric": voltage_leverage.tolist(),
    }
    payload["map_sha256"] = canonical_sha256(payload)
    return payload


def solve_e2_stage1(
    data: object,
    context: object,
    voltage: object,
    current: object,
    case: str,
    e1_schedule: Mapping[str, object],
    leverage_map: np.ndarray,
    leverage_sha: str,
) -> E2Stage1Result:
    import gurobipy as gp
    from gurobipy import GRB

    if case not in {"B1", "B3"}:
        raise ValueError("V33X_E2_CASE")
    leverage = np.asarray(leverage_map, dtype=float)
    if leverage.shape != (12, 96):
        raise ValueError("V33X_E2_LEVERAGE_AXIS")
    started = time.perf_counter()
    registry = build_resource_model(data, voltage, case, rho_aidc=1.0, rho_mess=0.10)
    add_grid_rows(registry, context, voltage, current)
    model = registry.model
    mess_ids = tuple(sorted(data.mess_records))
    frozen_p = np.asarray(e1_schedule["mess_p_kw"], dtype=float)
    frozen_q = np.asarray(e1_schedule["mess_q_kvar"], dtype=float)
    for slot in range(96):
        for index, mess in enumerate(mess_ids):
            model.addConstr(registry.mess_p[(mess, slot)] == float(frozen_p[slot, index]), name=f"v33x_frozen_mess_p[{mess},{slot}]")
            model.addConstr(registry.mess_q[(mess, slot)] == float(frozen_q[slot, index]), name=f"v33x_frozen_mess_q[{mess},{slot}]")

    rack_index = {rack: index for index, rack in enumerate(data.rack_ids)}
    site_index = {site: index for index, site in enumerate(data.aidc_ids)}
    h: dict[tuple[str, int], object] = {}
    for rack in data.rack_ids:
        r = rack_index[rack]
        available = np.maximum(0.0, (float(data.rack_gpu_capacity[r]) - np.asarray(data.delta.g_res_plan_gpu[r], dtype=float)) * 0.25 / 4.0)
        for slot in range(96):
            h[(rack, slot)] = model.addVar(lb=0.0, name=f"v33x_h_REC[{rack},{slot}]")
            model.addConstr(
                gp.quicksum(registry.x[(cohort, rack, slot)] for cohort in data.cohort_ids) + h[(rack, slot)] <= float(available[slot]),
                name=f"v33x_headroom_capacity[{rack},{slot}]",
            )

    e1_x = np.asarray(e1_schedule["workload_service_tensor"], dtype=float)
    for cohort_index, cohort in enumerate(data.cohort_ids):
        model.addConstr(
            gp.quicksum(registry.x[(cohort, rack, slot)] for rack in data.rack_ids for slot in range(96))
            >= float(e1_x[cohort_index].sum()) - SERVICE_TOL,
            name=f"v33x_service_parity_cohort[{cohort}]",
        )
    model.addConstr(
        gp.quicksum(registry.x.values()) >= float(e1_x.sum()) - SERVICE_TOL,
        name="v33x_service_parity_total",
    )
    model.update()
    model.setObjective(registry.eta, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V33X_E2_PRIMARY_STATUS:{case}:{model.Status}")
    primary = float(value(registry.eta))
    model.addConstr(registry.eta <= primary + PRIMARY_TOL, name="v33x_primary_objective_parity")

    leverage_expression = gp.quicksum(
        float(leverage[site_index[owner], slot]) * h[(rack, slot)]
        for rack, owner in zip(data.rack_ids, data.rack_aidc, strict=True)
        for slot in range(96)
    )
    model.setObjective(leverage_expression, GRB.MAXIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V33X_E2_HEADROOM_STATUS:{case}:{model.Status}")
    leverage_optimum = float(leverage_expression.getValue())
    model.addConstr(leverage_expression >= leverage_optimum - LEVERAGE_TOL, name="v33x_grid_effective_headroom_parity")

    deviation: dict[tuple[str, int], object] = {}
    e1_allocation = e1_x.sum(axis=0).T
    for rack in data.rack_ids:
        r = rack_index[rack]
        for slot in range(96):
            variable = model.addVar(lb=0.0, name=f"v33x_allocation_deviation[{rack},{slot}]")
            allocation = gp.quicksum(registry.x[(cohort, rack, slot)] for cohort in data.cohort_ids)
            model.addConstr(variable >= allocation - float(e1_allocation[slot, r]), name=f"v33x_deviation_pos[{rack},{slot}]")
            model.addConstr(variable >= float(e1_allocation[slot, r]) - allocation, name=f"v33x_deviation_neg[{rack},{slot}]")
            deviation[(rack, slot)] = variable
    model.setObjective(gp.quicksum(deviation.values()), GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V33X_E2_TIEBREAK_STATUS:{case}:{model.Status}")

    payload = payload_from_registry(
        registry, solver="MONOLITHIC", status="OPTIMAL", hard_feasible=True,
        objective=primary, lower_bound=primary, upper_bound=primary, gap=0.0,
        iterations=int(model.IterCount), optimality_cuts=0, feasibility_cuts=0,
        termination_reason="V33X_E2_LEXICOGRAPHIC_OPTIMAL", runtime_seconds=time.perf_counter() - started,
    )
    schedule = _schedule(payload, str(e1_schedule["reference_schedule_sha256"]))
    schedule["formulation_fingerprint"] = canonical_sha256({
        "experiment": "V33X_E2_ENDOGENOUS_GRID_EFFECTIVE_HEADROOM",
        "base": schedule["formulation_fingerprint"],
        "leverage_sha256": leverage_sha,
        "primary_tolerance": PRIMARY_TOL,
        "service_tolerance": SERVICE_TOL,
    })
    schedule["input_sha256"] = canonical_sha256({
        "base": schedule["input_sha256"], "E1_schedule_sha256": e1_schedule["schedule_sha256"],
        "leverage_sha256": leverage_sha,
    })
    schedule.pop("schedule_sha256", None)
    schedule["schedule_sha256"] = canonical_sha256(schedule)
    rack_headroom = np.asarray([[value(h[(rack, slot)]) for rack in data.rack_ids] for slot in range(96)])
    site_headroom = np.asarray([
        [rack_headroom[slot, [i for i, owner in enumerate(data.rack_aidc) if owner == site]].sum() for site in data.aidc_ids]
        for slot in range(96)
    ])
    x = np.asarray(schedule["workload_service_tensor"], dtype=float)
    cohort_shortfall = np.maximum(0.0, e1_x.sum(axis=(1, 2)) - x.sum(axis=(1, 2)))
    e1_backlog = np.asarray(e1_schedule["backlog_nodeh"], dtype=float)[-1]
    e2_backlog = np.asarray(schedule["backlog_nodeh"], dtype=float)[-1]
    result = E2Stage1Result(
        schedule=schedule,
        rack_headroom_96x48=rack_headroom,
        site_headroom_96x12=site_headroom,
        primary_objective=primary,
        leverage_objective=float(np.sum(leverage.T * site_headroom)),
        displacement_nodeh=float(np.sum(np.abs(x.sum(axis=0).T - e1_allocation))),
        service_parity_max_shortfall_nodeh=float(cohort_shortfall.max(initial=0.0)),
        terminal_backlog_worsening_max_nodeh=float(np.maximum(0.0, e2_backlog - e1_backlog).max(initial=0.0)),
        solver_iterations=int(model.IterCount),
        runtime_seconds=time.perf_counter() - started,
    )
    model.dispose()
    return result
