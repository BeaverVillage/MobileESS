"""Materialize the fail-closed V17 external H100 final review."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from .authority import sha256_file
from .v17_external_h100_forensic import write_json, zero_counters


DISCOVERY_COMMIT = "9416e059f4f36f8a99bef037b825cff6a04b77a2"
IDENTIFIABILITY_COMMIT = "3b5fc81"
FINAL_CLASSIFICATION = "V17_AIDC_POWER_V3_E_EXTERNAL_POWER_NOT_IDENTIFIABLE"


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def materialize(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); output = output.resolve()
    names = [
        "V17_AIDC_POWER_V3_EXTERNAL_PRECHANGE_MANIFEST.json",
        "V17_EXTERNAL_H100_DATASET_DISCOVERY.json",
        "V17_EXTERNAL_H100_SOURCE_AUTHORITY_MANIFEST.json",
        "V17_EXTERNAL_H100_HARDWARE_COMPATIBILITY.json",
        "V17_EXTERNAL_H100_SCHEMA_AUDIT.json",
        "V17_Kestrel_U2_SHARING_SEMANTICS_AUDIT.json",
        "V17_SCIENTIFIC_DATA_H100_POWER_RESPONSE_AUDIT.json",
        "V17_EUROSYS_H100_SHARING_POWER_AUDIT.json",
        "V17_AIDC_POWER_V3_EXTERNAL_ACCEPTANCE_CONTRACT.json",
        "V17_EXTERNAL_H100_CROSS_DATASET_CONSISTENCY.json",
        "V17_AIDC_POWER_V3_COHORT_IDENTIFIABILITY.json",
        "V17_AIDC_POWER_MODEL_V3_EXTERNAL_CONTRACT.json",
        "V17_AIDC_POWER_MODEL_V3_EXTERNAL_VALIDATION.json",
        "V17_AIDC_POWER_V1_V3_COVERAGE_COMPARISON.json",
    ]
    artifacts = {name: load(output / name) for name in names}
    hashes = {
        name: {"bytes": (output / name).stat().st_size, "sha256": sha256_file(output / name)}
        for name in names
    }
    discovery = artifacts["V17_EXTERNAL_H100_DATASET_DISCOVERY.json"]
    compatibility = artifacts["V17_EXTERNAL_H100_HARDWARE_COMPATIBILITY.json"]
    u2 = artifacts["V17_Kestrel_U2_SHARING_SEMANTICS_AUDIT.json"]
    science = artifacts["V17_SCIENTIFIC_DATA_H100_POWER_RESPONSE_AUDIT.json"]
    cohort = artifacts["V17_AIDC_POWER_V3_COHORT_IDENTIFIABILITY.json"]
    coverage = artifacts["V17_AIDC_POWER_V1_V3_COVERAGE_COMPARISON.json"]
    acceptance = artifacts["V17_AIDC_POWER_V3_EXTERNAL_ACCEPTANCE_CONTRACT.json"]
    ac = load(output / "V17_AC_RESTORATION_7DAY_REGRESSION.json")
    contract = artifacts["V17_AIDC_POWER_MODEL_V3_EXTERNAL_CONTRACT.json"]

    final = {
        "artifact_id": "V17_AIDC_POWER_V3_EXTERNAL_FINAL_REVIEW_V1",
        "status": "V17_AIDC_POWER_V3_EXTERNAL_NOT_AUTHORIZED",
        "primary_classification": FINAL_CLASSIFICATION,
        "U1_CLASSIFICATION": cohort["classifications"]["U1"],
        "U2_CLASSIFICATION": cohort["classifications"]["U2"],
        "U3_CLASSIFICATION": cohort["classifications"]["U3"],
        "start_gate": {
            "required_scientific_head": "0c441f1a8eb2b851fb6bf4bc7c3fde26f543970a",
            "clean_worktree_before_external_work": True,
            "prechange_manifest_sha256": hashes["V17_AIDC_POWER_V3_EXTERNAL_PRECHANGE_MANIFEST.json"]["sha256"],
        },
        "external_sources": discovery["datasets"],
        "hardware_and_boundary_compatibility": {
            "relationships": compatibility["relationships"],
            "absolute_external_kW_may_replace_Dataset312_kappa": False,
        },
        "Kestrel_U2": {
            "jobs": u2["U2_jobs"],
            "node_equivalent_hours": u2["U2_node_equivalent_hours"],
            "meaning": u2["entry_rule"],
            "observables": u2["observables"],
            "EuroSys_transfer": u2["external_semantic_transfer_classification"],
        },
        "Scientific_Data_role": {
            "improves_independent_H100_physical_response_authority": science["improves_H100_physical_power_authority"],
            "permitted_role": science["permitted_role"],
            "utilization_power_correlation": science["P_GPU_vs_GPU_utilization"]["pearson_correlation"],
            "unique_H100_sessions": science["unique_H100_sessions_by_CRC32"],
            "shared_job_attribution_authority": False,
        },
        "cohort_recovery": {
            "potential_unmodeled": {row["group"]: row for row in cohort["groups"]},
            "authorized_recoverable_node_equivalent_hours": cohort["recoverable_node_equivalent_hours"],
        },
        "coverage": {
            "V1": coverage["V1_coverage_fraction"],
            "potential_V3": coverage["V3_coverage_fraction"],
            "incremental": coverage["incremental_coverage_fraction"],
            "remaining_unmodeled": coverage["remaining_unmodeled_fraction"],
        },
        "candidate_models": {
            "equations": contract["candidate_equations_not_authorized"],
            "authorized": False,
            "reason": contract["reason"],
        },
        "held_out_validation": {
            "metrics": None,
            "fit_calls": 0,
            "reason": acceptance["status"],
            "prospective_numerical_threshold": None,
        },
        "V3_authority_minted": False,
        "RCMQT_V3": {"required": False, "performed": False, "reason": "No expanded active power boundary."},
        "same_7day_V3_science": {"required": False, "performed": False},
        "preserved_existing_AC_restoration_authority": {
            "classification": ac["classification"],
            "schedules": ac["schedule_count"],
            "first_pass_PASS": ac["first_pass_pass_count"],
            "restoration_required": ac["restoration_required_count"],
            "restoration_success": ac["restoration_success_count"],
            "restoration_failure": ac["restoration_failure_count"],
            "final_primary_PASS": ac["all_28_final_primary_PASS"],
            "final_secondary_PASS": ac["all_28_final_secondary_PASS"],
            "note": "Preserved evidence only; no schedule or AC rerun in this task.",
        },
        "active_final_AIDC_power_boundary": "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY",
        "READY_FOR_APRIL_RESUME": True,
        "resume_basis": "Existing V1-ready state preserved byte-identically; V3 was not activated.",
        "git_commits": {
            "external_source_discovery_provenance_schema": DISCOVERY_COMMIT,
            "Kestrel_U2_semantics_external_identifiability": IDENTIFIABILITY_COMMIT,
            "V3_model": "NOT_CREATED_NOT_AUTHORIZED",
            "RCMQT_V3": "NOT_CREATED_NOT_REQUIRED",
            "same_7day_V3": "NOT_CREATED_NOT_REQUIRED",
            "final_review": "THIS_ARTIFACT_COMMIT_REPORTED_BY_GIT_AFTER_CREATION",
        },
        "tests": {
            "focused_command": "python -m pytest -q tests/test_v17_external_h100_discovery.py tests/test_v17_external_h100_identifiability.py",
            "focused_result": "14 passed in 1.38s",
            "full_command": "python -m pytest -q tests",
            "full_result": "586 passed, 4 skipped, 84 subtests passed, 4 failed in 56.56s",
            "unrelated_or_environment_failures": [
                "torch absent: production-weight fingerprint test",
                "existing PFR multi-trust-region MESS projection regression",
                "two POSIX fcntl source-cache tests unsupported on Windows",
            ],
            "initial_environment_attempts": "A first collection lacked NumPy/Pandas/tzdata; a second run used incomplete cached pyarrow/gurobipy. Repository-external test cache was repaired, then the recorded full result was obtained.",
        },
        "artifact_sha256": hashes,
        "git_status_expected_after_final_commit": "CLEAN",
        "rejected_V2_byte_identity": {
            "contract_sha256": "882dfbdf24abade96bd2aacd1dae66dfd7a25e89885d9d62a902bc273dad937b",
            "validation_sha256": "36b93cbeb224223a98dfcf7c2d47c5b8c3fa0f8b358f205082595451d76ccb68",
        },
        **zero_counters(),
    }
    write_json(output / "V17_AIDC_POWER_V3_EXTERNAL_FINAL_REVIEW.json", final)
    return final


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(list(argv) if argv is not None else None)
    final = materialize(args.repo, args.output)
    print(json.dumps({
        "status": final["status"],
        "primary_classification": final["primary_classification"],
        "active_boundary": final["active_final_AIDC_power_boundary"],
        "READY_FOR_APRIL_RESUME": final["READY_FOR_APRIL_RESUME"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
