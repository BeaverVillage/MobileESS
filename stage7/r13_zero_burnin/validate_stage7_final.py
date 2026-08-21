#!/usr/bin/env python3
"""Final fail-closed validator for the complete R13 Stage-7 authority."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate(root: Path) -> dict:
    errors: list[str] = []
    required = [
        "C_7_FINAL_STATUS.json", "C_STAGE7_COMPLETION_EVIDENCE.json",
        "CURRENT_AUTHORITY.json", "INITIAL_STATES/INITIAL_STATE_MANIFEST.json",
        "INITIALIZER_BINDING/PRODUCTION_INITIALIZER_BINDING.json",
        "RESTART/RESTART_RESULTS.json", "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json",
        "NO_FUTURE/NO_FUTURE_ACTUAL_AUDIT.json",
        "C_TO_B_FINAL/B_ZERO_BURNIN_VALIDATION_RESULT.json",
        "C_TO_D_FINAL/D_ZERO_BURNIN_VALIDATION_RESULT.json", "SHA256SUMS.txt",
    ]
    for rel in required:
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")
    if errors:
        return {"status": "FAIL_CLOSED", "errors": errors}
    final = load(root / "C_7_FINAL_STATUS.json")
    states = load(root / "INITIAL_STATES/INITIAL_STATE_MANIFEST.json")
    binding = load(root / "INITIALIZER_BINDING/PRODUCTION_INITIALIZER_BINDING.json")
    restart = load(root / "RESTART/RESTART_RESULTS.json")
    actual = load(root / "RESTART/ACTUAL_H0_EVIDENCE_MANIFEST.json")
    no_future = load(root / "NO_FUTURE/NO_FUTURE_ACTUAL_AUDIT.json")
    b_result = load(root / "C_TO_B_FINAL/B_ZERO_BURNIN_VALIDATION_RESULT.json")
    d_result = load(root / "C_TO_D_FINAL/D_ZERO_BURNIN_VALIDATION_RESULT.json")
    if final.get("status") != "15_STAGE_STEP_7_FINAL_PASS":
        errors.append("final status is not PASS")
    if len(states.get("files", [])) != 12 or not states.get("status", "").startswith("PASS_12_OF_12"):
        errors.append("canonical initial states are not 12/12 PASS")
    if binding.get("actual_h0_subset_pending") is not False:
        errors.append("production binding still marks h0 subset pending")
    if restart.get("status") != "PASS" or restart.get("pass_count") != 4:
        errors.append("restart result is not 4/4 PASS")
    if actual.get("status") != "PASS_4_OF_4":
        errors.append("portable actual h0 evidence is not 4/4 PASS")
    for row in actual.get("results", []):
        if float(row.get("certified_mip_gap", 1.0)) > 0.03:
            errors.append(f"{row.get('candidate_id')}: certified gap exceeds 3%")
        if row.get("hash_exact") is not True or row.get("fresh_exact_opendss_pass") is not True:
            errors.append(f"{row.get('candidate_id')}: restart/OpenDSS evidence failed")
    for key in ("future_actual_used", "future_D2_reinjected", "future_plans_persisted"):
        if no_future.get(key) is not False:
            errors.append(f"no-future audit failed: {key}")
    if b_result.get("status") != "PASS":
        errors.append("B validator is not PASS")
    if d_result.get("status") != "PASS":
        errors.append("D validator is not PASS")
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(None, 1)
        path = root / rel.strip().lstrip("*")
        if not path.is_file() or sha256(path) != expected:
            errors.append(f"root SHA mismatch/missing: {rel.strip()}")
    return {
        "schema_version": "conversation_c.stage7.r13.final_validation.v1",
        "status": "PASS" if not errors else "FAIL_CLOSED",
        "canonical_pre_states": len(states.get("files", [])),
        "restart_pass_count": restart.get("pass_count"),
        "actual_gurobi_executions": actual.get("total_gurobi_executed_transitions"),
        "actual_opendss_executions": actual.get("total_opendss_executed_transitions"),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("authority_root", type=Path)
    args = parser.parse_args()
    result = validate(args.authority_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
