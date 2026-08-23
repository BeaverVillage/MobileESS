"""Fail-closed, read-only release gate for the 31-day January campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd

from pfr.canary import run_idc_migration_canary
from pfr.methods import (
    ExperimentAuthority,
    MAIN_COMPARISON_METHODS,
    MethodFactory,
)
from pfr.migration import load_migration_authority
from pfr.provenance import scientific_implementation_fingerprint
from pfr.tools.run_pfr_daily_campaign import ISSUES_PER_DAY, day_specs
from pfr.tools.run_pfr_matrix import _runtime_initial_state


TOTAL_ISSUES = 31 * ISSUES_PER_DAY
EXPECTED_ISSUES = set(range(TOTAL_ISSUES))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def require_files(paths: Sequence[Path], label: str) -> Mapping[str, Any]:
    missing = [str(path) for path in paths if not path.is_file()]
    return {"pass": not missing, "label": label, "missing": missing}


def validate_method_contracts() -> Mapping[str, Any]:
    hashes = tuple(format(index, "064x") for index in range(1, 8))
    factory = MethodFactory(ExperimentAuthority(*hashes))
    configs = factory.all()
    b8 = factory.supplementary()[0]
    periodic = {
        item.comparison_method_id.value
        for item in configs
        if item.control_mode == "PERIODIC_MPC"
    }
    expected_periodic = {"B1", "B2", "B3", "B4", "B5"}
    b0 = configs[0]
    b7 = configs[-1]
    b7_b8_common_capabilities = all(
        getattr(b7, name) == getattr(b8, name)
        for name in (
            "energy_flexibility",
            "temporal_workload_shift",
            "spatial_workload_migration",
            "risk_interface",
            "ai_training_aware",
            "joint_uncertainty",
            "slow_fast_control",
            "ac_safety_filter",
            "authority_fingerprint",
        )
    )
    passed = bool(
        tuple(item.comparison_method_id for item in configs)
        == MAIN_COMPARISON_METHODS
        and periodic == expected_periodic
        and b0.energy_flexibility == "NONE"
        and not b0.temporal_workload_shift
        and not b0.spatial_workload_migration
        and not b0.slow_fast_control
        and all(item.ac_safety_filter for item in configs)
        and b8.comparison_method_id.value == "B8"
        and b8.control_mode == "PERIODIC_MPC"
        and b8.periodic_replan_steps == 1
        and b8.risk_interface == "CALIBRATED"
        and b8.ac_safety_filter
        and b7_b8_common_capabilities
    )
    return {
        "pass": passed,
        "periodic_methods": sorted(periodic),
        "b0_capability": {
            "energy": b0.energy_flexibility,
            "temporal_compute": b0.temporal_workload_shift,
            "spatial_compute": b0.spatial_workload_migration,
            "fast_recourse": b0.slow_fast_control,
        },
        "safety_filter_common": all(item.ac_safety_filter for item in configs),
        "safety_controllable_subset_is_method_restricted": True,
        "supplementary_b8": {
            "control_mode": b8.control_mode,
            "periodic_replan_steps": b8.periodic_replan_steps,
            "periodic_replan_minutes": 5,
            "risk_interface": b8.risk_interface,
            "main_registry_unchanged": True,
            "same_capabilities_as_b7_except_replan_invocation_timing": (
                b7_b8_common_capabilities
            ),
            "migration_checkpoint_authority_is_runtime_common": True,
        },
    }


def validate_migration_authority(path: Path) -> Mapping[str, Any]:
    authority = load_migration_authority(path)
    passed = bool(
        authority.authority_id == "PFR_IDC_MIGRATION_ABILENE12_H10080_V1"
        and authority.dataset_residency_mode == "PRESTAGED_AT_ALL_12_IDCS"
        and authority.checkpoint_interval_steps == 6
        and authority.framebuffer_reference_bytes_per_gpu == 80_000_000_000
        and authority.checkpoint_payload_occupancy_factor == 1.0
        and authority.sensitivity_factors == (0.25, 0.5, 1.0)
        and authority.restart_steps == 1
        and authority.maximum_active_transfers == 1
        and authority.transfer_capacity_bytes_per_step("IDC01", "IDC02") > 0
    )
    return {
        "pass": passed,
        "authority_id": authority.authority_id,
        "sha256": authority.fingerprint,
        "checkpoint_interval_steps": authority.checkpoint_interval_steps,
        "framebuffer_reference_bytes_per_gpu": (
            authority.framebuffer_reference_bytes_per_gpu
        ),
        "checkpoint_payload_occupancy_factor": (
            authority.checkpoint_payload_occupancy_factor
        ),
        "january_development_sensitivity_factors": authority.sensitivity_factors,
        "contract_sha256": authority.contract_fingerprint,
        "parameterization_sha256": authority.fingerprint,
        "restart_steps": authority.restart_steps,
        "dataset_residency_mode": authority.dataset_residency_mode,
        "parameter_classification": "MODELED_NOT_MEASURED",
    }


def validate_migration_runtime_canary(path: Path) -> Mapping[str, Any]:
    authority = load_migration_authority(path)
    with tempfile.TemporaryDirectory() as temporary:
        return run_idc_migration_canary(authority, Path(temporary))


def validate_common_native_grid_control(
    authority_path: Path, dss_path: Path, asset_audit_path: Path
) -> Mapping[str, Any]:
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    asset_audit = json.loads(asset_audit_path.read_text(encoding="utf-8"))
    capacitors = authority.get("existing_capacitors", ())
    control = authority.get("frozen_post_hoc_control_basis", {})
    dss = dss_path.read_text(encoding="utf-8")
    expected_names = {"C83", "C88a", "C90b", "C92c"}
    observed_names = {str(row.get("name")) for row in capacitors}
    passed = bool(
        authority.get("status")
        == "FROZEN_APPROVED_POST_HOC_VALIDATION_ONLY"
        and authority.get("scientific_authority_version")
        == "V13_13_POST_HOC_P100_FEEDER_SCALE_NATIVE_ELASTIC_AC_FREEZE_20260823"
        and authority.get("common_to_B0_B7") is True
        and authority.get("optimized_by_B_method") is False
        and authority.get("main_scientific_campaign_authorized") is False
        and authority.get("january_2025_post_hoc_validation_authorized") is True
        and authority.get("evaluation_classification")
        == "POST_HOC_DESIGN_VALIDATION_NOT_INDEPENDENT_HOLDOUT"
        and authority.get("asset_audit_authority")
        == "IEEE123_NATIVE_CONTROL_ASSET_AUDIT_V1"
        and asset_audit.get("status")
        == "PASS_ASSET_AUDIT_PARAMETER_GAP_FOUND"
        and asset_audit.get("source_sha256")
        == authority.get("original_ieee123_master_sha256")
        and asset_audit.get("compiled_audit", {}).get("capcontrol_count") == 0
        and authority.get("original_ieee123_master_modified") is False
        and authority.get("physical_topology_changed") is False
        and authority.get("capacitor_locations_or_ratings_changed") is False
        and observed_names == expected_names
        and sum(float(row["kvar"]) for row in capacitors) == 750.0
        and float(control.get("on_setting_v", float("nan"))) == 114.6
        and float(control.get("off_setting_v", float("nan"))) == 125.4
        and float(control.get("on_setting_pu", float("nan"))) == 0.955
        and float(control.get("off_setting_pu", float("nan"))) == 1.045
        and float(control.get("dead_time_seconds", float("nan"))) == 1800.0
        and authority.get("feeder_wide_global_guard", {}).get(
            "maximum_capacitor_candidate_states"
        )
        == 16
        and authority.get("feeder_wide_global_guard", {}).get(
            "maximum_total_candidate_evaluations"
        )
        == 928
        and authority.get("feeder_wide_global_guard", {}).get(
            "regulator_search_beam_width"
        )
        == 4
        and authority.get("feeder_wide_global_guard", {}).get(
            "regulator_search_tap_anchor_count"
        )
        == 2
        and authority.get("feeder_wide_global_guard", {}).get(
            "maximum_regulator_search_iterations"
        )
        == 16
        and authority.get("feeder_wide_global_guard", {}).get(
            "fixed_candidate_state_includes_capacitors_and_regulator_taps"
        )
        is True
        and authority.get("feeder_wide_global_guard", {}).get(
            "deep_restoration_algorithm"
        )
        == "FRESH_EXACT_FINITE_DIFFERENCE_INTEGER_TRUST_REGION"
        and authority.get("feeder_wide_global_guard", {}).get(
            "deep_restoration_seed_per_capacitor_state"
        )
        == 1
        and authority.get("feeder_wide_global_guard", {}).get(
            "deep_restoration_integer_trust_region_radius"
        )
        == 8
        and authority.get("feeder_wide_global_guard", {}).get(
            "deep_restoration_maximum_relinearizations"
        )
        == 4
        and authority.get("feeder_wide_global_guard", {}).get(
            "deep_restoration_exact_backtracking_fractions"
        )
        == [1.0, 0.5, 0.25, 0.125]
        and authority.get("feeder_wide_global_guard", {}).get(
            "deep_restoration_maximum_native_candidate_evaluations"
        )
        == 1184
        and authority.get("feeder_wide_global_guard", {}).get(
            "deep_restoration_maximum_total_candidate_evaluations"
        )
        == 1184
        and authority.get("feeder_wide_global_guard", {})
        .get("pv_volt_var", {})
        .get("enabled")
        is False
        and authority.get("feeder_wide_global_guard", {}).get(
            "deep_restoration_adds_mess_compute_or_load_shedding"
        )
        is False
        and authority.get("feeder_wide_global_guard", {}).get(
            "b_method_variables_introduced"
        )
        is False
        and authority.get("feeder_wide_global_guard", {}).get(
            "hard_limits_relaxed"
        )
        is False
        and all(f"Capacitor={name}" in dss for name in expected_names)
        and dss.count("New CapControl.") == 4
    )
    return {
        "pass": passed,
        "identity": authority.get("identity"),
        "scientific_authority_version": authority.get(
            "scientific_authority_version"
        ),
        "common_to_B0_B7": authority.get("common_to_B0_B7"),
        "original_ieee123_master_modified": authority.get(
            "original_ieee123_master_modified"
        ),
        "capacitors": sorted(observed_names),
        "total_existing_capacitor_kvar": sum(
            float(row.get("kvar", 0.0)) for row in capacitors
        ),
        "dss_sha256": sha256(dss_path),
        "authority_sha256": sha256(authority_path),
        "asset_audit_sha256": sha256(asset_audit_path),
        "main_scientific_campaign_authorized": authority.get(
            "main_scientific_campaign_authorized"
        ),
        "parameter_authority_resolution": authority.get(
            "parameter_authority_resolution", {}
        ),
    }


def validate_native_grid_control_release(authority_path: Path) -> Mapping[str, Any]:
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    released = bool(
        authority.get("status")
        == "FROZEN_APPROVED_POST_HOC_VALIDATION_ONLY"
        and authority.get("january_2025_post_hoc_validation_authorized") is True
        and authority.get("main_scientific_campaign_authorized") is False
        and authority.get("outcome_informed_parameter_tuning") is True
        and authority.get("evaluation_classification")
        == "POST_HOC_DESIGN_VALIDATION_NOT_INDEPENDENT_HOLDOUT"
    )
    return {
        "pass": released,
        "status": authority.get("status"),
        "main_scientific_campaign_authorized": authority.get(
            "main_scientific_campaign_authorized"
        ),
        "blocker": None
        if released
        else "JANUARY_POST_HOC_CAPACITOR_AUTHORITY_NOT_FROZEN",
    }


def validate_background_load_scale_audit(path: Path) -> Mapping[str, Any]:
    audit = json.loads(path.read_text(encoding="utf-8"))
    scale = audit.get("scaling_contract", {})
    evidence = audit.get("feeder_evidence", {})
    decision = audit.get("decision", {})
    passed = bool(
        audit.get("status")
        == "SUPERSEDED_P95_IS_INTENTIONAL_BUT_INCOMPATIBLE_WITH_B0_HARD_FEASIBILITY"
        and scale.get("configured_reference") == "p95"
        and abs(float(scale.get("ieee123_native_active_load_kw", 0.0)) - 3490.0)
        <= 1e-9
        and abs(float(scale.get("ieee123_native_reactive_load_kvar", 0.0)) - 1920.0)
        <= 1e-9
        and abs(float(scale.get("p95_operational_net_target_kw", 0.0)) - 3490.0)
        <= 0.001
        and float(evidence.get("official_48h_max_transformer_current_loading_pu", 2.0))
        < 1.0
        and float(
            evidence.get(
                "annual_background_peak_max_transformer_current_loading_pu", 0.0
            )
        )
        > 1.0
        and audit.get("comparison_interpretation", {}).get("alpha_grid_applied")
        is True
        and audit.get("superseded_by") == "FEEDER_ABSOLUTE_SCALE_CONTRACT_V2"
        and decision.get("classification")
        == "CASE_B_INTENTIONAL_STRESS_SUPERSEDED_BY_EXPERIMENT_FEASIBILITY_CONTRACT"
        and decision.get("background_load_scaling_change")
        == "AUTHORIZED_ONLY_BY_FEEDER_ABSOLUTE_SCALE_CONTRACT_V2"
    )
    return {
        "pass": passed,
        "status": audit.get("status"),
        "configured_reference": scale.get("configured_reference"),
        "equivalent_active_mapping_kw_per_regional_mw": scale.get(
            "equivalent_active_mapping_kw_per_regional_mw"
        ),
        "official_48h_max_transformer_current_loading_pu": evidence.get(
            "official_48h_max_transformer_current_loading_pu"
        ),
        "annual_background_peak_max_transformer_current_loading_pu": evidence.get(
            "annual_background_peak_max_transformer_current_loading_pu"
        ),
        "alpha_grid_applied": audit.get("comparison_interpretation", {}).get(
            "alpha_grid_applied"
        ),
        "sha256": sha256(path),
    }


def validate_feeder_absolute_scale(path: Path) -> Mapping[str, Any]:
    contract = json.loads(path.read_text(encoding="utf-8"))
    expected = 7100.2615 / 9490.53
    alpha = float(contract.get("alpha_grid", float("nan")))
    prohibited = contract.get("prohibited_features", {})
    passed = bool(
        contract.get("status") == "FROZEN_POST_HOC_P100_FEEDER_SCALE"
        and contract.get("scientific_authority_version")
        == "V13_13_POST_HOC_P100_FEEDER_SCALE_NATIVE_ELASTIC_AC_FREEZE_20260823"
        and abs(alpha - expected) <= 1e-15
        and contract.get("parameter_selection_is_failure_ratio_fit") is False
        and prohibited.get("pv_inverter_kva_inferred_from_peak_available_kw") is False
        and prohibited.get("pv_reactive_power_enabled_without_nameplate_authority") is False
        and prohibited.get("emergency_mess") is False
        and prohibited.get("load_shedding") is False
        and prohibited.get("hard_limit_relaxation") is False
        and prohibited.get("rating_uprate") is False
    )
    return {
        "pass": passed,
        "status": contract.get("status"),
        "alpha_grid": alpha,
        "scaled_quantities": contract.get("scaled_quantities", ()),
        "sha256": sha256(path),
    }


def validate_background_native_feasibility_gate(path: Path) -> Mapping[str, Any]:
    gate = json.loads(path.read_text(encoding="utf-8"))
    operating = gate.get("scan_operating_point", {})
    acceptance = gate.get("exact_acceptance", {})
    decisions = {
        row.get("decision") for row in gate.get("decision_logic", ())
    }
    passed = bool(
        gate.get("status") == "FROZEN_POST_HOC_GATE"
        and float(operating.get("facility_idc_p_kw", float("nan"))) == 0.0
        and float(operating.get("facility_idc_q_kvar", float("nan"))) == 0.0
        and float(operating.get("mess_p_kw", float("nan"))) == 0.0
        and float(operating.get("mess_q_kvar", float("nan"))) == 0.0
        and operating.get("mess_mobility_or_dispatch") is False
        and operating.get("load_shedding") is False
        and float(acceptance.get("minimum_voltage_pu", float("nan"))) == 0.95
        and float(acceptance.get("maximum_voltage_pu", float("nan"))) == 1.05
        and float(acceptance.get("maximum_line_loading_pu", float("nan"))) == 1.0
        and float(
            acceptance.get(
                "maximum_transformer_current_or_kva_loading_pu", float("nan")
            )
        )
        == 1.0
        and acceptance.get("hard_limits_relaxed") is False
        and "KEEP_CURRENT_PHYSICAL_SCALE" in decisions
        and "REQUIRE_SEPARATE_LEGAL_STATE_REACHABILITY_CERTIFICATE" in decisions
        and "WHOLE_SYSTEM_SCALE_REDESIGN_REVIEW" in decisions
    )
    return {
        "pass": passed,
        "status": gate.get("status"),
        "zero_idc": operating.get("facility_idc_p_kw") == 0.0,
        "zero_mess": operating.get("mess_p_kw") == 0.0,
        "hard_limits_relaxed": acceptance.get("hard_limits_relaxed"),
        "decisions": sorted(value for value in decisions if value),
    }


def validate_daily_pre(path: Path) -> Mapping[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    first = _runtime_initial_state(data, 0, require_population_identity=True)
    last = _runtime_initial_state(
        data, 30 * ISSUES_PER_DAY, require_population_identity=True
    )
    passed = bool(
        first.mess_energy_kwh == last.mess_energy_kwh
        and first.mess_location == last.mess_location
        and tuple(first.mess_energy_kwh.values()) == (760.0,) * 4
        and tuple(first.mess_location.values())
        == ("STA09", "IDC12", "STA07", "STA11")
    )
    return {
        "pass": passed,
        "canonical_pre_sha256": data.get("canonical_pre_sha256"),
        "daily_episode_count": data.get("daily_episode_count"),
        "first_issue": first.issue,
        "last_day_first_issue": last.issue,
    }


def validate_power_sources(shared_root: Path) -> Mapping[str, Any]:
    observed: set[int] = set()
    missing_files: list[str] = []
    malformed_blocks: list[str] = []
    power_root = shared_root / "power_price"
    for block in range(16):
        start = block * 576
        root = power_root / f"block_{block:02d}_{start}_{start + 575}"
        required = (
            root / "BLOCK_AUTHORITY.json",
            root / "power__issues.npy",
            root / "power__q50_net_background_p_kw.npy",
            root / "power__q50_background_q_kvar.npy",
            root / "power__q90_gross_background_p_kw.npy",
            root / "power__q90_background_q_kvar.npy",
            root / "power__q10_pv_available_kw.npy",
            root / "price__issues.npy",
            root / "price__q50.npy",
        )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            missing_files.extend(missing)
            continue
        issues = np.asarray(np.load(required[1], mmap_mode="r"), dtype=np.int64)
        selected = issues[(issues >= 0) & (issues < TOTAL_ISSUES)]
        if len(set(map(int, selected))) != len(selected):
            malformed_blocks.append(str(root))
        observed.update(map(int, selected))
    missing_issues = sorted(EXPECTED_ISSUES - observed)
    extra_issues = sorted(observed - EXPECTED_ISSUES)
    return {
        "pass": not missing_files and not malformed_blocks and not missing_issues and not extra_issues,
        "observed_issue_count": len(observed),
        "missing_files": missing_files,
        "malformed_blocks": malformed_blocks,
        "missing_issue_sample": missing_issues[:20],
        "extra_issue_sample": extra_issues[:20],
        "grid_envelope_role": "PLAN_VALIDITY_DIAGNOSTIC_NOT_REALIZED_H0_COMMIT_GATE",
    }


def validate_mobility_sources(roots: Sequence[Path]) -> Mapping[str, Any]:
    observed: dict[int, str] = {}
    duplicates: list[int] = []
    malformed: list[str] = []
    for root in roots:
        for path in (root / "mobility_runtime").glob("issue_*.npz"):
            try:
                issue = int(path.stem.split("_")[1])
            except (IndexError, ValueError):
                malformed.append(str(path))
                continue
            if issue in observed:
                duplicates.append(issue)
            observed[issue] = str(path)
    observed_issues = set(observed)
    missing = sorted(EXPECTED_ISSUES - observed_issues)
    return {
        "pass": not duplicates and not malformed and not missing,
        "observed_issue_count": len(observed_issues & EXPECTED_ISSUES),
        "duplicates": sorted(set(duplicates))[:20],
        "malformed": malformed[:20],
        "missing_issue_sample": missing[:20],
    }


def validate_uncertainty(
    factorized_path: Path, workload_path: Path
) -> Mapping[str, Any]:
    factorized = json.loads(factorized_path.read_text(encoding="utf-8"))
    workload = json.loads(workload_path.read_text(encoding="utf-8"))
    components = factorized.get("components", {})
    grid = components.get("U_grid", {})
    passed = bool(
        factorized.get("status") == "PASS"
        and factorized.get("joint_cross_factor_recalibration") is False
        and set(components) == {"U_mob", "U_work", "U_grid"}
        and grid.get("authority_type") == "CAUSAL_ADAPTIVE_QUANTILE_ENVELOPE"
        and workload.get("status") == "PASS"
        and workload.get("calibration_year") == 2024
        and workload.get("no_2025_recalibration") is True
        and set(workload.get("idc_gpu_reserve", {}))
        == {f"IDC{index:02d}" for index in range(1, 13)}
    )
    return {
        "pass": passed,
        "factorization": factorized.get("uncertainty_universe"),
        "joint_cross_factor_recalibration": factorized.get(
            "joint_cross_factor_recalibration"
        ),
        "grid_authority_type": grid.get("authority_type"),
        "workload_calibration_year": workload.get("calibration_year"),
    }


def validate_jobs(independent_path: Path, canonical_path: Path) -> Mapping[str, Any]:
    independent = pd.read_parquet(
        independent_path,
        columns=("job_uid", "arrival_step", "requested_gpu"),
    )
    canonical = pd.read_parquet(
        canonical_path,
        columns=("job_uid", "runtime_seconds_source", "job_power_prefreeze_authorized"),
    )
    arrivals = independent["arrival_step"].astype(int)
    passed = bool(
        not independent["job_uid"].astype(str).duplicated().any()
        and not canonical["job_uid"].astype(str).duplicated().any()
        and (independent["requested_gpu"].astype(int) > 0).all()
        and (canonical["runtime_seconds_source"].astype(float) > 0).all()
        and canonical["job_power_prefreeze_authorized"].fillna(False).all()
        and ((arrivals >= 0) & (arrivals < TOTAL_ISSUES)).all()
    )
    return {
        "pass": passed,
        "independent_job_count": len(independent),
        "canonical_job_count": len(canonical),
        "arrival_min": int(arrivals.min()) if len(arrivals) else None,
        "arrival_max": int(arrivals.max()) if len(arrivals) else None,
    }


def write_report(path: Path, report: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--shared-root", type=Path, required=True)
    parser.add_argument("--exact-package-root", type=Path, required=True)
    parser.add_argument("--authority-package-root", type=Path, required=True)
    parser.add_argument("--primary-root", type=Path, required=True)
    parser.add_argument("--initial-state", type=Path, required=True)
    parser.add_argument("--independent-jobs", type=Path, required=True)
    parser.add_argument("--canonical-jobs", type=Path, required=True)
    parser.add_argument("--power-curve", type=Path, required=True)
    parser.add_argument("--mobility-root", type=Path, action="append", required=True)
    parser.add_argument("--route-catalog", type=Path, required=True)
    parser.add_argument("--mobility-template-bank", type=Path, required=True)
    parser.add_argument("--workload-uncertainty", type=Path, required=True)
    parser.add_argument("--factorized-uncertainty", type=Path, required=True)
    parser.add_argument(
        "--migration-authority",
        type=Path,
        help="Frozen IDC migration authority; defaults to the repository contract.",
    )
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    migration_authority_path = (
        args.migration_authority
        if args.migration_authority is not None
        else args.repo / "pfr/contracts/IDC_MIGRATION_AUTHORITY_V1.json"
    )

    basic_paths = (
        args.repo / "pfr/runtime.py",
        args.repo / "pfr/tools/run_pfr_matrix.py",
        args.repo / "pfr/tools/run_pfr_daily_campaign.py",
        args.exact_package_root / "opendss_metrics_common.py",
        args.repo / "science/EXACT_GRID_RUNNER_24SERVICE.py",
        args.initial_state,
        args.independent_jobs,
        args.canonical_jobs,
        args.power_curve,
        args.route_catalog,
        args.mobility_template_bank,
        args.workload_uncertainty,
        args.factorized_uncertainty,
        args.repo / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.dss",
        args.repo / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.json",
        args.repo / "pfr/contracts/IEEE123_NATIVE_CONTROL_ASSET_AUDIT_V1.json",
        args.repo / "pfr/contracts/PFR10_GLOBAL_AC_PROJECTION_REDESIGN_V8.json",
        args.repo / "pfr/contracts/BACKGROUND_LOAD_SCALE_CONSISTENCY_AUDIT_V1.json",
        args.repo / "pfr/contracts/BACKGROUND_NATIVE_FEASIBILITY_GATE_V1.json",
        args.repo / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json",
        args.repo / "pfr/tools/run_background_native_feasibility_gate.py",
        migration_authority_path,
    )
    checks: dict[str, Mapping[str, Any]] = {
        "required_files": require_files(basic_paths, "campaign authority files"),
        "required_directories": {
            "pass": all(
                path.is_dir()
                for path in (
                    args.repo,
                    args.shared_root,
                    args.exact_package_root,
                    args.authority_package_root,
                    args.primary_root,
                    *args.mobility_root,
                )
            ),
            "paths": [
                str(path)
                for path in (
                    args.repo,
                    args.shared_root,
                    args.exact_package_root,
                    args.authority_package_root,
                    args.primary_root,
                    *args.mobility_root,
                )
            ],
        },
    }
    if checks["required_files"]["pass"]:
        checks.update(
            {
                "method_contracts": validate_method_contracts(),
                "migration_authority": validate_migration_authority(
                    migration_authority_path
                ),
                "migration_runtime_canary": validate_migration_runtime_canary(
                    migration_authority_path
                ),
                "common_native_grid_control": validate_common_native_grid_control(
                    args.repo
                    / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.json",
                    args.repo
                    / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.dss",
                    args.repo
                    / "pfr/contracts/IEEE123_NATIVE_CONTROL_ASSET_AUDIT_V1.json",
                ),
                "native_grid_control_release_gate": validate_native_grid_control_release(
                    args.repo
                    / "pfr/contracts/COMMON_NATIVE_GRID_VOLT_VAR_CONTROL_V1.json"
                ),
                "background_load_scale_consistency": validate_background_load_scale_audit(
                    args.repo
                    / "pfr/contracts/BACKGROUND_LOAD_SCALE_CONSISTENCY_AUDIT_V1.json"
                ),
                "background_native_feasibility_gate": validate_background_native_feasibility_gate(
                    args.repo
                    / "pfr/contracts/BACKGROUND_NATIVE_FEASIBILITY_GATE_V1.json"
                ),
                "feeder_absolute_scale": validate_feeder_absolute_scale(
                    args.repo
                    / "pfr/contracts/FEEDER_ABSOLUTE_SCALE_CONTRACT_V2.json"
                ),
                "daily_pre": validate_daily_pre(args.initial_state),
                "power_sources": validate_power_sources(args.shared_root),
                "mobility_sources": validate_mobility_sources(args.mobility_root),
                "uncertainty": validate_uncertainty(
                    args.factorized_uncertainty, args.workload_uncertainty
                ),
                "jobs": validate_jobs(args.independent_jobs, args.canonical_jobs),
            }
        )
        route = json.loads(args.route_catalog.read_text(encoding="utf-8"))
        template = pd.read_parquet(args.mobility_template_bank)
        checks["route_and_template"] = {
            "pass": route.get("status") == "PASS"
            and len(route.get("routes", ())) == 1656
            and all(f"u{index:03d}" in template for index in range(129)),
            "route_count": len(route.get("routes", ())),
            "template_row_count": len(template),
        }
    status = "PASS" if checks and all(row.get("pass") is True for row in checks.values()) else "FAIL_CLOSED"
    report = {
        "schema_version": "JAN2025_31DAY_POST_HOC_PREFLIGHT_V13_13_FREEZE_20260823",
        "evaluation_classification": "POST_HOC_DESIGN_VALIDATION_NOT_INDEPENDENT_HOLDOUT",
        "independent_holdout_claim": False,
        "status": status,
        "campaign_days": len(day_specs(1, 31)),
        "expected_episodes": 31 * 8,
        "expected_scored_issues": TOTAL_ISSUES * 8,
        "checks": checks,
        "critical_code_sha256": {
            str(path.relative_to(args.repo)): sha256(path)
            for path in basic_paths[:3]
        },
        "scientific_implementation_fingerprint": scientific_implementation_fingerprint(
            args.repo
        ),
    }
    write_report(args.report, report)
    print(json.dumps({"status": status, "report": str(args.report)}), flush=True)
    if status != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
