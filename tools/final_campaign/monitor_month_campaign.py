#!/usr/bin/env python3
"""Strictly read-only V28 campaign monitor."""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import date, timedelta
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
CONFIG = {
    "april": ("APRIL_PREFLIGHT", date(2025, 4, 1), 30, "v28_april_full_month_preflight"),
    "may": ("MAY_FINAL", date(2025, 5, 1), 31, "v28_may_final_science"),
}


def dates(start: date, count: int) -> list[str]:
    return [(start + timedelta(days=offset)).isoformat() for offset in range(count)]


def process_stats(pid: int | None) -> dict[str, float | None]:
    if not pid:
        return {"CPU_percent": None, "current_RSS_bytes": None}
    try:
        import psutil
        process = psutil.Process(pid)
        return {"CPU_percent": process.cpu_percent(interval=0.0), "current_RSS_bytes": process.memory_info().rss}
    except Exception:
        return {"CPU_percent": None, "current_RSS_bytes": None}


def snapshot(campaign: str, failed_only: bool, active_only: bool) -> dict:
    name, start, count, suffix = CONFIG[campaign]
    result_root = REPO / "frozen_artifacts" / suffix
    progress_root = REPO / "progress" / suffix
    rows = []
    for day in dates(start, count):
        progress_path = progress_root / f"{day}.json"
        progress = {}
        if progress_path.is_file():
            try: progress = json.loads(progress_path.read_text(encoding="utf-8"))
            except Exception as exc: progress = {"status": "INCOMPLETE", "last_error": f"CORRUPT_PROGRESS:{exc}"}
        prefix = "APRIL" if campaign == "april" else "MAY"
        cert = result_root / day / f"{prefix}_DAY_CERTIFICATE_{day.replace('-', '_')}.json"
        if cert.is_file():
            try:
                certificate = json.loads(cert.read_text(encoding="utf-8"))
                status = "PASS" if certificate.get("status") == "PASS" else "FAIL"
            except Exception: status = "FAIL"
        else:
            status = str(progress.get("status", "PENDING"))
            if status == "NON_AUTHORITY_SMOKE_ONLY": status = "PENDING"
        heartbeat_epoch = float(progress.get("heartbeat_epoch", 0) or 0)
        pid = progress.get("pid")
        row = {
            "date": day, "status": status, "pipeline_step": progress.get("pipeline_step"),
            "B0_status": progress.get("B0_status"), "B1_status": progress.get("B1_status"),
            "B2_status": progress.get("B2_status"), "B3_status": progress.get("B3_status"),
            "solver_name": progress.get("solver_name"), "solver_runtime_seconds": progress.get("solver_runtime_seconds"),
            "iteration_count": progress.get("iteration_count"), "cut_count": progress.get("cut_count"),
            "OpenDSS_slot_progress": progress.get("OpenDSS_slot_progress", 0), "PID": pid,
            **process_stats(int(pid) if pid else None), "peak_RSS_bytes": progress.get("peak_RSS_bytes"),
            "heartbeat_age_seconds": None if not heartbeat_epoch else max(0.0, time.time() - heartbeat_epoch),
            "log_path": progress.get("log_path"), "last_error": progress.get("last_error"),
        }
        if failed_only and status not in {"FAIL", "INCOMPLETE"}: continue
        if active_only and status != "RUNNING": continue
        rows.append(row)
    all_status = []
    for day in dates(start, count):
        progress = progress_root / f"{day}.json"
        prefix = "APRIL" if campaign == "april" else "MAY"
        cert = result_root / day / f"{prefix}_DAY_CERTIFICATE_{day.replace('-', '_')}.json"
        if cert.is_file(): all_status.append("PASS")
        elif progress.is_file():
            try:
                status = json.loads(progress.read_text(encoding="utf-8")).get("status", "PENDING")
                all_status.append("PENDING" if status == "NON_AUTHORITY_SMOKE_ONLY" else status)
            except Exception: all_status.append("INCOMPLETE")
        else: all_status.append("PENDING")
    counts = {status: all_status.count(status) for status in ("PASS", "FAIL", "RUNNING", "INCOMPLETE", "PENDING")}
    completed = counts["PASS"] + counts["FAIL"]
    return {
        "Campaign": name, "Resolution": "15 min / 96 slots", "Day_workers": 2, "Gurobi_threads": 4,
        "Totals": {"total": count, **counts, "elapsed_seconds": None, "estimated_completion_seconds": None if completed == 0 else 0},
        "days": rows, "read_only": True,
    }


def render(value: dict) -> str:
    totals = value["Totals"]
    lines = [f"Campaign: {value['Campaign']}", f"Resolution: {value['Resolution']}", "Day workers: 2", "Gurobi threads: 4",
             "Totals: " + " ".join(f"{key}={totals[key]}" for key in ("total", "PASS", "FAIL", "RUNNING", "INCOMPLETE", "PENDING"))]
    for row in value["days"]:
        lines.append(f"{row['date']} {row['status']} step={row['pipeline_step']} solver={row['solver_name']} OpenDSS={row['OpenDSS_slot_progress']}/96 pid={row['PID']} rss={row['current_RSS_bytes']} heartbeat_age={row['heartbeat_age_seconds']} log={row['log_path']} error={row['last_error']}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", choices=CONFIG, required=True)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--watch-seconds", type=float)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--failed-only", action="store_true")
    parser.add_argument("--active-only", action="store_true")
    args = parser.parse_args()
    if args.failed_only and args.active_only: raise SystemExit("FILTERS_ARE_MUTUALLY_EXCLUSIVE")
    while True:
        value = snapshot(args.campaign, args.failed_only, args.active_only)
        print(json.dumps(value, indent=2) if args.json else render(value), flush=True)
        if args.once or not args.watch_seconds: return 0
        time.sleep(max(1.0, args.watch_seconds))


if __name__ == "__main__": raise SystemExit(main())
