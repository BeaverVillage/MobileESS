"""Read-only Windows resource and scientific-source preservation inventory.

Never builds a solver model, imports Gurobi, changes processes, schedules,
automations, campaign markers, or any predecessor checkout. A pre-build sample
does not authorize optimization. The caller must refresh admission after build.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from v42_svr11.resources import snapshot

GIB = 1024 ** 3
PR207 = "497609b46faa14ea7e32a9483a333ab32fd264ef"
PR209 = "9383a99f1bdcabbd49c79b3ad9f9ee36d523868a"
PR210 = "6a8fd44f59f1f461c60d2d14f5f5be605e4ed640"
ORIGINALS = {
    "PR207_Source18r": (Path(r"D:\v42_svr11_epoch18r_20261011"), PR207),
    "PR209_physical_global_lb": (Path(r"D:\ChatGPT\Mobile ESS 2\work\source18r-physical-global-lb-pilot"), PR209),
    "PR210_Joint16": (Path(r"D:\v42_joint_critical_grid_lb_20261012"), PR210),
}
PR209_DOCS = ORIGINALS["PR209_physical_global_lb"][0] / "docs/v42_physical_global_lb_pilot"
NATIVE_TOKENS = (
    "v42_svr11.worker", "gurobi_cl", "gurobi.sh", "run_joint", "run_native",
    "native_worker", "--mode native", "--mode solve", "--phase native",
)


def memory():
    info = psutil.Process().memory_info()
    return dict(time=time.time(), system=snapshot(), RSS_bytes=info.rss,
                Peak_RSS_bytes=getattr(info, "peak_wset", info.rss),
                Private_Commit_bytes=getattr(info, "private", info.rss),
                Peak_Private_Commit_bytes=getattr(info, "peak_pagefile", None))


def admission(sample, extra=2 * GIB):
    """PR210 admission contract; callback uses extra=0 to enforce floors."""
    if extra < 0:
        raise ValueError("Reserve cannot be negative")
    system = sample["system"]
    return (system["RAM_available"] >= 4 * GIB + extra
            and system["Commit_available"] >= 6 * GIB + extra)


def growth_reserve(pre_build, post_build):
    growth = max(0, post_build["Private_Commit_bytes"] - pre_build["Private_Commit_bytes"])
    return max(2 * GIB, 4 * growth)


def admission_record(pre_build, post_build):
    extra = growth_reserve(pre_build, post_build)
    return dict(PASS=admission(post_build, extra), sample=post_build,
                RAM_reserve_bytes=4 * GIB, commit_reserve_bytes=6 * GIB,
                estimated_additional_bytes=extra,
                observed_model_build_private_growth_bytes=max(0, post_build["Private_Commit_bytes"] - pre_build["Private_Commit_bytes"]),
                estimation_basis="Model already resident; reserve max(2 GiB, 4x observed model-build private growth). Callback enforces actual 4 GiB RAM and 6 GiB commit floors.")


def digest(path):
    path = Path(path)
    h = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while data := source.read(1024 * 1024):
            h.update(data)
            size += len(data)
    return dict(path=str(path), bytes=size, sha256=h.hexdigest())


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=True)
    return result.stdout.strip()


def inventory():
    processes, errors = [], []
    for process in psutil.process_iter(["pid", "name", "create_time", "cmdline"]):
        name = (process.info["name"] or "").lower()
        if not (name.startswith("python") or "gurobi" in name) or process.pid == psutil.Process().pid:
            continue
        try:
            info = process.memory_info()
            modules = sorted({item.path for item in process.memory_maps(grouped=True)
                              if "gurobi" in item.path.lower()})
            processes.append(dict(
                PID=process.pid, create_time=process.create_time(), name=process.name(),
                command=process.cmdline(), cwd=process.cwd(), status=process.status(),
                CPU_seconds=sum(process.cpu_times()[:2]), RSS_bytes=info.rss,
                Peak_RSS_bytes=getattr(info, "peak_wset", None),
                Private_Commit_bytes=getattr(info, "private", None),
                gurobi_loaded_modules=modules,
                descendants=[dict(PID=child.pid, create_time=child.create_time(), command=child.cmdline())
                             for child in process.children(recursive=True)],
            ))
        except (psutil.Error, OSError) as exc:
            errors.append(dict(PID=process.pid, error=repr(exc)))
    return processes, errors


def heavy_candidates(processes):
    return [process for process in processes
            if process["gurobi_loaded_modules"]
            or any(token in " ".join(process["command"]).lower() for token in NATIVE_TOKENS)]


def readonly_audit(phase="PRE_BUILD_READONLY", observation_seconds=2.0, estimated_additional_bytes=2 * GIB,
                   remote_check=False):
    if not 0 <= observation_seconds <= 10 or estimated_additional_bytes < 0:
        raise ValueError("Invalid observation duration or growth reserve")
    before, errors_before = inventory()
    system_before = snapshot()
    start = time.monotonic()
    time.sleep(observation_seconds)
    after, errors_after = inventory()
    system_after = snapshot()
    elapsed = time.monotonic() - start
    by_pid = {process["PID"]: process for process in before}
    for process in after:
        previous = by_pid.get(process["PID"])
        process["CPU_delta_seconds"] = (process["CPU_seconds"] - previous["CPU_seconds"]
                                          if previous and previous["create_time"] == process["create_time"] else None)
    baseline = json.loads((PR209_DOCS / "HOLD_READONLY.json").read_text(encoding="utf-8"))
    by_pid_after = {process["PID"]: process for process in after}
    controllers = []
    for original in baseline["controllers"]:
        pid = original["expected_PID"]
        process = by_pid_after.get(pid)
        matches = bool(process) and process["create_time"] == original["current"]["create_time"] and process["command"] == original["current"]["command"]
        computational = ([child for child in process["descendants"]
                          if not child["command"] or not child["command"][0].lower().endswith("conhost.exe")]
                         if process else None)
        controllers.append(dict(epoch=original["epoch"], expected_PID=pid, current=process,
                                matches_PR209_baseline_identity=matches,
                                computational_descendants=computational,
                                computational_descendants_empty=bool(process) and not computational,
                                observed_CPU_delta_seconds=process["CPU_delta_seconds"] if process else None,
                                note="Status labels can transiently toggle. Existing conhost console children are recorded and are not computational workers. A tiny CPU tick alone is not a Native solve."))
    originals = []
    for name, (root, expected) in ORIGINALS.items():
        head = command(["git", "-C", str(root), "rev-parse", "HEAD"])
        status = command(["git", "-C", str(root), "status", "--porcelain"])
        record = dict(name=name, path=str(root), HEAD=head, expected_HEAD=expected,
                      HEAD_matches=head == expected, clean=not status, git_status=status)
        if remote_check:
            number = name.split("_", 1)[0][2:]
            remote = json.loads(command(["gh", "pr", "view", number, "--repo", "BeaverVillage/MobileESS", "--json", "headRefOid,headRefName,baseRefName,isDraft,url"]))
            record.update(remote=remote, remote_HEAD_matches=remote["headRefOid"] == expected)
        originals.append(record)
    holds = []
    for original in baseline["hold_markers"]:
        path = Path(original["path"])
        record = digest(path)
        record.update(content=json.loads(path.read_text(encoding="utf-8")),
                      sha256_matches_PR209=record["sha256"] == original["sha256"])
        holds.append(record)
    automations = []
    for original in baseline["automations"]:
        path = Path(original["path"])
        record = digest(path)
        line = next(line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("status = "))
        record.update(status=line.split("=", 1)[1].strip().strip('"'),
                      sha256_matches_PR209=record["sha256"] == original["sha256"])
        automations.append(record)
    shell = shutil.which("pwsh") or shutil.which("powershell")
    task_script = "Get-ScheduledTask -TaskName 'MobileESS_V42_May_B2_B3_Autonomous_*' | ForEach-Object { [PSCustomObject]@{TaskName=$_.TaskName;TaskPath=$_.TaskPath;State=$_.State.ToString();Enabled=$_.Settings.Enabled;Actions=@($_.Actions | Select-Object Execute,Arguments,WorkingDirectory)} } | ConvertTo-Json -Depth 5"
    tasks = json.loads(command([shell, "-NoProfile", "-Command", task_script]))
    if isinstance(tasks, dict):
        tasks = [tasks]
    floors = dict(RAM_available_min_bytes=4 * GIB, Commit_available_min_bytes=6 * GIB)
    memory_pass = all(sample["RAM_available"] >= 4 * GIB and sample["Commit_available"] >= 6 * GIB
                      for sample in (system_before, system_after))
    growth_pass = all(sample["RAM_available"] >= 4 * GIB + estimated_additional_bytes
                      and sample["Commit_available"] >= 6 * GIB + estimated_additional_bytes
                      for sample in (system_before, system_after))
    heavy = heavy_candidates(after)
    checks = dict(original_PR207_PR209_PR210_HEAD_and_clean=all(record["HEAD_matches"] and record["clean"] for record in originals),
                  seven_controller_identities_match=len(controllers) == 7 and all(record["matches_PR209_baseline_identity"] for record in controllers),
                  held_controller_computational_descendants_empty=all(record["computational_descendants_empty"] for record in controllers),
                  no_other_observed_Gurobi_or_native_worker=not heavy,
                  no_process_scan_errors=not errors_before and not errors_after,
                  held_markers_byte_identical_to_PR209=all(record["sha256_matches_PR209"] for record in holds),
                  two_schedules_disabled=len(tasks) == 2 and all(task["State"] == "Disabled" and not task["Enabled"] for task in tasks),
                  relevant_automations_PAUSED_and_unchanged=all(record["status"] == "PAUSED" and record["sha256_matches_PR209"] for record in automations),
                  current_sample_memory_floors_PASS=memory_pass,
                  current_sample_estimated_growth_headroom_PASS=growth_pass)
    if remote_check:
        checks["remote_PR207_PR209_PR210_HEAD_matches"] = all(record["remote_HEAD_matches"] for record in originals)
    now = datetime.now(timezone.utc)
    return dict(schema="V42_CRITICAL_GRID_CG_READONLY_RESOURCE_HOLD_V1", phase=phase,
                observed_UTC=now.isoformat(), observed_Asia_Seoul=now.astimezone(timezone(timedelta(hours=9))).isoformat(),
                PASS=all(checks.values()), checks=checks, observation_seconds=elapsed,
                system_before=system_before, system_after=system_after, memory_floors=floors,
                estimated_additional_native_growth_bytes=estimated_additional_bytes,
                is_post_build_native_admission=phase == "POST_BUILD_PRE_OPTIMIZE" and all(checks.values()),
                recommendation="Refresh actual RAM/commit after native readback. Reserve max(2 GiB, 4x observed model-build private growth), above the 4 GiB RAM and 6 GiB commit floors; normally terminate on a floor breach.",
                originals=originals, controllers=controllers, python_and_Gurobi_processes=after,
                other_heavy_candidates=heavy, process_scan_errors=errors_before + errors_after,
                scheduled_tasks=tasks, automations=automations, hold_markers=holds,
                PR209_HOLD_baseline=digest(PR209_DOCS / "HOLD_READONLY.json"),
                state_mutations=0, model_builds=0, Native_optimize_calls=0,
                scope="Read-only observation. Only new research-branch evidence is written. PRE_BUILD does not authorize Optimize.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=REPO / "docs/v42_critical_grid_cg/PRE_RUN_RESOURCE_HOLD.json")
    parser.add_argument("--phase", default="PRE_BUILD_READONLY")
    parser.add_argument("--observation-seconds", type=float, default=2.0)
    parser.add_argument("--estimated-additional-gib", type=float, default=2.0)
    parser.add_argument("--remote-check", action="store_true")
    args = parser.parse_args()
    result = readonly_audit(args.phase, args.observation_seconds, int(args.estimated_additional_gib * GIB), args.remote_check)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(args.output), PASS=result["PASS"], checks=result["checks"], system_after=result["system_after"]), ensure_ascii=False))


if __name__ == "__main__":
    main()
