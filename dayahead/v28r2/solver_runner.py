"""Monolithic runner for the common V28R2 LP formulation."""

from __future__ import annotations

import math
import time

import numpy as np

from dayahead.grid_lp import LINE_POLYGON_FACES, V_MAX_SQUARED, V_MIN_SQUARED
from dayahead.v28r2.electrical_subproblem import (
    anchored_polygon_parameters,
    is_dominated_mess_current_row,
    slot_coefficients,
)
from dayahead.v28r2.solver_payload import SolverPayload, payload_from_registry
from dayahead.v28r2.variable_registry import VariableRegistry, build_resource_model


def add_grid_rows(
    registry: VariableRegistry,
    context: object,
    voltage: object,
    current: object,
    *,
    planning_vmax_pu: float | None = None,
    voltage_correction: object | None = None,
) -> None:
    import gurobipy as gp

    planning_vmax_squared = V_MAX_SQUARED if planning_vmax_pu is None else float(planning_vmax_pu) ** 2
    if not math.isfinite(planning_vmax_squared) or planning_vmax_squared <= V_MIN_SQUARED:
        raise ValueError("V28R2_PLANNING_VMAX_RANGE")
    model = registry.model
    # The common line-current objective is also the frozen hard line-loading
    # gate.  One upper bound avoids duplicating every polygon face.
    registry.eta.UB = min(float(registry.eta.UB), 1.0)
    for slot in range(96):
        coefficient = slot_coefficients(context, voltage, current, slot)
        controls = registry.control_expressions[slot]
        for node in range(len(coefficient.voltage_constant)):
            expression = float(coefficient.voltage_constant[node]) + gp.quicksum(
                float(coefficient.voltage_matrix[index, node]) * controls[index]
                for index in range(len(controls))
            )
            if voltage_correction is None:
                lower_squared, upper_squared = V_MIN_SQUARED, planning_vmax_squared
            else:
                from dayahead.v34.correction import bind_squared_voltage_bounds

                node_name = str(voltage["node_names"][node])
                phase = "ABC"[int(node_name.rsplit(".", 1)[1]) - 1]
                up, low = voltage_correction.value_for(node_name, phase, slot)
                lower_squared, upper_squared = bind_squared_voltage_bounds(up, low)
            model.addConstr(expression >= lower_squared, name=f"grid_voltage_low[{slot},{node}]")
            model.addConstr(expression <= upper_squared, name=f"grid_voltage_high[{slot},{node}]")
        bias, correction, _polygon_anchor = anchored_polygon_parameters(coefficient)
        for branch, branch_name in enumerate(coefficient.branch_names):
            if is_dominated_mess_current_row(branch_name):
                continue
            if branch_name.startswith("transformer."):
                expression = float(coefficient.current_constant[branch]) + gp.quicksum(
                    float(coefficient.current_matrix[index, branch]) * controls[index]
                    for index in range(len(controls))
                )
                current_hat = model.addVar(lb=0.0, name=f"current_hat[{slot},{branch}]")
                model.addConstr(current_hat >= expression, name=f"current_epigraph[{slot},{branch}]")
                model.addConstr(current_hat <= 1.0, name=f"transformer_current_hard[{slot},{branch}]")
            else:
                # Store each 60-control sparse affine row once; the 16 face
                # inequalities then contain only four scalar variables.
                p_flow = model.addVar(lb=-gp.GRB.INFINITY, name=f"line_p[{slot},{branch}]")
                q_flow = model.addVar(lb=-gp.GRB.INFINITY, name=f"line_q[{slot},{branch}]")
                tangent_correction = model.addVar(
                    lb=-gp.GRB.INFINITY, name=f"line_tangent_correction[{slot},{branch}]",
                )
                model.addConstr(
                    p_flow == float(coefficient.flow_p_constant[branch]) + gp.quicksum(
                        float(coefficient.flow_p_matrix[branch, index]) * controls[index]
                        for index in range(len(controls))
                    ),
                    name=f"line_p_affine[{slot},{branch}]",
                )
                model.addConstr(
                    q_flow == float(coefficient.flow_q_constant[branch]) + gp.quicksum(
                        float(coefficient.flow_q_matrix[branch, index]) * controls[index]
                        for index in range(len(controls))
                    ),
                    name=f"line_q_affine[{slot},{branch}]",
                )
                model.addConstr(
                    tangent_correction == gp.quicksum(
                        float(correction[index, branch])
                        * (controls[index] - float(coefficient.anchor[index]))
                        for index in range(len(controls))
                    ),
                    name=f"line_tangent_correction_affine[{slot},{branch}]",
                )
                apothem = (
                    float(coefficient.branch_limits[branch])
                    * math.cos(math.pi / LINE_POLYGON_FACES)
                )
                for face in range(LINE_POLYGON_FACES):
                    angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                    model.addConstr(
                        registry.eta
                        >= (
                            math.cos(angle) * p_flow + math.sin(angle) * q_flow
                        ) / apothem
                        + tangent_correction
                        + float(bias[branch]),
                        name=f"line_current_polygon[{slot},{branch},{face}]",
                    )
        for branch, rating in enumerate(coefficient.transformer_ratings):
            if rating is None:
                continue
            p = float(coefficient.flow_p_constant[branch]) + gp.quicksum(
                float(coefficient.flow_p_matrix[branch, index]) * controls[index]
                for index in range(len(controls))
            )
            q = float(coefficient.flow_q_constant[branch]) + gp.quicksum(
                float(coefficient.flow_q_matrix[branch, index]) * controls[index]
                for index in range(len(controls))
            )
            apothem = float(rating) * math.cos(math.pi / LINE_POLYGON_FACES)
            for face in range(LINE_POLYGON_FACES):
                angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                model.addConstr(
                    math.cos(angle) * p + math.sin(angle) * q <= apothem,
                    name=f"transformer_total_kva_hard[{slot},{branch},{face}]",
                )
    model.update()


def solve_monolithic(
    *, data, context: object, voltage: object, current: object, case: str,
    voltage_correction: object | None = None,
    mess_disabled: bool = False,
) -> SolverPayload:
    from gurobipy import GRB

    started = time.perf_counter()
    registry = build_resource_model(data, voltage, case, mess_disabled=mess_disabled)
    add_grid_rows(
        registry, context, voltage, current,
        voltage_correction=voltage_correction,
    )
    registry.model.optimize()
    runtime = time.perf_counter() - started
    if registry.model.Status != GRB.OPTIMAL:
        raise RuntimeError(f"V28R2_MONOLITHIC_STATUS:{case}:{int(registry.model.Status)}")
    objective = float(registry.model.ObjVal)
    return payload_from_registry(
        registry, solver="MONOLITHIC", status="OPTIMAL", hard_feasible=True,
        objective=objective, lower_bound=float(registry.model.ObjBound), upper_bound=objective,
        gap=0.0, iterations=int(registry.model.IterCount), optimality_cuts=0,
        feasibility_cuts=0, termination_reason="GUROBI_OPTIMAL", runtime_seconds=runtime,
    )
