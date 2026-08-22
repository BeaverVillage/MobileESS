"""Print compact progress for a January independent-day campaign."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time


METHODS = tuple(f"B{index}" for index in range(8))
EXPECTED_PER_DAY = 288 * len(METHODS)


def inspect_day(root: Path) -> dict[str, object]:
    counts = {
        method: len(tuple((root / method).glob("issue_*/COMMIT_MARKER.json")))
        for method in METHODS
    }
    completed = sum(counts.values())
    summary_path = root / "MATRIX_SUMMARY.json"
    status = "RUNNING" if completed else "PENDING"
    if summary_path.is_file():
        try:
            status = "PASS" if json.loads(summary_path.read_text(encoding="utf-8")).get("status") == "PASS" else "FAIL"
        except (OSError, json.JSONDecodeError):
            status = "FAIL"
    elif any((root / method / "FAILURE.json").is_file() for method in METHODS):
        status = "FAIL"
    return {"completed": completed, "status": status}


def snapshot(root: Path, start_day: int, end_day: int) -> str:
    rows = []
    for day in range(start_day, end_day + 1):
        info = inspect_day(root / f"2025-01-{day:02d}")
        rows.append((day, int(info["completed"]), str(info["status"])))
    total = sum(row[1] for row in rows)
    expected = EXPECTED_PER_DAY * len(rows)
    failures = sum(row[2] == "FAIL" for row in rows)
    overall = "FAIL" if failures else ("PASS" if total == expected else "RUNNING")
    visible = [row for row in rows if row[2] in {"RUNNING", "FAIL"}]
    if not visible:
        completed_rows = [row for row in rows if row[2] == "PASS"]
        visible = completed_rows[-1:] if completed_rows else rows[:1]
    lines = [
        f"day {day:02d}/{end_day:02d} | {done}/{EXPECTED_PER_DAY} | "
        f"{100.0 * done / EXPECTED_PER_DAY:5.1f}% | {status}"
        for day, done, status in visible
    ]
    lines.append(
        f"total | {total}/{expected} | {100.0 * total / expected:5.1f}% | "
        f"{overall} | fail_days={failures}"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--start-day", type=int, default=1)
    parser.add_argument("--end-day", type=int, default=31)
    parser.add_argument("--watch-seconds", type=float, default=0.0)
    args = parser.parse_args()
    while True:
        print(snapshot(args.root, args.start_day, args.end_day), flush=True)
        if args.watch_seconds <= 0:
            break
        time.sleep(args.watch_seconds)
        print("", flush=True)


if __name__ == "__main__":
    main()
