"""Run fixed-AEST January dates as independent canonical-PRE episodes."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
import hashlib
import json
import os
import queue
import signal
import shutil
import subprocess
import sys
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, IO, Mapping, Sequence

try:
    import fcntl
except ImportError:  # pragma: no cover - production campaigns run under WSL/POSIX.
    fcntl = None

from pfr.cpu_topology import discover_disjoint_cpu_groups
from pfr.provenance import scientific_implementation_fingerprint
from pfr.result_storage import materialize_period_summary


ISSUES_PER_DAY = 288
METHOD_COUNT = 8
ELECTRICAL_STRESS_METHODS = tuple(f"B{index:02d}" for index in range(10))
ELECTRICAL_STRESS_METHOD_COUNT = len(ELECTRICAL_STRESS_METHODS)
B8_METHOD_COUNT = 1
_ACTIVE_CHILDREN: set[subprocess.Popen[str]] = set()
_ACTIVE_CHILDREN_LOCK = threading.Lock()
_STOP_REQUESTED = threading.Event()
_RECEIVED_STOP_SIGNAL: int | None = None


class CampaignAlreadyRunningError(RuntimeError):
    """Raised before artifacts are touched when an output root is already active."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def acquire_campaign_lock(output: Path) -> IO[str]:
    """Hold a non-blocking lifetime lock for one campaign output root."""
    output.mkdir(parents=True, exist_ok=True)
    lock_path = output / ".CAMPAIGN_RUN.lock"
    handle = lock_path.open("a+", encoding="utf-8")
    if fcntl is not None:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            handle.seek(0)
            owner = handle.read().strip() or "owner metadata unavailable"
            handle.close()
            raise CampaignAlreadyRunningError(
                f"campaign output root is already active: {output}; owner={owner}"
            ) from exc
    owner = {
        "status": "ACTIVE",
        "pid": os.getpid(),
        "started_at_utc": utc_now(),
        "output_root": str(output.resolve()),
        "argv": sys.argv,
    }
    handle.seek(0)
    handle.truncate()
    handle.write(json.dumps(owner, sort_keys=True) + "\n")
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def release_campaign_lock(handle: IO[str]) -> None:
    try:
        handle.seek(0)
        handle.truncate()
        handle.write(
            json.dumps(
                {"status": "RELEASED", "pid": os.getpid(), "released_at_utc": utc_now()},
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    finally:
        handle.close()


def install_stop_signal_handlers() -> None:
    """Make SIGINT/SIGTERM interrupt the campaign even if a parent ignored them."""
    _STOP_REQUESTED.clear()

    def raise_keyboard_interrupt(signum: int, _frame: Any) -> None:
        global _RECEIVED_STOP_SIGNAL
        _RECEIVED_STOP_SIGNAL = signum
        _STOP_REQUESTED.set()
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, raise_keyboard_interrupt)
    signal.signal(signal.SIGTERM, raise_keyboard_interrupt)


def received_stop_signal_name() -> str:
    if _RECEIVED_STOP_SIGNAL is None:
        return "SIGINT"
    return signal.Signals(_RECEIVED_STOP_SIGNAL).name


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
    cpu_affinity: Sequence[int] | None = None,
) -> int:
    if _STOP_REQUESTED.is_set():
        return 130
    launch_command = list(command)
    if cpu_affinity is not None:
        taskset = shutil.which("taskset")
        if taskset is None:
            raise RuntimeError("topology-aware affinity requested but taskset is missing")
        if not cpu_affinity:
            raise RuntimeError("topology-aware affinity produced an empty CPU group")
        launch_command = [
            taskset,
            "--cpu-list",
            ",".join(str(cpu) for cpu in cpu_affinity),
            *launch_command,
        ]
    process = subprocess.Popen(
        launch_command,
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
    authorized_implementation_fingerprints: Sequence[str] = (),
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
    artifact_fingerprint = manifest.get("scientific_implementation_fingerprint")
    return bool(
        summary_passes(summary, method_count=method_count)
        and (
            artifact_fingerprint == implementation_fingerprint
            or artifact_fingerprint in authorized_implementation_fingerprints
        )
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


def _log_tail(path: Path, *, max_lines: int = 240) -> list[str]:
    if not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[
            -max_lines:
        ]
    except OSError as exc:
        return [f"<unable to read log: {type(exc).__name__}: {exc}>"]


def write_day_failure_evidence(
    *,
    day_root: Path,
    spec: DaySpec,
    returncode: int,
    command: Sequence[str],
    implementation_fingerprint: str,
    preserved_attempt: Path | None,
) -> Path:
    """Persist enough immutable evidence to diagnose a failed run without replay."""
    log_path = day_root / "DAY_RUN.log"
    evidence_path = day_root / "FAILURE_EVIDENCE.json"
    atomic_write_json(
        evidence_path,
        {
            "schema_version": "PFR_DAILY_FAILURE_EVIDENCE_V1",
            "status": "FAIL_CLOSED",
            "captured_at_utc": utc_now(),
            "calendar_date": spec.calendar_date,
            "start_issue": spec.start_issue,
            "returncode": returncode,
            "command": list(command),
            "cwd": str(day_root.parent),
            "scientific_implementation_fingerprint": implementation_fingerprint,
            "day_artifact": str(day_root),
            "preserved_previous_attempt": (
                str(preserved_attempt) if preserved_attempt is not None else None
            ),
            "matrix_summary_present": (day_root / "MATRIX_SUMMARY.json").is_file(),
            "run_manifest_present": (day_root / "RUN_MANIFEST.json").is_file(),
            "day_log": str(log_path),
            "day_log_tail": _log_tail(log_path),
            "artifact_files": sorted(
                str(path.relative_to(day_root))
                for path in day_root.rglob("*")
                if path.is_file()
            ),
        },
    )
    return evidence_path


def run_day(
    spec: DaySpec,
    *,
    repo: Path,
    output: Path,
    common: Sequence[str],
    capture_day_logs: bool,
    reuse_passed_days: bool,
    supplementary_b8_periodic_5min: bool,
    diagnostic_method: str | None = None,
    electrical_stress_campaign: bool = False,
    cpu_affinity: Sequence[int] | None = None,
    diagnostic_steps_per_day: int | None = None,
    authorized_pass_fingerprints: Sequence[str] = (),
    reuse_passed_methods: bool = False,
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
    method_count = (
        1
        if supplementary_b8_periodic_5min or diagnostic_method is not None
        else (
            ELECTRICAL_STRESS_METHOD_COUNT
            if electrical_stress_campaign
            else METHOD_COUNT
        )
    )
    if reuse_passed_days and reusable_pass(
        day_root,
        implementation_fingerprint,
        shared_authority_sha256,
        method_count,
        authorized_pass_fingerprints,
    ):
        artifact_manifest = json.loads(
            (day_root / "RUN_MANIFEST.json").read_text(encoding="utf-8")
        )
        artifact_fingerprint = str(
            artifact_manifest["scientific_implementation_fingerprint"]
        )
        return {
            "calendar_date": spec.calendar_date,
            "start_issue": spec.start_issue,
            "status": "PASS",
            "artifact": str(day_root),
            "reused_existing_pass": True,
            "scientific_implementation_fingerprint": implementation_fingerprint,
            "artifact_scientific_implementation_fingerprint": artifact_fingerprint,
            "cross_implementation_reuse_authorized": (
                artifact_fingerprint != implementation_fingerprint
            ),
            "shared_exogenous_authority_sha256": shared_authority_sha256,
        }

    preserved_attempt = None
    if day_root.exists() and not reuse_passed_methods:
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
    if electrical_stress_campaign:
        command.append("--electrical-stress-campaign")
    if reuse_passed_methods:
        command.append("--reuse-passed-methods")
    if diagnostic_method is not None:
        command.extend(
            (
                "--diagnostic-method",
                diagnostic_method,
                "--restart-checkpoint-interval",
                "8",
            )
        )
    if diagnostic_steps_per_day is not None:
        command.extend(
            (
                "--diagnostic-stop-after-issue",
                str(spec.start_issue + diagnostic_steps_per_day - 1),
            )
        )
    if capture_day_logs:
        with (day_root / "DAY_RUN.log").open("w", encoding="utf-8") as log:
            returncode = run_child(
                command,
                cwd=repo,
                stdout=log,
                cpu_affinity=cpu_affinity,
            )
    else:
        returncode = run_child(command, cwd=repo, cpu_affinity=cpu_affinity)

    if returncode != 0 or not summary_path.is_file():
        evidence_path = write_day_failure_evidence(
            day_root=day_root,
            spec=spec,
            returncode=returncode,
            command=command,
            implementation_fingerprint=implementation_fingerprint,
            preserved_attempt=preserved_attempt,
        )
        result = {
            "calendar_date": spec.calendar_date,
            "start_issue": spec.start_issue,
            "status": "FAIL_CLOSED",
            "returncode": returncode,
            "artifact": str(day_root),
            "failure_evidence": str(evidence_path),
        }
        if preserved_attempt is not None:
            result["preserved_previous_attempt"] = str(preserved_attempt)
        return result
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    bounded_diagnostic_pass = bool(
        diagnostic_steps_per_day is not None
        and summary.get("status") == "DIAGNOSTIC_STOP"
        and int(summary.get("valid_commit_markers", -1))
        == diagnostic_steps_per_day
    )
    day_status = (
        "PASS"
        if summary_passes(summary, method_count=method_count)
        or bounded_diagnostic_pass
        else "FAIL_CLOSED"
    )
    result = {
        "calendar_date": spec.calendar_date,
        "start_issue": spec.start_issue,
        "status": day_status,
        "artifact": str(day_root),
        "reused_existing_pass": False,
        "scientific_implementation_fingerprint": implementation_fingerprint,
        "shared_exogenous_authority_sha256": shared_authority_sha256,
        "bounded_diagnostic_pass": bounded_diagnostic_pass,
    }
    if preserved_attempt is not None:
        result["preserved_previous_attempt"] = str(preserved_attempt)
    if day_status == "FAIL_CLOSED":
        result["failure_evidence"] = str(
            write_day_failure_evidence(
                day_root=day_root,
                spec=spec,
                returncode=returncode,
                command=command,
                implementation_fingerprint=implementation_fingerprint,
                preserved_attempt=preserved_attempt,
            )
        )
    return result


def run_day_with_affinity_slot(
    spec: DaySpec,
    *,
    affinity_slots: queue.Queue[tuple[int, ...]] | None,
    **kwargs: Any,
) -> Mapping[str, Any]:
    """Hold one disjoint CPU slot for the complete lifetime of a day process."""

    affinity = affinity_slots.get() if affinity_slots is not None else None
    try:
        result = run_day(spec, cpu_affinity=affinity, **kwargs)
        return {
            **result,
            "cpu_affinity": list(affinity) if affinity is not None else None,
        }
    finally:
        if affinity_slots is not None and affinity is not None:
            affinity_slots.put(affinity)


def campaign_payload(
    *,
    start_day: int,
    end_day: int,
    day_workers: int,
    summaries: Sequence[Mapping[str, Any]],
    final: bool,
    supplementary_b8_periodic_5min: bool,
    checkpoint_payload_occupancy_factor: float | None = None,
    diagnostic_method: str | None = None,
    electrical_stress_campaign: bool = False,
    fail_fast: bool = False,
    cpu_affinity_policy: str = "none",
    cpu_affinity_groups: Sequence[Sequence[int]] = (),
    diagnostic_steps_per_day: int | None = None,
    authorized_pass_fingerprints: Sequence[str] = (),
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
            else (
                "PFR_ELECTRICAL_STRESS_B00_B09_DAILY_CAMPAIGN_V1"
                if electrical_stress_campaign
                else "PFR_JAN2025_POST_HOC_DAILY_VALIDATION_V13_13_FREEZE_20260823"
            )
        ),
        "status": status,
        "evaluation_classification": (
            "JANUARY_2025_B07_ELECTRICAL_STRESS_RISK_CALIBRATION_FIT"
            if diagnostic_method == "B07"
            else (
                "JANUARY_2025_B6_HISTORICAL_RISK_CALIBRATION_FIT"
                if diagnostic_method == "B6"
                else "POST_HOC_DESIGN_VALIDATION_NOT_INDEPENDENT_HOLDOUT"
            )
        ),
        "independent_holdout_claim": False,
        "calendar_timezone": "FIXED_AEST_UTC_PLUS_10_NO_DST",
        "start_day": start_day,
        "end_day": end_day,
        "day_process_workers": day_workers,
        "gurobi_threads_per_process": int(os.environ.get("PFR_GUROBI_THREADS", "1")),
        "cpu_affinity_policy": cpu_affinity_policy,
        "cpu_affinity_groups": [list(group) for group in cpu_affinity_groups],
        "diagnostic_steps_per_day": diagnostic_steps_per_day,
        "scientific_result_eligible": diagnostic_steps_per_day is None,
        "authorized_verified_pass_reuse_fingerprints": sorted(
            set(authorized_pass_fingerprints)
        ),
        "cross_implementation_pass_reuse_is_explicit": True,
        "independent_daily_cold_start": True,
        "cross_day_endogenous_state_carryover": False,
        "continue_to_next_method_after_failure": True,
        "continue_to_next_day_after_failure": not fail_fast,
        "fail_fast_on_first_day_failure": fail_fast,
        "failure_evidence_preserved_before_continuation": True,
        "failure_evidence_preserved_before_abort": True,
        "controller_burn_in_steps": 0,
        "issues_per_method_per_day": ISSUES_PER_DAY,
        "methods_per_day": (
            1
            if supplementary_b8_periodic_5min or diagnostic_method is not None
            else (
                ELECTRICAL_STRESS_METHOD_COUNT
                if electrical_stress_campaign
                else METHOD_COUNT
            )
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
                    else [f"B{index}" for index in range(METHOD_COUNT)]
                )
            )
        ),
        "diagnostic_method": diagnostic_method,
        "electrical_stress_campaign": electrical_stress_campaign,
        "supplementary_b8_periodic_5min": supplementary_b8_periodic_5min,
        "checkpoint_payload_occupancy_factor": (
            checkpoint_payload_occupancy_factor
        ),
        "checkpoint_payload_parameterization": (
            "ENGINEERING_SCENARIO_NOT_MEASURED_CHECKPOINT_SIZE"
            if checkpoint_payload_occupancy_factor is not None
            else "FROZEN_PRIMARY_AUTHORITY_VALUE"
        ),
        "daily_runs": sorted(summaries, key=lambda row: str(row["calendar_date"])),
    }


