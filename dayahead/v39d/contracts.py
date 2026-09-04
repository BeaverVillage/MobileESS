"""Immutable V39D orchestration boundaries.

V39D changes orchestration only.  Every numerical authority named here is a
read-only input inherited from V37--V39C.
"""

from __future__ import annotations

from pathlib import Path

from dayahead.v39c.contracts import EXPECTED_DATES, EXPECTED_GPU_CAPACITY, SLOTS


IMPLEMENTATION_ID = "V39D_INDEPENDENT_DAILY_TEMPORAL_FIRST_AIDC_MIGRATION_V1"
BRANCH = "codex/v39d-independent-daily-temporal-first-migration"
START_HEAD = "9c64cd0b1721c606347c1c0c712faee6e071e8b8"
CAPACITY_FREEZE_COMMIT = "7741844618c7661301be6ecc84b98f003ffb844b"
CAPACITY_FILE_SHA256 = (
    "bef9175ce8bcbbfcbdde6d66d41f7f10da18998859dec5000ec9fbed44fe0c9e"
)
CAPACITY_CANONICAL_SHA256 = (
    "6af48aa50f4cfbaa42f40eedb966fdc99c77656ec5a415c2d84089baccfb99ce"
)
V39C_CHAIN_MIGRATIONS = 211
SOLVER_SEED = 20260905
SOLVER_THREADS = 1

ARTIFACT_ROOT = Path(
    "dayahead/artifacts/v39d_independent_daily_temporal_first_migration"
)
RACK_AUTHORITY_PATH = ARTIFACT_ROOT / "V39D_SYNTHETIC_LOGICAL_RACK_COMPATIBILITY_AUTHORITY.json"
RACK_FREEZE_CERTIFICATE_PATH = ARTIFACT_ROOT / "V39D_RACK_FREEZE_CERTIFICATE.json"
RACK_CONSISTENCY_AUDIT_PATH = ARTIFACT_ROOT / "V39D_RACK_SITE_CONSISTENCY_AUDIT.json"
CACHE_ROOT = Path("dayahead/cache/v39d_independent_daily_temporal_first_migration")
V37_DAY_ROOT = Path("dayahead/artifacts/v37_r4a_per_day_aidc/days")
V39C_ARTIFACT_ROOT = Path("dayahead/artifacts/v39c_aidc_gpu_capacity_refreeze")
V39C_PREMAY_GANG_AUDIT_PATH = (
    V39C_ARTIFACT_ROOT / "V39C_PREMAY_JOB_GANG_SIZE_AUDIT.json"
)

CASES = ("B0", "B1", "B2", "B3")
CASE_MODE = {"B0": "RW", "B1": "RSP", "B2": "RW", "B3": "RSP"}
RW_CASES = ("B0", "B2")
RSP_CASES = ("B1", "B3")

REQUIRED_ARTIFACTS = (
    "V39D_FINAL_REVIEW.md",
    "V39D_INDEPENDENT_DAILY_CONTRACT.json",
    "V39D_COMMON_DAILY_INITIAL_AIDC_STATE.parquet",
    "V39D_DAILY_INITIAL_STATE_FAIRNESS_AUDIT.json",
    "V39D_TEMPORAL_FIRST_POLICY_CONTRACT.json",
    "V39D_TEMPORAL_FIRST_ESCALATION_AUDIT.parquet",
    "V39D_MIGRATION_MINIMUM_WITNESS_AUDIT.json",
    "V39D_SITE_GPU_TRAJECTORIES.parquet",
    "V39D_SITE_IT_POWER_TRAJECTORIES.parquet",
    "V39D_SITE_PCC_POWER_TRAJECTORIES.parquet",
    "V39D_POWER_CONSERVATION_AUDIT.json",
    "V39D_ACTUAL_RACK_ASSIGNMENT_CONTRACT.json",
    "V39D_ACTUAL_NO_REOPTIMIZATION_AUDIT.json",
    "V39D_B0_B3_IDENTITY_AUDIT.json",
    "V39D_MAY_31DAY_INPUT_PREFLIGHT.json",
    "V39D_TEST_REPORT.json",
    "V39D_IMPLEMENTATION_FINGERPRINT.json",
)

assert len(EXPECTED_DATES) == 31
assert len(EXPECTED_GPU_CAPACITY) == 12
assert sum(EXPECTED_GPU_CAPACITY.values()) == 624
assert SLOTS == 96
