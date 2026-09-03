"""Atomic date status and monitor-view helpers."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import time
from typing import Any, Iterable

from .contracts import DAY_TOTAL_UNITS, EXPECTED_DATES


TERMINAL = {"PASS", "FAIL"}


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(
        path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
    )
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    for attempt in range(20):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.05)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_status(
    path: Path,
    day: str,
    status: str,
    completed_units: int,
    current_stage: str | None,
    *,
    error: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if status not in {"PENDING", "RUNNING", "PASS", "FAIL"}:
        raise ValueError("V37_STATUS_VALUE")
    units = int(completed_units)
    if not 0 <= units <= DAY_TOTAL_UNITS:
        raise ValueError("V37_STATUS_UNITS")
    payload: dict[str, Any] = {
        "date": day,
        "status": status,
        "completed_units": units,
        "total_units": DAY_TOTAL_UNITS,
        "current_stage": current_stage,
        "pass": status == "PASS",
        "fail": status == "FAIL",
        "last_update": datetime.now(timezone.utc).isoformat(),
        "error": error,
    }
    if extra:
        payload.update(extra)
    atomic_json(path, payload)
    return payload


def load_statuses(status_root: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(status_root.glob("2025-05-*.json")):
        try:
            value = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if value.get("date") in EXPECTED_DATES:
            rows.append(value)
    return rows


def monitor_view(rows: Iterable[dict[str, Any]], expected_count: int = 31) -> dict[str, Any]:
    values = list(rows)
    passed = sum(row.get("status") == "PASS" for row in values)
    failed = sum(row.get("status") == "FAIL" for row in values)
    active = sorted(
        (row for row in values if row.get("status") == "RUNNING"),
        key=lambda row: str(row.get("date")),
    )
    return {
        "PASS": passed,
        "FAIL": failed,
        "ACTIVE": len(active),
        "REMAIN": max(0, int(expected_count) - passed - failed),
        "active_dates": active,
        "complete": passed + failed >= int(expected_count) and not active,
    }
