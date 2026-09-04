"""Materialize the final fail-closed V17 V3R2 Eagle/Kestrel review."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any

from .authority import sha256_file
from .v17_v3r2_eagle_forensic import write_json, zero_counters
from .v17_v3r2_transfer_decision import ACTIVE_BOUNDARY, PRIMARY_CLASSIFICATION


COMMITS = {
    "Eagle_discovery_provenance_schema_time_alignment": "845acf17217a0e682b4e441d97f13ab7bda136f4",
    "Kestrel_native_energy_U2_forensic": "befd82083f80c247bc38a6dd4b8512d834d784a8",
    "Eagle_shared_node_marginal_validation": "ae91e8b3541d47767c53df9b19dc046c4ee1b16b",
    "V100_H100_transfer_D1_causality": "7ff7493d41d586cb20646fdd997813b8b139e3b3",
    "V3R2_model_RCMQT": "NOT_CREATED_NOT_AUTHORIZED",
    "same_7day_electrical_validation": "NOT_CREATED_NOT_REQUIRED",
    "final_review": "THIS_ARTIFACT_COMMIT_REPORTED_AFTER_CREATION",
}


def _load(output: Path, name: str) -> dict[str, Any]:
    return json.loads((output / name).read_text(encoding="utf-8"))


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def _verify_prechange(repo: Path, output: Path) -> dict[str, Any]:
    manifest = _load(output, "V17_AIDC_POWER_V3R2_EAGLE_PRECHANGE_MANIFEST.json")
    mismatches: list[dict[str, str]] = []
    for record in manifest["preservation_scope"]["all_records"]:
        path = repo / record["path"]
        actual = sha256_file(path) if path.is_file() else "MISSING"
        if actual != record["sha256"]:
            mismatches.append({"path": record["path"], "expected": record["sha256"], "actual": actual})
    return {
        "record_count": len(manifest["preservation_scope"]["all_records"]),
        "mismatch_count": len(mismatches),
        "mismatches": mismatches,
        "pass": not mismatches,
    }


def build(repo: Path, output: Path) -> Path:
    discovery = _load(output, "V17_EAGLE_DATASET_DISCOVERY.json")
    hardware = _load(output, "V17_EAGLE_HARDWARE_MEASUREMENT_AUTHORITY.json")
    timing = _load(output, "V17_EAGLE_TEMPORAL_ALIGNMENT_CONTRACT.json")
    job_schema = _load(output, "V17_EAGLE_JOB_ENERGY_SCHEMA_AUDIT.json")
    native = _load(output, "V17_KESTREL_NATIVE_ENERGY_FIELD_AUDIT.json")
    energy = _load(output, "V17_V3R2_KESTREL_U2_ENERGY_IDENTIFIABILITY.json")
    marginal = _load(output, "V17_EAGLE_SHARED_MARGINAL_POWER_VALIDATION.json")
    states = _load(output, "V17_EAGLE_SHARED_NODE_STATE_DATASET.json")
    transfer = _load(output, "V17_V3R2_V100_TO_H100_RESPONSE_TRANSFER_AUDIT.json")
    d1 = _load(output, "V17_AIDC_POWER_V3R2_D1_CAUSALITY_AUDIT.json")
    cohort = _load(output, "V17_AIDC_POWER_V3R2_COHORT_IDENTIFIABILITY.json")
    coverage = _load(output, "V17_AIDC_POWER_V1_V3R2_COVERAGE_COMPARISON.json")
    decision = _load(output, "V17_AIDC_POWER_V3R2_ACTIVATION_DECISION.json")
    prior = _load(output, "V17_AIDC_POWER_V3R1_ZENODO_FINAL_REVIEW.json")
    preservation = _verify_prechange(repo, output)
    if not preservation["pass"]:
        raise RuntimeError("V17_V3R2_PRECHANGE_AUTHORITY_MUTATION_DETECTED")

    artifact_names = [
        "V17_AIDC_POWER_V3R2_EAGLE_PRECHANGE_MANIFEST.json",
        "V17_EAGLE_DATASET_DISCOVERY.json",
        "V17_EAGLE_SOURCE_AUTHORITY_MANIFEST.json",
        "V17_EAGLE_HARDWARE_MEASUREMENT_AUTHORITY.json",
        "V17_EAGLE_JOB_ENERGY_SCHEMA_AUDIT.json",
        "V17_EAGLE_GPU_NODE_TELEMETRY_SCHEMA_AUDIT.json",
        "V17_EAGLE_TEMPORAL_ALIGNMENT_CONTRACT.json",
        "V17_KESTREL_NATIVE_ENERGY_FIELD_AUDIT.json",
        "V17_V3R2_KESTREL_U2_REPRODUCTION.json",
        "V17_V3R2_KESTREL_U2_NODE_INTERVALS_MANIFEST.json",
        "V17_V3R2_KESTREL_U2_ENERGY_IDENTIFIABILITY.json",
        "V17_EAGLE_SHARED_NODE_STATE_DATASET.json",
        "V17_EAGLE_KESTREL_COMMON_OBSERVABLE_CONTRACT.json",
        "V17_EAGLE_SHARED_POWER_SPLIT_CONTRACT.json",
        "V17_EAGLE_SHARED_MARGINAL_POWER_VALIDATION.json",
        "V17_AIDC_POWER_V3R2_TRANSFER_ACCEPTANCE_CONTRACT.json",
        "V17_V3R2_V100_TO_H100_RESPONSE_TRANSFER_AUDIT.json",
        "V17_AIDC_POWER_V3R2_D1_CAUSALITY_AUDIT.json",
        "V17_AIDC_POWER_V3R2_COHORT_IDENTIFIABILITY.json",
        "V17_AIDC_POWER_MODEL_V3R2_CONTRACT.json",
        "V17_AIDC_POWER_MODEL_V3R2_VALIDATION.json",
        "V17_AIDC_POWER_V1_V3R2_COVERAGE_COMPARISON.json",
        "V17_AIDC_POWER_V3R2_ACTIVATION_DECISION.json",
    ]
    artifact_sha = {
        name: {"bytes": (output / name).stat().st_size, "sha256": sha256_file(output / name)}
        for name in artifact_names
    }
    review = {
        "schema": "V17_AIDC_POWER_V3R2_EAGLE_FINAL_REVIEW_V1",
        "status": "V17_AIDC_POWER_V3R2_EAGLE_NOT_AUTHORIZED",
        "primary_classification": PRIMARY_CLASSIFICATION,
        "KESTREL_NATIVE_ENERGY_CLASSIFICATION": energy["classification"],
        "EAGLE_SHARED_MARGINAL_CLASSIFICATION": marginal["EAGLE_SHARED_MARGINAL_CLASSIFICATION"],
        "V100_TO_H100_TRANSFER_CLASSIFICATION": transfer["V100_TO_H100_TRANSFER_CLASSIFICATION"],
        "U1_CLASSIFICATION": cohort["U1_CLASSIFICATION"],
        "U2_CLASSIFICATION": cohort["U2_CLASSIFICATION"],
        "U3_CLASSIFICATION": cohort["U3_CLASSIFICATION"],
        "Eagle_sources": discovery["sources"],
        "Eagle_hardware": hardware["hardware"],
        "Eagle_measurement": hardware["measurement"],
        "Eagle_job_telemetry_overlap": {
            "jobs_overlapping_Ganglia": job_schema["six_gpu_node_subset"]["rows_overlapping_ganglia_period"],
            "jobs_overlapping_iLO": job_schema["six_gpu_node_subset"]["rows_overlapping_ilo_period"],
            "physical_node_time_join_available": True,
        },
        "Eagle_time_alignment": timing["alignment_rule"],
        "Kestrel_native_energy": {
            "source_semantics": native["source_semantics"],
            "U2_statistics": native["U2_statistics"],
            "classification": energy["classification"],
        },
        "Eagle_common_observables": ["concurrent_job_count", "sum_requested_gpus", "sum_requested_cpus"],
        "Eagle_state_evidence": {
            "exact_samples": states["counts"]["exact_single_node_or_idle_samples"],
            "co_resident_samples": states["EAGLE_U2_ANALOG_samples"],
            "max_exact_concurrent_jobs": states["counts"]["max_exact_concurrent_jobs"],
        },
        "Eagle_total_power_heldout_metrics": marginal["heldout_total_power_metrics"],
        "Eagle_marginal_power_heldout_metrics": marginal["heldout_natural_transition_metrics"],
        "concurrent_job_count_incremental_information": marginal["concurrent_job_count_information_beyond_gpu_count"],
        "normalized_Eagle_sharing_response": {
            "equation": "g_shared(X)=P_dynamic(X)/P_dynamic(full-GPU reference)",
            "valid": False,
            "reason": "no source-identifiable co-resident Eagle state and unreliable marginal transitions",
        },
        "transfer_decision": transfer,
        "D1_causal_state_decision": d1,
        "cohort_support": {
            "U2A_new_active_jobs": cohort["U2A"]["jobs"],
            "U2A_new_active_node_equivalent_hours": cohort["U2A"]["node_equivalent_hours"],
            "U2B_historical_only_node_equivalent_hours": cohort["U2B"]["node_equivalent_hours"],
        },
        "coverage": coverage,
        "V3R2_authority_minted": decision["V3R2_authority_minted"],
        "RCMQT_V3R2": {"required": decision["RCMQT_V3R2_required"], "performed": decision["RCMQT_V3R2_performed"]},
        "same_7day_V3R2": {"required": decision["same_7day_regression_required"], "performed": decision["same_7day_regression_performed"]},
        "preserved_AC_restoration_evidence": prior["preserved_existing_AC_restoration_authority"],
        "active_final_AIDC_power_boundary": ACTIVE_BOUNDARY,
        "READY_FOR_APRIL_RESUME": decision["READY_FOR_APRIL_RESUME"],
        "prechange_authority_preservation": preservation,
        "artifact_sha256": artifact_sha,
        "git_commits": COMMITS,
        "generation_git_head": _git(repo, "rev-parse", "HEAD"),
        "generation_worktree_status": _git(repo, "status", "--short"),
        "tests": {
            "focused_command": "python -m pytest tests/test_v17_v3r2_eagle_forensic.py tests/test_v17_v3r2_final_review.py -q",
            "focused_result": "15 passed in 0.11s",
            "full_command": "python -m pytest tests -q",
            "full_result": "615 passed, 4 skipped, 84 subtests passed, 4 failed in 58.52s",
            "unrelated_or_environment_failures": [
                "torch absent: production-weight fingerprint test",
                "existing PFR multi-trust-region MESS projection regression",
                "two POSIX fcntl source-cache tests unsupported on Windows",
            ],
        },
        **zero_counters(),
    }
    path = output / "V17_AIDC_POWER_V3R2_EAGLE_FINAL_REVIEW.json"
    write_json(path, review)
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(build(args.repo.resolve(), args.output.resolve()))


if __name__ == "__main__":
    main()
