"""Fail-closed guards for the V33XR3R1 authority materializer.

No production optimizer or OpenDSS module is imported here.  The pre-flight
found that the frozen canonical P/G/W predictor is April-only, so the run must
stop before constructing an electrical model, solving B1, or opening Fresh.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Mapping

from .contracts import END_DAY, START_DAY


def validate_day(value: object) -> date:
    parsed = date.fromisoformat(str(value))
    if not START_DAY <= parsed <= END_DAY:
        raise ValueError("V33XR3R1_DAY_OUTSIDE_JANMAR")
    return parsed


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass
class MaterializationFirewall:
    schedule_sha256: str | None = None
    actual_reads: int = 0
    fresh_reads: int = 0

    def freeze_schedule(self, schedule_sha256: str) -> None:
        if len(schedule_sha256) != 64 or any(c not in "0123456789abcdef" for c in schedule_sha256):
            raise ValueError("V33XR3R1_SCHEDULE_SHA_REQUIRED")
        self.schedule_sha256 = schedule_sha256

    def open_actual(self, schedule_sha256: str) -> None:
        if self.schedule_sha256 is None or schedule_sha256 != self.schedule_sha256:
            raise RuntimeError("V33XR3R1_ACTUAL_INACCESSIBLE_BEFORE_FREEZE")
        self.actual_reads += 1

    def open_fresh(self, schedule_sha256: str) -> None:
        if self.schedule_sha256 is None or schedule_sha256 != self.schedule_sha256:
            raise RuntimeError("V33XR3R1_FRESH_INACCESSIBLE_BEFORE_FREEZE")
        self.fresh_reads += 1


def validate_pass_marker(marker: Mapping[str, object], root: Path) -> bool:
    """Skip a day only when every immutable referenced object still hashes."""
    required = {
        "day", "code_head", "schedule_sha256", "planning_voltage_artifact_sha256",
        "fresh_voltage_artifact_sha256", "source_sha_bundle", "status", "files",
    }
    if set(marker) < required or marker.get("status") != "PASS":
        return False
    try:
        validate_day(marker["day"])
    except (TypeError, ValueError):
        return False
    files = marker.get("files")
    if not isinstance(files, Mapping):
        return False
    for relative, expected in files.items():
        path = root / str(relative)
        if not path.is_file() or sha256_file(path) != expected:
            return False
    return True
