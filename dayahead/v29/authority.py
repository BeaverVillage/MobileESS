"""Frozen V29 scientific authority gates."""

from __future__ import annotations

import json
from pathlib import Path


RHO_AIDC = 0.10
SLOTS = 96
RESOLUTION_MINUTES = 15
CASES = ("B0", "B1", "B2", "B3")


def require_carryin_authority(repo: Path) -> dict[str, object]:
    path = repo / "dayahead/artifacts/v29_grid_responsive_aidc/V29_CARRYIN_AUTHORITY_DECISION.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not payload.get("CARRYIN_AUTHORITY_READY"):
        raise RuntimeError("V29_BLOCKED_CARRYIN_SOURCE_AUTHORITY_INSUFFICIENT")
    if payload.get("APRIL_FIT_ROWS") != 0 or payload.get("POST_CUTOFF_ACTUAL_FEATURE_COUNT") != 0:
        raise RuntimeError("V29_CARRYIN_CAUSALITY_GATE")
    return payload
