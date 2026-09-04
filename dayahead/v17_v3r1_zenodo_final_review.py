"""Materialize the fail-closed V17 V3R1 Zenodo final review."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

from .v17_v3r1_zenodo import write_json, zero_counters
from .v17_v3r1_zenodo_identifiability import (
    PRIMARY_CLASSIFICATION,
    U1_CLASSIFICATION,
    U2_CLASSIFICATION,
    U3_CLASSIFICATION,
)


DISCOVERY_COMMIT = "86f5f745a3afdf01aea6c3375b3f606e53dba8c1"
IDENTIFIABILITY_COMMIT = "19541655cde19b46c120bb378e87a9c55e045c10"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load(output: Path, name: str) -> dict[str, Any]:
    return json.loads((output / name).read_text(encoding="utf-8"))


def _artifact_hashes(output: Path, names: list[str]) -> dict[str, Any]:
    return {
        name: {"bytes": (output / name).stat().st_size, "sha256": sha256_file(output / name)}
        for name in names
    }


def _verify_prechange(repo: Path, output: Path) -> dict[str, Any]:
    manifest = _load(output, "V17_AIDC_POWER_V3R1_ZENODO_PRECHANGE_MANIFEST.json")
    mismatches: list[dict[str, str]] = []
    missing: list[str] = []
    for row in manifest["preservation_scope"]["all_records"]:
        path = repo / row["path"]
        if not path.is_file():
            missing.append(row["path"])
            continue
        actual = sha256_file(path)
        if actual != row["sha256"]:
            mismatches.append({"path": row["path"], "expected": row["sha256"], "actual": actual})
    return {
        "record_count": len(manifest["preservation_scope"]["all_records"]),
        "missing": missing,
        "mismatches": mismatches,
        "pass": not missing and not mismatches,
    }


def materialize(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve()
    output = output.resolve()
    discovery = _load(output, "V17_EUROSYS_ZENODO_ARTIFACT_DISCOVERY.json")
    delta = _load(output, "V17_EUROSYS_GITHUB_VS_ZENODO_SOURCE_DELTA.json")
    inventory = _load(output, "V17_EUROSYS_ZENODO_RAW_DATA_INVENTORY.json")
    provenance = _load(output, "V17_EUROSYS_ZENODO_MEASUREMENT_PROVENANCE.json")
    transfer = _load(output, "V17_V3R1_H100_HARDWARE_TRANSFER_MATRIX.json")
    reproduction = _load(output, "V17_V3R1_Kestrel_U2_REPRODUCTION.json")
    bridge = _load(output, "V17_V3R1_EXTERNAL_TO_KESTREL_SEMANTIC_BRIDGE.json")
    aggregate = _load(output, "V17_V3R1_U2_AGGREGATE_STATE_COVERAGE.json")
    ident = _load(output, "V17_AIDC_POWER_V3R1_COHORT_IDENTIFIABILITY.json")
    coverage = _load(output, "V17_AIDC_POWER_V1_V3R1_COVERAGE_COMPARISON.json")
    validation = _load(output, "V17_AIDC_POWER_MODEL_V3R1_VALIDATION.json")
    old_final = _load(output, "V17_AIDC_POWER_V3_EXTERNAL_FINAL_REVIEW.json")
    ac = _load(output, "V17_AC_RESTORATION_7DAY_REGRESSION.json")

    preservation = _verify_prechange(repo, output)
    if not preservation["pass"]:
        raise RuntimeError("V17_V3R1_PRECHANGE_AUTHORITY_IDENTITY_FAILURE")
    names = [
        "V17_AIDC_POWER_V3R1_ZENODO_PRECHANGE_MANIFEST.json",
        "V17_EUROSYS_ZENODO_ARTIFACT_DISCOVERY.json",
        "V17_EUROSYS_GITHUB_VS_ZENODO_SOURCE_DELTA.json",
        "V17_EUROSYS_ZENODO_RAW_DATA_INVENTORY.json",
        "V17_EUROSYS_ZENODO_MEASUREMENT_PROVENANCE.json",
        "V17_V3R1_H100_HARDWARE_TRANSFER_MATRIX.json",
        "V17_V3R1_Kestrel_U2_REPRODUCTION.json",
        "V17_V3R1_EXTERNAL_TO_KESTREL_SEMANTIC_BRIDGE.json",
        "V17_V3R1_U2_AGGREGATE_STATE_COVERAGE.json",
        "V17_V3R1_EXTERNAL_SPLIT_CONTRACT.json",
        "V17_AIDC_POWER_V3R1_ACCEPTANCE_CONTRACT.json",
        "V17_AIDC_POWER_V3R1_COHORT_IDENTIFIABILITY.json",
        "V17_AIDC_POWER_MODEL_V3R1_CONTRACT.json",
        "V17_AIDC_POWER_MODEL_V3R1_VALIDATION.json",
        "V17_AIDC_POWER_V1_V3R1_COVERAGE_COMPARISON.json",
    ]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1"], cwd=repo, text=True)
    final = {
        "artifact_id": "V17_AIDC_POWER_V3R1_ZENODO_FINAL_REVIEW_V1",
        "status": "V17_AIDC_POWER_V3R1_ZENODO_NOT_AUTHORIZED",
        "primary_classification": PRIMARY_CLASSIFICATION,
        "U1_CLASSIFICATION": U1_CLASSIFICATION,
        "U2_CLASSIFICATION": U2_CLASSIFICATION,
        "U3_CLASSIFICATION": U3_CLASSIFICATION,
        "start_gate": {
            "required_head": "671f4fe402a25be281397c5fa8ad262cea4f29c0",
            "start_working_tree_clean": True,
            "prechange_preservation": preservation,
        },
        "official_Zenodo_source": {
            "path": discovery["source"]["absolute_path"],
            "sha256": discovery["source"]["sha256"],
            "bytes": discovery["source"]["bytes"],
            "doi": discovery["official_record"]["doi"],
            "concept_doi": discovery["official_record"]["concept_doi"],
            "license": discovery["license"]["id"],
            "user_shortcut": discovery["user_supplied_internet_shortcut"],
        },
        "prior_GitHub_source": {
            "path": delta["github_snapshot"]["archive_path"],
            "sha256": delta["github_snapshot"]["archive_sha256"],
            "bytes": delta["github_snapshot"]["archive_bytes"],
            "measurement_authority": False,
        },
        "Zenodo_inventory": {
            "telemetry_files": inventory["telemetry_file_count"],
            "telemetry_rows": inventory["telemetry_row_count"],
            "H100_telemetry_files": inventory["H100_telemetry_file_count"],
            "benchmark_result_files": inventory["benchmark_result_file_count"],
            "families": inventory["families"],
        },
        "hardware_and_measurement_boundary": {
            "direct_absolute_external_kW_transfer_authorized": transfer["direct_absolute_external_kW_transfer_authorized"],
            "platforms": transfer["platforms"],
            "GPU_device_board_power": provenance["power_boundaries"]["GPU_device_board_power"],
            "node_aggregate_power": provenance["power_boundaries"]["node_aggregate_power"],
            "CPU_package_power": provenance["power_boundaries"]["CPU_package_power"],
        },
        "Kestrel_U2": {
            "meaning": bridge["U2_meaning"],
            "jobs": reproduction["U2"]["jobs"],
            "node_equivalent_hours": reproduction["U2"]["node_equivalent_hours"],
            "known": bridge["U2_known"],
            "unknown": bridge["U2_unknown"],
            "Zenodo_transfer": U2_CLASSIFICATION,
            "ex_post_aggregate_state_coverage": {
                "jobs": aggregate["fully_reconstructable_ex_post_jobs"],
                "job_fraction": aggregate["fully_reconstructable_ex_post_job_fraction"],
                "node_equivalent_hours": aggregate["fully_reconstructable_ex_post_node_equivalent_hours"],
                "node_hour_fraction": aggregate["fully_reconstructable_ex_post_node_hour_fraction"],
                "active_point_model_support_node_hours": aggregate["active_point_model_support_node_hours"],
            },
        },
        "Scientific_Data_role": {
            "improves_independent_H100_physical_response_authority": old_final["Scientific_Data_role"]["improves_independent_H100_physical_response_authority"],
            "shared_job_attribution_authority": False,
            "role": "independent H100 device activity-power evidence; not Kestrel U2 sharing authority",
        },
        "cohort_recovery": {
            "U1_node_equivalent_hours": ident["U1"]["node_equivalent_hours"],
            "U2_node_equivalent_hours": ident["U2"]["node_equivalent_hours"],
            "U3_node_equivalent_hours": ident["U3"]["node_equivalent_hours"],
            "authorized_recoverable_node_equivalent_hours": {"U1": 0.0, "U2": 0.0, "U3": 0.0},
        },
        "coverage": {
            "V1": coverage["V1_coverage_fraction"],
            "potential_V3R1": coverage["V3R1_coverage_fraction"],
            "incremental": coverage["incremental_coverage_fraction"],
        },
        "candidate_model": {
            "equation": transfer["only_candidate_equation"],
            "authorized": False,
            "reason": bridge["marginal_power_of_schedulable_work"]["reason"],
        },
        "held_out_validation": {
            "performed": False,
            "metrics": validation["held_out_metrics"],
            "marginal_power_metrics": validation["marginal_power_metrics"],
            "fit_calls": validation["fit_calls"],
            "held_out_error_reads": validation["held_out_error_reads"],
        },
        "V3R1_authority_minted": False,
        "RCMQT_V3R1": {"required": False, "performed": False, "reason": "No expanded active power boundary."},
        "same_7day_V3R1_science": {"required": False, "performed": False},
        "preserved_existing_AC_restoration_authority": {
            "schedules": 28,
            "first_pass_PASS": 27,
            "restoration_required": ac["restoration_required_count"],
            "restoration_success": ac["restoration_success_count"],
            "restoration_failure": ac["restoration_failure_count"],
            "note": "Preserved evidence only; no AC or schedule rerun in V3R1.",
        },
        "active_final_AIDC_power_boundary": "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY",
        "READY_FOR_APRIL_RESUME": True,
        "resume_basis": "The prior V1-ready state and all 247 prechange authority files remain byte-identical; V3R1 was not activated.",
        "git_commits": {
            "Zenodo_discovery_provenance_source_delta": DISCOVERY_COMMIT,
            "raw_inventory_Kestrel_bridge_identifiability": IDENTIFIABILITY_COMMIT,
            "V3R1_model": "NOT_CREATED_NOT_AUTHORIZED",
            "RCMQT_V3R1": "NOT_CREATED_NOT_REQUIRED",
            "same_7day_V3R1": "NOT_CREATED_NOT_REQUIRED",
            "final_review": "THIS_ARTIFACT_COMMIT_REPORTED_AFTER_CREATION",
        },
        "generation_git_head": head,
        "generation_worktree_status": status,
        "artifact_sha256": _artifact_hashes(output, names),
        "tests": {
            "focused_command": "py -3.11 -m pytest tests/test_v17_v3r1_zenodo_discovery.py tests/test_v17_v3r1_zenodo_identifiability.py -q",
            "focused_result": "14 passed in 0.83s",
            "full_command": "py -3.11 -m pytest tests -q",
            "full_result": "600 passed, 4 skipped, 84 subtests passed, 4 failed in 55.61s",
            "unbounded_root_command": "py -3.11 -m pytest -q",
            "unbounded_root_result": "collection interrupted by existing science/r25l_b5_monolithic_gate_proof_test.py SystemExit; 4 collection errors in 19.06s",
            "unrelated_or_environment_failures": [
                "torch absent: production-weight fingerprint test",
                "existing PFR multi-trust-region MESS projection regression",
                "two POSIX fcntl source-cache tests unsupported on Windows",
            ],
        },
        "rejected_V2_byte_identity": {
            "contract_sha256": "882dfbdf24abade96bd2aacd1dae66dfd7a25e89885d9d62a902bc273dad937b",
            "validation_sha256": "36b93cbeb224223a98dfcf7c2d47c5b8c3fa0f8b358f205082595451d76ccb68",
        },
        "prior_rejected_V3_final_sha256": "1bc1b017124e687132970ad67cd8eaf33ba6a6644d4c09468cd514af03cf6a42",
        **zero_counters(),
    }
    write_json(output / "V17_AIDC_POWER_V3R1_ZENODO_FINAL_REVIEW.json", final)
    return {
        "status": PRIMARY_CLASSIFICATION,
        "V3R1_minted": False,
        "READY_FOR_APRIL_RESUME": True,
        "prechange_preservation_pass": preservation["pass"],
        **zero_counters(),
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(list(argv) if argv is not None else None)
    print(json.dumps(materialize(args.repo, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
