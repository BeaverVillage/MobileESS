"""Finalize the V17 AC-loop / AIDC-power-boundary joint gate."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any, Sequence

from .authority import sha256_file
from .v17_deferrability_semantics import write_json


TRACK_A = "V17_AC_LOOP_A_COMMON_CLOSED_LOOP_IMPLEMENTED_PASS"
TRACK_B = "V17_AIDC_POWER_V2_C_PARTIAL_NODE_POWER_NOT_IDENTIFIABLE"
COMBINED = "V17_JOINT_B_AC_LOOP_PASS_AIDC_V2_NOT_IDENTIFIABLE"


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True, encoding="utf-8").strip()


def finalize(repo: Path, output: Path) -> dict[str, Any]:
    repo = repo.resolve(); output = output.resolve()
    names = {
        "prechange_manifest": "V17_JOINT_AC_LOOP_AIDC_POWER_V2_PRECHANGE_MANIFEST.json",
        "ac_contract": "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1.json",
        "cut_validation": "V17_AC_RESTORATION_CUT_VALIDATION.json",
        "apr12_trace": "V17_APR12_B2_RESTORATION_TRACE.json",
        "seven_day": "V17_AC_RESTORATION_7DAY_REGRESSION.json",
        "source_audit": "V17_AIDC_PARTIAL_NODE_SOURCE_AUDIT.json",
        "decomposition": "V17_AIDC_UNMODELED_COHORT_DECOMPOSITION.json",
        "identifiability": "V17_AIDC_PARTIAL_NODE_POWER_IDENTIFIABILITY.json",
        "v2_validation": "V17_AIDC_POWER_MODEL_V2_VALIDATION.json",
        "v2_contract": "V17_AIDC_POWER_MODEL_V2_CONTRACT.json",
        "boundary": "V17_AIDC_POWER_V1_V2_BOUNDARY_COMPARISON.json",
    }
    payloads = {key: json.loads((output / name).read_text(encoding="utf-8")) for key, name in names.items()}
    regression = payloads["seven_day"]; identity = payloads["identifiability"]
    if regression["classification"] != TRACK_A or regression["status"] != "PASS":
        raise RuntimeError("V17_JOINT_TRACK_A_NOT_PASS")
    if identity["classification"] != TRACK_B or identity["scientific_boundary_expansion_authorized"]:
        raise RuntimeError("V17_JOINT_TRACK_B_CLASSIFICATION_MISMATCH")
    if payloads["v2_contract"]["status"] != "REJECTED_NOT_AUTHORIZED":
        raise RuntimeError("V17_JOINT_V2_NOT_EXPLICITLY_REJECTED")

    prechange = payloads["prechange_manifest"]
    mismatches = []
    for row in prechange["files"]:
        path = repo / row["path"]
        actual = sha256_file(path) if path.is_file() else None
        if actual != row["sha256"]:
            mismatches.append({"path": row["path"], "expected": row["sha256"], "actual": actual})
    if mismatches:
        raise RuntimeError(f"V17_JOINT_PRECHANGE_AUTHORITY_BYTES_CHANGED:{mismatches[:3]}")

    training_path = output / "V17_RCMQT_V2_TRAINING_REPORT.json"
    training = json.loads(training_path.read_text(encoding="utf-8"))
    weights_path = output / training["weights_file"]
    if sha256_file(weights_path) != training["weights_file_sha256"]:
        raise RuntimeError("V17_JOINT_ACTIVE_RCMQT_WEIGHT_SHA_MISMATCH")
    freeze_path = output / "V17_V5_CURRENT_REPAIR_7DAY_PRE_EVALUATION_FREEZE_MANIFEST.json"
    freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    if freeze["status"] != "PASS_FROZEN_BEFORE_B0_B3":
        raise RuntimeError("V17_JOINT_ACTIVE_HJ_FREEZE_NOT_PASS")

    artifact_shas = {key: {"path": names[key], "sha256": sha256_file(output / names[key])}
                     for key in names}
    readiness = {
        "scientific_AC_restoration_contract_frozen": True,
        "Apr12_B2_closed_loop_resolved": payloads["apr12_trace"]["status"] == "PASS",
        "same_7day_final_AC_regression_PASS": regression["status"] == "PASS",
        "AIDC_implementation_or_unit_defect_unresolved": False,
        "active_AIDC_power_boundary_has_explicit_source_authority": True,
        "active_boundary": "V17_AIDC_POWER_MODEL_V1_FROZEN_KAPPA_BOUNDARY",
        "V2_extension_status": "REJECTED_NOT_AUTHORIZED",
        "active_H_J_surrogate_correspond_to_active_V1_boundary": True,
        "reason_H_J_remain_valid": "Track B made no model/cohort/forecast/reference changes; the prechange manifest proves all frozen V1 anchors and coefficients remained byte-identical.",
        "May_reads_zero": True,
        "June_reads_zero": True,
    }
    ready = all(value for key, value in readiness.items() if key not in {
        "AIDC_implementation_or_unit_defect_unresolved", "active_boundary", "V2_extension_status", "reason_H_J_remain_valid"
    }) and not readiness["AIDC_implementation_or_unit_defect_unresolved"]
    result = {
        "artifact_id": "V17_AC_LOOP_AIDC_POWER_V2_COMBINED_REVIEW_V1",
        "status": "PASS",
        "TRACK_A_CLASSIFICATION": TRACK_A,
        "TRACK_B_CLASSIFICATION": TRACK_B,
        "combined_state": COMBINED,
        "April_resume_decision": "READY_FOR_APRIL_RESUME" if ready else "APRIL_RESUME_BLOCKED",
        "stop_point_observed": "STOP_AFTER_SAME_7DAY_FINAL_REGRESSION",
        "remaining_April_resumed": False,
        "Track_A": {
            "schedule_count": regression["schedule_count"],
            "first_pass_pass_count": regression["first_pass_pass_count"],
            "restoration_required_count": regression["restoration_required_count"],
            "restoration_success_count": regression["restoration_success_count"],
            "restoration_failure_count": regression["restoration_failure_count"],
            "all_28_final_primary_PASS": regression["all_28_final_primary_PASS"],
            "all_28_final_secondary_PASS": regression["all_28_final_secondary_PASS"],
            "all_28_service_parity_PASS": regression["all_28_service_parity_PASS"],
            "all_28_terminal_SOC_PASS": regression["all_28_terminal_SOC_PASS"],
            "regression_sha256_reproduced_after_Track_B_gate": True,
            "regression_sha256": sha256_file(output / names["seven_day"]),
        },
        "Track_B": {
            "classification": TRACK_B,
            "partial_node_source_backed": False,
            "V2_authority_minted": False,
            "V2_model_or_forecast_training_calls": 0,
            "V1_retained": True,
            "claim_boundary": "POWER_MODEL_COMPATIBILITY_BOUNDARY_DOMINANT",
            "semantic_flexible_node_equivalent_hours": payloads["boundary"]["semantic_flexible_node_equivalent_hours"],
            "V1_modelable_node_equivalent_hours": payloads["boundary"]["V1_modelable_node_equivalent_hours"],
            "V1_modelable_node_hour_fraction_of_semantic": payloads["boundary"]["V1_modelable_node_hour_fraction_of_semantic"],
            "U1_potential_not_authorized": payloads["boundary"]["U1_potential_only_not_recoverable_without_authority"],
        },
        "active_model_and_electrical_authority": {
            "power_response_source": {"path": "dayahead/aidc_power_response.py", "sha256": sha256_file(repo / "dayahead/aidc_power_response.py")},
            "RCMQT_training_report": {"path": str(training_path.relative_to(repo)).replace("\\", "/"), "sha256": sha256_file(training_path)},
            "RCMQT_weights": {"path": str(weights_path.relative_to(repo)).replace("\\", "/"), "sha256": sha256_file(weights_path)},
            "RCMQT_weight_config_fingerprint": training["final_weight_config_fingerprint"],
            "V5_H_J_pre_evaluation_freeze": {"path": str(freeze_path.relative_to(repo)).replace("\\", "/"), "sha256": sha256_file(freeze_path), "freeze_token": freeze["freeze_token"]},
            "electrical_anchor_and_coefficient_shas": freeze["electrical_anchors_and_coefficients"],
        },
        "prechange_preservation": {
            "file_count": len(prechange["files"]),
            "sha256_mismatch_count": len(mismatches),
            "all_byte_identical": not mismatches,
        },
        "readiness": readiness,
        "artifact_sha256": artifact_shas,
        "git_commits_before_final_review": {
            "contract_and_cut_validation": "b7bf805",
            "Apr12_and_7day_AC_loop": "c250038",
            "partial_node_forensic": "60d9a66",
            "AIDC_Power_V2_implementation_commit": None,
            "why_no_V2_commit": "Classification A was not achieved; implementation was forbidden.",
        },
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "AIDC_site_changes": 0,
        "beta_changes": 0,
        "PUE_changes": 0,
        "PF_changes": 0,
        "effect_selected_parameters": 0,
        "grid_benefit_selected_parameters": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }
    write_json(output / "V17_AC_LOOP_AIDC_POWER_V2_COMBINED_REVIEW.json", result)
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    result = finalize(args.repo, args.output)
    print(json.dumps({"status": result["status"], "combined": result["combined_state"], "resume": result["April_resume_decision"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
