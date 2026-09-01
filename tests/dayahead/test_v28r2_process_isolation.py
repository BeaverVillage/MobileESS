import hashlib
import json
from pathlib import Path

import pytest

from dayahead.v28r2.certificate import write_certificate
from tools.final_campaign.monitor_v28r2_april import snapshot
from tools.final_campaign.run_v28r2_april import (
    DAY_WORKERS,
    april_days,
    campaign_roots,
    certificate_path,
    child_command,
    immutable_pass,
    supervise_commands,
    verify_launch_gates,
)


def test_april_plan_uses_exact_day_cli_and_frozen_resources():
    assert len(april_days()) == 30
    assert april_days()[0] == "2025-04-01"
    assert april_days()[-1] == "2025-04-30"
    assert DAY_WORKERS == 2
    command = child_command("2025-04-01", python="python-test")
    assert command == (
        "python-test", "-m", "dayahead.v28r2.heavy_backend",
        "--campaign", "april", "--day", "2025-04-01",
        "--mode", "authority-preflight",
    )


def test_supervisor_never_has_more_than_two_day_processes(tmp_path: Path):
    roots = {
        "frozen_artifacts": tmp_path / "results",
        "logs": tmp_path / "logs",
        "progress": tmp_path / "progress",
    }
    active = 0
    peak = 0

    class FakeProcess:
        returncode = None

        def __init__(self):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            self.polled = False

        def poll(self):
            nonlocal active
            if not self.polled:
                self.polled = True
                active -= 1
                self.returncode = 0
                return 0
            return self.returncode

    def factory(*_args, **kwargs):
        assert kwargs["shell"] is False
        assert kwargs["env"]["V28R2_GUROBI_THREADS"] == "4"
        return FakeProcess()

    commands = [(day, child_command(day, python="python-test")) for day in april_days()[:7]]
    result = supervise_commands(commands, roots, popen_factory=factory, poll_seconds=0.01)
    assert peak == 2
    assert len(result) == 7
    assert all(row["status"] == "PASS" for row in result)


def test_launch_gate_fails_closed_before_workers(tmp_path: Path):
    with pytest.raises(RuntimeError, match="GATE_ARTIFACT_MISSING"):
        verify_launch_gates(tmp_path / "missing.json")
    path = tmp_path / "flags.json"
    path.write_text(json.dumps({"APRIL_RUNNER_READY": False}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="GATES_NOT_READY"):
        verify_launch_gates(path)


def test_valid_april_pass_is_immutable_skip(tmp_path: Path):
    cert = certificate_path(tmp_path, "2025-04-01")
    write_certificate(cert, {"artifact_id": "DAY", "day": "2025-04-01", "status": "PASS", "non_authority_smoke": False})
    assert immutable_pass(cert, "2025-04-01")
    assert not immutable_pass(cert, "2025-04-02")


def file_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*")) if path.is_file()
    }


def test_monitor_snapshot_is_read_only_and_supports_day_filter(tmp_path: Path):
    paths = campaign_roots(tmp_path)
    state_path = paths["progress"] / "2025-04-01" / "DAY_STATE.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(json.dumps({
        "status": "RUNNING",
        "current_step": "05_B0_MONOLITHIC",
        "completed_steps": ["01_INPUT_AUTHORITY_CHECK"],
        "step_sha256": {"01_INPUT_AUTHORITY_CHECK": "a" * 64},
        "predecessor_sha256": "a" * 64,
        "heartbeat_epoch": 100.0,
        "pid": None,
        "counters": {"active_solver": "MONOLITHIC", "lb": 1.0, "ub": 1.1},
    }), encoding="utf-8")
    before = file_hashes(tmp_path)
    value = snapshot(tmp_path, selected_day="2025-04-01", now=110.0)
    after = file_hashes(tmp_path)
    assert before == after
    assert value["read_only"] is True
    assert len(value["days"]) == 1
    assert value["days"][0]["predecessor_sha_status"] == "VERIFIED"
    assert value["days"][0]["heartbeat_age_seconds"] == 10.0


def test_runner_source_has_no_thread_executor():
    source = (Path(__file__).resolve().parents[2] / "tools/final_campaign/run_v28r2_april.py").read_text(encoding="utf-8")
    assert "ThreadPoolExecutor" not in source
    assert "subprocess.Popen" in source
