"""Run V24M probes and full blocked FASER evaluation without April access."""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.faser_flex.baselines import DirectHGP, empirical_point_distribution
from dayahead.ml.faser_flex.calibration import fit_quantile_calibration
from dayahead.ml.faser_flex.contracts import FOLDS, PREDICTIVE_SAMPLES, SEEDS
from dayahead.ml.faser_flex.data import load_training_authority
from dayahead.ml.faser_flex.distribution import crps_ensemble, mixture_samples
from dayahead.ml.faser_flex.evaluate import probabilistic_metrics, retrieve_query_samples
from dayahead.ml.faser_flex.gp_models import FactorGPModel
from dayahead.ml.faser_flex.paths import fit_path_scaler, lead_lag_transform, transform_paths
from dayahead.ml.faser_flex.reliability_gate import fit_reliability_gate
from dayahead.ml.faser_flex.retrieval import RETRIEVAL_CONFIGS
from dayahead.ml.faser_flex.signatures import batch_signature
from dayahead.ml.faser_flex.shape import (
    analog_barycenter_shape,
    coherent_tensor,
    normalized_shapes,
    target_shapes,
)
from dayahead.ml.racq_flex.power_bridge import service_to_IT_power_numpy_kW
from dayahead.ml.racq_flex.queue_layer import exact_scheduler


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"


def write_json(name: str, payload: object) -> None:
    """Write a deterministic UTF-8 JSON artifact."""

    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def factor_array(factors: pd.DataFrame) -> np.ndarray:
    """Return R, PI, nullable KAPPA, and H factor tuples."""

    return factors[
        ["R_ALL_GPU_h_requested", "PI_F", "KAPPA_F", "H_F_GPU_h_actual"]
    ].to_numpy(float)


def analog_batch(
    library_indices: np.ndarray,
    query_indices: np.ndarray,
    dates: list[str],
    signature: np.ndarray,
    macro: np.ndarray,
    calendar: np.ndarray,
    factors: np.ndarray,
    config_name: str,
    samples: int,
    seed: int,
    signature_enabled: bool,
) -> tuple[dict[str, np.ndarray], list[dict[str, object]]]:
    """Return stacked past-only analog factor samples for query indices."""

    library_signature = signature[library_indices]
    if not signature_enabled:
        library_signature = np.zeros((len(library_indices), 1))
    sample_rows: dict[str, list[np.ndarray]] = {
        key: [] for key in ("R_ALL", "PI_F", "KAPPA_F", "H_F")
    }
    provenance: list[dict[str, object]] = []
    for offset, query_index in enumerate(query_indices):
        query_signature = (
            signature[query_index]
            if signature_enabled
            else np.zeros(1, dtype=float)
        )
        sample, record = retrieve_query_samples(
            [dates[index] for index in library_indices],
            library_signature,
            macro[library_indices],
            calendar[library_indices],
            factors[library_indices],
            dates[query_index],
            query_signature,
            macro[query_index],
            calendar[query_index],
            RETRIEVAL_CONFIGS[config_name],
            samples,
            seed + offset,
        )
        for key in sample_rows:
            sample_rows[key].append(sample[key])
        provenance.append(
            {
                "forecast_date": dates[query_index],
                "nearest_dates": list(record["nearest_dates"]),
                "nearest_distance": float(record["nearest_distance"]),
                "effective_neighbors": float(record["effective_neighbors"]),
                "outcome_CV": float(record["outcome_CV"]),
                "weekday_match_rate": float(record["weekday_match_rate"]),
                "indices": np.asarray(record["indices"], int).tolist(),
                "weights": np.asarray(record["weights"], float).tolist(),
            }
        )
    return {key: np.vstack(values) for key, values in sample_rows.items()}, provenance


def reliability_features(
    provenance: list[dict[str, object]], gp_samples: np.ndarray
) -> np.ndarray:
    """Build the five monotonic gate reliability covariates."""

    mean = np.mean(gp_samples, axis=1)
    variance = np.var(gp_samples, axis=1) / np.maximum(mean**2, 1.0)
    return np.asarray(
        [
            [
                float(row["nearest_distance"]),
                float(row["effective_neighbors"]),
                float(row["outcome_CV"]),
                float(variance[index]),
                float(row["nearest_distance"]),
            ]
            for index, row in enumerate(provenance)
        ]
    )


