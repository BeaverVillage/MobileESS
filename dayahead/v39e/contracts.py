"""Immutable boundaries for the V39E fast validation."""

from __future__ import annotations

from pathlib import Path

from dayahead.v39d.contracts import (
    CAPACITY_CANONICAL_SHA256,
    CAPACITY_FILE_SHA256,
    EXPECTED_DATES,
    EXPECTED_GPU_CAPACITY,
    RACK_AUTHORITY_PATH,
    RACK_FREEZE_CERTIFICATE_PATH,
    SLOTS,
    V37_DAY_ROOT,
)


IMPLEMENTATION_ID = "V39E_RW_ANCHORED_COMMON_INITIAL_STATE_FAST_VALIDATION_V1"
START_HEAD = "692cfc2ce0949c8ac2f76ba6e37ca94fac9358fc"
BRANCH = "codex/v39e-rw-anchored-initial-state-fast-validation"
ARTIFACT_ROOT = Path("dayahead/artifacts/v39e_rw_anchored_initial_state_fast_validation")
SOLVER_SEED = 20260905
MAX_PARALLEL_DAY_WORKERS = 4
GUROBI_THREADS_PER_MODEL = 4
# Backward-compatible internal name; runtime authority is the explicit constant above.
SOLVER_THREADS = GUROBI_THREADS_PER_MODEL

RACK_AUTHORITY_SHA256 = (
    "f302163fdc48a95aa27bb5b71893ad04b4fcb70b9682399d2d87e881b1f3d3ec"
)
RACK_FREEZE_COMMIT = "9ff503ae643a7bed756b03d1a005f3f398438145"

__all__ = [
    "ARTIFACT_ROOT",
    "BRANCH",
    "CAPACITY_CANONICAL_SHA256",
    "CAPACITY_FILE_SHA256",
    "EXPECTED_DATES",
    "EXPECTED_GPU_CAPACITY",
    "IMPLEMENTATION_ID",
    "RACK_AUTHORITY_PATH",
    "RACK_AUTHORITY_SHA256",
    "RACK_FREEZE_CERTIFICATE_PATH",
    "RACK_FREEZE_COMMIT",
    "SLOTS",
    "GUROBI_THREADS_PER_MODEL",
    "MAX_PARALLEL_DAY_WORKERS",
    "SOLVER_SEED",
    "SOLVER_THREADS",
    "START_HEAD",
    "V37_DAY_ROOT",
]
