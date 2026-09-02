"""V33M3 MESS block bound to the common V28R2 planning-grid rows."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Mapping, Sequence

import gurobipy as gp
from gurobipy import GRB
import numpy as np

from dayahead.grid_lp import LINE_POLYGON_FACES
from dayahead.v28r2.electrical_subproblem import SlotCoefficients, is_dominated_mess_current_row, slot_coefficients
from dayahead.v33m import MessMobilityInputs, ServicePCCMapping, add_mess_mobility_block, extract_mess_trajectory
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v33m.route_table import MobilityRouteTable

from .correction import StaticCorrection, bind_squared_voltage_bounds


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
    if len(inputs.mess_ids) != 1:
        raise ValueError("V34_SEQUENTIAL_COORDINATION_REQUIRES_ONE_VEHICLE_BLOCK")
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
    initial_energy = inputs.initial_energy_by_mess[mess_id]
    for (key_mess, slot, service), variable in block.occupancy.items():
        variable.Start = float(service == initial_service)
    for (key_mess, slot, service), variable in block.stay.items():
        variable.Start = float(service == initial_service)
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
    fixed_p = {} if fixed_mess_p_by_service is None else dict(fixed_mess_p_by_service)
    fixed_q = {} if fixed_mess_q_by_service is None else dict(fixed_mess_q_by_service)
    controls = tuple(map(str, voltage_authority["control_names"]))
    node_names = tuple(map(str, voltage_authority["node_names"]))
    if len(controls) != 60 or len(node_names) != 386:
        raise RuntimeError("V34_COMMON_GRID_AXIS")

    if not enforce_planning_grid_constraints:
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
            planning_i.append(coefficient.current_constant + coefficient.current_matrix.T @ vector)
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
    eta = model.addVar(lb=0.0, name="v34_rho_planning")
    grid_constraints = 0
    p_services = tuple(name[10:-1] for name in controls[12:36])
    q_services = tuple(name[12:-1] for name in controls[36:60])
    if p_services != q_services or set(p_services) != set(route_table.service_ids):
        raise RuntimeError("V34_COMMON_MESS_SERVICE_AXIS")

    def sparse_expression(base: float, vector: np.ndarray, slot: int) -> gp.LinExpr:
        constant = float(base + vector[:12] @ aidc[slot])
        constant += sum(float(vector[12 + index]) * float(fixed_p.get((service, slot), 0.0)) for index, service in enumerate(p_services))
        constant += sum(float(vector[36 + index]) * float(fixed_q.get((service, slot), 0.0)) for index, service in enumerate(p_services))
        variables = (
            [block.p_discharge[mess_id, slot, service] for service in p_services]
            + [block.p_charge[mess_id, slot, service] for service in p_services]
            + [block.q[mess_id, slot, service] for service in p_services]
        )
        scalars = np.concatenate((vector[12:36], -vector[12:36], vector[36:60]))
        nonzero = np.flatnonzero(np.abs(scalars) > 1e-15)
        return gp.LinExpr(
            [float(scalars[index]) for index in nonzero],
            [variables[index] for index in nonzero],
        ) + constant

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

        for index, branch in enumerate(coefficient.branch_names):
            expression = sparse_expression(float(coefficient.current_constant[index]), coefficient.current_matrix[:, index], slot)
            if not is_dominated_mess_current_row(branch):
                current = model.addVar(lb=-GRB.INFINITY, name=f"v34_i_aff[{slot},{index}]")
                current_hat = model.addVar(lb=0.0, ub=1.0, name=f"v34_i_hat[{slot},{index}]")
                model.addConstr(current == expression, name=f"v34_current_affine[{slot},{index}]")
                model.addConstr(current_hat >= current, name=f"v34_current_epigraph[{slot},{index}]")
                grid_constraints += 2
                if not branch.startswith("transformer."):
                    model.addConstr(eta >= current_hat, name=f"v34_current_objective[{slot},{index}]")
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
    solve_started = time.perf_counter(); model.optimize(); solve_seconds = time.perf_counter() - solve_started
    accepted_statuses = {GRB.OPTIMAL, GRB.WORK_LIMIT, GRB.TIME_LIMIT, GRB.SUBOPTIMAL}
    if model.Status not in accepted_statuses or model.SolCount < 1:
        raise RuntimeError(f"V34_INTEGRATED_MESS_SOLVER_STATUS:{model.Status}")
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
        planning_i.append(coefficient.current_constant + coefficient.current_matrix.T @ numeric)
    termination = {
        GRB.OPTIMAL: "OPTIMAL",
        GRB.TIME_LIMIT: "TIME_LIMIT",
        GRB.WORK_LIMIT: "WORK_LIMIT",
        GRB.SUBOPTIMAL: "SUBOPTIMAL",
    }.get(model.Status, f"STATUS_{model.Status}")
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
    )


def _rss_bytes() -> int:
    try:
        import psutil
        return int(psutil.Process().memory_info().rss)
    except (ImportError, OSError):
        return 0
