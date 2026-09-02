"""Immutable V34 chronology, cases, firewalls, and result labels."""

from __future__ import annotations

from datetime import date, timedelta
from types import MappingProxyType


AIDC_STARTING_HEAD = "8749f7785a61e0d3574dc3d847e63c8cd534ffbf"
MESS_SOURCE_HEAD = "e02ea8d9be9298a482faf42d97a7cb9ec6a7c2fc"
MESS_PREINTEGRATION_HEAD = "d42c3d2bdf1282f9e31563adfdbcf3100aa71f93"
BRANCH = "codex/v34-aidc-mess-april-calibration-validation"

OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
CASE_ACTUATORS = MappingProxyType({
    "B0": MappingProxyType({"aidc": False, "mess": False}),
    "B1": MappingProxyType({"aidc": True, "mess": False}),
    "B2": MappingProxyType({"aidc": False, "mess": True}),
    "B3": MappingProxyType({"aidc": True, "mess": True}),
})


def _days(first: date, last: date) -> tuple[str, ...]:
    return tuple(
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    )


CALIBRATION_DAYS = _days(date(2025, 4, 1), date(2025, 4, 20))
VALIDATION_DAYS = _days(date(2025, 4, 21), date(2025, 4, 30))
CALIBRATION_CASES = ("B1", "B3")
PHASE_LABELS = (
    "APR01_20_AC_FIDELITY_CALIBRATION",
    "APR21_30_PROSPECTIVE_UNCORRECTED_RESIDUAL_VALIDATION",
    "APR21_30_CORRECTED_INTEGRATED_VALIDATION",
)
CANDIDATE_FAMILIES = ("M1", "M2", "M3")
PLANNING_VMIN_PU = 0.95
PLANNING_VMAX_PU = 1.05
SLOTS = 96
DAY_PROCESSES = 4
SOLVER_THREADS = 4

ACTUAL_AIDC_FIREWALL_FIELDS = (
    "grid_voltage_reads_for_AIDC_decision",
    "grid_current_reads_for_AIDC_decision",
    "transformer_loading_reads_for_AIDC_decision",
    "rho_reads_for_AIDC_decision",
    "Fresh_reads_for_AIDC_decision",
    "planning_grid_sensitivity_reads_for_Actual_AIDC_decision",
)

MAY_FIREWALL_FIELDS = (
    "MAY_SOURCE_NUMERIC_READS",
    "MAY_TARGET_READS",
    "MAY_OPTIMIZATION_CALLS",
    "MAY_FRESH_CALLS",
    "MAY_RESULT_READS",
)

CLASSIFICATIONS = (
    "V34_APRIL_CALIBRATION_VALIDATION_PASS_MAY_PREFREEZE_READY",
    "V34_MESS_INTEGRATION_BLOCKED",
    "V34_APRIL_FORECAST_AUTHORITY_BLOCKED",
    "V34_APR01_20_CALIBRATION_BLOCKED",
    "V34_STATIC_AC_FIDELITY_CORRECTION_INSUFFICIENT",
    "V34_CORRECTION_BINDING_BLOCKED",
    "V34_APR21_30_DAYAHEAD_PHYSICAL_FAIL",
    "V34_APR21_30_ACTUAL_PHYSICAL_FAIL",
    "V34_AIDC_GRID_FEEDBACK_FIREWALL_FAIL",
    "V34_MESS_ACTUAL_FIREWALL_FAIL",
    "V34_CAUSALITY_FAIL",
    "V34_IMPLEMENTATION_FAIL",
)


def assert_official_cases(cases: tuple[str, ...] | list[str]) -> None:
    if tuple(cases) != OFFICIAL_CASES:
        raise ValueError("V34_OFFICIAL_CASES_MUST_BE_EXACTLY_B0_B1_B2_B3")


def reject_may(day: str) -> None:
    if str(day).startswith("2025-05-"):
        raise PermissionError("V34_MAY_NUMERIC_FIREWALL")

