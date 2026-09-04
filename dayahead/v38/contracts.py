"""Frozen V38 bindings layered on the V37 May parent."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path


IMPLEMENTATION_ID = "V38_AIDC_SPATIOTEMPORAL_WAN_MIGRATION_V1"
PARENT_HEAD = "56f0c08c1239ad6dca25c4fb0ffec590a1c97a68"
BRANCH = "codex/v38-aidc-spatiotemporal-wan-migration"
OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
EXPECTED_DATES = tuple(
    (date(2025, 5, 1) + timedelta(days=offset)).isoformat()
    for offset in range(31)
)
SLOTS = 96
SIMULATION_SLOTS = 120
SLOT_SECONDS = 900
GPU_CAPACITY = 624
CENTER_SWING_W_PER_GPU = 547.7239090195797
CHECKPOINT_INTERVAL_SECONDS = 1800
RESTART_SECONDS = 300
MAX_PARALLEL_DATES = 4
MAX_WORKERS_PER_DATE = 4
MONITOR_REFRESH_SECONDS = 10

ARTIFACT_ROOT = Path("dayahead/artifacts/v38_aidc_spatiotemporal_wan")
DAY_ROOT = ARTIFACT_ROOT / "days"
STATUS_ROOT = ARTIFACT_ROOT / "status"
DATE_RESULT_ROOT = ARTIFACT_ROOT / "results"
LOG_ROOT = Path("logs/v38_aidc_spatiotemporal_wan")
CACHE_ROOT = Path("dayahead/cache/v38_aidc_spatiotemporal_wan")
RAW_ROOT = Path("frozen_artifacts/v38_final_schema")
PASS_ID = "MAY_2025_V38_AIDC_SPATIOTEMPORAL_WAN_FINAL"
PHASE = "V38_LOCKED_FINAL_EVALUATION"

V37_DAY_ROOT = Path("dayahead/artifacts/v37_r4a_per_day_aidc/days")
V37_INPUT_PREFLIGHT = Path(
    "dayahead/artifacts/v37_r4_may_campaign_repair/"
    "V37_R4_MAY_31DAY_PRODUCTION_PREFLIGHT.json"
)
V37_TRUE_LOADER_PREFLIGHT = Path(
    "dayahead/artifacts/v37_r4_may_campaign_repair/"
    "V37_R4A_TRUE_31DAY_PRODUCTION_LOADER_PREFLIGHT.json"
)
RACK_CONTRACT = Path("dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json")
RACK_PROVENANCE = Path(
    "dayahead/artifacts/v16/RACK_POWER_CAPACITY_PROVENANCE_AUDIT_V1.json"
)
WAN_CONTRACT = Path("pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json")
C1_CONTRACT = Path(
    "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json"
)
SITE_SENSITIVITY = Path(
    "dayahead/artifacts/v35r3_aidc_mess_algorithm/"
    "V35R3_AIDC_SITE_SW2_SENSITIVITY.csv"
)
HOME_MAPPING = ARTIFACT_ROOT / "V38_HOME_IDC_MAPPING.parquet"
HOME_MAPPING_AUDIT = ARTIFACT_ROOT / "V38_HOME_IDC_MAPPING_AUDIT.json"
IMPLEMENTATION_FINGERPRINT = ARTIFACT_ROOT / "V38_IMPLEMENTATION_FINGERPRINT.json"
INPUT_PREFLIGHT = ARTIFACT_ROOT / "V38_MAY_31DAY_INPUT_PREFLIGHT.json"
TRUE_LOADER_PREFLIGHT = (
    ARTIFACT_ROOT / "V38_TRUE_31DAY_PRODUCTION_LOADER_PREFLIGHT.json"
)
SCIENCE_FREEZE = ARTIFACT_ROOT / "V38_FINAL_SCIENCE_FREEZE.json"
CAMPAIGN_LOCK = ARTIFACT_ROOT / "V38_CAMPAIGN.lock.json"
MONITOR_LOCK = ARTIFACT_ROOT / "V38_MONITOR.lock.json"
LAUNCH_STATE = ARTIFACT_ROOT / "V38_MAY_CAMPAIGN_LAUNCH.json"
PROCESS_MANIFEST = ARTIFACT_ROOT / "V38_MAY_CAMPAIGN_PROCESS_MANIFEST.json"
MONITOR_START = ARTIFACT_ROOT / "V38_MAY_MONITOR_START.json"

RAW_WAN_ROOT = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\raw데이터\WAN"
)
RAW_WAN_TOPOLOGY = RAW_WAN_ROOT / "abilene_network_native.txt.txt"
RAW_WAN_README = RAW_WAN_ROOT / "abilene_readme.txt.txt"
RAW_WAN_TRAFFIC = (
    RAW_WAN_ROOT / "directed-abilene-zhang-5min-over-6months-ALL-native.tgz"
)
RAW_RACK_CAPACITY = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\processed데이터"
    r"\데이터센터\NLR Kestrel Jobs Data\stage_k5c3_20260723_062008"
    r"\outputs\optimization_main_rack_parameters.csv"
)

EXPECTED_WAN_TOPOLOGY_SHA256 = (
    "e620c92985e6d8b8c09c8e32588d806c8c1c03e3e944a07119672d1804fda512"
)
EXPECTED_WAN_README_SHA256 = (
    "3a3ea1d4d28eab79a53aebfd7f6dc8a00b7731385ea62504871fdf7fc73625e5"
)
EXPECTED_WAN_TRAFFIC_SHA256 = (
    "2f311130d77e40db88da1aa6db8055b6fce8d077bf4bae87398563e1b84e70ce"
)
EXPECTED_RACK_SHA256 = (
    "4546c0672a4d25aa5c7c92ea90fb90ec8d3c009dda426939179b293abdeb83c0"
)

RUNTIME_FIREWALL = {
    "runtime_AIDC_reschedule_calls": 0,
    "runtime_AIDC_replacement_calls": 0,
    "runtime_running_migration_reoptimization_calls": 0,
    "runtime_WAN_path_reoptimization_calls": 0,
    "runtime_WAN_schedule_reoptimization_calls": 0,
    "runtime_Rack_reoptimization_calls": 0,
}

# This alias documents the earlier supplemental schema without exposing the
# legacy term as a current V38 counter.
LEGACY_COUNTER_ALIASES = {
    "runtime_IDC_replacement_calls": "runtime_AIDC_replacement_calls",
}
