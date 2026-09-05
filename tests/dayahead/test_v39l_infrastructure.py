from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from dayahead.v39l.infrastructure import (
    ORCHESTRATOR_TOKENS,
    durable_atomic_json,
    identity_matches,
    process_inventory,
    validate_v39k,
)


REPO = Path(__file__).resolve().parents[2]


def _row(pid: int, command: str, creation: str = "2026-09-05T08:00:00+00:00"):
    return {
        "ProcessId": pid,
        "ParentProcessId": 1,
        "CreationDate": creation,
        "Name": "python.exe",
        "ExecutablePath": "C:/Python/python.exe",
        "CommandLine": command,
    }


def test_durable_atomic_json_replaces_complete_document(tmp_path: Path) -> None:
    path = tmp_path / "heartbeat.json"
    durable_atomic_json(path, {"sequence": 1, "active": [13, 14]})
    durable_atomic_json(path, {"sequence": 2, "active": []})
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "active": [], "sequence": 2,
    }
    assert not list(tmp_path.glob("*.tmp"))


def test_process_inventory_detects_duplicate_days_and_orchestrators() -> None:
    rows = [
        _row(101, "python run_v39l_detached_may.py --scheduled-resume"),
        _row(102, "python run_v39l_detached_may.py --scheduled-resume"),
        _row(201, "python -m dayahead.tools.run_v39e_may_day --day 2025-05-13"),
        _row(202, "python -m dayahead.tools.run_v39e_may_day --day 2025-05-13"),
        _row(203, "python -m dayahead.tools.run_v39e_may_day --day 2025-05-14"),
        _row(999, "python unrelated.py"),
    ]
    result = process_inventory(rows)
    assert result["ACTIVE_AUTHORITATIVE_ORCHESTRATORS"] == 2
    assert result["DUPLICATE_DAY_WORKERS"] == 1
    assert result["duplicate_day_worker_pids"] == {"2025-05-13": [201, 202]}
    assert all(row["pid"] != 999 for row in result["orchestrators"] + result["workers"])


def test_identity_requires_pid_creation_time_and_command_tokens() -> None:
    saved = {
        "pid": 101,
        "creation_time_utc": "2026-09-05T08:00:00+00:00",
        "command_match_tokens": list(ORCHESTRATOR_TOKENS),
    }
    live = process_inventory([
        _row(101, "python run_v39l_detached_may.py --scheduled-resume")
    ])["orchestrators"][0]
    assert identity_matches(saved, live)
    assert not identity_matches({**saved, "pid": 100}, live)
    assert not identity_matches(
        {**saved, "creation_time_utc": "2026-09-05T07:59:50+00:00"}, live
    )
    assert not identity_matches({**saved, "command_match_tokens": ["other.py"]}, live)


def test_current_v39k_binding_is_exact() -> None:
    binding = validate_v39k(REPO)
    assert binding["status"] == "PASS"
    assert binding["fallback_migrations"] == {
        "2025-05-23": 4,
        "2025-05-24": 2,
        "2025-05-25": 8,
        "2025-05-26": 15,
    }
    assert binding["May17_retained"] is True
    assert binding["minimum_RUNNING_migrations"] == 105
    assert binding["RUNNING_migration_days"] == 12


def test_v39l_infrastructure_does_not_invalidate_frozen_preflight() -> None:
    from dayahead.v39e.temporal_refreeze import load_ready_refreeze

    preflight = load_ready_refreeze(REPO)
    assert (preflight["status"], preflight["READY"], preflight["NOT_READY"], preflight["missing"]) == (
        "PASS", 31, 0, 0,
    )
