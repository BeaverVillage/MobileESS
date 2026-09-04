"""PUE-free extraction of the frozen V16.3 electrical LP subproblem."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from dayahead.grid_lp import LINE_POLYGON_FACES, V_MAX_SQUARED, V_MIN_SQUARED
from dayahead.v28r2.variable_registry import VariableRegistry, configure_model, value


_MESS_CURRENT_ROW = re.compile(r"^transformer\.mess_(?:idc|sta)\d{2}_tx::[abc]$")


def is_dominated_mess_current_row(name: str) -> bool:
    """Frozen V16.3 rule for generated dedicated MESS transformer phases."""

    return _MESS_CURRENT_ROW.fullmatch(str(name).lower()) is not None


def _sha(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=float).encode()).hexdigest()


def _planning_flow_base_and_sensitivity(binding: object, slot: int, anchor: np.ndarray):
    data = binding.factories[slot].data
    branches = tuple(data.branches)
    controls = tuple(
        [f"aidc_load_kw[AIDC{index:02d}]" for index in range(1, 13)]
        + sorted(key for key in binding.baseline_master[slot] if key.startswith("mess_p_kw["))
        + sorted(key for key in binding.baseline_master[slot] if key.startswith("mess_q_kvar["))
    )
    master = dict(binding.baseline_master[slot])
    for index, key in enumerate(controls):
        master[key] = float(anchor[index])
    outgoing = defaultdict(list)
    for index, branch in enumerate(branches):
        outgoing[(branch.parent_bus, branch.phase)].append(index)
    p = np.zeros(len(branches)); q = np.zeros(len(branches))
    sp = np.zeros((len(branches), 60)); sq = np.zeros((len(branches), 60))
    control_index = {key: index for index, key in enumerate(controls)}
    for index in reversed(range(len(branches))):
        branch = branches[index]
        node = (branch.child_bus, branch.phase)
        p[index] = float(data.base_load_p_kw.get(node, 0.0)) - sum(
            float(coefficient) * master[key] for key, coefficient in data.master_p_injection.get(node, {}).items()
        )
        q[index] = float(data.base_load_q_kvar.get(node, 0.0)) - sum(
            float(coefficient) * master[key] for key, coefficient in data.master_q_injection.get(node, {}).items()
        )
        for key, coefficient in data.master_p_injection.get(node, {}).items():
            sp[index, control_index[key]] -= float(coefficient)
        for key, coefficient in data.master_q_injection.get(node, {}).items():
            sq[index, control_index[key]] -= float(coefficient)
        for child in outgoing.get(node, ()):
            p[index] += p[child]; q[index] += q[child]
            sp[index] += sp[child]; sq[index] += sq[child]
    return p, q, sp, sq


@dataclass(frozen=True)
class SlotCoefficients:
    slot: int
    control_names: tuple[str, ...]
    branch_names: tuple[str, ...]
    anchor: np.ndarray
    voltage_constant: np.ndarray
    voltage_matrix: np.ndarray
    current_constant: np.ndarray
    current_matrix: np.ndarray
    flow_p_constant: np.ndarray
    flow_q_constant: np.ndarray
    flow_p_matrix: np.ndarray
    flow_q_matrix: np.ndarray
    transformer_ratings: tuple[float | None, ...]
    coefficient_sha256: str


def slot_coefficients(context: object, voltage: object, current: object, slot: int) -> SlotCoefficients:
    _reference, _vintage, _background, binding, _path, _authority = context
    controls = tuple(map(str, voltage["control_names"]))
    branches = tuple(map(str, voltage["branch_names"]))
    if controls != tuple(map(str, current["control_names"])) or branches != tuple(map(str, current["branch_names"])):
        raise RuntimeError("V28R2_ELECTRICAL_AXIS_MISMATCH")
    anchor = np.asarray(voltage["anchor_control"][slot], dtype=float)
    h = np.asarray(voltage["sensitivity"][slot], dtype=float)
    v0 = np.asarray(voltage["anchor_v_squared"][slot], dtype=float)
    ji = np.asarray(current["current_sensitivity_pu_per_control"][slot], dtype=float)
    i0 = np.asarray(current["anchor_current_loading_pu"][slot], dtype=float)
    p0, q0, sp, sq = _planning_flow_base_and_sensitivity(binding, slot, anchor)
    rows = tuple(binding.factories[slot].data.branches)
    ratings = tuple(
        binding.factories[slot].data.transformer_limit_kva.get((row.branch_id, row.phase))
        for row in rows
    )
    payload = {
        "slot": slot, "controls": controls, "branches": branches, "anchor": anchor.tolist(),
        "v_constant": (v0 - h.T @ anchor).tolist(), "H": h.tolist(),
        "i_constant": (i0 - ji.T @ anchor).tolist(), "J_I": ji.tolist(),
        "p_constant": (p0 - sp @ anchor).tolist(), "q_constant": (q0 - sq @ anchor).tolist(),
        "S_P": sp.tolist(), "S_Q": sq.tolist(), "ratings": ratings,
    }
    return SlotCoefficients(
        slot, controls, branches, anchor, v0 - h.T @ anchor, h,
        i0 - ji.T @ anchor, ji, p0 - sp @ anchor, q0 - sq @ anchor,
        sp, sq, ratings, _sha(payload),
    )


@dataclass(frozen=True)
class SubproblemResult:
    slot: int
    feasible: bool
    objective: float | None
    gradient: tuple[float, ...]
    intercept: float | None
    proof: float | None
    farkas_cut_violation: float | None
    dual_sha256: str
    dual_nonzero_count: int
    critical_branch: str | None
    critical_loading: float | None
    status: str
    runtime_seconds: float


class ExactGridSubproblem:
    def __init__(self, coefficients: SlotCoefficients):
        import gurobipy as gp
        from gurobipy import GRB

        self.coefficients = coefficients
        self.model = gp.Model(f"v28r2_grid_sp_{coefficients.slot:02d}")
        configure_model(self.model)
        model = self.model
        self.registry = []
        voltage = [model.addVar(lb=V_MIN_SQUARED, ub=V_MAX_SQUARED, name=f"v[{index}]") for index in range(len(coefficients.voltage_constant))]
        current = [model.addVar(lb=-GRB.INFINITY, name=f"i_aff[{index}]") for index in range(len(coefficients.current_constant))]
        self.current_hat = [
            model.addVar(
                lb=0.0,
                ub=(GRB.INFINITY if is_dominated_mess_current_row(name) else 1.0),
                name=f"i_hat[{index}]",
            )
            for index, name in enumerate(coefficients.branch_names)
        ]
        flow_p = [model.addVar(lb=-GRB.INFINITY, name=f"tx_p[{index}]") for index in range(len(coefficients.flow_p_constant))]
        flow_q = [model.addVar(lb=-GRB.INFINITY, name=f"tx_q[{index}]") for index in range(len(coefficients.flow_q_constant))]
        self.rho = model.addVar(lb=0.0, name="rho_t")
        self.voltage_rows, self.current_rows, self.p_rows, self.q_rows = [], [], [], []
        for index, variable in enumerate(voltage):
            row = model.addConstr(variable == float(coefficients.voltage_constant[index]), name=f"voltage_affine[{index}]")
            self.registry.append((row, coefficients.voltage_matrix[:, index]))
            self.voltage_rows.append(row)
        for index, variable in enumerate(current):
            row = model.addConstr(variable == float(coefficients.current_constant[index]), name=f"current_affine[{index}]")
            self.registry.append((row, coefficients.current_matrix[:, index]))
            self.current_rows.append(row)
            if is_dominated_mess_current_row(coefficients.branch_names[index]):
                continue
            model.addConstr(self.current_hat[index] >= variable, name=f"current_epigraph[{index}]")
            if not coefficients.branch_names[index].startswith("transformer."):
                model.addConstr(self.rho >= self.current_hat[index], name=f"line_objective[{index}]")
        for index in range(len(flow_p)):
            p_row = model.addConstr(flow_p[index] == float(coefficients.flow_p_constant[index]), name=f"flow_p_affine[{index}]")
            q_row = model.addConstr(flow_q[index] == float(coefficients.flow_q_constant[index]), name=f"flow_q_affine[{index}]")
            self.registry.extend(((p_row, coefficients.flow_p_matrix[index]), (q_row, coefficients.flow_q_matrix[index])))
            self.p_rows.append(p_row)
            self.q_rows.append(q_row)
            rating = coefficients.transformer_ratings[index]
            if rating is not None:
                apothem = float(rating) * math.cos(math.pi / LINE_POLYGON_FACES)
                for face in range(LINE_POLYGON_FACES):
                    angle = 2.0 * math.pi * face / LINE_POLYGON_FACES
                    model.addConstr(
                        math.cos(angle) * flow_p[index] + math.sin(angle) * flow_q[index] <= apothem,
                        name=f"transformer_total_kva[{index},{face}]",
                    )
        model.setObjective(self.rho, GRB.MINIMIZE)
        model.update()

    def solve(self, controls: Sequence[float], iteration: int, raw_dir: Path | None = None) -> SubproblemResult:
        from gurobipy import GRB

        x = np.asarray(controls, dtype=float)
        coefficient = self.coefficients
        for index, row in enumerate(self.voltage_rows):
            row.RHS = float(coefficient.voltage_constant[index] + coefficient.voltage_matrix[:, index] @ x)
        for index, row in enumerate(self.current_rows):
            row.RHS = float(coefficient.current_constant[index] + coefficient.current_matrix[:, index] @ x)
        for index, row in enumerate(self.p_rows):
            row.RHS = float(coefficient.flow_p_constant[index] + coefficient.flow_p_matrix[index] @ x)
        for index, row in enumerate(self.q_rows):
            row.RHS = float(coefficient.flow_q_constant[index] + coefficient.flow_q_matrix[index] @ x)
        self.model.optimize()
        runtime = float(self.model.Runtime)
        constraints = self.model.getConstrs()
        if self.model.Status == GRB.OPTIMAL:
            dual = {row.ConstrName: float(row.Pi) for row, _ in self.registry}
            gradient = sum(
                (float(row.Pi) * np.asarray(vector, dtype=float) for row, vector in self.registry),
                start=np.zeros(60),
            )
            objective = float(self.model.ObjVal)
            lines = [
                (float(self.current_hat[index].X), coefficient.branch_names[index])
                for index in range(len(self.current_hat))
                if not coefficient.branch_names[index].startswith("transformer.")
            ]
            loading, branch = max(lines, key=lambda item: (item[0], item[1]))
            result = SubproblemResult(
                coefficient.slot, True, objective, tuple(map(float, gradient)),
                objective - float(gradient @ x), None, None, _sha(dual),
                sum(abs(value) > 1e-12 for value in dual.values()), branch, loading,
                "OPTIMAL", runtime,
            )
        elif self.model.Status == GRB.INFEASIBLE:
            multipliers = np.asarray(self.model.getAttr("FarkasDual", constraints), dtype=float)
            dual = {row.ConstrName: float(value) for row, value in zip(constraints, multipliers, strict=True)}
            gradient = sum(
                (float(row.FarkasDual) * np.asarray(vector, dtype=float) for row, vector in self.registry),
                start=np.zeros(60),
            )
            variables = self.model.getVars()
            combined = np.zeros(len(variables), dtype=float)
            for row, multiplier in zip(constraints, multipliers, strict=True):
                if abs(float(multiplier)) <= 1e-15:
                    continue
                expression = self.model.getRow(row)
                for term in range(expression.size()):
                    combined[expression.getVar(term).index] += float(multiplier) * float(expression.getCoeff(term))
            rhs = float(sum(float(multiplier) * float(row.RHS) for row, multiplier in zip(constraints, multipliers, strict=True)))
            minimum = 0.0
            for variable, scalar in zip(variables, combined, strict=True):
                if abs(float(scalar)) <= 1e-15:
                    continue
                bound = float(variable.LB if scalar > 0 else variable.UB)
                if not math.isfinite(bound):
                    raise RuntimeError("V28R2_FARKAS_UNBOUNDED_MINIMUM")
                minimum += float(scalar) * bound
            violation = minimum - rhs
            if violation <= 1e-10:
                raise RuntimeError("V28R2_INVALID_FARKAS_CERTIFICATE")
            result = SubproblemResult(
                coefficient.slot, False, None, tuple(map(float, gradient)), None,
                float(self.model.FarkasProof), float(violation), _sha(dual),
                sum(abs(value) > 1e-12 for value in dual.values()), None, None,
                "INFEASIBLE_FARKAS", runtime,
            )
        else:
            raise RuntimeError(f"V28R2_GRID_SUBPROBLEM_STATUS:{self.model.Status}")
        if raw_dir is not None:
            raw_dir.mkdir(parents=True, exist_ok=True)
            path = raw_dir / f"iter_{iteration:03d}_slot_{coefficient.slot:02d}.json"
            path.write_text(json.dumps({
                "slot": result.slot, "iteration": iteration, "status": result.status,
                "gradient": result.gradient, "objective": result.objective,
                "FarkasProof": result.proof, "bound_aware_cut_violation": result.farkas_cut_violation,
                "dual_sha256": result.dual_sha256,
            }, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        return result


def add_cut(master: VariableRegistry, result: SubproblemResult, index: int) -> str:
    import gurobipy as gp

    expression = gp.quicksum(
        float(result.gradient[control]) * master.control_expressions[result.slot][control]
        for control in range(60)
    )
    if result.feasible:
        master.model.addConstr(master.eta >= float(result.intercept) + expression, name=f"optimality_cut[{index},{result.slot}]")
        return "OPTIMALITY"
    controls = np.asarray([value(item) for item in master.control_expressions[result.slot]])
    threshold = float(np.asarray(result.gradient) @ controls) + float(result.farkas_cut_violation)
    master.model.addConstr(-expression <= -threshold, name=f"farkas_cut[{index},{result.slot}]")
    return "FARKAS"
