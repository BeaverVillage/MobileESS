"""Resume-safe rolling four-date V37 campaign supervisor and final reports."""

from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping

import psutil

from .contracts import (
    ARTIFACT_ROOT, BRANCH, CAMPAIGN_LOCK, DATE_MANIFEST, DATE_RESULT_ROOT,
    EXPECTED_DATES, FIREWALL, LOG_ROOT, MAX_PARALLEL_DATES,
    MAX_WORKERS_PER_DATE, PARENT_HEAD, SOURCE_DATA_REPOSITORY,
    STATUS_ROOT, WSL_DISTRIBUTION, WSL_PYTHON,
)
from .manifest import build_date_manifest
from .status import atomic_json, read_json, write_status


MEETING_FIELDS = (
    "date", "PASS_FAIL", "B0_Planning_rho", "B1_Planning_rho", "B2_Planning_rho", "B3_Planning_rho",
    "B0_Fresh_rho", "B1_Fresh_rho", "B2_Fresh_rho", "B3_Fresh_rho",
    "B1_minus_B0_Planning", "B2_minus_B0_Planning", "B3_minus_B0_Planning", "B3_minus_B2_Planning",
    "B1_minus_B0_Fresh", "B2_minus_B0_Fresh", "B3_minus_B0_Fresh", "B3_minus_B2_Fresh",
    "B2_relocations", "B3_relocations", "B2_fallback", "B3_fallback", "wallclock_min",
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True, encoding="utf-8").strip()


def _pid_alive(pid: int) -> bool:
    try:
        process = psutil.Process(int(pid))
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except (psutil.Error, ValueError, TypeError):
        return False


def acquire_lock(repo: Path) -> tuple[bool, dict[str, Any]]:
    path = repo / CAMPAIGN_LOCK
    if path.is_file():
        try:
            existing = read_json(path)
        except (OSError, ValueError, json.JSONDecodeError):
            existing = {}
        if _pid_alive(existing.get("pid", -1)):
            return False, existing
    payload = {
        "artifact_id": "V37_CAMPAIGN_LOCK_V1", "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(), "worktree": str(repo.resolve()),
    }
    atomic_json(path, payload)
    return True, payload


def release_lock(repo: Path) -> None:
    path = repo / CAMPAIGN_LOCK
    try:
        if path.is_file() and int(read_json(path).get("pid", -1)) == os.getpid():
            path.unlink()
    except (OSError, ValueError, json.JSONDecodeError):
        pass


def _windows_to_wsl(path: Path) -> str:
    value = str(path.resolve())
    if len(value) >= 3 and value[1] == ":":
        return f"/mnt/{value[0].lower()}/{value[3:].replace(chr(92), '/')}"
    raise RuntimeError(f"V37_WSL_PATH:{value}")


def materialize_sources(repo: Path, days: list[str]) -> dict[str, Any]:
    output = repo / ARTIFACT_ROOT / "V37_MAY_SOURCE_MATERIALIZATION.json"
    if output.is_file():
        prior = read_json(output)
        if prior.get("status") == "PASS" and set(prior.get("requested_dates", [])) == set(days):
            return prior
    command = [
        "wsl.exe", "-d", WSL_DISTRIBUTION, "--", WSL_PYTHON,
        _windows_to_wsl(repo / "tools/v37/prepare_may_sources.py"),
        "--source-repo", _windows_to_wsl(SOURCE_DATA_REPOSITORY),
        "--dates", *days, "--output", _windows_to_wsl(output),
    ]
    completed = subprocess.run(command, cwd=repo, check=False, text=True)
    if not output.is_file():
        return {
            "status": "FAIL", "requested_dates": days, "runnable_dates": [],
            "failed_dates": {day: [f"SOURCE_MATERIALIZER_EXIT_{completed.returncode}"] for day in days},
        }
    return read_json(output)


def _distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    data = sorted(float(value) for value in values)
    if not data:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "count": len(data), "mean": statistics.fmean(data), "median": statistics.median(data),
        "min": data[0], "max": data[-1],
    }


