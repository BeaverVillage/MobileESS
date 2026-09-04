from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import gurobipy as gp
from gurobipy import GRB
import numpy as np

from dayahead.v17_ac_restoration_contract import RHO, RestorationCut, ViolationType
from dayahead.v34.integrated_mess import WORK_LIMIT_TIERS, _add_restoration_cuts
from dayahead.v37.contracts import BEAM_WIDTH, DEFAULT_K
from dayahead.v37r3.restoration import (
    K_MAX,
    extract_ac_violations,
    extract_voltage_violations,
)
from dayahead.v37r3.voltage_authority import load_joint_voltage_authority


REPO = Path(__file__).resolve().parents[2]


def _fresh_with_one_lower_violation() -> SimpleNamespace:
    voltage = np.ones((96, 1), dtype=float)
    voltage[7, 0] = 0.949
    return SimpleNamespace(
        day="2025-04-01",
        case="B2",
        schedule_sha256="a" * 64,
        node_names=("mess_sta01_pcc.1",),
        node_phases=("A",),
        branch_names=("line.one",),
        branch_phases=("A",),
        branch_kinds=("line",),
        phase_current_loading_pu=np.zeros((96, 1)),
        transformer_total_kva_loading_pu=np.full((96, 1), np.nan),
        voltage_pu=voltage,
    )


def _cut(violation, coefficient: float, iteration: int) -> RestorationCut:
    names = tuple(f"u[{index}]" for index in range(60))
    coefficients = np.zeros(60)
    coefficients[12] = coefficient
    radius = np.zeros(60)
    radius[12] = 55.0
    return RestorationCut(
        violation_sha256=violation.sha256,
        local_ac_operating_point_sha256="b" * 64,
        derivative_sha256="c" * 64,
        violation_type=ViolationType.VOLTAGE_LOWER,
        slot=7,
        relation=">=",
        actual_value=float(violation.actual_value),
        hard_limit=0.95,
        margin=0.000060616731687528454,
        trust_region_rho=RHO,
        iteration_index=iteration,
        control_names=names,
        anchor_controls=(0.0,) * 60,
        coefficients=tuple(map(float, coefficients)),
        local_radius=tuple(map(float, radius)),
    )


def test_april_only_joint_authority_has_complete_same_state_vectors() -> None:
    authority, _sha = load_joint_voltage_authority(REPO)
    gradients = authority["joint_gradients"]
    assert authority["May_data_used_for_derivation"] is False
    assert len(gradients) == 24 * 24 * 3
    assert all(row["P_Q_same_April_state"] is True for row in gradients)
    assert all(str(row["selected_day"]).startswith("2025-04-") for row in gradients)
    assert {row["phase"] for row in gradients} == {"A", "B", "C"}
    assert len({row["source_service"] for row in gradients}) == 24
    assert len({row["target_service"] for row in gradients}) == 24


def test_trigger_cumulative_insertion_and_final_cut_arithmetic() -> None:
    violations = extract_voltage_violations(_fresh_with_one_lower_violation())
    assert len(violations) == 1
    assert violations[0].slot == 7
    assert violations[0].phase == "A"

    model = gp.Model("v37_r3_cut_smoke")
    model.Params.OutputFlag = 0
    x = model.addVar(lb=-100.0, ub=100.0, name="mess_p")
    expressions = [tuple(0.0 for _ in range(60)) for _ in range(96)]
    expressions[7] = tuple([0.0] * 12 + [x] + [0.0] * 47)
    cuts = (_cut(violations[0], 0.001, 1), _cut(violations[0], 0.002, 2))
    rows, trust_count = _add_restoration_cuts(
        model, cuts[0].control_names, expressions, cuts,
    )
    model.setObjective(x, GRB.MINIMIZE)
    model.optimize()

    assert model.Status == GRB.OPTIMAL
    assert len(rows) == 2
    assert trust_count == 4
    assert model.getConstrByName("fresh_ac_restoration_lower[0,7]") is not None
    assert model.getConstrByName("fresh_ac_restoration_lower[1,7]") is not None
    for cut, row in zip(cuts, rows, strict=True):
        lhs = cut.actual_value + cut.coefficients[12] * x.X
        rhs = cut.hard_limit + cut.margin
        assert lhs >= rhs - 1.0e-8
        assert abs((lhs - rhs) + row.Slack) <= 1.0e-8


def test_exact_v17_extractor_includes_current_and_transformer_kva() -> None:
    fresh = _fresh_with_one_lower_violation()
    current = np.zeros((96, 2), dtype=float)
    current[3, 0] = 1.10
    current[4, 1] = 1.20
    transformer_kva = np.full((96, 2), np.nan, dtype=float)
    transformer_kva[4, 1] = 1.30
    complete = SimpleNamespace(
        **{
            **fresh.__dict__,
            "branch_names": ("line.one", "transformer.one"),
            "branch_phases": ("A", "B"),
            "branch_kinds": ("line", "transformer"),
            "phase_current_loading_pu": current,
            "transformer_total_kva_loading_pu": transformer_kva,
        }
    )
    violations = extract_ac_violations(complete)
    assert {row.violation_type for row in violations} == {
        ViolationType.VOLTAGE_LOWER,
        ViolationType.LINE_CURRENT,
        ViolationType.TRANSFORMER_CURRENT,
        ViolationType.TRANSFORMER_KVA,
    }


def test_frozen_algorithm_parameters_unchanged() -> None:
    assert DEFAULT_K == 200
    assert BEAM_WIDTH == 2
    assert WORK_LIMIT_TIERS == (60.0, 180.0, 300.0)
    assert RHO == 0.10
    assert K_MAX == 5
