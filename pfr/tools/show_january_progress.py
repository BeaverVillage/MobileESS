"""Print compact progress for a January independent-day campaign."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time


METHODS = tuple(f"B{index}" for index in range(8))
EXPECTED_PER_DAY = 288 * len(METHODS)


def active_matrix_outputs() -> set[Path]:
    """Return output roots of live matrix children (Linux/WSL only)."""
    proc = Path("/proc")
    if not proc.is_dir():
        return set()
    active: set[Path] = set()
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            arguments = (entry / "cmdline").read_bytes().split(b"\0")
            argv = [item.decode(errors="replace") for item in arguments if item]
        except (OSError, PermissionError):
            continue
        if "pfr.tools.run_pfr_matrix" not in argv:
            continue
        for index, argument in enumerate(argv):
            if argument == "--output" and index + 1 < len(argv):
                active.add(Path(argv[index + 1]).resolve())
            elif argument.startswith("--output="):
                active.add(Path(argument.split("=", 1)[1]).resolve())
    return active


def inspect_day(root: Path, *, active: bool = False) -> dict[str, object]:
    counts = {
        method: len(tuple((root / method).glob("issue_*/COMMIT_MARKER.json")))
        for method in METHODS
    }
    completed = sum(counts.values())
    summary_path = root / "MATRIX_SUMMARY.json"
    status = "RUNNING" if active else ("INCOMPLETE" if root.exists() else "PENDING")
    if summary_path.is_file():
        try:
            status = "PASS" if json.loads(summary_path.read_text(encoding="utf-8")).get("status") == "PASS" else "FAIL"
        except (OSError, json.JSONDecodeError):
            status = "FAIL"
    elif (root / "ORCHESTRATION_FAILURE.json").is_file():
        status = "FAIL"
    elif any((root / method / "FAILURE.json").is_file() for method in METHODS):
        status = "RUNNING_WITH_FAILURE" if active else "INCOMPLETE_WITH_FAILURE"
    return {"completed": completed, "status": status, "counts": counts}


def snapshot(root: Path, start_day: int, end_day: int) -> str:
    active_outputs = active_matrix_outputs()
    rows = []
    for day in range(start_day, end_day + 1):
        day_root = root / f"2025-01-{day:02d}"
        info = inspect_day(day_root, active=day_root.resolve() in active_outputs)
        rows.append((day, int(info["completed"]), str(info["status"]), info["counts"]))
    total = sum(row[1] for row in rows)
    expected = EXPECTED_PER_DAY * len(rows)
    failures = sum(row[2] == "FAIL" for row in rows)
    active_failures = sum(row[2] == "RUNNING_WITH_FAILURE" for row in rows)
    incomplete_failures = sum(row[2] == "INCOMPLETE_WITH_FAILURE" for row in rows)
    incomplete = sum(row[2] == "INCOMPLETE" for row in rows)
    running = sum(row[2] == "RUNNING" for row in rows)
    overall = (
        "FAIL"
        if failures
        else (
            "RUNNING_WITH_FAILURE"
            if active_failures
            else (
                "RUNNING"
                if running
                else (
                    "INCOMPLETE_WITH_FAILURE"
                    if incomplete_failures
                    else (
                        "INCOMPLETE"
                        if incomplete
                        else ("PASS" if total == expected else "PENDING")
                    )
                )
            )
        )
    )
    visible = [
        row for row in rows
        if row[2]
        in {
            "RUNNING",
            "RUNNING_WITH_FAILURE",
            "INCOMPLETE",
            "INCOMPLETE_WITH_FAILURE",
            "FAIL",
        }
    ]
    if not visible:
        completed_rows = [row for row in rows if row[2] == "PASS"]
        visible = completed_rows[-1:] if completed_rows else rows[:1]
    lines = [
        f"day {day:02d}/{end_day:02d} | {done}/{EXPECTED_PER_DAY} | "
        f"{100.0 * done / EXPECTED_PER_DAY:5.1f}% | {status} | "
        + " ".join(f"{method}={counts[method]:03d}" for method in METHODS)
        for day, done, status, counts in visible
    ]
    lines.append(
        f"total | {total}/{expected} | {100.0 * total / expected:5.1f}% | "
        f"{overall} | fail_days={failures} | active_fail_days={active_failures} | "
        f"incomplete_days={incomplete + incomplete_failures}"
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
