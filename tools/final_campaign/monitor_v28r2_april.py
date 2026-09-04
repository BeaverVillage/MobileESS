#!/usr/bin/env python3
"""Strictly read-only V28R2 April campaign monitor."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Mapping

from dayahead.v28r2.backend_contract import DAY_WORKERS, EXECUTION_STEPS, GUROBI_THREADS


REPO = Path(__file__).resolve().parents[2]
ROOT_SUFFIX = "v28r2_april_full_month_preflight"
APRIL_DAYS = tuple(f"2025-04-{day:02d}" for day in range(1, 31))
STEPS_PER_DAY = len(EXECUTION_STEPS)
ISSUES_PER_DAY = 96
TOTAL_ISSUES = len(APRIL_DAYS) * ISSUES_PER_DAY


def issue_progress(completed_steps: int, status: str) -> tuple[int, int]:
    """Map backend-step progress onto the requested 96-issue day scale."""
    if status == "PASS":
        return ISSUES_PER_DAY, ISSUES_PER_DAY
    completed = min(ISSUES_PER_DAY - 1, completed_steps * ISSUES_PER_DAY // STEPS_PER_DAY)
    current = min(ISSUES_PER_DAY, completed + (1 if status == "RUNNING" else 0))
    return completed, current


def roots(repo: Path = REPO) -> dict[str, Path]:
    return {
        "frozen_artifacts": repo / "frozen_artifacts" / ROOT_SUFFIX,
        "logs": repo / "logs" / ROOT_SUFFIX,
        "progress": repo / "progress" / ROOT_SUFFIX,
    }


def read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError) as error:
        return {"_read_error": f"{type(error).__name__}:{error}"}
    return value if isinstance(value, dict) else {"_read_error": "NON_OBJECT_JSON"}


def latest_line(path: Path) -> str | None:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            position = stream.tell()
            buffer = bytearray()
            while position > 0:
                position -= 1
                stream.seek(position)
                character = stream.read(1)
                if character == b"\n" and buffer:
                    break
                if character != b"\n":
                    buffer.extend(character)
            return bytes(reversed(buffer)).decode("utf-8", errors="replace") or None
    except OSError:
        return None


def failure_summary(path: Path) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    prefixes = ("ModuleNotFoundError:", "ImportError:", "RuntimeError:", "ValueError:", "FileNotFoundError:")
    for line in reversed(lines[-300:]):
        concise = line.strip()
        if concise.startswith(prefixes):
            return concise
    return next((line.strip() for line in reversed(lines) if line.strip()), None)


def process_stats(pid: int | None) -> dict[str, float | int | None]:
    if not pid:
        return {"cpu_percent": None, "current_rss_bytes": None}
    try:
        import psutil

        process = psutil.Process(pid)
        return {
            "cpu_percent": process.cpu_percent(interval=0.0),
            "current_rss_bytes": process.memory_info().rss,
        }
    except Exception:
        return {"cpu_percent": None, "current_rss_bytes": None}


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (OSError, PermissionError):
        return False
    return True


def certificate_status(path: Path, day: str) -> tuple[str | None, str | None]:
    payload = read_json(path)
    if not payload:
        return None, None
    stored = payload.get("certificate_sha256")
    try:
        from dayahead.v28r2.certificate import certificate_digest

        valid = stored == certificate_digest(payload)
    except Exception as error:
        return "FAIL", f"CERTIFICATE_VERIFY_ERROR:{error}"
    if valid and payload.get("status") == "PASS" and payload.get("day") == day and not payload.get("non_authority_smoke", False):
        return "PASS", None
    return "FAIL", "INVALID_APRIL_PASS_CERTIFICATE"


def predecessor_status(state: Mapping[str, object]) -> str:
    completed = state.get("completed_steps", [])
    hashes = state.get("step_sha256", {})
    predecessor = state.get("predecessor_sha256")
    if not isinstance(completed, list) or not isinstance(hashes, dict):
        return "INVALID"
    expected = hashes.get(completed[-1]) if completed else None
    return "VERIFIED" if predecessor == expected else "MISMATCH"


def snapshot(
    repo: Path = REPO,
    *,
    active_only: bool = False,
    failed_only: bool = False,
    selected_day: str | None = None,
    now: float | None = None,
) -> dict[str, object]:
    if selected_day is not None and selected_day not in APRIL_DAYS:
        raise ValueError("V28R2_MONITOR_DAY_OUTSIDE_APRIL")
    if active_only and failed_only:
        raise ValueError("V28R2_MONITOR_FILTERS_MUTUALLY_EXCLUSIVE")
    current = time.time() if now is None else now
    paths = roots(repo)
    supervisor = read_json(paths["progress"] / "supervisor.json")
    skipped_days = set(map(str, supervisor.get("skipped_immutable_pass", [])))
    supervisor_results = {
        str(row.get("day")): str(row.get("status"))
        for row in supervisor.get("results", []) if isinstance(row, dict) and row.get("day")
    }
    supervisor_status = str(supervisor.get("status", "WAITING"))
    supervisor_pid_value = supervisor.get("pid")
    supervisor_pid = (
        int(supervisor_pid_value)
        if isinstance(supervisor_pid_value, (int, float)) and supervisor_pid_value > 0 else None
    )
    supervisor_active = supervisor_status == "RUNNING" and process_alive(supervisor_pid)
    planned_days = set(map(str, supervisor.get("planned", [])))
    started_value = supervisor.get("started_epoch")
    supervisor_started = float(started_value) if isinstance(started_value, (int, float)) else None
    rows: list[dict[str, object]] = []
    statuses: list[str] = []
    completed_issues_total = 0
    for day in APRIL_DAYS:
        state_path = paths["progress"] / day / "DAY_STATE.json"
        state = read_json(state_path)
        cert_path = paths["frozen_artifacts"] / day / f"APRIL_DAY_CERTIFICATE_{day.replace('-', '_')}.json"
        cert_status, cert_error = certificate_status(cert_path, day)
        heartbeat_value = state.get("heartbeat_epoch")
        heartbeat = float(heartbeat_value) if isinstance(heartbeat_value, (int, float)) else None
        state_is_current = supervisor_status != "RUNNING" or (
            supervisor_active
            and (supervisor_started is None or (heartbeat is not None and heartbeat >= supervisor_started))
        )
        state_status = state.get("status")
        if cert_status is not None:
            status = cert_status
        elif day in skipped_days:
            status = "PASS"
        elif day in supervisor_results:
            status = supervisor_results[day]
        elif supervisor_status == "RUNNING" and not supervisor_active:
            status = "INCOMPLETE" if day in planned_days else "PENDING"
        elif supervisor_status == "RUNNING" and day not in planned_days:
            status = "PENDING"
        elif not state_is_current:
            status = "PENDING"
        else:
            status = str(state_status) if state_status else "PENDING"
        if status not in {"PENDING", "RUNNING", "PASS", "FAIL", "INCOMPLETE"}:
            status = "INCOMPLETE"
        statuses.append(status)
        effective_state = state if state_is_current else {}
        effective_heartbeat = heartbeat if state_is_current else None
        supervisor_error = (
            "SUPERVISOR_PROCESS_NOT_RUNNING"
            if status == "INCOMPLETE" and supervisor_status == "RUNNING" and not supervisor_active
            else None
        )
        completed_steps = effective_state.get("completed_steps", [])
        completed_step_count = len(completed_steps) if isinstance(completed_steps, list) else 0
        completed_issue_count, current_issue = issue_progress(completed_step_count, status)
        completed_issues_total += min(ISSUES_PER_DAY, completed_issue_count)
        if selected_day is not None and day != selected_day:
            continue
        if active_only and status != "RUNNING":
            continue
        if failed_only and status not in {"FAIL", "INCOMPLETE"}:
            continue
        counters = effective_state.get("counters", {}) if isinstance(effective_state.get("counters"), dict) else {}
        failure = effective_state.get("failure", {}) if isinstance(effective_state.get("failure"), dict) else {}
        pid_value = effective_state.get("pid")
        pid = int(pid_value) if isinstance(pid_value, (int, float)) and pid_value > 0 else None
        log_path = paths["logs"] / f"{day}.log"
        row = {
            "day": day,
            "status": status,
            "skipped_immutable_pass": day in skipped_days,
            "current_step": effective_state.get("current_step"),
            "completed_issues": completed_issue_count,
            "current_issue": current_issue,
            "total_issues": ISSUES_PER_DAY,
            "predecessor_sha_status": predecessor_status(effective_state) if effective_state else "NOT_STARTED",
            "pid": pid,
            "heartbeat_age_seconds": None if effective_heartbeat is None else max(0.0, current - effective_heartbeat),
            **process_stats(pid),
            "peak_rss_bytes": counters.get("peak_rss_bytes"),
            "active_solver": counters.get("active_solver"),
            "objective": counters.get("objective"),
            "incumbent": counters.get("incumbent"),
            "lb": counters.get("lb"),
            "ub": counters.get("ub"),
            "gap": counters.get("gap"),
            "iterations": counters.get("iterations"),
            "optimality_cuts": counters.get("optimality_cuts"),
            "feasibility_cuts": counters.get("feasibility_cuts"),
            "active_opendss_trajectory": counters.get("active_opendss_trajectory"),
            "opendss_slot": counters.get("opendss_slot", 0),
            "latest_log_line": latest_line(log_path),
            "last_error": cert_error or supervisor_error or failure.get("message") or effective_state.get("_read_error") or (failure_summary(log_path) if status in {"FAIL", "INCOMPLETE"} else None),
            "output_path": str((paths["frozen_artifacts"] / day).resolve()),
        }
        rows.append(row)
    counts = {name: statuses.count(name) for name in ("PASS", "FAIL", "RUNNING", "INCOMPLETE", "PENDING")}
    started = supervisor.get("started_epoch")
    elapsed = current - float(started) if isinstance(started, (int, float)) else None
    completed = counts["PASS"] + counts["FAIL"]
    eta = None
    if elapsed is not None and completed > 0 and completed < len(APRIL_DAYS):
        eta = elapsed / completed * (len(APRIL_DAYS) - completed) / DAY_WORKERS
    visible_running = [row for row in rows if row["status"] == "RUNNING"]
    visible_failed = [row for row in rows if row["status"] in {"FAIL", "INCOMPLETE"}]
    campaign_status = (
        "PASS" if counts["PASS"] == len(APRIL_DAYS)
        else "RUNNING" if counts["RUNNING"]
        else "FAIL" if counts["FAIL"] or counts["INCOMPLETE"]
        else "WAITING"
    )
    return {
        "campaign": "APRIL_PREFLIGHT",
        "status": campaign_status,
        "resolution": "15 min / 96 slots",
        "day_workers": DAY_WORKERS,
        "gurobi_threads": GUROBI_THREADS,
        "totals": {
            "total": 30,
            **counts,
            "skipped_immutable_pass": len(skipped_days),
            "elapsed_seconds": elapsed,
            "estimated_completion_seconds": eta,
            "completed_issues": completed_issues_total,
            "total_issues": TOTAL_ISSUES,
            "overall_progress_percent": round(100.0 * completed_issues_total / TOTAL_ISSUES, 2),
            "completed_days_percent": round(100.0 * counts["PASS"] / len(APRIL_DAYS), 2),
        },
        "current": visible_running,
        "failures": visible_failed,
        "days": rows,
        "read_only": True,
    }


def render(value: Mapping[str, object]) -> str:
    totals = value["totals"]
    current = value["current"]
    current_text = ", ".join(
        f"{row['day']} issue {row['current_issue']}/{row['total_issues']}"
        for row in current
    ) or "없음"
    failures = value["failures"]
    if failures:
        first = failures[0]
        fail_text = f"{len(failures)}일 | {first['day']}: {first['last_error'] or '원인 확인 필요'}"
    else:
        fail_text = "없음"
    lines = [
        f"V28R2 APRIL  상태: {value['status']}",
        f"현재 작업: {current_text}",
        f"전체 작업: {totals['completed_issues']}/{totals['total_issues']} issue ({totals['overall_progress_percent']:.2f}%)",
        f"완료 날짜: {totals['PASS']}/30 ({totals['completed_days_percent']:.2f}%)",
        f"FAIL: {fail_text}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--watch-seconds", type=float, default=10.0)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--active-only", action="store_true")
    parser.add_argument("--failed-only", action="store_true")
    parser.add_argument("--day", choices=APRIL_DAYS)
    args = parser.parse_args(argv)
    if args.active_only and args.failed_only:
        parser.error("--active-only and --failed-only are mutually exclusive")
    while True:
        value = snapshot(active_only=args.active_only, failed_only=args.failed_only, selected_day=args.day)
        if not args.json:
            print("\033[2J\033[H", end="")
        print(json.dumps(value, indent=2) if args.json else render(value), flush=True)
        if args.once:
            return 0
        time.sleep(max(1.0, args.watch_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
