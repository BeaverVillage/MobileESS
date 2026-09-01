import json
import subprocess
from pathlib import Path

import pytest

from dayahead.v28r2 import backend_contract
from dayahead.v28r2.backend_contract import DayRunSpec, NativeSettings, fixed_aest_axis
from dayahead.v28r2.certificate import verify_certificate, write_certificate
from dayahead.v28r2.day_state import DayState
from dayahead.v28r2.runtime_ledger import RuntimeLedger


SHA = "a" * 64


def spec() -> DayRunSpec:
    return DayRunSpec(
        day="2025-04-01", campaign="april", timestamps_fixed_aest=fixed_aest_axis("2025-04-01"),
        git_head=SHA, code_tree_sha256=SHA, config_sha256=SHA, source_day_sha256=SHA,
        ml_model_sha256=SHA, thermal_sha256=SHA, scale_sha256=SHA,
        formulation_fingerprint=SHA, settings=NativeSettings(),
        output_roots={"frozen_artifacts": "a", "logs": "b", "progress": "c"},
    )


def test_day_run_spec_is_fixed_96_slot_aest_and_four_threads():
    value = spec()
    value.validate()
    assert len(value.timestamps_fixed_aest) == 96
    assert value.settings.gurobi_threads == 4
    assert value.settings.day_workers == 4


def test_git_head_retries_windows_linked_worktree_path_under_wsl(tmp_path: Path, monkeypatch):
    (tmp_path / ".git").write_text("gitdir: C:/repo/.git/worktrees/child\n", encoding="utf-8")
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        if command[:2] == ["wslpath", "-u"]:
            return subprocess.CompletedProcess(command, 0, "/mnt/c/repo/.git/worktrees/child\n", "")
        if any(str(arg).startswith("--git-dir=") for arg in command):
            return subprocess.CompletedProcess(command, 0, "b" * 40 + "\n", "")
        return subprocess.CompletedProcess(command, 128, "", "not a git repository")

    monkeypatch.setattr(backend_contract, "NATIVE_WINDOWS", False)
    monkeypatch.setattr(backend_contract.subprocess, "run", fake_run)
    assert backend_contract.git_head(tmp_path) == "b" * 40
    assert any(
        "--git-dir=/mnt/c/repo/.git/worktrees/child" in str(argument).replace("\\", "/")
        for command in commands for argument in command
    )


def test_state_reuse_recomputes_artifact_and_predecessor_hashes(tmp_path: Path):
    state_path = tmp_path / "state.json"
    artifact = tmp_path / "one.json"
    artifact.write_text('{"ok":true}\n', encoding="utf-8")
    state = DayState("2025-04-01", "april", spec().sha256)
    state.begin_step("01_INPUT_AUTHORITY_CHECK")
    state.complete_step("01_INPUT_AUTHORITY_CHECK", {"one": artifact}, {"measured": 1})
    state.save(state_path)
    loaded = DayState.load(state_path)
    assert loaded.reusable_prefix_length() == 1
    artifact.write_text('{"ok":false}\n', encoding="utf-8")
    assert loaded.reusable_prefix_length() == 0


def test_completed_step_deep_freezes_nested_runtime_counters(tmp_path: Path):
    artifact = tmp_path / "one.json"
    artifact.write_text('{"ok":true}\n', encoding="utf-8")
    nested = {"ledger": {"solver_calls": []}}
    state = DayState("2025-04-01", "april", spec().sha256)
    state.begin_step("01_INPUT_AUTHORITY_CHECK")
    state.complete_step("01_INPUT_AUTHORITY_CHECK", {"one": artifact}, nested)
    sealed = state.step_sha256["01_INPUT_AUTHORITY_CHECK"]
    nested["ledger"]["solver_calls"].append({"case": "B0"})
    assert state.step_counters["01_INPUT_AUTHORITY_CHECK"]["ledger"]["solver_calls"] == []
    assert state.step_sha256["01_INPUT_AUTHORITY_CHECK"] == sealed
    assert state.reusable_prefix_length() == 1


def test_runtime_ledger_never_prefills_success_counts():
    ledger = RuntimeLedger("2025-04-01")
    assert ledger.solver_calls == []
    assert ledger.opendss_solved_slots == {}
    assert ledger.pue_calls == {}
    assert ledger.optimizer_calls_by_namespace["ACTUAL"] == 0
    ledger.begin_opendss("DA/B0")
    ledger.record_opendss_slot("DA/B0", 0, True)
    assert ledger.opendss_solved_slots["DA/B0"] == 1
    assert ledger.opendss_engine_count["DA/B0"] == 1
    with pytest.raises(RuntimeError):
        ledger.record_opendss_slot("DA/B0", 2, True)


def test_certificate_digest_is_recomputed_from_disk(tmp_path: Path):
    path = tmp_path / "certificate.json"
    write_certificate(path, {"artifact_id": "TEST", "value": 1})
    assert verify_certificate(path)["value"] == 1
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["value"] = 2
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(RuntimeError):
        verify_certificate(path)
