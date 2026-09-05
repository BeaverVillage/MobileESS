"""Runtime admission gate only. No solver, DA mutation, or campaign restart."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

# May23 added after the user-requested terminal-site audit failed; admission only.
HELD_DAYS = frozenset(("2025-05-23", "2025-05-24", "2025-05-25", "2025-05-26"))
GATE = Path("dayahead/artifacts/v39h_terminal_state_audit/TERMINAL_AUDIT_LAUNCH_GATE.json")


def admission(repo: Path, day: str) -> dict:
    if day not in HELD_DAYS:
        return {"day": day, "release": True, "status": "UNAFFECTED_DATE"}
    try:
        gate = json.loads((repo / GATE).read_text(encoding="utf-8"))
        row = gate["dates"][day]
        released = gate.get("audit_complete") is True and row.get("release") is True
        return {"day": day, "release": released,
                "status": "TERMINAL_AUDIT_RELEASED" if released else row.get("status", "HOLD_PENDING_TERMINAL_AUDIT")}
    except (OSError, ValueError, KeyError, TypeError):
        return {"day": day, "release": False, "status": "HOLD_TERMINAL_AUDIT_AUTHORITY_UNAVAILABLE"}


def wait_for_admission(repo: Path, day: str) -> None:
    state = admission(repo, day)
    if state["release"]:
        return
    # The already-running parent has a fixed four-process queue and no reload
    # hook. Waiting here prevents Actual/solver entry without fabricating a
    # FAIL result or restarting that parent. Other queue slots remain usable.
    from dayahead.v39c.freeze import atomic_json
    printed = None
    while not state["release"]:
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "date": day, "status": "PENDING", "stage": state["status"],
            "current_stage": state["status"], "case": None,
            "completed_units": 0, "total_units": 14, "pass": False,
            "fail": False, "error": None, "last_update": now,
            "Actual_launch_blocked": True, "solver_calls": 0,
            "admission_wait_PID": os.getpid(), "gate_path": str(GATE),
        }
        atomic_json(repo / "dayahead/artifacts/v39e_full_may_2025/status" / f"{day}.json", payload)
        atomic_json(repo / GATE.parent / "launch_waits" / f"{day}.json", payload)
        if state["status"] != printed:
            print(f"V39H_TERMINAL_ADMISSION {day} {state['status']} Actual=NOT_STARTED solver_calls=0", flush=True)
            printed = state["status"]
        time.sleep(10)
        state = admission(repo, day)
    print(f"V39H_TERMINAL_ADMISSION {day} RELEASED", flush=True)
