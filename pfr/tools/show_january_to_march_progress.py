"""Show compact progress for the full January plus frozen February/March weeks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date, timedelta
import json
import os
from pathlib import Path
import time

from pfr.tools.jfm_isolation import load_isolated_run_root


ELECTRICAL_STRESS_METHODS = tuple(f"B{index:02d}" for index in range(10))
# Historical exports remain import-compatible for analysis tools that only read
# old campaigns.  New progress views use ELECTRICAL_STRESS_METHODS exclusively.
MAIN_METHODS = tuple(f"B{index}" for index in range(8))
B8_METHODS = ("B8",)


@dataclass(frozen=True)
class Period:
    label: str
    root: Path
    start: date
    days: int
    methods: tuple[str, ...]


def active_outputs() -> set[Path]:
    if not Path("/proc").is_dir():
        return set()
    outputs: set[Path] = set()
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            argv = [
                value.decode(errors="replace")
                for value in (process / "cmdline").read_bytes().split(b"\0")
                if value
            ]
        except (OSError, PermissionError):
            continue
        if "pfr.tools.run_pfr_matrix" not in argv:
            continue
        try:
            index = argv.index("--output")
            outputs.add(Path(argv[index + 1]).resolve())
        except (ValueError, IndexError, OSError):
            continue
    return outputs


def json_status(path: Path) -> str | None:
    try:
        return str(json.loads(path.read_text(encoding="utf-8")).get("status"))
    except (OSError, json.JSONDecodeError):
        return None


def inspect_day(
    day_root: Path, active: bool, methods: tuple[str, ...]
) -> tuple[str, int, list[str], dict[str, int]]:
    summary_path = day_root / "MATRIX_SUMMARY.json"
    if summary_path.is_file():
        summary_status = json_status(summary_path)
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            done = int(summary.get("valid_commit_markers", 0))
            failed = [str(value) for value in summary.get("failed_methods", ())]
            counts = {
                str(row.get("comparison_method_id")): int(
                    row.get("commit_marker_count", 0)
                )
                for row in summary.get("method_summaries", ())
            }
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return "CORRUPT_SUMMARY", 0, [], {}
        return (
            "PASS" if summary_status == "PASS" else "COMPLETE_WITH_FAILURE"
        ), done, failed, counts
    counts = {
        method: len(tuple((day_root / method).glob("issue_*/COMMIT_MARKER.json")))
        for method in methods
    }
    failed = [
        method
        for method in methods
        if (day_root / method / "FAILURE.json").is_file()
    ]
    if (day_root / "ORCHESTRATION_FAILURE.json").is_file():
        failed.append("ORCHESTRATION")
    if active:
        status = "RUNNING_WITH_RECORDED_FAILURE" if failed else "RUNNING"
    elif day_root.exists() and (sum(counts.values()) or failed):
        status = "INCOMPLETE_WITH_RECORDED_FAILURE" if failed else "INCOMPLETE"
    else:
        status = "PENDING"
    return status, sum(counts.values()), failed, counts


def snapshot(periods: list[Period]) -> str:
    active = active_outputs()
    lines: list[str] = []
    grand_done = grand_expected = grand_pass_days = grand_fail_days = 0
    for period in periods:
        expected_per_day = 288 * len(period.methods)
        rows = []
        for offset in range(period.days):
            calendar_date = period.start + timedelta(days=offset)
            day_root = period.root / calendar_date.isoformat()
            rows.append(
                (
                    calendar_date.isoformat(),
                    *inspect_day(
                        day_root,
                        day_root.resolve() in active,
                        period.methods,
                    ),
                )
            )
        done = sum(row[2] for row in rows)
        expected = period.days * expected_per_day
        pass_days = sum(row[1] == "PASS" for row in rows)
        fail_days = sum("FAIL" in row[1] for row in rows)
        running = [row for row in rows if row[1].startswith("RUNNING")]
        latest = running or [row for row in rows if row[1] != "PENDING"][-1:]
        lines.append(
            f"{period.label}: {done}/{expected} ({100.0 * done / expected:5.1f}%) "
            f"PASS_days={pass_days}/{period.days} failure_days={fail_days}"
        )
        for calendar_date, status, markers, failed, counts in latest:
            suffix = f" failed={','.join(failed)}" if failed else ""
            method_progress = " ".join(
                f"{method}={counts.get(method, 0):03d}"
                for method in period.methods
            )
            lines.append(
                f"  {calendar_date} {markers}/{expected_per_day} {status}{suffix} "
                f"{method_progress}"
            )
        grand_done += done
        grand_expected += expected
        grand_pass_days += pass_days
        grand_fail_days += fail_days
    lines.append(
        f"TOTAL: {grand_done}/{grand_expected} ({100.0 * grand_done / grand_expected:5.1f}%) "
        f"PASS_days={grand_pass_days}/{sum(period.days for period in periods)} "
        f"failure_days={grand_fail_days} active_days="
        f"{sum(row.resolve() in active for period in periods for row in (period.root / ((period.start + timedelta(days=offset)).isoformat()) for offset in range(period.days)))}"
    )
    return "\n".join(lines)


def source_progress() -> str:
    base = Path("/home/jaewon/mobile_ess_work/frozen_artifacts")
    contract_path = (
        Path(__file__).parents[1]
        / "contracts/FROZEN_2025_FULL_MONTH_VALIDATION_PERIODS_V1.json"
    )
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "SOURCES: contract unavailable"
    lines = []
    total_power_blocks = 0
    expected_power_blocks = 0
    total_generated_mobility = 0
    expected_generated_mobility = 0
    completed_chunks = 0
    expected_chunks = 0
    completed_authorities = 0
    for period in contract["periods"]:
        period_id = period["period_id"]
        shared = base / f"PFR_{period_id}_SHARED_EXOGENOUS_V13_13"
        blocks = len(
            tuple((shared / "power_price").glob("block_*_*_*/BLOCK_AUTHORITY.json"))
        )
        generated_counts = []
        for chunk in period["mobility_generation_chunks"]:
            root = (
                base
                / "PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS"
                / period_id
                / str(chunk["start"])
                / "mobility/mobility_runtime"
            )
            generated_counts.append(len(tuple(root.glob("issue_*.npz"))))
        view_count = len(
            tuple((shared / "mobility/mobility_runtime").glob("issue_*.npz"))
        )
        authority = (shared / "SHARED_EXOGENOUS_AUTHORITY.json").is_file()
        total_power_blocks += blocks
        expected_power_blocks += 16
        total_generated_mobility += sum(generated_counts)
        expected_generated_mobility += sum(
            int(chunk["count"]) for chunk in period["mobility_generation_chunks"]
        )
        completed_chunks += sum(
            count == int(chunk["count"])
            for count, chunk in zip(
                generated_counts, period["mobility_generation_chunks"]
            )
        )
        expected_chunks += len(period["mobility_generation_chunks"])
        completed_authorities += int(authority)
        lines.append(
            f"SOURCE {period_id}: power_blocks={blocks}/16 "
            f"generated_mobility="
            + ",".join(
                f"{count}/{chunk['count']}"
                for count, chunk in zip(
                    generated_counts, period["mobility_generation_chunks"]
                )
            )
            + f" view={view_count}/{period['days'] * 288} authority={'PASS' if authority else 'PENDING'}"
        )
    lines.append(
        f"PREPROCESS TOTAL: chunks={completed_chunks}/{expected_chunks} "
        f"mobility_artifacts={total_generated_mobility}/{expected_generated_mobility} "
        f"power_blocks={total_power_blocks}/{expected_power_blocks} "
        f"month_authorities={completed_authorities}/{len(contract['periods'])}"
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--watch-seconds", type=float, default=10.0)
    args = parser.parse_args()
    authority = load_isolated_run_root(args.run_root)
    run_root = Path(authority["run_root"])
    layout = authority["layout"]
    periods = [
        Period(
            "JANUARY B00-B09",
            run_root / layout["january_b00_b09"],
            date(2025, 1, 1),
            31,
            ELECTRICAL_STRESS_METHODS,
        ),
        Period(
            "FEBRUARY B00-B09",
            run_root / layout["february_b00_b09"],
            date(2025, 2, 1),
            28,
            ELECTRICAL_STRESS_METHODS,
        ),
        Period(
            "MARCH B00-B09",
            run_root / layout["march_b00_b09"],
            date(2025, 3, 1),
            31,
            ELECTRICAL_STRESS_METHODS,
        ),
    ]
    print(
        f"ISOLATED RUN: {run_root} "
        f"commit={authority['expected_full_commit_sha']} "
        f"branch={authority['expected_branch']}",
        flush=True,
    )
    while True:
        print(source_progress(), flush=True)
        print(snapshot(periods), flush=True)
        if args.watch_seconds <= 0:
            break
        time.sleep(args.watch_seconds)
        print("", flush=True)


if __name__ == "__main__":
    main()
