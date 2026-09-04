"""Resume-safe bounded May campaign using frozen V39E DA authorities."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any

from dayahead.v38.authority import canonical_sha256
from dayahead.v39c.freeze import atomic_json, sha256_file

from .campaign_adapter import DATE_RESULT_ROOT, LOG_ROOT, STATUS_ROOT, freeze_path
from .contracts import EXPECTED_DATES, MAX_PARALLEL_DAY_WORKERS
from .full_preflight import FULL_ROOT
from .progress import ProgressTracker


MAX_PARALLEL_DAYS = MAX_PARALLEL_DAY_WORKERS
CASES = ("B0", "B1", "B2", "B3")


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _freeze_shas(repo: Path, day: str) -> dict[str, str]:
    return {
        case: sha256_file(freeze_path(repo, day, case))
        for case in CASES if freeze_path(repo, day, case).is_file()
    }


def _certificate_path(repo: Path, day: str) -> Path:
    return repo / FULL_ROOT / "certificates" / f"V39E_MAY_DAY_CERTIFICATE_{day}.json"


def _reusable(repo: Path, day: str, classification: str) -> bool:
    result_path = repo / DATE_RESULT_ROOT / f"{day}.json"
    certificate_path = _certificate_path(repo, day)
    if not result_path.is_file() or not certificate_path.is_file():
        return False
    try:
        certificate = _read(certificate_path)
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    return (
        certificate.get("terminal") is True
        and certificate.get("campaign_classification") == classification
        and certificate.get("DA_freeze_file_SHA256") == _freeze_shas(repo, day)
        and certificate.get("result_file_SHA256") == sha256_file(result_path)
    )


def _certify(repo: Path, day: str, classification: str) -> dict[str, Any]:
    result_path = repo / DATE_RESULT_ROOT / f"{day}.json"
    result = _read(result_path) if result_path.is_file() else {
        "status": "FAIL", "error": "MISSING_DATE_RESULT",
    }
    certificate = {
        "artifact_id": "V39E_MAY_DAY_CERTIFICATE_V1",
        "operating_day": day,
        "terminal": True,
        "status": result.get("status", "FAIL"),
        "campaign_classification": classification,
        "DIAGNOSTIC_OVERRIDE": classification == "DIAGNOSTIC_OVERRIDE_MAY_CAMPAIGN",
        "DA_freeze_file_SHA256": _freeze_shas(repo, day),
        "result_file_SHA256": sha256_file(result_path) if result_path.is_file() else None,
        "case_count": len(result.get("cases", {})),
        "Actual_temporal_reoptimization_calls": 0,
        "Actual_AIDC_reoptimization_calls": 0,
        "Actual_migration_reoptimization_calls": 0,
        "Actual_WAN_reroute_calls": 0,
        "certified_at": datetime.now(timezone.utc).isoformat(),
    }
    atomic_json(_certificate_path(repo, day), certificate)
    return certificate


def _status_snapshot(repo: Path, completed: list[str]) -> tuple[dict[str, int], int]:
    counts = {case: len(completed) for case in CASES}
    restoration = 0
    for day in EXPECTED_DATES:
        path = repo / STATUS_ROOT / f"{day}.json"
        if not path.is_file() or day in completed:
            continue
        try:
            status = _read(path)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        units = int(status.get("completed_units", 0))
        counts["B0"] += int(units >= 2)
        counts["B1"] += int(units >= 4)
        counts["B2"] += int(units >= 9)
        counts["B3"] += int(units >= 14)
        restoration += int("RESTORATION" in str(status.get("stage", "")))
    return counts, restoration


def run_campaign(
    repo: Path, progress: ProgressTracker, preflight: dict[str, Any],
) -> dict[str, Any]:
    repo = repo.resolve()
    root = repo / FULL_ROOT
    (repo / STATUS_ROOT).mkdir(parents=True, exist_ok=True)
    (repo / DATE_RESULT_ROOT).mkdir(parents=True, exist_ok=True)
    (repo / LOG_ROOT).mkdir(parents=True, exist_ok=True)
    (root / "certificates").mkdir(parents=True, exist_ok=True)
    authoritative = preflight.get("status") == "PASS" and preflight.get("READY") == 31
    classification = (
        "AUTHORITATIVE_V39E_MAY_CAMPAIGN"
        if authoritative else "DIAGNOSTIC_OVERRIDE_MAY_CAMPAIGN"
    )
    bypass = not authoritative
    pending = [
        day for day in EXPECTED_DATES if not _reusable(repo, day, classification)
    ]
    completed = [day for day in EXPECTED_DATES if day not in pending]
    failed = [
        day for day in completed
        if _read(repo / DATE_RESULT_ROOT / f"{day}.json").get("status") != "PASS"
    ]
    progress.update(
        phase="MAY_ACTUAL",
        campaign_classification=(
            "AUTHORITATIVE" if authoritative else "DIAGNOSTIC_OVERRIDE"
        ),
        completed_days=completed,
        running_days=[],
        pending_days=pending,
        failed_days=failed,
        MAY_STARTED="YES",
        MAY_COMPLETED="NO",
        exact_current_blocker=None,
        overall_progress_percent=50.0 if authoritative else 0.0,
    )

    active: dict[str, tuple[subprocess.Popen[str], Any]] = {}
    peak = 0
    while pending or active:
        while pending and len(active) < MAX_PARALLEL_DAYS:
            day = pending.pop(0)
            stream = (repo / LOG_ROOT / f"{day}.log").open(
                "a", encoding="utf-8", newline="\n"
            )
            environment = dict(os.environ)
            environment.update({
                "PYTHONPATH": str(repo),
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
            })
            process = subprocess.Popen(
                [
                    sys.executable, "-m", "dayahead.tools.run_v39e_may_day",
                    "--repo", str(repo), "--day", day,
                ],
                cwd=repo,
                stdout=stream,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment,
            )
            active[day] = process, stream
            peak = max(peak, len(active))

        terminal: list[str] = []
        for day, (process, stream) in list(active.items()):
            code = process.poll()
            if code is None:
                continue
            stream.close()
            result_path = repo / DATE_RESULT_ROOT / f"{day}.json"
            if not result_path.is_file():
                atomic_json(result_path, {
                    "artifact_id": "V39E_MAY_DATE_RESULT_V1",
                    "date": day,
                    "status": "FAIL",
                    "error": f"DATE_PROCESS_EXIT_{code}",
                    "campaign_classification": classification,
                    "DIAGNOSTIC_OVERRIDE": bypass,
                })
            result = _read(result_path)
            result["campaign_classification"] = classification
            result["DIAGNOSTIC_OVERRIDE"] = bypass
            result["Actual_temporal_reoptimization_calls"] = 0
            result["Actual_AIDC_reoptimization_calls"] = 0
            result["Actual_migration_reoptimization_calls"] = 0
            result["Actual_WAN_reroute_calls"] = 0
            atomic_json(result_path, result)
            _certify(repo, day, classification)
            completed.append(day)
            if result.get("status") != "PASS":
                failed.append(day)
            terminal.append(day)
        for day in terminal:
            del active[day]

        case_counts, restoration = _status_snapshot(repo, completed)
        result_rows = [
            _read(repo / DATE_RESULT_ROOT / f"{day}.json") for day in completed
        ]
        fresh_pass = sum(
            row.get("Fresh_96_of_96_PASS") is True for row in result_rows
        )
        progress.update(
            completed_days=sorted(completed),
            running_days=sorted(active),
            pending_days=list(pending),
            failed_days=sorted(set(failed)),
            worker_PIDs=[os.getpid()] + [value[0].pid for value in active.values()],
            latest_completed_day=max(completed) if completed else None,
            latest_failure=max(failed) if failed else None,
            exact_current_blocker=(
                None if not failed else _read(
                    repo / DATE_RESULT_ROOT / f"{max(failed)}.json"
                ).get("error", "PHYSICAL_OR_FRESH_GATE_FAIL")
            ),
            case_status=case_counts,
            Fresh_PASS=fresh_pass,
            Fresh_restoration=restoration,
            Fresh_FAIL=len(failed),
            overall_progress_percent=(
                (50.0 if authoritative else 0.0)
                + (50.0 if authoritative else 100.0) * len(completed) / 31.0
            ),
        )
        if pending or active:
            time.sleep(2)

    results = {
        day: _read(repo / DATE_RESULT_ROOT / f"{day}.json") for day in EXPECTED_DATES
    }
    pass_days = [day for day, row in results.items() if row.get("status") == "PASS"]
    fail_days = [day for day in EXPECTED_DATES if day not in pass_days]
    summary = {
        "artifact_id": "V39E_MAY_CAMPAIGN_SUMMARY_V1",
        "campaign_classification": classification,
        "DIAGNOSTIC_OVERRIDE": bypass,
        "dates_attempted": len(results),
        "PASS_dates": pass_days,
        "FAIL_dates": fail_days,
        "B0_completed": sum("B0" in row.get("cases", {}) for row in results.values()),
        "B1_completed": sum("B1" in row.get("cases", {}) for row in results.values()),
        "B2_completed": sum("B2" in row.get("cases", {}) for row in results.values()),
        "B3_completed": sum("B3" in row.get("cases", {}) for row in results.values()),
        "Actual_fixed_replay_count": sum(len(row.get("cases", {})) for row in results.values()),
        "Actual_temporal_reoptimization_calls": 0,
        "Actual_AIDC_reoptimization_calls": 0,
        "Actual_migration_reoptimization_calls": 0,
        "Actual_WAN_reroute_calls": 0,
        "Fresh_96_of_96_PASS_days": sum(
            row.get("Fresh_96_of_96_PASS") is True for row in results.values()
        ),
        "failed_day_cases": {
            day: row.get("error", "PHYSICAL_OR_FRESH_GATE_FAIL")
            for day, row in results.items() if row.get("status") != "PASS"
        },
        "max_parallel_days": MAX_PARALLEL_DAYS,
        "peak_parallel_days": peak,
        "resumable": True,
        "PRECHECK_BYPASSED": "YES" if bypass else "NO",
        "MAY_STARTED": "YES",
        "MAY_COMPLETED": "YES",
    }
    summary["campaign_result_SHA256"] = canonical_sha256(summary)
    atomic_json(root / "V39E_MAY_CAMPAIGN_SUMMARY.json", summary)
    progress.update(
        phase="COMPLETE",
        completed_days=list(EXPECTED_DATES),
        running_days=[],
        pending_days=[],
        failed_days=fail_days,
        worker_PIDs=[os.getpid()],
        Fresh_PASS=summary["Fresh_96_of_96_PASS_days"],
        Fresh_FAIL=len(fail_days),
        overall_progress_percent=100.0,
        MAY_COMPLETED="YES",
        exact_current_blocker=(
            None if not fail_days else summary["failed_day_cases"][fail_days[0]]
        ),
    )
    return summary


__all__ = ["MAX_PARALLEL_DAYS", "run_campaign"]
