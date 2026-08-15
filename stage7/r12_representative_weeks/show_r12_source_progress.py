#!/usr/bin/env python3
"""Show concise R12 source-cache progress without process or worker IDs."""

from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_CACHE = Path("/home/jaewon/mobile_ess_work/stage7_r12_common_mobility_cache_2025")


def duration(seconds: float | None) -> str:
    if seconds is None or not math.isfinite(seconds) or seconds < 0:
        return "unknown"
    whole = int(round(seconds))
    days, whole = divmod(whole, 86400)
    hours, whole = divmod(whole, 3600)
    minutes, seconds = divmod(whole, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours or days:
        parts.append(f"{hours}h")
    if minutes or hours or days:
        parts.append(f"{minutes}m")
    parts.append(f"{seconds}s")
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args()
    progress_path = args.cache / "R12_COMMON_MOBILITY_PROGRESS.json"
    index_path = args.cache / "R12_COMMON_MOBILITY_INDEX.partial.csv"

    progress = {}
    if progress_path.is_file():
        progress = json.loads(progress_path.read_text(encoding="utf-8"))

    completed = int(progress.get("completed_issue_count", 0))
    if index_path.is_file():
        with index_path.open("r", encoding="utf-8", newline="") as stream:
            completed = max(0, sum(1 for _ in stream) - 1)
    required = int(progress.get("required_issue_count", 6912))
    percent = 100.0 * completed / required if required else 100.0

    artifacts = sorted(
        (args.cache / "mobility_runtime").glob("issue_*.npz"),
        key=lambda path: path.stat().st_mtime,
    ) if (args.cache / "mobility_runtime").is_dir() else []
    recent = artifacts[-101:]
    rate_per_minute = None
    eta_seconds = None
    idle_seconds = None
    if recent:
        now = datetime.now(timezone.utc).timestamp()
        idle_seconds = max(0.0, now - recent[-1].stat().st_mtime)
    if len(recent) >= 2:
        elapsed = recent[-1].stat().st_mtime - recent[0].stat().st_mtime
        if elapsed > 0:
            rate_per_minute = 60.0 * (len(recent) - 1) / elapsed
            eta_seconds = 60.0 * max(0, required - completed) / rate_per_minute

    print(f"STATUS={progress.get('status', 'NOT_STARTED')}")
    print(f"COMPLETED={completed}/{required} ({percent:.2f}%)")
    print(f"LAST_ISSUE={progress.get('last_completed_issue', 'unknown')}")
    print(f"RATE_RECENT={rate_per_minute:.2f} issues/min" if rate_per_minute else "RATE_RECENT=unknown")
    print(f"ETA_RECENT={duration(eta_seconds)}")
    print(f"IDLE_SINCE_LAST_COMMIT={duration(idle_seconds)}")
    print(f"CPU_WORKERS={progress.get('cpu_worker_count', 'unknown')}")
    print(f"SAFE_FALLBACK_ROWS={progress.get('unseen_safe_horizon_fallback_rows', 0)}")
    print(f"SAFE_FALLBACK_STEPS={progress.get('unseen_safe_horizon_steps', [])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
