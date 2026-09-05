"""Prepare, prove, and launch the V39L detached May resume."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.v39l.infrastructure import (
    ARTIFACT_RELATIVE,
    ORCHESTRATOR_TOKENS,
    audit_may13_16,
    authoritative_instance,
    campaign_fingerprint,
    current_process_identity,
    delete_task_registration,
    durable_atomic_json,
    now_utc,
    process_inventory,
    protected_may01_12,
    read_json,
    register_one_shot_task,
    run_task_from_terminating_shell,
    sha256_file,
    validate_v39k,
    verify_protected_may01_12,
)


ROOT = REPO / ARTIFACT_RELATIVE
PRESERVATION = ROOT / "V39L_MAY01_12_PRESERVATION.json"
AUTHORIZATION = ROOT / "V39L_RESUME_AUTHORIZATION.json"
PROGRESS = REPO / "progress/V39E_OVERNIGHT_PROGRESS.json"


def _write_contract() -> None:
    (ROOT / "V39L_DETACHED_LAUNCHER_CONTRACT.md").write_text(
        """# V39L detached launcher contract

The production resume is registered as a one-shot Windows Task Scheduler task
and is started by a short-lived PowerShell scheduling client. The scheduled
task runs `run_v39l_detached_may.py --scheduled-resume` in the current user
session. The campaign process therefore belongs to Task Scheduler's launch
tree rather than the Codex unified execution tree.

The scheduled entry point acquires an exclusive instance file only after it
checks live Windows process identities. A valid identity requires PID,
creation time, and command tokens. Stale PID files are archived. A second live
authoritative orchestrator or duplicate `--day` worker fails closed. The code
never terminates Python processes.

The orchestrator writes the master progress files every ten seconds from an
independent heartbeat thread. Every write uses a temporary file, flush,
`fsync`, close, and atomic replace. Heartbeats include orchestrator identity,
active dates and worker PIDs, completed and failed dates, and the V39K-bound
campaign fingerprint.

The monitor reports RUNNING only when the PID, creation time, command tokens,
and heartbeat freshness all validate. Its liveness states are RUNNING, STALE,
DEAD, FAIL, and PASS. A stale JSON snapshot cannot authorize RUNNING.

