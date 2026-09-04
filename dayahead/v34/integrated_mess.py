"""V33M3 MESS block bound to the common V28R2 planning-grid rows."""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import time
from typing import Mapping, Sequence

import gurobipy as gp
from gurobipy import GRB
import numpy as np

from dayahead.grid_lp import LINE_POLYGON_FACES
from dayahead.v28r2.electrical_subproblem import (
    SlotCoefficients,
    anchored_polygon_loading,
    anchored_polygon_parameters,
    is_dominated_mess_current_row,
    slot_coefficients,
)
from dayahead.v33m import MessMobilityInputs, ServicePCCMapping, add_mess_mobility_block, extract_mess_trajectory
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v33m.route_table import MobilityRouteTable
from dayahead.v17_ac_restoration_contract import (
    RHO as RESTORATION_RHO,
    RestorationCut,
)

from .correction import StaticCorrection, bind_squared_voltage_bounds


WORK_LIMIT_TIERS = (60.0, 180.0, 300.0)
RESTRICTED_MIP_GAP = 1e-7
RESOLVED_OBJECTIVE_TOLERANCE = 1e-6


@dataclass(frozen=True)
class IntegratedMessResult:
    trajectory: MessTrajectory
    planning_voltage_pu: np.ndarray
    planning_current_pu: np.ndarray
    objective: float
    common_control_names: tuple[str, ...]
    solver_status: str
    grid_constraint_count: int
    variable_count: int
    constraint_count: int
    model_build_seconds: float
    solve_seconds: float
    peak_rss_bytes: int
    incumbent_available: bool
    termination: str
    best_bound: float
    mip_gap: float
    binary_count: int
    move_binary_count: int
    stay_variable_count: int
    planning_rho: float
    prior_fixed_P_l1_kW_slots: float
    prior_fixed_Q_l1_kvar_slots: float
    current_vehicle_free_variable_count: int
    future_vehicle_variable_count: int
    zero_actuation_objective: float = math.inf
    restricted_stationary_objective: float = math.inf
    restricted_stationary_best_bound: float = math.inf
    restricted_stationary_mip_gap: float = math.inf
    restricted_stationary_status: str = "NOT_RUN"
    restricted_stationary_sum_abs_p_kw_slots: float = 0.0
    restricted_stationary_sum_abs_q_kvar_slots: float = 0.0
    restricted_incumbent_improves_zero: bool = False
    mip_start_accepted: bool = False
    work_limit_tiers_attempted: tuple[float, ...] = ()
    escalation_reason: str | None = None
    bounded_compute_classification: str = "NOT_APPLICABLE"
    preferred_restricted_objective: float = math.inf
    selected_restricted_start: str = "STAY"
    preferred_mip_start_loaded: bool = False
    restoration_cut_count: int = 0
    restoration_trust_region_constraint_count: int = 0
    restoration_recourse_trust_region_constraint_count: int = 0
    restoration_cut_arithmetic: tuple[Mapping[str, object], ...] = ()
    fixed_discrete_MESS_decisions: bool = False


def _configured_model(name: str) -> gp.Model:
    model = gp.Model(name)
    model.Params.OutputFlag = 0
    model.Params.Threads = 4
    model.Params.Seed = 20260828
    model.Params.MIPGap = 1e-3
    model.Params.FeasibilityTol = 1e-6
    model.Params.OptimalityTol = 1e-6
    model.Params.TimeLimit = 600.0
    model.Params.WorkLimit = 60.0
    model.Params.MIPFocus = 1
    # Stop with a reportable solver status instead of allowing an unbounded
    # branch-and-bound memory excursion during the production campaign.
    model.Params.SoftMemLimit = 8.0
    model.Params.NodefileStart = 1.0
    return model


def _set_zero_stay_start(
    block: object,
    mess_id: str,
    initial_service: str,
    initial_energy: float,
) -> None:
    for (key_mess, _slot, service), variable in block.occupancy.items():
        variable.Start = float(key_mess == mess_id and service == initial_service)
    for (key_mess, _slot, service), variable in block.stay.items():
        variable.Start = float(key_mess == mess_id and service == initial_service)
    for variable in block.move.values():
        variable.Start = 0.0
    for variable in block.discharge_mode.values():
        variable.Start = 0.0
    for variable in block.p_discharge.values():
        variable.Start = 0.0
    for variable in block.p_charge.values():
        variable.Start = 0.0
    for variable in block.q.values():
        variable.Start = 0.0
    for variable in block.energy.values():
        variable.Start = float(initial_energy)


def _fix_discrete_trajectory_and_load_start(
    block: object,
    trajectory: MessTrajectory,
) -> None:
    """Fix only selected mobility decisions and warm-start continuous P/Q/SoC."""

    rows = {(row.mess_id, int(row.slot)): row for row in trajectory.slots}
    expected = {
        (mess_id, slot)
        for mess_id in block.inputs.mess_ids
        for slot in range(block.inputs.horizon_slots)
    }
    if set(rows) != expected:
        raise ValueError("V37_R3_FIXED_DISCRETE_TRAJECTORY_AXIS")
    selected_moves = {
        (
            move.mess_id,
            int(move.departure_slot),
            str(move.origin_service_id),
            str(move.destination_service_id),
        )
        for move in trajectory.planned_move_commitments()
    }
    if not selected_moves.issubset(block.move):
        raise ValueError("V37_R3_FIXED_DISCRETE_ROUTE_NOT_IN_MODEL")
    for key, variable in block.move.items():
        value = float(key in selected_moves)
        variable.LB = value
        variable.UB = value
        variable.Start = value
    stay_values: dict[tuple[str, int, str], float] = {}
    for (mess_id, slot, service), variable in block.stay.items():
        row = rows[mess_id, int(slot)]
        value = float(row.mode == "CONNECTED" and row.service_id == service)
        variable.LB = value
        variable.UB = value
        variable.Start = value
        stay_values[mess_id, int(slot), service] = value
    occupancy_values: dict[tuple[str, int, str], float] = {}
    for mess_id in block.inputs.mess_ids:
        for service in block.inputs.route_table.service_ids:
            occupancy_values[mess_id, 0, service] = float(
                service == block.inputs.initial_service_by_mess[mess_id]
            )
        for boundary in range(1, block.inputs.horizon_slots + 1):
            for service in block.inputs.route_table.service_ids:
                value = stay_values[mess_id, boundary - 1, service]
                value += sum(
                    1.0
                    for key in selected_moves
                    if key[0] == mess_id
                    and key[3] == service
                    and key[1] + block.move_route[key].connection_ready_slots_15min
                    == boundary
                )
                if value not in {0.0, 1.0}:
                    raise ValueError("V37_R4_FIXED_DISCRETE_OCCUPANCY_NOT_BINARY")
                occupancy_values[mess_id, boundary, service] = value
    for (mess_id, boundary, service), variable in block.occupancy.items():
        value = occupancy_values[mess_id, int(boundary), service]
        variable.LB = value
        variable.UB = value
        variable.Start = value
    for mess_id, slot in expected:
        row = rows[mess_id, slot]
        block.discharge_mode[mess_id, slot].Start = float(row.p_kw > 1e-9)
        for service in block.inputs.route_table.service_ids:
            active = row.mode == "CONNECTED" and row.service_id == service
            block.p_discharge[mess_id, slot, service].Start = (
                max(float(row.p_kw), 0.0) if active else 0.0
            )
            block.p_charge[mess_id, slot, service].Start = (
                max(-float(row.p_kw), 0.0) if active else 0.0
            )
            block.q[mess_id, slot, service].Start = (
                float(row.q_kvar) if active else 0.0
            )
        block.energy[mess_id, slot].Start = float(row.battery_energy_kwh)
    for mess_id in block.inputs.mess_ids:
        block.energy[mess_id, block.inputs.horizon_slots].Start = float(
            block.inputs.electrical_authority.terminal_energy_kwh
        )
    block.model.update()


