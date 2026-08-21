"""Run fixed-AEST January dates as independent canonical-PRE episodes."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence


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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--start-day", type=int, required=True)
    parser.add_argument("--end-day", type=int, required=True)
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

    args.output.mkdir(parents=True, exist_ok=True)
    summaries = []
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

    for spec in day_specs(args.start_day, args.end_day):
        day_root = args.output / spec.calendar_date
        command = [
            sys.executable,
            str(args.repo / "pfr/tools/run_pfr_matrix.py"),
            *common,
            "--candidate-id", spec.candidate_id,
            "--start-issue", str(spec.start_issue),
            "--output", str(day_root),
        ]
        completed = subprocess.run(command, cwd=args.repo, check=False)
        summary_path = day_root / "MATRIX_SUMMARY.json"
        if completed.returncode != 0 or not summary_path.is_file():
            summaries.append({
                "calendar_date": spec.calendar_date,
                "start_issue": spec.start_issue,
                "status": "FAIL_CLOSED",
                "returncode": completed.returncode,
            })
            break
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        passed = (
            summary.get("status") == "PASS"
            and summary.get("expected_commit_markers") == ISSUES_PER_DAY * METHOD_COUNT
            and summary.get("all_actual_gurobi") is True
            and summary.get("all_fresh_exact_opendss") is True
            and summary.get("all_state_chains_complete") is True
            and summary.get("future_actual_used") is False
        )
        summaries.append({
            "calendar_date": spec.calendar_date,
            "start_issue": spec.start_issue,
            "status": "PASS" if passed else "FAIL_CLOSED",
            "artifact": str(day_root),
        })
        if not passed:
            break

    expected_days = args.end_day - args.start_day + 1
    status = "PASS" if len(summaries) == expected_days and all(row["status"] == "PASS" for row in summaries) else "FAIL_CLOSED"
    campaign = {
        "schema_version": "PFR_JAN2025_INDEPENDENT_DAILY_CAMPAIGN_RUN_V13_2",
        "status": status,
        "calendar_timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "start_day": args.start_day,
        "end_day": args.end_day,
        "independent_daily_cold_start": True,
        "cross_day_endogenous_state_carryover": False,
        "controller_burn_in_steps": 0,
        "issues_per_method_per_day": ISSUES_PER_DAY,
        "methods_per_day": METHOD_COUNT,
        "daily_runs": summaries,
    }
    (args.output / "CAMPAIGN_SUMMARY.json").write_text(
        json.dumps(campaign, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"status": status, "days": len(summaries), "output": str(args.output)}))
    if status != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
