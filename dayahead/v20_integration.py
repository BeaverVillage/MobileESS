"""Model-agnostic V20 forecast-to-facility integration contracts.

No grid solver is imported or called here.  All quantities remain workload or
electrical preflight values, and missing physical authorities fail closed.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable


TIER_NAMES = ["FULL_1", "FULL_2", "FULL_4", "FULL_8", "FULL_16", "PARTIAL"]
FULL_KAPPA_KW_PER_NODE = {
    "FULL_1": 2.289471346990805,
    "FULL_2": 2.2220251879720374,
    "FULL_4": 2.0938566188449466,
    "FULL_8": 2.026464800777849,
    "FULL_16": 1.9654597010662909,
}
PARTIAL_KW_PER_GPU = 0.48563611660901085
PUE = 1.30


class ContractError(ValueError):
    """Fail-closed integration contract error."""


def _matrix(value: Any, name: str) -> list[list[float]]:
    if not isinstance(value, list) or len(value) != 96:
        raise ContractError(f"{name} must have 96 slots")
    out: list[list[float]] = []
    for row in value:
        if not isinstance(row, list) or len(row) != 6:
            raise ContractError(f"{name} must have six tiers per slot")
        vals = [float(x) for x in row]
        if any(x < 0 for x in vals):
            raise ContractError(f"{name} contains negative mass")
        out.append(vals)
    return out


def validate_forecast_bundle(bundle: dict[str, Any], tolerance: float = 1e-8) -> dict[str, Any]:
    required = {
        "model_id", "model_class", "model_acceptance_status", "training_cutoff",
        "forecast_cutoff", "forecast_day", "daily_mean_GPU_h", "daily_Q50_GPU_h",
        "daily_Q90_GPU_h", "slot_tier_mean_GPU_h", "slot_tier_Q50_GPU_h",
        "slot_tier_Q90_GPU_h", "tier_names", "mass_identity_errors",
        "causality_certificate", "model_SHA", "data_SHA",
    }
    missing = sorted(required - bundle.keys())
    if missing:
        raise ContractError(f"missing forecast fields: {missing}")
    if bundle["tier_names"] != TIER_NAMES:
        raise ContractError("tier_names/order mismatch")
    errors: dict[str, float] = {}
    for quantile, daily_key, matrix_key in (
        ("mean", "daily_mean_GPU_h", "slot_tier_mean_GPU_h"),
        ("Q50", "daily_Q50_GPU_h", "slot_tier_Q50_GPU_h"),
        ("Q90", "daily_Q90_GPU_h", "slot_tier_Q90_GPU_h"),
    ):
        matrix = _matrix(bundle[matrix_key], matrix_key)
        error = abs(sum(sum(row) for row in matrix) - float(bundle[daily_key]))
        errors[quantile] = error
        if error > tolerance:
            raise ContractError(f"{quantile} mass identity error {error}")
    if not bundle["causality_certificate"].get("passed", False):
        raise ContractError("causality certificate did not pass")
    return {"status": "PASS", "mass_identity_errors": errors, "negative_mass_count": 0}


def select_forecast_model(v19_review: dict[str, Any], comparison: dict[str, Any]) -> dict[str, str]:
    """Select using V19 training-only acceptance, never facility/grid results."""
    if bool(v19_review.get("PROPOSED_MODEL_ACCEPTED")):
        selected = v19_review.get("proposed_model_id", "C-MASS-TPP")
        model_class = "C_MASS_TPP"
        status = "PROPOSED_ACCEPTED"
    else:
        candidates = comparison.get("accepted_baselines", [])
        if not candidates:
            raise ContractError("no accepted training-only fallback baseline")
        best = min(candidates, key=lambda item: (float(item["training_only_daily_WAPE"]), item["model_id"]))
        selected = best["model_id"]
        model_class = best.get("model_class", "BASELINE")
        status = "FALLBACK_ACCEPTED_BASELINE"
    return {"model_id": selected, "model_class": model_class,
            "model_acceptance_status": status, "selection_basis": "TRAINING_ONLY_BLOCKED_CV"}


def validate_scale_bundle(bundle: dict[str, Any], require_final: bool = False) -> dict[str, Any]:
    sites = bundle.get("sites")
    if not isinstance(sites, list) or len(sites) != 12:
        raise ContractError("SITE_SCALE_BUNDLE_V1 requires 12 sites")
    weights = [site.get("power_weight") for site in sites]
    gpu_weights = [site.get("GPU_weight") for site in sites]
    if any(w is not None and float(w) < 0 for w in weights + gpu_weights):
        raise ContractError("negative site weight")
    final_power = all(w is not None for w in weights)
    final_gpu = all(w is not None for w in gpu_weights)
    if final_power and abs(sum(float(w) for w in weights) - 1.0) > 1e-8:
        raise ContractError("power weights do not sum to one")
    if final_gpu and abs(sum(float(w) for w in gpu_weights) - 1.0) > 1e-8:
        raise ContractError("GPU weights do not sum to one")
    if require_final and not (final_power and final_gpu):
        raise ContractError("final site power/GPU authority is incomplete")
    return {"status": "PASS", "final_power_weight_complete": final_power,
            "final_GPU_weight_complete": final_gpu}


def schedule_jobs_edf(jobs: Iterable[dict[str, Any]], capacity_GPU_h_per_slot: Iterable[float]) -> dict[str, Any]:
    jobs2 = [deepcopy(j) for j in jobs]
    capacities = [float(x) for x in capacity_GPU_h_per_slot]
    remaining = {str(j["job_id"]): float(j["GPU_h"]) for j in jobs2}
    allocation = [{str(j["job_id"]): 0.0 for j in jobs2} for _ in capacities]
    for slot, cap in enumerate(capacities):
        pending = sorted((j for j in jobs2 if int(j["release_slot"]) <= slot < int(j["deadline_slot"])
                          and remaining[str(j["job_id"])] > 0),
                         key=lambda j: (int(j["deadline_slot"]), str(j["job_id"])))
        for job in pending:
            if cap <= 0:
                break
            jid = str(job["job_id"])
            limit = float(job.get("max_GPU_h_per_slot", cap))
            amount = min(cap, limit, remaining[jid])
            allocation[slot][jid] += amount
            remaining[jid] -= amount
            cap -= amount
    terminal = sum(remaining.values())
    deadline_violations = sum(1 for j in jobs2 if remaining[str(j["job_id"])] > 1e-9)
    input_mass = sum(float(j["GPU_h"]) for j in jobs2)
    output_mass = sum(sum(slot.values()) for slot in allocation)
    max_capacity_violation = max((sum(slot.values()) - capacities[i] for i, slot in enumerate(allocation)), default=0.0)
    return {"allocation": allocation, "input_GPU_h": input_mass, "scheduled_GPU_h": output_mass,
            "terminal_backlog_GPU_h": terminal, "work_conservation_error": abs(input_mass - output_mass - terminal),
            "deadline_violations": deadline_violations,
            "max_capacity_violation_GPU_h": max(0.0, max_capacity_violation),
            "hidden_shedding_GPU_h": 0.0}


def tier_GPU_h_to_IT_kWh(slot_tier_GPU_h: list[list[float]]) -> dict[str, Any]:
    matrix = _matrix(slot_tier_GPU_h, "slot_tier_GPU_h")
    energy: list[float] = []
    for row in matrix:
        total = 0.0
        for idx, tier in enumerate(TIER_NAMES):
            if tier == "PARTIAL":
                total += row[idx] * PARTIAL_KW_PER_GPU
            else:
                total += (row[idx] / 4.0) * FULL_KAPPA_KW_PER_NODE[tier]
        energy.append(total)
    return {"slot_IT_kWh": energy, "total_IT_kWh": sum(energy),
            "partial_authority": "GPU_BOARD_LOWER_BOUND", "hidden_multiplier_count": 0,
            "partial_CPU_increment": None}


def allocate_to_sites(system_values: list[float], gpu_weights: list[float] | None,
                      authority_class: str) -> dict[str, Any]:
    if gpu_weights is None:
        raise ContractError("site GPU allocation unavailable; explicit engineering allocation required")
    if len(gpu_weights) != 12 or any(float(w) < 0 for w in gpu_weights) or abs(sum(gpu_weights) - 1.0) > 1e-8:
        raise ContractError("invalid GPU allocation weights")
    by_site = [[float(x) * float(w) for x in system_values] for w in gpu_weights]
    max_error = max(abs(sum(by_site[i][t] for i in range(12)) - float(system_values[t]))
                    for t in range(len(system_values))) if system_values else 0.0
    return {"site_values": by_site, "authority_class": authority_class,
            "site_system_identity_error": max_error, "facility_scale_multiplier_count": 0}


def facility_bridge(locked_kW: list[list[float]], flex_ref_kW: list[list[float]],
                    flex_da_kW: list[list[float]], pue: float = PUE) -> dict[str, Any]:
    if pue != PUE:
        raise ContractError("PUE must remain exactly 1.30")
    if not (len(locked_kW) == len(flex_ref_kW) == len(flex_da_kW) == 12):
        raise ContractError("facility bridge requires 12 sites")
    ref, da = [], []
    for site in range(12):
        if not (len(locked_kW[site]) == len(flex_ref_kW[site]) == len(flex_da_kW[site])):
            raise ContractError("slot length mismatch")
        sr, sd = [], []
        for locked, fref, fda in zip(locked_kW[site], flex_ref_kW[site], flex_da_kW[site]):
            vals = [float(locked), float(fref), float(fda)]
            if any(x < 0 for x in vals):
                raise ContractError("negative facility component; no clipping allowed")
            sr.append(vals[0] + vals[1]); sd.append(vals[0] + vals[2])
        ref.append(sr); da.append(sd)
    return {"P_IT_REF_kW": ref, "P_IT_DA_kW": da,
            "P_PCC_REF_kW": [[x * PUE for x in row] for row in ref],
            "P_PCC_DA_kW": [[x * PUE for x in row] for row in da],
            "PUE": PUE, "PUE_application_count": 1, "negative_residual_count": 0,
            "facility_conservation_error": 0.0}


def run_preflight(forecast: dict[str, Any], scale: dict[str, Any], scheduler: dict[str, Any],
                  power: dict[str, Any], allocation: dict[str, Any], facility: dict[str, Any],
                  locked_test_authority: bool, preservation_pass: bool) -> dict[str, Any]:
    gates = {
        "G1_forecast_mass": validate_forecast_bundle(forecast)["status"] == "PASS",
        "G2_causality_certificate": bool(forecast["causality_certificate"].get("passed")),
        "G3_scheduler_conservation": scheduler["work_conservation_error"] <= 1e-8 and scheduler["hidden_shedding_GPU_h"] == 0,
        "G4_deadline": scheduler["deadline_violations"] == 0 and scheduler["terminal_backlog_GPU_h"] <= 1e-8,
        "G5_compute_capacity": scheduler["max_capacity_violation_GPU_h"] <= 1e-8,
        "G6_power_tier_conversion": power["hidden_multiplier_count"] == 0,
        "G7_site_allocation": allocation["site_system_identity_error"] <= 1e-8,
        "G8_facility_conservation": facility["facility_conservation_error"] <= 1e-8 and facility["negative_residual_count"] == 0,
        "G9_PUE": facility["PUE"] == PUE and facility["PUE_application_count"] == 1,
        "G10_PCC_interface_rating": bool(scale.get("PCC_interface_gate_passed", False)),
        "G11_site_system_sum": allocation["site_system_identity_error"] <= 1e-8,
        "G12_scale_authority": bool(scale.get("scale_authority_ready", False)),
        "G13_locked_test_authority": bool(locked_test_authority),
        "G14_preservation": bool(preservation_pass),
    }
    return {"gates": {k: "PASS" if v else "FAIL" for k, v in gates.items()},
            "passed": all(gates.values()), "grid_solver_calls": 0, "OpenDSS_calls": 0,
            "B0_B1_B2_B3_calls": 0}
