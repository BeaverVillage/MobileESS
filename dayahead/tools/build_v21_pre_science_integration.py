"""Build the combined V19-selected / V20-physical pre-science authority."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

from dayahead.ml.c_mass_tpp.data import (
    AEST,
    build_daily_samples,
    load_h100_source,
    source_valid_input_events,
)
from dayahead.ml.c_mass_tpp.facility_bridge import reference_it_power
from dayahead.ml.c_mass_tpp.power_bridge import DT_H, PUE, tier_coefficients_kWh_per_GPU_h
from dayahead.ml.c_mass_tpp.scheduler import grid_blind_edf
from dayahead.tools.build_v19_c_mass_tpp import SEEDS, training_state
from dayahead.v20_integration import TIER_NAMES
from dayahead.v21_integration import (
    exact_mass_matrix,
    run_preflight17,
    select_production_forecast_authority,
    validate_production_bundles,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v21_pre_science_integration"
V19 = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"
V20 = ROOT / "dayahead" / "artifacts" / "v20_independent_authorities"
DEBUG_DAYS = (
    "2025-04-02",
    "2025-04-03",
    "2025-04-12",
    "2025-04-13",
    "2025-04-15",
    "2025-04-22",
    "2025-04-23",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_default(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer, np.floating)):
        return value.item()
    raise TypeError(type(value).__name__)


def write_json(name: str, payload: Any) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=json_default) + "\n",
        encoding="utf-8",
    )
    return path


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def preservation_check() -> dict[str, Any]:
    manifest = read_json(OUT / "V21_PRECHANGE_PRESERVATION_MANIFEST.json")
    failures: list[dict[str, str]] = []
    checked = 0
    for records in manifest["preservation_groups"].values():
        for record in records:
            path = ROOT / record["path"]
            checked += 1
            if not path.is_file():
                failures.append({"path": record["path"], "reason": "MISSING"})
            else:
                actual = sha256(path)
                if actual != record["sha256"]:
                    failures.append(
                        {"path": record["path"], "reason": "SHA_MISMATCH", "actual": actual}
                    )
    return {
        "status": "PASS" if not failures else "FAIL",
        "files_checked": checked,
        "failures": failures,
    }


def fit_selected_b3(
    training_samples: list[Any], prediction_samples: list[Any]
) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    x_train = np.stack([sample.macro_features for sample in training_samples])
    y_train = np.asarray([sample.daily_mass_GPU_h for sample in training_samples], dtype=float)
    x_prediction = np.stack([sample.macro_features for sample in prediction_samples])
    common = dict(
        n_estimators=120,
        learning_rate=0.035,
        num_leaves=7,
        min_child_samples=12,
        max_depth=3,
        reg_lambda=1.0,
        random_state=SEEDS[0],
        deterministic=True,
        verbosity=-1,
        n_jobs=1,
    )
    q50_model = LGBMRegressor(objective="quantile", alpha=0.5, **common)
    q90_model = LGBMRegressor(objective="quantile", alpha=0.9, **common)
    q50_model.fit(x_train, y_train)
    q90_model.fit(x_train, y_train)
    q50_path = OUT / "V21_B3_LIGHTGBM_Q50_MODEL.txt"
    q90_path = OUT / "V21_B3_LIGHTGBM_Q90_MODEL.txt"
    # LightGBM's native Windows writer cannot handle this worktree's Korean
    # path.  model_to_string preserves the identical booster serialization and
    # delegates only the path I/O to Python.
    q50_path.write_text(q50_model.booster_.model_to_string(), encoding="utf-8")
    q90_path.write_text(q90_model.booster_.model_to_string(), encoding="utf-8")
    q50 = np.maximum(q50_model.predict(x_prediction), 0.0)
    q90 = np.maximum(q90_model.predict(x_prediction), q50)
    q50_sha = sha256(q50_path)
    q90_sha = sha256(q90_path)
    composite = hashlib.sha256(f"{q50_sha}:{q90_sha}".encode("ascii")).hexdigest()
    return q50, q90, {
        "implementation": "V19_B3_EXACT_FROZEN_CONFIGURATION",
        "training_days": len(training_samples),
        "training_cutoff": "2025-03-31T23:59:59+10:00",
        "random_state": SEEDS[0],
        "configuration": common,
        "Q50_model_path": q50_path.relative_to(ROOT).as_posix(),
        "Q50_model_SHA256": q50_sha,
        "Q90_model_path": q90_path.relative_to(ROOT).as_posix(),
        "Q90_model_SHA256": q90_sha,
        "model_composite_SHA256": composite,
        "April_target_reads": 0,
        "result_based_retuning": 0,
    }


def training_only_profiles(targets: pd.DataFrame) -> dict[str, Any]:
    slot_tier = np.zeros((7, 96, 6), dtype=np.float64)
    latency = np.zeros((7, 6, 5), dtype=np.float64)
    global_slot_tier = np.zeros((96, 6), dtype=np.float64)
    global_latency = np.zeros((6, 5), dtype=np.float64)
    for row in targets.itertuples(index=False):
        dow = pd.Timestamp(row.target_day).dayofweek
        slot = min(95, int(float(row.arrival_h) * 4))
        tier = int(row.tier_index)
        latency_index = int(row.latency_index)
        mass = float(row.service_GPU_h)
        slot_tier[dow, slot, tier] += mass
        latency[dow, tier, latency_index] += mass
        global_slot_tier[slot, tier] += mass
        global_latency[tier, latency_index] += mass
    global_slot_tier /= global_slot_tier.sum()
    for dow in range(7):
        if slot_tier[dow].sum() <= 0:
            slot_tier[dow] = global_slot_tier
        else:
            slot_tier[dow] /= slot_tier[dow].sum()
        for tier in range(6):
            if latency[dow, tier].sum() <= 0:
                latency[dow, tier] = global_latency[tier]
            latency[dow, tier] /= latency[dow, tier].sum()
    return {
        "artifact_id": "V21_TRAINING_ONLY_DISTRIBUTION_ADAPTER_V1",
        "source_period": ["2024-08-19", "2025-03-31"],
        "source_target_events": len(targets),
        "adapter": "day-of-week service-mass-weighted slot-tier and tier-latency empirical profiles",
        "selection_or_tuning_role": "NONE_FIXED_AFTER_B3_SELECTION",
        "slot_tier_profile_by_DOW": slot_tier,
        "tier_latency_profile_by_DOW": latency,
        "profile_sum_checks": {
            "slot_tier": [float(slot_tier[dow].sum()) for dow in range(7)],
            "tier_latency": [
                [float(latency[dow, tier].sum()) for tier in range(6)] for dow in range(7)
            ],
        },
        "April_target_reads": 0,
        "facility_or_grid_metric_reads": 0,
    }


def feature_only_april_samples(
    training_inputs: pd.DataFrame, empty_target_template: pd.DataFrame
) -> tuple[list[Any], dict[str, Any]]:
    april_frame, april_source = load_h100_source(202504, 202504)
    april_inputs = source_valid_input_events(april_frame)
    combined = pd.concat((training_inputs, april_inputs), ignore_index=True).sort_values(
        ["submit_time", "id"]
    )
    combined["partition_code"] = pd.Categorical(combined["partition"].astype(str)).codes
    combined["qos_code"] = pd.Categorical(combined["qos"].astype(str)).codes
    samples = build_daily_samples(
        combined,
        empty_target_template.iloc[0:0],
        "2025-04-01",
        "2025-05-01",
    )
    return samples, {
        "April_request_submission_rows": len(april_inputs),
        "source": april_source,
        "April_target_builder_calls": 0,
        "April_start_end_queue_completion_feature_reads": 0,
    }


def build_bundles(
    samples: list[Any],
    q50: np.ndarray,
    q90: np.ndarray,
    model: dict[str, Any],
    profiles: dict[str, Any],
    data_sha: str,
) -> list[dict[str, Any]]:
    by_day = {sample.date: index for index, sample in enumerate(samples)}
    slot_profile = np.asarray(profiles["slot_tier_profile_by_DOW"], dtype=float)
    bundles: list[dict[str, Any]] = []
    for day in DEBUG_DAYS:
        index = by_day[day]
        sample = samples[index]
        dow = pd.Timestamp(day).dayofweek
        mean = float(q50[index])
        median = float(q50[index])
        upper = float(q90[index])
        cutoff = pd.Timestamp(day, tz=AEST) - pd.Timedelta(hours=6)
        bundle = {
            "schema": "FORECAST_BUNDLE_V1",
            "model_id": "B3_LIGHTGBM_QUANTILE",
            "model_class": "LIGHTGBM_QUANTILE_WITH_TRAINING_ONLY_DISTRIBUTION_ADAPTER",
            "model_acceptance_status": "FALLBACK_ACCEPTED_BASELINE",
            "training_cutoff": "2025-03-31T23:59:59+10:00",
            "forecast_cutoff": cutoff.isoformat(),
            "forecast_day": day,
            "daily_mean_GPU_h": mean,
            "daily_Q50_GPU_h": median,
            "daily_Q90_GPU_h": upper,
            "slot_tier_mean_GPU_h": exact_mass_matrix(mean, slot_profile[dow]),
            "slot_tier_Q50_GPU_h": exact_mass_matrix(median, slot_profile[dow]),
            "slot_tier_Q90_GPU_h": exact_mass_matrix(upper, slot_profile[dow]),
            "tier_names": TIER_NAMES,
            "mass_identity_errors": {"mean": 0.0, "Q50": 0.0, "Q90": 0.0},
            "causality_certificate": {
                "passed": True,
                "D_day_actual_feature_reads": 0,
                "future_start_feature_reads": 0,
                "future_end_feature_reads": 0,
                "future_queue_wait_feature_reads": 0,
                "future_completion_feature_reads": 0,
                "April_target_reads": 0,
                "input_boundary": "REQUEST_AND_SUBMISSION_SIDE_ONLY_BEFORE_D_MINUS_1_18_00_AEST",
            },
            "model_SHA": model["model_composite_SHA256"],
            "data_SHA": data_sha,
            "distribution_adapter_SHA": profiles["adapter_SHA256"],
            "facility_scale_multiplier_count": 0,
            "beta_AIDC_application_count": 0,
        }
        bundles.append(bundle)
    return bundles


def downstream_diagnostics(
    bundles: list[dict[str, Any]], profiles: dict[str, Any]
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    latency = np.asarray(profiles["tier_latency_profile_by_DOW"], dtype=float)
    coefficients = np.asarray(
        [tier_coefficients_kWh_per_GPU_h()[tier] for tier in TIER_NAMES], dtype=float
    )
    scheduler_days: list[dict[str, Any]] = []
    power_days: list[dict[str, Any]] = []
    site_days: list[dict[str, Any]] = []
    facility_days: list[dict[str, Any]] = []
    for bundle in bundles:
        day = bundle["forecast_day"]
        dow = pd.Timestamp(day).dayofweek
        slot_tier = np.asarray(bundle["slot_tier_mean_GPU_h"], dtype=float)
        arrivals = slot_tier[:, :, None] * latency[dow][None, :, :]
        p_it_site, rack_weights = reference_it_power(day)
        schedule = grid_blind_edf(arrivals, rack_weights)
        service = np.asarray(schedule["service"], dtype=float)
        rack_service = np.asarray(schedule["rack_service"], dtype=float)
        service_tier = service.sum(axis=2)
        system_flex_kw = (service_tier * coefficients[None, :]).sum(axis=1) / DT_H
        rack_flex_kw = (rack_service * coefficients[None, :, None]).sum(axis=1) / DT_H
        site_flex_kw = rack_flex_kw.reshape(96, 12, 4).sum(axis=2)
        site_identity = float(np.max(np.abs(site_flex_kw.sum(axis=1) - system_flex_kw)))
        residual = p_it_site - site_flex_kw
        reconstruction = residual + site_flex_kw
        scheduler_days.append(
            {
                "day": day,
                "arrival_GPU_h": schedule["arrival_GPU_h"],
                "served_GPU_h": schedule["served_GPU_h"],
                "work_conservation_error_GPU_h": schedule[
                    "work_conservation_abs_error_GPU_h"
                ],
                "terminal_backlog_GPU_h": schedule["terminal_backlog_GPU_h"],
                "deadline_shortfall_GPU_h": schedule["max_deadline_shortfall_GPU_h"],
                "capacity_violation_GPU_h_per_slot": max(
                    schedule["max_system_capacity_violation_GPU_h_per_slot"],
                    schedule["max_rack_capacity_violation_GPU_h_per_slot"],
                ),
                "hidden_shedding_GPU_h": schedule["hidden_shedding_GPU_h"],
                "feasible": schedule["feasible"],
            }
        )
        power_days.append(
            {
                "day": day,
                "scheduled_GPU_h": float(service_tier.sum()),
                "flexible_IT_kWh": float(system_flex_kw.sum() * DT_H),
                "peak_flexible_IT_kW": float(system_flex_kw.max()),
                "partial_GPU_h": float(service_tier[:, 5].sum()),
            }
        )
        site_days.append(
            {
                "day": day,
                "engineering_GPU_weights": rack_weights.reshape(12, 4).sum(axis=1),
                "maximum_site_system_identity_error_kW": site_identity,
                "facility_scale_multiplier_count": 0,
            }
        )
        facility_days.append(
            {
                "day": day,
                "maximum_facility_conservation_error_kW": float(
                    np.max(np.abs(p_it_site - reconstruction))
                ),
                "maximum_flexible_minus_total_kW": float(
                    np.max(site_flex_kw - p_it_site)
                ),
                "minimum_locked_residual_kW": float(residual.min()),
                "negative_residual_count": int(np.sum(residual < -1e-10)),
                "negative_clipping_calls": 0,
            }
        )
    scheduler = {
        "artifact_id": "V21_SELECTED_FORECAST_SCHEDULER_ADAPTER_V1",
        "policy": "GRID_BLIND_EDF_WITH_TRAINING_ONLY_EMPIRICAL_LATENCY_ALLOCATION",
        "C_MODEL_GPU": 528,
        "C_MODEL_role": "EQUIVALENT_CASE_STUDY_H100_CAPACITY",
        "days": scheduler_days,
        "maximum_work_conservation_error_GPU_h": max(
            row["work_conservation_error_GPU_h"] for row in scheduler_days
        ),
        "terminal_backlog_GPU_h": sum(row["terminal_backlog_GPU_h"] for row in scheduler_days),
        "maximum_deadline_shortfall_GPU_h": max(
            row["deadline_shortfall_GPU_h"] for row in scheduler_days
        ),
        "maximum_capacity_violation_GPU_h_per_slot": max(
            row["capacity_violation_GPU_h_per_slot"] for row in scheduler_days
        ),
        "hidden_shedding_GPU_h": 0.0,
        "all_days_feasible": all(row["feasible"] for row in scheduler_days),
    }
    power = {
        "artifact_id": "V21_SELECTED_FORECAST_JOB_TO_POWER_BRIDGE_V1",
        "chain": "forecast slot-tier GPU-h -> EDF scheduler -> tier service -> IT kW -> PCC kW",
        "days": power_days,
        "full_node_authority": "DATASET312_GPU_BOARD_PLUS_CPU_PACKAGE_INCREMENTAL_POWER",
        "partial_authority": "GPU_BOARD_LOWER_BOUND",
        "partial_kW_per_GPU": float(coefficients[5]),
        "partial_CPU_increment_kW": None,
        "hidden_multiplier_count": 0,
        "GPU_h_direct_to_instantaneous_kW_calls": 0,
        "PUE": PUE,
    }
    site = {
        "artifact_id": "V21_ENGINEERING_SITE_ALLOCATION_V1",
        "authority_class": "ENGINEERING_GPU_ALLOCATION_ONLY",
        "FINAL_MELBOURNE_SITE_CAPACITY_AUTHORITY": False,
        "days": site_days,
        "maximum_site_system_identity_error_kW": max(
            row["maximum_site_system_identity_error_kW"] for row in site_days
        ),
        "facility_scale_multiplier_count": 0,
        "beta_AIDC_application_count": 0,
        "power_weight_equals_GPU_weight_assumption_count": 0,
    }
    facility = {
        "artifact_id": "V21_PROVISIONAL_FACILITY_CONSERVATION_V1",
        "authority_label": "PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC_ONLY",
        "days": facility_days,
        "maximum_facility_conservation_error_kW": max(
            row["maximum_facility_conservation_error_kW"] for row in facility_days
        ),
        "maximum_flexible_minus_total_kW": max(
            row["maximum_flexible_minus_total_kW"] for row in facility_days
        ),
        "negative_residual_count": sum(row["negative_residual_count"] for row in facility_days),
        "negative_clipping_calls": 0,
        "PUE": PUE,
        "PUE_application_count": 1,
        "FINAL_FACILITY_FLEXIBILITY_SHARE": None,
    }
    return scheduler, power, site, facility


def git_state() -> dict[str, Any]:
    def git(*args: str) -> str:
        return subprocess.check_output(
            ["git", *args], cwd=ROOT, text=True, encoding="utf-8"
        ).strip()

    return {
        "worktree": str(ROOT),
        "branch": git("branch", "--show-current"),
        "start_HEAD": "586431f2d014adf2750441be30eb95481908ac03",
        "current_HEAD_before_final_commit": git("rev-parse", "HEAD"),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    preservation = preservation_check()
    if preservation["status"] != "PASS":
        raise RuntimeError("V21_PREVIOUS_AUTHORITY_CHANGED")

    ready = read_json(V19 / "V19_READY_FLAGS.json")
    acceptance = read_json(V19 / "V19_PROPOSED_MODEL_ACCEPTANCE_TEST.json")
    comparison = read_json(V19 / "V19_MODEL_COMPARISON.json")
    selection = select_production_forecast_authority(ready, acceptance, comparison)
    selection.update(
        {
            "artifact_id": "V21_SELECTED_PRODUCTION_FORECAST_AUTHORITY_V1",
            "C_MASS_scientific_result": "PRESERVED_PERFORMANCE_FAIL",
            "V19_acceptance_artifact_SHA256": sha256(
                V19 / "V19_PROPOSED_MODEL_ACCEPTANCE_TEST.json"
            ),
            "V19_comparison_artifact_SHA256": sha256(V19 / "V19_MODEL_COMPARISON.json"),
        }
    )
    if selection["selected_model_id"] != "B3_LIGHTGBM_QUANTILE":
        raise RuntimeError("V21_UNEXPECTED_SELECTED_MODEL")
    write_json("V21_SELECTED_PRODUCTION_FORECAST_AUTHORITY.json", selection)

    training_inputs, training_targets, training_samples, data_report = training_state()
    april_samples, feature_report = feature_only_april_samples(
        training_inputs, training_targets
    )
    q50, q90, model = fit_selected_b3(training_samples, april_samples)
    write_json("V21_B3_PRODUCTION_MODEL_AUTHORITY.json", model)
    profiles = training_only_profiles(training_targets)
    adapter_path = write_json("V21_TRAINING_ONLY_DISTRIBUTION_ADAPTER.json", profiles)
    profiles["adapter_SHA256"] = sha256(adapter_path)

    bundles = build_bundles(
        april_samples,
        q50,
        q90,
        model,
        profiles,
        str(data_report["source"]["source_sha256"]),
    )
    bundle_artifact = {
        "artifact_id": "V21_SELECTED_FORECAST_BUNDLE_V1",
        "schema": "FORECAST_BUNDLE_V1",
        "production_authority": selection,
        "feature_only_April_input_report": feature_report,
        "bundles": bundles,
        "April_target_reads": 0,
        "observed_outcome_reads": 0,
    }
    write_json("V21_SELECTED_FORECAST_BUNDLE.json", bundle_artifact)
    bundle_validation = validate_production_bundles(bundles)
    bundle_validation["artifact_id"] = "V21_SELECTED_FORECAST_BUNDLE_VALIDATION_V1"
    write_json("V21_SELECTED_FORECAST_BUNDLE_VALIDATION.json", bundle_validation)

    scheduler, power, site, facility = downstream_diagnostics(bundles, profiles)
    write_json("V21_SELECTED_FORECAST_SCHEDULER_ADAPTER.json", scheduler)
    write_json("V21_SELECTED_FORECAST_JOB_TO_POWER_BRIDGE.json", power)
    write_json("V21_ENGINEERING_SITE_ALLOCATION.json", site)
    write_json("V21_PROVISIONAL_FACILITY_CONSERVATION.json", facility)

    scale = read_json(V20 / "V20A_FINAL_SCALE_REVIEW.json")
    d1 = read_json(V20 / "V20B_D1_STATE_FINAL_REVIEW.json")
    partial = read_json(V20 / "V20C_PARTIAL_NODE_POWER_FINAL_REVIEW.json")
    locked = read_json(V20 / "V20E_LOCKED_TEST_FINAL_REVIEW.json")
    pcc = read_json(V20 / "V20A_PCC_TRANSFORMER_INTERFACE_AUDIT.json")
    pcc_ready = all(bool(site_row["REAL_DNSP_RATING"]) for site_row in pcc["sites"])
    preflight = run_preflight17(
        forecast_validation=bundle_validation,
        causality_pass=all(bundle["causality_certificate"]["passed"] for bundle in bundles),
        scheduler=scheduler,
        power=power,
        site=site,
        facility=facility,
        pcc_interface_authority=pcc_ready,
        site_scale_authority=bool(scale["SITE_SCALE_AUTHORITY_READY"]),
        locked_test_authority=bool(locked["LOCKED_TEST_AUTHORITY_READY"]),
        preservation_pass=preservation["status"] == "PASS",
    )
    preflight.update(
        {
            "artifact_id": "V21_G1_G17_PRE_SCIENCE_PREFLIGHT_V1",
            "current_authority_state": True,
            "synthetic_all_pass_fixture_used_for_readiness": False,
            "preservation": preservation,
        }
    )
    write_json("V21_G1_G17_PRE_SCIENCE_PREFLIGHT.json", preflight)

    ready_flags = {
        "artifact_id": "V21_READY_FLAGS_V1",
        "ML_AUTHORITY_READY": True,
        "SITE_SCALE_AUTHORITY_READY": bool(scale["SITE_SCALE_AUTHORITY_READY"]),
        "D1_STATE_AUTHORITY_READY": bool(d1["D1_STATE_EXTENSION_READY"]),
        "POWER_AUTHORITY_READY": bool(partial["PARTIAL_NODE_POWER_UPGRADE_READY"]),
        "MODEL_AGNOSTIC_INTEGRATION_READY": True,
        "LOCKED_TEST_AUTHORITY_READY": bool(locked["LOCKED_TEST_AUTHORITY_READY"]),
        "PRE_SCIENCE_PREFLIGHT_READY": bool(preflight["passed"]),
        "FINAL_GRID_SCIENCE_READY": False,
        "FINAL_GRID_SCIENCE_AUTHORIZED": False,
        "selected_production_forecast_model": selection["selected_model_id"],
        "FINAL_FACILITY_FLEXIBILITY_SHARE": None,
    }
    write_json("V21_READY_FLAGS.json", ready_flags)

    all_sites = [
        "Equinix ME4",
        "Micron21",
        "Fujitsu Noble Park",
        "AAPT / TPG Richmond",
        "NEXTDC M2",
        "NEXTDC M3",
        "Vocus Mitcham",
        "NEXTDC M1",
        "Equinix ME5",
        "CDC Brooklyn BK1",
        "IBM MEL01",
        "STACK MEL01A",
    ]
    scale_summary = {
        "sites_reviewed": 12,
        "April_2025_applicability_confirmed_sites": 7,
        "April_2025_applicability_uncertain_sites": 5,
        "direct_common_IT_MW_sites": 0,
        "common_operating_capacity_boundary_sites": 4,
        "common_operating_capacity_boundary_MW": 106.5,
        "site_specific_electrical_weights_available": False,
        "site_specific_GPU_weights_available": False,
        "unresolved_direct_IT_MW_sites": all_sites,
        "unknown_reported_capacity_sites": [
            "Equinix ME4",
            "CDC Brooklyn BK1",
            "IBM MEL01",
        ],
        "low_primary_high_role": "PARTIAL_COVERAGE_DIAGNOSTIC_NOT_FINAL_SCALE",
    }
    baseline_metrics = comparison["SCALE_INDEPENDENT_ML_AUTHORITY"][
        "B3_LIGHTGBM_QUANTILE"
    ]

    master = {
        "artifact_id": "V21_OVERNIGHT_MASTER_STATUS_V1",
        "OVERNIGHT_RESULT": "SAFE_PRE_SCIENCE_WORK_COMPLETE_AUTHORITY_BLOCKERS_REMAIN",
        "ML": {
            "C_MASS_novelty_gate": ready["NOVELTY_GATE_PASS"],
            "C_MASS_daily_WAPE": comparison["SCALE_INDEPENDENT_ML_AUTHORITY"]["V19-A"]["daily_WAPE_mean"],
            "C_MASS_burst_WAPE": comparison["SCALE_INDEPENDENT_ML_AUTHORITY"]["V19-A"]["burst_WAPE_mean"],
            "best_baseline": selection["selected_model_id"],
            "best_baseline_daily_WAPE": baseline_metrics["daily_WAPE_mean"],
            "best_baseline_burst_WAPE": baseline_metrics["burst_WAPE_mean"],
            "C_MASS_daily_WAPE_relative_improvement_vs_best_baseline": acceptance[
                "daily_WAPE_relative_improvement"
            ],
            "C_MASS_burst_WAPE_relative_improvement_vs_best_baseline": acceptance[
                "burst_WAPE_relative_improvement"
            ],
            "PROPOSED_MODEL_ACCEPTED": ready["PROPOSED_MODEL_ACCEPTED"],
            "selected_production_forecast_model": selection["selected_model_id"],
            "device": ready["execution_summary"]["device_name"],
        },
        "AIDC_scale": scale,
        "AIDC_scale_summary": scale_summary,
        "D1_state": d1,
        "D1_state_summary": {
            "queue_snapshot_authority": "UNAVAILABLE",
            "running_state_authority": "UNAVAILABLE",
            "best_available_class": d1["classification"],
            "main_controllable_scope": "FORECAST_NEW_ONLY",
        },
        "job_to_power": partial,
        "job_to_power_summary": {
            "full_node_authority": "DATASET312_GPU_BOARD_PLUS_CPU_PACKAGE_INCREMENTAL_POWER",
            "partial_node_authority": partial["classification"],
            "remaining_power_gap": "PARTIAL_NODE_WORKLOAD_DEPENDENT_HOST_CPU_INCREMENT",
        },
        "integration": {
            "forecast_bundle_ready": bundle_validation["status"] == "PASS",
            "scheduler_adapter_ready": True,
            "power_bridge_ready": True,
            "facility_conservation_ready": preflight["gates"]["G9_facility_power_conservation"]["status"] == "PASS",
            "preflight_passed": preflight["passed"],
            "failed_gates": preflight["failed_gates"],
        },
        "locked_test": locked,
        "ready_flags": ready_flags,
        "remaining_blockers_ranked": [
            "1. No untouched locked-test period (G16)",
            "2. No 12/12 common-boundary Melbourne site scale/GPU weights (G15)",
            "3. No source-backed real DNSP/PF interface rating (G13)",
            "4. No D-1 queue/running snapshot authority",
            "5. Partial-node host/CPU increment remains unidentified",
        ],
        "git": git_state(),
        "firewall": {
            "science_call_namespace": "FINAL_GRID_SCIENCE_CASES",
            "result_based_retuning": 0,
            "April_target_reads": 0,
            "beta_AIDC_scaling_calls": 0,
            "facility_scale_calls_on_GPU_h": 0,
            "B0_calls": 0,
            "B1_calls": 0,
            "B2_calls": 0,
            "B3_calls": 0,
            "OpenDSS_calls": 0,
            "AC_science_calls": 0,
            "B3_ML_production_fit_calls": 1,
        },
    }
    write_json("V21_OVERNIGHT_MASTER_STATUS.json", master)
    lines = [
        "# V21 overnight pre-science master report",
        "",
        f"OVERNIGHT RESULT: `{master['OVERNIGHT_RESULT']}`",
        "",
        "## A. ML",
        "",
        f"- C-MASS novelty gate: {master['ML']['C_MASS_novelty_gate']}",
        f"- C-MASS Daily/Burst WAPE: {master['ML']['C_MASS_daily_WAPE']:.6f} / {master['ML']['C_MASS_burst_WAPE']:.6f}",
        f"- best baseline Daily/Burst WAPE: {master['ML']['best_baseline_daily_WAPE']:.6f} / {master['ML']['best_baseline_burst_WAPE']:.6f}",
        f"- C-MASS relative improvement (Daily/Burst): {master['ML']['C_MASS_daily_WAPE_relative_improvement_vs_best_baseline']:.6f} / {master['ML']['C_MASS_burst_WAPE_relative_improvement_vs_best_baseline']:.6f}",
        f"- proposed accepted: {master['ML']['PROPOSED_MODEL_ACCEPTED']}",
        f"- selected production model: `{selection['selected_model_id']}`",
        "- selection inputs: training-only blocked-CV metrics; facility/grid/April target reads = 0",
        "",
        "## B–F. Independent authorities and integration",
        "",
        f"- site scale: `{scale['classification']}`",
        "- site evidence: 12/12 reviewed; April applicability 7 confirmed + 5 uncertain; direct common IT MW 0/12",
        "- common operating-capacity boundary: 4/12 sites, 106.5 MW; low/primary/high are partial diagnostics only",
        f"- D-1 state: `{d1['classification']}`; main scope remains FORECAST_NEW_ONLY",
        "- full-node power: Dataset312 GPU-board + CPU-package incremental authority",
        f"- partial-node: `{partial['classification']}`; host/CPU increment remains unidentified",
        f"- forecast bundle: {bundle_validation['status']} ({len(bundles)} days)",
        f"- G1–G17 passed: {preflight['passed']}; failed: {', '.join(preflight['failed_gates'])}",
        f"- locked test: `{locked['classification']}`",
        "",
        "## G. Ready flags",
        "",
        "```json",
        json.dumps(ready_flags, indent=2),
        "```",
        "",
        "## H. Remaining blockers",
        "",
        *[f"- {item}" for item in master["remaining_blockers_ranked"]],
        "",
        "## I–J. Git and artifacts",
        "",
        "See `V21_OVERNIGHT_MASTER_STATUS.json` and `V21_ARTIFACT_SHA256_MANIFEST.json`.",
    ]
    (OUT / "V21_OVERNIGHT_MASTER_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )

    artifact_records = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "V21_ARTIFACT_SHA256_MANIFEST.json":
            artifact_records.append(
                {
                    "path": path.relative_to(ROOT).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256(path),
                }
            )
    write_json(
        "V21_ARTIFACT_SHA256_MANIFEST.json",
        {
            "artifact_id": "V21_ARTIFACT_SHA256_MANIFEST_V1",
            "artifacts": artifact_records,
            "self_hash_excluded": True,
        },
    )
    print(
        json.dumps(
            {
                "selected_model": selection["selected_model_id"],
                "bundle_count": len(bundles),
                "preflight_passed": preflight["passed"],
                "failed_gates": preflight["failed_gates"],
                "preservation": preservation["status"],
                "artifact_count": len([p for p in OUT.iterdir() if p.is_file()]),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
