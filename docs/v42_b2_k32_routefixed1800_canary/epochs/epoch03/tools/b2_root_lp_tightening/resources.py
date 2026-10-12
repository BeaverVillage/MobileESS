"""Read-only B1 priority and Windows memory admission for B2 LP research.

B1 is currently quiescent after its unchanged global integrity error, not a
completed 31-date campaign. A fresh full audit is required before each LP.
Callbacks use a light process/file check and normally terminate only B2 on drift.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools.critical_grid_cg.resources import (
    GIB, admission, admission_record, command, digest, growth_reserve,
    heavy_candidates as _strict_heavy_candidates, inventory, memory, readonly_audit,
)

DOCS = REPO / "docs/v42_b2_root_lp_tightening"
BASELINE = DOCS / "B1_PROTECTED_BASELINE.json"
B1_ROOT = Path(r"D:\v42_b1_only_may_20261012_04")
B1_SOURCE = Path(r"D:\v42_b1_only_source_20261012")
B1_HEAD = "4a969c59823c67dc5f52474491b24a9d55107e3d"
PR211_ROOT = Path(r"D:\v42_critical_grid_cg_lb_20261012")
PR211_HEAD = "d12315a3757aec187c8da0685c28ef901466386a"
OVERRIDE = DOCS / "USER_PRIORITY_OVERRIDE.json"
USER_OVERRIDE_QUOTE = "B1 돌리지 말라고 했어. 너 작업이 우선이야. 실행할 프로세서 있으면 실행해."
REPAIR_TOOLS = Path(r"D:\v42_b1_repair_source_20261012\tools")
KNOWN_NATIVE0_AUDITS = {
    str(REPAIR_TOOLS / "b1_pricing_incomplete_audit.py"): "e407d3e3c3f291fa665e8f59e36251678bc6c9b484c9d0224fde369625d0775a",
    str(REPAIR_TOOLS / "b1_history_model_audit.py"): "95d8e67bdc5e61ce7bda853fb75b523bd3ea3922d644a232891d13cd59f1142e",
}
HISTORY_PREFIX_SHA = "cf166c1bf4c3cc48d5d349212cebd816e593c2097c014b23175c96f07559f615"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def sha(path):
    return digest(path)["sha256"]


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def user_priority_override():
    try:
        record = read(OVERRIDE)
        return (record.get("user_request") == USER_OVERRIDE_QUOTE
                and record.get("B2_root_LP_study_priority") is True
                and record.get("previous_B1_first_condition_overridden") is True
                and record.get("launch_B1") is False
                and record.get("do_not_change_B1_source_ledger_results") is True
                and record.get("actual_other_heavy_solver_and_RAM_commit_gates_preserved") is True)
    except (OSError, ValueError, KeyError):
        return False


def known_native0_audit(process):
    """Only reviewed, SHA-pinned Python audit entrypoints; never unknown GP."""
    try:
        argv = process.get("command") or []
        script = next((argument for argument in argv[1:] if str(argument).lower().endswith(".py")), None)
        if not script:
            return False
        script = Path(script)
        if not script.is_absolute():
            if not process.get("cwd"):
                return False
            script = Path(process["cwd"]) / script
        script = str(script.resolve())
        expected = next((value for path, value in KNOWN_NATIVE0_AUDITS.items()
                         if str(script).lower() == path.lower()), None)
        if expected is None or sha(script) != expected:
            return False
        if str(script).lower().endswith("b1_history_model_audit.py"):
            return sha(REPAIR_TOOLS / "b1_snapshot_prefix.py") == HISTORY_PREFIX_SHA
        return True
    except (OSError, ValueError, KeyError):
        return False


def heavy_candidates(processes):
    candidates = _strict_heavy_candidates(processes)
    if not user_priority_override():
        return candidates
    return [process for process in candidates if not known_native0_audit(process)]


def tasks():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    script = "Get-ScheduledTask -TaskName '*B1_Only*V4*' | ForEach-Object {[PSCustomObject]@{TaskName=$_.TaskName;State=$_.State.ToString();Enabled=$_.Settings.Enabled;Actions=@($_.Actions|Select-Object Execute,Arguments,WorkingDirectory)}} | ConvertTo-Json -Depth 5"
    result = json.loads(command([shell, "-NoProfile", "-Command", script]))
    return [result] if isinstance(result, dict) else result


def task_contract(task_records):
    # A watchdog can briefly enter Running while returning at the error guard.
    # Preserve its enabled state and actions; do not mistake State for a worker.
    return [{k: record[k] for k in ("TaskName", "Enabled", "Actions")}
            for record in sorted(task_records, key=lambda item: item["TaskName"])]


def b1_active_processes(processes):
    active = []
    for process in processes:
        argv = process.get("command") or []
        joined = " ".join(argv).lower()
        roles = {str(argument).lower() for argument in argv}
        # Repair/audit scripts can retain large Gurobi objects despite Native=0.
        # Do not infer that they are light from the absence of an optimize call.
        # Only the known monitor and currently frozen error-guarded V4 safeguard
        # roles are exempt from the broad B1 computational-process gate.
        b1_marked = any(marker in joined for marker in ("v42_b1", "b1_", "\\b1\\", "/b1/"))
        frozen_v4_observer = (str(B1_SOURCE / "tools/b1_only_v4.py").lower() in joined
                              and str(B1_ROOT).lower() in joined
                              and bool(roles & {"monitor", "safeguard"}))
        historical_monitor = "v42_pr134_b1.host" in joined and "monitor" in roles
        authorized_native0_audit = user_priority_override() and known_native0_audit(process)
        actual_native_role = bool(roles & {"run", "worker", "coordinator", "native"}) or "b1_bootstrap.py" in joined
        # Under the latest user instruction, a non-solving data audit alone is
        # not a scheduling conflict. Unknown loaded Gurobi remains separate.
        broad_B1_block = b1_marked and (not user_priority_override() or actual_native_role)
        if ("v42_svr11.worker" in joined
                or (broad_B1_block and not frozen_v4_observer and not historical_monitor
                    and not authorized_native0_audit)):
            active.append(process)
    return active


@lru_cache(maxsize=1)
def _module_api():
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    api = ctypes.WinDLL("psapi", use_last_error=True)
    kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
    api.EnumProcessModulesEx.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.HMODULE), wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.DWORD)
    api.EnumProcessModulesEx.restype = wintypes.BOOL
    api.GetModuleBaseNameW.argtypes = (wintypes.HANDLE, wintypes.HMODULE, wintypes.LPWSTR, wintypes.DWORD)
    api.GetModuleBaseNameW.restype = wintypes.DWORD
    return kernel, api


def quick_loaded_Gurobi(pid):
    """Windows DLL enumeration only; no large virtual-memory-map traversal."""
    import ctypes
    from ctypes import wintypes
    kernel, api = _module_api()
    handle = kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    if not handle:
        if not psutil.pid_exists(pid):
            raise psutil.NoSuchProcess(pid)
        raise OSError(ctypes.get_last_error(), "OpenProcess for DLL inventory")
    try:
        modules = (wintypes.HMODULE * 2048)()
        needed = wintypes.DWORD()
        if not api.EnumProcessModulesEx(handle, modules, ctypes.sizeof(modules), ctypes.byref(needed), 3):
            if not psutil.pid_exists(pid):
                raise psutil.NoSuchProcess(pid)
            raise OSError(ctypes.get_last_error(), "EnumProcessModulesEx")
        if needed.value > ctypes.sizeof(modules):
            raise OSError("DLL inventory capacity exceeded")
        found = []
        for module in modules[:needed.value // ctypes.sizeof(wintypes.HMODULE)]:
            name = ctypes.create_unicode_buffer(512)
            if not api.GetModuleBaseNameW(handle, module, name, len(name)):
                if not psutil.pid_exists(pid):
                    raise psutil.NoSuchProcess(pid)
                raise OSError(ctypes.get_last_error(), "GetModuleBaseNameW")
            if "gurobi" in name.value.lower():
                found.append(name.value)
        return found
    finally:
        kernel.CloseHandle(handle)


def quick_process_inventory():
    processes, errors = [], []
    for process in psutil.process_iter(["pid", "name", "create_time", "cmdline"]):
        if process.pid == os.getpid():
            continue
        name = (process.info["name"] or "").lower()
        if not (name.startswith("python") or "gurobi" in name):
            continue
        try:
            record = dict(PID=process.pid, create_time=process.create_time(),
                          name=process.name(), command=process.cmdline(), cwd=process.cwd(),
                          gurobi_loaded_modules=[])
            if not (user_priority_override() and known_native0_audit(record)):
                record["gurobi_loaded_modules"] = quick_loaded_Gurobi(process.pid)
            processes.append(record)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            # Natural process exit between enumeration and attribute reads
            # is a cleared peer, not an unknown access/integrity condition.
            continue
        except (psutil.Error, OSError) as exc:
            errors.append(dict(PID=process.pid, error=repr(exc)))
    return processes, errors


def create_baseline():
    if BASELINE.exists():
        return read(BASELINE)
    ledger = read(B1_ROOT / "CAMPAIGN_LEDGER.json")
    protected = [B1_ROOT / name for name in (
        "GLOBAL_SYSTEM_ERROR.json", "CAMPAIGN_LEDGER.json", "CAMPAIGN_MANIFEST.json", "REPORT.json",
        "SUPERVISOR_PROCESS.json", "SUPERVISOR_HEARTBEAT.json",
    )]
    protected += [B1_SOURCE / "tools" / name for name in (
        "b1_only_v4.py", "register_b1_only_v4.ps1", "b1_raw_rejection_audit.py", "finalize_b1_only_v4.py",
    )]
    protected += [Path(r"C:\Users\kjw39\.codex\automations") / name / "automation.toml" for name in (
        "v42-may-b2-b3-autonomous-recovery", "v42-may-b1-b2-hourly-recovery",
    )]
    dates = []
    for key, row in ledger["dates"].items():
        if row.get("result"):
            path = Path(row["result"])
            protected.append(path)
            native = sorted(path.parent.rglob("NATIVE_RUNTIME_LEDGER.json"))
            protected.extend(native)
            dates.append(dict(date=key, status=row["status"], reason=row.get("reason"),
                              Native_Runtime=row.get("Native_Runtime"), result=digest(path),
                              native_ledgers=[digest(p) for p in native]))
    unique = sorted(set(protected), key=str)
    now = datetime.now(timezone.utc)
    result = dict(schema="V42_B1_READONLY_PROTECTED_BASELINE_V1", observed_UTC=now.isoformat(),
                  observed_Asia_Seoul=now.astimezone(timezone(timedelta(hours=9))).isoformat(),
                  source=str(B1_SOURCE), expected_git_HEAD=B1_HEAD, root=str(B1_ROOT),
                  protected_files=[digest(path) for path in unique], scheduled_tasks=tasks(),
                  native_dates=dates, campaign_status=ledger["status"],
                  date_status_counts=dict(Counter(row["status"] for row in ledger["dates"].values())),
                  all31_completed=len(ledger["dates"]) == 31 and all(
                      row["status"] in ("PASS", "FAIL") for row in ledger["dates"].values()),
                  B1_execution_ended_with_global_error=ledger["status"] == "GLOBAL_INTEGRITY_ERROR",
                  no_mutation_of_B1=True, B2_Native_calls=0)
    write(BASELINE, result)
    return result


@lru_cache(maxsize=1)
def _baseline():
    return read(BASELINE)


def protected_checks(baseline):
    checked = []
    for record in baseline["protected_files"]:
        path = Path(record["path"])
        try:
            observed = digest(path)
            checked.append(dict(path=str(path), expected_sha256=record["sha256"],
                                observed_sha256=observed["sha256"], unchanged=observed == record))
        except (OSError, ValueError) as exc:
            checked.append(dict(path=str(path), unchanged=False, error=repr(exc)))
    return checked


def quick_callback_b1_safety():
    """Structured callback receipt; never label an opaque false as a conflict."""
    result = dict(PASS=False, reasons=[], identified_processes=[], errors=[],
                  protected_changes=[], natural_process_exits_skipped=True,
                  user_B2_priority_override=user_priority_override(), observed_time=time.time())
    try:
        baseline = _baseline()
        result["protected_changes"] = [item for item in protected_checks(baseline) if not item["unchanged"]]
        if result["protected_changes"]:
            result["reasons"].append("PROTECTED_B1_BYTES_CHANGED")
        if not (B1_ROOT / "GLOBAL_SYSTEM_ERROR.json").is_file():
            result["reasons"].append("ORIGINAL_B1_ERROR_GUARD_ABSENT")
        processes, errors = quick_process_inventory()
        result["errors"] = errors
        if errors:
            result["reasons"].append("PROCESS_ACCESS_OR_INVENTORY_ERROR")
        # Commands and cheap Windows DLL enumeration detect actual/unknown
        # Native peers without a full virtual-memory-map walk.
        workers = b1_active_processes(processes)
        heavy = heavy_candidates(processes)
        if workers:
            result["reasons"].append("ACTUAL_B1_NATIVE_WORKER_OR_DISPATCHER")
        if heavy:
            result["reasons"].append("OTHER_NATIVE_COMMAND_OR_UNKNOWN_GUROBI_DLL")
        result["identified_processes"] = workers + [p for p in heavy if p not in workers]
        result["permitted_native0_audits"] = [p for p in processes if user_priority_override() and known_native0_audit(p)]
        result["PASS"] = not result["reasons"]
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        result["reasons"].append("CALLBACK_GATE_EXCEPTION")
        result["errors"].append(dict(error=repr(exc)))
    return result


def quick_callback_b1_safe():
    return quick_callback_b1_safety()["PASS"]


def b1_safety():
    """Fresh priority gate; unchanged abort guard is execution quiescence only."""
    baseline = create_baseline()
    protected = protected_checks(baseline)
    processes, errors = inventory()
    active = b1_active_processes(processes)
    heavy = heavy_candidates(processes)
    ledger = read(B1_ROOT / "CAMPAIGN_LEDGER.json")
    source = (B1_SOURCE / "tools/b1_only_v4.py").read_text(encoding="utf-8-sig")
    safeguard = source[source.index("def safeguard(root):"):]
    source_HEAD = command(["git", "-C", str(B1_SOURCE), "rev-parse", "HEAD"])
    source_status = command(["git", "-C", str(B1_SOURCE), "status", "--porcelain"])
    current_tasks = tasks()
    original_task_contract = task_contract(baseline["scheduled_tasks"])
    current_task_contract = task_contract(current_tasks)
    task_state_same = current_task_contract == original_task_contract
    override = user_priority_override()
    disabled_stop_accepted = (override
        and [{k: item[k] for k in ("TaskName", "Actions")} for item in current_task_contract]
            == [{k: item[k] for k in ("TaskName", "Actions")} for item in original_task_contract]
        and all(not item["Enabled"] for item in current_task_contract))
    checks = dict(
        frozen_B1_protected_bytes_unchanged=all(item["unchanged"] for item in protected),
        B1_source_exact_PR212_HEAD_clean=source_HEAD == B1_HEAD and not source_status,
        original_global_error_guard_present=(B1_ROOT / "GLOBAL_SYSTEM_ERROR.json").is_file(),
        original_global_integrity_error_status=ledger["status"] == "GLOBAL_INTEGRITY_ERROR",
        no_B1_worker_or_supervisor=not active,
        no_other_observed_heavy_Gurobi=not heavy,
        process_inventory_no_errors=not errors,
        exact_watchdog_guard_returns_before_dispatch=(
            "if (root/'STOP_REQUEST.json').exists() or (root/'GLOBAL_SYSTEM_ERROR.json').exists():return" in safeguard
            and safeguard.index("GLOBAL_SYSTEM_ERROR.json") < safeguard.index("subprocess.Popen")
        ),
        B1_task_enabled_and_action_contract_unchanged=task_state_same or disabled_stop_accepted,
        no_campaign_completion_claim=not (B1_ROOT / "CAMPAIGN_COMPLETION.json").exists(),
    )
    now = datetime.now(timezone.utc)
    return dict(schema="V42_B1_PRIORITY_READONLY_SAFETY_V1", PASS=all(checks.values()), checks=checks,
                observed_UTC=now.isoformat(), observed_Asia_Seoul=now.astimezone(timezone(timedelta(hours=9))).isoformat(),
                B1_execution_quiescent_after_original_failure=all(checks.values()),
                B1_all31_complete=False, B1_campaign_status=ledger["status"],
                date_status_counts=dict(Counter(row["status"] for row in ledger["dates"].values())),
                no_B1_native_worker=not active, error_guard=digest(B1_ROOT / "GLOBAL_SYSTEM_ERROR.json"),
                baseline=digest(BASELINE), protected_files=protected,
                source_git_HEAD=source_HEAD, source_git_status=source_status,
                scheduled_tasks=current_tasks, processes=processes, B1_active_processes=active,
                other_heavy_candidates=heavy, process_inventory_errors=errors,
                latest_user_B2_priority_override=override,
                requested_B1_disabled_stop_observed_readonly=disabled_stop_accepted,
                permitted_SHA_pinned_Native0_audits=[process for process in processes
                    if override and known_native0_audit(process)],
                policy=("Latest explicit user instruction gives B2 priority. SHA-pinned reviewed Native0 audits may coexist subject to actual RAM/commit/CPU admission; actual Native workers and unknown Gurobi processes remain excluded. Preserve original B1 source, results and ledgers; observe the user-requested Disabled task state without changing tasks."
                        if override else "B1 priority. Refresh before each LP and check lightweight B1 guard/process gate during Native; terminate B2 normally if any B1 worker, supervisor, repair/audit computational process appears or protected bytes drift. Only known monitor and frozen error-guarded V4 safeguard roles are allowed. Never stop or alter B1."),
                mutations_of_B1=0, B2_Native_calls=0)


def audit(phase="PRE_BUILD_READONLY", remote_check=False):
    result = readonly_audit(phase=phase, remote_check=remote_check)
    safety = b1_safety()
    # The authorized PR212 B1-only prompt replaced the older PR209 heartbeat
    # prompt. Preserve its current PAUSED bytes; keep the historical mismatch
    # visible instead of demanding a rollback to the superseded prompt.
    historical = result["checks"].pop("relevant_automations_PAUSED_and_unchanged")
    baseline_files = {record["path"]: record for record in _baseline()["protected_files"]}
    automation_checks = [record["status"] == "PAUSED" and record["path"] in baseline_files
                         and record["sha256"] == baseline_files[record["path"]]["sha256"]
                         for record in result["automations"]]
    result["historical_PR209_automation_check"] = dict(PASS=historical,
        interpretation="Authorized PR212 B1-only heartbeat prompt differs from PR209; current PAUSED bytes are frozen in this new research baseline. No automation was modified by this work.")
    result["checks"]["current_PR212_automations_PAUSED_and_frozen"] = all(automation_checks)
    head = command(["git", "-C", str(PR211_ROOT), "rev-parse", "HEAD"])
    status = command(["git", "-C", str(PR211_ROOT), "status", "--porcelain"])
    result["checks"].update(PR211_exact_HEAD_clean=head == PR211_HEAD and not status,
                             B1_actual_execution_ended_and_error_guard_quiescence=safety["PASS"])
    result["originals"].append(dict(name="PR211_K48_CG", path=str(PR211_ROOT), HEAD=head,
                                   expected_HEAD=PR211_HEAD, HEAD_matches=head == PR211_HEAD,
                                   clean=not status, git_status=status))
    result.update(schema="V42_B2_ROOT_LP_READONLY_RESOURCE_B1_PRIORITY_V1", B1=safety,
                  PASS=all(result["checks"].values()), maximum_LP_calls=3,
                  maximum_requested_Native_seconds=720, per_LP_TimeLimit_seconds=240,
                  Full_MIP_calls=0, official_campaign_calls=0)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DOCS / "PRE_RUN_RESOURCE_HOLD.json")
    parser.add_argument("--phase", default="PRE_BUILD_READONLY")
    parser.add_argument("--remote-check", action="store_true")
    args = parser.parse_args()
    result = audit(args.phase, args.remote_check)
    write(args.output, result)
    print(json.dumps(dict(output=str(args.output), PASS=result["PASS"], checks=result["checks"],
                          system_after=result["system_after"], B1_counts=result["B1"]["date_status_counts"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
