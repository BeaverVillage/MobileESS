"""Immutable V35 chronology, case semantics, firewalls, and gate constants."""

from __future__ import annotations

from datetime import date, timedelta
from types import MappingProxyType
from typing import Mapping, Sequence


BRANCH = "codex/v35-selfhealing-april-may-final"
V34_CHECKPOINT_HEAD = "916de691834b3c1098fa2431fe21e4e3193542fb"
SLOTS = 96
RESOLUTION_MINUTES = 15
MESS_IDS = ("MESS01", "MESS02", "MESS03", "MESS04")
MESS_ORDER = MESS_IDS
WORK_LIMIT_TIERS = (60.0, 180.0, 300.0)
SOLVER_SEED = 20260828
MEMORY_RESERVE_BYTES = 4 * 1024**3
APRIL_RETRY_LIMIT = 5
MAY_RETRY_LIMIT = 3

OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
CASE_ACTUATORS = MappingProxyType({
    "B0": MappingProxyType({"aidc": False, "mess": False}),
    "B1": MappingProxyType({"aidc": True, "mess": False}),
    "B2": MappingProxyType({"aidc": False, "mess": True}),
    "B3": MappingProxyType({"aidc": True, "mess": True}),
})
AIDC_STAGE_CASE = MappingProxyType({"B0": "B0", "B1": "B1", "B2": "B0", "B3": "B1"})


def _days(first: date, last: date) -> tuple[str, ...]:
    return tuple(
        (first + timedelta(days=offset)).isoformat()
        for offset in range((last - first).days + 1)
    )


CALIBRATION_DAYS = _days(date(2025, 4, 1), date(2025, 4, 20))
VALIDATION_DAYS = _days(date(2025, 4, 21), date(2025, 4, 30))
APRIL_DAYS = CALIBRATION_DAYS + VALIDATION_DAYS
MAY_DAYS = _days(date(2025, 5, 1), date(2025, 5, 31))

PHASE_CALIBRATION = "APR01_20_AC_FIDELITY_CALIBRATION"
PHASE_PROSPECTIVE = "APR21_30_PROSPECTIVE_UNCORRECTED_RESIDUAL_VALIDATION"
PHASE_CORRECTED = "APR21_30_CORRECTED_INTEGRATED_VALIDATION"
PHASE_MAY = "LOCKED_FINAL_EVALUATION"
PHASES = (PHASE_CALIBRATION, PHASE_PROSPECTIVE, PHASE_CORRECTED, PHASE_MAY)

ACTUAL_AIDC_FIREWALL_FIELDS = (
    "grid_voltage_reads_for_AIDC_decision",
    "grid_current_reads_for_AIDC_decision",
    "transformer_loading_reads_for_AIDC_decision",
    "rho_reads_for_AIDC_decision",
    "Fresh_reads_for_AIDC_decision",
    "planning_grid_sensitivity_reads_for_Actual_AIDC_decision",
)
ACTUAL_MESS_FIREWALL_FIELDS = (
    "actual_MESS_optimizer_calls",
    "actual_MESS_reroute_calls",
    "actual_route_change_count",
)

FAILURE_CLASSES = (
    "ENGINEERING_SERIALIZATION_DEFECT",
    "ENGINEERING_RUNTIME_DEFECT",
    "ENGINEERING_CACHE_OR_RESUME_DEFECT",
    "ENGINEERING_SOLVER_INTEGRATION_DEFECT",
    "CASE_BINDING_DEFECT",
    "AIDC_COUPLING_DEFECT",
    "MESS_COUPLING_DEFECT",
    "FRESH_INTERFACE_DEFECT",
    "CAUSALITY_FIREWALL_DEFECT",
    "STORAGE_INTEGRITY_DEFECT",
    "SCIENTIFIC_AUTHORITY_CHANGE_REQUIRED",
)

CHECKPOINT_FIELDS = (
    "phase", "day", "case", "run_id", "code_HEAD", "science_authority_SHA",
    "forecast_SHA", "route_table_SHA", "AIDC_schedule_SHA", "MESS_trajectory_SHA",
    "combined_schedule_SHA", "Planning_SHA", "Fresh_SHA", "Actual_SHA",
    "solver_settings_SHA", "storage_schema_SHA", "status", "timestamp",
)

STORAGE_CATEGORIES = MappingProxyType({
    "input_authority": (
        "forecast_authority_SHA", "issue_time", "feature_cutoff", "AIDC_model_authority_SHA",
        "traffic_model_SHA", "feeder_SHA", "AIDC_scale_SHA", "C1_SHA", "road_graph_SHA",
        "service_mapping_SHA", "solver_settings_SHA",
    ),
    "dayahead_AIDC": (
        "workload_execution_tensor", "execution_slot", "site_rack_allocation",
        "authorized_workload", "deferred_backlog_workload", "AIDC_P", "AIDC_Q",
    ),
    "dayahead_MESS": (
        "initial_location", "MOVE_STAY", "destination", "departure_slot", "route",
        "forecast_ETA", "Safe_ETA", "connection_ready_slot", "travel_energy", "P", "Q",
        "SoC", "terminal_energy", "solver_evidence",
    ),
    "planning_grid": ("voltage", "line_current", "transformer_current", "transformer_kVA", "rho", "binding"),
    "fresh": ("voltage", "line_current", "transformer_current", "transformer_kVA", "rho_AC", "losses", "convergence", "schedule_SHA"),
    "actual_AIDC": ("arrivals", "executed", "same_site_recourse", "cross_site_recourse", "blocked", "backlog", "resource_only_recourse", "firewall"),
    "actual_MESS": ("DA_commitment", "realized_ETA", "realized_arrival", "realized_travel_energy", "realized_connection_ready", "PQ_availability", "terminal_SoC", "route_identity", "firewall"),
    "effects": ("B1_B0", "B2_B0", "B3_B1", "B3_B2"),
})


def assert_official_cases(cases: Sequence[str]) -> None:
    if tuple(cases) != OFFICIAL_CASES:
        raise ValueError("V35_OFFICIAL_CASES_MUST_BE_EXACTLY_B0_B1_B2_B3")


def phase_for_day(day: str, *, corrected: bool = False) -> str:
    if day in CALIBRATION_DAYS:
        if corrected:
            raise ValueError("V35_CORRECTION_NOT_ALLOWED_DURING_CALIBRATION")
        return PHASE_CALIBRATION
    if day in VALIDATION_DAYS:
        return PHASE_CORRECTED if corrected else PHASE_PROSPECTIVE
    if day in MAY_DAYS:
        if not corrected:
            raise ValueError("V35_MAY_REQUIRES_FROZEN_CORRECTION")
        return PHASE_MAY
    raise ValueError("V35_DAY_OUTSIDE_APRIL_MAY")


def assert_may_access(day: str, admission: Mapping[str, object] | None) -> None:
    if day not in MAY_DAYS:
        return
    if not admission or admission.get("status") != "PASS" or admission.get("May_numeric_reads_before_admission") != 0:
        raise PermissionError("V35_MAY_REQUIRES_COMPLETE_ADMISSION_GATE")


def zero_firewall(fields: Sequence[str]) -> dict[str, int]:
    return {field: 0 for field in fields}
