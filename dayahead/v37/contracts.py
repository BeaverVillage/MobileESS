"""Immutable V37 engineering and frozen-science bindings."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path


PARENT_HEAD = "d33ecfaa85005f2862c800cf514309e0f4ce95d4"
BRANCH = "codex/v37-may2025-locked-final"
WORKTREE = Path(r"C:\codex_mobileess_workspace\MobileESS_v37_may_final")

OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
EXPECTED_DATES = tuple(
    (date(2025, 5, 1) + timedelta(days=offset)).isoformat()
    for offset in range(31)
)
MAX_PARALLEL_DATES = 4
MAX_WORKERS_PER_DATE = 4
DAY_TOTAL_UNITS = 14
MONITOR_REFRESH_SECONDS = 10

AIDC_HEAD = "aa1a113abdd6eb1bc76cf3bfdcb6dcdb29660b2e"
MESS_HEAD = "a5c46a5c8b06e97e9e13a2078cb801fe51b240a9"
AIDC_PRIMARY_SCENARIO = "CENTER"
CENTER_SWING_W_PER_GPU = 547.7239090195797
APR01_EXPANDED_TEMPORAL_JOBS = 339
APR01_EXPANDED_TEMPORAL_GPU_HOURS = 14_832
APR01_PARTIAL_SHARED_TEMPORAL_JOBS = 336
APR01_PARTIAL_SHARED_TEMPORAL_GPU_HOURS = 14_256

DEFAULT_K = 200
K_FALLBACK = (200, 400, 800, "FULL")
BEAM_WIDTH = 2
BEAM_WIDTH_FALLBACK = 4
SEED_WIDTH = 2
MESS_ORDER = ("MESS01", "MESS02", "MESS03", "MESS04")

ARTIFACT_ROOT = Path("dayahead/artifacts/v37_may_r4a_per_day_final")
STATUS_ROOT = ARTIFACT_ROOT / "status"
DATE_RESULT_ROOT = ARTIFACT_ROOT / "dates"
LOG_ROOT = Path("logs/v37_may_r4a_per_day_final")
CACHE_ROOT = Path("dayahead/cache/v37_may_locked_final")
RAW_ROOT = Path("frozen_artifacts/v36_final_schema")
PASS_ID = "MAY_2025_R4A_PER_DAY_FINAL"
PHASE = "LOCKED_FINAL_EVALUATION"

SOURCE_DATA_REPOSITORY = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend"
)
WSL_DISTRIBUTION = "Ubuntu-MobileESS-D"
WSL_PYTHON = "/home/jaewon/.cache/mobileess-v28r2/venv/bin/python"

DATE_MANIFEST = ARTIFACT_ROOT / "V37_MAY_DATE_MANIFEST.json"
PRODUCTION_PREFLIGHT = Path(
    "dayahead/artifacts/v37_r4_may_campaign_repair/"
    "V37_R4_MAY_31DAY_PRODUCTION_PREFLIGHT.json"
)
CAMPAIGN_LOCK = ARTIFACT_ROOT / "V37_CAMPAIGN.lock.json"
MONITOR_LOCK = ARTIFACT_ROOT / "V37_MONITOR.lock.json"

PROGRESS_AFTER_CASE = {"B0": 2, "B1": 4, "B2": 9, "B3": 14}
BEAM_PROGRESS_BASE = {"B2": 4, "B3": 9}

FIREWALL = {
    "May_result_used_to_tune_CENTER": "NO",
    "May_result_used_to_tune_MESS": "NO",
    "IDC_location_changed": "NO",
    "Fresh_used_for_AIDC_or_MESS_initial_decisions": "NO",
    "Fresh_used_for_post_selection_AC_feasibility_detection": "YES",
    "Fresh_used_by_frozen_fixed_discrete_PQ_restoration": "YES",
    "Fresh_changes_MESS_destination_route_departure_or_move": "NO",
    "LOW_HIGH_official_runs": 0,
    "Apr01_rerun": "NO",
}
