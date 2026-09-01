#!/usr/bin/env python3
"""Process-isolated, resumable V28R2 April campaign supervisor."""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Mapping, Sequence


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v28r2.certificate import verify_certificate  # noqa: E402
from dayahead.v28r2.day_state import atomic_json  # noqa: E402


APRIL_START = date(2025, 4, 1)
APRIL_END = date(2025, 4, 30)
DAY_WORKERS = 2
GUROBI_THREADS = 4
ROOT_SUFFIX = "v28r2_april_full_month_preflight"
READY_FLAGS = REPO / "dayahead/artifacts/v28r2_heavy_backend/V28R2_IMPLEMENTATION_READY_FLAGS.json"
REQUIRED_LAUNCH_GATES = (
    "AUTHORITY_PRECEDENCE_READY",
    "WORKLOAD_ELIGIBILITY_READY",
    "P_REF_LIGHTGBM_READY",
    "G_REF_LIGHTGBM_READY",
    "W_FULLNODE_LIGHTGBM_READY",
    "FULLNODE_ADAPTER_READY",
    "REFERENCE_COMPUTE_SCHEDULE_READY",
    "REFERENCE_DELTA_CLOSURE_READY",
    "OPTIMIZER_CHANNEL_AUTHORITY_READY",
    "APRIL_SOURCE_COVERAGE_READY",
    "C1_AFFINE_CONSERVATISM_READY",
    "C1_AFFINE_ERROR_READY",
    "C1_SURROGATE_LP_COMPATIBLE",
    "C1_SOLVER_BINDING_READY",
    "SOLVER_PRIMAL_PAYLOAD_READY",
    "B3_SOLVER_EQUIVALENCE_READY",
    "DAYAHEAD_SCHEDULE_FREEZE_READY",
    "FRESH_OPENDSS_BACKEND_READY",
    "ACTUAL_FULL_REPLAY_READY",
    "PI_FULL_EXECUTION_READY",
    "MEASURED_RUNTIME_LEDGER_READY",
    "PROCESS_ISOLATION_READY",
    "CERTIFICATE_INTEGRITY_READY",
    "END_TO_END_HEAVY_SMOKE_PASS",
    "APRIL_RUNNER_READY",
)


def april_days() -> tuple[str, ...]:
    count = (APRIL_END - APRIL_START).days + 1
    return tuple((APRIL_START + timedelta(days=offset)).isoformat() for offset in range(count))


def campaign_roots(repo: Path = REPO) -> dict[str, Path]:
    return {
        "frozen_artifacts": repo / "frozen_artifacts" / ROOT_SUFFIX,
        "logs": repo / "logs" / ROOT_SUFFIX,
        "progress": repo / "progress" / ROOT_SUFFIX,
    }


def certificate_path(results_root: Path, day: str) -> Path:
    return results_root / day / f"APRIL_DAY_CERTIFICATE_{day.replace('-', '_')}.json"


def immutable_pass(path: Path, day: str) -> bool:
    if not path.is_file():
        return False
    try:
        payload = verify_certificate(path)
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError):
        return False
    return payload.get("status") == "PASS" and payload.get("day") == day and not payload.get("non_authority_smoke", False)


def verify_launch_gates(path: Path = READY_FLAGS) -> dict[str, object]:
    if not path.is_file():
        raise RuntimeError(f"V28R2_APRIL_LAUNCH_GATE_ARTIFACT_MISSING:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    failed = [gate for gate in REQUIRED_LAUNCH_GATES if payload.get(gate) is not True]
    if failed:
        raise RuntimeError("V28R2_APRIL_LAUNCH_GATES_NOT_READY:" + ",".join(failed))
    if payload.get("APRIL_FULL_MONTH_PREFLIGHT_PASS") is not False:
        raise RuntimeError("V28R2_APRIL_PASS_MUST_BE_FALSE_BEFORE_CAMPAIGN")
    return payload


def process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, PermissionError):
        return False
    return True


