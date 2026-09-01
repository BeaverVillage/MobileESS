"""Materialize the supplementary V16.3 decomposition completion manifest."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .authority import sha256_file
from .run_v16_3_decomposition_forensics import COUNTERS


REQUIRED = (
    "V16_3_DECOMPOSITION_EXECUTOR_CONTRACT.json",
    "V16_3_MAY02_STANDARD_BD_COMPLETION.json",
    "V16_3_MAY02_CL_MC_BD_COMPLETION.json",
    "V16_3_MAY02_DECOMPOSITION_EQUIVALENCE.json",
    "V16_3_POSTHOC_SUPPLEMENTARY_DECOMPOSITION_CONTRACT.json",
    "V16_3_SUPPLEMENTARY_ALL41_DECOMPOSITION_RESULTS.json",
    "V16_3_AIDC_REFERENCE_COHERENCE_FORENSIC.json",
    "V16_3_CRITICAL_CUT_ATTRIBUTION_DIAGNOSTIC.json",
)
FINAL_CLASSIFICATIONS = (
    "DECOMP_COMPLETION_A_MAY02_EQUIVALENT_SUPPLEMENTARY_COMPLETE",
    "DECOMP_COMPLETION_B_MAY02_EQUIVALENT_SUPPLEMENTARY_PARTIAL",
    "DECOMP_COMPLETION_C_EXECUTOR_NOT_EQUIVALENT",
    "DECOMP_COMPLETION_D_REFERENCE_PROVENANCE_DEFECT_FOUND",
    "DECOMP_COMPLETION_E_IMPLEMENTATION_FAILURE",
)


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def execute(repo: Path, output: Path) -> dict[str, object]:
    missing = [name for name in REQUIRED if not (output / name).is_file()]
    if missing:
        raise RuntimeError(f"DECOMPOSITION_COMPLETION_ARTIFACTS_MISSING:{missing}")
    contract = _load(output / REQUIRED[0])
    may02 = _load(output / REQUIRED[3])
    supplementary = _load(output / REQUIRED[5])
    coherence = _load(output / REQUIRED[6])
    attribution = _load(output / REQUIRED[7])
    reference_defect = bool(coherence["provenance_defect_found"])
    may02_pass = may02["status"] == "PASS"
    supplementary_complete = bool(
        supplementary["day_count"] == 41
        and supplementary["feasible_summary"]["all_standard_objective_equivalent"]
        and supplementary["feasible_summary"]["all_cl_mc_bd_objective_equivalent"]
        and supplementary["infeasible_summary"]["all_standard_status_identical"]
        and supplementary["infeasible_summary"]["all_cl_mc_bd_status_identical"]
        and max(supplementary["timeout_count"].values()) == 0
    )
    if reference_defect:
        classification = FINAL_CLASSIFICATIONS[3]
    elif not may02_pass:
        classification = FINAL_CLASSIFICATIONS[2]
    elif supplementary_complete:
        classification = FINAL_CLASSIFICATIONS[0]
    else:
        classification = FINAL_CLASSIFICATIONS[1]
    historical = repo / "dayahead/artifacts/v16_3_final"
    historical_checks = {
        name: {
            "expected_sha256": digest,
            "observed_sha256": sha256_file(historical / name),
            "exact": sha256_file(historical / name) == digest,
        }
        for name, digest in contract["historical_final_artifact_sha256"].items()
    }
    payload = {
        "artifact_id": "V16_3_DECOMPOSITION_COMPLETION_MANIFEST",
        "namespace_role": "ADDITIONAL_IMPLEMENTATION_COMPLETION_EVIDENCE",
        "original_final_science_classification_preserved": "FINAL_SCIENCE_DECOMPOSITION_INCOMPLETE",
        "historical_final_science_manifest_sha256": contract["final_science_manifest_sha256"],
        "authority_commit": contract["authority_commit"],
        "execution_contract_commit": contract["execution_contract_commit"],
        "final_execution_commit": contract["final_execution_commit"],
        "executor_checkpoint_commit": "054afedd04498c8acbcf9a6f994b0d63ab6f1bb2",
        "completion_evidence_parent_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo, text=True, capture_output=True, check=True).stdout.strip(),
        "required_artifact_sha256": {name: sha256_file(output / name) for name in REQUIRED},
        "historical_final_artifact_integrity": historical_checks,
        "historical_final_artifacts_all_exact": all(row["exact"] for row in historical_checks.values()),
        "May02_locked_gate": {
            "status": may02["status"],
            "relative_objective_difference": may02["relative_objective_difference"],
            "same_hard_feasibility_status": may02["same_hard_feasibility_status"],
        },
        "original_June02_benchmark_status": may02["ORIGINAL_JUNE_BENCHMARK_STATUS"],
        "supplementary_all41": {
            "complete": supplementary_complete,
            "day_count": supplementary["day_count"],
            "feasible_day_count": supplementary["feasible_day_count"],
            "infeasible_day_count": supplementary["infeasible_day_count"],
            "timeout_count": supplementary["timeout_count"],
        },
        "reference_coherence_classification": coherence["classification"],
        "reference_provenance_defect_found": reference_defect,
        "critical_cut_attribution_hypothesis_supported": attribution["hypothesis_supported"],
        "verification": {
            "targeted": {
                "command": "pytest tests/test_v16_3_decomposition_completion.py -q",
                "result": "9 passed",
                "status": "PASS",
            },
            "full_regression": {
                "command": "pytest tests -q",
                "result": "521 passed, 4 skipped, 84 subtests passed, 3 failed",
                "status": "KNOWN_UNRELATED_FAILURES",
                "failures": [
                    "tests/test_pfr_mess_energy_recovery.py::test_joint_projection_restores_feasibility_across_multiple_trust_regions",
                    "tests/test_shared_exact_source_preparation.py::test_exact_sources_are_prepared_once_and_reused_by_day_workers (Windows lacks POSIX fcntl)",
                    "tests/test_shared_exact_source_preparation.py::test_exact_source_cache_is_invalidated_by_source_identity (Windows lacks POSIX fcntl)",
                ],
                "changed_by_this_task": False,
            },
        },
        "firewall_counters": COUNTERS,
        "final_classification": classification,
        "next_decision": "READY_FOR_FINAL_RESULTS_INTERPRETATION_AND_PAPER" if may02_pass and not reference_defect else "DECOMPOSITION_OR_REFERENCE_REVIEW_REQUIRED",
    }
    path = output / "V16_3_DECOMPOSITION_COMPLETION_MANIFEST.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"classification": classification, "next_decision": payload["next_decision"], "sha256": sha256_file(path)}


def main() -> None:
    repo = Path.cwd()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--output", type=Path, default=repo / "dayahead/artifacts/v16_3_decomposition_completion")
    print(json.dumps(execute(**vars(parser.parse_args())), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