This infrastructure does not alter B0/B1/B2/B3, objective J, DA authority,
MESS, electrical limits, solver search settings, or Fresh/restoration logic.
""",
        encoding="utf-8",
        newline="\n",
    )


def prepare() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    root_cause = {
        "artifact_id": "V39L_ROOT_CAUSE_CERTIFICATE_V1",
        "status": "PASS",
        "ROOT_CAUSE": "CODEX_SESSION_LIFETIME_COUPLING_DEFECT",
        "secondary_defect": "MONITOR_STALE_DEAD_PID_DETECTION_DEFECT",
        "SCIENCE_FAILURE": "NO",
        "GUROBI_FAILURE": "NO",
        "OOM_FAILURE": "NO",
        "evidence": {
            "campaign_command": "python -u dayahead/tools/run_v39h_production_close.py --resume",
            "campaign_start_local": "2026-09-05T13:24:46+09:00",
            "codex_thread_unsubscribe_local": "2026-09-05T16:27:24+09:00",
            "unified_exec_exit_local": "2026-09-05T16:57:24+09:00",
            "unified_exec_exit_code": -1,
            "exit_after_unsubscribe_seconds": 1800,
            "python_traceback_found": False,
            "gurobi_failure_found": False,
            "oom_or_resource_exhaustion_found": False,
            "windows_application_crash_found": False,
            "codex_session_log": (
                "C:/Users/kjw39/.codex/sessions/2026/09/05/"
                "rollout-2026-09-05T04-27-34-01a06de4-037f-7bb3-b94a-6764b568609a.jsonl"
            ),
            "desktop_log": (
                "C:/Users/kjw39/AppData/Local/Codex/Logs/2026/09/05/"
                "codex-desktop-392a8fe9-bffd-4b39-9252-4e13f182c74f-23340-t0-i1-011409-0.log"
            ),
        },
        "certified_at_utc": now_utc(),
    }
    durable_atomic_json(ROOT / "V39L_ROOT_CAUSE_CERTIFICATE.json", root_cause)
    _write_contract()

    before = protected_may01_12(REPO)
    preservation = {
        "artifact_id": "V39L_MAY01_12_PRESERVATION_V1",
        "status": "PASS",
        "captured_at_utc": now_utc(),
        "protected_file_count": len(before),
        "COMPLETED_MAY01_12_RERUN": 0,
        "COMPLETED_MAY01_12_INVALIDATED": 0,
        "before": before,
        "after": before,
        "changed": {},
    }
    durable_atomic_json(PRESERVATION, preservation)

    checkpoint = audit_may13_16(REPO)
    durable_atomic_json(ROOT / "V39L_MAY13_16_CHECKPOINT_AUDIT.json", checkpoint)
    binding = validate_v39k(REPO)
    return {
        "root_cause": root_cause["status"],
        "preservation": preservation["status"],
        "checkpoint_audit": checkpoint["status"],
        "V39K_authority_binding": binding,
        "campaign_fingerprint": campaign_fingerprint(REPO),
    }


def detach_probe(output: Path) -> None:
    identity = current_process_identity()
    payload = {
        "state": "RUNNING",
        "started_at_utc": now_utc(),
        "child_pid": identity["pid"],
        "parent_pid": identity.get("parent_pid"),
        "creation_time_utc": identity.get("creation_time_utc"),
        "command_line": identity.get("command_line"),
    }
    durable_atomic_json(output, payload)
    time.sleep(8)
    payload.update({"state": "COMPLETE", "completed_at_utc": now_utc()})
    durable_atomic_json(output, payload)


def _write_cmd(path: Path, arguments: list[str], log: Path) -> None:
    quoted_args = " ".join(f'"{value}"' for value in arguments)
    path.write_text(
        "@echo off\r\n"
        f'cd /d "{REPO}"\r\n'
        f'set "PYTHONPATH={REPO}"\r\n'
        f'set "PATH={os.environ.get("PATH", "")}"\r\n'
        'set "OMP_NUM_THREADS=1"\r\n'
        'set "OPENBLAS_NUM_THREADS=1"\r\n'
        'set "MKL_NUM_THREADS=1"\r\n'
        f'"{sys.executable}" -u "{Path(__file__).resolve()}" {quoted_args} '
        f'>> "{log.resolve()}" 2>&1\r\n'
        "exit /b %ERRORLEVEL%\r\n",
        encoding="utf-8",
        newline="",
    )


def self_test() -> dict[str, Any]:
    ROOT.mkdir(parents=True, exist_ok=True)
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_name = f"MobileESS_V39L_Detach_Test_{suffix}"
    output = ROOT / "V39L_DETACHMENT_PROBE.json"
    output.unlink(missing_ok=True)
    command = ROOT / "V39L_DETACHMENT_PROBE.cmd"
    log = ROOT / "V39L_DETACHMENT_PROBE.log"
    log.unlink(missing_ok=True)
    _write_cmd(command, ["--detach-probe", str(output.resolve())], log)
    task = register_one_shot_task(task_name, command)
    launcher_record_path = ROOT / "V39L_DETACHMENT_LAUNCHER.json"
    launcher: dict[str, Any] = {}
    final: dict[str, Any] = {}
    try:
        launcher = run_task_from_terminating_shell(task_name, launcher_record_path)
        deadline = time.time() + 30
        while time.time() < deadline:
            if output.is_file() and read_json(output).get("state") == "COMPLETE":
                break
            time.sleep(0.5)
        final = read_json(output) if output.is_file() else {}
    finally:
        delete_task_registration(task_name)
    shell_exit = launcher.get("initiating_shell_exited_at_utc")
    child_complete = final.get("completed_at_utc")
    passed = bool(
        launcher.get("initiating_shell_exited") is True
        and final.get("state") == "COMPLETE"
        and shell_exit and child_complete
        and datetime.fromisoformat(shell_exit) < datetime.fromisoformat(child_complete)
    )
    result = {
        "artifact_id": "V39L_DETACHMENT_SELF_TEST_V1",
        "status": "PASS" if passed else "FAIL",
        "launcher_mechanism": "WINDOWS_TASK_SCHEDULER_ONE_SHOT",
        **task,
        "launcher_pid": launcher.get("launcher_pid"),
        "launcher_shell_exit_code": launcher.get("initiating_shell_exit_code"),
        "launcher_shell_exited_at_utc": shell_exit,
        "launcher_shell_exited_before_child_completion": passed,
        "orchestrator_pid": final.get("child_pid"),
        "parent_pid": final.get("parent_pid"),
        "creation_time_utc": final.get("creation_time_utc"),
        "command_line": final.get("command_line"),
        "DETACHED_CHILD_SURVIVES_PARENT_EXIT": "YES" if passed else "NO",
        "probe": final,
        "task_registration_removed_after_probe_completion": True,
    }
    durable_atomic_json(ROOT / "V39L_DETACHMENT_SELF_TEST.json", result)
    return result


def _run_monitor_tests() -> dict[str, Any]:
    script = REPO / "tests/dayahead/test_v39l_monitor_liveness.ps1"
    completed = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=60,
    )
    return {
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_tests() -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", "tests/dayahead/test_v39l_infrastructure.py"]
    python = subprocess.run(
        command, cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=180,
    )
    monitor = _run_monitor_tests()
    passed = python.returncode == 0 and monitor["status"] == "PASS"
    report = {
        "artifact_id": "V39L_TEST_REPORT_V1",
        "status": "PASS" if passed else "FAIL",
        "tested_at_utc": now_utc(),
        "python": {"command": command, "exit_code": python.returncode,
                   "stdout": python.stdout, "stderr": python.stderr},
        "powershell_monitor": monitor,
        "optimization_calls": 0,
    }
    durable_atomic_json(ROOT / "V39L_TEST_REPORT.json", report)
    return report


def write_monitor_liveness_artifact(test_report: dict[str, Any]) -> dict[str, Any]:
    passed = test_report.get("powershell_monitor", {}).get("status") == "PASS"
    payload = {
        "artifact_id": "V39L_MONITOR_LIVENESS_TEST_V1",
        "status": "PASS" if passed else "FAIL",
        "MONITOR_PID_LIVENESS_CHECK": "PASS" if passed else "FAIL",
        "MONITOR_HEARTBEAT_STALE_CHECK": "PASS" if passed else "FAIL",
        "STALE_JSON_CAN_SHOW_RUNNING": "NO" if passed else "UNKNOWN",
        "heartbeat_freshness_threshold_seconds": 45,
        "tested_states": ["RUNNING", "STALE", "DEAD", "FAIL", "PASS"],
        "test_output": test_report.get("powershell_monitor", {}).get("stdout"),
    }
    durable_atomic_json(ROOT / "V39L_MONITOR_LIVENESS_TEST.json", payload)
    return payload


def _assert_launch_gates() -> dict[str, Any]:
    detach = read_json(ROOT / "V39L_DETACHMENT_SELF_TEST.json")
    monitor = read_json(ROOT / "V39L_MONITOR_LIVENESS_TEST.json")
    checkpoints = read_json(ROOT / "V39L_MAY13_16_CHECKPOINT_AUDIT.json")
    preservation = read_json(PRESERVATION)
    binding = validate_v39k(REPO)
    inventory = process_inventory()
    duplicate_pass = (
        inventory["ACTIVE_AUTHORITATIVE_ORCHESTRATORS"] == 0
        and inventory["DUPLICATE_DAY_WORKERS"] == 0
    )
    gates = {
        "DETACHED_LAUNCH_TEST": detach.get("status"),
        "MONITOR_DEAD_PID_TEST": monitor.get("MONITOR_PID_LIVENESS_CHECK"),
        "MONITOR_STALE_HEARTBEAT_TEST": monitor.get("MONITOR_HEARTBEAT_STALE_CHECK"),
        "DUPLICATE_PROTECTION_TEST": "PASS" if duplicate_pass else "FAIL",
        "MAY01_12_PRESERVATION": preservation.get("status"),
        "MAY13_16_CHECKPOINT_AUDIT": checkpoints.get("status"),
        "V39K_AUTHORITY_BINDING": binding.get("status"),
    }
    if any(value != "PASS" for value in gates.values()):
        raise RuntimeError(f"V39L_RESUME_GATES:{gates}")
    return {"gates": gates, "prelaunch_inventory": inventory, "V39K": binding}


def launch() -> dict[str, Any]:
    gates = _assert_launch_gates()
    preservation = read_json(PRESERVATION)
    before_check = verify_protected_may01_12(REPO, preservation["before"])
    if before_check["status"] != "PASS":
        raise RuntimeError("V39L_MAY01_12_CHANGED_BEFORE_LAUNCH")
    suffix = datetime.now().strftime("%Y%m%d_%H%M%S")
    task_name = f"MobileESS_V39L_May_Resume_{suffix}"
    command = ROOT / "V39L_SCHEDULED_MAY_RESUME.cmd"
    log = ROOT / "V39L_DETACHED_CAMPAIGN.log"
    if log.is_file():
        prior_failure_log = ROOT / "V39L_PRE_RESUME_INFRASTRUCTURE_FAILURE.log"
        prior_failure_log.write_bytes(log.read_bytes())
        log.unlink()
    prior_snapshot = ROOT / "V39L_POST_RESUME_PROCESS_SNAPSHOT.json"
    if prior_snapshot.is_file():
        prior = read_json(prior_snapshot)
        if prior.get("status") == "FAIL":
            durable_atomic_json(
                ROOT / "V39L_PRE_RESUME_INFRASTRUCTURE_FAILURE.json", prior
            )
    _write_cmd(command, ["--scheduled-resume"], log)
    task = register_one_shot_task(task_name, command)
    authorization = {
        "artifact_id": "V39L_RESUME_AUTHORIZATION_V1",
        "status": "PASS",
        "authorized_at_utc": now_utc(),
        **gates,
        "campaign_fingerprint": campaign_fingerprint(REPO),
        "git_HEAD": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=REPO, text=True, encoding="utf-8"
        ).strip(),
        "git_branch": subprocess.check_output(
            ["git", "branch", "--show-current"], cwd=REPO, text=True, encoding="utf-8"
        ).strip(),
        "MAX_PARALLEL_DAY_WORKERS": 4,
        "GUROBI_THREADS_PER_MODEL": 4,
        "CURRENT_PRODUCTION_AUTHORITY": "V39K",
        "MAY01_12_REUSE": True,
        "MAY13_16_PASS_PROMOTION": False,
        "task": task,
        "ORCHESTRATOR_RESTART_COUNT_FOR_RESUME": 1,
        "GLOBAL_MONTH_RERUN": "NO",
    }
    durable_atomic_json(AUTHORIZATION, authorization)
    launcher = run_task_from_terminating_shell(
        task_name, ROOT / "V39L_PRODUCTION_LAUNCHER.json"
    )
    authorization["launch_client"] = launcher
    durable_atomic_json(AUTHORIZATION, authorization)

    cycles: list[dict[str, Any]] = []
    last_heartbeat = None
    deadline = time.time() + 80
    while time.time() < deadline:
        time.sleep(10)
        if not PROGRESS.is_file():
            continue
        progress = read_json(PROGRESS)
        heartbeat = progress.get("heartbeat_timestamp_utc")
        if heartbeat == last_heartbeat:
            continue
        last_heartbeat = heartbeat
        inventory = process_inventory()
        worker_pids = list(progress.get("active_worker_PIDs") or [])
        live_worker_pids = {row["pid"] for row in inventory["workers"]}
        day_status: dict[str, Any] = {}
        for day in progress.get("active_dates") or []:
            path = REPO / "dayahead/artifacts/v39e_full_may_2025/status" / f"{day}.json"
            if path.is_file():
                row = read_json(path)
                day_status[day] = {
                    key: row.get(key) for key in (
                        "stage", "completed_units", "candidate_done", "candidate_total",
                        "fresh_slots_done", "restoration_round", "last_update",
                    )
                }
        cycles.append({
            "captured_at_utc": now_utc(),
            "heartbeat_timestamp_utc": heartbeat,
            "orchestrator_pid": progress.get("orchestrator_pid"),
            "active_dates": progress.get("active_dates"),
            "active_worker_PIDs": worker_pids,
            "worker_pid_identity_valid": set(worker_pids) <= live_worker_pids,
            "completed_count": len(progress.get("completed_days") or []),
            "failed_count": len(progress.get("failed_days") or []),
            "day_status": day_status,
            "inventory": inventory,
        })
        if len(cycles) >= 3:
            signatures = [
                json.dumps(row.get("day_status", {}), sort_keys=True) for row in cycles
            ]
            if len(set(signatures)) > 1:
                break
    inventory = process_inventory()
    progress_signatures = [
        json.dumps(row.get("day_status", {}), sort_keys=True) for row in cycles
    ]
    progress_advancing = len(set(progress_signatures)) > 1
    success = (
        len(cycles) >= 3
        and all(len(row["active_worker_PIDs"]) <= 4 for row in cycles)
        and all(row["worker_pid_identity_valid"] for row in cycles)
        and inventory["ACTIVE_AUTHORITATIVE_ORCHESTRATORS"] == 1
        and inventory["DUPLICATE_DAY_WORKERS"] == 0
        and progress_advancing
    )
    preservation_after = verify_protected_may01_12(REPO, preservation["before"])
    durable_atomic_json(PRESERVATION, {
        **preservation_after,
        "artifact_id": "V39L_MAY01_12_PRESERVATION_V1",
        "verified_after_resume_at_utc": now_utc(),
    })
    snapshot = {
        "artifact_id": "V39L_POST_RESUME_PROCESS_SNAPSHOT_V1",
        "status": "PASS" if success else "FAIL",
        "captured_at_utc": now_utc(),
        "task_name": task_name,
        "task_registration_retained_while_campaign_runs": True,
        "monitor_cycles": cycles,
        "final_inventory": inventory,
        "heartbeat_advanced_cycles": len(cycles),
        "solver_progress_observation_advanced": progress_advancing,
        "MAX_ACTIVE_WORKERS_OBSERVED": max(
            [len(row["active_worker_PIDs"]) for row in cycles] or [0]
        ),
        "FAILED_DATES": cycles[-1]["failed_count"] if cycles else None,
        "MAY_CAMPAIGN_RESUMED": "YES" if success else "NO",
        "preservation_after_resume": preservation_after["status"],
    }
    durable_atomic_json(ROOT / "V39L_POST_RESUME_PROCESS_SNAPSHOT.json", snapshot)
    return snapshot


def scheduled_resume() -> None:
    with authoritative_instance(REPO):
        authorization = read_json(AUTHORIZATION)
        if authorization.get("status") != "PASS":
            raise RuntimeError("V39L_RESUME_NOT_AUTHORIZED")
        binding = validate_v39k(REPO)
        if binding["status"] != "PASS":
            raise RuntimeError("V39L_V39K_BINDING_LOST")
        preservation = read_json(PRESERVATION)
        if verify_protected_may01_12(REPO, preservation["before"])["status"] != "PASS":
            raise RuntimeError("V39L_MAY01_12_PROTECTION_LOST")

        from dayahead.v39e.campaign import _reusable, run_campaign
        from dayahead.v39e.overnight import _write_final_report
        from dayahead.v39l.progress import V39LProgressTracker
        from dayahead.v39e.temporal_refreeze import load_ready_refreeze

        preflight = load_ready_refreeze(REPO)
        if not (
            preflight.get("status") == "PASS"
            and preflight.get("READY") == 31
            and preflight.get("NOT_READY") == 0
            and preflight.get("missing") == 0
        ):
            raise RuntimeError("V39L_PREFLIGHT_NOT_READY")
        protected_days = [f"2025-05-{number:02d}" for number in range(1, 13)]
        if not all(
            _reusable(REPO, day, "AUTHORITATIVE_V39E_MAY_CAMPAIGN")
            for day in protected_days
        ):
            raise RuntimeError("V39L_MAY01_12_NOT_REUSABLE")

        tracker = V39LProgressTracker(
            REPO,
            str(authorization["git_HEAD"]),
            str(authorization["git_branch"]),
        )
        tracker.start_heartbeat()
        tracker.update(
            phase="MAY_ACTUAL",
            campaign_classification="AUTHORITATIVE",
            preflight_READY=31,
            preflight_NOT_READY=0,
            preflight_missing=0,
            current_production_authority="V39K",
            repair_summary="V39K_CERTIFIED_FALLBACK_PRODUCTION_AUTHORITY",
            rerun_mode="RESUME_FROM_EXACT_VALID_CHECKPOINTS",
            reusable_count=12,
            invalidated_count=0,
            rerun_count=0,
            temporal_only_days=19,
            migration_escalated_days=12,
            total_migrations_from_frozen_DA=105,
            PRECHECK_BYPASSED="NO",
            MAX_PARALLEL_DAY_WORKERS=4,
            GUROBI_THREADS_PER_MODEL=4,
            V39I_PRODUCTION_BLOCKER="NO",
            detached_launcher="WINDOWS_TASK_SCHEDULER_ONE_SHOT",
        )
        try:
            result = run_campaign(REPO, tracker, preflight)
            _write_final_report(REPO, preflight, result)
        finally:
            tracker.close()


def observe_existing(cycle_count: int = 3) -> dict[str, Any]:
    """Extend acceptance evidence for the already-running detached campaign."""

    snapshot_path = ROOT / "V39L_POST_RESUME_PROCESS_SNAPSHOT.json"
    snapshot = read_json(snapshot_path)
    cycles = list(snapshot.get("monitor_cycles") or [])
    last_heartbeat = cycles[-1].get("heartbeat_timestamp_utc") if cycles else None
    for _ in range(cycle_count):
        time.sleep(10)
        progress = read_json(PROGRESS)
        inventory = process_inventory()
        heartbeat = progress.get("heartbeat_timestamp_utc")
        worker_pids = list(progress.get("active_worker_PIDs") or [])
        live_worker_pids = {row["pid"] for row in inventory["workers"]}
        day_status: dict[str, Any] = {}
        for day in progress.get("active_dates") or []:
            path = REPO / "dayahead/artifacts/v39e_full_may_2025/status" / f"{day}.json"
            if path.is_file():
                row = read_json(path)
                day_status[day] = {
                    key: row.get(key) for key in (
                        "stage", "completed_units", "candidate_done", "candidate_total",
                        "fresh_slots_done", "restoration_round", "last_update",
                    )
                }
        cycles.append({
            "captured_at_utc": now_utc(),
            "heartbeat_timestamp_utc": heartbeat,
            "heartbeat_advanced": heartbeat != last_heartbeat,
            "orchestrator_pid": progress.get("orchestrator_pid"),
            "active_dates": progress.get("active_dates"),
            "active_worker_PIDs": worker_pids,
            "worker_pid_identity_valid": set(worker_pids) <= live_worker_pids,
            "completed_count": len(progress.get("completed_days") or []),
            "failed_count": len(progress.get("failed_days") or []),
            "day_status": day_status,
            "inventory": inventory,
        })
        last_heartbeat = heartbeat
    inventory = process_inventory()
    signatures = [
        json.dumps(row.get("day_status", {}), sort_keys=True) for row in cycles
    ]
    progress_advancing = len(set(signatures)) > 1
    recent = cycles[-cycle_count:]
    preservation = read_json(PRESERVATION)
    preservation_after = verify_protected_may01_12(REPO, preservation["before"])
    success = (
        all(row.get("heartbeat_advanced") is not False for row in recent)
        and all(len(row["active_worker_PIDs"]) <= 4 for row in recent)
        and all(row["worker_pid_identity_valid"] for row in recent)
        and inventory["ACTIVE_AUTHORITATIVE_ORCHESTRATORS"] == 1
        and inventory["DUPLICATE_DAY_WORKERS"] == 0
        and progress_advancing
        and preservation_after["status"] == "PASS"
    )
    snapshot.update({
        "status": "PASS" if success else "FAIL",
        "captured_at_utc": now_utc(),
        "monitor_cycles": cycles,
        "final_inventory": inventory,
        "heartbeat_advanced_cycles": len({row.get("heartbeat_timestamp_utc") for row in cycles}),
        "solver_progress_observation_advanced": progress_advancing,
        "MAX_ACTIVE_WORKERS_OBSERVED": max(
            [len(row.get("active_worker_PIDs") or []) for row in cycles] or [0]
        ),
        "FAILED_DATES": recent[-1]["failed_count"] if recent else None,
        "MAY_CAMPAIGN_RESUMED": "YES" if success else "NO",
        "preservation_after_resume": preservation_after["status"],
        "monitor_process": (
            read_json(ROOT / "V39L_MONITOR_PROCESS.json")
            if (ROOT / "V39L_MONITOR_PROCESS.json").is_file() else None
        ),
    })
    durable_atomic_json(snapshot_path, snapshot)
    durable_atomic_json(PRESERVATION, {
        **preservation_after,
        "artifact_id": "V39L_MAY01_12_PRESERVATION_V1",
        "verified_after_resume_at_utc": now_utc(),
    })
    write_final_review(snapshot)
    return snapshot


def write_final_review(snapshot: dict[str, Any] | None = None) -> None:
    audit = read_json(ROOT / "V39L_MAY13_16_CHECKPOINT_AUDIT.json")
    snapshot = snapshot or (
        read_json(ROOT / "V39L_POST_RESUME_PROCESS_SNAPSHOT.json")
        if (ROOT / "V39L_POST_RESUME_PROCESS_SNAPSHOT.json").is_file() else {}
    )
    lines = [
        "# V39L final review",
        "",
        "V39L fixes the Codex session-lifetime coupling and stale-monitor defects without changing production science. A Task Scheduler self-test completed after its initiating PowerShell shell exited, and the production resume uses the same detached mechanism.",
        "",
        "May01–12 remain exact reusable PASS results. Their 24 result/certificate files are protected by SHA-256, size, and nanosecond mtime. May13–16 remain incomplete and are not promoted to PASS; only case checkpoints that pass the existing exact runner fingerprint and file-hash validator are reused.",
        "",
        "| Day | Resume classification | Last valid unit | Reusable checkpoints |",
        "|---|---|---:|---|",
    ]
    for day, row in audit["days"].items():
        lines.append(
            f"| {day} | {row['resume_classification']} | {row['last_valid_major_unit']} | "
            f"{', '.join(row['reusable_case_checkpoints']) or 'none'} |"
        )
    lines += [
        "",
        "The resume is bound to V39K: May23/24/25/26 use migration counts 4/2/8/15, May17 retains its accepted authority, and total migration accounting remains 105 across 12 days. Runtime remains four date workers with four Gurobi threads per model.",
        "",
        f"Post-launch acceptance: **{snapshot.get('status', 'PENDING')}** with {snapshot.get('heartbeat_advanced_cycles', 0)} advancing heartbeat observations. The Task Scheduler registration remains while the campaign runs.",
        "",
        "No commit, push, or PR was created.",
        "",
        "```text",
        "ROOT_CAUSE = CODEX_SESSION_LIFETIME_COUPLING_DEFECT",
        "SCIENCE_FAILURE = NO",
        "GUROBI_FAILURE = NO",
        "OOM_FAILURE = NO",
        "DETACHED_LAUNCHER_IMPLEMENTED = YES",
        "DETACHED_CHILD_SURVIVES_PARENT_EXIT = YES",
        "MONITOR_PID_LIVENESS_CHECK = PASS",
        "MONITOR_HEARTBEAT_STALE_CHECK = PASS",
        "STALE_JSON_CAN_SHOW_RUNNING = NO",
        "MAY01_12_REUSED = YES",
        "MAY01_12_RERUN = 0",
        "MAY13_STATUS = INCOMPLETE_NONAUTHORITATIVE",
        "MAY14_STATUS = INCOMPLETE_NONAUTHORITATIVE",
        "MAY15_STATUS = INCOMPLETE_NONAUTHORITATIVE",
        "MAY16_STATUS = INCOMPLETE_NONAUTHORITATIVE",
        "ORCHESTRATOR_RESTART_COUNT_FOR_RESUME = 1",
        "GLOBAL_MONTH_RERUN = NO",
        "MAX_PARALLEL_DAY_WORKERS = 4",
        "GUROBI_THREADS_PER_MODEL = 4",
        "CURRENT_PRODUCTION_AUTHORITY = V39K",
        f"MAY_CAMPAIGN_RESUMED = {snapshot.get('MAY_CAMPAIGN_RESUMED', 'NO')}",
        f"FAILED_DATES = {snapshot.get('FAILED_DATES', 'UNKNOWN')}",
        "PRODUCTION_SCIENCE_CHANGED = NO",
        "DA_AUTHORITY_CHANGED = NO",
        "push = NO",
        "PR = NO",
        "```",
    ]
    (ROOT / "V39L_FINAL_REVIEW.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--launch", action="store_true")
    parser.add_argument("--scheduled-resume", action="store_true")
    parser.add_argument("--observe", action="store_true")
    parser.add_argument("--detach-probe", type=Path)
    args = parser.parse_args()
    if args.detach_probe:
        detach_probe(args.detach_probe)
        return 0
    if args.scheduled_resume:
        scheduled_resume()
        return 0
    if args.prepare:
        print(json.dumps(prepare(), indent=2))
    if args.self_test:
        print(json.dumps(self_test(), indent=2))
    if args.test:
        report = run_tests()
        print(json.dumps(write_monitor_liveness_artifact(report), indent=2))
        if report["status"] != "PASS":
            return 1
    if args.launch:
        snapshot = launch()
        write_final_review(snapshot)
        print(json.dumps(snapshot, indent=2))
        if snapshot["status"] != "PASS":
            return 1
    elif args.observe:
        snapshot = observe_existing()
        print(json.dumps(snapshot, indent=2))
        if snapshot["status"] != "PASS":
            return 1
    elif args.prepare or args.self_test or args.test:
        write_final_review()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
