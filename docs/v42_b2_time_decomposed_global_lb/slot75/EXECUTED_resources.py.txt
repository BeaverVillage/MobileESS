"""Read-only process, source, B1 stop-state and Windows memory admission.

This module imports no solver and never changes processes, schedules,
automations or predecessors. A pre-build audit never authorizes Optimize;
refresh ``admit`` after model readback. Only this new research tree is written.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
import os
from pathlib import Path
import shutil
import sys
import time

import psutil

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from tools.critical_grid_cg.resources import (
    GIB, admission, admission_record, command, digest, growth_reserve, memory,
)
from tools.b2_root_lp_tightening.resources import (
    known_native0_audit, quick_loaded_Gurobi,
)

DOCS = REPO / "docs/v42_b2_time_decomposed_global_lb"
BASELINE = DOCS / "PROTECTED_BASELINE.json"
B1_ROOT = Path(r"D:\v42_b1_only_may_20261012_04")
B1_STOP = Path(r"D:\v42_b1_repair_source_20261012\docs\v42_b1_rootcause_20261012\USER_B1_STOP_RECEIPT.json")
ORIGINALS = {
    "PR207": (Path(r"D:\v42_svr11_epoch18r_20261011"), "497609b46faa14ea7e32a9483a333ab32fd264ef"),
    "PR209": (Path(r"D:\ChatGPT\Mobile ESS 2\work\source18r-physical-global-lb-pilot"), "9383a99f1bdcabbd49c79b3ad9f9ee36d523868a"),
    "PR210": (Path(r"D:\v42_joint_critical_grid_lb_20261012"), "6a8fd44f59f1f461c60d2d14f5f5be605e4ed640"),
    "PR211": (Path(r"D:\v42_critical_grid_cg_lb_20261012"), "d12315a3757aec187c8da0685c28ef901466386a"),
    "PR212": (Path(r"D:\v42_b1_only_source_20261012"), "4a969c59823c67dc5f52474491b24a9d55107e3d"),
    "PR213": (Path(r"D:\v42_b1_repair_source_20261012"), "21c84ee6d8127d56ab69bd267f7d8f3fdb8d80ef"),
    "PR214": (Path(r"D:\v42_b2_root_lp_tightening_20261012"), "40ab888b884255e76fd6c89fd01933570b60c242"),
}
NATIVE_MARKERS = (
    "v42_svr11.worker", "gurobi_cl", "gurobi.sh", "run_joint", "run_native",
    "native_worker", "--mode native", "--mode solve", "--phase native",
    "time_decomposed_lb/pilot.py", "time_decomposed_lb\\pilot.py",
)


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def timestamp():
    now = datetime.now(timezone.utc)
    return dict(observed_UTC=now.isoformat(), observed_Asia_Seoul=now.astimezone(timezone(timedelta(hours=9))).isoformat())


def tasks():
    shell = shutil.which("pwsh") or shutil.which("powershell")
    script = "Get-ScheduledTask | Where-Object {$_.TaskName -like '*V42*B1*' -or $_.TaskName -like 'MobileESS_V42_May_B2_B3_Autonomous_*'} | ForEach-Object {[PSCustomObject]@{TaskName=$_.TaskName;TaskPath=$_.TaskPath;State=$_.State.ToString();Enabled=$_.Settings.Enabled;Actions=@($_.Actions|Select-Object Execute,Arguments,WorkingDirectory)}} | ConvertTo-Json -Depth 5"
    output = command([shell, "-NoProfile", "-Command", script])
    result = json.loads(output) if output else []
    return [result] if isinstance(result, dict) else result


def task_contract(records):
    return [{key: item[key] for key in ("TaskName", "TaskPath", "Enabled", "Actions")}
            for item in sorted(records, key=lambda item: item["TaskName"])]


def inventory():
    """Structured fast Windows DLL census, tolerating only natural exits."""
    processes, errors = [], []
    # Query expensive command-line/cwd/DLL details only after filtering the
    # executable name. Requesting cmdline for every Windows process made the
    # previous all-process callback census take approximately3.3 seconds.
    for process in psutil.process_iter(["pid", "name"]):
        if process.pid == os.getpid():
            continue
        name = (process.info["name"] or "").lower()
        if not (name.startswith("python") or "gurobi" in name):
            continue
        try:
            info = process.memory_info()
            record = dict(PID=process.pid, create_time=process.create_time(), name=process.name(),
                          command=process.cmdline(), cwd=process.cwd(), status=process.status(),
                          CPU_seconds=sum(process.cpu_times()[:2]), RSS_bytes=info.rss,
                          Private_Commit_bytes=getattr(info, "private", info.rss),
                          gurobi_loaded_modules=[])
            record["reviewed_SHA_pinned_Native0_audit"] = known_native0_audit(record)
            record["gurobi_loaded_modules"] = quick_loaded_Gurobi(process.pid)
            processes.append(record)
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            continue
        except (psutil.Error, OSError) as exc:
            errors.append(dict(PID=process.pid, error=repr(exc)))
    return processes, errors


def heavy_candidates(processes):
    answer = []
    for process in processes:
        joined = " ".join(process.get("command") or []).lower()
        native = any(marker in joined for marker in NATIVE_MARKERS)
        # A reviewed stored-evidence audit has no Optimize statement, but its
        # actual RAM/private memory still participates in admission. Unknown
        # loaded Gurobi is never exempted merely by a label or small CPU use.
        unknown_gp = bool(process.get("gurobi_loaded_modules")) and not process.get("reviewed_SHA_pinned_Native0_audit")
        if native or unknown_gp:
            answer.append(process)
    return answer


def b1_native_processes(processes):
    answer = []
    for process in processes:
        argv = process.get("command") or []
        joined = " ".join(argv).lower()
        b1 = any(marker in joined for marker in ("v42_b1", "b1_", "\\b1\\", "/b1/"))
        roles = {str(argument).lower() for argument in argv}
        if b1 and (roles & {"run", "worker", "coordinator", "native", "bootstrap"}
                   or "b1_bootstrap.py" in joined):
            answer.append(process)
    return answer


def create_baseline():
    if BASELINE.exists():
        return read(BASELINE)
    prior = read(REPO / "docs/v42_b2_root_lp_tightening/B1_PROTECTED_BASELINE.json")
    hold = read(REPO / "docs/v42_physical_global_lb_pilot/HOLD_READONLY.json")
    paths = {Path(item["path"]) for item in prior["protected_files"]}
    paths.update(Path(item["path"]) for item in hold["hold_markers"])
    paths.update(Path(item["path"]) for item in hold["automations"])
    paths.add(B1_STOP)
    # Previous scientific evidence stays in predecessor checkouts. Hash every
    # existing Native ledger without launching or constructing any model.
    for root, _head in ORIGINALS.values():
        for path in root.glob("docs/**/*LEDGER*.json"):
            paths.add(path)
    ledger = read(B1_ROOT / "CAMPAIGN_LEDGER.json")
    record = dict(schema="V42_TIME_DECOMPOSITION_READONLY_PROTECTED_BASELINE_V1", **timestamp(),
                  protected_files=[digest(path) for path in sorted(paths, key=str)],
                  scheduled_tasks=tasks(), B1_campaign_status=ledger["status"],
                  B1_stop_receipt=digest(B1_STOP),
                  B1_dispatch_authorized=False, B1_launches_by_this_study=0,
                  process_schedule_automation_mutations=0,
                  note="Current PR212/213 user-stopped state is frozen. Earlier historical monitor tasks may already be enabled; this task neither launches nor alters them. Current B1-only V3/V4 and B2/B3 campaign tasks must remain Disabled. Exact task Enabled/Action contracts are checked, transient State is only recorded.")
    write(BASELINE, record)
    return record


@lru_cache(maxsize=1)
def baseline():
    return read(BASELINE)


def protected_checks(record):
    answer = []
    for item in record["protected_files"]:
        try:
            current = digest(item["path"])
            answer.append(dict(path=item["path"], expected_sha256=item["sha256"], observed_sha256=current["sha256"], unchanged=current == item))
        except (OSError, ValueError) as exc:
            answer.append(dict(path=item["path"], unchanged=False, error=repr(exc)))
    return answer


def callbackcheck():
    result = dict(schema="V42_TIME_DECOMPOSITION_CALLBACK_GATE_V1", PASS=False, reasons=[], errors=[],
                  identified_processes=[], protected_changes=[], **timestamp())
    try:
        result["protected_changes"] = [item for item in protected_checks(baseline()) if not item["unchanged"]]
        if result["protected_changes"]:
            result["reasons"].append("PROTECTED_SOURCE_RESULT_OR_LEDGER_BYTES_CHANGED")
        processes, errors = inventory()
        workers = b1_native_processes(processes)
        heavy = heavy_candidates(processes)
        result.update(errors=errors, identified_processes=workers + [item for item in heavy if item not in workers],
                      permitted_reviewed_Native0_audits=[item for item in processes if item["reviewed_SHA_pinned_Native0_audit"]])
        if workers:
            result["reasons"].append("ACTUAL_B1_NATIVE_WORKER_OR_DISPATCHER")
        if heavy:
            result["reasons"].append("OTHER_NATIVE_COMMAND_OR_UNKNOWN_GUROBI_DLL")
        if errors:
            result["reasons"].append("PROCESS_ACCESS_OR_INVENTORY_ERROR")
        sample = memory()
        result["memory"] = sample
        if not admission(sample, extra=0):
            result["reasons"].append("ACTUAL_MEMORY_FLOOR_BREACH")
        result["PASS"] = not result["reasons"]
    except (OSError, ValueError, KeyError) as exc:
        result["reasons"].append("CALLBACK_GATE_EXCEPTION")
        result["errors"].append(dict(error=repr(exc)))
    return result


def source_checks(remote_check=False):
    answer = []
    for name, (root, expected) in ORIGINALS.items():
        head = command(["git", "-C", str(root), "rev-parse", "HEAD"])
        status = command(["git", "-C", str(root), "status", "--porcelain"])
        record = dict(name=name, path=str(root), HEAD=head, expected_HEAD=expected,
                      HEAD_matches=head == expected, clean=not status, git_status=status)
        if remote_check:
            remote = json.loads(command(["gh", "pr", "view", name[2:], "--repo", "BeaverVillage/MobileESS", "--json", "headRefOid,headRefName,url"]))
            record.update(remote=remote, remote_HEAD_matches=remote["headRefOid"] == expected)
        answer.append(record)
    return answer


def audit(phase="PRE_BUILD_READONLY", remote_check=False):
    frozen = create_baseline()
    current_tasks = tasks()
    current_contract = task_contract(current_tasks)
    originals = source_checks(remote_check)
    callback = callbackcheck()
    b1_tasks = [item for item in current_tasks if "B1_Only_May2025_20261012" in item["TaskName"]]
    campaign_tasks = [item for item in current_tasks if item["TaskName"].startswith("MobileESS_V42_May_B2_B3_Autonomous_")]
    automation_files = [item for item in frozen["protected_files"] if item["path"].endswith("automation.toml")]
    automations = []
    for item in automation_files:
        text = Path(item["path"]).read_text(encoding="utf-8")
        status = next(line for line in text.splitlines() if line.startswith("status = ")).split("=", 1)[1].strip().strip('"')
        automations.append(dict(path=item["path"], status=status))
    stop = read(B1_STOP)
    checks = dict(
        original_sources_exact_HEAD_and_clean=all(item["HEAD_matches"] and item["clean"] for item in originals),
        protected_source_result_Native_ledger_bytes_unchanged=not callback["protected_changes"],
        B1_user_stop_receipt_preserved_and_no_dispatch=stop.get("B1_dispatch_authorized") is False and stop.get("B1_retry_authorized") is False,
        current_B1_only_tasks_disabled=bool(b1_tasks) and all(not item["Enabled"] and item["State"] == "Disabled" for item in b1_tasks),
        May_B2_B3_campaign_tasks_disabled=len(campaign_tasks) == 2 and all(not item["Enabled"] and item["State"] == "Disabled" for item in campaign_tasks),
        all_prior_task_enabled_and_action_contracts_unchanged=current_contract == task_contract(frozen["scheduled_tasks"]),
        protected_automations_PAUSED=bool(automations) and all(item["status"] == "PAUSED" for item in automations),
        no_actual_B1_or_other_Heavy_solver_and_memory_floors=callback["PASS"],
    )
    if remote_check:
        checks["original_remote_heads_unchanged"] = all(item["remote_HEAD_matches"] for item in originals)
    return dict(schema="V42_TIME_DECOMPOSITION_READONLY_RESOURCE_SOURCE_AUDIT_V1", phase=phase, **timestamp(),
                PASS=all(checks.values()), checks=checks, originals=originals,
                protected_baseline=digest(BASELINE), callback_gate=callback, scheduled_tasks=current_tasks,
                automations=automations, system_after=callback.get("memory", {}).get("system"),
                B1_all31_complete=False, B1_launches=0, source_process_schedule_automation_mutations=0,
                Full96_model_builds=0, Native_optimize_calls=0,
                is_post_build_native_admission=False,
                note="Fresh read-only gate. Post-build admit(pre,post) additionally reserves max(2 GiB,4× private model growth) above RAM4/Commit6 GiB. No historical monitor State is interpreted as Native optimization.")


def admit(pre_build=None, post_build=None, phase="POST_BUILD_PRE_OPTIMIZE"):
    result = audit(phase)
    if pre_build is None or post_build is None:
        raise ValueError("Admission requires both actual pre-build and post-build memory samples")
    memory_gate = admission_record(pre_build, post_build)
    # Refresh current available RAM/commit after expensive source/process audit.
    fresh = memory()
    memory_gate["fresh_sample_after_source_process_audit"] = fresh
    memory_gate["PASS"] = memory_gate["PASS"] and admission(fresh, memory_gate["estimated_additional_bytes"])
    result["memory_admission"] = memory_gate
    result["checks"]["actual_post_build_growth_reserve_PASS"] = memory_gate["PASS"]
    result["PASS"] = all(result["checks"].values())
    result["is_post_build_native_admission"] = result["PASS"]
    return result


quick_callback_b1_safety = callbackcheck


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DOCS / "PRE_RUN_RESOURCE_SOURCE_AUDIT.json")
    parser.add_argument("--phase", default="PRE_BUILD_READONLY")
    parser.add_argument("--remote-check", action="store_true")
    args = parser.parse_args()
    result = audit(args.phase, args.remote_check)
    write(args.output, result)
    print(json.dumps(dict(output=str(args.output), PASS=result["PASS"], checks=result["checks"], system_after=result["system_after"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
