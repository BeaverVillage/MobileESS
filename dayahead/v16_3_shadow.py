"""One-shot prospective Apr-15 V16.3 shadow LP (not G12 authority)."""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import defaultdict
from typing import Mapping

import numpy as np

from .aidc_boundary_v16_1 import DT_HOURS, PUE_PLAN
from .aidc_power_response import GPU_PER_NODE, KAPPA_KW_PER_ACTIVE_H100_NODE
from .full_ieee123_b3_v16_2 import B3Inputs
from .grid_lp import LINE_POLYGON_FACES, V_MAX_SQUARED, V_MIN_SQUARED
from .mess_physics import (
    E_INITIAL_KWH,
    E_MAX_KWH,
    E_MIN_KWH,
    E_TERMINAL_KWH,
    PCS_KVA,
    PCS_POLYGON_FACES,
    P_LIMIT_KW,
)
from .run_v16_3_nonzero_validity import _aidc_limits, _planning_flow_base_and_sensitivity


def solve_shadow(
    *,
    inputs: B3Inputs,
    context,
    voltage_data,
    current_data,
    rho: float,
) -> dict[str, object]:
    """Solve exactly one candidate LP using only frozen affine grid rows."""

    import gurobipy as gp
    from gurobipy import GRB

    reference, _vintage, _background, binding, _voltage_path, authority = context
    controls = tuple(map(str, voltage_data["control_names"]))
    branch_names = tuple(map(str, voltage_data["branch_names"]))
    if controls != tuple(map(str, current_data["control_names"])) or branch_names != tuple(map(str, current_data["branch_names"])):
        raise RuntimeError("V163_SHADOW_AFFINE_AXIS_MISMATCH")
    started = time.perf_counter()
    model = gp.Model("v16_3_apr15_nonzero_shadow_candidate")
    model.Params.OutputFlag = 0
    model.Params.NumericFocus = 1

    cohorts = inputs.cohorts
    racks = inputs.rack_ids
    rack_index = {rack: i for i, rack in enumerate(racks)}
    aidc_racks = {
        f"AIDC{i:02d}": tuple(r for r, a in zip(racks, inputs.rack_aidc) if a == f"AIDC{i:02d}")
        for i in range(1, 13)
    }
    x = {(c, r, t): model.addVar(lb=0.0, name=f"workload[{c},{r},{t}]")
         for c in cohorts for r in racks for t in range(96)}
    backlog = {(c, b): model.addVar(lb=0.0, name=f"backlog[{c},{b}]")
               for c in cohorts for b in range(97)}
    for cohort in cohorts:
        model.addConstr(backlog[(cohort, 0)] == 0.0, name=f"service_initial[{cohort}]")
        for slot in range(96):
            model.addConstr(
                backlog[(cohort, slot + 1)] == backlog[(cohort, slot)]
                + inputs.arrivals[cohort][slot]
                - gp.quicksum(x[(cohort, rack, slot)] for rack in racks),
                name=f"service_balance[{cohort},{slot}]",
            )
        model.addConstr(backlog[(cohort, 96)] == 0.0, name=f"service_terminal_parity[{cohort}]")
    for slot in range(96):
        for rack in racks:
            r = rack_index[rack]
            model.addConstr(
                inputs.g_res_rack[slot][r]
                + GPU_PER_NODE / DT_HOURS * gp.quicksum(x[(cohort, rack, slot)] for cohort in cohorts)
                <= inputs.gpu_capacity[r],
                name=f"rack_gpu_hard[{rack},{slot}]",
            )

    aidc_load = {}
    for slot in range(96):
        for index in range(1, 13):
            aidc = f"AIDC{index:02d}"
            flexible = gp.quicksum(
                KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])] / DT_HOURS * x[(cohort, rack, slot)]
                for cohort in cohorts for rack in aidc_racks[aidc]
            )
            aidc_load[(aidc, slot)] = PUE_PLAN * (inputs.p_res_aidc_kw[slot][index - 1] + flexible)

    mess_p = {}; mess_q = {}; mess_e = {}
    service_to_mess = {str(record["service_site"]): mess_id for mess_id, record in inputs.mess_records.items()}
    for mess_id, record in sorted(inputs.mess_records.items()):
        transit = set(map(int, record["transit_slots"]))
        for boundary in range(97):
            mess_e[(mess_id, boundary)] = model.addVar(lb=E_MIN_KWH, ub=E_MAX_KWH,
                                                       name=f"mess_soc_kwh[{mess_id},{boundary}]")
        model.addConstr(mess_e[(mess_id, 0)] == E_INITIAL_KWH, name=f"mess_initial_soc[{mess_id}]")
        for slot in range(96):
            connected = slot not in transit
            mess_p[(mess_id, slot)] = model.addVar(
                lb=-rho * P_LIMIT_KW if connected else 0.0,
                ub=rho * P_LIMIT_KW if connected else 0.0,
                name=f"mess_p_kw[{mess_id},{slot}]",
            )
            mess_q[(mess_id, slot)] = model.addVar(
                lb=-rho * PCS_KVA if connected else 0.0,
                ub=rho * PCS_KVA if connected else 0.0,
                name=f"mess_q_kvar[{mess_id},{slot}]",
            )
            mobility = float(record["safe_mobility_energy_kwh"]) / len(transit) if slot in transit else 0.0
            model.addConstr(
                mess_e[(mess_id, slot + 1)] == mess_e[(mess_id, slot)]
                - DT_HOURS * mess_p[(mess_id, slot)] - mobility,
                name=f"mess_soc_balance[{mess_id},{slot}]",
            )
            apothem = PCS_KVA * math.cos(math.pi / PCS_POLYGON_FACES)
            for face in range(PCS_POLYGON_FACES):
                angle = 2 * math.pi * face / PCS_POLYGON_FACES
                model.addConstr(
                    math.cos(angle) * mess_p[(mess_id, slot)]
                    + math.sin(angle) * mess_q[(mess_id, slot)] <= apothem,
                    name=f"mess_pcs_hard[{mess_id},{slot},{face}]",
                )
        model.addConstr(mess_e[(mess_id, 96)] == E_TERMINAL_KWH,
                        name=f"mess_terminal_soc[{mess_id}]")

    eta = model.addVar(lb=0.0, name="max_normalized_phase_line_current")
    delta_by_slot = {}
    for slot in range(96):
        expressions = []
        for name in controls:
            if name.startswith("aidc_load_kw["):
                expressions.append(aidc_load[(name[13:-1], slot)])
            elif name.startswith("mess_p_kw["):
                service = name[10:-1]
                expressions.append(mess_p[(service_to_mess[service], slot)] if service in service_to_mess else 0.0)
            elif name.startswith("mess_q_kvar["):
                service = name[12:-1]
                expressions.append(mess_q[(service_to_mess[service], slot)] if service in service_to_mess else 0.0)
            else:
                raise RuntimeError(f"V163_SHADOW_UNKNOWN_CONTROL:{name}")
        anchor = np.asarray(voltage_data["anchor_control"][slot], dtype=float)
        delta = [expression - float(anchor[i]) for i, expression in enumerate(expressions)]
        delta_by_slot[slot] = delta
        down, up, _limits = _aidc_limits(reference, authority, slot)
        for i in range(12):
            model.addConstr(delta[i] >= -rho * float(down[i]), name=f"trust_aidc_low[{slot},{i}]")
            model.addConstr(delta[i] <= rho * float(up[i]), name=f"trust_aidc_high[{slot},{i}]")

        h = np.asarray(voltage_data["sensitivity"][slot], dtype=float)
        v0 = np.asarray(voltage_data["anchor_v_squared"][slot], dtype=float)
        for node in range(h.shape[1]):
            expression = float(v0[node]) + gp.quicksum(float(h[c, node]) * delta[c] for c in range(60))
            model.addConstr(expression >= V_MIN_SQUARED, name=f"grid_voltage_low[{slot},{node}]")
            model.addConstr(expression <= V_MAX_SQUARED, name=f"grid_voltage_high[{slot},{node}]")

        ji = np.asarray(current_data["current_sensitivity_pu_per_control"][slot], dtype=float)
        i0 = np.asarray(current_data["anchor_current_loading_pu"][slot], dtype=float)
        for branch, name in enumerate(branch_names):
            expression = float(i0[branch]) + gp.quicksum(float(ji[c, branch]) * delta[c] for c in range(60))
            model.addConstr(expression <= 1.0, name=f"grid_phase_current_hard[{slot},{name}]")
            if not name.startswith("transformer."):
                model.addConstr(eta >= expression, name=f"line_current_objective[{slot},{name}]")

        p0, q0, sp, sq = _planning_flow_base_and_sensitivity(binding, slot, anchor)
        branches = tuple(binding.factories[slot].data.branches)
        for branch, branch_row in enumerate(branches):
            key = (branch_row.branch_id, branch_row.phase)
            rating = binding.factories[slot].data.transformer_limit_kva.get(key)
            if rating is None:
                continue
            p = float(p0[branch]) + gp.quicksum(float(sp[branch, c]) * delta[c] for c in range(60))
            q = float(q0[branch]) + gp.quicksum(float(sq[branch, c]) * delta[c] for c in range(60))
            apothem = float(rating) * math.cos(math.pi / LINE_POLYGON_FACES)
            for face in range(LINE_POLYGON_FACES):
                angle = 2 * math.pi * face / LINE_POLYGON_FACES
                model.addConstr(math.cos(angle) * p + math.sin(angle) * q <= apothem,
                                name=f"transformer_total_kva_hard[{slot},{branch},{face}]")

    model.setObjective(eta, GRB.MINIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        return {
            "status": f"SHADOW_SOLVE_FAIL_GUROBI_{int(model.Status)}",
            "hard_feasible": False,
            "runtime_seconds": float(model.Runtime),
            "variable_count": int(model.NumVars),
            "constraint_count": int(model.NumConstrs),
        }
    controls_96x60 = np.asarray([
        [float((float(voltage_data["anchor_control"][slot, c]) + delta_by_slot[slot][c]).getValue()
               if hasattr(delta_by_slot[slot][c], "getValue")
               else float(voltage_data["anchor_control"][slot, c]) + float(delta_by_slot[slot][c]))
         for c in range(60)] for slot in range(96)
    ])
    terminal_error = max(abs(float(backlog[(cohort, 96)].X)) for cohort in cohorts)
    mess_terminal_error = max(abs(float(mess_e[(mess_id, 96)].X) - E_TERMINAL_KWH)
                              for mess_id in inputs.mess_records)
    workload_payload = [float(x[key].X) for key in sorted(x)]
    schedule_hash = hashlib.sha256(
        json.dumps({"controls": controls_96x60.tolist(), "workload": workload_payload},
                   sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "status": "OPTIMAL_PROSPECTIVE_SHADOW_ONLY",
        "hard_feasible": True,
        "objective_max_normalized_phase_line_current": float(eta.X),
        "runtime_seconds": float(model.Runtime),
        "wall_runtime_seconds": time.perf_counter() - started,
        "variable_count": int(model.NumVars),
        "constraint_count": int(model.NumConstrs),
        "terminal_service_parity_max_abs_error": terminal_error,
        "mess_terminal_soc_max_abs_error_kwh": mess_terminal_error,
        "controls_96x60": controls_96x60,
        "schedule_sha256": schedule_hash,
        "tap_decision_variable_count": 0,
        "OpenDSS_call_count_inside_model": 0,
    }

