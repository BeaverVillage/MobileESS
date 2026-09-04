"""Frozen lineage, interval, and source contracts for V35R3D-R1."""

from __future__ import annotations

from pathlib import Path

from dayahead.v35r3d.contracts import (
    GPU_CAPACITY,
    HPCODA_HEAD,
    ISSUE_TIME,
    KESTREL_ARCHIVE_SHA256,
    SLOT_SECONDS,
    TARGET_END,
    TARGET_END_SLOT,
    TARGET_OFFSET_SLOTS,
    TARGET_START,
    W1,
    W3,
    W5,
)


PARENT_HEAD = "98fb2923b24e145346d2f4bc3bb9be6aab395bba"
BRANCH = "codex/v35r3d-r1-running-residual-accounting-correction"
WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3d_r1_running_residual_accounting"
)
PARENT_WORKTREE = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v35r3d_kestrel_runtime_authority_closure"
)
PARENT_ARTIFACTS = (
    PARENT_WORKTREE / "dayahead" / "artifacts" / "v35r3d_kestrel_runtime_authority_closure"
)
PARENT_CACHE = (
    PARENT_WORKTREE / "dayahead" / "cache" / "v35r3d_kestrel_runtime_authority_closure"
)
ARTIFACT_DIRNAME = "v35r3d_r1_running_residual_accounting"
CALIBRATION_START = "2025-03-24T00:00:00+10:00"
CALIBRATION_END = "2025-03-31T00:00:00+10:00"
QUANTILE_LEVEL = 0.90
RUNTIME_AUTHORITY = "R2_DIAGNOSTIC_CAUSAL_RUNTIME"
RUNNING_RESIDUAL_AUTHORITY = "REQUESTED_WALLTIME_CONSERVATIVE"
