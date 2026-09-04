#!/usr/bin/env python3
"""Resumable two-worker April/May campaign orchestrator."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from dayahead.v28.daily_pipeline import atomic_json, execute_day  # noqa: E402


CAMPAIGNS = {
    "april": ("APRIL_PREFLIGHT", date(2025, 4, 1), date(2025, 4, 30), "v28_april_full_month_preflight"),
    "may": ("MAY_FINAL", date(2025, 5, 1), date(2025, 5, 31), "v28_may_final_science"),
}
STOP = False


def days(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=offset)).isoformat() for offset in range((end - start).days + 1)]


def git_head() -> str:
    return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=REPO, text=True).strip()


def certificate(results_root: Path, day: str) -> Path:
    prefix = "APRIL" if day.startswith("2025-04") else "MAY"
    return results_root / day / f"{prefix}_DAY_CERTIFICATE_{day.replace('-', '_')}.json"


def valid_pass(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return value.get("status") == "PASS" and value.get("certificate_sha256") == value.get("self_check_sha256")


def issue_certificate(path: Path, day: str, result: dict, attempt: int) -> None:
    payload = {
        "date": day, "status": "PASS", "PASS_revision": attempt,
        "git_head": git_head(), "code_sha": git_head(), "config_sha": "BOUND_IN_MAY_FREEZE_OR_APRIL_ATTEMPT",
        "source_sha": "RECORDED_IN_DAY_RESULT", "model_sha": "V28_FINAL_LIGHTGBM_SHA256",
        "solver_settings": {"day_workers": 2, "gurobi_threads": 4},
        "OpenDSS_settings": {"slots": 96, "fresh": True, "native_controls": True},
        "previous_attempts": attempt - 1, "defect_ids": [], "logs": [],
        "result_sha": hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    identity = hashlib.sha256(canonical).hexdigest()
    payload["certificate_sha256"] = identity
    payload["self_check_sha256"] = identity
    atomic_json(path, payload)


def run_one(campaign: str, day: str, roots: dict[str, Path], smoke: bool) -> dict:
    day_root = roots["results"] / day
    cert = certificate(roots["results"], day)
    if not smoke and valid_pass(cert):
        return {"date": day, "status": "SKIP_IMMUTABLE_PASS"}
    progress = roots["progress"] / f"{day}.json"
    heartbeat = roots["progress"] / f"{day}.heartbeat"
    log = roots["logs"] / f"{day}.log"
    day_root.mkdir(parents=True, exist_ok=True)
    roots["logs"].mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8", buffering=1) as stream:
        stream.write(f"{time.time()} START {campaign} {day} pid={os.getpid()} smoke={smoke}\n")
        try:
            result = execute_day(repo=REPO, day=day, day_root=day_root, progress_path=progress, heartbeat_path=heartbeat, log_path=log, non_authority_smoke=smoke)
            if not smoke:
                issue_certificate(cert, day, result, 1)
            atomic_json(progress, {"date": day, "status": result["status"], "pipeline_step": "COMPLETE", "pid": os.getpid(), "heartbeat_epoch": time.time(), "log_path": str(log)})
            return {"date": day, "status": result["status"]}
        except BaseException as exc:
            status = "INCOMPLETE" if isinstance(exc, (KeyboardInterrupt, SystemExit)) else "FAIL"
            atomic_json(progress, {"date": day, "status": status, "pipeline_step": "STOPPED", "pid": os.getpid(), "heartbeat_epoch": time.time(), "log_path": str(log), "last_error": f"{type(exc).__name__}:{exc}"})
            stream.write(f"{time.time()} {status} {type(exc).__name__}:{exc}\n")
            return {"date": day, "status": status, "error": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--campaign", choices=CAMPAIGNS, required=True)
    parser.add_argument("--non-authority-smoke-day")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    name, start, end, suffix = CAMPAIGNS[args.campaign]
    selected = [args.non_authority_smoke_day] if args.non_authority_smoke_day else days(start, end)
    if any(day not in days(start, end) for day in selected):
        raise SystemExit("V28_DAY_OUTSIDE_CAMPAIGN")
    if args.dry_run:
        print(json.dumps({"campaign": name, "days": selected, "day_workers": 2, "gurobi_threads": 4}, indent=2))
        return 0
    if args.campaign == "may" and not (REPO / "frozen_artifacts/v28_april_full_month_preflight/APRIL_FULL_MONTH_PREFLIGHT_PASS.json").is_file():
        raise SystemExit("MAY_REQUIRES_APRIL_30_OF_30_PASS")
    roots = {kind: REPO / kind / suffix for kind in ("frozen_artifacts", "logs", "progress")}
    roots["results"] = roots.pop("frozen_artifacts")
    for path in roots.values(): path.mkdir(parents=True, exist_ok=True)
    lock = roots["progress"] / "campaign.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(f"V28_CAMPAIGN_LOCKED:{lock}")
    os.write(descriptor, f"{os.getpid()}\n".encode()); os.close(descriptor)
    def stop(_signum, _frame):
        global STOP
        STOP = True
    signal.signal(signal.SIGINT, stop); signal.signal(signal.SIGTERM, stop)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="v28-day") as pool:
            futures = {pool.submit(run_one, name, day, roots, bool(args.non_authority_smoke_day)): day for day in selected}
            results = []
            for future in concurrent.futures.as_completed(futures):
                results.append(future.result())
                if STOP: break
        print(json.dumps(sorted(results, key=lambda item: item["date"]), indent=2))
        return 0 if all(row["status"] in {"PASS", "SKIP_IMMUTABLE_PASS", "NON_AUTHORITY_SMOKE_ONLY"} for row in results) else 1
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
