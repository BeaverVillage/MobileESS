"""Show committed January-April progress without speculative time estimates."""

from __future__ import annotations

import argparse
from datetime import date
import json
import os
from pathlib import Path
import time

from pfr.tools.jfm_isolation import load_isolated_run_root
from pfr.tools.show_january_to_march_progress import (
    ELECTRICAL_STRESS_METHODS,
    Period,
    snapshot,
)


def active_phase() -> str:
    phases = set()
    if not Path("/proc").is_dir():
        return "UNKNOWN"
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
        if "run_pfr_matrix" in command:
            phases.add("MONTH_EXECUTION")
        elif "PREPARE_W02_POWER_PRICE_SOURCE.py" in command:
            phases.add("APRIL_POWER_PREPROCESS")
        elif "PREPARE_W02_MOBILITY_SOURCE.py" in command:
            phases.add("APRIL_MOBILITY_PREPROCESS")
        elif "prepare_april_2025" in command:
            phases.add("APRIL_PREPROCESS_WRAPPER")
        elif "audit_january_to_april_consistency" in command:
            phases.add("FINAL_CONSISTENCY_AUDIT")
    return ",".join(sorted(phases)) if phases else "NONE"


def april_source_progress() -> str:
    base = Path("/home/jaewon/mobile_ess_work/frozen_artifacts")
    contract_path = (
        Path(__file__).parents[1]
        / "contracts/FROZEN_2025_APRIL_VALIDATION_PERIOD_V1.json"
    )
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    period = contract["periods"][0]
    period_id = period["period_id"]
    shared = base / f"PFR_{period_id}_SHARED_EXOGENOUS_V13_13"
    power = len(
        tuple((shared / "power_price").glob("block_*_*_*/BLOCK_AUTHORITY.json"))
    )
    chunk_rows = []
    for chunk in period["mobility_generation_chunks"]:
        root = (
            base
            / "PFR_V13_13_FULL_MONTH_SOURCE_CHUNKS"
            / period_id
            / str(chunk["start"])
            / "mobility"
        )
        count = len(tuple((root / "mobility_runtime").glob("issue_*.npz")))
        authority = root / "REP_WEEK_MOBILITY_FULL_AUTHORITY.json"
        authority_pass = False
        try:
            authority_pass = (
                json.loads(authority.read_text(encoding="utf-8")).get("status")
                == "PASS"
            )
        except (OSError, json.JSONDecodeError):
            pass
        chunk_rows.append(
            f"{chunk['start']}={count}/{chunk['count']}"
            f"({'PASS' if authority_pass else 'PENDING'})"
        )
    view = len(tuple((shared / "mobility/mobility_runtime").glob("issue_*.npz")))
    shared_pass = False
    try:
        shared_pass = (
            json.loads(
                (shared / "SHARED_EXOGENOUS_AUTHORITY.json").read_text(
                    encoding="utf-8"
                )
            ).get("status")
            == "PASS"
        )
    except (OSError, json.JSONDecodeError):
        pass
    return (
        f"APRIL PREPROCESS: power_blocks={power}/16 chunks="
        + " ".join(chunk_rows)
        + f" view={view}/8640 authority={'PASS' if shared_pass else 'PENDING'}"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--watch-seconds", type=float, default=10.0)
    args = parser.parse_args()
    authority = load_isolated_run_root(args.run_root)
    run_root = Path(authority["run_root"])
    layout = authority["layout"]
    periods = [
        Period("JANUARY B00-B09", run_root / layout["january_b00_b09"], date(2025, 1, 1), 31, ELECTRICAL_STRESS_METHODS),
        Period("FEBRUARY B00-B09", run_root / layout["february_b00_b09"], date(2025, 2, 1), 28, ELECTRICAL_STRESS_METHODS),
        Period("MARCH B00-B09", run_root / layout["march_b00_b09"], date(2025, 3, 1), 31, ELECTRICAL_STRESS_METHODS),
        Period("APRIL B00-B09", run_root / layout["april_b00_b09"], date(2025, 4, 1), 30, ELECTRICAL_STRESS_METHODS),
    ]
    while True:
        print(
            f"ISOLATED RUN: {run_root} commit={authority['expected_full_commit_sha']} "
            f"phase={active_phase()}",
            flush=True,
        )
        print(april_source_progress(), flush=True)
        print(snapshot(periods), flush=True)
        print("ETA: NOT_REPORTED (commit-based progress only)", flush=True)
        if args.watch_seconds <= 0:
            break
        time.sleep(args.watch_seconds)
        print("", flush=True)


if __name__ == "__main__":
    main()
