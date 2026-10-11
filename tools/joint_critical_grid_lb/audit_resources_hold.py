"""Read-only Windows resource/HOLD inventory for the Joint16 LB pilot.

This helper never builds a model, imports Gurobi, dispatches a campaign, or
changes a process, schedule, automation, source checkout, or prior result.
Run again immediately before optimize; a pre-build sample is not admission.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta

import psutil

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from v42_svr11.resources import snapshot

GIB = 1024**3
PR207 = "497609b46faa14ea7e32a9483a333ab32fd264ef"
PR209 = "9383a99f1bdcabbd49c79b3ad9f9ee36d523868a"
ORIGINALS = {
    "PR207_Source18r": (Path(r"D:\v42_svr11_epoch18r_20261011"), PR207),
    "PR209_physical_global_lb": (
        Path(r"D:\ChatGPT\Mobile ESS 2\work\source18r-physical-global-lb-pilot"), PR209
    ),
}
PR209_DOCS = ORIGINALS["PR209_physical_global_lb"][0] / "docs/v42_physical_global_lb_pilot"


def digest(path):
    p = Path(path)
    data = p.read_bytes()
    return dict(path=str(p), bytes=len(data), sha256=hashlib.sha256(data).hexdigest())


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=True)
    return result.stdout.strip()


def inventory():
    processes, errors = [], []
    for p in psutil.process_iter(["pid", "name", "create_time", "cmdline"]):
        name = (p.info["name"] or "").lower()
        if not (name.startswith("python") or "gurobi" in name) or p.pid == psutil.Process().pid:
            continue
        try:
            mem = p.memory_info()
            modules = sorted({m.path for m in p.memory_maps(grouped=True) if "gurobi" in m.path.lower()})
            processes.append(dict(
                PID=p.pid, create_time=p.create_time(), name=p.name(), command=p.cmdline(),
                cwd=p.cwd(), status=p.status(), CPU_seconds=sum(p.cpu_times()[:2]),
                RSS_bytes=mem.rss, Peak_RSS_bytes=getattr(mem, "peak_wset", None),
                Private_Commit_bytes=getattr(mem, "private", None),
                gurobi_loaded_modules=modules,
                descendants=[dict(PID=c.pid, create_time=c.create_time(), command=c.cmdline())
                             for c in p.children(recursive=True)],
            ))
        except (psutil.Error, OSError) as exc:
            errors.append(dict(PID=p.pid, error=repr(exc)))
    return processes, errors


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, default=REPO / "docs/v42_joint_critical_grid_lb_pilot/PRE_RUN_RESOURCE_HOLD.json")
    ap.add_argument("--phase", default="PRE_BUILD_READONLY")
    ap.add_argument("--observation-seconds", type=float, default=2.0)
    ap.add_argument("--estimated-additional-gib", type=float, default=2.0)
    args = ap.parse_args()
    assert 0 <= args.observation_seconds <= 10
    assert args.estimated_additional_gib >= 0
    before, errors_before = inventory()
    system_before = snapshot()
    wall_before = time.monotonic()
    time.sleep(args.observation_seconds)
    after, errors_after = inventory()
    system_after = snapshot()
    elapsed = time.monotonic() - wall_before
    by_pid = {p["PID"]: p for p in before}
    for p in after:
        previous = by_pid.get(p["PID"])
        p["CPU_delta_seconds"] = (p["CPU_seconds"] - previous["CPU_seconds"]
                                  if previous and previous["create_time"] == p["create_time"] else None)
    old = json.loads((PR209_DOCS / "HOLD_READONLY.json").read_text(encoding="utf-8"))
    baseline_by_pid = {p["expected_PID"]: p for p in old["controllers"]}
    by_pid_after = {p["PID"]: p for p in after}
    controllers = []
    for pid, baseline in baseline_by_pid.items():
        p = by_pid_after.get(pid)
        identity = (bool(p) and p["create_time"] == baseline["current"]["create_time"]
                    and p["command"] == baseline["current"]["command"])
        computational_descendants = ([c for c in p["descendants"]
                                      if not c["command"] or not c["command"][0].lower().endswith("conhost.exe")]
                                     if p else None)
        controllers.append(dict(
            epoch=baseline["epoch"], expected_PID=pid, current=p,
            matches_PR209_baseline_identity=identity,
            descendants_empty=bool(p) and not p["descendants"],
            computational_descendants=computational_descendants,
            computational_descendants_empty=bool(p) and not computational_descendants,
            observed_CPU_delta_seconds=p["CPU_delta_seconds"] if p else None,
            note="Status labels may transiently toggle; tiny CPU ticks alone are not a native solve. Existing conhost.exe console children are reported but are not computational workers.",
        ))
    worker_tokens = ("v42_svr11.worker", "gurobi_cl", "gurobi.sh", "run_joint", "run_native")
    heavy = [p for p in after if p["gurobi_loaded_modules"]
             or any(t in " ".join(p["command"]).lower() for t in worker_tokens)]
    # Conservative classification: any other process loading Gurobi is disallowed.
    # The audit itself excludes its PID and does not load Gurobi.
    originals = []
    for name, (root, expected) in ORIGINALS.items():
        head = command(["git", "-C", str(root), "rev-parse", "HEAD"])
        status = command(["git", "-C", str(root), "status", "--porcelain"])
        originals.append(dict(name=name, path=str(root), HEAD=head, expected_HEAD=expected,
                              HEAD_matches=head == expected, clean=not status, git_status=status))
    holds = []
    for baseline in old["hold_markers"]:
        p = Path(baseline["path"])
        record = digest(p)
        record.update(content=json.loads(p.read_text(encoding="utf-8")),
                      sha256_matches_PR209=record["sha256"] == baseline["sha256"])
        holds.append(record)
    automations = []
    for baseline in old["automations"]:
        p = Path(baseline["path"])
        record = digest(p)
        status_line = next(line for line in p.read_text(encoding="utf-8").splitlines() if line.startswith("status = "))
        record.update(status=status_line.split("=", 1)[1].strip().strip('"'),
                      sha256_matches_PR209=record["sha256"] == baseline["sha256"])
        automations.append(record)
    shell = shutil.which("pwsh") or shutil.which("powershell")
    script = "Get-ScheduledTask -TaskName 'MobileESS_V42_May_B2_B3_Autonomous_*' | ForEach-Object { [PSCustomObject]@{TaskName=$_.TaskName;TaskPath=$_.TaskPath;State=$_.State.ToString();Enabled=$_.Settings.Enabled;Actions=@($_.Actions | Select-Object Execute,Arguments,WorkingDirectory)} } | ConvertTo-Json -Depth 5"
    tasks = json.loads(command([shell, "-NoProfile", "-Command", script]))
    if isinstance(tasks, dict):
        tasks = [tasks]
    floors = dict(RAM_available_min_bytes=4 * GIB, Commit_available_min_bytes=6 * GIB)
    estimated = int(args.estimated_additional_gib * GIB)
    memory_floor_pass = all(m["RAM_available"] >= floors["RAM_available_min_bytes"]
                            and m["Commit_available"] >= floors["Commit_available_min_bytes"]
                            for m in (system_before, system_after))
    headroom_pass = all(m["RAM_available"] >= floors["RAM_available_min_bytes"] + estimated
                        and m["Commit_available"] >= floors["Commit_available_min_bytes"] + estimated
                        for m in (system_before, system_after))
    checks = dict(
        original_PR207_PR209_HEAD_and_clean=all(p["HEAD_matches"] and p["clean"] for p in originals),
        seven_controller_identities_match=len(controllers) == 7 and all(p["matches_PR209_baseline_identity"] for p in controllers),
        held_controller_computational_descendants_empty=all(p["computational_descendants_empty"] for p in controllers),
        no_other_observed_Gurobi_or_native_worker=not heavy,
        no_process_scan_errors=not errors_before and not errors_after,
        held_markers_byte_identical_to_PR209=all(p["sha256_matches_PR209"] for p in holds),
        two_schedules_disabled=len(tasks) == 2 and all(p["State"] == "Disabled" and not p["Enabled"] for p in tasks),
        relevant_automations_PAUSED_and_unchanged=all(p["status"] == "PAUSED" and p["sha256_matches_PR209"] for p in automations),
        current_sample_memory_floors_PASS=memory_floor_pass,
        current_sample_estimated_growth_headroom_PASS=headroom_pass,
    )
    now = datetime.now(timezone.utc)
    result = dict(
        schema="V42_JOINT_CRITICAL_GRID_READONLY_RESOURCE_HOLD_V1",
        phase=args.phase, observed_UTC=now.isoformat(), observed_Asia_Seoul=now.astimezone(timezone(timedelta(hours=9))).isoformat(),
        PASS=all(checks.values()), checks=checks, observation_seconds=elapsed,
        system_before=system_before, system_after=system_after, memory_floors=floors,
        estimated_additional_native_growth_bytes=estimated,
        recommendation="After native matrix readback, refresh actual RAM/commit; retain 4 GiB RAM and 6 GiB commit floors plus an independently justified additional-growth reserve. A 2 GiB Gurobi SoftMemLimit can support this reserve but does not replace RSS/private/system monitoring. Stop normally if a floor is crossed.",
        is_post_build_native_admission=args.phase == "POST_BUILD_PRE_OPTIMIZE" and all(checks.values()),
        originals=originals, controllers=controllers, python_and_Gurobi_processes=after,
        other_heavy_candidates=heavy, process_scan_errors=errors_before + errors_after,
        scheduled_tasks=tasks, automations=automations, hold_markers=holds,
        PR209_HOLD_baseline=digest(PR209_DOCS / "HOLD_READONLY.json"),
        state_mutations=0, model_builds=0, Native_optimize_calls=0,
        scope="Read-only observation, with only a new research-branch evidence file written. A PRE_BUILD sample cannot authorize optimize.",
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(output=str(args.output), PASS=result["PASS"], checks=checks, system_after=system_after), ensure_ascii=False))


if __name__ == "__main__":
    main()