def _add_restoration_cuts(
    model: gp.Model,
    control_names: Sequence[str],
    expressions_by_slot: Sequence[Sequence[object]],
    restoration_cuts: Sequence[RestorationCut],
    *,
    include_cuts: bool = True,
    include_trust_region: bool = True,
) -> tuple[tuple[gp.Constr, ...], int]:
    """Insert the frozen V17 same-slot affine cuts and trust regions."""

    control_axis = tuple(map(str, control_names))
    cut_rows: list[gp.Constr] = []
    trust_region_rows = 0
    for cut_index, cut in enumerate(restoration_cuts):
        if cut.trust_region_rho != RESTORATION_RHO:
            raise RuntimeError("V17_AC_RESTORATION_CUT_RHO_MISMATCH")
        if cut.control_names != control_axis:
            raise RuntimeError("V17_AC_RESTORATION_CUT_CONTROL_AXIS_MISMATCH")
        if not 0 <= int(cut.slot) < len(expressions_by_slot):
            raise RuntimeError("V17_AC_RESTORATION_CUT_SLOT_OUT_OF_RANGE")
        expressions = expressions_by_slot[int(cut.slot)]
        if len(expressions) != len(control_axis):
            raise RuntimeError("V17_AC_RESTORATION_EXPRESSION_AXIS_MISMATCH")
        affine = float(cut.actual_value) + gp.quicksum(
            float(coefficient) * (expressions[index] - float(cut.anchor_controls[index]))
            for index, coefficient in enumerate(cut.coefficients)
        )
        if include_cuts:
            if cut.relation == "<=":
                row = model.addConstr(
                    affine <= float(cut.hard_limit) - float(cut.margin),
                    name=f"fresh_ac_restoration_upper[{cut_index},{cut.slot}]",
                )
            elif cut.relation == ">=":
                row = model.addConstr(
                    affine >= float(cut.hard_limit) + float(cut.margin),
                    name=f"fresh_ac_restoration_lower[{cut_index},{cut.slot}]",
                )
            else:
                raise RuntimeError("V17_AC_RESTORATION_CUT_RELATION_INVALID")
            cut_rows.append(row)
        elif cut.relation not in {"<=", ">="}:
            raise RuntimeError("V17_AC_RESTORATION_CUT_RELATION_INVALID")
        if not include_trust_region:
            continue
        for control_index, radius in enumerate(cut.local_radius):
            if float(radius) <= 0.0:
                continue
            center = float(cut.anchor_controls[control_index])
            model.addConstr(
                expressions[control_index] >= center - float(radius),
                name=f"fresh_ac_cut_trust_low[{cut_index},{cut.slot},{control_index}]",
            )
            model.addConstr(
                expressions[control_index] <= center + float(radius),
                name=f"fresh_ac_cut_trust_high[{cut_index},{cut.slot},{control_index}]",
            )
            trust_region_rows += 2
    return tuple(cut_rows), trust_region_rows


def _add_restoration_recourse_trust_region(
    model: gp.Model,
    control_names: Sequence[str],
    expressions_by_slot: Sequence[Sequence[object]],
    anchor_controls_96x60: np.ndarray,
    *,
    p_radius_kw: float,
    q_radius_kvar: float,
) -> int:
    """Keep every restoration P/Q recourse slot local to the failed Fresh run.

    A violation cut is local in one slot, but MESS energy coupling lets an
    otherwise unrestricted full-horizon re-solve replace P/Q in unrelated
    slots.  That invalidates the sequential-locality assumption and can move
    the physical violation to a new slot on every official round.  The frozen
    rho is therefore applied to the full 96-slot recourse step while the
    existing cut-specific stale-anchor guards remain in force.
    """

    names = tuple(map(str, control_names))
    anchor = np.asarray(anchor_controls_96x60, dtype=float)
    if anchor.shape != (len(expressions_by_slot), len(names)):
        raise ValueError(
            "V37_RESTORATION_RECOURSE_TRUST_ANCHOR_AXIS:"
            f"{anchor.shape}:{len(expressions_by_slot)}x{len(names)}"
        )
    if not np.isfinite(anchor).all():
        raise ValueError("V37_RESTORATION_RECOURSE_TRUST_ANCHOR_NONFINITE")
    if p_radius_kw <= 0.0 or q_radius_kvar <= 0.0:
        raise ValueError("V37_RESTORATION_RECOURSE_TRUST_RADIUS")

    rows = 0
    for slot, expressions in enumerate(expressions_by_slot):
        if len(expressions) != len(names):
            raise RuntimeError("V37_RESTORATION_RECOURSE_TRUST_EXPRESSION_AXIS")
        for control_index, name in enumerate(names):
            if name.startswith("mess_p_kw["):
                radius = float(p_radius_kw)
            elif name.startswith("mess_q_kvar["):
                radius = float(q_radius_kvar)
            else:
                continue
            center = float(anchor[slot, control_index])
            model.addConstr(
                expressions[control_index] >= center - radius,
                name=f"fresh_ac_recourse_trust_low[{slot},{control_index}]",
            )
            model.addConstr(
                expressions[control_index] <= center + radius,
                name=f"fresh_ac_recourse_trust_high[{slot},{control_index}]",
            )
            rows += 2
    return rows


