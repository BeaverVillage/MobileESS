"""Show preprocessing-only progress for the April 2025 campaign."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time


def json_value(path: Path, name: str, default: object = None) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get(name, default)
    except (OSError, json.JSONDecodeError):
        return default


def active_phases() -> list[str]:
    if not Path("/proc").is_dir():
        return []
    phases = set()
    for process in Path("/proc").iterdir():
        if not process.name.isdigit() or int(process.name) == os.getpid():
            continue
        try:
            command = " ".join(
                value.decode(errors="replace")
                for value in (process / "cmdline").read_bytes().split(b"\0")
                if value
            )
        except (OSError, PermissionError):
            continue
        if "APR2025_FULL" not in command and "prepare_april_2025" not in command:
            continue
        if "PREPARE_W02_POWER_PRICE_SOURCE.py" in command:
            phases.add("POWER_PRICE")
        elif "PREPARE_W02_MOBILITY_SOURCE.py" in command:
            if "--phase traffic" in command:
                phases.add("MOBILITY_TRAFFIC")
            elif "--phase full" in command:
                phases.add("MOBILITY_FULL")
            else:
                phases.add("MOBILITY")
        elif "prepare_full_month_source_view" in command:
            phases.add("SOURCE_VIEW")
        elif "build_calendar_daily_pre" in command:
            phases.add("DAILY_PRE")
        elif "build_calendar_job_cohort" in command:
            phases.add("JOB_COHORT")
        elif "preflight_full_month_2025" in command:
            phases.add("PREFLIGHT")
        else:
            phases.add("APRIL_PREP_WRAPPER")
    return sorted(phases)


def snapshot(base: Path, contract_path: Path) -> str:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    period = contract["periods"][0]
    period_id = str(period["period_id"])
    input_root = base / f"PFR_{period_id}_V13_13_DAILY_INPUTS"
    shared = base / f"PFR_{period_id}_SHARED_EXOGENOUS_V13_13"

    pre_path = input_root / "pre/DAILY_CANONICAL_PRE_MANIFEST.json"
    jobs_path = input_root / "jobs/INDEPENDENT_JOB_COHORT_AUTHORITY.json"
    pre_status = str(json_value(pre_path, "status", "PENDING"))
    pre_episodes = int(json_value(pre_path, "daily_episode_count", 0) or 0)
    jobs_status = str(json_value(jobs_path, "status", "PENDING"))
    job_count = int(json_value(jobs_path, "authorized_valid_rows", 0) or 0)

    power_blocks = len(
        tuple((shared / "power_price").glob("block_*_*_*/BLOCK_AUTHORITY.json"))
    )
    expected_power_blocks = len(period["power_generation_starts"]) * 4

    mobility_rows = []
    completed_chunks = 0
    total_mobility = 0
    expected_mobility = 0
    for chunk in period["mobility_generation_chunks"]:
        root = (
            base
            / "PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS"
            / period_id
            / str(chunk["start"])
            / "mobility"
        )
        count = len(tuple((root / "mobility_runtime").glob("issue_*.npz")))
        expected = int(chunk["count"])
        authority = root / "REP_WEEK_MOBILITY_FULL_AUTHORITY.json"
        authority_pass = json_value(authority, "status") == "PASS"
        complete = count == expected and authority_pass
        completed_chunks += int(complete)
        total_mobility += count
        expected_mobility += expected
        mobility_rows.append(
            f"  chunk {chunk['start']}: {count}/{expected} "
            f"authority={'PASS' if authority_pass else 'PENDING'}"
        )

    view_count = len(
        tuple((shared / "mobility/mobility_runtime").glob("issue_*.npz"))
    )
    expected_view = int(period["days"]) * 288
    shared_authority = json_value(
        shared / "SHARED_EXOGENOUS_AUTHORITY.json", "status", "PENDING"
    )
    preflight = json_value(
        input_root / "PREFLIGHT_REPORT.json", "status", "PENDING"
    )
    phases = active_phases()
    overall = (
        "PASS_READY_TO_RUN"
        if preflight == "PASS_READY_TO_RUN"
        else ("RUNNING" if phases else "PENDING_OR_STOPPED")
    )

    lines = [
        f"APRIL PREPROCESS: {overall} active={','.join(phases) if phases else 'NONE'}",
        f"INPUT: PRE={pre_status} episodes={pre_episodes}/240 "
        f"JOBS={jobs_status} job_count={job_count}",
        f"POWER: blocks={power_blocks}/{expected_power_blocks}",
        f"MOBILITY: chunks={completed_chunks}/{len(period['mobility_generation_chunks'])} "
        f"artifacts={total_mobility}/{expected_mobility}",
        *mobility_rows,
        f"SOURCE VIEW: mobility={view_count}/{expected_view} "
        f"authority={shared_authority}",
        f"PREFLIGHT: {preflight}",
    ]
    return "\n".join(lines)


def main() -> None:
    repo = Path(__file__).parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        type=Path,
        default=Path("/home/jaewon/mobile_ess_work/frozen_artifacts"),
    )
    parser.add_argument(
        "--period-contract",
        type=Path,
        default=repo / "pfr/contracts/FROZEN_2025_APRIL_VALIDATION_PERIOD_V1.json",
    )
    parser.add_argument("--watch-seconds", type=float, default=10.0)
    args = parser.parse_args()
    while True:
        print(snapshot(args.base, args.period_contract), flush=True)
        if args.watch_seconds <= 0:
            break
        time.sleep(args.watch_seconds)
        print("", flush=True)


if __name__ == "__main__":
    main()
