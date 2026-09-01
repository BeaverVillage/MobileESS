"""Deterministic non-scientific regression fixture for a local AC cut loop."""

from __future__ import annotations

from typing import Any


def run_fixture() -> dict[str, Any]:
    """Exercise FAIL -> local cut -> reoptimization -> PASS on a scalar LP.

    The scalar values are fixture-only and have no relationship to IEEE123,
    April schedules, or any frozen scientific parameter.
    """

    voltage_limit = 1.05
    intercept = 1.04
    local_sensitivity = 0.02
    control_upper = 1.0
    solve_count = 0
    fresh_ac_count = 0

    def solve(upper: float) -> float:
        nonlocal solve_count
        solve_count += 1
        # Exact solution of max u subject to 0 <= u <= upper.
        return max(0.0, min(1.0, float(upper)))

    def fresh_ac(control: float) -> tuple[float, bool]:
        nonlocal fresh_ac_count
        fresh_ac_count += 1
        voltage = intercept + local_sensitivity * control
        return voltage, voltage <= voltage_limit + 1e-12

    initial_control = solve(control_upper)
    initial_voltage, initial_pass = fresh_ac(initial_control)
    if initial_pass:
        raise RuntimeError("V17_AC_RESTORATION_FIXTURE_DID_NOT_CREATE_VIOLATION")

    # Violation-specific first-order cut at the failed operating point.
    local_cut_control_upper = initial_control + (voltage_limit - initial_voltage) / local_sensitivity
    restored_control = solve(min(control_upper, local_cut_control_upper))
    restored_voltage, restored_pass = fresh_ac(restored_control)
    if not restored_pass:
        raise RuntimeError("V17_AC_RESTORATION_FIXTURE_CUT_DID_NOT_RESTORE")

    return {
        "fixture_id": "V17_NON_SCIENTIFIC_LOCAL_AC_CUT_REGRESSION_V1",
        "scope": "DETERMINISTIC_UNIT_REGRESSION_ONLY_NO_SCIENCE_PARAMETERS",
        "initial": {
            "control": initial_control,
            "fresh_ac_voltage_pu": initial_voltage,
            "fresh_ac_status": "FAIL",
        },
        "cut": {
            "type": "LOCAL_VIOLATION_SPECIFIC_LINEAR_CUT",
            "control_upper": local_cut_control_upper,
        },
        "restored": {
            "control": restored_control,
            "fresh_ac_voltage_pu": restored_voltage,
            "fresh_ac_status": "PASS",
        },
        "optimization_call_count": solve_count,
        "fresh_ac_call_count": fresh_ac_count,
        "science_parameter_changes": 0,
        "status": "PASS_FAIL_CUT_REOPTIMIZE_PASS",
    }