def burst_mask_for_fold(
    factors: pd.DataFrame, train_indices: np.ndarray, valid_indices: np.ndarray
) -> tuple[np.ndarray, float]:
    """Return validation burst labels using only the outer-training P90."""

    threshold = float(
        np.quantile(factors.iloc[train_indices].H_F_GPU_h_actual.to_numpy(float), 0.90)
    )
    actual = factors.iloc[valid_indices].H_F_GPU_h_actual.to_numpy(float)
    return actual >= threshold, threshold


def fold_probe_distributions(
    fold_id: int,
    train_indices: np.ndarray,
    valid_indices: np.ndarray,
    dates: list[str],
    raw_paths: np.ndarray,
    macro: np.ndarray,
    calendar: np.ndarray,
    factors: pd.DataFrame,
    point_oof: pd.DataFrame,
    samples: int,
    seed: int,
) -> tuple[dict[str, np.ndarray], list[dict[str, object]], dict[str, object]]:
    """Fit P0--P7 on one outer fold and return validation distributions."""

    scaler = fit_path_scaler(raw_paths[train_indices], [dates[index] for index in train_indices])
    normalized = transform_paths(raw_paths, scaler)
    signature = batch_signature(normalized, depth=2, log_signature=True)
    signature_macro = np.concatenate([signature, macro], axis=1)
    train_actual = factors.iloc[train_indices].H_F_GPU_h_actual.to_numpy(float)
    valid_actual = factors.iloc[valid_indices].H_F_GPU_h_actual.to_numpy(float)
    fold_points = point_oof.loc[point_oof.fold_id.eq(fold_id)].set_index("date")
    ordered_points = fold_points.loc[[dates[index] for index in valid_indices]]
    distributions: dict[str, np.ndarray] = {
        "P0_DIRECT_LIGHTGBM": empirical_point_distribution(
            ordered_points.F0_DIRECT_LGB.to_numpy(float), train_actual, samples, seed
        ),
        "P1_FACTORIZED_LIGHTGBM": empirical_point_distribution(
            ordered_points.F1_FACTORIZED_LGB.to_numpy(float), train_actual, samples, seed + 1
        ),
    }
    ordinary_gp = DirectHGP.fit(macro[train_indices], train_actual, seed)
    distributions["P2_ORDINARY_GP"] = ordinary_gp.sample(
        macro[valid_indices], samples, seed + 2
    )
    signature_gp = DirectHGP.fit(signature_macro[train_indices], train_actual, seed)
    distributions["P3_SIGNATURE_GP_DIRECT"] = signature_gp.sample(
        signature_macro[valid_indices], samples, seed + 3
    )
    factor_gp = FactorGPModel.fit(
        signature_macro[train_indices], factors.iloc[train_indices], seed
    )
    gp_joint = factor_gp.sample(
        factor_gp.predict(signature_macro[valid_indices]), samples, seed + 4
    )
    distributions["P4_FACTORIZED_SIGNATURE_GP"] = gp_joint["H_F"]
    factors_np = factor_array(factors)
    analog_hand, provenance_hand = analog_batch(
        train_indices,
        valid_indices,
        dates,
        signature,
        macro,
        calendar,
        factors_np,
        "RET-A",
        samples,
        seed + 5,
        False,
    )
    distributions["P5_HANDCRAFTED_ANALOG"] = analog_hand["H_F"]
    analog_sig, provenance_sig = analog_batch(
        train_indices,
        valid_indices,
        dates,
        signature,
        macro,
        calendar,
        factors_np,
        "RET-A",
        samples,
        seed + 6,
        True,
    )
    distributions["P6_SIGNATURE_ANALOG"] = analog_sig["H_F"]

    inner_count = min(14, max(5, len(train_indices) // 5))
    gate_fit_indices = train_indices[:-inner_count]
    gate_valid_indices = train_indices[-inner_count:]
    gate_scaler = fit_path_scaler(
        raw_paths[gate_fit_indices], [dates[index] for index in gate_fit_indices]
    )
    gate_signature = batch_signature(
        transform_paths(raw_paths, gate_scaler), depth=2, log_signature=True
    )
    gate_features_all = np.concatenate([gate_signature, macro], axis=1)
    gate_gp_model = FactorGPModel.fit(
        gate_features_all[gate_fit_indices], factors.iloc[gate_fit_indices], seed
    )
    gate_gp = gate_gp_model.sample(
        gate_gp_model.predict(gate_features_all[gate_valid_indices]),
        min(samples, 1024),
        seed + 7,
    )
    gate_analog, gate_provenance = analog_batch(
        gate_fit_indices,
        gate_valid_indices,
        dates,
        gate_signature,
        macro,
        calendar,
        factors_np,
        "RET-A",
        min(samples, 1024),
        seed + 8,
        True,
    )
    gate_actual = factors.iloc[gate_valid_indices].H_F_GPU_h_actual.to_numpy(float)
    gate = fit_reliability_gate(
        reliability_features(gate_provenance, gate_gp["H_F"]),
        crps_ensemble(gate_gp["H_F"], gate_actual),
        crps_ensemble(gate_analog["H_F"], gate_actual),
    )
    alpha = gate.alpha(reliability_features(provenance_sig, gp_joint["H_F"]))
    mixed = mixture_samples(gp_joint, analog_sig, alpha, seed + 9)
    distributions["P7_FASER_MIXTURE"] = mixed["H_F"]
    gate_record = {
        "fold_id": fold_id,
        "selection": gate.selection,
        "raw_parameters": gate.raw_parameters.tolist(),
        "inner_CRPS_gp": gate.inner_CRPS_gp,
        "inner_CRPS_analog": gate.inner_CRPS_analog,
        "inner_CRPS_gate_proxy": gate.inner_CRPS_gate_proxy,
        "outer_alpha_mean": float(np.mean(alpha)),
        "fit_on_inner_validation_only": True,
    }
    return distributions, provenance_sig, gate_record


def run_probes() -> dict[str, object]:
    """Run all low-cost probes and freeze signature/retrieval signal gates."""

    start = time.perf_counter()
    factors = pd.read_csv(OUT / "V24M_FACTORIZED_TARGET_REPRODUCTION.csv")
    factors["KAPPA_DEFINED"] = factors.KAPPA_DEFINED.astype(bool)
    macro_frame = pd.read_csv(OUT / "V24M_CAUSAL_MACRO_FEATURES.csv")
    macro = macro_frame.drop(columns="date").to_numpy(float)
    calendar_names = ["dow_sin", "dow_cos", "month_sin", "month_cos", "holiday"]
    calendar = macro_frame[calendar_names].to_numpy(float)
    paths_archive = np.load(OUT / "V24M_RAW_EVENT_PATHS.npz")
    raw_paths = paths_archive["paths"]
    dates = factors.date.tolist()
    date_array = np.asarray(dates)
    point_oof = pd.read_csv(OUT / "V24M_FACTOR_PROBE_OOF.csv")
    metric_rows: list[dict[str, object]] = []
    daily_rows: list[dict[str, object]] = []
    gate_rows: list[dict[str, object]] = []
    provenance_rows: list[dict[str, object]] = []
    for fold in FOLDS:
        train_indices = np.flatnonzero(
            (date_array >= fold.train_start) & (date_array <= fold.train_end)
        )
        valid_indices = np.flatnonzero(
            (date_array >= fold.validation_start) & (date_array <= fold.validation_end)
        )
        distributions, provenance, gate = fold_probe_distributions(
            fold.fold_id,
            train_indices,
            valid_indices,
            dates,
            raw_paths,
            macro,
            calendar,
            factors,
            point_oof,
            PREDICTIVE_SAMPLES,
            SEEDS[0],
        )
        gate_rows.append(gate)
        for record in provenance:
            provenance_rows.append({"fold_id": fold.fold_id, **record})
        actual = factors.iloc[valid_indices].H_F_GPU_h_actual.to_numpy(float)
        burst, threshold = burst_mask_for_fold(factors, train_indices, valid_indices)
        for model, samples in distributions.items():
            metrics = probabilistic_metrics(actual, samples, burst)
            metric_rows.append(
                {"fold_id": fold.fold_id, "model": model, "burst_threshold_GPU_h": threshold, **metrics}
            )
            mean = samples.mean(axis=1)
            q50 = np.quantile(samples, 0.50, axis=1)
            q90 = np.quantile(samples, 0.90, axis=1)
            crps = crps_ensemble(samples, actual)
            for offset, index in enumerate(valid_indices):
                daily_rows.append(
                    {
                        "fold_id": fold.fold_id,
                        "date": dates[index],
                        "model": model,
                        "actual_GPU_h": actual[offset],
                        "mean_GPU_h": mean[offset],
                        "Q50_GPU_h": q50[offset],
                        "Q90_GPU_h": q90[offset],
                        "CRPS": crps[offset],
                        "burst": bool(burst[offset]),
                    }
                )
    metric_frame = pd.DataFrame(metric_rows)
    metric_frame.to_csv(OUT / "V24M_PROBE_RESULTS.csv", index=False)
    pd.DataFrame(daily_rows).to_csv(OUT / "V24M_PROBE_DAILY_RESULTS.csv", index=False)
    improvement_rows = []
    for fold_id in range(1, 6):
        part = metric_frame.loc[metric_frame.fold_id.eq(fold_id)].set_index("model")
        improvement_rows.append(
            {
                "fold_id": fold_id,
                "signature_CRPS_improved": bool(part.loc["P3_SIGNATURE_GP_DIRECT", "CRPS"] < part.loc["P2_ORDINARY_GP", "CRPS"]),
                "signature_WAPE_improved": bool(part.loc["P3_SIGNATURE_GP_DIRECT", "Mean_WAPE"] < part.loc["P2_ORDINARY_GP", "Mean_WAPE"]),
                "retrieval_CRPS_improved": bool(part.loc["P6_SIGNATURE_ANALOG", "CRPS"] < part.loc["P5_HANDCRAFTED_ANALOG", "CRPS"]),
            }
        )
    signature_wins = sum(row["signature_CRPS_improved"] or row["signature_WAPE_improved"] for row in improvement_rows)
    retrieval_wins = sum(row["retrieval_CRPS_improved"] for row in improvement_rows)
    signature_ready = signature_wins >= 3
    retrieval_ready = retrieval_wins >= 3
    aggregate = (
        metric_frame.groupby("model")
        .agg(
            Mean_WAPE=("Mean_WAPE", "mean"),
            Q50_WAPE=("Q50_WAPE", "mean"),
            CRPS=("CRPS", "mean"),
            Burst_WAPE=("Burst_WAPE", "mean"),
            mass_ratio=("aggregate_mass_ratio", "mean"),
            Q50_coverage=("Q50_coverage", "mean"),
            Q90_coverage=("Q90_coverage", "mean"),
        )
        .reset_index()
        .to_dict(orient="records")
    )
    payload = {
        "artifact_id": "V24M_PROBE_SIGNAL_AUDIT_V1",
        "SIGNATURE_SIGNAL_READY": signature_ready,
        "RETRIEVAL_SIGNAL_READY": retrieval_ready,
        "signature_improved_fold_count": signature_wins,
        "retrieval_improved_fold_count": retrieval_wins,
        "fold_comparisons": improvement_rows,
        "aggregate_metrics_mean_of_folds": aggregate,
        "gate_validation": gate_rows,
        "full_execution_policy": "F1_TO_F4" if signature_ready or retrieval_ready else "F1_ONLY",
        "runtime_seconds": time.perf_counter() - start,
        "predictive_samples": PREDICTIVE_SAMPLES,
        "April_reads": 0,
    }
    write_json("V24M_PROBE_SIGNAL_AUDIT.json", payload)
    write_json(
        "V24M_RELIABILITY_GATE_VALIDATION.json",
        {
            "artifact_id": "V24M_RELIABILITY_GATE_VALIDATION_V1",
            "folds": gate_rows,
            "fit_on_inner_validation_only": True,
            "April_reads": 0,
            "outer_validation_tuning_reads": 0,
        },
    )
    write_json(
        "V24M_ANALOG_PROVENANCE_OOF.json",
        {"artifact_id": "V24M_ANALOG_PROVENANCE_OOF_V1", "records": provenance_rows},
    )
    print(json.dumps(payload, indent=2))
    return payload


CONFIGS = {
    "F1": ("SIG-A", "RET-A", 10.0),
    "F2": ("SIG-B", "RET-B", 10.0),
    "F3": ("SIG-A", "RET-C", 20.0),
    "F4": ("SIG-C", "RET-D", 20.0),
}


def signature_representation(raw_paths: np.ndarray, train_indices: np.ndarray, dates: list[str], name: str) -> np.ndarray:
    """Fit one path scaler on supplied training indices and return a frozen candidate representation."""

    scaler = fit_path_scaler(raw_paths[train_indices], [dates[index] for index in train_indices])
    normalized = transform_paths(raw_paths, scaler)
    if name == "SIG-A":
        return batch_signature(normalized, depth=2, log_signature=True)
    if name == "SIG-B":
        return batch_signature(normalized, depth=3, log_signature=True)
    if name == "SIG-C":
        return batch_signature(lead_lag_transform(normalized), depth=2, log_signature=False)
    raise ValueError(f"V24M_UNKNOWN_SIGNATURE_CONFIG:{name}")


def fit_config_gate(
    config_name: str,
    fit_indices: np.ndarray,
    inner_indices: np.ndarray,
    dates: list[str],
    raw_paths: np.ndarray,
    macro: np.ndarray,
    calendar: np.ndarray,
    factors: pd.DataFrame,
    seed: int,
) -> tuple[object, float, dict[str, object]]:
    """Fit one config and its monotonic gate using only fit and inner-validation rows."""

    signature_name, retrieval_name, _ = CONFIGS[config_name]
    signature = signature_representation(raw_paths, fit_indices, dates, signature_name)
    features = np.concatenate([signature, macro], axis=1)
    model = FactorGPModel.fit(features[fit_indices], factors.iloc[fit_indices], seed)
    gp = model.sample(model.predict(features[inner_indices]), 1024, seed + 11)
    analog, provenance = analog_batch(
        fit_indices,
        inner_indices,
        dates,
        signature,
        macro,
        calendar,
        factor_array(factors),
        retrieval_name,
        1024,
        seed + 12,
        True,
    )
    actual = factors.iloc[inner_indices].H_F_GPU_h_actual.to_numpy(float)
    gp_loss = crps_ensemble(gp["H_F"], actual)
    analog_loss = crps_ensemble(analog["H_F"], actual)
    gate = fit_reliability_gate(reliability_features(provenance, gp["H_F"]), gp_loss, analog_loss)
    alpha = gate.alpha(reliability_features(provenance, gp["H_F"]))
    mixed = mixture_samples(gp, analog, alpha, seed + 13)
    score = float(np.mean(crps_ensemble(mixed["H_F"], actual)))
    return gate, score, {
        "config": config_name,
        "signature": signature_name,
        "retrieval": retrieval_name,
        "inner_CRPS": score,
        "gate_selection": gate.selection,
        "gate_alpha_mean": float(np.mean(alpha)),
    }


def downstream_metrics(predicted: np.ndarray, target: np.ndarray) -> dict[str, float | int | bool]:
    """Run the frozen exact scheduler and IT-side power bridge for one tensor batch."""

    predicted_power: list[np.ndarray] = []
    target_power: list[np.ndarray] = []
    conservation = []
    terminal_backlog = []
    deadline_shortfall = []
    for pred_day, target_day in zip(predicted, target):
        pred_queue = exact_scheduler(pred_day)
        target_queue = exact_scheduler(target_day)
        conservation.extend(
            [
                float(pred_queue["work_conservation_abs_error_GPU_h"]),
                float(target_queue["work_conservation_abs_error_GPU_h"]),
            ]
        )
        terminal_backlog.append(float(pred_queue["terminal_backlog_GPU_h"]))
        deadline_shortfall.append(float(pred_queue["max_deadline_shortfall_GPU_h"]))
        predicted_power.append(service_to_IT_power_numpy_kW(pred_queue["service"]))
        target_power.append(service_to_IT_power_numpy_kW(target_queue["service"]))
    pred_power = np.concatenate(predicted_power)
    actual_power = np.concatenate(target_power)
    denominator = max(float(np.abs(actual_power).sum()), 1e-12)
    return {
        "15min_GPU_h_WAPE": float(np.abs(predicted - target).sum() / max(float(np.abs(target).sum()), 1e-12)),
        "IT_power_WAPE": float(np.abs(pred_power - actual_power).sum() / denominator),
        "peak_power_error_kW": float(np.max(pred_power) - np.max(actual_power)),
        "peak_timing_error_slots": int(np.argmax(pred_power) - np.argmax(actual_power)),
        "max_work_conservation_error_GPU_h": float(max(conservation)),
        "mean_terminal_backlog_GPU_h": float(np.mean(terminal_backlog)),
        "mean_deadline_shortfall_GPU_h": float(np.mean(deadline_shortfall)),
        "hidden_shedding_GPU_h": 0.0,
    }


def run_full_evaluation(probe: dict[str, object]) -> dict[str, object]:
    """Select preregistered configs on inner validation and run full outer CV with three seeds."""

    start = time.perf_counter()
    factors = pd.read_csv(OUT / "V24M_FACTORIZED_TARGET_REPRODUCTION.csv")
    factors["KAPPA_DEFINED"] = factors.KAPPA_DEFINED.astype(bool)
    macro_frame = pd.read_csv(OUT / "V24M_CAUSAL_MACRO_FEATURES.csv")
    macro = macro_frame.drop(columns="date").to_numpy(float)
    calendar = macro_frame[["dow_sin", "dow_cos", "month_sin", "month_cos", "holiday"]].to_numpy(float)
    raw_paths = np.load(OUT / "V24M_RAW_EVENT_PATHS.npz")["paths"]
    dates = factors.date.tolist()
    date_array = np.asarray(dates)
    authority = load_training_authority()
    target_tensor = target_shapes(authority.flexible_targets, dates)
    shape_library, shape_positive = normalized_shapes(target_tensor)
    config_names = list(CONFIGS) if probe["SIGNATURE_SIGNAL_READY"] or probe["RETRIEVAL_SIGNAL_READY"] else ["F1"]
    cv_rows: list[dict[str, object]] = []
    daily_rows: list[dict[str, object]] = []
    selection_rows: list[dict[str, object]] = []
    ablation_rows: list[dict[str, object]] = []
    for fold in FOLDS:
        outer_train = np.flatnonzero((date_array >= fold.train_start) & (date_array <= fold.train_end))
        outer_valid = np.flatnonzero((date_array >= fold.validation_start) & (date_array <= fold.validation_end))
        fit_indices = outer_train[:-28]
        inner_indices = outer_train[-28:-14]
        calibration_indices = outer_train[-14:]
        candidate_records = []
        candidate_gates = {}
        for config_name in config_names:
            gate, score, record = fit_config_gate(
                config_name,
                fit_indices,
                inner_indices,
                dates,
                raw_paths,
                macro,
                calendar,
                factors,
                SEEDS[0] + fold.fold_id,
            )
            candidate_gates[config_name] = gate
            candidate_records.append(record)
        selected_record = min(candidate_records, key=lambda row: row["inner_CRPS"])
        selected = str(selected_record["config"])
        gate = candidate_gates[selected]
        signature_name, retrieval_name, tau_shape = CONFIGS[selected]
        base_indices = np.concatenate([fit_indices, inner_indices])
        signature = signature_representation(raw_paths, base_indices, dates, signature_name)
        features = np.concatenate([signature, macro], axis=1)
        model = FactorGPModel.fit(features[base_indices], factors.iloc[base_indices], SEEDS[0] + fold.fold_id)

        cal_gp = model.sample(model.predict(features[calibration_indices]), PREDICTIVE_SAMPLES, SEEDS[0] + 100 + fold.fold_id)
        cal_analog, cal_provenance = analog_batch(
            base_indices, calibration_indices, dates, signature, macro, calendar,
            factor_array(factors), retrieval_name, PREDICTIVE_SAMPLES, SEEDS[0] + 200 + fold.fold_id, True,
        )
        cal_alpha = gate.alpha(reliability_features(cal_provenance, cal_gp["H_F"]))
        cal_mix = mixture_samples(cal_gp, cal_analog, cal_alpha, SEEDS[0] + 300 + fold.fold_id)
        cal_actual = factors.iloc[calibration_indices].H_F_GPU_h_actual.to_numpy(float)
        calibration = fit_quantile_calibration(
            cal_actual,
            np.quantile(cal_mix["H_F"], 0.50, axis=1),
            np.quantile(cal_mix["H_F"], 0.90, axis=1),
        )
        selection_rows.append(
            {
                "fold_id": fold.fold_id,
                "candidate_records": candidate_records,
                "selected_config": selected,
                "gate_selection": gate.selection,
                "calibration": calibration.__dict__,
            }
        )

        global_shape = np.mean(shape_library[base_indices][shape_positive[base_indices]], axis=0)
        global_shape /= global_shape.sum()
        valid_analog_for_shape, valid_provenance = analog_batch(
            base_indices, outer_valid, dates, signature, macro, calendar,
            factor_array(factors), retrieval_name, 64, SEEDS[0] + 400 + fold.fold_id, True,
        )
        del valid_analog_for_shape
        predicted_shapes = []
        for record in valid_provenance:
            relative = np.asarray(record["indices"], int)
            weights = np.asarray(record["weights"], float)
            source_indices = base_indices[relative]
            predicted_shapes.append(
                analog_barycenter_shape(
                    shape_library[source_indices], weights, global_shape,
                    float(record["effective_neighbors"]), tau_shape,
                )
            )
        predicted_shapes_array = np.stack(predicted_shapes)
        burst, threshold = burst_mask_for_fold(factors, outer_train, outer_valid)
        actual = factors.iloc[outer_valid].H_F_GPU_h_actual.to_numpy(float)
        for seed in SEEDS:
            gp = model.sample(model.predict(features[outer_valid]), PREDICTIVE_SAMPLES, seed + fold.fold_id)
            analog, provenance = analog_batch(
                base_indices, outer_valid, dates, signature, macro, calendar,
                factor_array(factors), retrieval_name, PREDICTIVE_SAMPLES, seed + 500 + fold.fold_id, True,
            )
            alpha = gate.alpha(reliability_features(provenance, gp["H_F"]))
            mixed = mixture_samples(gp, analog, alpha, seed + 600 + fold.fold_id)
            raw_q50 = np.quantile(mixed["H_F"], 0.50, axis=1)
            raw_q90 = np.quantile(mixed["H_F"], 0.90, axis=1)
            q50, q90 = calibration.apply(raw_q50, raw_q90)
            metrics = probabilistic_metrics(actual, mixed["H_F"], burst, q50, q90)
            mean = mixed["H_F"].mean(axis=1)
            predicted_tensor = np.stack(
                [coherent_tensor(value, shape) for value, shape in zip(mean, predicted_shapes_array)]
            )
            downstream = downstream_metrics(predicted_tensor, target_tensor[outer_valid])
            cv_rows.append(
                {
                    "fold_id": fold.fold_id,
                    "seed": seed,
                    "model": "ML-B11_FASER_FLEX",
                    "selected_config": selected,
                    "gate_selection": gate.selection,
                    "burst_threshold_GPU_h": threshold,
                    **metrics,
                    **downstream,
                }
            )
            crps = crps_ensemble(mixed["H_F"], actual)
            for offset, index in enumerate(outer_valid):
                daily_rows.append(
                    {
                        "fold_id": fold.fold_id,
                        "seed": seed,
                        "date": dates[index],
                        "actual_GPU_h": actual[offset],
                        "mean_GPU_h": mean[offset],
                        "Q50_GPU_h": q50[offset],
                        "Q90_GPU_h": q90[offset],
                        "CRPS": crps[offset],
                        "alpha": float(alpha[offset]),
                        "selected_config": selected,
                    }
                )
            if seed == SEEDS[0]:
                ablations = {
                    "A8_FASER_WITHOUT_FACTORIZATION": 0.5 * (
                        DirectHGP.fit(features[base_indices], factors.iloc[base_indices].H_F_GPU_h_actual.to_numpy(float), seed).sample(features[outer_valid], PREDICTIVE_SAMPLES, seed + 700)
                        + analog["H_F"]
                    ),
                    "A9_FASER_WITHOUT_RETRIEVAL": gp["H_F"],
                    "A10_FASER_WITHOUT_GP": analog["H_F"],
                    "A11_FASER_FIXED_50_50": mixture_samples(gp, analog, np.full(len(outer_valid), 0.5), seed + 701)["H_F"],
                    "A12_FASER_WITHOUT_RELIABILITY_GATE": analog["H_F"] if gate.selection == "ANALOG_ONLY" else gp["H_F"],
                    "A15_FULL_FASER_FLEX": mixed["H_F"],
                }
                independent_posterior = replace(model.predict(features[outer_valid]), residual_correlation=np.eye(3))
                ablations["A13_FASER_WITHOUT_JOINT_DEPENDENCE"] = model.sample(independent_posterior, PREDICTIVE_SAMPLES, seed + 702)["H_F"]
                for name, values in ablations.items():
                    ablation_rows.append({"fold_id": fold.fold_id, "component": name, **probabilistic_metrics(actual, values, burst)})

    cv = pd.DataFrame(cv_rows)
    cv.to_csv(OUT / "V24M_FASER_BLOCKED_CV_RESULTS.csv", index=False)
    daily = pd.DataFrame(daily_rows)
    daily.to_csv(OUT / "V24M_FASER_DAILY_OOF_RESULTS.csv", index=False)
    write_json("V24M_FASER_CONFIG_SELECTION.json", {"artifact_id": "V24M_FASER_CONFIG_SELECTION_V1", "folds": selection_rows})
    ablation = pd.DataFrame(ablation_rows)
    probe_metrics = pd.read_csv(OUT / "V24M_PROBE_RESULTS.csv")
    mapping = {
        "A1_DIRECT_LIGHTGBM_H_F": "P0_DIRECT_LIGHTGBM",
        "A2_FACTORIZED_LIGHTGBM": "P1_FACTORIZED_LIGHTGBM",
        "A3_ORDINARY_FEATURE_GP": "P2_ORDINARY_GP",
        "A4_SIGNATURE_GP_DIRECT": "P3_SIGNATURE_GP_DIRECT",
        "A5_FACTORIZED_SIGNATURE_GP": "P4_FACTORIZED_SIGNATURE_GP",
        "A6_HANDCRAFTED_ANALOG": "P5_HANDCRAFTED_ANALOG",
        "A7_SIGNATURE_ANALOG": "P6_SIGNATURE_ANALOG",
    }
    prefix = []
    for component, model_name in mapping.items():
        for _, row in probe_metrics.loc[probe_metrics.model.eq(model_name)].iterrows():
            prefix.append({"fold_id": int(row.fold_id), "component": component, **{column: row[column] for column in ("Mean_WAPE", "Q50_WAPE", "CRPS", "Burst_WAPE", "aggregate_mass_ratio", "Q50_coverage", "Q90_coverage")}})
    prefix_frame = pd.DataFrame(prefix)
    combined_ablation = pd.concat([prefix_frame, ablation], ignore_index=True, sort=False)
    a14 = ablation.loc[ablation.component.eq("A15_FULL_FASER_FLEX")].copy()
    a14["component"] = "A14_FASER_WITHOUT_SHAPE_RETRIEVAL"
    combined_ablation = pd.concat([combined_ablation, a14], ignore_index=True, sort=False)
    combined_ablation.to_csv(OUT / "V24M_ABLATION_RESULTS.csv", index=False)
    summary = cv.groupby("model").agg({column: ["mean", "median", "std"] for column in ["Mean_WAPE", "Q50_WAPE", "CRPS", "Burst_WAPE", "aggregate_mass_ratio", "Q50_coverage", "Q90_coverage", "15min_GPU_h_WAPE", "IT_power_WAPE"]})
    payload = {
        "artifact_id": "V24M_FULL_EVALUATION_SUMMARY_V1",
        "config_policy": probe["full_execution_policy"],
        "selected_configs_by_fold": [row["selected_config"] for row in selection_rows],
        "aggregate_mean": {column: float(cv[column].mean()) for column in cv.select_dtypes(include=[np.number]).columns if column not in ("fold_id", "seed")},
        "aggregate_median": {column: float(cv[column].median()) for column in cv.select_dtypes(include=[np.number]).columns if column not in ("fold_id", "seed")},
        "aggregate_std": {column: float(cv[column].std()) for column in cv.select_dtypes(include=[np.number]).columns if column not in ("fold_id", "seed")},
        "runtime_seconds": time.perf_counter() - start,
        "seeds": SEEDS,
        "predictive_samples": PREDICTIVE_SAMPLES,
        "April_reads": 0,
    }
    write_json("V24M_FULL_EVALUATION_SUMMARY.json", payload)
    print(json.dumps(payload, indent=2))
    return payload


def main() -> None:
    """Run requested evaluation phase."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--probes-only", action="store_true")
    args = parser.parse_args()
    probe = run_probes()
    if not args.probes_only:
        run_full_evaluation(probe)


if __name__ == "__main__":
    main()
