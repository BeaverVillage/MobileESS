"""Monolithic runner for the common V28R2 LP formulation."""

from __future__ import annotations

import math
import time

import numpy as np

from dayahead.grid_lp import LINE_POLYGON_FACES, V_MAX_SQUARED, V_MIN_SQUARED
from dayahead.v28r2.electrical_subproblem import is_dominated_mess_current_row, slot_coefficients
from dayahead.v28r2.solver_payload import SolverPayload, payload_from_registry
from dayahead.v28r2.variable_registry import VariableRegistry, build_resource_model


def add_grid_rows(registry: VariableRegistry, context: object, voltage: object, current: object) -> None:
    import gurobipy as gp

    model = registry.model
    for slot in range(96):
        coefficient = slot_coefficients(context, voltage, current, slot)
        controls = registry.control_expressions[slot]
        for node in range(len(coefficient.voltage_constant)):
            expression = float(coefficient.voltage_constant[node]) + gp.quicksum(
                float(coefficient.voltage_matrix[index, node]) * controls[index]
                for index in range(len(controls))
            )
            model.addConstr(expression >= V_MIN_SQUARED, name=f"grid_voltage_low[{slot},{node}]")
            model.addConstr(expression <= V_MAX_SQUARED, name=f"grid_voltage_high[{slot},{node}]")
        for branch, branch_name in enumerate(coefficient.branch_names):
            if is_dominated_mess_current_row(branch_name):
                continue
            expression = float(coefficient.current_constant[branch]) + gp.quicksum(
                float(coefficient.current_matrix[index, branch]) * controls[index]
                for index in range(len(controls))
            )
            current_hat = model.addVar(lb=0.0, name=f"current_hat[{slot},{branch}]")
            model.addConstr(current_hat >= expression, name=f"current_epigraph[{slot},{branch}]")
            if branch_name.startswith("transformer."):
                model.addConstr(current_hat <= 1.0, name=f"transformer_current_hard[{slot},{branch}]")
            else:
                model.addConstr(current_hat <= 1.0, name=f"line_current_hard[{slot},{branch}]")
                model.addConstr(registry.eta >= current_hat, name=f"line_objective[{slot},{branch}]")
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
) -> SolverPayload:
    from gurobipy import GRB

    started = time.perf_counter()
    registry = build_resource_model(data, voltage, case)
    add_grid_rows(registry, context, voltage, current)
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