def acquire_lock(path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
            old_pid = int(old["pid"])
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            old_pid = -1
        if process_alive(old_pid):
            raise RuntimeError(f"V28R2_APRIL_SUPERVISOR_ALREADY_RUNNING:{old_pid}")
    descriptor = os.open(path, os.O_CREAT | os.O_TRUNC | os.O_WRONLY)
    payload = json.dumps({"pid": os.getpid(), "created_epoch": time.time()}, sort_keys=True).encode("utf-8") + b"\n"
    os.write(descriptor, payload)
    os.close(descriptor)
    return os.getpid()


def release_lock(path: Path, owner_pid: int) -> None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if int(payload.get("pid", -1)) == owner_pid:
        path.unlink(missing_ok=True)


def child_command(day: str, python: str = sys.executable) -> tuple[str, ...]:
    if day not in april_days():
        raise ValueError("V28R2_DAY_OUTSIDE_APRIL")
    return (
        python,
        "-m",
        "dayahead.v28r2.heavy_backend",
        "--campaign",
        "april",
        "--day",
        day,
        "--mode",
        "authority-preflight",
    )


def child_environment(base: Mapping[str, str] | None = None) -> dict[str, str]:
    environment = dict(os.environ if base is None else base)
    environment.update({
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
        "V28R2_DAY_WORKERS": str(DAY_WORKERS),
        "V28R2_GUROBI_THREADS": str(GUROBI_THREADS),
    })
    return environment


@dataclass
class ActiveDay:
    day: str
    process: object
    log_stream: object
    started_epoch: float


PopenFactory = Callable[..., object]


def supervise_commands(
    commands: Sequence[tuple[str, Sequence[str]]],
    roots: Mapping[str, Path],
    *,
    popen_factory: PopenFactory = subprocess.Popen,
    poll_seconds: float = 0.25,
    stop_requested: Callable[[], bool] = lambda: False,
) -> list[dict[str, object]]:
    """Run at most two independent day processes; no solver object is shared."""

    pending = list(commands)
    active: dict[str, ActiveDay] = {}
    results: list[dict[str, object]] = []
    environment = child_environment()
    while pending or active:
        while pending and len(active) < DAY_WORKERS and not stop_requested():
            day, command = pending.pop(0)
            log_path = roots["logs"] / f"{day}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            stream = log_path.open("ab", buffering=0)
            process = popen_factory(
                tuple(command), cwd=REPO, env=environment,
                stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                shell=False,
            )
            active[day] = ActiveDay(day, process, stream, time.time())
        completed: list[str] = []
        for day, record in active.items():
            returncode = record.process.poll()
            if returncode is None:
                continue
            record.log_stream.close()
            results.append({
                "day": day,
                "status": "PASS" if returncode == 0 else "FAIL",
                "returncode": int(returncode),
                "elapsed_seconds": time.time() - record.started_epoch,
            })
            completed.append(day)
        for day in completed:
            del active[day]
        if stop_requested():
            for record in active.values():
                record.process.terminate()
            for record in active.values():
                try:
                    record.process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    record.process.kill()
                    record.process.wait(timeout=10)
                record.log_stream.close()
                results.append({"day": record.day, "status": "INCOMPLETE", "returncode": record.process.returncode})
            active.clear()
            results.extend({"day": day, "status": "PENDING", "returncode": None} for day, _command in pending)
            break
        if active and not completed:
            time.sleep(max(0.01, poll_seconds))
    return sorted(results, key=lambda item: str(item["day"]))


def write_supervisor_snapshot(path: Path, payload: Mapping[str, object]) -> None:
    atomic_json(path, dict(payload))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--day", choices=april_days())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    selected = (args.day,) if args.day else april_days()
    roots = campaign_roots()
    planned: list[tuple[str, tuple[str, ...]]] = []
    skipped: list[str] = []
    for day in selected:
        if immutable_pass(certificate_path(roots["frozen_artifacts"], day), day):
            skipped.append(day)
        else:
            planned.append((day, child_command(day)))
    plan = {
        "campaign": "APRIL_PREFLIGHT",
        "days": list(selected),
        "process_model": "INDEPENDENT_DAY_SUBPROCESS",
        "day_workers": DAY_WORKERS,
        "gurobi_threads_per_child": GUROBI_THREADS,
        "planned": [day for day, _command in planned],
        "skipped_immutable_pass": skipped,
    }
    if args.dry_run:
        print(json.dumps(plan, indent=2))
        return 0
    verify_launch_gates()
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)
    lock_path = roots["progress"] / "campaign.lock"
    owner = acquire_lock(lock_path)
    stop = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)
    snapshot_path = roots["progress"] / "supervisor.json"
    write_supervisor_snapshot(snapshot_path, {**plan, "status": "RUNNING", "pid": os.getpid(), "started_epoch": time.time()})
    try:
        results = supervise_commands(planned, roots, stop_requested=lambda: stop)
        success = all(row["status"] == "PASS" for row in results) and not stop
        write_supervisor_snapshot(snapshot_path, {
            **plan,
            "status": "COMPLETE" if success else "INCOMPLETE",
            "pid": os.getpid(),
            "completed_epoch": time.time(),
            "results": results,
        })
        print(json.dumps({**plan, "results": results}, indent=2))
        return 0 if success else 1
    finally:
        release_lock(lock_path, owner)


if __name__ == "__main__":
    raise SystemExit(main())
