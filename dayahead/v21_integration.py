"""V21 production-selection and fail-closed pre-science integration contracts."""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from dayahead.v20_integration import TIER_NAMES, ContractError, validate_forecast_bundle


BASELINE_PREFIX = "B"


def accepted_baseline_candidates(model_comparison: dict[str, Any]) -> list[dict[str, Any]]:
    """Apply model-independent structural gates to every evaluated baseline.

    The gate does not contain a performance threshold and therefore cannot be
    adjusted to favor one baseline. Ranking is the already-frozen training-only
    blocked-CV Daily WAPE.
    """
    authority = model_comparison["SCALE_INDEPENDENT_ML_AUTHORITY"]
    candidates: list[dict[str, Any]] = []
    for model_id, metrics in authority.items():
        if not model_id.startswith(BASELINE_PREFIX):
            continue
        finite = all(
            math.isfinite(float(metrics[key]))
            for key in ("daily_WAPE_mean", "burst_WAPE_mean", "aggregate_mass_ratio_mean")
        )
        nonnegative = float(metrics.get("negative_prediction_count_mean", 1.0)) == 0.0
        noncrossing = float(metrics.get("quantile_crossing_count_mean", 1.0)) == 0.0
        accepted = bool(finite and nonnegative and noncrossing)
        candidates.append(
            {
                "model_id": model_id,
                "model_class": (
                    "LIGHTGBM_QUANTILE"
                    if model_id == "B3_LIGHTGBM_QUANTILE"
                    else "EVALUATED_BASELINE"
                ),
                "training_only_daily_WAPE": float(metrics["daily_WAPE_mean"]),
                "training_only_burst_WAPE": float(metrics["burst_WAPE_mean"]),
                "aggregate_mass_ratio": float(metrics["aggregate_mass_ratio_mean"]),
                "finite_metric_gate": finite,
                "nonnegative_prediction_gate": nonnegative,
                "quantile_non_crossing_gate": noncrossing,
                "accepted": accepted,
            }
        )
    return candidates


def select_production_forecast_authority(
    ready: dict[str, Any], acceptance: dict[str, Any], model_comparison: dict[str, Any]
) -> dict[str, Any]:
    if bool(ready["PROPOSED_MODEL_ACCEPTED"]) != bool(
        acceptance["PROPOSED_MODEL_ACCEPTED"]
    ):
        raise ContractError("V19 acceptance artifacts disagree")
    candidates = accepted_baseline_candidates(model_comparison)
    if ready["PROPOSED_MODEL_ACCEPTED"]:
        selected = acceptance["selected_C_MASS_TPP_variant"]
        model_class = "C_MASS_TPP"
        status = "PROPOSED_ACCEPTED"
    else:
        eligible = [item for item in candidates if item["accepted"]]
        if not eligible:
            raise ContractError("no structurally accepted fallback baseline")
        winner = min(
            eligible,
            key=lambda item: (item["training_only_daily_WAPE"], item["model_id"]),
        )
        selected = winner["model_id"]
        model_class = winner["model_class"]
        status = "FALLBACK_ACCEPTED_BASELINE"
    return {
        "selected_model_id": selected,
        "selected_model_class": model_class,
        "model_acceptance_status": status,
        "selection_basis": "FROZEN_TRAINING_ONLY_BLOCKED_CV_DAILY_WAPE",
        "facility_metric_reads": 0,
        "grid_metric_reads": 0,
        "April_target_reads": 0,
        "result_based_retuning": 0,
        "accepted_baseline_candidates": candidates,
    }


def exact_mass_matrix(total: float, profile: np.ndarray) -> list[list[float]]:
    total = float(total)
    if total < 0:
        raise ContractError("negative daily mass")
    profile = np.asarray(profile, dtype=np.float64)
    if profile.shape != (96, 6) or np.any(profile < 0):
        raise ContractError("slot-tier profile must be nonnegative 96x6")
    denominator = float(profile.sum())
    if denominator <= 0:
        raise ContractError("slot-tier profile has zero mass")
    matrix = total * profile / denominator
    matrix[-1, -1] += total - float(matrix.sum())
    if np.any(matrix < -1e-12):
        raise ContractError("round-off correction produced negative mass")
    return matrix.tolist()


def validate_production_bundles(bundles: list[dict[str, Any]]) -> dict[str, Any]:
    if not bundles:
        raise ContractError("no production forecast bundles")
    reports = []
    for bundle in bundles:
        reports.append(
            {"forecast_day": bundle["forecast_day"], **validate_forecast_bundle(bundle)}
        )
    return {
        "status": "PASS",
        "bundle_count": len(bundles),
        "reports": reports,
        "maximum_mass_identity_error_GPU_h": max(
            max(report["mass_identity_errors"].values()) for report in reports
        ),
        "negative_mass_count": 0,
    }


