"""Prospective V16.3 AC-anchored affine voltage model.

This module is deliberately outside the active V16.2 factory.  It represents
frozen D-1 voltage sensitivities as master-dependent LP rows; regulator taps
are immutable input data and never optimization variables.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping, Sequence

from .grid_lp import FeasibilityCut, GridLPSolution, MasterDependentRow, OptimalityCut


V_MIN_SQUARED = 0.95**2
V_MAX_SQUARED = 1.05**2


@dataclass(frozen=True)
class FrozenD1ControlState:
    operating_day: str
    regulator_taps_96: tuple[Mapping[str, float], ...]
    capacitor_states_96: tuple[Mapping[str, tuple[int, ...]], ...]
    source_kind: str = "D1_FORECAST_ONLY_AC_ANCHOR"

    def __post_init__(self) -> None:
        if len(self.regulator_taps_96) != 96 or len(self.capacitor_states_96) != 96:
            raise ValueError("V163_CONTROL_STATE_REQUIRES_96_SLOTS")
        expected = {"reg1a", "reg2a", "reg3a", "reg3c", "reg4a", "reg4b", "reg4c"}
        if any(set(row) != expected for row in self.regulator_taps_96):
            raise ValueError("V163_ALL_SEVEN_NATIVE_REGULATORS_REQUIRED")

    def fingerprint(self) -> str:
        payload = {
            "operating_day": self.operating_day,
            "regulator_taps_96": self.regulator_taps_96,
            "capacitor_states_96": self.capacitor_states_96,
            "source_kind": self.source_kind,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class AcAnchoredAffineVoltageSlice:
    time_index: int
    node_names: tuple[str, ...]
    control_names: tuple[str, ...]
    anchor_v_squared: tuple[float, ...]
    sensitivity_by_control: Mapping[str, tuple[float, ...]]
    anchor_control: Mapping[str, float]
    regulator_taps: Mapping[str, float]
    capacitor_states: Mapping[str, tuple[int, ...]]

    def __post_init__(self) -> None:
        if not 0 <= self.time_index < 96:
            raise ValueError("V163_TIME_INDEX_OUT_OF_RANGE")
        if len(self.node_names) != len(self.anchor_v_squared):
            raise ValueError("V163_NODE_AXIS_MISMATCH")
        if set(self.control_names) != set(self.sensitivity_by_control) or set(self.control_names) != set(self.anchor_control):
            raise ValueError("V163_CONTROL_AXIS_MISMATCH")
        if any(len(self.sensitivity_by_control[key]) != len(self.node_names) for key in self.control_names):
            raise ValueError("V163_SENSITIVITY_NODE_AXIS_MISMATCH")
        if any(not isinstance(value, float) for value in self.anchor_v_squared):
            raise TypeError("V163_SQUARED_VOLTAGE_MUST_BE_FLOAT")

    @property
    def variable_types(self) -> Mapping[str, str]:
        return {name: "CONTINUOUS_MASTER_INPUT" for name in self.control_names}

    def evaluate(self, master: Mapping[str, float]) -> Mapping[str, float]:
        delta = {key: float(master[key]) - float(self.anchor_control[key]) for key in self.control_names}
        return {
            node: self.anchor_v_squared[index] + sum(
                self.sensitivity_by_control[key][index] * delta[key] for key in self.control_names
            )
            for index, node in enumerate(self.node_names)
        }

    def master_dependent_rows(self) -> tuple[MasterDependentRow, ...]:
        rows: list[MasterDependentRow] = []
        for index, node in enumerate(self.node_names):
            offset = self.anchor_v_squared[index] - sum(
                self.sensitivity_by_control[key][index] * float(self.anchor_control[key])
                for key in self.control_names
            )
            coefficients = {key: self.sensitivity_by_control[key][index] for key in self.control_names}
            # A zero-valued auxiliary variable gives the canonical form
            # 0 >= b - Bx for both lower and upper hard voltage bounds.
            rows.append(MasterDependentRow(
                f"affine_voltage_lower[{node}]", {key: -value for key, value in coefficients.items()},
                V_MIN_SQUARED - offset, ">=",
            ))
            rows.append(MasterDependentRow(
                f"affine_voltage_upper[{node}]", coefficients, offset - V_MAX_SQUARED, ">=",
            ))
        return tuple(rows)

    def fingerprint(self) -> str:
        payload = {
            "time_index": self.time_index,
            "node_names": self.node_names,
            "control_names": self.control_names,
            "anchor_v_squared": self.anchor_v_squared,
            "sensitivity_by_control": self.sensitivity_by_control,
            "anchor_control": self.anchor_control,
            "regulator_taps": self.regulator_taps,
            "capacitor_states": self.capacitor_states,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class AffineVoltageGridLPFactory:
    """Time-local LP certificate factory for prospective affine voltage rows."""

    scientific_eligible = False
    integer_variable_count = 0
    binary_variable_count = 0
    opendss_call_count = 0

    def __init__(self, affine_slice: AcAnchoredAffineVoltageSlice):
        self.affine_slice = affine_slice
        self.master_dependent_row_registry = affine_slice.master_dependent_rows()

    def solve(self, master: Mapping[str, float], source_iteration: int = 0) -> GridLPSolution:
        try:
            import gurobipy as gp
            from gurobipy import GRB
        except ImportError as exc:
            raise RuntimeError("gurobipy is required for V16.3 prospective dual tests") from exc
        model = gp.Model(f"v163_affine_voltage_t{self.affine_slice.time_index:02d}")
        model.Params.OutputFlag = 0
        model.Params.DualReductions = 0
        model.Params.InfUnbdInfo = 1
        zero = model.addVar(lb=0.0, ub=0.0, name="affine_voltage_zero")
        registry = [(model.addConstr(zero >= row.rhs(master), name=row.row_name), row) for row in self.master_dependent_row_registry]
        model.setObjective(0.0, GRB.MINIMIZE)
        model.optimize()
        keys = self.affine_slice.control_names
        if model.Status == GRB.OPTIMAL:
            pi = {row.row_name: float(constr.Pi) for constr, row in registry}
            gradient = {key: sum(float(constr.Pi) * row.master_coefficients.get(key, 0.0) for constr, row in registry) for key in keys}
            cut = OptimalityCut(self.affine_slice.time_index, -sum(gradient[key] * float(master[key]) for key in keys), gradient, source_iteration)
            return GridLPSolution(self.affine_slice.time_index, True, 0.0, pi, {}, cut, None, {})
        if model.Status == GRB.INFEASIBLE:
            rays = {row.row_name: float(constr.FarkasDual) for constr, row in registry}
            gradient = {key: sum(float(constr.FarkasDual) * row.master_coefficients.get(key, 0.0) for constr, row in registry) for key in keys}
            proof = float(model.FarkasProof)
            threshold = sum(gradient[key] * float(master[key]) for key in keys) + proof
            cut = FeasibilityCut(self.affine_slice.time_index, {key: -value for key, value in gradient.items()}, -threshold, source_iteration)
            return GridLPSolution(self.affine_slice.time_index, False, None, {}, rays, None, cut, {})
        raise RuntimeError(f"V163_UNEXPECTED_GUROBI_STATUS:{model.Status}")


def make_96_affine_factories(slices: Sequence[AcAnchoredAffineVoltageSlice]) -> tuple[AffineVoltageGridLPFactory, ...]:
    if len(slices) != 96 or tuple(row.time_index for row in slices) != tuple(range(96)):
        raise ValueError("V163_AFFINE_FACTORY_TIME_AXIS_MUST_BE_96")
    return tuple(AffineVoltageGridLPFactory(row) for row in slices)