def _stationary_restricted_incumbent(
    model: gp.Model,
    block: object,
    mess_id: str,
    initial_service: str,
) -> dict[str, object]:
    """Solve the exact full model with mobility temporarily fixed to STAY.

    The temporary rows are removed before the production solve.  Capturing the
    solution as a MIP start ensures that the complete mobility model can never
    return an incumbent worse than this cheap, production-feasible policy.
    """

    fixed_rows: list[gp.Constr] = []
    for (key_mess, _slot, service), variable in block.occupancy.items():
        fixed_rows.append(model.addConstr(
            variable == float(key_mess == mess_id and service == initial_service),
            name=f"v35_restricted_occupancy[{variable.index}]",
        ))
    for (key_mess, _slot, service), variable in block.stay.items():
        fixed_rows.append(model.addConstr(
            variable == float(key_mess == mess_id and service == initial_service),
            name=f"v35_restricted_stay[{variable.index}]",
        ))
    for variable in block.move.values():
        fixed_rows.append(model.addConstr(variable == 0.0, name=f"v35_restricted_move[{variable.index}]"))
    model.update()
    production_gap = float(model.Params.MIPGap)
    production_work_limit = float(model.Params.WorkLimit)
    model.Params.MIPGap = RESTRICTED_MIP_GAP
    model.Params.WorkLimit = WORK_LIMIT_TIERS[0]
    model.optimize()
    if model.SolCount < 1:
        status = int(model.Status)
        model.remove(fixed_rows)
        model.update()
        model.Params.MIPGap = production_gap
        model.Params.WorkLimit = production_work_limit
        model.reset()
        return {
            "available": False,
            "status": f"STATUS_{status}",
            "objective": math.inf,
            "best_bound": math.inf,
            "mip_gap": math.inf,
            "start": (),
            "sum_abs_p": 0.0,
            "sum_abs_q": 0.0,
        }

    raw_status = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.WORK_LIMIT: "WORK_LIMIT",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.SUBOPTIMAL: "SUBOPTIMAL",
    }.get(model.Status, f"STATUS_{model.Status}")
    start = tuple(float(variable.X) for variable in model.getVars())
    sum_abs_p = sum(
        abs(float(block.p_discharge[key].X) - float(block.p_charge[key].X))
        for key in block.p_discharge
    )
    sum_abs_q = sum(abs(float(variable.X)) for variable in block.q.values())
    result = {
        "available": True,
        "status": raw_status,
        "objective": float(model.ObjVal),
        "best_bound": float(model.ObjBound),
        "mip_gap": float(model.MIPGap),
        "start": start,
        "sum_abs_p": float(sum_abs_p),
        "sum_abs_q": float(sum_abs_q),
    }
    model.remove(fixed_rows)
    model.update()
    model.Params.MIPGap = production_gap
    model.Params.WorkLimit = production_work_limit
    model.reset()
    for variable, value in zip(model.getVars(), start, strict=True):
        variable.Start = value
    return result


def _bounded_compute_classification(raw_status: str, objective: float, best_bound: float) -> str:
    absolute_gap = abs(float(objective) - float(best_bound))
    if raw_status == "OPTIMAL" and absolute_gap <= RESOLVED_OBJECTIVE_TOLERANCE:
        return "OPTIMAL_CERTIFIED"
    return "FEASIBLE_BOUNDED_COMPUTE_INCUMBENT"


