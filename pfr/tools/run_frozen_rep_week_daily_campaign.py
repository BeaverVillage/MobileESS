"""Run a frozen 2025 representative week as independent daily B0-B7 episodes."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from datetime import date, timedelta
import hashlib
import json
import os
import queue
from pathlib import Path
from typing import Any, Mapping

from pfr.cpu_topology import discover_disjoint_cpu_groups
from pfr.tools.run_pfr_daily_campaign import (
    DaySpec,
    ELECTRICAL_STRESS_METHODS,
    ISSUES_PER_DAY,
    install_stop_signal_handlers,
    run_day_with_affinity_slot,
    stop_active_children,
    write_campaign,
)
from pfr.result_storage import materialize_period_summary


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def period_specs(
    period: Mapping[str, Any],
    *,
    start_day_index: int = 1,
    end_day_index: int | None = None,
) -> tuple[DaySpec, ...]:
    start = date.fromisoformat(str(period["calendar_start"]))
    issue_first = int(period["global_issue_first"])
    days = int(period["days"])
    selected_end = days if end_day_index is None else int(end_day_index)
    if not 1 <= start_day_index <= selected_end <= days:
        raise ValueError(
            "period day slice must satisfy 1 <= start <= end <= period days"
        )
    return tuple(
        DaySpec(
            day_index=offset + 1,
            calendar_date=(start + timedelta(days=offset)).isoformat(),
            start_issue=issue_first + offset * ISSUES_PER_DAY,
            candidate_id=f"{period['period_id']}_DAY{offset + 1:02d}",
        )
        for offset in range(start_day_index - 1, selected_end)
    )


def payload(
    period: Mapping[str, Any],
    rows: list[Mapping[str, Any]],
    *,
    workers: int,
    final: bool,
    continue_after_failure: bool,
    supplementary_b8_periodic_5min: bool = False,
    diagnostic_method: str | None = None,
    electrical_stress_campaign: bool = False,
    cpu_affinity_policy: str = "none",
    cpu_affinity_groups: tuple[tuple[int, ...], ...] = (),
    expected_days: int | None = None,
    start_day_index: int = 1,
    end_day_index: int | None = None,
) -> Mapping[str, Any]:
    expected = int(period["days"]) if expected_days is None else expected_days
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
        "period_day_index_first": start_day_index,
        "period_day_index_last": (
            int(period["days"]) if end_day_index is None else end_day_index
        ),
        "full_period_execution": expected == int(period["days"]),
        "evaluation_classification": (
            "FEBRUARY_2025_DEVELOPMENT_VALIDATION_NOT_INDEPENDENT_EXECUTION"
            if period.get("period_id") == "FEB2025_FULL"
            and diagnostic_method in {"B6", "B7"}
            else period.get(
                "evaluation_classification",
                "FROZEN_OUT_OF_MONTH_GENERALIZATION_VALIDATION_NOT_STRICTLY_UNSEEN",
            )
        ),
        "independent_holdout_claim": False,
        "calendar_timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "day_process_workers": workers,
        "gurobi_threads_per_process": int(os.environ.get("PFR_GUROBI_THREADS", "1")),
        "cpu_affinity_policy": cpu_affinity_policy,
        "cpu_affinity_groups": [list(group) for group in cpu_affinity_groups],
        "independent_daily_cold_start": True,
        "cross_day_endogenous_state_carryover": False,
        "continue_to_next_method_after_failure": True,
        "continue_to_next_day_after_failure": continue_after_failure,
        "failure_evidence_preserved_before_continuation": True,
        "issues_per_method_per_day": ISSUES_PER_DAY,
        "methods_per_day": (
            1
            if supplementary_b8_periodic_5min or diagnostic_method is not None
            else (len(ELECTRICAL_STRESS_METHODS) if electrical_stress_campaign else 8)
        ),
        "method_ids": (
            ["B8"]
            if supplementary_b8_periodic_5min
            else (
                [diagnostic_method]
                if diagnostic_method is not None
                else (
                    list(ELECTRICAL_STRESS_METHODS)
                    if electrical_stress_campaign
                    else [f"B{index}" for index in range(8)]
                )
            )
        ),
        "diagnostic_method": diagnostic_method,
        "electrical_stress_campaign": electrical_stress_campaign,
        "supplementary_b8_periodic_5min": supplementary_b8_periodic_5min,
        "daily_runs": sorted(rows, key=lambda row: str(row["calendar_date"])),
    }


def main() -> None:
    install_stop_signal_handlers()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--period-id", required=True)
    parser.add_argument("--period-contract", type=Path)
    parser.add_argument("--day-workers", type=int, default=4)
    parser.add_argument("--start-day-index", type=int, default=1)
    parser.add_argument("--end-day-index", type=int)
    parser.add_argument(
        "--cpu-affinity",
        choices=("none", "disjoint"),
        default="none",
    )
    parser.add_argument("--capture-day-logs", action="store_true")
    parser.add_argument(
        "--continue-after-failure",
        action="store_true",
        help="Preserve a failed B/day and continue through the remaining B/day queue.",
    )
    parser.add_argument(
        "--supplementary-b8-periodic-5min",
        action="store_true",
        help="Run only B8 for the frozen out-of-month daily period.",
    )
    parser.add_argument(
        "--diagnostic-method",
        choices=(
            tuple(f"B{index}" for index in range(9))
            + ELECTRICAL_STRESS_METHODS
        ),
        help="Run one method for a development-validation period.",
    )
    parser.add_argument(
        "--electrical-stress-campaign",
        action="store_true",
        help="Run the frozen ordered B00-B09 electrical-stress campaign.",
    )
    parser.add_argument(
        "--reuse-passed-methods",
        action="store_true",
        help="Validate and reuse completed PASS methods within partial days.",
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
    parser.add_argument("--risk-calibration", type=Path)
    parser.add_argument(
        "--h0-fidelity-audit-every-steps",
        type=int,
        default=0,
        help=(
            "Run the fixed same-state H0 surrogate/Fresh-AC candidate audit "
            "at this interval for eligible methods (0 disables it)."
        ),
    )
    parser.add_argument(
        "--migration-authority",
        type=Path,
        help="Frozen IDC migration authority; defaults to the repository contract.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.diagnostic_method and args.supplementary_b8_periodic_5min:
        parser.error(
            "--diagnostic-method and --supplementary-b8-periodic-5min are mutually exclusive"
        )
    if args.electrical_stress_campaign and (
        args.diagnostic_method or args.supplementary_b8_periodic_5min
    ):
        parser.error(
            "--electrical-stress-campaign is mutually exclusive with single-method modes"
        )
    calibrated_method_selected = bool(
        args.supplementary_b8_periodic_5min
        or args.electrical_stress_campaign
        or args.diagnostic_method in {"B7", "B8", "B08", "B09"}
        or args.diagnostic_method is None
    )
    if calibrated_method_selected and args.risk_calibration is None:
        parser.error("--risk-calibration is required before calibrated B7/B8 execution")
    if args.diagnostic_method in {"B6", "B07"} and args.risk_calibration is not None:
        parser.error("raw-risk calibration/validation must retain its raw-risk interface")
    if not 1 <= args.day_workers <= 31:
        parser.error("--day-workers must be in [1, 31]")
    if args.h0_fidelity_audit_every_steps < 0:
        parser.error("--h0-fidelity-audit-every-steps cannot be negative")

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
    if args.risk_calibration is not None:
        common.extend(("--risk-calibration", str(args.risk_calibration)))
    if args.h0_fidelity_audit_every_steps:
        common.extend(
            (
                "--h0-fidelity-audit-every-steps",
                str(args.h0_fidelity_audit_every_steps),
            )
        )
    args.output.mkdir(parents=True, exist_ok=True)
    specs = period_specs(
        period,
        start_day_index=args.start_day_index,
        end_day_index=args.end_day_index,
    )
    selected_end_day_index = (
        int(period["days"])
        if args.end_day_index is None
        else args.end_day_index
    )
    affinity_groups: tuple[tuple[int, ...], ...] = ()
    affinity_slots: queue.Queue[tuple[int, ...]] | None = None
    if args.cpu_affinity == "disjoint":
        affinity_groups = discover_disjoint_cpu_groups(
            workers=args.day_workers,
            threads_per_worker=int(os.environ.get("PFR_GUROBI_THREADS", "1")),
        )
        affinity_slots = queue.Queue()
        for group in affinity_groups:
            affinity_slots.put(group)
    rows: list[Mapping[str, Any]] = []
    pool = ThreadPoolExecutor(max_workers=args.day_workers)
    futures: dict[Future[Mapping[str, Any]], DaySpec] = {
        pool.submit(
            run_day_with_affinity_slot,
            spec,
            affinity_slots=affinity_slots,
            repo=args.repo,
            output=args.output,
            common=common,
            capture_day_logs=args.capture_day_logs,
            reuse_passed_days=True,
            supplementary_b8_periodic_5min=(
                args.supplementary_b8_periodic_5min
            ),
            diagnostic_method=args.diagnostic_method,
            electrical_stress_campaign=args.electrical_stress_campaign,
            reuse_passed_methods=args.reuse_passed_methods,
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
                    supplementary_b8_periodic_5min=(
                        args.supplementary_b8_periodic_5min
                    ),
                    diagnostic_method=args.diagnostic_method,
                    electrical_stress_campaign=args.electrical_stress_campaign,
                    cpu_affinity_policy=args.cpu_affinity,
                    cpu_affinity_groups=affinity_groups,
                    expected_days=len(specs),
                    start_day_index=args.start_day_index,
                    end_day_index=selected_end_day_index,
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
        supplementary_b8_periodic_5min=(
            args.supplementary_b8_periodic_5min
        ),
        diagnostic_method=args.diagnostic_method,
        electrical_stress_campaign=args.electrical_stress_campaign,
        cpu_affinity_policy=args.cpu_affinity,
        cpu_affinity_groups=affinity_groups,
        expected_days=len(specs),
        start_day_index=args.start_day_index,
        end_day_index=selected_end_day_index,
    )
    write_campaign(args.output, campaign)
    if campaign["status"] == "PASS" and args.electrical_stress_campaign:
        materialize_period_summary(
            args.output,
            calendar_dates=tuple(spec.calendar_date for spec in specs),
            method_ids=ELECTRICAL_STRESS_METHODS,
        )
    print(json.dumps({"status": campaign["status"], "output": str(args.output)}))
    if campaign["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
