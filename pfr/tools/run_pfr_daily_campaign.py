"""Run fixed-AEST January dates as independent canonical-PRE episodes."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from pfr.provenance import scientific_implementation_fingerprint


ISSUES_PER_DAY = 288
METHOD_COUNT = 8
B8_METHOD_COUNT = 1
_ACTIVE_CHILDREN: set[subprocess.Popen[str]] = set()
_ACTIVE_CHILDREN_LOCK = threading.Lock()
_STOP_REQUESTED = threading.Event()


def signal_process_group(process: subprocess.Popen[str], signum: int) -> None:
    if process.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(process.pid, signum)
            return
        except ProcessLookupError:
            return
    process.send_signal(signum)


def run_child(
    command: Sequence[str],
    *,
    cwd: Path,
    stdout: Any = None,
) -> int:
    if _STOP_REQUESTED.is_set():
        return 130
    process = subprocess.Popen(
        command,
        cwd=cwd,
        stdout=stdout,
        stderr=subprocess.STDOUT if stdout is not None else None,
        text=True,
        start_new_session=True,
    )
    with _ACTIVE_CHILDREN_LOCK:
        _ACTIVE_CHILDREN.add(process)
    if _STOP_REQUESTED.is_set() and process.poll() is None:
        signal_process_group(process, signal.SIGINT)
    try:
        return process.wait()
    finally:
        with _ACTIVE_CHILDREN_LOCK:
            _ACTIVE_CHILDREN.discard(process)


def discover_campaign_process_groups(output: Path) -> set[int]:
    """Find live matrix process groups, including children orphaned by a race."""
    if os.name != "posix" or not Path("/proc").is_dir():
        return set()
    campaign_root = output.resolve()
    groups: set[int] = set()
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            argv = [
                value.decode(errors="replace")
                for value in (entry / "cmdline").read_bytes().split(b"\0")
                if value
            ]
        except (OSError, PermissionError):
            continue
        if "pfr.tools.run_pfr_matrix" not in argv:
            continue
        try:
            output_index = argv.index("--output")
            child_output = Path(argv[output_index + 1]).resolve()
        except (ValueError, IndexError, OSError):
            continue
        if child_output.parent != campaign_root:
            continue
        try:
            groups.add(os.getpgid(int(entry.name)))
        except ProcessLookupError:
            continue
    return groups


def _signal_groups(groups: Sequence[int], signum: int) -> None:
    for group in groups:
        try:
            os.killpg(group, signum)
        except ProcessLookupError:
            continue


def stop_active_children(output: Path) -> None:
    _STOP_REQUESTED.set()
    with _ACTIVE_CHILDREN_LOCK:
        active = tuple(_ACTIVE_CHILDREN)
    groups = {
        process.pid for process in active if process.poll() is None and os.name == "posix"
    }
    groups.update(discover_campaign_process_groups(output))
    if os.name == "posix":
        _signal_groups(sorted(groups), signal.SIGINT)
    else:
        for process in active:
            signal_process_group(process, signal.SIGINT)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline and (
        any(process.poll() is None for process in active)
        or discover_campaign_process_groups(output)
    ):
        time.sleep(0.05)
    remaining_groups = discover_campaign_process_groups(output)
    remaining_groups.update(
        process.pid
        for process in active
        if process.poll() is None and os.name == "posix"
    )
    if os.name == "posix":
        _signal_groups(sorted(remaining_groups), signal.SIGTERM)
    else:
        for process in active:
            if process.poll() is None:
                signal_process_group(process, signal.SIGTERM)
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and (
        any(process.poll() is None for process in active)
        or discover_campaign_process_groups(output)
    ):
        time.sleep(0.05)
    remaining_groups = discover_campaign_process_groups(output)
    remaining_groups.update(
        process.pid
        for process in active
        if process.poll() is None and os.name == "posix"
    )
    if os.name == "posix":
        _signal_groups(sorted(remaining_groups), signal.SIGKILL)
    else:
        for process in active:
            if process.poll() is None:
                signal_process_group(process, signal.SIGKILL)


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


def summary_passes(
    summary: Mapping[str, Any], *, method_count: int = METHOD_COUNT
) -> bool:
    return bool(
        summary.get("status") == "PASS"
        and summary.get("expected_commit_markers") == ISSUES_PER_DAY * method_count
        and summary.get("all_actual_gurobi") is True
        and summary.get("all_fresh_exact_opendss") is True
        and summary.get("all_state_chains_complete") is True
        and summary.get("future_actual_used") is False
    )


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reusable_pass(
    day_root: Path,
    implementation_fingerprint: str,
    shared_authority_sha256: str | None = None,
    method_count: int = METHOD_COUNT,
) -> bool:
    summary_path = day_root / "MATRIX_SUMMARY.json"
    manifest_path = day_root / "RUN_MANIFEST.json"
    if not summary_path.is_file() or not manifest_path.is_file():
        return False
    try:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(
        summary_passes(summary, method_count=method_count)
        and manifest.get("scientific_implementation_fingerprint")
        == implementation_fingerprint
        and (
            shared_authority_sha256 is None
            or manifest.get("shared_exogenous_authority_sha256")
            == shared_authority_sha256
        )
    )


def preserve_existing_day(day_root: Path, output: Path) -> Path:
    output_resolved = output.resolve()
    day_resolved = day_root.resolve()
    if day_resolved.parent != output_resolved:
        raise RuntimeError("refusing to move a day artifact outside the campaign root")
    archive_root = output_resolved / "_preserved_attempts"
    archive_root.mkdir(parents=True, exist_ok=True)
    suffix = time.time_ns()
    target = archive_root / f"{day_root.name}__attempt_{suffix}"
    while target.exists():
        suffix += 1
        target = archive_root / f"{day_root.name}__attempt_{suffix}"
    day_resolved.replace(target)
    return target


def run_day(
    spec: DaySpec,
    *,
    repo: Path,
    output: Path,
    common: Sequence[str],
    capture_day_logs: bool,
    reuse_passed_days: bool,
    supplementary_b8_periodic_5min: bool,
) -> Mapping[str, Any]:
    day_root = output / spec.calendar_date
    summary_path = day_root / "MATRIX_SUMMARY.json"
    implementation_fingerprint = scientific_implementation_fingerprint(repo)
    try:
        shared_index = common.index("--shared-root")
        shared_root = Path(common[shared_index + 1])
    except (ValueError, IndexError) as exc:
        raise RuntimeError("daily command lacks --shared-root") from exc
    shared_authority_sha256 = file_sha256(
        shared_root / "SHARED_EXOGENOUS_AUTHORITY.json"
    )
    method_count = B8_METHOD_COUNT if supplementary_b8_periodic_5min else METHOD_COUNT
    if reuse_passed_days and reusable_pass(
        day_root,
        implementation_fingerprint,
        shared_authority_sha256,
        method_count,
    ):
        return {
            "calendar_date": spec.calendar_date,
            "start_issue": spec.start_issue,
            "status": "PASS",
            "artifact": str(day_root),
            "reused_existing_pass": True,
            "scientific_implementation_fingerprint": implementation_fingerprint,
            "shared_exogenous_authority_sha256": shared_authority_sha256,
        }

    preserved_attempt = None
    if day_root.exists():
        preserved_attempt = preserve_existing_day(day_root, output)
    day_root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pfr.tools.run_pfr_matrix",
        *common,
        "--candidate-id", spec.candidate_id,
        "--start-issue", str(spec.start_issue),
        "--output", str(day_root),
    ]
    if supplementary_b8_periodic_5min:
        command.append("--supplementary-b8-periodic-5min")
    if capture_day_logs:
        with (day_root / "DAY_RUN.log").open("w", encoding="utf-8") as log:
            returncode = run_child(command, cwd=repo, stdout=log)
    else:
        returncode = run_child(command, cwd=repo)

    if returncode != 0 or not summary_path.is_file():
        result = {
            "calendar_date": spec.calendar_date,
            "start_issue": spec.start_issue,
            "status": "FAIL_CLOSED",
            "returncode": returncode,
            "artifact": str(day_root),
        }
        if preserved_attempt is not None:
            result["preserved_previous_attempt"] = str(preserved_attempt)
        return result
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    result = {
        "calendar_date": spec.calendar_date,
        "start_issue": spec.start_issue,
        "status": (
            "PASS"
            if summary_passes(summary, method_count=method_count)
            else "FAIL_CLOSED"
        ),
        "artifact": str(day_root),
        "reused_existing_pass": False,
        "scientific_implementation_fingerprint": implementation_fingerprint,
        "shared_exogenous_authority_sha256": shared_authority_sha256,
    }
    if preserved_attempt is not None:
        result["preserved_previous_attempt"] = str(preserved_attempt)
    return result


def campaign_payload(
    *,
    start_day: int,
    end_day: int,
    day_workers: int,
    summaries: Sequence[Mapping[str, Any]],
    final: bool,
    supplementary_b8_periodic_5min: bool,
) -> Mapping[str, Any]:
    expected_days = end_day - start_day + 1
    complete = len(summaries) == expected_days
    all_pass = complete and all(row["status"] == "PASS" for row in summaries)
    any_fail = any(row["status"] == "FAIL_CLOSED" for row in summaries)
    status = "PASS" if all_pass else ("FAIL_CLOSED" if final or any_fail else "IN_PROGRESS")
    return {
        "schema_version": (
            "PFR_JAN2025_POST_HOC_B8_PERIODIC_5MIN_SUPPLEMENTARY_V1"
            if supplementary_b8_periodic_5min
            else "PFR_JAN2025_POST_HOC_DAILY_VALIDATION_V13_13_FREEZE_20260823"
        ),
        "status": status,
        "evaluation_classification": "POST_HOC_DESIGN_VALIDATION_NOT_INDEPENDENT_HOLDOUT",
        "independent_holdout_claim": False,
        "calendar_timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "start_day": start_day,
        "end_day": end_day,
        "day_process_workers": day_workers,
        "gurobi_threads_per_process": int(os.environ.get("PFR_GUROBI_THREADS", "1")),
        "independent_daily_cold_start": True,
        "cross_day_endogenous_state_carryover": False,
        "continue_to_next_method_after_failure": True,
        "continue_to_next_day_after_failure": True,
        "failure_evidence_preserved_before_continuation": True,
        "controller_burn_in_steps": 0,
        "issues_per_method_per_day": ISSUES_PER_DAY,
        "methods_per_day": (
            B8_METHOD_COUNT if supplementary_b8_periodic_5min else METHOD_COUNT
        ),
        "method_ids": (
            ["B8"]
            if supplementary_b8_periodic_5min
            else [f"B{index}" for index in range(METHOD_COUNT)]
        ),
        "supplementary_b8_periodic_5min": supplementary_b8_periodic_5min,
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
    parser.add_argument(
        "--supplementary-b8-periodic-5min",
        action="store_true",
        help="Run only the post-hoc B8 five-minute periodic timing baseline.",
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

    native_authority_path = (
        args.repo / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.json"
    )
    if not native_authority_path.is_file():
        raise RuntimeError("native grid-control authority is missing")
    native_authority = json.loads(
        native_authority_path.read_text(encoding="utf-8")
    )
    post_hoc_authorized = bool(
        native_authority.get("status")
        == "FROZEN_APPROVED_POST_HOC_VALIDATION_ONLY"
        and native_authority.get("january_2025_post_hoc_validation_authorized")
        is True
        and native_authority.get("evaluation_classification")
        == "POST_HOC_DESIGN_VALIDATION_NOT_INDEPENDENT_HOLDOUT"
    )
    if not post_hoc_authorized:
        print(
            "BLOCKED before worker launch: native capacitor threshold/delay/dwell "
            "authority is not frozen for January post-hoc validation. "
            "No day process was started.",
            file=sys.stderr,
            flush=True,
        )
        raise SystemExit(2)

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
        "--migration-authority", str(
            args.migration_authority
            if args.migration_authority is not None
            else args.repo / "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
        ),
    ]
    for mobility_root in args.mobility_root:
        common.extend(("--mobility-root", str(mobility_root)))

    summaries: list[Mapping[str, Any]] = []
    pool = ThreadPoolExecutor(max_workers=args.day_workers)
    futures: dict[Future[Mapping[str, Any]], DaySpec] = {}
    try:
        futures = {
            pool.submit(
                run_day,
                spec,
                repo=args.repo,
                output=args.output,
                common=common,
                capture_day_logs=args.capture_day_logs,
                reuse_passed_days=not args.no_reuse_passed_days,
                supplementary_b8_periodic_5min=(
                    args.supplementary_b8_periodic_5min
                ),
            ): spec
            for spec in specs
        }
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
                temporary_failure = day_root / "ORCHESTRATION_FAILURE.json.tmp"
                temporary_failure.write_text(
                    json.dumps(failure, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                temporary_failure.replace(day_root / "ORCHESTRATION_FAILURE.json")
                row = {
                    "calendar_date": spec.calendar_date,
                    "start_issue": spec.start_issue,
                    "status": "FAIL_CLOSED",
                    "artifact": str(day_root),
                    "orchestration_exception": failure,
                }
            summaries.append(row)
            write_campaign(
                args.output,
                campaign_payload(
                    start_day=args.start_day,
                    end_day=args.end_day,
                    day_workers=args.day_workers,
                    summaries=summaries,
                    final=False,
                    supplementary_b8_periodic_5min=(
                        args.supplementary_b8_periodic_5min
                    ),
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
    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        for future in futures:
            future.cancel()
        stop_active_children(args.output)
        pool.shutdown(wait=True, cancel_futures=True)
        interrupted = dict(
            campaign_payload(
                start_day=args.start_day,
                end_day=args.end_day,
                day_workers=args.day_workers,
                summaries=summaries,
                final=False,
                supplementary_b8_periodic_5min=(
                    args.supplementary_b8_periodic_5min
                ),
            )
        )
        interrupted["status"] = "INTERRUPTED"
        interrupted["signal"] = "SIGINT"
        write_campaign(args.output, interrupted)
        print(json.dumps({
            "status": "INTERRUPTED",
            "days": len(summaries),
            "output": str(args.output),
        }), flush=True)
        raise SystemExit(130)
    else:
        pool.shutdown(wait=True)

    campaign = campaign_payload(
        start_day=args.start_day,
        end_day=args.end_day,
        day_workers=args.day_workers,
        summaries=summaries,
        final=True,
        supplementary_b8_periodic_5min=args.supplementary_b8_periodic_5min,
    )
    write_campaign(args.output, campaign)
    print(json.dumps({"status": campaign["status"], "days": len(summaries), "output": str(args.output)}))
    if campaign["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
