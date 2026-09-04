from __future__ import annotations

import json
from pathlib import Path
import subprocess

from dayahead.v37.status import atomic_json, monitor_view, read_json, write_status
from dayahead.v37.contracts import CAMPAIGN_LOCK, DATE_RESULT_ROOT, PRODUCTION_PREFLIGHT
from dayahead.v37.campaign import (
    _complete_terminal_result,
    acquire_lock,
    release_lock,
)


REPO = Path(__file__).resolve().parents[2]
MONITOR = REPO / "tools/v37/monitor_may.ps1"


def _row(day: str, **values: object) -> dict[str, object]:
    return {
        "date": day,
        "status": "RUNNING",
        "completed_units": 6,
        "total_units": 14,
        "major_units_done": 6,
        "major_units_total": 14,
        "stage": "B2_MESS03",
        "current_stage": "B2_MESS03",
        "beam_parent_index": 1,
        "beam_parent_total": 2,
        "search_level": "K200",
        "candidate_done": 77,
        "candidate_total": 201,
        "candidate_new_done": 77,
        "candidate_new_total": 201,
        "last_update": "2026-09-04T00:00:00+00:00",
        **values,
    }


def _render(root: Path, *, json_output: bool = False) -> str:
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
        "-File", str(MONITOR), "-StatusRoot", str(root),
        "-ExpectedCount", "31", "-RefreshSeconds", "10", "-Once",
    ]
    if json_output:
        command.append("-Json")
    return subprocess.check_output(command, cwd=REPO, text=True, encoding="utf-8")


def test_python_monitor_view_removes_terminal_rows_and_advances_pending() -> None:
    rows = [
        _row("2025-05-01", status="PASS"),
        _row("2025-05-02", status="FAIL", error_summary="B2 RESTORATION_NOT_CONVERGED"),
        _row("2025-05-03"),
        _row("2025-05-04", status="PENDING", stage="QUEUED"),
    ]
    view = monitor_view(rows)
    assert view["PASS"] == 1
    assert view["FAIL"] == 1
    assert [row["date"] for row in view["active_dates"]] == ["2025-05-03"]


def test_same_mess_stage_keeps_detail_until_stage_transition(tmp_path: Path) -> None:
    path = tmp_path / "2025-05-01.json"
    write_status(
        path, "2025-05-01", "RUNNING", 4, "B2_MESS01",
        extra={
            "mess_index": 1,
            "beam_parent_index": 1,
            "beam_parent_total": 1,
            "search_level": "K200",
            "candidate_done": 77,
            "candidate_total": 201,
        },
    )
    write_status(
        path, "2025-05-01", "RUNNING", 4, "B2_MESS01",
        extra={"workers": 4, "beam_width_active": 2},
    )
    retained = read_json(path)
    assert retained["candidate_done"] == 77
    assert retained["candidate_total"] == 201
    assert retained["beam_parent_index"] == 1

    write_status(path, "2025-05-01", "RUNNING", 5, "B2_MESS02")
    advanced = read_json(path)
    assert advanced["candidate_done"] is None
    assert advanced["candidate_total"] is None
    assert advanced["beam_parent_index"] is None


def test_campaign_duplicate_lock_and_verified_stale_recovery(tmp_path: Path) -> None:
    acquired, current = acquire_lock(tmp_path)
    assert acquired is True
    acquired_again, existing = acquire_lock(tmp_path)
    assert acquired_again is False
    assert existing["pid"] == current["pid"]
    release_lock(tmp_path)


def test_terminal_date_reuse_requires_current_implementation_fingerprint(
    tmp_path: Path,
) -> None:
    day = "2025-05-01"
    readiness = tmp_path / PRODUCTION_PREFLIGHT
    result = tmp_path / DATE_RESULT_ROOT / f"{day}.json"
    atomic_json(readiness, {"final_implementation_fingerprint_sha256": "new"})
    terminal = {"status": "PASS"}
    old_payload = {
        "status": "PASS",
        "cases": {case: {} for case in ("B0", "B1", "B2", "B3")},
    }
    atomic_json(result, old_payload)
    assert _complete_terminal_result(tmp_path, day, terminal) is False
    atomic_json(result, {
        **old_payload,
        "final_implementation_fingerprint_sha256": "old",
    })
    assert _complete_terminal_result(tmp_path, day, terminal) is False
    atomic_json(result, {
        **old_payload,
        "final_implementation_fingerprint_sha256": "new",
    })
    assert _complete_terminal_result(tmp_path, day, terminal) is True
    lock = tmp_path / CAMPAIGN_LOCK
    atomic_json(lock, {"pid": 999_999_999, "artifact_id": "STALE_TEST"})
    acquired_after_stale, _new = acquire_lock(tmp_path)
    assert acquired_after_stale is True
    release_lock(tmp_path)


