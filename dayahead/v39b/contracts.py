"""Frozen inputs and fail-closed boundaries for the V39B diagnostic."""

from __future__ import annotations

from pathlib import Path

from dayahead.v39a.contracts import EXPECTED_DATES, SITE_CAPACITY


IMPLEMENTATION_ID = "V39B_PREIMPLEMENTATION_SCIENTIFIC_DIAGNOSTIC_V1"
DIAGNOSTIC_LABEL = "NON_PRODUCTION_DIAGNOSTIC_ONLY"
SOURCE_HEAD = "b78fa725e8f98ef43091dd67a8a642275de7f963"
SOURCE_FINGERPRINT = (
    "43a4c15aa88bc84cc0433ca20a81410b0885a3a90f70b64bd480e6e483bc3f76"
)
BRANCH = "codex/v39b-preaudit-spatiotemporal-feasibility"
CAPACITY_AUTHORITY_SHA256 = (
    "4546c0672a4d25aa5c7c92ea90fb90ec8d3c009dda426939179b293abdeb83c0"
)

ARTIFACT_ROOT = Path("dayahead/artifacts/v39b_preimplementation_diagnostic")
V39A_ARTIFACT_ROOT = Path("dayahead/artifacts/v39a_causal_aidc_site_placement_power")
V37_DAY_ROOT = Path("dayahead/artifacts/v37_r4a_per_day_aidc/days")
V37_SCHEDULER_SOURCE = Path("dayahead/v37/aidc_materializer.py")

TEMPORAL_MODES = ("RW", "RSP")
SLOTS = 96
STORED_SLOTS = 120
TARGET_OFFSET_SLOTS = 24
SLOT_SECONDS = 900
SOLVER_SEED = 20260904
SOLVER_THREADS = 1

SHIFTABLE_CLASSES = frozenset(
    {"NORMAL_QUEUE_CONTROLLED", "STANDBY_QUEUE_CONTROLLED"}
)
NONSHIFTABLE_CLASSES = frozenset(
    {"RUNNING_FIXED", "HIGH_PROTECTED", "FIXED_PROTECTED"}
)

INFEASIBLE_DAY_MODES = (
    ("2025-05-21", "RW"), ("2025-05-21", "RSP"),
    ("2025-05-22", "RW"), ("2025-05-22", "RSP"),
    ("2025-05-23", "RW"), ("2025-05-23", "RSP"),
    ("2025-05-24", "RW"), ("2025-05-24", "RSP"),
    ("2025-05-25", "RSP"), ("2025-05-26", "RSP"),
    ("2025-05-27", "RW"), ("2025-05-27", "RSP"),
    ("2025-05-28", "RW"), ("2025-05-28", "RSP"),
)

assert len(EXPECTED_DATES) == 31
assert sum(SITE_CAPACITY.values()) == 624
