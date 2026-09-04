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
DETAIL_FIELDS = (
    "mess_index",
    "beam_parent_index",
    "beam_parent_total",
    "search_level",
    "candidate_done",
    "candidate_total",
    "candidate_new_done",
    "candidate_new_total",
    "seed_done",
    "seed_total",
    "full_milp_status",
    "restoration_round",
    "restoration_round_max",
    "restoration_new_cuts",
    "restoration_total_cuts",
    "fresh_slots_done",
    "fresh_slots_total",
)
DETAIL_ACTIVITY_FIELDS = (
    "candidate_total",
    "seed_total",
    "full_milp_status",
    "restoration_round",
    "fresh_slots_done",
)


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(
        path.suffix + f".{os.getpid()}.{threading.get_ident()}.tmp"
    )
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    for attempt in range(300):
        try:
            os.replace(temporary, path)
            return
        except PermissionError:
            if attempt == 299:
                raise
            time.sleep(0.1)


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
        "major_units_done": units,
        "major_units_total": DAY_TOTAL_UNITS,
        "case": (
            str(current_stage).split("_", 1)[0]
            if current_stage and str(current_stage).startswith(("B0_", "B1_", "B2_", "B3_"))
            else None
        ),
        "stage": current_stage,
        "mess_index": None,
        "beam_parent_index": None,
        "beam_parent_total": None,
        "search_level": None,
        "candidate_done": None,
        "candidate_total": None,
        "candidate_new_done": None,
        "candidate_new_total": None,
        "seed_done": None,
        "seed_total": None,
        "full_milp_status": None,
        "restoration_round": None,
        "restoration_round_max": 5,
        "restoration_new_cuts": None,
        "restoration_total_cuts": None,
        "fresh_slots_done": None,
        "fresh_slots_total": 96,
        "pass": status == "PASS",
        "fail": status == "FAIL",
        "last_update": datetime.now(timezone.utc).isoformat(),
        "error": error,
        "error_summary": error,
    }
    if extra:
        payload.update(extra)
    # The two-second beam watcher reports the same major stage without the
    # candidate detail emitted by the solver callback.  Preserve the most
    # recent detail until the stage itself changes; otherwise a 10-second
    # monitor refresh can make route-search progress flash and disappear.
    incoming_has_detail = bool(
        extra and any(field in extra for field in DETAIL_ACTIVITY_FIELDS)
    )
    if status == "RUNNING" and not incoming_has_detail and path.is_file():
        try:
            prior = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            prior = {}
        if (
            prior.get("status") == "RUNNING"
            and prior.get("stage") == current_stage
            and any(prior.get(field) is not None for field in DETAIL_ACTIVITY_FIELDS)
        ):
            for field in DETAIL_FIELDS:
                payload[field] = prior.get(field)
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