def _complete_terminal_result(repo: Path, day: str, status: Mapping[str, Any]) -> bool:
    if status.get("status") not in {"PASS", "FAIL"}:
        return False
    path = repo / DATE_RESULT_ROOT / f"{day}.json"
    if not path.is_file():
        return False
    try:
        result = read_json(path)
        readiness = read_json(
            repo
            / "dayahead/artifacts/v37_r3_restore_intended_cuts/"
            "V37_MAY_FINAL_RUN_READINESS.json"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    expected_fingerprint = readiness.get("final_implementation_fingerprint_sha256")
    return (
        result.get("status") in {"PASS", "FAIL"}
        and set(result.get("cases", {})) == {"B0", "B1", "B2", "B3"}
        and bool(expected_fingerprint)
        and result.get("final_implementation_fingerprint_sha256")
        == expected_fingerprint
    )


def _date_wallclock_seconds(repo: Path, day: str, fallback: float) -> float:
    starts: list[datetime] = []
    ends: list[datetime] = []
    for case in ("B0", "B1", "B2", "B3"):
        path = repo / "frozen_artifacts/v36_final_schema" / "MAY_2025_LOCKED_FINAL" / day / case / "inputs/RUN_PROVENANCE.json"
        if not path.is_file():
            continue
        provenance = read_json(path)
        starts.append(datetime.fromisoformat(str(provenance["run_start_timestamp"])))
        ends.append(datetime.fromisoformat(str(provenance["run_end_timestamp"])))
    if len(starts) == len(ends) == 4:
        return max(0.0, (max(ends) - min(starts)).total_seconds())
    return float(fallback)


def _meeting_row(day: str, result: dict[str, Any]) -> dict[str, Any]:
    if "cases" not in result:
        return {field: day if field == "date" else result.get("status", "FAIL") if field == "PASS_FAIL" else "" for field in MEETING_FIELDS}
    c = result["cases"]
    return {
        "date": day, "PASS_FAIL": result["status"],
        **{f"{case}_Planning_rho": c[case]["Planning_rho"] for case in ("B0", "B1", "B2", "B3")},
        **{f"{case}_Fresh_rho": c[case]["Fresh_rho"] for case in ("B0", "B1", "B2", "B3")},
        "B1_minus_B0_Planning": c["B1"]["Planning_rho"] - c["B0"]["Planning_rho"],
        "B2_minus_B0_Planning": c["B2"]["Planning_rho"] - c["B0"]["Planning_rho"],
        "B3_minus_B0_Planning": c["B3"]["Planning_rho"] - c["B0"]["Planning_rho"],
        "B3_minus_B2_Planning": c["B3"]["Planning_rho"] - c["B2"]["Planning_rho"],
        "B1_minus_B0_Fresh": c["B1"]["Fresh_rho"] - c["B0"]["Fresh_rho"],
        "B2_minus_B0_Fresh": c["B2"]["Fresh_rho"] - c["B0"]["Fresh_rho"],
        "B3_minus_B0_Fresh": c["B3"]["Fresh_rho"] - c["B0"]["Fresh_rho"],
        "B3_minus_B2_Fresh": c["B3"]["Fresh_rho"] - c["B2"]["Fresh_rho"],
        "B2_relocations": c["B2"]["relocation_transitions"], "B3_relocations": c["B3"]["relocation_transitions"],
        "B2_fallback": c["B2"]["fallback_count"], "B3_fallback": c["B3"]["fallback_count"],
        "wallclock_min": float(result["wallclock_seconds"]) / 60.0,
    }


def finalize_campaign(repo: Path, started: float, peak_active: int) -> dict[str, Any]:
    manifest = read_json(repo / DATE_MANIFEST)
    results = {
        day: read_json(repo / DATE_RESULT_ROOT / f"{day}.json")
        for day in EXPECTED_DATES if (repo / DATE_RESULT_ROOT / f"{day}.json").is_file()
    }
    for day, result in results.items():
        if "cases" not in result:
            continue
        corrected = dict(result)
        corrected["wallclock_seconds"] = _date_wallclock_seconds(
            repo, day, float(result.get("wallclock_seconds", 0.0)),
        )
        corrected["wallclock_basis"] = "B0_START_TO_B3_END_FROM_PERSISTED_PROVENANCE"
        results[day] = corrected
        atomic_json(repo / DATE_RESULT_ROOT / f"{day}.json", corrected)
    pass_dates = [day for day in EXPECTED_DATES if results.get(day, {}).get("status") == "PASS"]
    fail_dates = [day for day in EXPECTED_DATES if results.get(day, {}).get("status") == "FAIL"]
    missing_dates = [row["date"] for row in manifest["missing_dates"]]
    evaluated = [day for day in EXPECTED_DATES if "cases" in results.get(day, {})]
    evaluated_results = [results[day] for day in evaluated]
    objective_stats = {
        case: _distribution(result["cases"][case]["J"] for result in evaluated_results)
        for case in ("B0", "B1", "B2", "B3")
    }
    planning_stats = {
        case: _distribution(result["cases"][case]["Planning_rho"] for result in evaluated_results)
        for case in ("B0", "B1", "B2", "B3")
    }
    fresh_stats = {
        case: _distribution(result["cases"][case]["Fresh_rho"] for result in evaluated_results)
        for case in ("B0", "B1", "B2", "B3")
    }
    effect_stats = {
        label: {
            metric: _distribution(result["effects"][label][metric] for result in evaluated_results)
            for metric in ("J", "Planning_rho", "Fresh_rho")
        }
        for label in ("B1-B0", "B2-B0", "B3-B0", "B3-B2", "B3-B1")
    }
    physical_dates = [day for day in evaluated if not results[day].get("physical_gates_PASS", False)]
    fresh_non96 = [day for day in evaluated if not results[day].get("Fresh_96_of_96_PASS", False)]
    fallback_dates = [
        day for day in evaluated
        if any(results[day]["cases"][case]["fallback_count"] for case in ("B2", "B3"))
    ]
    relocation_stats = {
        case: _distribution(result["cases"][case]["relocation_transitions"] for result in evaluated_results)
        for case in ("B2", "B3")
    }
    multi_relocation_dates = [
        day for day in evaluated
        if any(
            int(count) > 1
            for case in ("B2", "B3")
            for count in results[day]["cases"][case]["relocations_by_vehicle"].values()
        )
    ]
    relocation_totals = {
        case: sum(int(result["cases"][case]["relocation_transitions"]) for result in evaluated_results)
        for case in ("B2", "B3")
    }
    campaign_log = repo / LOG_ROOT / "campaign.log"
    start_epoch = (
        campaign_log.stat().st_ctime
        if campaign_log.is_file()
        else time.time() - (time.perf_counter() - started)
    )
    total_wallclock = max(0.0, time.time() - start_epoch)
    all_runnable_terminal = bool(manifest["runnable_dates"]) and all(day in results for day in manifest["runnable_dates"])
    all_runnable_pass = all(results.get(day, {}).get("status") == "PASS" for day in manifest["runnable_dates"])
    classification = (
        "V37_MAY_LOCKED_FINAL_EVALUATION_PASS_WITH_FAIL_CLOSED_MISSING_DATA"
        if all_runnable_terminal and all_runnable_pass and missing_dates
        else "V37_MAY_LOCKED_FINAL_EVALUATION_PASS" if all_runnable_terminal and all_runnable_pass
        else "V37_MAY_LOCKED_FINAL_EVALUATION_COMPLETE_WITH_FAILURES"
    )
    summary = {
        "artifact_id": "V37_MAY_FINAL_SUMMARY_V1", "classification": classification,
        "expected_dates": list(EXPECTED_DATES), "runnable_dates": manifest["runnable_dates"],
        "PASS_dates": pass_dates, "FAIL_dates": fail_dates, "missing_data_dates": missing_dates,
        "total_expected_dates": len(EXPECTED_DATES), "runnable_date_count": len(manifest["runnable_dates"]),
        "PASS_count": len(pass_dates), "FAIL_count": len(fail_dates), "missing_data_count": len(missing_dates),
        "evaluated_date_count": len(evaluated),
        "statistics_include_physical_FAIL_dates": True,
        "campaign_started_at_utc": datetime.fromtimestamp(start_epoch, timezone.utc).isoformat(),
        "total_wallclock_seconds": total_wallclock,
        "current_supervisor_wallclock_seconds": time.perf_counter() - started,
        "sum_date_wallclock_seconds": sum(float(result.get("wallclock_seconds", 0.0)) for result in results.values()),
        "parallelism": {"max_parallel_dates": MAX_PARALLEL_DATES, "max_workers_per_date": MAX_WORKERS_PER_DATE, "peak_active_dates": peak_active},
        "objective_statistics": objective_stats, "Planning_rho_statistics": planning_stats,
        "Fresh_rho_statistics": fresh_stats, "effect_distributions": effect_stats,
        "physical_violation_dates": physical_dates, "Fresh_non_96_of_96_dates": fresh_non96,
        "MESS_fallback_dates": fallback_dates, "MESS_relocation_statistics": relocation_stats,
        "MESS_relocation_totals": relocation_totals,
        "MESS_total_physical_relocations": sum(relocation_totals.values()),
        "dates_with_any_vehicle_over_one_relocation": multi_relocation_dates,
        "failures": {
            day: results[day].get("error", "FINAL_PHYSICAL_OR_FRESH_GATE_FAIL")
            for day in fail_dates
        },
        "firewall": FIREWALL,
        "meeting_ready": all_runnable_terminal and len(manifest["runnable_dates"]) == len(EXPECTED_DATES),
    }
    atomic_json(repo / ARTIFACT_ROOT / "V37_MAY_FINAL_SUMMARY.json", summary)
    rows = [_meeting_row(day, results.get(day, {"status": "FAIL"})) for day in EXPECTED_DATES]
    for name in ("V37_MAY_FINAL_SUMMARY.csv", "V37_MAY_MEETING_TABLE.csv"):
        path = repo / ARTIFACT_ROOT / name
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        with temporary.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=MEETING_FIELDS)
            writer.writeheader(); writer.writerows(rows)
        os.replace(temporary, path)
    review = [
        "# V37 May 2025 Locked Final Evaluation", "",
        f"- Classification: `{classification}`",
        f"- Expected / runnable / PASS / FAIL / missing: {len(EXPECTED_DATES)} / {len(manifest['runnable_dates'])} / {len(pass_dates)} / {len(fail_dates)} / {len(missing_dates)}",
        f"- Peak date parallelism: {peak_active} (limit {MAX_PARALLEL_DATES})",
        f"- Workers per date: {MAX_WORKERS_PER_DATE}",
        f"- Physical-violation dates: {physical_dates or 'none'}",
        f"- Fresh non-96/96 dates: {fresh_non96 or 'none'}",
        f"- MESS fallback dates: {fallback_dates or 'none'}",
        f"- MESS physical relocation totals (B2 / B3 / combined): {relocation_totals['B2']} / {relocation_totals['B3']} / {sum(relocation_totals.values())}",
        f"- Dates with any vehicle over one relocation: {multi_relocation_dates or 'none'}", "",
        "May outcomes were not used to tune CENTER, MESS, IDC locations, C1, or any Planning/Fresh decision.",
        "Fresh OpenDSS remained ex-post validation only.",
    ]
    (repo / ARTIFACT_ROOT / "V37_MAY_FINAL_REVIEW.md").write_text("\n".join(review) + "\n", encoding="utf-8")
    return summary


