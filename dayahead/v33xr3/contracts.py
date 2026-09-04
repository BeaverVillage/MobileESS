"""Frozen constants for the V33XR3 audit-only task."""

from __future__ import annotations

from datetime import date

STARTING_HEAD = "f162da62a7ec1a0e3f870e7ece2eb3231848c818"
SOURCE_BRANCH = "codex/v33x-r2-e1-vmax-10495"
BRANCH = "codex/v33xr3-janmar-planning-fresh-voltage-audit"
CLASSIFICATION = "V33XR3_JANMAR_MATCHED_DAYAHEAD_AUTHORITY_MISSING"

START_DAY = date(2025, 1, 1)
CALIBRATION_END = date(2025, 2, 28)
VALIDATION_START = date(2025, 3, 1)
END_DAY = date(2025, 3, 31)
EXPECTED_DAYS = 90

MATCH_FIELDS = (
    "day",
    "case",
    "slot",
    "schedule_sha256",
    "aidc_p_sha256",
    "aidc_q_sha256",
    "mess_p_sha256",
    "mess_q_sha256",
    "background_demand_sha256",
    "pv_sha256",
    "c1_pue_sha256",
    "native_state_sha256",
    "source_voltage_sha256",
    "feeder_construction_sha256",
    "node",
    "phase",
)

ACTUAL_AIDC_INTERNAL_RESOURCE_RECOURSE_ALLOWED = True
ACTUAL_GRID_FEEDBACK_AIDC_CONTROL_ALLOWED = False
FRESH_USED_AS_ACTUAL_CONTROL_ORACLE = False
