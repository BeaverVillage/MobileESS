#!/usr/bin/env python3
"""Semantic fail-closed validator for the C -> D Stage-7 final handoff."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


REQUIRED = [
    "CURRENT_AUTHORITY.json", "C_STAGE7_FINAL_STATUS.json",
    "C_STAGE7_COMPLETION_EVIDENCE.json", "CAUSAL_FRAME_CONTRACT.json",
    "STATESTORE_CONTRACT.json", "PRE_POST_HASH_CONTRACT.json",
    "CHECKPOINT_STATE_SCHEMA.json", "NO_FUTURE_ACTUAL_AUDIT.json",
    "INDEPENDENT_RUNTIME_JOB_AUTHORITY_CONTRACT.json",
    "EVALUATION_BOUNDARY_CONTRACT.json", "RIGHT_CENSORING_STATE_CONTRACT.json",
    "JOB_IDENTITY_CONTRACT.json", "SUPERSESSION_LINEAGE.json",
    "C_STAGE7_TO_D_SUMMARY.json", "SHA256SUMS.txt",
]
EXPECTED_IDS = [
    "W02_2025-01-13", "W07_2025-02-17", "W10_2025-03-10",
    "W17_2025-04-28", "W18_2025-05-05", "W25_2025-06-23",
    "W26_2025-06-30", "W32_2025-08-11", "W38_2025-09-22",
    "W41_2025-10-13", "W44_2025-11-03", "W51_2025-12-22",
]


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
    for rel in REQUIRED:
        if not (root / rel).is_file():
            errors.append(f"missing required file: {rel}")
    if errors:
        return {"status": "FAIL_CLOSED", "errors": errors}
    for line in (root / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, rel = line.split(None, 1)
        path = root / rel.strip().lstrip("*")
        if not path.is_file():
            errors.append(f"SHA target missing: {path.relative_to(root)}")
        elif sha256(path) != expected:
            errors.append(f"SHA mismatch: {path.relative_to(root)}")

    final = load(root / "C_STAGE7_FINAL_STATUS.json")
    summary = load(root / "C_STAGE7_TO_D_SUMMARY.json")
    boundary = load(root / "EVALUATION_BOUNDARY_CONTRACT.json")
    arrival = load(root / "INDEPENDENT_RUNTIME_JOB_AUTHORITY_CONTRACT.json")
    censoring = load(root / "RIGHT_CENSORING_STATE_CONTRACT.json")
    identity = load(root / "JOB_IDENTITY_CONTRACT.json")
    no_future = load(root / "NO_FUTURE_ACTUAL_AUDIT.json")
    parquet = root / str(arrival.get("primary_file", ""))
    if final.get("status") != "15_STAGE_STEP_7_FINAL_PASS":
        errors.append("Stage-7 final status is not PASS")
    if summary.get("stage7_status") != "PASS":
        errors.append("D summary stage7_status != PASS")
    if summary.get("D_R14_change_required") is not False:
        errors.append("D R14 must remain unchanged")
    if boundary.get("controller_burn_in_steps") != 0:
        errors.append("controller burn-in must be zero")
    if boundary.get("selection_window_pre_history_steps") != 576:
        errors.append("selection pre-history must remain 576")
    if boundary.get("initialization_mode") != "DETERMINISTIC_CANONICAL_COLD_START":
        errors.append("canonical cold-start boundary missing")
    if [row.get("candidate_id") for row in boundary.get("episodes", [])] != EXPECTED_IDS:
        errors.append("representative-week evaluation boundary mismatch")
    if arrival.get("source_is_independent_of_job_event") is not True:
        errors.append("F7 arrival authority is not independent")
    if arrival.get("rows") != 59901 or arrival.get("unique_job_uid") != 59901:
        errors.append("F7 arrival authority cardinality mismatch")
    if not parquet.is_file() or sha256(parquet) != arrival.get("primary_file_sha256"):
        errors.append("F7 canonical parquet missing or SHA mismatch")
    if censoring.get("right_censoring") is not True:
        errors.append("right-censoring flag missing")
    if censoring.get("survival_estimator") != "Kaplan–Meier":
        errors.append("survival estimator changed")
    if censoring.get("completed_only_empirical_cdf_allowed") is not False:
        errors.append("completed-only empirical CDF must remain forbidden")
    if identity.get("authoritative_id_field") != "job_uid":
        errors.append("authoritative job ID changed")
    if identity.get("D_job_event_bridge") != "job_event.job_id = str(C.job_uid)":
        errors.append("D job identity bridge changed")
    if no_future.get("future_actual_used") is not False:
        errors.append("future actual used")
    if no_future.get("future_D2_reinjected") is not False:
        errors.append("future D2 reinjected")
    if no_future.get("future_plans_persisted") is not False:
        errors.append("future plans persisted")
    positive = load(root / "fixtures/positive/F7_COVERAGE_FIXTURE.json")
    negative = load(root / "fixtures/negative_missing_log/F7_COVERAGE_FIXTURE.json")
    positive_pass = (
        positive.get("runtime_completion_log_present") is True
        and set(positive.get("completed_job_uids", []))
        | set(positive.get("right_censored_job_uids", []))
        == set(positive.get("expected_job_uids", []))
    )
    negative_fail_closed = (
        negative.get("runtime_completion_log_present") is False
        and negative.get("expected_status") == "FAIL_CLOSED"
    )
    if not positive_pass:
        errors.append("positive F7 coverage fixture failed")
    if not negative_fail_closed:
        errors.append("missing-log negative fixture did not fail closed")
    return {
        "schema_version": "conversation_c.to_d.stage7_zero_burnin_validation.v2",
        "status": "PASS" if not errors else "FAIL_CLOSED",
        "independent_f7_rows": arrival.get("rows"),
        "controller_burn_in_steps": boundary.get("controller_burn_in_steps"),
        "right_censoring": censoring.get("right_censoring"),
        "D_R14_change_required": summary.get("D_R14_change_required"),
        "positive_fixture": "PASS" if positive_pass else "FAIL",
        "negative_missing_log_fixture": "PASS_FAIL_CLOSED" if negative_fail_closed else "FAIL",
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("handoff_root", type=Path)
    args = parser.parse_args()
    result = validate(args.handoff_root.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