def run_campaign(repo: Path) -> dict[str, Any]:
    started = time.perf_counter()
    if _git(repo, "branch", "--show-current") != BRANCH:
        raise RuntimeError("V37_WRONG_BRANCH")
    if _git(repo, "merge-base", PARENT_HEAD, "HEAD") != PARENT_HEAD:
        raise RuntimeError("V37_PARENT_LINEAGE")
    acquired, lock = acquire_lock(repo)
    if not acquired:
        print(f"CAMPAIGN_ALREADY_RUNNING pid={lock.get('pid')}", flush=True)
        return {"status": "ALREADY_RUNNING", "pid": lock.get("pid")}
    try:
        (repo / STATUS_ROOT).mkdir(parents=True, exist_ok=True)
        (repo / DATE_RESULT_ROOT).mkdir(parents=True, exist_ok=True)
        (repo / LOG_ROOT).mkdir(parents=True, exist_ok=True)
        manifest = build_date_manifest(repo)
        for missing in manifest["missing_dates"]:
            day = missing["date"]
            error = ";".join(missing["reasons"])
            atomic_json(repo / DATE_RESULT_ROOT / f"{day}.json", {
                "artifact_id": "V37_MAY_DATE_RESULT_V1", "date": day, "status": "FAIL",
                "error": error, "missing_data": True, "firewall": FIREWALL,
            })
            write_status(repo / STATUS_ROOT / f"{day}.json", day, "FAIL", 0, None, error=error, extra={"missing_data": True})
        # Reset prior non-PASS engineering failures before source preparation so
        # the live monitor never presents a stale terminal campaign as final.
        for day in manifest["runnable_dates"]:
            status_path = repo / STATUS_ROOT / f"{day}.json"
            prior = read_json(status_path) if status_path.is_file() else {}
            if not _complete_terminal_result(repo, day, prior):
                write_status(status_path, day, "PENDING", 0, "SOURCE_PREPARATION")
        print(f"V37 source materialization: {len(manifest['runnable_dates'])} dates", flush=True)
        source_report = materialize_sources(repo, list(manifest["runnable_dates"]))
        source_runnable = set(source_report.get("runnable_dates", []))
        newly_missing = []
        for day in manifest["runnable_dates"]:
            if day not in source_runnable:
                reasons = source_report.get("failed_dates", {}).get(day, ["SOURCE_MATERIALIZATION_FAIL"])
                newly_missing.append({"date": day, "reasons": reasons})
                atomic_json(repo / DATE_RESULT_ROOT / f"{day}.json", {
                    "artifact_id": "V37_MAY_DATE_RESULT_V1", "date": day, "status": "FAIL",
                    "error": ";".join(reasons), "missing_data": True, "firewall": FIREWALL,
                })
                write_status(repo / STATUS_ROOT / f"{day}.json", day, "FAIL", 0, None, error=";".join(reasons), extra={"missing_data": True})
        if newly_missing:
            manifest["runnable_dates"] = [day for day in manifest["runnable_dates"] if day in source_runnable]
            manifest["missing_dates"].extend(newly_missing)
            manifest["runnable_count"] = len(manifest["runnable_dates"])
            manifest["missing_count"] = len(manifest["missing_dates"])
            atomic_json(repo / DATE_MANIFEST, manifest)

        pending = []
        for day in manifest["runnable_dates"]:
            status_path = repo / STATUS_ROOT / f"{day}.json"
            status = read_json(status_path) if status_path.is_file() else {}
            if _complete_terminal_result(repo, day, status):
                continue
            pending.append(day)
            write_status(status_path, day, "PENDING", int(status.get("completed_units", 0)), "QUEUED")

        active: dict[str, tuple[subprocess.Popen[str], Any]] = {}
        peak_active = 0
        while pending or active:
            while pending and len(active) < MAX_PARALLEL_DATES:
                day = pending.pop(0)
                log_path = repo / LOG_ROOT / f"{day}.log"
                stream = log_path.open("a", encoding="utf-8", newline="\n")
                env = dict(os.environ)
                env.update({"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1"})
                process = subprocess.Popen(
                    [sys.executable, "-m", "dayahead.tools.run_v37_may", "--day", day],
                    cwd=repo, stdout=stream, stderr=subprocess.STDOUT, text=True, env=env,
                )
                active[day] = (process, stream)
                peak_active = max(peak_active, len(active))
                print(f"V37 START {day} pid={process.pid} active={len(active)}", flush=True)
            finished = []
            for day, (process, stream) in active.items():
                code = process.poll()
                if code is None:
                    continue
                stream.close(); finished.append(day)
                print(f"V37 TERMINAL {day} exit={code}", flush=True)
                status_path = repo / STATUS_ROOT / f"{day}.json"
                terminal_status = read_json(status_path) if status_path.is_file() else {}
                if not _complete_terminal_result(repo, day, terminal_status):
                    atomic_json(repo / DATE_RESULT_ROOT / f"{day}.json", {
                        "date": day, "status": "FAIL", "error": f"DATE_PROCESS_EXIT_{code}", "firewall": FIREWALL,
                    })
                    write_status(repo / STATUS_ROOT / f"{day}.json", day, "FAIL", 0, None, error=f"DATE_PROCESS_EXIT_{code}")
            for day in finished:
                del active[day]
            if pending or active:
                time.sleep(2)
        return finalize_campaign(repo, started, peak_active)
    finally:
        release_lock(repo)
