from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np

from dayahead import final_science_solver_v16_3
from dayahead.v17_ac_restoration_runner import _case_control_indices, _extract_violations


def test_common_case_control_eligibility_is_exact() -> None:
    assert _case_control_indices("B0") == ()
    assert _case_control_indices("B1") == tuple(range(12))
    assert _case_control_indices("B2") == tuple(range(12, 60))
    assert _case_control_indices("B3") == tuple(range(60))


def test_exact_voltage_violation_is_dispatchable() -> None:
    capture = {"voltage": np.asarray([1.05001, 0.94999]), "branch_metrics": []}
    rows = _extract_violations(
        day="2025-04-12", case="B2", slot=3, nodes=("1.1", "2.3"),
        capture=capture, schedule_sha256="a" * 64,
    )
    assert [row.violation_type.value for row in rows] == ["VOLTAGE_UPPER", "VOLTAGE_LOWER"]
    assert rows[0].asset == "bus.1" and rows[0].phase == "A"
    assert rows[1].asset == "bus.2" and rows[1].phase == "C"
    assert all(len(row.sha256) == 64 for row in rows)


def test_solver_has_executable_cut_and_stale_anchor_guard() -> None:
    source = inspect.getsource(final_science_solver_v16_3.solve_shadow)
    assert "fresh_ac_restoration_upper" in source
    assert "fresh_ac_restoration_lower" in source
    assert "fresh_ac_cut_trust_low" in source
    assert "OpenDSS" not in source.replace('"OpenDSS_call_count_inside_model"', "")


def test_materialized_apr12_and_common_7day_regression_pass() -> None:
    root = Path(__file__).resolve().parents[1]
    artifacts = root / "dayahead/artifacts/v17_candidate"
    trace = json.loads((artifacts / "V17_APR12_B2_RESTORATION_TRACE.json").read_text(encoding="utf-8"))
    regression = json.loads((artifacts / "V17_AC_RESTORATION_7DAY_REGRESSION.json").read_text(encoding="utf-8"))
    assert trace["status"] == "PASS"
    assert trace["restoration_iterations"] == 1
    assert trace["iterations"][0]["primary_Fresh_AC"]["voltage_violation_count"] == 2
    assert trace["final_primary_Fresh_AC"]["all_frozen_hard_constraints_pass"] is True
    assert trace["final_secondary_native_RegControl_Fresh_AC"]["all_frozen_hard_constraints_pass"] is True
    assert regression["classification"] == "V17_AC_LOOP_A_COMMON_CLOSED_LOOP_IMPLEMENTED_PASS"
    assert regression["schedule_count"] == 28
    assert regression["first_pass_pass_count"] == 27
    assert regression["restoration_required_count"] == 1
    assert regression["restoration_success_count"] == 1
    assert regression["restoration_failure_count"] == 0
    assert regression["all_28_final_primary_PASS"] is True
    assert regression["all_28_final_secondary_PASS"] is True
    assert regression["all_28_service_parity_PASS"] is True
    assert regression["all_28_terminal_SOC_PASS"] is True
    assert regression["May_scientific_input_reads"] == 0
    assert regression["June_scientific_input_reads"] == 0
    assert regression["remaining_April_day_runs"] == 0
