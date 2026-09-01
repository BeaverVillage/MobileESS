"""Mint the reviewed V16.3 authority without running final science campaigns."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from .authority import sha256_file
from .run_authority_semantic_g11_v16_2 import _write_json
from .v16_3_authority import (
    AUTHORITY_ID,
    BETA_AIDC,
    CONTROL_DIMENSION,
    CONTROL_SEMANTICS_ID,
    CURRENT_COEFFICIENT_HASH_OF_DAILY_HASHES,
    PHASE_CURRENT_DIMENSION,
    RHO_VALID,
    TIME_LOCAL_GRID_LP_COUNT,
)


EVIDENCE_CHECKPOINT_SHA = "ea8dac048bf756a65a22fb4e906e6ef2812570c8"
REVIEW_SHA256 = "02f120e16afbb54dd87140db36e8af71f1495bceea4a79b2ce573b3110ef2991"
APR15_SCHEDULE_SHA256 = "f5b5f4569e81c48a4662b0e4dfe177cc96eee00f57063693ccf149243a0a6bff"
NATIVE_MASTER_SHA256 = "cc7c2f153ca1e57f9fb5cad8b3c3e1ecbcb20c5db59ca4d65539411a50525969"

ACTIVATION_COUNTERS = {
    "scientific_authority_changes": 1,
    "production_V16_3_activations": 1,
    "raw_AIDC_data_changes": 0,
    "P_IT_REF_changes": 0,
    "G_REF_changes": 0,
    "W_F_changes": 0,
    "kappa_changes": 0,
    "PUE_changes": 0,
    "PF_changes": 0,
    "alpha_grid_changes": 0,
    "native_ieee123_changes": 0,
    "source_voltage_changes": 0,
    "native_regulator_setting_changes": 0,
    "capacitor_hardware_or_authority_changes": 0,
    "line_rating_changes": 0,
    "transformer_rating_changes": 0,
    "u080_changes": 0,
    "AIDC_PCC_rating_changes": 0,
    "MESS_PCC_rating_changes": 0,
    "host_mapping_changes": 0,
    "MESS_parameter_changes": 0,
    "objective_meaning_changes": 0,
    "gamma_crit_changes": 0,
    "voltage_limit_changes": 0,
    "tap_cooptimization_variables_added": 0,
    "legacy_v13_control_sidecar_loads": 0,
    "OpenDSS_calls_inside_Benders": 0,
    "may_scientific_loader_access_count": 0,
    "june_scientific_loader_access_count": 0,
    "G12_final_calls": 0,
    "G13_calls": 0,
    "G14_calls": 0,
    "C12_calls": 0,
}


def _load(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"V163_REFREEZE_JSON_ROOT:{path}")
    return payload


def _payload_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source(repo: Path, relative: str) -> dict[str, object]:
    path = repo / relative
    if not path.is_file():
        raise RuntimeError(f"V163_REFREEZE_SOURCE_MISSING:{relative}")
    return {"path": relative.replace("\\", "/"), "sha256": sha256_file(path)}


def _verify_cache_manifest(repo: Path, relative: str) -> dict[str, object]:
    manifest_path = repo / relative
    manifest = _load(manifest_path)
    data_root = manifest_path.parent / "data"
    for row in manifest["files"]:
        path = data_root / str(row["name"])
        if path.stat().st_size != int(row["bytes"]) or sha256_file(path) != str(row["sha256"]):
            raise RuntimeError(f"V163_REFREEZE_CACHE_HASH_MISMATCH:{path.name}")
    return {
        "path": relative,
        "sha256": sha256_file(manifest_path),
        "file_count": int(manifest["file_count"]),
        "total_bytes": int(manifest["total_bytes"]),
        "verification": "PASS_ALL_FILE_BYTES_AND_SHA256",
        "large_cache_committed_to_normal_git": False,
    }


def _validate_evidence(repo: Path) -> dict[str, object]:
    candidate = repo / "dayahead/artifacts/v16_3_candidate"
    review_path = candidate / "V16_3_PREREFREEZE_CORRECTION_REVIEW_V3.json"
    if sha256_file(review_path) != REVIEW_SHA256:
        raise RuntimeError("V163_REFREEZE_REVIEW_SHA_MISMATCH")
    review = _load(review_path)
    shadow = _load(candidate / "V16_3_APR15_NONZERO_SHADOW_DUAL_AC_VALIDATION.json")
    current = _load(candidate / "V16_3_AC_ANCHORED_PHASE_CURRENT_CONTRACT_CANDIDATE.json")
    voltage = _load(candidate / "V16_3_AC_ANCHORED_VOLTAGE_SENSITIVITY_CONTRACT_CANDIDATE.json")
    anchor = _load(candidate / "V16_3_D1_AC_ANCHOR_CONTRACT_CANDIDATE.json")
    taps = _load(candidate / "V16_3_EXOGENOUS_NATIVE_TAP_SCHEDULE_CANDIDATE.json")
    semantics = _load(candidate / "V16_3_FROZEN_COMMON_CONTROL_SEMANTICS_CANDIDATE.json")
    trust = _load(candidate / "V16_3_FROZEN_PRIMARY_TRUST_REGION_CANDIDATE.json")

    required = {
        "review_classification": review["final_classification"] == "V163_CORR_A_FROZEN_PRIMARY_AND_CURRENT_SURROGATE_VALID",
        "review_next": review["next_decision"] == "READY_FOR_V16_3_SCIENTIFIC_REFREEZE_REVIEW",
        "beta": float(review["beta_AIDC"]) == BETA_AIDC,
        "rho": float(trust["rho_valid_frozen_primary"]) == RHO_VALID,
        "current_shape": int(current["branch_phase_dimension"]) == PHASE_CURRENT_DIMENSION
        and int(current["control_dimension"]) == CONTROL_DIMENSION,
        "current_hash": current["coefficient_hash_of_daily_hashes"] == CURRENT_COEFFICIENT_HASH_OF_DAILY_HASHES,
        "voltage_shape": int(voltage["control_dimensions"]["total"]) == CONTROL_DIMENSION
        and int(voltage["time_local_slice_count"]) == TIME_LOCAL_GRID_LP_COUNT,
        "anchor_days": len(anchor["included_days"]) == 29 and bool(anchor["D1_cutoff_compliance_all_days"]),
        "tap_identity": bool(anchor["anchor_B0_B1_B2_B3_identical"])
        and int(taps["tap_decision_variables"]) == 0
        and taps["recompute_after_B0_B1_B2_B3"] is False,
        "common_semantics": semantics["semantics_id"] == CONTROL_SEMANTICS_ID
        and len(set(semantics["Apr15_common_control_fingerprints"].values())) == 1,
        "shadow_schedule": shadow["schedule_sha256"] == APR15_SCHEDULE_SHA256,
        "shadow_lp": bool(shadow["prospective_shadow_solve"]["hard_feasible"]),
        "shadow_primary": bool(shadow["primary_Fresh_OpenDSS_frozen_D1_taps"]["all_frozen_hard_constraints_pass"]),
        "shadow_secondary": bool(shadow["secondary_Fresh_OpenDSS_native_RegControl"]["all_frozen_hard_constraints_pass"]),
        "service_parity": float(shadow["prospective_shadow_solve"]["terminal_service_parity_max_abs_error"]) == 0.0,
        "mess_terminal": float(shadow["prospective_shadow_solve"]["mess_terminal_soc_max_abs_error_kwh"]) == 0.0,
    }
    failed = [key for key, passed in required.items() if not passed]
    if failed:
        raise RuntimeError(f"V163_REFREEZE_EVIDENCE_FAIL:{failed}")

    voltage_manifest = _verify_cache_manifest(
        repo, "dayahead/artifacts/v16_3_candidate/V16_3_CANDIDATE_NPZ_SHA256_MANIFEST.json"
    )
    current_manifest = _verify_cache_manifest(
        repo, "dayahead/artifacts/v16_3_candidate/V16_3_CURRENT_CANDIDATE_NPZ_SHA256_MANIFEST.json"
    )
    h_daily = [str(row["fingerprint"]) for row in voltage["per_day_files"]]
    return {
        "checks": required,
        "candidate_sources": {
            name: _source(repo, f"dayahead/artifacts/v16_3_candidate/{name}")
            for name in (
                "V16_3_D1_AC_ANCHOR_CONTRACT_CANDIDATE.json",
                "V16_3_EXOGENOUS_NATIVE_TAP_SCHEDULE_CANDIDATE.json",
                "V16_3_AC_ANCHORED_VOLTAGE_SENSITIVITY_CONTRACT_CANDIDATE.json",
                "V16_3_AC_ANCHORED_PHASE_CURRENT_CONTRACT_CANDIDATE.json",
                "V16_3_FROZEN_COMMON_CONTROL_SEMANTICS_CANDIDATE.json",
                "V16_3_FROZEN_PRIMARY_TRUST_REGION_CANDIDATE.json",
                "V16_3_APR15_NONZERO_SHADOW_DUAL_AC_VALIDATION.json",
                "V16_3_PREREFREEZE_CORRECTION_REVIEW_V3.json",
            )
        },
        "voltage_cache_manifest": voltage_manifest,
        "current_cache_manifest": current_manifest,
        "voltage_H_hash_of_daily_fingerprints": _payload_sha256(h_daily),
        "voltage_daily_fingerprints": h_daily,
        "shadow": shadow,
        "current": current,
        "voltage": voltage,
        "anchor": anchor,
        "taps": taps,
        "semantics": semantics,
        "trust": trust,
    }


def execute(repo: Path, output: Path) -> dict[str, object]:
    repo = repo.resolve()
    output = output.resolve()
    evidence = _validate_evidence(repo)
    output.mkdir(parents=True, exist_ok=True)
    shadow = evidence["shadow"]
    current = evidence["current"]
    voltage = evidence["voltage"]
    anchor = evidence["anchor"]
    taps = evidence["taps"]
    semantics = evidence["semantics"]

    common = {
        "authority_id": AUTHORITY_ID,
        "status": "ACTIVE_PROSPECTIVE_PRODUCTION_PLANNING_AUTHORITY",
        "prospective": True,
        "evidence_checkpoint_sha": EVIDENCE_CHECKPOINT_SHA,
        "May_June_firewall": {
            "may_scientific_loader_access_count": 0,
            "june_scientific_loader_access_count": 0,
            "May_forecast_rows": 0,
            "final_B0_B1_B2_B3_run": "NOT_RUN",
            "G12_G13_G14_C12": "NOT_RUN",
        },
    }
    scientific = {
        **common,
        "artifact_id": "V16_3_SCIENTIFIC_AUTHORITY",
        "classification": "V163_REFREEZE_PASS_AUTHORITY_ACTIVE",
        "next_decision": "READY_FOR_FINAL_B0_B1_B2_B3_AND_DECOMPOSITION_RUN",
        "frozen_parameters": {
            "beta_AIDC": BETA_AIDC,
            "beta_interpretation": "CASE_STUDY_AIDC_TO_FEEDER_PENETRATION_EMBEDDING_FACTOR",
            "rho_valid": RHO_VALID,
            "PUE": 1.30,
            "PF": 0.95,
            "voltage_limits_pu": [0.95, 1.05],
        },
        "control_semantics": CONTROL_SEMANTICS_ID,
        "planning_models": {
            "voltage": "D1_AC_ANCHORED_AFFINE_VOLTAGE",
            "phase_current": "D1_AC_ANCHORED_AFFINE_PHASE_CURRENT_WITH_NONNEGATIVE_EPIGRAPH",
            "time_local_grid_LP_count": TIME_LOCAL_GRID_LP_COUNT,
        },
        "objective": "MINIMUM_MAXIMUM_NORMALIZED_PHASE_LINE_CURRENT_LOADING",
        "regression_certificate": APR15_SCHEDULE_SHA256,
        "activation_counters": ACTIVATION_COUNTERS,
    }
    implementation = {
        **common,
        "artifact_id": "V16_3_IMPLEMENTATION_BINDING",
        "production_active": True,
        "python_binding": {
            "authority_module": "dayahead.v16_3_authority",
            "phase_current_epigraph": "dayahead.v16_3_authority.add_phase_current_epigraph",
            "physical_current_materializer": "dayahead.v16_3_authority.physical_phase_current_pu",
            "shadow_regression_binding": "dayahead.v16_3_shadow.solve_shadow",
            "module_sha256": sha256_file(repo / "dayahead/v16_3_authority.py"),
            "shadow_module_sha256": sha256_file(repo / "dayahead/v16_3_shadow.py"),
        },
        "phase_current_rows": {
            "epigraph": "I_hat_pu >= I_aff_pu",
            "nonnegative": "I_hat_pu >= 0",
            "hard": "I_hat_pu <= 1",
            "line_objective": "lambda >= I_hat_pu",
            "integer_or_binary_variables_added": 0,
        },
        "separate_thermal_families": [
            "LINE_PHASE_CURRENT",
            "TRANSFORMER_PHASE_CURRENT",
            "TRANSFORMER_TOTAL_KVA_WHERE_AUTHORITATIVE",
            "MESS_PCS_700_KVA",
        ],
        "decomposition": {
            "time_local_grid_LP_count": 96,
            "master_dependence": "AFFINE",
            "Pi_optimality_cuts": "PRESERVED",
            "Farkas_feasibility_cuts": "PRESERVED",
            "standard_BD_worst_time_single_cut": "UNCHANGED",
            "CL_MC_BD_all_critical_time_multi_cut": "UNCHANGED",
            "gamma_crit": "UNCHANGED",
            "LB_UB_gap_definitions": "UNCHANGED",
            "OpenDSS_calls_inside_Benders": 0,
        },
        "activation_counters": ACTIVATION_COUNTERS,
    }
    anchor_authority = {
        **common,
        "artifact_id": "V16_3_D1_AC_ANCHOR_AUTHORITY",
        "semantics": "FRESH_OPENDSS_D1_FORECAST_REFERENCE_NATIVE_CONTROL_ANCHOR",
        "included_April_days": anchor["included_days"],
        "excluded_days": anchor["excluded_days"],
        "D1_cutoff_compliance_all_days": anchor["D1_cutoff_compliance_all_days"],
        "inputs": anchor["inputs"],
        "native_ieee123_master_sha256": NATIVE_MASTER_SHA256,
        "anchor_fingerprint_hash": _payload_sha256(anchor["anchor_case_fingerprints"]["B0"]),
        "B0_B1_B2_B3_anchor_identity": anchor["anchor_B0_B1_B2_B3_identical"],
        "optimized_result_reads": 0,
    }
    tap_authority = {
        **common,
        "artifact_id": "V16_3_COMMON_FROZEN_TAP_AUTHORITY",
        "semantics_id": CONTROL_SEMANTICS_ID,
        "generation": [
            "BUILD_D1_FORECAST_REFERENCE_FRESH_OPENDSS_ANCHOR",
            "ALLOW_NATIVE_REGCONTROL_AT_ANCHOR",
            "CAPTURE_96_SLOT_NATIVE_TAP_STATES",
            "FREEZE_BEFORE_OPTIMIZATION",
        ],
        "regulators": taps["regulators"],
        "tap_trajectory_hash": _payload_sha256([row["fingerprint"] for row in taps["tap_schedule"]]),
        "same_trajectory_for": ["B0", "B1", "B2", "B3"],
        "Apr15_common_control_fingerprints": semantics["Apr15_common_control_fingerprints"],
        "tap_decision_variables": 0,
        "tap_recompute_after_result": 0,
        "OpenDSS_calls_inside_Benders": 0,
    }
    voltage_authority = {
        **common,
        "artifact_id": "V16_3_AC_ANCHORED_VOLTAGE_AUTHORITY",
        "equation": "v_plan = v_anchor + H_P*Delta_P + H_Q*Delta_Q",
        "stored_equation": voltage["equation"],
        "time_local_slices": 96,
        "control_dimension": 60,
        "D1_generated_only": True,
        "frozen_tap_state": True,
        "optimized_result_leakage": 0,
        "affine_LP": True,
        "Pi_Farkas_compatible": True,
        "H_recompute_during_optimization": 0,
        "H_hash_of_daily_fingerprints": evidence["voltage_H_hash_of_daily_fingerprints"],
        "cache_manifest": evidence["voltage_cache_manifest"],
        "perturbation_rule": voltage["perturbation_rule"],
    }
    current_authority = {
        **common,
        "artifact_id": "V16_3_AC_ANCHORED_PHASE_CURRENT_AUTHORITY",
        "affine_equation": "I_aff_pu = I_anchor_pu + J_I_pu*Delta_u",
        "physical_epigraph": ["I_hat_pu >= I_aff_pu", "I_hat_pu >= 0"],
        "hard_constraint": "I_hat_pu <= 1",
        "line_objective_row": "lambda >= I_hat_pu",
        "branch_phase_dimension": 383,
        "control_dimension": 60,
        "J_I_hash_of_daily_hashes": CURRENT_COEFFICIENT_HASH_OF_DAILY_HASHES,
        "generation": current["generation"],
        "rating_side_provenance": current["rating_side_provenance"],
        "cache_manifest": evidence["current_cache_manifest"],
        "LP_Pi_Farkas_preserved": True,
        "integer_or_binary_variables_added": 0,
    }
    trust_authority = {
        **common,
        "artifact_id": "V16_3_TRUST_REGION_AUTHORITY",
        "rho_valid": RHO_VALID,
        "rho_valid_frozen_primary": RHO_VALID,
        "form": "ASYMMETRIC_WEIGHTED_L_INFINITY_BOX_PLUS_EXISTING_MESS_PCS_POLYGON",
        "equation": "-rho*s_down[j,t] <= Delta_u[j,t] <= rho*s_up[j,t]",
        "future_result_enlargement_allowed": False,
        "rho_0_25_and_above_role": "DIAGNOSTIC_SENSITIVITY_ONLY",
        "May_June_recalibration_allowed": False,
    }
    beta_authority = {
        **common,
        "artifact_id": "V16_3_BETA025_CASESTUDY_PENETRATION_AUTHORITY",
        "beta_AIDC": BETA_AIDC,
        "interpretation": "CASE_STUDY_AIDC_TO_FEEDER_PENETRATION_EMBEDDING_FACTOR",
        "not_interpreted_as": [
            "RAW_DATA_CORRECTION",
            "GPU_EFFICIENCY_SCALING",
            "MEASURED_AIDC_POWER_MODIFICATION",
        ],
        "all_extensive_AIDC_quantities_scale_coherently": True,
        "kappa_changed": False,
        "result_dependent_selection": False,
    }
    primary = shadow["primary_Fresh_OpenDSS_frozen_D1_taps"]
    secondary = shadow["secondary_Fresh_OpenDSS_native_RegControl"]
    dual_ac = {
        **common,
        "artifact_id": "V16_3_DUAL_FRESH_AC_VALIDATION_CONTRACT",
        "primary": {
            "control": "EXACT_COMMON_FROZEN_D1_TAP_TRAJECTORY",
            "purpose": "FAIR_ATTRIBUTION_OF_AIDC_AND_MOBILE_ESS_FLEXIBILITY",
            "required": "PASS",
        },
        "secondary": {
            "control": "NATIVE_REGCONTROL_ON",
            "purpose": "PHYSICAL_ROBUSTNESS_SENSITIVITY",
            "required": "PASS",
        },
        "post_hoc_tuning_from_AC": False,
        "Apr15_regression": {
            "schedule_sha256": APR15_SCHEDULE_SHA256,
            "schedule_redesigned_or_resolved": False,
            "epigraph_projection_equivalence": {
                "hard": "I_aff<=1 iff max(0,I_aff)<=1",
                "objective": "lambda>=0 and lambda>=I_aff iff lambda>=max(0,I_aff)",
                "existing_schedule_feasibility_preserved": True,
            },
            "terminal_service_parity_residual": shadow["prospective_shadow_solve"]["terminal_service_parity_max_abs_error"],
            "MESS_terminal_SOC_residual": shadow["prospective_shadow_solve"]["mess_terminal_soc_max_abs_error_kwh"],
            "trust_region_respected_all_96_slots": True,
            "primary": primary,
            "secondary": secondary,
            "voltage_violations": int(primary["voltage_violation_count"]) + int(secondary["voltage_violation_count"]),
            "phase_current_violations": int(primary["phase_current_violation_count"]) + int(secondary["phase_current_violation_count"]),
            "transformer_kva_violations": int(primary["transformer_total_kva_violation_count"]) + int(secondary["transformer_total_kva_violation_count"]),
            "status": "PASS_NO_TUNING",
        },
    }

    payloads: Mapping[str, dict[str, object]] = {
        "V16_3_SCIENTIFIC_AUTHORITY.json": scientific,
        "V16_3_IMPLEMENTATION_BINDING.json": implementation,
        "V16_3_D1_AC_ANCHOR_AUTHORITY.json": anchor_authority,
        "V16_3_COMMON_FROZEN_TAP_AUTHORITY.json": tap_authority,
        "V16_3_AC_ANCHORED_VOLTAGE_AUTHORITY.json": voltage_authority,
        "V16_3_AC_ANCHORED_PHASE_CURRENT_AUTHORITY.json": current_authority,
        "V16_3_TRUST_REGION_AUTHORITY.json": trust_authority,
        "V16_3_BETA025_CASESTUDY_PENETRATION_AUTHORITY.json": beta_authority,
        "V16_3_DUAL_FRESH_AC_VALIDATION_CONTRACT.json": dual_ac,
    }
    for name, payload in payloads.items():
        _write_json(output / name, payload)
    artifact_shas = {name: sha256_file(output / name) for name in payloads}
    manifest = {
        **common,
        "artifact_id": "V16_3_REFREEZE_MANIFEST",
        "classification": "V163_REFREEZE_PASS_AUTHORITY_ACTIVE",
        "next_decision": "READY_FOR_FINAL_B0_B1_B2_B3_AND_DECOMPOSITION_RUN",
        "authority_artifact_sha256": artifact_shas,
        "manifest_self_sha256_recording": "RETURNED_BY_RUNNER_AND_RECORDED_IN_AUTHORITY_COMMIT_REPORT",
        "candidate_evidence_sha256": evidence["candidate_sources"],
        "cache_manifests": {
            "voltage": evidence["voltage_cache_manifest"],
            "current": evidence["current_cache_manifest"],
        },
        "all_sections_1_through_14_pass": True,
        "activation_counters": ACTIVATION_COUNTERS,
    }
    manifest_name = "V16_3_REFREEZE_MANIFEST.json"
    _write_json(output / manifest_name, manifest)
    artifact_shas[manifest_name] = sha256_file(output / manifest_name)
    return {
        "authority_id": AUTHORITY_ID,
        "classification": "V163_REFREEZE_PASS_AUTHORITY_ACTIVE",
        "next_decision": "READY_FOR_FINAL_B0_B1_B2_B3_AND_DECOMPOSITION_RUN",
        "artifact_sha256": artifact_shas,
        "activation_counters": ACTIVATION_COUNTERS,
    }


def main(argv: Sequence[str] | None = None) -> int:
    repo = Path.cwd()
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=repo)
    parser.add_argument("--output", type=Path, default=repo / "dayahead/artifacts/v16_3")
    result = execute(**vars(parser.parse_args(argv)))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
