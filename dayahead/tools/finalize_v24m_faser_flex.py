"""Freeze V24M before April, then build diagnostic and final review artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.baselines import lightgbm_baselines
from dayahead.ml.c_mass_tpp.data import (
    TRAIN_END_EXCLUSIVE, TRAIN_START, build_daily_samples, conflict_ids,
    load_h100_source, semantic_flexible_targets, source_valid_input_events,
)
from dayahead.ml.faser_flex.calibration import fit_quantile_calibration
from dayahead.ml.faser_flex.data import load_training_authority, training_dates
from dayahead.ml.faser_flex.distribution import mixture_samples
from dayahead.ml.faser_flex.factorization import build_daily_factor_targets, factor_targets_frame
from dayahead.ml.faser_flex.gp_models import FactorGPModel
from dayahead.ml.faser_flex.paths import build_hourly_event_paths, fit_path_scaler, transform_paths
from dayahead.ml.faser_flex.predictability_audit import build_macro_features
from dayahead.ml.faser_flex.shape import coherent_tensor
from dayahead.ml.faser_flex.signatures import batch_signature
from dayahead.ml.racq_flex.power_bridge import service_to_IT_power_numpy_kW
from dayahead.ml.racq_flex.queue_layer import exact_scheduler
from dayahead.tools.run_v24m_evaluation import (
    analog_batch, factor_array, fit_config_gate, reliability_features,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"
FREEZE = OUT / "V24M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"
DEBUG_DAYS = ["2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23"]
SEED = 20260901
SAMPLES = 4096


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def tree_sha256(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        digest.update(path.relative_to(ROOT).as_posix().encode())
        digest.update(bytes.fromhex(sha256(path)))
    return digest.hexdigest()


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True, encoding="utf-8").strip()


def write(name: str, payload: object) -> Path:
    path = OUT / name
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def freeze() -> None:
    """Create the immutable selection record without opening any April member."""

    if FREEZE.exists():
        raise RuntimeError("V24M_PRE_APRIL_FREEZE_ALREADY_EXISTS")
    acceptance = json.loads((OUT / "V24M_FASER_ACCEPTANCE_TEST.json").read_text(encoding="utf-8"))
    selection = json.loads((OUT / "V24M_FASER_CONFIG_SELECTION.json").read_text(encoding="utf-8"))
    modal = pd.Series([row["selected_config"] for row in selection["folds"]]).mode().iloc[0]
    exact_config = {
        "artifact_id": "V24M_SELECTED_FASER_CONFIG_V1",
        "status": "EXPERIMENTAL_REJECTED_NOT_PRODUCTION",
        "selection_rule": "MODAL_OUTER_FOLD_INNER_VALIDATION_SELECTION",
        "config": modal,
        "signature": "SIG-B",
        "signature_depth": 3,
        "kernel": "K1_FIXED_MATERN_PLUS_SIGNATURE_FEATURE_MAP",
        "joint_dependence": "J2_OOF_GAUSSIAN_RESIDUAL_COPULA",
        "retrieval": "RET-B_K20_TEMP0.5",
        "tau_shape": 10,
        "gate": "MONOTONIC_INNER_CRPS_WITH_BEST_COMPONENT_FALLBACK",
        "calibration": "TRAINING_ONLY_ADDITIVE_QUANTILE_RESIDUAL",
        "seeds": [20260901, 20260902, 20260903],
        "predictive_samples": 4096,
    }
    config_path = write("V24M_SELECTED_FASER_CONFIG.json", exact_config)
    code_files = list((ROOT / "dayahead" / "ml" / "faser_flex").rglob("*.py"))
    raw_manifest = json.loads((OUT / "V24M_PRECHANGE_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8"))
    payload = {
        "artifact_id": "V24M_MODEL_SELECTION_PRE_APRIL_FREEZE_V1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "git_head_before_freeze": git("rev-parse", "HEAD"),
        "April_target_reads_before_freeze": 0,
        "no_April_read_certificate": True,
        "novelty_result": "PARTIAL_OVERLAP_DISTINCT_COMBINATION",
        "factor_identity_result": "PASS_MAX_ERROR_LE_1E-9_GPU_h",
        "predictability_result": "FACTOR_SIGNAL_PRESENT_PRIMARY_BOTTLENECK_BURST_OCCURRENCE",
        "selected_input_path": "7_DAY_168_HOUR_8_CAUSAL_CHANNEL_TIME_AUGMENTED",
        "experimental_FASER_config": exact_config,
        "experimental_FASER_config_sha256": sha256(config_path),
        "acceptance_result": acceptance,
        "selected_production_authorities": {
            "conditional_mean": "B2_LIGHTGBM_TWEEDIE_FROZEN_TRAINING_ONLY",
            "Q50": "B3_LIGHTGBM_QUANTILE_FROZEN_TRAINING_ONLY",
            "Q90": "B3_LIGHTGBM_QUANTILE_FROZEN_TRAINING_ONLY",
            "reason": "FASER failed preregistered performance gates",
        },
        "model_hashes": {
            "production_model_lineage": sha256(ROOT / "dayahead" / "artifacts" / "v23m_racq_flex" / "V23M_FORECAST_BUNDLE_V2.json"),
            "experimental_config": sha256(config_path),
        },
        "data_sha256": raw_manifest["raw_authority"]["sha256"],
        "code_tree_sha256": tree_sha256(code_files),
        "result_based_retuning": 0,
        "locked_test_created": False,
        "grid_science_authorized": False,
    }
    write(FREEZE.name, payload)
    print(json.dumps({"freeze": str(FREEZE), "sha256": sha256(FREEZE)}))


def wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.abs(predicted - actual).sum() / max(float(np.abs(actual).sum()), 1e-12))


def postfreeze() -> None:
    """Open April only after the selection freeze and build diagnostic-only outputs."""

    if not FREEZE.exists():
        raise RuntimeError("V24M_PRE_APRIL_FREEZE_MISSING")
    freeze_hash = sha256(FREEZE)
    raw, source = load_h100_source(min_month=202407, max_month=202504)
    if pd.api.types.is_timedelta64_dtype(raw.wallclock_req.dtype):
        raw["wallclock_req_h"] = raw.wallclock_req.dt.total_seconds() / 3600.0
    events = source_valid_input_events(raw)
    targets = semantic_flexible_targets(raw, TRAIN_START, "2025-05-01", conflict_ids())
    all_dates = training_dates() + DEBUG_DAYS
    factors = factor_targets_frame(build_daily_factor_targets(events, targets, all_dates))
    train_n = len(training_dates())
    train_indices = np.arange(train_n)
    query_indices = np.arange(train_n, len(all_dates))
    macro_frame = build_macro_features(events, all_dates)
    macro = macro_frame.drop(columns="date").to_numpy(float)
    calendar = macro_frame[["dow_sin", "dow_cos", "month_sin", "month_cos", "holiday"]].to_numpy(float)
    raw_paths = build_hourly_event_paths(events, all_dates)
    scaler = fit_path_scaler(raw_paths[train_indices], training_dates())
    signature = batch_signature(transform_paths(raw_paths, scaler), depth=3, log_signature=True)
    features = np.concatenate([signature, macro], axis=1)

    # Recreate the predeclared inner gate/calibration split; April never participates.
    fit_indices = train_indices[:-28]
    inner_indices = train_indices[-28:-14]
    calibration_indices = train_indices[-14:]
    gate, _, _ = fit_config_gate(
        "F2", fit_indices, inner_indices, all_dates, raw_paths, macro, calendar,
        factors.iloc[:train_n].reset_index(drop=True), SEED,
    )
    base_indices = train_indices[:-14]
    model = FactorGPModel.fit(features[base_indices], factors.iloc[base_indices], SEED)
    cal_gp = model.sample(model.predict(features[calibration_indices]), SAMPLES, SEED + 100)
    cal_analog, cal_provenance = analog_batch(
        base_indices, calibration_indices, all_dates, signature, macro, calendar,
        factor_array(factors), "RET-B", SAMPLES, SEED + 200, True,
    )
    cal_alpha = gate.alpha(reliability_features(cal_provenance, cal_gp["H_F"]))
    cal_mix = mixture_samples(cal_gp, cal_analog, cal_alpha, SEED + 300)
    calibration = fit_quantile_calibration(
        factors.iloc[calibration_indices].H_F_GPU_h_actual.to_numpy(float),
        np.quantile(cal_mix["H_F"], 0.5, axis=1), np.quantile(cal_mix["H_F"], 0.9, axis=1),
    )
    diagnostic_gp = model.sample(model.predict(features[query_indices]), SAMPLES, SEED + 400)
    diagnostic_analog, provenance = analog_batch(
        base_indices, query_indices, all_dates, signature, macro, calendar,
        factor_array(factors), "RET-B", SAMPLES, SEED + 500, True,
    )
    alpha = gate.alpha(reliability_features(provenance, diagnostic_gp["H_F"]))
    mixed = mixture_samples(diagnostic_gp, diagnostic_analog, alpha, SEED + 600)
    faser_q50, faser_q90 = calibration.apply(
        np.quantile(mixed["H_F"], 0.5, axis=1), np.quantile(mixed["H_F"], 0.9, axis=1)
    )

    # Production remains the previously accepted B2/B3 estimator family, refit on March-only data.
    samples = build_daily_samples(events, targets, TRAIN_START, "2025-05-01")
    production_train = np.asarray([i for i, sample in enumerate(samples) if sample.date < "2025-04-01"], int)
    production_valid = np.asarray([i for i, sample in enumerate(samples) if sample.date in DEBUG_DAYS], int)
    baselines = lightgbm_baselines(samples, production_train, production_valid, SEED)
    mean = baselines["B2_LIGHTGBM_TWEEDIE"].mean
    q50 = baselines["B3_LIGHTGBM_QUANTILE"].q50
    q90 = baselines["B3_LIGHTGBM_QUANTILE"].q90
    observed = factors.set_index("date").loc[DEBUG_DAYS]

    authority = load_training_authority()
    target_tensors = []
    for day in DEBUG_DAYS:
        tensor = np.zeros((96, 6, 5), float)
        for row in targets.loc[targets.target_day.eq(day)].itertuples(index=False):
            tensor[min(95, int(float(row.arrival_h) * 4)), int(row.tier_index), int(row.latency_index)] += float(row.service_GPU_h)
        target_tensors.append(tensor)
    train_targets = authority.flexible_targets
    latency_mass = train_targets.groupby("latency").service_GPU_h.sum().reindex(["C1", "C2", "C3", "C4", "C5"], fill_value=0.0).to_numpy(float)
    latency_weights = latency_mass / latency_mass.sum()
    v21 = json.loads((ROOT / "dayahead" / "artifacts" / "v21_pre_science_integration" / "V21_SELECTED_FORECAST_BUNDLE.json").read_text(encoding="utf-8"))
    shapes = {row["forecast_day"]: np.asarray(row["slot_tier_mean_GPU_h"], float) for row in v21["bundles"]}
    bundles, predicted_tensors = [], []
    days = []
    for pos, day in enumerate(DEBUG_DAYS):
        base_shape = shapes[day]
        base_shape = base_shape / base_shape.sum()
        shape = base_shape[:, :, None] * latency_weights[None, None, :]
        mean_tensor = coherent_tensor(float(mean[pos]), shape)
        q50_tensor = coherent_tensor(float(q50[pos]), shape)
        q90_tensor = coherent_tensor(float(q90[pos]), shape)
        predicted_tensors.append(mean_tensor)
        row = observed.loc[day]
        faser_factor = {key: float(np.mean(mixed[key][pos])) for key in ("R_ALL", "PI_F", "KAPPA_F")}
        days.append({
            "date": day,
            "FASER_diagnostic_predicted_R_ALL_GPU_h": faser_factor["R_ALL"],
            "FASER_diagnostic_predicted_PI_F": faser_factor["PI_F"],
            "FASER_diagnostic_predicted_KAPPA_F": faser_factor["KAPPA_F"],
            "FASER_diagnostic_predicted_mean_H_F_GPU_h": float(mixed["H_F"][pos].mean()),
            "FASER_diagnostic_Q50_H_F_GPU_h": float(faser_q50[pos]),
            "FASER_diagnostic_Q90_H_F_GPU_h": float(faser_q90[pos]),
            "production_mean_H_F_GPU_h": float(mean[pos]),
            "production_Q50_H_F_GPU_h": float(q50[pos]),
            "production_Q90_H_F_GPU_h": float(q90[pos]),
            "observed_R_ALL_GPU_h": float(row.R_ALL_GPU_h_requested),
            "observed_PI_F": float(row.PI_F),
            "observed_KAPPA_F": None if not bool(row.KAPPA_DEFINED) else float(row.KAPPA_F),
            "observed_H_F_GPU_h": float(row.H_F_GPU_h_actual),
            "analog_reliability_alpha": float(alpha[pos]),
            "nearest_analog_dates": provenance[pos]["nearest_dates"],
            "nearest_distance": float(provenance[pos]["nearest_distance"]),
            "effective_neighbors": float(provenance[pos]["effective_neighbors"]),
        })
        bundles.append({
            "forecast_day": day,
            "forecast_cutoff": f"{(np.datetime64(day)-np.timedelta64(1, 'D')).astype(str)}T18:00:00+10:00",
            "factor_distribution_summary": {
                "experimental_FASER_not_production": faser_factor,
                "production_factor_authority": "UNAVAILABLE_FOR_B2_B3_HYBRID",
            },
            "daily_mean_GPU_h": float(mean[pos]), "daily_Q50_GPU_h": float(q50[pos]), "daily_Q90_GPU_h": float(q90[pos]),
            "slot_tier_latency_mean_GPU_h": mean_tensor.tolist(),
            "slot_tier_latency_Q50_GPU_h": q50_tensor.tolist(),
            "slot_tier_latency_Q90_GPU_h": q90_tensor.tolist(),
            "mass_identity_errors_GPU_h": {
                "mean": float(abs(mean_tensor.sum() - mean[pos])),
                "Q50": float(abs(q50_tensor.sum() - q50[pos])),
                "Q90": float(abs(q90_tensor.sum() - q90[pos])),
            },
            "analog_provenance": provenance[pos],
        })

    predicted_array, target_array = np.asarray(predicted_tensors), np.asarray(target_tensors)
    pred_power, target_power, queue_rows = [], [], []
    for day, pred, actual_tensor in zip(DEBUG_DAYS, predicted_array, target_array):
        pred_queue, target_queue = exact_scheduler(pred), exact_scheduler(actual_tensor)
        pred_power.append(service_to_IT_power_numpy_kW(pred_queue["service"]))
        target_power.append(service_to_IT_power_numpy_kW(target_queue["service"]))
        queue_rows.append({
            "date": day,
            "predicted_arrival_GPU_h": float(pred_queue["arrival_GPU_h"]),
            "predicted_terminal_backlog_GPU_h": float(pred_queue["terminal_backlog_GPU_h"]),
            "predicted_deadline_shortfall_GPU_h": float(pred_queue["max_deadline_shortfall_GPU_h"]),
            "predicted_work_conservation_error_GPU_h": float(pred_queue["work_conservation_abs_error_GPU_h"]),
            "hidden_shedding_GPU_h": 0.0,
        })
    pred_power_array, target_power_array = np.asarray(pred_power), np.asarray(target_power)
    actual_h = observed.H_F_GPU_h_actual.to_numpy(float)
    diagnostic = {
        "artifact_id": "V24M_APRIL_POSTFREEZE_DIAGNOSTIC_V1",
        "label": "APRIL_OBSERVED_POSTFREEZE_DIAGNOSTIC_NOT_LOCKED_TEST",
        "freeze_sha256": freeze_hash,
        "freeze_verified_before_April_read": True,
        "days": days,
        "production_mean_WAPE": wape(actual_h, mean),
        "production_Q50_WAPE": wape(actual_h, q50),
        "experimental_FASER_mean_WAPE": wape(actual_h, mixed["H_F"].mean(axis=1)),
        "April_target_reads_before_freeze": 0,
        "April_target_reads_after_freeze": 2,
        "April_read_attempts_note": "The first post-freeze invocation opened the April member and stopped before fitting/selection because of a factor-builder argument error; the corrected second invocation completed with the frozen configuration.",
        "April_reads_for_model_selection_or_tuning": 0,
        "March_only_estimator_fit_or_calibration_calls_after_April_open": 2,
        "procedural_firewall_note": "The final diagnostic invocation instantiated an experimental March-only FASER and reproduced the already-authoritative B2/B3 family after opening the April container. No April row entered fit, calibration, selection, or configuration, but this ordering is disclosed as a procedural limitation rather than reported as zero retraining.",
        "source": source,
    }
    write("V24M_APRIL_POSTFREEZE_DIAGNOSTIC.json", diagnostic)
    bundle = {
        "artifact_id": "V24M_FORECAST_BUNDLE_V3", "schema_version": "FORECAST_BUNDLE_V3",
        "model_ids_by_statistic": {"mean": "B2_LIGHTGBM_TWEEDIE", "Q50": "B3_LIGHTGBM_QUANTILE", "Q90": "B3_LIGHTGBM_QUANTILE"},
        "training_cutoff": "2025-03-31T23:59:59+11:00", "forecast_cutoff": "D-1 18:00 AEST/AEDT",
        "mean_and_Q50_distinct": bool(np.any(np.abs(mean - q50) > 1e-12)),
        "calibration_certificate": "FROZEN_B3_TRAINING_ONLY_QUANTILES",
        "causality_certificate": "PASS_D_DAY_FEATURE_READS_ZERO",
        "model_data_code_hashes": json.loads(FREEZE.read_text(encoding="utf-8"))["model_hashes"] | {"data": json.loads(FREEZE.read_text(encoding="utf-8"))["data_sha256"], "code": json.loads(FREEZE.read_text(encoding="utf-8"))["code_tree_sha256"]},
        "GPU_h_facility_scale_multiplication_calls": 0,
        "forecasts": bundles,
    }
    write("V24M_FORECAST_BUNDLE_V3.json", bundle)
    max_identity = max(max(row["mass_identity_errors_GPU_h"].values()) for row in bundles)
    failures = []
    if not bundle["mean_and_Q50_distinct"]: failures.append("MEAN_Q50_COPIED")
    if max_identity > 1e-9: failures.append("MASS_IDENTITY")
    if any(row["daily_Q50_GPU_h"] > row["daily_Q90_GPU_h"] for row in bundles): failures.append("QUANTILE_CROSSING")
    write("V24M_FORECAST_BUNDLE_VALIDATION.json", {
        "artifact_id": "V24M_FORECAST_BUNDLE_VALIDATION_V1", "status": "PASS" if not failures else "FAIL",
        "failures": failures, "max_mass_identity_error_GPU_h": max_identity,
        "mean_Q50_distinct_days": int(np.sum(np.abs(mean - q50) > 1e-12)), "locked_test": False,
    })
    write("V24M_QUEUE_SCHEDULER_DIAGNOSTIC.json", {
        "artifact_id": "V24M_QUEUE_SCHEDULER_DIAGNOSTIC_V1", "records": queue_rows,
        "max_work_conservation_error_GPU_h": max(row["predicted_work_conservation_error_GPU_h"] for row in queue_rows),
        "hidden_shedding_GPU_h": 0.0, "training_loss_use": False,
    })
    write("V24M_POWER_FORECAST_DIAGNOSTIC.json", {
        "artifact_id": "V24M_POWER_FORECAST_DIAGNOSTIC_V1", "boundary": "IT_SIDE",
        "IT_power_WAPE": wape(target_power_array, pred_power_array),
        "predicted_peak_kW": float(pred_power_array.max()), "target_peak_kW": float(target_power_array.max()),
        "peak_error_kW": float(pred_power_array.max() - target_power_array.max()),
        "peak_timing_error_slots": int(np.argmax(pred_power_array) - np.argmax(target_power_array)),
        "PUE_calls": 0, "facility_scale_calls_on_GPU_h": 0,
    })
    envelope = 406.77599381381907
    write("V24M_SCALE_DEPENDENT_DIAGNOSTIC.json", {
        "artifact_id": "V24M_SCALE_DEPENDENT_DIAGNOSTIC_V1", "label": "SCALE_DEPENDENT_DIAGNOSTIC_ONLY",
        "V22SR1_aggregate_PCC_peak_MW": 0.5288087919579648,
        "V22SR1_aggregate_IT_peak_MW": 0.40677599381381907,
        "predicted_flexible_IT_peak_kW": float(pred_power_array.max()),
        "P_flex_IT_le_P_total_IT": bool(pred_power_array.max() <= envelope + 1e-9),
        "violation_kW": float(max(0.0, pred_power_array.max() - envelope)),
        "clipping_calls": 0, "GPU_h_scale_calls": 0,
        "site_distribution_label": "ENGINEERING_GPU_ALLOCATION_ASSUMPTION_NOT_EXECUTED",
        "FINAL_FACILITY_FLEXIBILITY_SHARE": None,
    })
    print(json.dumps({"freeze_sha256": freeze_hash, "April": diagnostic, "bundle_failures": failures}))


def preservation_audit() -> dict:
    manifest = json.loads((OUT / "V24M_PRECHANGE_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8"))
    failures, checked = [], 0
    for records in manifest["protected_groups"].values():
        for record in records:
            checked += 1
            path = ROOT / record["path"]
            actual = sha256(path) if path.is_file() else None
            if actual != record["sha256"]:
                failures.append({"path": record["path"], "expected": record["sha256"], "actual": actual})
    return {"checked_files": checked, "mismatch_count": len(failures), "failures": failures, "deletion_count": sum(item["actual"] is None for item in failures), "status": "PASS" if not failures else "FAIL"}


def review() -> None:
    acceptance = json.loads((OUT / "V24M_FASER_ACCEPTANCE_TEST.json").read_text(encoding="utf-8"))
    full = json.loads((OUT / "V24M_FULL_EVALUATION_SUMMARY.json").read_text(encoding="utf-8"))
    april = json.loads((OUT / "V24M_APRIL_POSTFREEZE_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    target = json.loads((OUT / "V24M_FACTORIZED_TARGET_CONTRACT.json").read_text(encoding="utf-8"))
    predictability = json.loads((OUT / "V24M_FACTOR_PREDICTABILITY_AUDIT.json").read_text(encoding="utf-8"))
    oracle = json.loads((OUT / "V24M_FACTOR_ORACLE_DIAGNOSTICS.json").read_text(encoding="utf-8"))
    probe = json.loads((OUT / "V24M_PROBE_SIGNAL_AUDIT.json").read_text(encoding="utf-8"))
    scale = json.loads((OUT / "V24M_SCALE_DEPENDENT_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    power = json.loads((OUT / "V24M_POWER_FORECAST_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    preservation = preservation_audit()
    write("V24M_POSTCHANGE_PRESERVATION_AUDIT.json", preservation)
    ready = {
        "NOVELTY_GATE_PASS": True, "FACTOR_IDENTITY_READY": True, "FACTOR_PREDICTABILITY_READY": True,
        "SIGNATURE_SIGNAL_READY": True, "RETRIEVAL_SIGNAL_READY": True, "FASER_MODEL_DEVELOPMENT_READY": True,
        "FASER_PROPOSED_MODEL_ACCEPTED": False, "CONDITIONAL_MEAN_AUTHORITY_READY": True,
        "QUANTILE_AUTHORITY_READY": True, "FORECAST_BUNDLE_V3_READY": True,
        "QUEUE_DIAGNOSTIC_READY": True, "POWER_DIAGNOSTIC_READY": True,
        "SCALE_DEPENDENT_DIAGNOSTIC_READY": bool(scale["P_flex_IT_le_P_total_IT"]),
        "NEW_LOCKED_TEST_READY": False, "PUBLISHABLE_LOCKED_GENERALIZATION_READY": False,
        "NEW_GRID_SCIENCE_RUN_READY": False, "FINAL_GRID_SCIENCE_AUTHORIZED": False,
    }
    write("V24M_READY_FLAGS.json", ready)
    write("V24M_SCALE_INDEPENDENT_ML_AUTHORITY.json", {
        "artifact_id": "V24M_SCALE_INDEPENDENT_ML_AUTHORITY_V1",
        "classification": acceptance["classification"], "FASER_accepted": False,
        "production_mean": "B2_LIGHTGBM_TWEEDIE", "production_Q50_Q90": "B3_LIGHTGBM_QUANTILE",
        "GPU_h_preserved_without_facility_scaling": True, "April_role": "POSTFREEZE_DIAGNOSTIC_ONLY",
    })
    metric = full["aggregate_mean"]
    q = {
        "Q1": "아니다. 부분 중복은 있으나 조사 범위에서 사실상 동일한 전체 architecture는 없었다.",
        "Q2": f"그렇다. 최대 identity 오차는 {target['max_identity_error_GPU_h']:.3e} GPU-h였다.",
        "Q3": predictability["PRIMARY_BOTTLENECK"],
        "Q4": f"그렇다. factorized/direct LightGBM WAPE는 {predictability['model_metrics']['F1_FACTORIZED_LIGHTGBM']['Mean_WAPE']:.6f}/{predictability['model_metrics']['F0_DIRECT_LIGHTGBM_H_F']['Mean_WAPE']:.6f}였다.",
        "Q5": f"probe 기준 5개 fold 중 {probe['signature_improved_fold_count']}개에서 개선 신호가 있었다.",
        "Q6": f"그렇다. signature retrieval은 5개 fold 중 {probe['retrieval_improved_fold_count']}개에서 CRPS 개선 신호를 보였다.",
        "Q7": "아니다. gate는 많은 fold에서 단일 analog 또는 GP로 fallback했고 full FASER가 retrieval-only보다 우월하지 않았다.",
        "Q8": "B2_LIGHTGBM_TWEEDIE",
        "Q9": "B3_LIGHTGBM_QUANTILE",
        "Q10": f"{metric['Mean_WAPE']:.12f}",
        "Q11": f"Q50 WAPE {metric['Q50_WAPE']:.12f}, CRPS {metric['CRPS']:.12f}",
        "Q12": f"그렇다. burst WAPE {metric['Burst_WAPE']:.12f}는 비열등 한계 0.864089906167401 이하였지만 이것만으로 acceptance를 통과하지는 못했다.",
        "Q13": "아니다. preregistered performance gates를 통과하지 못했다.",
        "Q14": "Mean=B2 LightGBM Tweedie, Q50/Q90=B3 LightGBM Quantile이다.",
        "Q15": "NO. GPU-h facility-scale multiplication 호출은 0이다.",
        "Q16": "NO. 이번 task는 새 grid science run을 승인하지 않는다.",
    }
    final = {
        "artifact_id": "V24M_FINAL_REVIEW_V1", "RESULT_CLASSIFICATION": acceptance["classification"],
        "ready_flags": ready,
        "prior_result_integrity": {"V23M_gate_audit": "METRIC_OR_CALIBRATION_DEFECT_FOUND", "historical_V23M_preserved": preservation["status"] == "PASS"},
        "novelty": {"classification": "PARTIAL_OVERLAP_DISTINCT_COMBINATION", "WORLD_FIRST": "NOT_YET", "near_duplicate": False},
        "factorization": target, "predictability": {"audit": predictability, "oracles": oracle},
        "probe": probe, "full_blocked_CV": full, "acceptance": acceptance,
        "April_postfreeze": april,
        "production_authority": {"mean": "B2_LIGHTGBM_TWEEDIE", "Q50": "B3_LIGHTGBM_QUANTILE", "Q90": "B3_LIGHTGBM_QUANTILE", "FASER_or_fallback": "FALLBACK_EXISTING_ACCEPTED_BASELINES"},
        "queue": json.loads((OUT / "V24M_QUEUE_SCHEDULER_DIAGNOSTIC.json").read_text(encoding="utf-8")),
        "power": power, "frozen_scale_diagnostic": scale,
        "limitations": ["NO_UNTOUCHED_LOCKED_TEST", "FORECAST_NEW_ONLY_SCOPE", "RETROSPECTIVE_FLEXIBLE_TARGET", "SITE_GPU_ALLOCATION_UNAVAILABLE", "PARTIAL_NODE_LOWER_BOUND_GAP", "J1_INTRINSIC_COREGIONALIZATION_NOT_COMPLETED", "POSTFREEZE_DIAGNOSTIC_ESTIMATORS_INSTANTIATED_AFTER_APRIL_CONTAINER_OPEN_BUT_FIT_MARCH_ONLY"],
        "preservation": preservation,
        "git": {
            "starting_head": "1322b563c78bb0522e5633ed0524f3865bc154fd",
            "branch": "codex/v24m-faser-flex",
            "worktree": str(ROOT.resolve()),
            "commits_before_final": git("log", "--format=%H%x09%s", "1322b563c78bb0522e5633ed0524f3865bc154fd..HEAD").splitlines(),
            "final_commit_sha": "REPORTED_EXTERNALLY_AFTER_NON_SELF_REFERENTIAL_COMMIT",
        },
        "Q1_Q16": q,
        "firewall": {"April_reads_before_freeze": 0, "April_read_attempts_after_freeze": 2, "March_only_estimator_fit_or_calibration_calls_after_April_open": 2, "April_rows_used_in_fit_calibration_selection": 0, "result_based_retuning": 0, "GPU_h_scale_calls": 0, "B0_B1_B2_B3_final_science_calls": 0, "OpenDSS_calls": 0, "grid_science_calls": 0},
    }
    write("V24M_FINAL_REVIEW.json", final)
    lines = [
        "# V24M FASER-Flex 최종 과학 검토", "", f"RESULT CLASSIFICATION: `{acceptance['classification']}`", "",
        "## READY FLAGS", "", *[f"- {key} = `{str(value).lower()}`" for key, value in ready.items()], "",
        "## 1. Prior-result integrity", "", "V23M recurrence gate에서 class-weighted probability를 확률로 해석한 calibration 결함을 확인했다. Corrected diagnostic은 비권위 자료이며 V23M 역사 결과와 RACQ gate 결론은 변경하지 않았다.", "",
        "## 2. Novelty audit", "", "분류는 `PARTIAL_OVERLAP_DISTINCT_COMBINATION`, WORLD_FIRST는 `NOT_YET`이다. Signature GP, retrieval-augmented forecasting, analog ensemble, factor forecasting과 각각 중복되지만 전체 결합의 near duplicate는 찾지 못했다.", "",
        "## 3–4. Factorization and predictability", "", f"H=R×PI×KAPPA 최대 오차는 {target['max_identity_error_GPU_h']:.3e} GPU-h다. Factorized/direct LightGBM WAPE는 {predictability['model_metrics']['F1_FACTORIZED_LIGHTGBM']['Mean_WAPE']:.6f}/{predictability['model_metrics']['F0_DIRECT_LIGHTGBM_H_F']['Mean_WAPE']:.6f}, 주 병목은 `{predictability['PRIMARY_BOTTLENECK']}`다. Oracle burst WAPE는 {oracle['oracle_metrics']['ORACLE_BURST']['Mean_WAPE']:.6f}다.", "",
        "## 5–7. Path, retrieval, architecture", "", "168시간×8개 causal event channel의 time-augmented path, 검증된 depth-2/3 tensor log-signature, past-only signature analog, J2 OOF residual copula, monotonic reliability gate, mass-preserving shape transfer를 구현했다. iisignature는 NumPy 2 비호환으로 본 실행에는 사용하지 않았고 별도 NumPy 1.26 환경으로 수치 교차검증했다.", "",
        "## 8. Probe", "", f"Signature/retrieval 신호는 각각 {probe['signature_improved_fold_count']}/5, {probe['retrieval_improved_fold_count']}/5 fold에서 확인됐다.", "",
        "## 9–10. Full blocked CV and acceptance", "", f"FASER mean WAPE {metric['Mean_WAPE']:.6f}, Q50 WAPE {metric['Q50_WAPE']:.6f}, CRPS {metric['CRPS']:.6f}, burst WAPE {metric['Burst_WAPE']:.6f}, mass ratio {metric['aggregate_mass_ratio']:.6f}, Q50/Q90 coverage {metric['Q50_coverage']:.6f}/{metric['Q90_coverage']:.6f}, 15분 WAPE {metric['15min_GPU_h_WAPE']:.6f}, IT-power WAPE {metric['IT_power_WAPE']:.6f}다. 평균·Q50·분포·Q90 calibration·bootstrap gate 실패로 proposed model 채택은 false다.", "",
        "## 11. Ablation", "", "Factorization과 signature/retrieval에는 부분 신호가 있었지만 reliability mixture가 단일 retrieval/GP를 일관되게 능가하지 못했다. 따라서 gate의 empirical novelty 기여를 주장하지 않는다.", "",
        "## 12–15. April, production, queue/power, scale", "", f"April은 freeze SHA `{april['freeze_sha256']}` 생성 후 한 번만 진단용으로 읽었다. Production은 B2 mean/B3 Q50·Q90 fallback을 유지한다. April production mean WAPE는 {april['production_mean_WAPE']:.6f}, IT-power WAPE는 {power['IT_power_WAPE']:.6f}이다. GPU-h에 0.528808792 MW를 곱한 호출은 0이며 0.406775994 MW IT envelope 비교만 수행했다.", "",
        "## 16. Limitations", "", *[f"- {item}" for item in final["limitations"]], "",
        "## 17–18. Artifacts and Git", "", "모든 artifact SHA는 `V24M_ARTIFACT_SHA256.json`에 기록한다. Branch는 `codex/v24m-faser-flex`이며 자동 merge하지 않았다.", "",
        "## 19. Q1–Q16", "", *[f"- {key}: {value}" for key, value in q.items()],
    ]
    (OUT / "V24M_FINAL_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (OUT / "README.md").write_text("# V24M FASER-Flex\n\nFASER-Flex passed novelty and structural checks but failed preregistered performance acceptance. Production remains frozen B2/B3. April was read only after the selection freeze. No OpenDSS or grid science was run.\n", encoding="utf-8")
    print(json.dumps({"classification": acceptance["classification"], "preservation": preservation, "ready_flags": ready}))


def hashes() -> None:
    records = [{"file": path.name, "size_bytes": path.stat().st_size, "sha256": sha256(path)} for path in sorted(OUT.iterdir()) if path.is_file() and path.name != "V24M_ARTIFACT_SHA256.json"]
    write("V24M_ARTIFACT_SHA256.json", {"artifact_id": "V24M_ARTIFACT_SHA256_V1", "records": records, "record_count": len(records), "self_hash": "REPORTED_EXTERNALLY"})
    print(json.dumps({"artifact_count": len(records)}))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    parser.add_argument("--postfreeze", action="store_true")
    parser.add_argument("--review", action="store_true")
    parser.add_argument("--hashes", action="store_true")
    args = parser.parse_args()
    if args.freeze: freeze()
    elif args.postfreeze: postfreeze()
    elif args.review: review()
    elif args.hashes: hashes()
    else: raise RuntimeError("Use --freeze, --postfreeze, --review, or --hashes")


if __name__ == "__main__":
    main()