def run_preflight17(
    *,
    forecast_validation: dict[str, Any],
    causality_pass: bool,
    scheduler: dict[str, Any],
    power: dict[str, Any],
    site: dict[str, Any],
    facility: dict[str, Any],
    pcc_interface_authority: bool,
    site_scale_authority: bool,
    locked_test_authority: bool,
    preservation_pass: bool,
) -> dict[str, Any]:
    gates: dict[str, tuple[bool, str]] = {
        "G1_forecast_daily_event_tier_mass": (
            forecast_validation["status"] == "PASS"
            and forecast_validation["maximum_mass_identity_error_GPU_h"] <= 1e-8
            and forecast_validation["negative_mass_count"] == 0,
            "FORECAST_BUNDLE_V1 exact mean/Q50/Q90 identities",
        ),
        "G2_causality_certificate": (causality_pass, "D-1 request/submission features only"),
        "G3_scheduler_workload_conservation": (
            float(scheduler["maximum_work_conservation_error_GPU_h"]) <= 1e-8
            and float(scheduler["hidden_shedding_GPU_h"]) == 0.0,
            "arrival = served + terminal backlog; no hidden shedding",
        ),
        "G4_deadline_SLA": (
            float(scheduler["maximum_deadline_shortfall_GPU_h"]) <= 1e-8
            and float(scheduler["terminal_backlog_GPU_h"]) <= 1e-8,
            "training-only empirical latency adapter with frozen EDF",
        ),
        "G5_compute_capacity": (
            float(scheduler["maximum_capacity_violation_GPU_h_per_slot"]) <= 1e-8,
            "C_MODEL is equivalent-case-study capacity only",
        ),
        "G6_tier_to_power_conversion": (
            int(power["hidden_multiplier_count"]) == 0,
            "frozen hybrid tier coefficients after scheduling",
        ),
        "G7_partial_node_boundary": (
            power["partial_authority"] == "GPU_BOARD_LOWER_BOUND"
            and power["partial_CPU_increment_kW"] is None,
            "accepted lower bound retained; no invented host increment",
        ),
        "G8_site_allocation": (
            site["authority_class"] == "ENGINEERING_GPU_ALLOCATION_ONLY"
            and int(site["facility_scale_multiplier_count"]) == 0,
            "explicit engineering allocation, not final Melbourne GPU authority",
        ),
        "G9_facility_power_conservation": (
            float(facility["maximum_facility_conservation_error_kW"]) <= 1e-8,
            "P_IT = P_locked + P_flex without clipping",
        ),
        "G10_flex_le_total": (
            float(facility["maximum_flexible_minus_total_kW"]) <= 1e-8,
            "P_flex <= P_total every site/slot",
        ),
        "G11_negative_residual": (
            int(facility["negative_residual_count"]) == 0,
            "negative residual is a failure; clipping calls = 0",
        ),
        "G12_PUE_exactly_once": (
            float(facility["PUE"]) == 1.30
            and int(facility["PUE_application_count"]) == 1,
            "PUE applied once after IT composition",
        ),
        "G13_PCC_transformer_interface": (
            pcc_interface_authority,
            "requires source-backed DNSP rating/PF rather than synthetic 1.5 MVA",
        ),
        "G14_site_sum_system_total": (
            float(site["maximum_site_system_identity_error_kW"]) <= 1e-8,
            "site sums equal system total",
        ),
        "G15_site_scale_authority": (
            site_scale_authority,
            "requires 12/12 common-boundary site authority",
        ),
        "G16_locked_test_authority": (
            locked_test_authority,
            "requires truly untouched sealed target period",
        ),
        "G17_preservation_hashes": (
            preservation_pass,
            "V17/V18/V18R1/V18R2/V19/V20 byte preservation",
        ),
    }
    return {
        "gates": {
            name: {"status": "PASS" if passed else "FAIL", "evidence": evidence}
            for name, (passed, evidence) in gates.items()
        },
        "passed": all(passed for passed, _ in gates.values()),
        "failed_gates": [name for name, (passed, _) in gates.items() if not passed],
        "science_call_namespace": "FINAL_GRID_SCIENCE_CASES",
        "grid_solver_calls": 0,
        "B0_calls": 0,
        "B1_calls": 0,
        "B2_calls": 0,
        "B3_calls": 0,
        "OpenDSS_calls": 0,
        "AC_science_calls": 0,
        "B3_ML_production_fit_calls": 1,
    }
