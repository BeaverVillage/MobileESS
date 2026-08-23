"""Run a frozen 2025 representative week as independent daily B0-B7 episodes."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from pfr.tools.run_pfr_daily_campaign import (
    DaySpec,
    ISSUES_PER_DAY,
    run_day,
    stop_active_children,
    write_campaign,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def period_specs(period: Mapping[str, Any]) -> tuple[DaySpec, ...]:
    start = date.fromisoformat(str(period["calendar_start"]))
    issue_first = int(period["global_issue_first"])
    days = int(period["days"])
    return tuple(
        DaySpec(
            day_index=offset + 1,
            calendar_date=(start + timedelta(days=offset)).isoformat(),
            start_issue=issue_first + offset * ISSUES_PER_DAY,
            candidate_id=f"{period['period_id']}_DAY{offset + 1:02d}",
        )
        for offset in range(days)
    )


def payload(
    period: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    *,
    workers: int,
    final: bool,
    continue_after_failure: bool,
) -> Mapping[str, Any]:
    expected = int(period["days"])
    complete = len(rows) == expected
    any_fail = any(row["status"] == "FAIL_CLOSED" for row in rows)
    status = (
        "PASS"
        if complete and not any_fail
        else ("FAIL_CLOSED" if final or any_fail else "IN_PROGRESS")
    )
    return {
        "schema_version": "PFR_FROZEN_REP_WEEK_DAILY_VALIDATION_V13_13",
        "status": status,
        "period_id": period["period_id"],
        "evaluation_classification": (
            period.get(
                "evaluation_classification",
                "FROZEN_OUT_OF_MONTH_GENERALIZATION_VALIDATION_NOT_STRICTLY_UNSEEN",
            )
        ),
        "independent_holdout_claim": False,
        "calendar_timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "day_process_workers": workers,
        "gurobi_threads_per_process": int(os.environ.get("PFR_GUROBI_THREADS", "1")),
        "independent_daily_cold_start": True,
        "cross_day_endogenous_state_carryover": False,
        "continue_to_next_method_after_failure": True,
        "continue_to_next_day_after_failure": continue_after_failure,
        "failure_evidence_preserved_before_continuation": True,
        "issues_per_method_per_day": ISSUES_PER_DAY,
        "methods_per_day": 8,
        "daily_runs": sorted(rows, key=lambda row: str(row["calendar_date"])),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--period-id", required=True)
    parser.add_argument("--period-contract", type=Path)
    parser.add_argument("--day-workers", type=int, default=4)
    parser.add_argument("--capture-day-logs", action="store_true")
    parser.add_argument(
        "--continue-after-failure",
        action="store_true",
        help="Preserve a failed B/day and continue through the remaining B/day queue.",
    )
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
    parser.add_argument(
        "--migration-authority",
        type=Path,
        help="Frozen IDC migration authority; defaults to the repository contract.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.day_workers <= 31:
        parser.error("--day-workers must be in [1, 31]")

    contract_path = args.period_contract or (
        args.repo / "pfr/contracts/FROZEN_2025_REP_WEEK_VALIDATION_PERIODS_V1.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    matches = [
        row for row in contract["periods"] if row["period_id"] == args.period_id
    ]
    if len(matches) != 1:
        raise RuntimeError("period is not present exactly once in the frozen authority")
    period = {
        **matches[0],
        "evaluation_classification": contract.get(
            "evaluation_classification",
            "FROZEN_OUT_OF_MONTH_GENERALIZATION_VALIDATION_NOT_STRICTLY_UNSEEN",
        ),
    }
    shared_authority = args.shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"
    expected_authority_sha = period.get("shared_exogenous_authority_sha256")
    if expected_authority_sha is not None and sha256(shared_authority) != expected_authority_sha:
        raise RuntimeError("shared exogenous authority SHA drift")
    source = json.loads(shared_authority.read_text(encoding="utf-8"))
    if (
        source.get("status") != "PASS"
        or source.get("candidate_id") != args.period_id
        or source.get("future_actual_used_by_optimizer") is not False
        or int(source.get("scored_issue_first", -1))
        != int(period["global_issue_first"])
        or int(source.get("scored_issue_last", -1))
        != int(period["global_issue_last"])
    ):
        raise RuntimeError("shared exogenous authority does not match the frozen period")
    if expected_authority_sha is None and source.get("period_contract_sha256") != sha256(contract_path):
        raise RuntimeError("generated full-month source is not bound to its period contract")

    common = [
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
        "--migration-authority", str(
            args.migration_authority
            if args.migration_authority is not None
            else args.repo / "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
        ),
    ]
    for mobility_root in args.mobility_root:
        common.extend(("--mobility-root", str(mobility_root)))
    args.output.mkdir(parents=True, exist_ok=True)
    specs = period_specs(period)
    rows: list[Mapping[str, Any]] = []
    pool = ThreadPoolExecutor(max_workers=args.day_workers)
    futures: dict[Future[Mapping[str, Any]], DaySpec] = {
        pool.submit(
            run_day,
            spec,
            repo=args.repo,
            output=args.output,
            common=common,
            capture_day_logs=args.capture_day_logs,
            reuse_passed_days=True,
        ): spec
        for spec in specs
    }
    try:
        for future in as_completed(futures):
            spec = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                day_root = args.output / spec.calendar_date
                day_root.mkdir(parents=True, exist_ok=True)
                failure = {
                    "status": "FAIL_CLOSED_ORCHESTRATION_EXCEPTION",
                    "calendar_date": spec.calendar_date,
                    "start_issue": spec.start_issue,
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "partial_results_preserved": True,
                }
                temporary = day_root / "ORCHESTRATION_FAILURE.json.tmp"
                temporary.write_text(
                    json.dumps(failure, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                temporary.replace(day_root / "ORCHESTRATION_FAILURE.json")
                row = {
                    "calendar_date": spec.calendar_date,
                    "start_issue": spec.start_issue,
                    "status": "FAIL_CLOSED",
                    "artifact": str(day_root),
                    "orchestration_exception": failure,
                }
            rows.append(row)
            write_campaign(
                args.output,
                payload(
                    period,
                    rows,
                    workers=args.day_workers,
                    final=False,
                    continue_after_failure=args.continue_after_failure,
                ),
            )
            print(
                json.dumps(
                    {
                        "day": row["calendar_date"],
                        "completed_days": len(rows),
                        "total_days": len(specs),
                        "status": row["status"],
                    }
                ),
                flush=True,
            )
            if row["status"] != "PASS" and not args.continue_after_failure:
                for pending in futures:
                    pending.cancel()
                stop_active_children(args.output)
                break
    except KeyboardInterrupt:
        for future in futures:
            future.cancel()
        stop_active_children(args.output)
        raise SystemExit(130)
    finally:
        pool.shutdown(wait=True, cancel_futures=True)

    campaign = payload(
        period,
        rows,
        workers=args.day_workers,
        final=True,
        continue_after_failure=args.continue_after_failure,
    )
    write_campaign(args.output, campaign)
    print(json.dumps({"status": campaign["status"], "output": str(args.output)}))
    if campaign["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