def _apply_preferred_restricted_start(
    model: gp.Model,
    block: object,
    mess_id: str,
    payload: Mapping[str, object],
    *,
    aidc: np.ndarray | None = None,
    coefficients: Sequence[SlotCoefficients] | None = None,
    fixed_p: Mapping[tuple[str, int], float] | None = None,
    fixed_q: Mapping[tuple[str, int], float] | None = None,
) -> None:
    """Translate one complete fixed-route opportunity solution to a MIPStart."""

    candidate = payload["candidate"]
    get = lambda name: getattr(candidate, name) if hasattr(candidate, name) else candidate[name]
    if str(get("mess_id")) != mess_id:
        raise ValueError("V35R3_MIPSTART_MESS_ID")
    origin = str(get("origin"))
    destination = str(get("destination"))
    is_stay = bool(get("is_stay"))
    departure = None if is_stay else int(get("departure_slot"))
    ready = None if is_stay else int(get("connection_ready_slot"))
    p_dis = np.asarray(payload["p_discharge_kw"], dtype=float)
    p_ch = np.asarray(payload["p_charge_kw"], dtype=float)
    q = np.asarray(payload["q_kvar"], dtype=float)
    energy = np.asarray(payload["energy_kwh"], dtype=float)
    if p_dis.shape != (96,) or p_ch.shape != (96,) or q.shape != (96,) or energy.shape != (97,):
        raise ValueError("V35R3_MIPSTART_ARRAY_AXIS")
    if np.any(p_dis < -1e-7) or np.any(p_ch < -1e-7) or np.any((p_dis > 1e-7) & (p_ch > 1e-7)):
        raise ValueError("V35R3_MIPSTART_DIRECTION")
    if not is_stay:
        key = (mess_id, departure, origin, destination)
        if key not in block.move or departure is None or ready is None:
            raise ValueError("V35R3_MIPSTART_ROUTE_NOT_IN_FULL_MODEL")
    for variable in model.getVars():
        variable.Start = GRB.UNDEFINED
    for (key_mess, boundary, service), variable in block.occupancy.items():
        active = False
        if key_mess == mess_id:
            if is_stay:
                active = service == origin
            else:
                active = (boundary <= departure and service == origin) or (boundary >= ready and service == destination)
        variable.Start = float(active)
    for (key_mess, slot, service), variable in block.stay.items():
        active = False
        if key_mess == mess_id:
            if is_stay:
                active = service == origin
            else:
                active = (slot < departure and service == origin) or (slot >= ready and service == destination)
        variable.Start = float(active)
    for key, variable in block.move.items():
        variable.Start = float(not is_stay and key == (mess_id, departure, origin, destination))
    services = block.inputs.route_table.service_ids
    for slot in range(96):
        active_service = origin if is_stay else (
            origin if slot < departure else (destination if slot >= ready else None)
        )
        block.discharge_mode[mess_id, slot].Start = float(p_dis[slot] > 1e-7)
        for service in services:
            active = service == active_service
            block.p_discharge[mess_id, slot, service].Start = float(p_dis[slot] if active else 0.0)
            block.p_charge[mess_id, slot, service].Start = float(p_ch[slot] if active else 0.0)
            block.q[mess_id, slot, service].Start = float(q[slot] if active else 0.0)
    for boundary in range(97):
        block.energy[mess_id, boundary].Start = float(energy[boundary])
    if aidc is not None and coefficients is not None:
        fixed_p = {} if fixed_p is None else fixed_p
        fixed_q = {} if fixed_q is None else fixed_q
        services = tuple(name[10:-1] for name in coefficients[0].control_names[12:36])
        by_name = {variable.VarName: variable for variable in model.getVars()}
        rho = 0.0
        for slot, coefficient in enumerate(coefficients):
            active_service = origin if is_stay else (
                origin if slot < departure else (destination if slot >= ready else None)
            )
            p_values = [float(fixed_p.get((service, slot), 0.0)) for service in services]
            q_values = [float(fixed_q.get((service, slot), 0.0)) for service in services]
            if active_service is not None:
                service_index = services.index(active_service)
                p_values[service_index] += float(p_dis[slot] - p_ch[slot])
                q_values[service_index] += float(q[slot])
            controls = np.asarray(list(aidc[slot]) + p_values + q_values, dtype=float)
            squared = coefficient.voltage_constant + coefficient.voltage_matrix.T @ controls
            affine_current = coefficient.current_constant + coefficient.current_matrix.T @ controls
            flow_p = coefficient.flow_p_constant + coefficient.flow_p_matrix @ controls
            flow_q = coefficient.flow_q_constant + coefficient.flow_q_matrix @ controls
            current = anchored_polygon_loading(coefficient, controls)
            bias, tangent_delta, _ = anchored_polygon_parameters(coefficient)
            del bias
            tangent = tangent_delta.T @ (controls - coefficient.anchor)

            def set_start(name: str, value: float) -> None:
                variable = by_name.get(name)
                if variable is not None:
                    variable.Start = float(value)

            for index in range(len(squared)):
                set_start(f"v34_v_squared[{slot},{index}]", squared[index])
            for index, branch in enumerate(coefficient.branch_names):
                if not branch.startswith("transformer.") and not is_dominated_mess_current_row(branch):
                    rho = max(rho, float(current[index]))
                    set_start(f"v34_line_p[{slot},{index}]", flow_p[index])
                    set_start(f"v34_line_q[{slot},{index}]", flow_q[index])
                    set_start(f"v34_line_tangent_correction[{slot},{index}]", tangent[index])
                elif not is_dominated_mess_current_row(branch):
                    set_start(f"v34_i_aff[{slot},{index}]", affine_current[index])
                    set_start(f"v34_i_hat[{slot},{index}]", max(0.0, float(affine_current[index])))
                if coefficient.transformer_ratings[index] is not None:
                    set_start(f"v34_tx_p[{slot},{index}]", flow_p[index])
                    set_start(f"v34_tx_q[{slot},{index}]", flow_q[index])
        set_start("v34_rho_planning", rho)
    model.update()


def _preferred_restricted_incumbent(
    model: gp.Model,
    block: object,
    mess_id: str,
    payload: Mapping[str, object],
    aidc: np.ndarray,
    coefficients: Sequence[SlotCoefficients],
    fixed_p: Mapping[tuple[str, int], float],
    fixed_q: Mapping[tuple[str, int], float],
) -> dict[str, object]:
    """Polish the selected opportunity in the exact full model.

    Only the single selected route is fixed.  This closes any numerical gap
    between the compact opportunity model and the production model, captures
    every auxiliary value, and supplies a complete, solver-accepted MIPStart
    after the temporary rows are removed.
    """

    candidate = payload["candidate"]
    get = lambda name: getattr(candidate, name) if hasattr(candidate, name) else candidate[name]
    origin = str(get("origin"))
    destination = str(get("destination"))
    is_stay = bool(get("is_stay"))
    departure = None if is_stay else int(get("departure_slot"))
    ready = None if is_stay else int(get("connection_ready_slot"))
    fixed_bounds: list[tuple[gp.Var, float, float]] = []

    def fix(variable: gp.Var, value: float) -> None:
        fixed_bounds.append((variable, float(variable.LB), float(variable.UB)))
        variable.LB = variable.UB = float(value)

    for (key_mess, boundary, service), variable in block.occupancy.items():
        active = False
        if key_mess == mess_id:
            if is_stay:
                active = service == origin
            else:
                active = (boundary <= departure and service == origin) or (boundary >= ready and service == destination)
        fix(variable, float(active))
    for (key_mess, slot, service), variable in block.stay.items():
        active = False
        if key_mess == mess_id:
            if is_stay:
                active = service == origin
            else:
                active = (slot < departure and service == origin) or (slot >= ready and service == destination)
        fix(variable, float(active))
    selected_key = None if is_stay else (mess_id, departure, origin, destination)
    for key, variable in block.move.items():
        fix(variable, float(key == selected_key))
    _apply_preferred_restricted_start(
        model, block, mess_id, payload,
        aidc=aidc, coefficients=coefficients, fixed_p=fixed_p, fixed_q=fixed_q,
    )
    production_gap = float(model.Params.MIPGap)
    production_work_limit = float(model.Params.WorkLimit)
    production_solution_limit = int(model.Params.SolutionLimit)
    production_output_flag = int(model.Params.OutputFlag)
    model.Params.MIPGap = RESTRICTED_MIP_GAP
    model.Params.WorkLimit = WORK_LIMIT_TIERS[0]
    model.Params.SolutionLimit = 1
    model.Params.OutputFlag = 0
    model.optimize()
    available = model.SolCount > 0
    result = {
        "available": available,
        "objective": float(model.ObjVal) if available else math.inf,
        "status": (
            {GRB.OPTIMAL: "OPTIMAL", GRB.WORK_LIMIT: "WORK_LIMIT", GRB.TIME_LIMIT: "TIME_LIMIT"}.get(
                model.Status, f"STATUS_{model.Status}"
            )
        ),
        "start": tuple(float(variable.X) for variable in model.getVars()) if available else (),
    }
    for variable, lower, upper in fixed_bounds:
        variable.LB = lower
        variable.UB = upper
    model.update()
    model.Params.MIPGap = production_gap
    model.Params.WorkLimit = production_work_limit
    model.Params.SolutionLimit = production_solution_limit
    model.Params.OutputFlag = production_output_flag
    model.reset()
    if available:
        for variable, value in zip(model.getVars(), result["start"], strict=True):
            variable.Start = value
    return result


