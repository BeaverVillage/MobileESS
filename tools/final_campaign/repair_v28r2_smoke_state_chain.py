#!/usr/bin/env python3
"""One-time transparent migration for the pre-fix shallow-copy state chain."""

from __future__ import annotations

import json
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.v28r2.backend_contract import canonical_sha256, sha256_file  # noqa: E402
from dayahead.v28r2.day_state import DayState, atomic_json  # noqa: E402


STATE = REPO / "progress/v28r2_non_authority_heavy_smoke/2025-04-01/DAY_STATE.json"
ROOT = REPO / "frozen_artifacts/v28r2_non_authority_heavy_smoke/2025-04-01"
CORRECTION = ROOT / "V28R2_STATE_CHAIN_SHALLOW_COPY_CORRECTION.json"


def main() -> None:
    raw = json.loads(STATE.read_text(encoding="utf-8"))
    old_state_sha = raw["state_sha256"]
    unsigned = {key: value for key, value in raw.items() if key != "state_sha256"}
    if old_state_sha != canonical_sha256(unsigned):
        raise RuntimeError("V28R2_PRECORRECTION_STATE_ROOT_SHA_MISMATCH")
    state = DayState.load(STATE)
    if state.status != "PASS" or len(state.completed_steps) != 30 or state.reusable_prefix_length() == 30:
        raise RuntimeError("V28R2_STATE_CORRECTION_NOT_APPLICABLE")
    file_count = 0
    for step in state.completed_steps:
        for name, record in state.artifacts[step].items():
            path = Path(record["path"])
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                raise RuntimeError(f"V28R2_STATE_CORRECTION_ARTIFACT_TAMPER:{step}:{name}")
            file_count += 1
    old_step_sha = dict(state.step_sha256)
    predecessor = None
    new_step_sha = {}
    for step in state.completed_steps:
        digest = canonical_sha256({
            "step": step,
            "predecessor_sha256": predecessor,
            "artifacts": state.artifacts[step],
            "counters": state.step_counters[step],
        })
        new_step_sha[step] = digest
        predecessor = digest
    state.step_sha256 = new_step_sha
    state.predecessor_sha256 = predecessor
    state.save(STATE)
    repaired = DayState.load(STATE)
    if repaired.reusable_prefix_length() != 30:
        raise RuntimeError("V28R2_STATE_CORRECTION_RESEAL_FAILED")
    correction = {
        "artifact_id": "V28R2_STATE_CHAIN_SHALLOW_COPY_CORRECTION_V1",
        "status": "PASS",
        "scope": "SERIALIZABLE_STATE_METADATA_ONLY",
        "scientific_artifact_bytes_modified": 0,
        "solver_calls_added": 0,
        "OpenDSS_solves_added": 0,
        "root_cause": "DayState.complete_step shallow-copied nested RuntimeLedger snapshot objects",
        "production_fix": "deep copy counters in DayState and detached RuntimeLedger payload snapshots",
        "precorrection_state_sha256": old_state_sha,
        "postcorrection_state_sha256": json.loads(STATE.read_text(encoding="utf-8"))["state_sha256"],
        "artifact_file_sha256_reverified_count": file_count,
        "old_step_sha256": old_step_sha,
        "new_step_sha256": new_step_sha,
        "state_path": str(STATE.resolve()),
    }
    atomic_json(CORRECTION, correction)
    print(json.dumps({
        "status": "PASS", "artifact_files_reverified": file_count,
        "scientific_artifact_bytes_modified": 0,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