def test_powershell_monitor_renders_candidate_fallback_and_restoration(tmp_path: Path) -> None:
    status_root = tmp_path / "status"
    rows = {
        "2025-05-01": _row("2025-05-01", status="PASS"),
        "2025-05-02": _row(
            "2025-05-02", status="FAIL",
            error_summary="B2 RESTORATION_NOT_CONVERGED",
        ),
        "2025-05-03": _row("2025-05-03"),
        "2025-05-04": _row(
            "2025-05-04", search_level="K400",
            candidate_done=244, candidate_total=401,
        ),
        "2025-05-05": _row(
            "2025-05-05", search_level="K800",
            candidate_done=611, candidate_total=801,
        ),
        "2025-05-06": _row(
            "2025-05-06", search_level="FULL",
            candidate_done=1420, candidate_total=2160,
        ),
    }
    for day, row in rows.items():
        atomic_json(status_root / f"{day}.json", row)
    text = _render(status_root)
    assert "parent 1/2 | K200 | cand 77/201" in text
    assert "K400 | cand 244/401" in text
    assert "K800 | cand 611/801" in text
    assert "FULL | cand 1420/2160" in text
    assert "LAST FAIL: 2025-05-02 B2 RESTORATION_NOT_CONVERGED" in text

    atomic_json(status_root / "2025-05-03.json", _row(
        "2025-05-03", candidate_done=None, candidate_total=None,
        candidate_new_done=None, candidate_new_total=None,
        seed_done=1, seed_total=2, full_milp_status="RUNNING",
    ))
    text = _render(status_root)
    assert "parent 1/2 | K200 | seed 1/2 | RUNNING" in text

    atomic_json(status_root / "2025-05-03.json", _row(
        "2025-05-03", completed_units=8, major_units_done=8,
        stage="B2_FINAL_FULL", current_stage="B2_FINAL_FULL",
        beam_parent_index=None, beam_parent_total=None,
        search_level=None, candidate_done=None, candidate_total=None,
        candidate_new_done=None, candidate_new_total=None,
        full_milp_status="Full MILP",
    ))
    assert "Full MILP" in _render(status_root)

    atomic_json(status_root / "2025-05-03.json", _row(
        "2025-05-03", completed_units=8, major_units_done=8,
        stage="B2_RESTORATION", current_stage="B2_RESTORATION",
        restoration_round=1, restoration_round_max=5,
        restoration_new_cuts=3, restoration_total_cuts=3,
        full_milp_status="P_Q_FULL_MILP_RUNNING",
        beam_parent_index=None, beam_parent_total=None,
        search_level=None, candidate_done=None, candidate_total=None,
    ))
    text = _render(status_root)
    assert "round 1/5 | cuts +3 / total 3 | P_Q_FULL_MILP_RUNNING" in text

    fresh = _row(
        "2025-05-03", completed_units=8, major_units_done=8,
        stage="B2_RESTORATION", current_stage="B2_RESTORATION",
        restoration_round=1, restoration_round_max=5,
        restoration_new_cuts=3, restoration_total_cuts=3,
        fresh_slots_done=72, fresh_slots_total=96,
        beam_parent_index=None, beam_parent_total=None,
        search_level=None, candidate_done=None, candidate_total=None,
    )
    atomic_json(status_root / "2025-05-03.json", fresh)
    assert "Fresh 72/96" in _render(status_root)

    terminal = dict(fresh, status="PASS")
    atomic_json(status_root / "2025-05-03.json", terminal)
    atomic_json(status_root / "2025-05-07.json", _row("2025-05-07"))
    view = json.loads(_render(status_root, json_output=True))
    assert view["PASS"] == 2
    assert "2025-05-03" not in [row["date"] for row in view["active_dates"]]
    assert "2025-05-07" in [row["date"] for row in view["active_dates"]]


def test_powershell_monitor_renders_31_date_complete_screen(tmp_path: Path) -> None:
    status_root = tmp_path / "status"
    for day_index in range(1, 32):
        day = f"2025-05-{day_index:02d}"
        atomic_json(status_root / f"{day}.json", _row(day, status="PASS"))
    text = _render(status_root)
    assert "V37-R4A MAY PER-DAY FINAL - COMPLETE" in text
    assert "PASS  31" in text
    assert "ACTIVE  0" in text
    assert "REMAIN  0" in text