def write_campaign(output: Path, payload: Mapping[str, Any]) -> None:
    atomic_write_json(output / "CAMPAIGN_SUMMARY.json", payload)


def main() -> None:
    install_stop_signal_handlers()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--start-day", type=int, required=True)
    parser.add_argument("--end-day", type=int, required=True)
    parser.add_argument("--day-workers", type=int, default=1)
    parser.add_argument(
        "--cpu-affinity",
        choices=("none", "disjoint"),
        default="none",
        help="Pin each active day process to a disjoint topology-aware CPU set.",
    )
    parser.add_argument(
        "--diagnostic-steps-per-day",
        type=int,
        help=(
            "Benchmark only: retain the 288-step episode horizon but stop each "
            "diagnostic day after this many committed issues."
        ),
    )
    parser.add_argument("--capture-day-logs", action="store_true")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop all day workers after the first failure, preserving evidence.",
    )
    parser.add_argument("--no-reuse-passed-days", action="store_true")
    parser.add_argument(
        "--reuse-verified-pass-fingerprint",
        action="append",
        default=[],
        help=(
            "Explicitly authorize reuse of a fully gated PASS day produced by "
            "this prior scientific implementation fingerprint. The artifact's "
            "original fingerprint remains recorded in campaign provenance."
        ),
    )
    parser.add_argument(
        "--supplementary-b8-periodic-5min",
        action="store_true",
        help="Run only the post-hoc B8 five-minute periodic timing baseline.",
    )
    parser.add_argument(
        "--diagnostic-method",
        choices=(
            tuple(f"B{index}" for index in range(9))
            + ELECTRICAL_STRESS_METHODS
        ),
        help="Run one method per day for a technical or sensitivity campaign.",
    )
    parser.add_argument(
        "--electrical-stress-campaign",
        action="store_true",
        help="Run the frozen ordered B00-B09 electrical-stress campaign.",
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
        "--risk-calibration",
        type=Path,
        help=(
            "Frozen January B07 electrical-stress event-risk calibration for "
            "calibrated B08/B09 execution."
        ),
    )
    parser.add_argument(
        "--migration-authority",
        type=Path,
        help="Frozen IDC migration authority; defaults to the repository contract.",
    )
    parser.add_argument(
        "--checkpoint-payload-occupancy-factor",
        type=float,
        choices=(0.25, 0.5, 1.0),
        help="January development sensitivity only.",
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
    if args.diagnostic_steps_per_day is not None:
        if args.diagnostic_method is None:
            parser.error("--diagnostic-steps-per-day requires --diagnostic-method")
        if not 1 <= args.diagnostic_steps_per_day < ISSUES_PER_DAY:
            parser.error("--diagnostic-steps-per-day must be in [1, 287]")
    calibrated_method_selected = bool(
        args.supplementary_b8_periodic_5min
        or args.electrical_stress_campaign
        or args.diagnostic_method in {"B7", "B8", "B08", "B09"}
        or args.diagnostic_method is None
    )
    if calibrated_method_selected and args.risk_calibration is None:
        parser.error("--risk-calibration is required before calibrated B7/B8 execution")
    if args.diagnostic_method in {"B6", "B07"} and args.risk_calibration is not None:
        parser.error("raw-risk calibration fitting must not load a calibrated-risk artifact")
    if not 1 <= args.day_workers <= 31:
        parser.error("--day-workers must be in [1, 31]")
    for fingerprint in args.reuse_verified_pass_fingerprint:
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            parser.error(
                "--reuse-verified-pass-fingerprint must be a lowercase SHA-256"
            )

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
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        campaign_lock = acquire_campaign_lock(args.output)
    except CampaignAlreadyRunningError as exc:
        print(f"FAIL_CLOSED_DUPLICATE_CAMPAIGN: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(73) from exc
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
    if args.risk_calibration is not None:
        common.extend(("--risk-calibration", str(args.risk_calibration)))
    for mobility_root in args.mobility_root:
        common.extend(("--mobility-root", str(mobility_root)))
    if args.checkpoint_payload_occupancy_factor is not None:
        common.extend(
            (
                "--checkpoint-payload-occupancy-factor",
                str(args.checkpoint_payload_occupancy_factor),
            )
        )

    summaries: list[Mapping[str, Any]] = []
    first_failure: Mapping[str, Any] | None = None
    pool = ThreadPoolExecutor(max_workers=args.day_workers)
    futures: dict[Future[Mapping[str, Any]], DaySpec] = {}
    try:
        futures = {
            pool.submit(
                run_day_with_affinity_slot,
                spec,
                affinity_slots=affinity_slots,
                repo=args.repo,
                output=args.output,
                common=common,
                capture_day_logs=args.capture_day_logs,
                reuse_passed_days=(
                    not args.no_reuse_passed_days
                    and args.checkpoint_payload_occupancy_factor is None
                ),
                supplementary_b8_periodic_5min=(
                    args.supplementary_b8_periodic_5min
                ),
                diagnostic_method=args.diagnostic_method,
                electrical_stress_campaign=args.electrical_stress_campaign,
                diagnostic_steps_per_day=args.diagnostic_steps_per_day,
                authorized_pass_fingerprints=(
                    args.reuse_verified_pass_fingerprint
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
                    "captured_at_utc": utc_now(),
                    "calendar_date": spec.calendar_date,
                    "start_issue": spec.start_issue,
                    "exception_type": type(exc).__name__,
                    "message": str(exc),
                    "traceback": traceback.format_exc(),
                    "partial_results_preserved": True,
                }
                atomic_write_json(day_root / "ORCHESTRATION_FAILURE.json", failure)
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
                    checkpoint_payload_occupancy_factor=(
                        args.checkpoint_payload_occupancy_factor
                    ),
                    diagnostic_method=args.diagnostic_method,
                    electrical_stress_campaign=args.electrical_stress_campaign,
                    fail_fast=args.fail_fast,
                    cpu_affinity_policy=args.cpu_affinity,
                    cpu_affinity_groups=affinity_groups,
                    diagnostic_steps_per_day=args.diagnostic_steps_per_day,
                    authorized_pass_fingerprints=(
                        args.reuse_verified_pass_fingerprint
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
            if args.fail_fast and row["status"] == "FAIL_CLOSED":
                first_failure = row
                for pending in futures:
                    if pending is not future:
                        pending.cancel()
                stop_active_children(args.output)
                atomic_write_json(
                    args.output / "CAMPAIGN_FAILURE_EVIDENCE.json",
                    {
                        "schema_version": "PFR_CAMPAIGN_FAILURE_EVIDENCE_V1",
                        "status": "FAIL_CLOSED_FIRST_FAILURE_ABORT",
                        "captured_at_utc": utc_now(),
                        "first_failure": row,
                        "completed_results": sorted(
                            summaries, key=lambda item: str(item["calendar_date"])
                        ),
                        "scheduled_dates": [item.calendar_date for item in specs],
                        "active_children_stopped": True,
                        "partial_results_preserved": True,
                    },
                )
                break
    except KeyboardInterrupt:
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
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
                checkpoint_payload_occupancy_factor=(
                    args.checkpoint_payload_occupancy_factor
                ),
                diagnostic_method=args.diagnostic_method,
                electrical_stress_campaign=args.electrical_stress_campaign,
                fail_fast=args.fail_fast,
                cpu_affinity_policy=args.cpu_affinity,
                cpu_affinity_groups=affinity_groups,
                diagnostic_steps_per_day=args.diagnostic_steps_per_day,
                authorized_pass_fingerprints=(
                    args.reuse_verified_pass_fingerprint
                ),
            )
        )
        interrupted["status"] = "INTERRUPTED"
        interrupted["signal"] = received_stop_signal_name()
        write_campaign(args.output, interrupted)
        print(json.dumps({
            "status": "INTERRUPTED",
            "days": len(summaries),
            "output": str(args.output),
        }), flush=True)
        release_campaign_lock(campaign_lock)
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
        checkpoint_payload_occupancy_factor=(
            args.checkpoint_payload_occupancy_factor
        ),
        diagnostic_method=args.diagnostic_method,
        electrical_stress_campaign=args.electrical_stress_campaign,
        fail_fast=args.fail_fast,
        cpu_affinity_policy=args.cpu_affinity,
        cpu_affinity_groups=affinity_groups,
        diagnostic_steps_per_day=args.diagnostic_steps_per_day,
        authorized_pass_fingerprints=args.reuse_verified_pass_fingerprint,
    )
    if first_failure is not None:
        campaign = dict(campaign)
        campaign["status"] = "FAIL_CLOSED"
        campaign["aborted_after_first_failure"] = True
        campaign["first_failure"] = first_failure
    write_campaign(args.output, campaign)
    if campaign["status"] == "PASS" and args.electrical_stress_campaign:
        materialize_period_summary(
            args.output,
            calendar_dates=tuple(spec.calendar_date for spec in specs),
            method_ids=ELECTRICAL_STRESS_METHODS,
        )
    print(json.dumps({"status": campaign["status"], "days": len(summaries), "output": str(args.output)}))
    if campaign["status"] != "PASS":
        release_campaign_lock(campaign_lock)
        raise SystemExit(1)
    release_campaign_lock(campaign_lock)


if __name__ == "__main__":
    main()
