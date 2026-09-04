"""Frozen V39A bindings layered on the exact V38 failure-evidence HEAD."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path


IMPLEMENTATION_ID = "V39A_CAUSAL_AIDC_SITE_PLACEMENT_POWER_V1"
V38_FAIL_EVIDENCE_HEAD = "cf7762d82f485d9f7f463bb6e5119f2e5d197a13"
V38_IMPLEMENTATION_FINGERPRINT = (
    "ea004826ff0d8e0025e51818e5e95083778f03404c192720f6a1954163f8e786"
)
BRANCH = "codex/v39a-causal-aidc-site-placement-power"

ARTIFACT_ROOT = Path("dayahead/artifacts/v39a_causal_aidc_site_placement_power")
V37_DAY_ROOT = Path("dayahead/artifacts/v37_r4a_per_day_aidc/days")
V38_ARTIFACT_ROOT = Path("dayahead/artifacts/v38_aidc_spatiotemporal_wan")

EXPECTED_DATES = tuple(
    (date(2025, 5, 1) + timedelta(days=offset)).isoformat()
    for offset in range(31)
)
TEMPORAL_MODES = ("RW", "RSP")
SLOTS = 96
TARGET_OFFSET_SLOTS = 24
GPU_CAPACITY = 624

SITE_CAPACITY = {
    "AIDC01": 42,
    "AIDC02": 75,
    "AIDC03": 77,
    "AIDC04": 34,
    "AIDC05": 53,
    "AIDC06": 68,
    "AIDC07": 21,
    "AIDC08": 62,
    "AIDC09": 139,
    "AIDC10": 17,
    "AIDC11": 12,
    "AIDC12": 24,
}

FULL_ACTIVE_IT_KW = Decimal("406.775993813819")
C_REF_W_PER_GPU = Decimal("651.884605470864")
CENTER_SWING_W_PER_GPU = Decimal("547.7239090195797")
IDLE_W_PER_GPU = C_REF_W_PER_GPU - CENTER_SWING_W_PER_GPU
POWER_TOLERANCE_KW = Decimal("0.000000000002")

VOLTAGE_AUTHORITY = Path(
    "dayahead/artifacts/v37_r3_restore_intended_cuts/"
    "V37_R3_JOINT_VOLTAGE_AUTHORITY.json"
)
VOLTAGE_FROZEN_SHA256 = (
    "3ee89daad6d63cffb70c1a890f5141cf33bf4c951c9a9c364ae36692bcda6151"
)
VOLTAGE_LOGICAL_LF_SHA256 = (
    "ffa1db91e4a7abca6312c3b4763d0bd9030eb115743fb3b17bd2b96381e37c24"
)

RUNTIME_FIREWALL = {
    "runtime_AIDC_reschedule_calls": 0,
    "runtime_AIDC_replacement_calls": 0,
    "runtime_running_migration_reoptimization_calls": 0,
    "runtime_WAN_path_reoptimization_calls": 0,
    "runtime_WAN_schedule_reoptimization_calls": 0,
    "runtime_Rack_reoptimization_calls": 0,
}
