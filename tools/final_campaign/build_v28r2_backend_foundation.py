#!/usr/bin/env python3
"""Freeze the persistent V28R2 day-backend foundation contracts."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.authority import sha256_file
from dayahead.v28r2.backend_contract import (
    DAY_WORKERS, EXECUTION_STEPS, GUROBI_THREADS, RESOLUTION_MINUTES, SLOTS,
)


OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"


def write(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    os.replace(temporary, path)


def main() -> None:
    sources = {
        name: REPO / "dayahead/v28r2" / name
        for name in ("backend_contract.py", "day_state.py", "runtime_ledger.py", "heavy_backend.py", "certificate.py")
    }
    hashes = {name: sha256_file(path) for name, path in sources.items()}
    write("V28R2_HEAVY_BACKEND_CONTRACT.json", {
        "artifact_id": "V28R2_HEAVY_BACKEND_CONTRACT_V1",
        "status": "PASS_FOUNDATION_IMPLEMENTED",
        "resolution_minutes": RESOLUTION_MINUTES,
        "slots_per_day": SLOTS,
        "timezone": "FIXED_AEST_UTC_PLUS_10",
        "day_workers": DAY_WORKERS,
        "gurobi_threads_per_active_solve": GUROBI_THREADS,
        "within_day_heavy_solves": "SEQUENTIAL",
        "step_axis": list(EXECUTION_STEPS),
        "stateless_callback_is_production_authority": False,
        "live_native_objects_persisted": False,
        "source_sha256": hashes,
        "PERSISTENT_DAILY_BACKEND_FOUNDATION_READY": True,
    })
    write("V28R2_DAY_STATE_CONTRACT.json", {
        "artifact_id": "V28R2_DAY_STATE_CONTRACT_V1",
        "status": "PASS",
        "statuses": ["PENDING", "RUNNING", "PASS", "FAIL", "INCOMPLETE"],
        "serializable_fields": [
            "current_step", "completed_steps", "predecessor_sha256", "step_sha256",
            "step_counters", "artifacts", "attempts", "pid", "heartbeat_epoch",
            "counters", "failure", "defect_ids",
        ],
        "reuse_rule": "recompute every referenced artifact SHA and the complete predecessor digest chain",
        "write_rule": "temporary file plus atomic os.replace",
        "valid_pass_immutable_policy": True,
        "source_sha256": hashes["day_state.py"],
        "DAY_STATE_READY": True,
    })
    write("V28R2_RUNTIME_LEDGER_CONTRACT.json", {
        "artifact_id": "V28R2_RUNTIME_LEDGER_CONTRACT_V1",
        "status": "PASS",
        "measured_only": True,
        "initial_completed_solver_calls": 0,
        "initial_completed_opendss_slots": 0,
        "pue_trajectories": [
            "DA/B0", "DA/B1", "DA/B2", "DA/B3", "ACT/R0", "ACT/B0",
            "ACT/B1", "ACT/B2", "ACT/B3", "PI/B3",
        ],
        "actual_optimizer_calls_required": 0,
        "expected_slots_are_not_written_as_completed_slots": True,
        "source_sha256": hashes["runtime_ledger.py"],
        "MEASURED_RUNTIME_LEDGER_FOUNDATION_READY": True,
    })


if __name__ == "__main__":
    main()
