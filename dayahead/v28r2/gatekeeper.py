"""Fail-closed execution gates separating development from heavy execution."""

from __future__ import annotations

import json
from pathlib import Path


SMOKE_GATE_FILE = "V28R2_HEAVY_SMOKE_LAUNCH_GATES.json"
AUTHORITY_GATE_FILE = "V28R2_IMPLEMENTATION_READY_FLAGS.json"


def _require(path: Path, keys: tuple[str, ...], error: str) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"{error}:MISSING:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    failed = [key for key in keys if payload.get(key) is not True]
    if failed:
        raise RuntimeError(f"{error}:" + ",".join(failed))
    return payload


def verify_smoke_launch(repo: Path) -> dict[str, object]:
    return _require(
        repo / "dayahead/artifacts/v28r2_heavy_backend" / SMOKE_GATE_FILE,
        ("HEAVY_SMOKE_LAUNCH_AUTHORIZED",),
        "V28R2_HEAVY_SMOKE_LAUNCH_GATES_NOT_READY",
    )


def verify_authority_launch(repo: Path) -> dict[str, object]:
    return _require(
        repo / "dayahead/artifacts/v28r2_heavy_backend" / AUTHORITY_GATE_FILE,
        ("APRIL_RUNNER_READY", "END_TO_END_HEAVY_SMOKE_PASS"),
        "V28R2_AUTHORITY_PRODUCTION_LAUNCH_GATES_NOT_READY",
    )
