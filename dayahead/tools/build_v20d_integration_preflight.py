"""Build V20D contracts and execute deterministic integration preflight."""

from __future__ import annotations

import json
from pathlib import Path

from dayahead.v20_integration import (
    TIER_NAMES, allocate_to_sites, facility_bridge, run_preflight,
    schedule_jobs_edf, select_forecast_model, tier_GPU_h_to_IT_kWh,
    validate_forecast_bundle, validate_scale_bundle,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"


def write(name: str, value: object) -> None:
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def matrix(total: float) -> list[list[float]]:
    value = total / (96 * 6)
    return [[value] * 6 for _ in range(96)]


def forecast_fixture() -> dict[str, object]:
    return {
        "schema": "FORECAST_BUNDLE_V1", "model_id": "FIXTURE_BASELINE",
        "model_class": "DETERMINISTIC_TEST_FIXTURE", "model_acceptance_status": "TEST_ONLY",
        "training_cutoff": "2025-03-31T23:59:59+10:00",
        "forecast_cutoff": "2025-03-31T18:00:00+10:00", "forecast_day": "2025-04-01",
        "daily_mean_GPU_h": 12.0, "daily_Q50_GPU_h": 10.0, "daily_Q90_GPU_h": 20.0,
        "slot_tier_mean_GPU_h": matrix(12.0), "slot_tier_Q50_GPU_h": matrix(10.0),
        "slot_tier_Q90_GPU_h": matrix(20.0), "tier_names": TIER_NAMES,
        "mass_identity_errors": {"mean": 0.0, "Q50": 0.0, "Q90": 0.0},
        "causality_certificate": {"passed": True, "future_actual_feature_reads": 0},
        "model_SHA": "1" * 64, "data_SHA": "2" * 64,
    }


def scale_fixture(final: bool) -> dict[str, object]:
    sites = []
    for i in range(12):
        sites.append({"site_id": f"AIDC{i+1:02d}", "P_IT_peak": 0.1 if final else None,
                      "P_PCC_peak": 0.13 if final else None,
                      "power_weight": 1 / 12 if final else None,
                      "scale_authority_class": "FIXTURE_FINAL" if final else "INCOMPLETE_V20A",
                      "GPU_weight": 1 / 12 if final else None,
                      "GPU_weight_authority_class": "FIXTURE_FINAL" if final else "NOT_IDENTIFIABLE",
                      "transformer_interface_rating_kVA": 1500.0,
                      "REAL_DNSP_RATING": False, "source_evidence_SHA": "3" * 64})
    return {"schema": "SITE_SCALE_BUNDLE_V1", "sites": sites,
            "scale_authority_ready": final, "PCC_interface_gate_passed": final}


def main() -> None:
    forecast_contract = {
        "artifact_id": "V20D_FORECAST_BUNDLE_CONTRACT_V1", "schema": "FORECAST_BUNDLE_V1",
        "required_fields": ["model_id", "model_class", "model_acceptance_status", "training_cutoff",
                            "forecast_cutoff", "forecast_day", "daily_mean_GPU_h", "daily_Q50_GPU_h",
                            "daily_Q90_GPU_h", "slot_tier_mean_GPU_h[96,6]", "slot_tier_Q50_GPU_h[96,6]",
                            "slot_tier_Q90_GPU_h[96,6]", "tier_names", "mass_identity_errors",
                            "causality_certificate", "model_SHA", "data_SHA"],
        "tier_names": TIER_NAMES, "mass_tolerance": 1e-8, "negative_mass_allowed": False,
        "model_name_dependency": False,
    }
    write("V20D_FORECAST_BUNDLE_CONTRACT.json", forecast_contract)

    write("V20D_SITE_SCALE_BUNDLE_CONTRACT.json", {
        "artifact_id": "V20D_SITE_SCALE_BUNDLE_CONTRACT_V1", "schema": "SITE_SCALE_BUNDLE_V1",
        "site_fields": ["site_id", "P_IT_peak", "P_PCC_peak", "power_weight",
                        "scale_authority_class", "GPU_weight", "GPU_weight_authority_class",
                        "transformer_interface_rating", "source/evidence_SHA"],
        "null_allowed": True, "null_imputation_allowed": False,
        "power_weight_equals_GPU_weight_assumed": False,
    })

    accepted = select_forecast_model(
        {"PROPOSED_MODEL_ACCEPTED": True, "proposed_model_id": "C-MASS-TPP"},
        {"accepted_baselines": [{"model_id": "B2", "training_only_daily_WAPE": 0.4}]})
    fallback = select_forecast_model(
        {"PROPOSED_MODEL_ACCEPTED": False},
        {"accepted_baselines": [{"model_id": "B2", "model_class": "LIGHTGBM",
                                  "training_only_daily_WAPE": 0.4},
                                 {"model_id": "B1", "model_class": "RULE",
                                  "training_only_daily_WAPE": 0.6}]})
    write("V20D_MODEL_SELECTION_ADAPTER_CONTRACT.json", {
        "artifact_id": "V20D_MODEL_SELECTION_ADAPTER_CONTRACT_V1",
        "selection_rule": "C-MASS iff V19 PROPOSED_MODEL_ACCEPTED=true; else minimum training-only blocked-CV WAPE accepted baseline",
        "facility_or_grid_metric_reads": 0, "V19_absent_behavior": "MOCK_FIXTURE_TEST_ONLY_NO_PRODUCTION_SELECTION",
        "accepted_fixture": accepted, "fallback_fixture": fallback,
    })

    write("V20D_FINAL_INTEGRATION_PREFLIGHT_CONTRACT.json", {
        "artifact_id": "V20D_FINAL_INTEGRATION_PREFLIGHT_CONTRACT_V1",
        "gates": [f"G{i}" for i in range(1, 15)],
        "gate_meanings": ["forecast mass", "causality certificate", "scheduler conservation", "deadline",
                          "compute capacity", "power-tier conversion", "site allocation",
                          "facility conservation", "PUE", "PCC/interface rating", "site/system sum",
                          "scale authority", "locked-test authority", "preservation"],
        "grid_solver_calls": 0, "command": "python -m dayahead.tools.build_v20d_integration_preflight",
    })

    forecast = forecast_fixture(); validate_forecast_bundle(forecast)
    final_scale = scale_fixture(True); validate_scale_bundle(final_scale, require_final=True)
    jobs = [{"job_id": "a", "GPU_h": 1.0, "release_slot": 0, "deadline_slot": 4,
             "max_GPU_h_per_slot": 0.5},
            {"job_id": "b", "GPU_h": 0.5, "release_slot": 1, "deadline_slot": 4,
             "max_GPU_h_per_slot": 0.5}]
    scheduler = schedule_jobs_edf(jobs, [0.5] * 96)
    power = tier_GPU_h_to_IT_kWh(forecast["slot_tier_mean_GPU_h"])
    allocation = allocate_to_sites(power["slot_IT_kWh"], [1 / 12] * 12, "FIXTURE_FINAL")
    locked = [[10.0] * 96 for _ in range(12)]
    flex = [[x * 4.0 for x in site] for site in allocation["site_values"]]
    facility = facility_bridge(locked, flex, flex)
    fixture_result = run_preflight(forecast, final_scale, scheduler, power, allocation, facility, True, True)
    actual_scale = scale_fixture(False); validate_scale_bundle(actual_scale)
    actual_result = run_preflight(forecast, actual_scale, scheduler, power, allocation, facility, False, True)
    test = {
        "artifact_id": "V20D_FINAL_INTEGRATION_PREFLIGHT_TEST_V1",
        "deterministic_fixture": fixture_result,
        "current_authority_state": actual_result,
        "current_authority_expected_blockers": ["G10_PCC_interface_rating", "G12_scale_authority", "G13_locked_test_authority"],
        "MODEL_AGNOSTIC_INTEGRATION_READY": fixture_result["passed"],
        "grid_solver_calls": 0,
    }
    write("V20D_FINAL_INTEGRATION_PREFLIGHT_TEST.json", test)

    write("V20D_SCIENCE_RUN_AUTHORIZATION_TEMPLATE.json", {
        "artifact_id": "V20D_SCIENCE_RUN_AUTHORIZATION_TEMPLATE_V1",
        "status": "TEMPLATE_NOT_AUTHORIZED", "forecast_bundle_SHA": None, "site_scale_bundle_SHA": None,
        "locked_test_freeze_SHA": None, "preflight_test_SHA": None,
        "required_all_gates_PASS": [f"G{i}" for i in range(1, 15)],
        "FINAL_SCIENCE_READY": "PENDING_V19_MODEL_AUTHORITY",
        "authorization_signature": None,
    })


if __name__ == "__main__":
    main()