def solve_integrated_mess(
    *,
    case: str,
    aidc_pcc_kw_96x12: np.ndarray,
    electrical_context: object,
    voltage_authority: object,
    current_authority: object,
    route_table: MobilityRouteTable,
    service_to_pcc: Mapping[str, str],
    initial_service_by_mess: Mapping[str, str],
    correction: StaticCorrection | None = None,
    fixed_mess_p_by_service: Mapping[tuple[str, int], float] | None = None,
    fixed_mess_q_by_service: Mapping[tuple[str, int], float] | None = None,
    enforce_planning_grid_constraints: bool = True,
    grid_coefficients: Sequence[SlotCoefficients] | None = None,
    force_at_least_one_move: bool = False,
    preferred_restricted_start: Mapping[str, object] | None = None,
    restoration_cuts: Sequence[RestorationCut] = (),
    fixed_discrete_trajectory: MessTrajectory | None = None,
    restoration_include_cuts: bool = True,
    restoration_include_trust_region: bool = True,
    restoration_recourse_anchor_controls: np.ndarray | None = None,
    infeasible_iis_path: Path | None = None,
) -> IntegratedMessResult:
    if case not in {"B2", "B3"}:
        raise ValueError("V34_INTEGRATED_MESS_ONLY_FOR_B2_B3")
    aidc = np.asarray(aidc_pcc_kw_96x12, dtype=float)
    if aidc.shape != (96, 12) or not np.isfinite(aidc).all():
        raise ValueError("V34_AIDC_PCC_AXIS")
    mapping = ServicePCCMapping(dict(service_to_pcc), "V34_FROZEN_C376_MAPPING")
    inputs = MessMobilityInputs.create(
        route_table,
        96,
        initial_service_by_mess,
        mapping,
        electrical_authority=MessElectricalAuthority.from_repository(),
    )
    fixed_discrete = fixed_discrete_trajectory is not None
    if not fixed_discrete and len(inputs.mess_ids) != 1:
        raise ValueError("V34_SEQUENTIAL_COORDINATION_REQUIRES_ONE_VEHICLE_BLOCK")
    if fixed_discrete and force_at_least_one_move:
        raise ValueError("V37_R3_FIXED_DISCRETE_CONFLICTS_WITH_FORCE_MOVE")
    if restoration_recourse_anchor_controls is not None and not fixed_discrete:
        raise ValueError("V37_RESTORATION_RECOURSE_TRUST_REQUIRES_FIXED_DISCRETE")
    if restoration_recourse_anchor_controls is not None and not restoration_cuts:
        raise ValueError("V37_RESTORATION_RECOURSE_TRUST_REQUIRES_CUT")
    if restoration_recourse_anchor_controls is not None and not restoration_include_trust_region:
        raise ValueError("V37_RESTORATION_RECOURSE_TRUST_DISABLED")
    build_started = time.perf_counter()
    model = _configured_model(f"v34_integrated_{case}")
    block = add_mess_mobility_block(model, inputs)
    if force_at_least_one_move:
        model.addConstr(block.number_move_departures >= 1, name="v34_diagnostic_force_move")
    # A contract-valid incumbent is known a priori: remain at the initial
    # service, exchange zero P/Q, and hold terminal-equal initial energy.
    # Supplying it avoids spending campaign time rediscovering feasibility.
    mess_id = inputs.mess_ids[0]
    initial_service = inputs.initial_service_by_mess[mess_id]
    if fixed_discrete:
        assert fixed_discrete_trajectory is not None
        if {row.mess_id for row in fixed_discrete_trajectory.slots} != set(inputs.mess_ids):
            raise ValueError("V37_R3_FIXED_DISCRETE_MESS_AXIS")
        _fix_discrete_trajectory_and_load_start(block, fixed_discrete_trajectory)
    else:
        initial_energy = inputs.initial_energy_by_mess[mess_id]
        _set_zero_stay_start(block, mess_id, initial_service, initial_energy)
    fixed_p = {} if fixed_mess_p_by_service is None else dict(fixed_mess_p_by_service)
    fixed_q = {} if fixed_mess_q_by_service is None else dict(fixed_mess_q_by_service)
    controls = tuple(map(str, voltage_authority["control_names"]))
    node_names = tuple(map(str, voltage_authority["node_names"]))
    if len(controls) != 60 or len(node_names) != 386:
        raise RuntimeError("V34_COMMON_GRID_AXIS")

    if not enforce_planning_grid_constraints:
        if restoration_cuts:
            raise ValueError("V37_R3_RESTORATION_CUT_REQUIRES_FULL_GRID_MODEL")
        # Phase-0 engineering smoke: construct the complete 24-service MESS
        # block and its common control axis, solve deterministically, then
        # evaluate the resulting frozen controls through the same affine rows.
        # Production/calibration calls retain the default hard grid binding.
        model.setObjectiveN(block.total_travel_energy, 0, priority=3, weight=1.0, name="MIN_TRAVEL_ENERGY")
        model.setObjectiveN(block.number_move_departures, 1, priority=2, weight=1.0, name="MIN_MOVES")
        model.setObjectiveN(block.deterministic_move_ordinal, 2, priority=1, weight=1.0, name="DETERMINISTIC_TIE")
        model.ModelSense = GRB.MINIMIZE
        solve_started = time.perf_counter(); model.optimize(); solve_seconds = time.perf_counter() - solve_started
        if model.Status != GRB.OPTIMAL:
            raise RuntimeError(f"V34_INTEGRATION_SMOKE_MESS_STATUS:{model.Status}")
        trajectory = extract_mess_trajectory(block)
        by_service_p = dict(fixed_p); by_service_q = dict(fixed_q)
        for item in trajectory.slots:
            if item.service_id is None:
                continue
            key = (item.service_id, item.slot)
            by_service_p[key] = by_service_p.get(key, 0.0) + item.p_kw
            by_service_q[key] = by_service_q.get(key, 0.0) + item.q_kvar
        planning_v, planning_i = [], []
        for slot in range(96):
            coefficient = slot_coefficients(electrical_context, voltage_authority, current_authority, slot)
            numeric = []
            for name in controls:
                if name.startswith("aidc_load_kw["):
                    numeric.append(float(aidc[slot, int(name[17:-1]) - 1]))
                elif name.startswith("mess_p_kw["):
                    numeric.append(float(by_service_p.get((name[10:-1], slot), 0.0)))
                elif name.startswith("mess_q_kvar["):
                    numeric.append(float(by_service_q.get((name[12:-1], slot), 0.0)))
                else:
                    raise RuntimeError(f"V34_UNKNOWN_COMMON_CONTROL:{name}")
            vector = np.asarray(numeric, dtype=float)
            planning_v.append(np.sqrt(np.maximum(0.0, coefficient.voltage_constant + coefficient.voltage_matrix.T @ vector)))
            planning_i.append(anchored_polygon_loading(coefficient, vector))
        return IntegratedMessResult(
            trajectory, np.asarray(planning_v), np.asarray(planning_i), 0.0,
            controls, "OPTIMAL", 0, int(model.NumVars), int(model.NumConstrs),
            solve_started - build_started, solve_seconds, _rss_bytes(),
            True, "OPTIMAL", float(model.ObjBound), float(model.MIPGap),
            int(model.NumBinVars), len(block.move), len(block.stay), 0.0,
            sum(abs(value) for value in fixed_p.values()),
            sum(abs(value) for value in fixed_q.values()),
            sum(variable.LB < variable.UB for variable in model.getVars()), 0,
        )

    coefficients = tuple(grid_coefficients) if grid_coefficients is not None else tuple(
        slot_coefficients(electrical_context, voltage_authority, current_authority, slot)
        for slot in range(96)
    )
    if len(coefficients) != 96 or tuple(item.slot for item in coefficients) != tuple(range(96)):
        raise ValueError("V34_GRID_COEFFICIENT_AXIS")
    eta = model.addVar(lb=0.0, ub=1.0, name="v34_rho_planning")
    grid_constraints = 0
    p_services = tuple(name[10:-1] for name in controls[12:36])
    q_services = tuple(name[12:-1] for name in controls[36:60])
    if p_services != q_services or set(p_services) != set(route_table.service_ids):
        raise RuntimeError("V34_COMMON_MESS_SERVICE_AXIS")

    def sparse_expression(base: float, vector: np.ndarray, slot: int) -> gp.LinExpr:
        constant = float(base + vector[:12] @ aidc[slot])
        constant += sum(float(vector[12 + index]) * float(fixed_p.get((service, slot), 0.0)) for index, service in enumerate(p_services))
        constant += sum(float(vector[36 + index]) * float(fixed_q.get((service, slot), 0.0)) for index, service in enumerate(p_services))
        return gp.LinExpr(constant) + gp.quicksum(
            float(vector[12 + index]) * block.p_injection_by_service_slot[service, slot]
            + float(vector[36 + index]) * block.q_injection_by_service_slot[service, slot]
            for index, service in enumerate(p_services)
            if abs(float(vector[12 + index])) > 1e-15
            or abs(float(vector[36 + index])) > 1e-15
        )

    expressions_by_slot = tuple(
        tuple(map(float, aidc[slot]))
        + tuple(
            float(fixed_p.get((service, slot), 0.0))
            + block.p_injection_by_service_slot[service, slot]
            for service in p_services
        )
        + tuple(
            float(fixed_q.get((service, slot), 0.0))
            + block.q_injection_by_service_slot[service, slot]
            for service in p_services
        )
        for slot in range(96)
    )

    recourse_trust_region_constraint_count = 0
    if restoration_recourse_anchor_controls is not None:
        recourse_trust_region_constraint_count = _add_restoration_recourse_trust_region(
            model,
            controls,
            expressions_by_slot,
            restoration_recourse_anchor_controls,
            p_radius_kw=RESTORATION_RHO * float(
                inputs.electrical_authority.active_power_limit_kw
            ),
            q_radius_kvar=RESTORATION_RHO * float(inputs.electrical_authority.pcs_kva),
        )

    for slot, coefficient in enumerate(coefficients):
        for index, node in enumerate(node_names):
            expression = sparse_expression(float(coefficient.voltage_constant[index]), coefficient.voltage_matrix[:, index], slot)
            phase = "ABC"[int(node.rsplit(".", 1)[1]) - 1]
            up, low = (0.0, 0.0) if correction is None else correction.value_for(node, phase, slot)
            lower, upper = bind_squared_voltage_bounds(up, low)
            # One affine row plus a bounded auxiliary stores the large sparse
            # coefficient vector once (two direct bounds duplicate it).
            voltage = model.addVar(lb=lower, ub=upper, name=f"v34_v_squared[{slot},{index}]")
            model.addConstr(voltage == expression, name=f"v34_voltage_affine[{slot},{index}]")
            grid_constraints += 1

        bias, tangent_delta, _polygon_anchor = anchored_polygon_parameters(coefficient)
        for index, branch in enumerate(coefficient.branch_names):
            if not is_dominated_mess_current_row(branch) and branch.startswith("transformer."):
                expression = sparse_expression(
                    float(coefficient.current_constant[index]),
                    coefficient.current_matrix[:, index],
                    slot,
                )
                current = model.addVar(lb=-GRB.INFINITY, name=f"v34_i_aff[{slot},{index}]")
                current_hat = model.addVar(lb=0.0, ub=1.0, name=f"v34_i_hat[{slot},{index}]")
                model.addConstr(current == expression, name=f"v34_current_affine[{slot},{index}]")
                model.addConstr(current_hat >= current, name=f"v34_current_epigraph[{slot},{index}]")
                grid_constraints += 2
            elif not is_dominated_mess_current_row(branch):
                p_flow = model.addVar(lb=-GRB.INFINITY, name=f"v34_line_p[{slot},{index}]")
                q_flow = model.addVar(lb=-GRB.INFINITY, name=f"v34_line_q[{slot},{index}]")
                tangent_correction = model.addVar(
                    lb=-GRB.INFINITY,
                    name=f"v34_line_tangent_correction[{slot},{index}]",
                )
                model.addConstr(
                    p_flow == sparse_expression(
                        float(coefficient.flow_p_constant[index]),
                        coefficient.flow_p_matrix[index],
                        slot,
                    ),
                    name=f"v34_line_p_affine[{slot},{index}]",
                )
                model.addConstr(
                    q_flow == sparse_expression(
                        float(coefficient.flow_q_constant[index]),
                        coefficient.flow_q_matrix[index],
                        slot,
                    ),
                    name=f"v34_line_q_affine[{slot},{index}]",
                )
                model.addConstr(
                    tangent_correction == sparse_expression(
                        -float(tangent_delta[:, index] @ coefficient.anchor),
                        tangent_delta[:, index],
                        slot,
                    ),
                    name=f"v34_line_tangent_correction_affine[{slot},{index}]",
                )
                grid_constraints += 3
                apothem = (
                    float(coefficient.branch_limits[index])
                    * math.cos(math.pi / LINE_POLYGON_FACES)
                )
                for face in range(LINE_POLYGON_FACES):
                    angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                    model.addConstr(
                        eta
                        >= (
                            math.cos(angle) * p_flow + math.sin(angle) * q_flow
                        ) / apothem
                        + tangent_correction
                        + float(bias[index]),
                        name=f"v34_line_current_polygon[{slot},{index},{face}]",
                    )
                    grid_constraints += 1
            rating = coefficient.transformer_ratings[index]
            if rating is None:
                continue
            # Reusing affine flow auxiliaries across every polygon face avoids
            # materializing the same 48-service coefficient row 12 times.
            p_flow = model.addVar(lb=-GRB.INFINITY, name=f"v34_tx_p[{slot},{index}]")
            q_flow = model.addVar(lb=-GRB.INFINITY, name=f"v34_tx_q[{slot},{index}]")
            model.addConstr(
                p_flow == sparse_expression(float(coefficient.flow_p_constant[index]), coefficient.flow_p_matrix[index], slot),
                name=f"v34_tx_p_affine[{slot},{index}]",
            )
            model.addConstr(
                q_flow == sparse_expression(float(coefficient.flow_q_constant[index]), coefficient.flow_q_matrix[index], slot),
                name=f"v34_tx_q_affine[{slot},{index}]",
            )
            grid_constraints += 2
            apothem = float(rating) * math.cos(math.pi / LINE_POLYGON_FACES)
            for face in range(LINE_POLYGON_FACES):
                angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                model.addConstr(
                    math.cos(angle) * p_flow + math.sin(angle) * q_flow <= apothem,
                    name=f"v34_transformer_kva[{slot},{index},{face}]",
                )
                grid_constraints += 1

    cut_rows, trust_region_constraint_count = _add_restoration_cuts(
        model, controls, expressions_by_slot, restoration_cuts,
        include_cuts=restoration_include_cuts,
        include_trust_region=restoration_include_trust_region,
    )
    grid_constraints += (
        len(cut_rows)
        + trust_region_constraint_count
        + recourse_trust_region_constraint_count
    )

    # The corrected V34 policy explicitly prioritizes reproducible completion
    # over exact global-optimal equivalence.  One scalar deterministic
    # objective avoids four full MIP re-solves while retaining every allowed
    # STAY/MOVE, destination, departure, P/Q, and SoC decision.
    model.setObjective(
        eta
        + 1e-8 * block.total_travel_energy
        + 1e-10 * block.number_move_departures
        + 1e-16 * block.deterministic_move_ordinal,
        GRB.MINIMIZE,
    )
    model_build_seconds = time.perf_counter() - build_started
    zero_rho = 0.0
    for slot, coefficient in enumerate(coefficients):
        numeric = np.asarray(
            list(aidc[slot])
            + [float(fixed_p.get((service, slot), 0.0)) for service in p_services]
            + [float(fixed_q.get((service, slot), 0.0)) for service in p_services],
            dtype=float,
        )
        current = anchored_polygon_loading(coefficient, numeric)
        for index, branch in enumerate(coefficient.branch_names):
            if not branch.startswith("transformer.") and not is_dominated_mess_current_row(branch):
                zero_rho = max(zero_rho, float(current[index]))

    # A V35R3 preferred start is supplied only after the opportunity scanner has
    # exhaustively solved STAY and every feasible initial destination/departure
    # candidate.  Re-solving STAY here is therefore redundant and, on the large
    # B3 model, can consume most of the full-solve budget before the better
    # candidate is even loaded.
    if fixed_discrete:
        restricted = {
            "available": False,
            "objective": math.inf,
            "best_bound": math.inf,
            "mip_gap": math.inf,
            "status": "SKIPPED_FIXED_DISCRETE_RESTORATION_RECOURSE",
            "start": (),
            "sum_abs_p": 0.0,
            "sum_abs_q": 0.0,
        }
    elif preferred_restricted_start is None:
        restricted = _stationary_restricted_incumbent(model, block, mess_id, initial_service)
    else:
        restricted = {
            "available": False,
            "objective": math.inf,
            "best_bound": math.inf,
            "mip_gap": math.inf,
            "status": "SKIPPED_COMPLETE_OPPORTUNITY_SCAN",
            "start": (),
            "sum_abs_p": 0.0,
            "sum_abs_q": 0.0,
        }
    preferred_objective = math.inf
    preferred_loaded = False
    selected_start = "STAY"
    if preferred_restricted_start is not None and not fixed_discrete:
        opportunity_objective = float(preferred_restricted_start["objective"])
        if (
            math.isfinite(opportunity_objective)
            and (
                not bool(restricted["available"])
                or opportunity_objective < float(restricted["objective"]) - RESOLVED_OBJECTIVE_TOLERANCE
            )
        ):
            preferred = _preferred_restricted_incumbent(
                model, block, mess_id, preferred_restricted_start,
                aidc, coefficients, fixed_p, fixed_q,
            )
            preferred_objective = float(preferred["objective"])
            preferred_loaded = bool(preferred["available"])
            candidate = preferred_restricted_start["candidate"]
            candidate_is_stay = bool(
                getattr(candidate, "is_stay")
                if hasattr(candidate, "is_stay")
                else candidate["is_stay"]
            )
            if preferred_loaded and not candidate_is_stay:
                selected_start = "CONGESTION_AWARE_MOVE"
            elif preferred_loaded:
                selected_start = "STAY"
            elif bool(restricted["available"]):
                for variable, value in zip(model.getVars(), restricted["start"], strict=True):
                    variable.Start = value
                selected_start = "STAY"
    quality_bound = min(float(restricted["objective"]), preferred_objective)
    attempted: list[float] = []
    escalation_reason: str | None = None
    solve_started = time.perf_counter()
    for work_limit in WORK_LIMIT_TIERS:
        attempted.append(work_limit)
        model.Params.WorkLimit = work_limit
        model.optimize()
        if model.SolCount < 1:
            escalation_reason = "NO_FULL_MODEL_FEASIBLE_INCUMBENT"
            continue
        if math.isfinite(quality_bound) and float(model.ObjVal) > quality_bound + RESOLVED_OBJECTIVE_TOLERANCE:
            escalation_reason = "FULL_MODEL_INCUMBENT_WORSE_THAN_BEST_RESTRICTED_FEASIBLE_INCUMBENT"
            continue
        break
    solve_seconds = time.perf_counter() - solve_started
    accepted_statuses = {GRB.OPTIMAL, GRB.WORK_LIMIT, GRB.TIME_LIMIT, GRB.SUBOPTIMAL}
    if model.Status not in accepted_statuses or model.SolCount < 1:
        if model.Status == GRB.INFEASIBLE and infeasible_iis_path is not None:
            target = Path(infeasible_iis_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            model.computeIIS()
            model.write(str(target))
        raise RuntimeError(f"V34_INTEGRATED_MESS_SOLVER_STATUS:{model.Status}")
    if math.isfinite(quality_bound) and float(model.ObjVal) > quality_bound + RESOLVED_OBJECTIVE_TOLERANCE:
        raise RuntimeError("V35_MESS_FULL_MODEL_WORSE_THAN_RESTRICTED_INCUMBENT")
    # Evaluate the frozen solution numerically.  Keeping tens of thousands of
    # Python LinExpr wrappers alive through optimize materially increases RSS.
    trajectory = extract_mess_trajectory(block)
    by_service_p = dict(fixed_p)
    by_service_q = dict(fixed_q)
    for item in trajectory.slots:
        if item.service_id is None:
            continue
        key = (item.service_id, item.slot)
        by_service_p[key] = by_service_p.get(key, 0.0) + item.p_kw
        by_service_q[key] = by_service_q.get(key, 0.0) + item.q_kvar
    planning_v, planning_i = [], []
    for slot, coefficient in enumerate(coefficients):
        numeric = np.asarray(
            list(aidc[slot])
            + [float(by_service_p.get((service, slot), 0.0)) for service in p_services]
            + [float(by_service_q.get((service, slot), 0.0)) for service in p_services],
            dtype=float,
        )
        planning_v.append(np.sqrt(np.maximum(0.0, coefficient.voltage_constant + coefficient.voltage_matrix.T @ numeric)))
        planning_i.append(anchored_polygon_loading(coefficient, numeric))
    numeric_controls = np.asarray(
        [
            list(aidc[slot])
            + [float(by_service_p.get((service, slot), 0.0)) for service in p_services]
            + [float(by_service_q.get((service, slot), 0.0)) for service in p_services]
            for slot in range(96)
        ],
        dtype=float,
    )
    cut_arithmetic: list[Mapping[str, object]] = []
    applied_cuts = tuple(restoration_cuts) if restoration_include_cuts else ()
    for cut_index, (cut, row) in enumerate(zip(applied_cuts, cut_rows, strict=True)):
        values = numeric_controls[int(cut.slot)]
        lhs = float(cut.actual_value) + float(
            np.asarray(cut.coefficients, dtype=float)
            @ (values - np.asarray(cut.anchor_controls, dtype=float))
        )
        rhs = float(cut.hard_limit) + (
            float(cut.margin) if cut.relation == ">=" else -float(cut.margin)
        )
        arithmetic_slack = lhs - rhs if cut.relation == ">=" else rhs - lhs
        solver_slack = -float(row.Slack) if cut.relation == ">=" else float(row.Slack)
        cut_arithmetic.append({
            "cut_index": cut_index,
            "cut_sha256": cut.sha256,
            "slot": int(cut.slot),
            "relation": cut.relation,
            "lhs": lhs,
            "rhs": rhs,
            "arithmetic_slack": float(arithmetic_slack),
            "solver_slack": solver_slack,
            "absolute_slack_crosscheck_error": abs(float(arithmetic_slack) - solver_slack),
        })
    termination = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.WORK_LIMIT: "WORK_LIMIT",
        GRB.SUBOPTIMAL: "SUBOPTIMAL",
    }.get(model.Status, f"STATUS_{model.Status}")
    classification = _bounded_compute_classification(
        termination, float(model.ObjVal), float(model.ObjBound),
    )
    return IntegratedMessResult(
        trajectory, np.asarray(planning_v), np.asarray(planning_i), float(model.ObjVal), controls,
        termination,
        grid_constraints, int(model.NumVars), int(model.NumConstrs),
        model_build_seconds, solve_seconds, _rss_bytes(),
        True, termination, float(model.ObjBound), float(model.MIPGap),
        int(model.NumBinVars), len(block.move), len(block.stay), float(eta.X),
        sum(abs(value) for value in fixed_p.values()),
        sum(abs(value) for value in fixed_q.values()),
        sum(variable.LB < variable.UB for variable in model.getVars()), 0,
        zero_actuation_objective=float(zero_rho),
        restricted_stationary_objective=float(restricted["objective"]),
        restricted_stationary_best_bound=float(restricted["best_bound"]),
        restricted_stationary_mip_gap=float(restricted["mip_gap"]),
        restricted_stationary_status=str(restricted["status"]),
        restricted_stationary_sum_abs_p_kw_slots=float(restricted["sum_abs_p"]),
        restricted_stationary_sum_abs_q_kvar_slots=float(restricted["sum_abs_q"]),
        restricted_incumbent_improves_zero=bool(
            bool(restricted["available"])
            and float(restricted["objective"]) < float(zero_rho) - RESOLVED_OBJECTIVE_TOLERANCE
        ),
        mip_start_accepted=bool(
            math.isfinite(quality_bound)
            and float(model.ObjVal) <= quality_bound + RESOLVED_OBJECTIVE_TOLERANCE
        ),
        work_limit_tiers_attempted=tuple(attempted),
        escalation_reason=escalation_reason if len(attempted) > 1 else None,
        bounded_compute_classification=classification,
        preferred_restricted_objective=preferred_objective,
        selected_restricted_start=selected_start,
        preferred_mip_start_loaded=preferred_loaded,
        restoration_cut_count=len(applied_cuts),
        restoration_trust_region_constraint_count=trust_region_constraint_count,
        restoration_recourse_trust_region_constraint_count=(
            recourse_trust_region_constraint_count
        ),
        restoration_cut_arithmetic=tuple(cut_arithmetic),
        fixed_discrete_MESS_decisions=fixed_discrete,
    )


def _rss_bytes() -> int:
    try:
        import psutil
        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return 0
