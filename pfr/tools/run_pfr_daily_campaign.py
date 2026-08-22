"""Run fixed-AEST January dates as independent canonical-PRE episodes."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence


ISSUES_PER_DAY = 288
METHOD_COUNT = 8


@dataclass(frozen=True)
class DaySpec:
    day_index: int
    calendar_date: str
    start_issue: int
    candidate_id: str


def day_specs(start_day: int, end_day: int) -> tuple[DaySpec, ...]:
    if not 1 <= start_day <= end_day <= 31:
        raise ValueError("day range must satisfy 1 <= start <= end <= 31")
    epoch = date(2025, 1, 1)
    return tuple(
        DaySpec(
            day_index=day,
            calendar_date=str(epoch + timedelta(days=day - 1)),
            start_issue=(day - 1) * ISSUES_PER_DAY,
            candidate_id=f"JAN2025_DAY{day:02d}",
        )
        for day in range(start_day, end_day + 1)
    )


def summary_passes(summary: Mapping[str, Any]) -> bool:
    return bool(
        summary.get("status") == "PASS"
        and summary.get("expected_commit_markers") == ISSUES_PER_DAY * METHOD_COUNT
        and summary.get("all_actual_gurobi") is True
        and summary.get("all_fresh_exact_opendss") is True
        and summary.get("all_state_chains_complete") is True
        and summary.get("future_actual_used") is False
    )


def run_day(
    spec: DaySpec,
    *,
    repo: Path,
    output: Path,
    common: Sequence[str],
    capture_day_logs: bool,
    reuse_passed_days: bool,
) -> Mapping[str, Any]:
    day_root = output / spec.calendar_date
    summary_path = day_root / "MATRIX_SUMMARY.json"
    if reuse_passed_days and summary_path.is_file():
        try:
            existing = json.loads(summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if summary_passes(existing):
            return {
                "calendar_date": spec.calendar_date,
                "start_issue": spec.start_issue,
                "status": "PASS",
                "artifact": str(day_root),
                "reused_existing_pass": True,
            }

    day_root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(repo / "pfr/tools/run_pfr_matrix.py"),
        *common,
        "--candidate-id", spec.candidate_id,
        "--start-issue", str(spec.start_issue),
        "--output", str(day_root),
    ]
    if capture_day_logs:
        with (day_root / "DAY_RUN.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(
                command, cwd=repo, check=False, stdout=log,
                stderr=subprocess.STDOUT, text=True,
            )
    else:
        completed = subprocess.run(command, cwd=repo, check=False)

    if completed.returncode != 0 or not summary_path.is_file():
        return {
            "calendar_date": spec.calendar_date,
            "start_issue": spec.start_issue,
            "status": "FAIL_CLOSED",
            "returncode": completed.returncode,
            "artifact": str(day_root),
        }
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    return {
        "calendar_date": spec.calendar_date,
        "start_issue": spec.start_issue,
        "status": "PASS" if summary_passes(summary) else "FAIL_CLOSED",
        "artifact": str(day_root),
        "reused_existing_pass": False,
    }


def campaign_payload(
    *,
    start_day: int,
    end_day: int,
    day_workers: int,
    summaries: Sequence[Mapping[str, Any]],
    final: bool,
) -> Mapping[str, Any]:
    expected_days = end_day - start_day + 1
    complete = len(summaries) == expected_days
    all_pass = complete and all(row["status"] == "PASS" for row in summaries)
    any_fail = any(row["status"] == "FAIL_CLOSED" for row in summaries)
    status = "PASS" if all_pass else ("FAIL_CLOSED" if final or any_fail else "IN_PROGRESS")
    return {
        "schema_version": "PFR_JAN2025_INDEPENDENT_DAILY_CAMPAIGN_RUN_V13_2_1",
        "status": status,
        "calendar_timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "start_day": start_day,
        "end_day": end_day,
        "day_process_workers": day_workers,
        "gurobi_threads_per_process": int(os.environ.get("PFR_GUROBI_THREADS", "1")),
        "independent_daily_cold_start": True,
        "cross_day_endogenous_state_carryover": False,
        "controller_burn_in_steps": 0,
        "issues_per_method_per_day": ISSUES_PER_DAY,
        "methods_per_day": METHOD_COUNT,
        "daily_runs": sorted(summaries, key=lambda row: str(row["calendar_date"])),
    }


def write_campaign(output: Path, payload: Mapping[str, Any]) -> None:
    temporary = output / "CAMPAIGN_SUMMARY.json.tmp"
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output / "CAMPAIGN_SUMMARY.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--start-day", type=int, required=True)
    parser.add_argument("--end-day", type=int, required=True)
    parser.add_argument("--day-workers", type=int, default=1)
    parser.add_argument("--capture-day-logs", action="store_true")
    parser.add_argument("--no-reuse-passed-days", action="store_true")
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--exact-package-root", type=Path, required=True)
    parser.add_argument("--authority-package-root", type=Path, required=True)
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument("--initial-state", type=Path, required=True)
    parser.add_argument("--independent-jobs", type=Path, required=True)
    parser.add_argument("--canonical-jobs", type=Path, required=True)
    parser.add_argument("--power-curve", type=Path, required=True)
    parser.add_argument("--mobility-root", type=Path, action="append", required=True)
    parser.add_argument("--route-catalog", type=Path, required=True)
    parser.add_argument("--mobility-template-bank", type=Path, required=True)
    parser.add_argument("--workload-uncertainty", type=Path, required=True)
    parser.add_argument("--factorized-uncertainty", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.day_workers <= 31:
        parser.error("--day-workers must be in [1, 31]")

    specs = day_specs(args.start_day, args.end_day)
    args.output.mkdir(parents=True, exist_ok=True)
    common: list[str] = [
        "--repo", str(args.repo),
        "--count", str(ISSUES_PER_DAY),
        "--shared-root", str(args.shared_root),
        "--exact-package-root", str(args.exact_package_root),
        "--authority-package-root", str(args.authority_package_root),
        "--primary-root", str(args.primary_root),
        "--initial-state", str(args.initial_state),
        "--independent-jobs", str(args.independent_jobs),
        "--canonical-jobs", str(args.canonical_jobs),
        "--power-curve", str(args.power_curve),
        "--route-catalog", str(args.route_catalog),
        "--mobility-template-bank", str(args.mobility_template_bank),
        "--workload-uncertainty", str(args.workload_uncertainty),
        "--factorized-uncertainty", str(args.factorized_uncertainty),
    ]
    for mobility_root in args.mobility_root:
        common.extend(("--mobility-root", str(mobility_root)))

    summaries: list[Mapping[str, Any]] = []
    with ThreadPoolExecutor(max_workers=args.day_workers) as pool:
        futures: dict[Future[Mapping[str, Any]], DaySpec] = {
            pool.submit(
                run_day,
                spec,
                repo=args.repo,
                output=args.output,
                common=common,
                capture_day_logs=args.capture_day_logs,
                reuse_passed_days=not args.no_reuse_passed_days,
            ): spec
            for spec in specs
        }
        for future in as_completed(futures):
            row = future.result()
            summaries.append(row)
            write_campaign(
                args.output,
                campaign_payload(
                    start_day=args.start_day,
                    end_day=args.end_day,
                    day_workers=args.day_workers,
                    summaries=summaries,
                    final=False,
                ),
            )
            done = len(summaries)
            print(json.dumps({
                "day": row["calendar_date"],
                "completed_days": done,
                "total_days": len(specs),
                "percent": round(100.0 * done / len(specs), 1),
                "status": row["status"],
            }), flush=True)

    campaign = campaign_payload(
        start_day=args.start_day,
        end_day=args.end_day,
        day_workers=args.day_workers,
        summaries=summaries,
        final=True,
    )
    write_campaign(args.output, campaign)
    print(json.dumps({"status": campaign["status"], "days": len(summaries), "output": str(args.output)}))
    if campaign["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
