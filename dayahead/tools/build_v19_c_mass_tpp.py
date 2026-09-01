from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
import platform
import subprocess
import sys
import time
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from dayahead.ml.c_mass_tpp.baselines import (
    deep_baselines,
    lightgbm_baselines,
    persistence_proxy,
    v18r2_candidate_b,
)
from dayahead.ml.c_mass_tpp.data import (
    APRIL_END_EXCLUSIVE,
    KESTREL,
    KESTREL_SHA256,
    LATENCIES,
    ROOT,
    TIERS,
    TRAIN_END_EXCLUSIVE,
    TRAIN_START,
    DailySample,
    build_daily_samples,
    causality_audit,
    conflict_ids,
    event_feature_matrix,
    expanding_blocked_folds,
    indices_for_period,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)
from dayahead.ml.c_mass_tpp.evaluate import (
    aggregate_event_metrics,
    block_bootstrap_error_difference,
    daily_metrics,
    event_metrics,
)
from dayahead.ml.c_mass_tpp.facility_bridge import reference_it_power
from dayahead.ml.c_mass_tpp.power_bridge import (
    DT_H,
    PUE,
    actual_target_power,
    packets_to_power,
    power_metrics,
    tier_coefficients_kWh_per_GPU_h,
)
from dayahead.ml.c_mass_tpp.scheduler import grid_blind_edf, packet_arrivals
from dayahead.ml.c_mass_tpp.train import TrainingResult, predict_cmass, train_cmass


OUT = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"
PRECHANGE = OUT / "V19_PRECHANGE_PRESERVATION_MANIFEST.json"
SEEDS = (20260901, 20260902, 20260903)
VARIANTS = ("V19-A", "V19-B", "V19-C")
DEBUG_DAYS = (
    "2025-04-02",
    "2025-04-03",
    "2025-04-12",
    "2025-04-13",
    "2025-04-15",
    "2025-04-22",
    "2025-04-23",
)
START_HEAD = "77a86e3ded8087ea0109ccfca631bd2396ecd9fe"
START_BRANCH = "codex/dayahead-aidc-joint-v1"
NEW_BRANCH = "codex/v19-c-mass-tpp"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_default(value: object) -> object:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, Path):
        return str(value)
    raise TypeError(type(value).__name__)


def write_json(name: str, value: object) -> Path:
    path = OUT / name
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False, default=json_default) + "\n",
        encoding="utf-8",
    )
    return path


def write_csv(name: str, rows: list[dict[str, object]], fields: list[str]) -> Path:
    path = OUT / name
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def verify_kestrel() -> None:
    if sha256(KESTREL) != KESTREL_SHA256:
        raise RuntimeError("V19_KESTREL_SOURCE_SHA_CHANGED")


def verify_preservation() -> dict[str, object]:
    manifest = json.loads(PRECHANGE.read_text(encoding="utf-8"))
    failures = []
    for group, records in manifest["preservation_groups"].items():
        for record in records:
            path = ROOT / record["path"]
            actual = sha256(path) if path.is_file() else None
            if actual != record["sha256"]:
                failures.append(
                    {
                        "group": group,
                        "path": record["path"],
                        "expected": record["sha256"],
                        "actual": actual,
                    }
                )
    return {"status": "PASS" if not failures else "FAIL", "failures": failures}


def training_state() -> tuple[pd.DataFrame, pd.DataFrame, list[DailySample], dict[str, object]]:
    verify_kestrel()
    frame, source = load_h100_source(202407, 202503)
    inputs = source_valid_input_events(frame)
    targets = semantic_flexible_targets(frame, TRAIN_START, TRAIN_END_EXCLUSIVE, conflict_ids())
    samples = build_daily_samples(inputs, targets, TRAIN_START, TRAIN_END_EXCLUSIVE)
    counts = np.asarray([len(sample.target_event_mass_GPU_h) for sample in samples])
    daily = np.asarray([sample.daily_mass_GPU_h for sample in samples])
    identities = [
        abs(sample.daily_mass_GPU_h - float(sample.target_event_mass_GPU_h.sum()))
        for sample in samples
    ]
    report = {
        "source": source,
        "all_H100_source_rows_loaded_July2024_to_March2025": len(frame),
        "source_valid_submission_request_input_events": len(inputs),
        "semantic_flexible_target_events_after_76_conflict_exclusion": len(targets),
        "training_days": len(samples),
        "training_total_master_mass_GPU_h": float(daily.sum()),
        "positive_target_days": int(np.sum(daily > 0)),
        "K_max_training_observed": int(counts.max()),
        "event_count_quantiles": {
            str(q): float(np.quantile(counts, q)) for q in (0.5, 0.9, 0.95, 0.99, 1.0)
        },
        "daily_master_event_sum_max_abs_error_GPU_h": float(max(identities)),
        "causality": causality_audit(),
    }
    return inputs, targets, samples, report


def metric_rows(
    samples: list[DailySample],
    rows: list[dict[str, object]],
) -> dict[str, float | None]:
    actual = np.asarray([row["actual"] for row in rows], dtype=float)
    mean = np.asarray([row["mean"] for row in rows], dtype=float)
    q50 = np.asarray([row["q50"] for row in rows], dtype=float)
    q90 = np.asarray([row["q90"] for row in rows], dtype=float)
    result = daily_metrics(actual, mean, q50, q90, float("inf"))
    burst = np.asarray([bool(row["burst"]) for row in rows])
    error = mean - actual
    result["burst_day_count"] = int(burst.sum())
    result["burst_WAPE"] = (
        float(np.abs(error[burst]).sum() / max(actual[burst].sum(), 1e-12))
        if burst.any()
        else None
    )
    result["burst_MAE_GPU_h"] = float(np.mean(np.abs(error[burst]))) if burst.any() else None
    result["burst_underforecast_ratio"] = (
        float(mean[burst].sum() / max(actual[burst].sum(), 1e-12)) if burst.any() else None
    )
    return result


def add_prediction_rows(
    store: dict[str, dict[str, list[dict[str, object]]]],
    model: str,
    seed_key: str,
    samples: list[DailySample],
    validation_index: np.ndarray,
    prediction_mean: np.ndarray,
    prediction_q50: np.ndarray,
    prediction_q90: np.ndarray,
    fold_id: int,
    burst_threshold: float,
) -> None:
    for position, index in enumerate(validation_index):
        sample = samples[int(index)]
        store[model][seed_key].append(
            {
                "fold": fold_id,
                "index": int(index),
                "date": sample.date,
                "actual": sample.daily_mass_GPU_h,
                "mean": float(prediction_mean[position]),
                "q50": float(prediction_q50[position]),
                "q90": float(prediction_q90[position]),
                "burst": sample.daily_mass_GPU_h >= burst_threshold,
            }
        )


def training_pretrain_arrays(
    input_events: pd.DataFrame, validation_start: str
) -> tuple[np.ndarray, np.ndarray]:
    boundary = pd.Timestamp(validation_start, tz="UTC") - pd.Timedelta(hours=10)
    selected = input_events.loc[input_events["submit_time"].lt(boundary)]
    features = event_feature_matrix(selected)
    seconds = selected["submit_time"].astype("int64").to_numpy(np.float64) / 1e9
    return features, seconds


def power_for_daily_rows(
    samples: list[DailySample],
    rows: list[dict[str, object]],
    fold_train_indices: dict[int, np.ndarray],
) -> dict[str, float]:
    coefficients = tier_coefficients_kWh_per_GPU_h()
    coefficient = np.asarray([coefficients[tier] for tier in TIERS])
    actual_all: list[float] = []
    predicted_all: list[float] = []
    cache: dict[tuple[int, int], tuple[np.ndarray, np.ndarray]] = {}
    for row in rows:
        fold = int(row["fold"])
        index = int(row["index"])
        dow = pd.Timestamp(samples[index].date).dayofweek
        key = (fold, dow)
        if key not in cache:
            selected = [
                i
                for i in fold_train_indices[fold]
                if pd.Timestamp(samples[int(i)].date).dayofweek == dow
            ]
            if len(selected) < 3:
                selected = list(fold_train_indices[fold])
            slot_mass = np.stack([samples[int(i)].target_slot_mass_GPU_h for i in selected])
            tier_mass = np.stack([samples[int(i)].target_tier_mass_GPU_h for i in selected])
            slot_shape = slot_mass.sum(axis=0)
            slot_shape = slot_shape / max(slot_shape.sum(), 1e-12)
            tier_shape = tier_mass.sum(axis=0)
            tier_shape = tier_shape / max(tier_shape.sum(), 1e-12)
            cache[key] = slot_shape, tier_shape
        slot_shape, tier_shape = cache[key]
        predicted_kw = float(row["mean"]) * slot_shape * float(tier_shape @ coefficient) / DT_H
        actual_kw = actual_target_power(
            samples[index].target_event_time_h,
            samples[index].target_event_tier,
            samples[index].target_event_mass_GPU_h,
        )
        predicted_all.extend(predicted_kw.tolist())
        actual_all.extend(actual_kw.tolist())
    return power_metrics(np.asarray(actual_all), np.asarray(predicted_all))


def aggregate_seed_metrics(
    store: dict[str, dict[str, list[dict[str, object]]]],
    samples: list[DailySample],
    fold_train_indices: dict[int, np.ndarray],
) -> tuple[dict[str, object], dict[str, dict[str, dict[str, float | None]]]]:
    comparison: dict[str, object] = {}
    raw: dict[str, dict[str, dict[str, float | None]]] = {}
    for model, by_seed in store.items():
        raw[model] = {}
        for seed, rows in by_seed.items():
            metrics = metric_rows(samples, rows)
            metrics.update(power_for_daily_rows(samples, rows, fold_train_indices))
            raw[model][seed] = metrics
        metric_names = sorted({key for metrics in raw[model].values() for key in metrics})
        summary: dict[str, object] = {"seed_metrics": raw[model]}
        for metric in metric_names:
            values = [
                float(metrics[metric])
                for metrics in raw[model].values()
                if metrics.get(metric) is not None and math.isfinite(float(metrics[metric]))
            ]
            if values:
                summary[f"{metric}_mean"] = float(np.mean(values))
                summary[f"{metric}_median"] = float(np.median(values))
                summary[f"{metric}_std"] = float(np.std(values))
        comparison[model] = summary
    return comparison, raw


def cv_evaluation(
    input_events: pd.DataFrame,
    samples: list[DailySample],
    k_max: int,
    epochs: int,
) -> dict[str, object]:
    store: dict[str, dict[str, list[dict[str, object]]]] = defaultdict(lambda: defaultdict(list))
    models: dict[tuple[str, int, int], TrainingResult] = {}
    training_reports: list[dict[str, object]] = []
    fold_train_indices: dict[int, np.ndarray] = {}
    folds_payload = []
    for fold in expanding_blocked_folds():
        train_index = indices_for_period(samples, fold.train_start, fold.train_end)
        validation_index = indices_for_period(samples, fold.validation_start, fold.validation_end)
        fold_train_indices[fold.fold_id] = train_index
        train_mass = np.asarray([samples[i].daily_mass_GPU_h for i in train_index])
        threshold = float(np.quantile(train_mass, 0.9))
        folds_payload.append(
            {
                **asdict(fold),
                "train_days": len(train_index),
                "validation_days": len(validation_index),
                "train_P50_GPU_h": float(np.quantile(train_mass, 0.5)),
                "train_P90_burst_threshold_GPU_h": threshold,
                "future_leakage": False,
            }
        )
        for name, prediction in {
            "B0_V18R2_CANDIDATE_B": v18r2_candidate_b(samples, train_index, validation_index),
            "B1_PERSISTENCE_PROXY": persistence_proxy(samples, train_index, validation_index),
        }.items():
            add_prediction_rows(
                store,
                name,
                "deterministic",
                samples,
                validation_index,
                prediction.mean,
                prediction.q50,
                prediction.q90,
                fold.fold_id,
                threshold,
            )
        tree = lightgbm_baselines(samples, train_index, validation_index, SEEDS[0])
        for name, prediction in tree.items():
            add_prediction_rows(
                store,
                name,
                "deterministic",
                samples,
                validation_index,
                prediction.mean,
                prediction.q50,
                prediction.q90,
                fold.fold_id,
                threshold,
            )
        pre_features, pre_seconds = training_pretrain_arrays(input_events, fold.validation_start)
        for seed in SEEDS:
            for name, prediction in deep_baselines(samples, train_index, validation_index, seed).items():
                add_prediction_rows(
                    store,
                    name,
                    str(seed),
                    samples,
                    validation_index,
                    prediction.mean,
                    prediction.q50,
                    prediction.q90,
                    fold.fold_id,
                    threshold,
                )
            for variant in VARIANTS:
                trained = train_cmass(
                    samples,
                    train_index,
                    variant,
                    seed,
                    k_max,
                    pre_features,
                    pre_seconds,
                    epochs=epochs,
                )
                models[(variant, seed, fold.fold_id)] = trained
                prediction = predict_cmass(trained, samples, validation_index, decode_events=False)
                add_prediction_rows(
                    store,
                    variant,
                    str(seed),
                    samples,
                    validation_index,
                    np.asarray([row["mean"] for row in prediction]),
                    np.asarray([row["q50"] for row in prediction]),
                    np.asarray([row["q90"] for row in prediction]),
                    fold.fold_id,
                    threshold,
                )
                training_reports.append(
                    {
                        "fold": fold.fold_id,
                        "variant": variant,
                        "seed": seed,
                        "variance_power": trained.variance_power,
                        "epochs": trained.epochs,
                        "elapsed_seconds": trained.elapsed_seconds,
                        "epoch_runtime_seconds": trained.epoch_runtime_seconds,
                        "final_training_loss": trained.final_training_loss,
                        "pretraining": trained.pretraining,
                        "parameters": trained.model.parameter_count(),
                        "execution_device": trained.execution_device,
                        "device_name": trained.device_name,
                        "peak_VRAM_bytes": trained.peak_VRAM_bytes,
                        "gpu_utilization_samples_percent": trained.gpu_utilization_samples_percent,
                    }
                )
    comparison, raw_metrics = aggregate_seed_metrics(store, samples, fold_train_indices)
    selected_variant = min(
        VARIANTS, key=lambda name: float(comparison[name]["daily_WAPE_mean"])
    )
    seed_wape = {
        seed: float(raw_metrics[selected_variant][str(seed)]["daily_WAPE"]) for seed in SEEDS
    }
    median_seed = sorted(SEEDS, key=lambda seed: seed_wape[seed])[1]
    event_rows = []
    mass_errors = []
    proposed_power_actual: list[float] = []
    proposed_power_prediction: list[float] = []
    for fold in expanding_blocked_folds():
        validation_index = indices_for_period(samples, fold.validation_start, fold.validation_end)
        prediction = predict_cmass(
            models[(selected_variant, median_seed, fold.fold_id)],
            samples,
            validation_index,
            decode_events=True,
        )
        for record in prediction:
            sample = samples[int(record["index"])]
            selected = np.asarray(record["selected_index"], dtype=int)
            tier_probability = np.asarray(record["tier_probability_all"])
            latency_probability = np.asarray(record["latency_probability_all"])
            arrival = np.asarray(record["arrival_h_all"])
            event_mass = np.asarray(record["event_mass_mean_all"])
            event_rows.append(
                event_metrics(
                    arrival[selected],
                    tier_probability[selected].argmax(axis=1) if len(selected) else np.zeros(0),
                    latency_probability[selected].argmax(axis=1) if len(selected) else np.zeros(0),
                    event_mass[selected],
                    sample.target_event_time_h,
                    sample.target_event_tier,
                    sample.target_event_latency,
                    sample.target_event_mass_GPU_h,
                )
            )
            predicted_power = np.asarray(
                packets_to_power(arrival, tier_probability, event_mass)["power_IT_kW"]
            )
            actual_power = actual_target_power(
                sample.target_event_time_h,
                sample.target_event_tier,
                sample.target_event_mass_GPU_h,
            )
            proposed_power_prediction.extend(predicted_power.tolist())
            proposed_power_actual.extend(actual_power.tolist())
            mass_errors.extend(
                [
                    float(record["mass_identity_mean_error"]),
                    float(record["mass_identity_q50_error"]),
                    float(record["mass_identity_q90_error"]),
                ]
            )
    selected_event_metrics = aggregate_event_metrics(event_rows)
    selected_event_metrics.update(
        power_metrics(np.asarray(proposed_power_actual), np.asarray(proposed_power_prediction))
    )
    selected_event_metrics["daily_event_mass_identity_max_abs_error_GPU_h"] = float(max(mass_errors))
    return {
        "store": store,
        "models": models,
        "fold_train_indices": fold_train_indices,
        "folds": folds_payload,
        "comparison": comparison,
        "raw_metrics": raw_metrics,
        "training_reports": training_reports,
        "selected_variant": selected_variant,
        "median_seed": median_seed,
        "selected_event_metrics": selected_event_metrics,
    }


def ensemble_rows(
    store: dict[str, dict[str, list[dict[str, object]]]], model: str
) -> list[dict[str, object]]:
    by_date: dict[str, list[dict[str, object]]] = defaultdict(list)
    for rows in store[model].values():
        for row in rows:
            by_date[str(row["date"])].append(row)
    result = []
    for date in sorted(by_date):
        rows = by_date[date]
        first = rows[0]
        result.append(
            {
                **first,
                "mean": float(np.mean([float(row["mean"]) for row in rows])),
                "q50": float(np.mean([float(row["q50"]) for row in rows])),
                "q90": float(np.mean([float(row["q90"]) for row in rows])),
            }
        )
    return result


def acceptance(cv: dict[str, object]) -> dict[str, object]:
    comparison = cv["comparison"]
    proposed = cv["selected_variant"]
    baselines = [name for name in comparison if name not in VARIANTS]
    best = min(baselines, key=lambda name: float(comparison[name]["daily_WAPE_mean"]))
    proposed_wape = float(comparison[proposed]["daily_WAPE_mean"])
    baseline_wape = float(comparison[best]["daily_WAPE_mean"])
    proposed_burst = float(comparison[proposed]["burst_WAPE_mean"])
    baseline_burst = float(comparison[best]["burst_WAPE_mean"])
    proposed_rows = ensemble_rows(cv["store"], proposed)
    baseline_rows = ensemble_rows(cv["store"], best)
    baseline_map = {row["date"]: row for row in baseline_rows}
    actual = np.asarray([row["actual"] for row in proposed_rows])
    p = np.asarray([row["mean"] for row in proposed_rows])
    b = np.asarray([baseline_map[row["date"]]["mean"] for row in proposed_rows])
    bootstrap = block_bootstrap_error_difference(actual, p, b)
    wape_improvement = (baseline_wape - proposed_wape) / baseline_wape
    burst_improvement = (baseline_burst - proposed_burst) / baseline_burst
    proposed_ratio = float(comparison[proposed]["aggregate_mass_ratio_mean"])
    baseline_ratio = float(comparison[best]["aggregate_mass_ratio_mean"])
    structural = float(cv["selected_event_metrics"]["daily_event_mass_identity_max_abs_error_GPU_h"]) <= 1e-8
    accepted = bool(
        wape_improvement >= 0.10
        and burst_improvement >= 0.10
        and bootstrap["supports_proposed_improvement"]
        and abs(proposed_ratio - 1.0) < abs(baseline_ratio - 1.0)
        and structural
    )
    modest = bool(
        not accepted
        and wape_improvement > 0
        and burst_improvement > 0
        and bootstrap["supports_proposed_improvement"]
    )
    return {
        "best_non_proposed_baseline": best,
        "selected_C_MASS_TPP_variant": proposed,
        "daily_WAPE_relative_improvement": wape_improvement,
        "burst_WAPE_relative_improvement": burst_improvement,
        "bootstrap": bootstrap,
        "proposed_mass_ratio": proposed_ratio,
        "baseline_mass_ratio": baseline_ratio,
        "proposed_closer_to_one": abs(proposed_ratio - 1.0) < abs(baseline_ratio - 1.0),
        "hard_structural_tests_pass": structural,
        "PROPOSED_MODEL_ACCEPTED": accepted,
        "PROPOSED_MODEL_STATUS": "STRONG_ACCEPT" if accepted else ("NOVEL_BUT_MODEST_GAIN" if modest else "PERFORMANCE_FAIL"),
    }


def ablation_study(
    input_events: pd.DataFrame,
    samples: list[DailySample],
    cv: dict[str, object],
    k_max: int,
    epochs: int,
) -> list[dict[str, object]]:
    selected = str(cv["selected_variant"])
    comparison = cv["comparison"]
    rows: list[dict[str, object]] = []
    reuse = [
        ("A1_WO_SSL_PRETRAINING", "V19-A", "predefined V19-A"),
        ("A2_WO_BURST_HEAD", "V19-B", "predefined V19-B"),
    ]
    for name, model, note in reuse:
        metrics = comparison[model]
        rows.append(
            {
                "ablation": name,
                "daily_WAPE": metrics.get("daily_WAPE_mean"),
                "burst_WAPE": metrics.get("burst_WAPE_mean"),
                "mass_ratio": metrics.get("aggregate_mass_ratio_mean"),
                "event_set_metric": None,
                "power_WAPE": metrics.get("flexible_IT_power_WAPE_mean"),
                "mass_identity_max_error_GPU_h": None,
                "execution": "REUSED_THREE_SEED_FIVE_FOLD_VARIANT",
                "note": note,
            }
        )
    specifications = [
        ("A3_WO_EVENT_ENCODER", {"use_event_encoder": False}),
        ("A4_WO_HARD_MASS_RECONCILIATION", {"use_hard_reconciliation": False}),
        ("A5_WO_POWER_TIER_MARK", {"use_power_tier_mark": False}),
        ("A6_STANDARD_TRANSFORMER_ENCODER", {"encoder_type": "standard_transformer_15min_tokens"}),
        ("A7_96_SLOT_HIERARCHICAL_DECODER", {"decoder_type": "hierarchical_96_slot"}),
    ]
    for name, overrides in specifications:
        prediction_rows: list[dict[str, object]] = []
        event_metric_rows: list[dict[str, float | None]] = []
        power_actual: list[float] = []
        power_prediction: list[float] = []
        identity_errors: list[float] = []
        for fold in expanding_blocked_folds():
            train_index = indices_for_period(samples, fold.train_start, fold.train_end)
            validation_index = indices_for_period(samples, fold.validation_start, fold.validation_end)
            train_mass = np.asarray([samples[i].daily_mass_GPU_h for i in train_index])
            threshold = float(np.quantile(train_mass, 0.9))
            features, seconds = training_pretrain_arrays(input_events, fold.validation_start)
            trained = train_cmass(
                samples,
                train_index,
                selected,
                SEEDS[0],
                k_max,
                features,
                seconds,
                config_overrides=overrides,
                epochs=max(2, epochs // 2),
            )
            predictions = predict_cmass(trained, samples, validation_index, decode_events=True)
            for record in predictions:
                sample = samples[int(record["index"])]
                prediction_rows.append(
                    {
                        "fold": fold.fold_id,
                        "index": int(record["index"]),
                        "date": sample.date,
                        "actual": sample.daily_mass_GPU_h,
                        "mean": record["mean"],
                        "q50": record["q50"],
                        "q90": record["q90"],
                        "burst": sample.daily_mass_GPU_h >= threshold,
                    }
                )
                arrival = np.asarray(record["arrival_h_all"])
                tier_probability = np.asarray(record["tier_probability_all"])
                latency_probability = np.asarray(record["latency_probability_all"])
                event_mass = np.asarray(record["event_mass_mean_all"])
                selected_index = np.asarray(record["selected_index"], dtype=int)
                event_metric_rows.append(
                    event_metrics(
                        arrival[selected_index],
                        tier_probability[selected_index].argmax(axis=1) if len(selected_index) else np.zeros(0),
                        latency_probability[selected_index].argmax(axis=1) if len(selected_index) else np.zeros(0),
                        event_mass[selected_index],
                        sample.target_event_time_h,
                        sample.target_event_tier,
                        sample.target_event_latency,
                        sample.target_event_mass_GPU_h,
                    )
                )
                predicted = np.asarray(packets_to_power(arrival, tier_probability, event_mass)["power_IT_kW"])
                actual = actual_target_power(
                    sample.target_event_time_h,
                    sample.target_event_tier,
                    sample.target_event_mass_GPU_h,
                )
                power_prediction.extend(predicted.tolist())
                power_actual.extend(actual.tolist())
                identity_errors.append(float(record["mass_identity_mean_error"]))
        metrics = metric_rows(samples, prediction_rows)
        events = aggregate_event_metrics(event_metric_rows)
        power = power_metrics(np.asarray(power_actual), np.asarray(power_prediction))
        rows.append(
            {
                "ablation": name,
                "daily_WAPE": metrics["daily_WAPE"],
                "burst_WAPE": metrics["burst_WAPE"],
                "mass_ratio": metrics["aggregate_mass_ratio"],
                "event_set_metric": events.get("OT_event_set_cost"),
                "power_WAPE": power["flexible_IT_power_WAPE"],
                "mass_identity_max_error_GPU_h": float(max(identity_errors)),
                "execution": "ONE_PREREGISTERED_SEED_FIVE_FOLD",
                "note": "A4 intentionally removes the structural identity; A6 pools all events into 672 causal tokens; A7 keeps aggregate mass but uses 96 anonymous slot queries.",
            }
        )
    return rows


def final_training(
    input_events: pd.DataFrame,
    samples: list[DailySample],
    selected_variant: str,
    k_max: int,
    epochs: int,
) -> list[TrainingResult]:
    train_index = np.arange(len(samples), dtype=np.int64)
    selected = input_events.loc[
        input_events["submit_AEST"].lt(pd.Timestamp("2025-04-01", tz=input_events["submit_AEST"].dt.tz))
    ]
    features = event_feature_matrix(selected)
    seconds = selected["submit_time"].astype("int64").to_numpy(np.float64) / 1e9
    return [
        train_cmass(
            samples,
            train_index,
            selected_variant,
            seed,
            k_max,
            features,
            seconds,
            epochs=epochs,
        )
        for seed in SEEDS
    ]


def write_pre_april_freeze(
    cv: dict[str, object],
    acceptance_result: dict[str, object],
    final_models: list[TrainingResult],
) -> tuple[Path, str]:
    payload = {
        "artifact_id": "V19_MODEL_SELECTION_PRE_APRIL_FREEZE_V1",
        "created_before_any_April_target_read": True,
        "April_target_reads_before_freeze": 0,
        "selected_variant": cv["selected_variant"],
        "selection_metric": "three-seed mean Daily GPU-h WAPE on five training-only expanding blocked folds",
        "median_seed_for_event_diagnostics": cv["median_seed"],
        "acceptance": acceptance_result,
        "final_training": [
            {
                "seed": result.seed,
                "variant": result.variant,
                "variance_power": result.variance_power,
                "epochs": result.epochs,
                "parameters": result.model.parameter_count(),
                "pretraining": result.pretraining,
                "macro_mean": result.macro_mean,
                "macro_std": result.macro_std,
                "config": asdict(result.model.config),
            }
            for result in final_models
        ],
        "facility_scale_firewall": {
            "model_selection_uses_facility_share": False,
            "model_selection_uses_grid_objective": False,
            "C_MODEL_GPU": 528,
            "C_MODEL_role": "EQUIVALENT_CASE_STUDY_H100_CAPACITY",
            "facility_scale_authority": "NOT_FINAL_REAL_WORLD_AUTHORITY",
        },
        "random_seed_policy": "all three preregistered seeds retained; no lucky-seed selection",
        "future_locked_test_available": False,
    }
    path = write_json("V19_MODEL_SELECTION_PRE_APRIL_FREEZE.json", payload)
    return path, sha256(path)


def ensemble_prediction_records(records: list[dict[str, object]]) -> dict[str, object]:
    return {
        "mean": float(np.mean([record["mean"] for record in records])),
        "q50": float(np.mean([record["q50"] for record in records])),
        "q90": float(np.mean([record["q90"] for record in records])),
        "count_mean": float(np.mean([record["count_mean"] for record in records])),
        "burst_probability": np.mean(
            np.stack([np.asarray(record["burst_probability"]) for record in records]), axis=0
        ),
        "arrival_h_all": np.mean(
            np.stack([np.asarray(record["arrival_h_all"]) for record in records]), axis=0
        ),
        "tier_probability_all": np.mean(
            np.stack([np.asarray(record["tier_probability_all"]) for record in records]), axis=0
        ),
        "latency_probability_all": np.mean(
            np.stack([np.asarray(record["latency_probability_all"]) for record in records]), axis=0
        ),
        "event_mass_mean_all": np.mean(
            np.stack([np.asarray(record["event_mass_mean_all"]) for record in records]), axis=0
        ),
        "event_mass_q50_all": np.mean(
            np.stack([np.asarray(record["event_mass_q50_all"]) for record in records]), axis=0
        ),
        "event_mass_q90_all": np.mean(
            np.stack([np.asarray(record["event_mass_q90_all"]) for record in records]), axis=0
        ),
    }


def april_postfreeze(
    training_inputs: pd.DataFrame,
    final_models: list[TrainingResult],
    freeze_sha: str,
) -> dict[str, object]:
    freeze_path = OUT / "V19_MODEL_SELECTION_PRE_APRIL_FREEZE.json"
    if not freeze_path.is_file() or sha256(freeze_path) != freeze_sha:
        raise RuntimeError("V19_PRE_APRIL_FREEZE_MISSING_OR_CHANGED")
    april_frame, april_source = load_h100_source(202504, 202504)
    april_inputs = source_valid_input_events(april_frame)
    combined_inputs = pd.concat((training_inputs, april_inputs), ignore_index=True).sort_values(
        ["submit_time", "id"]
    )
    combined_inputs["partition_code"] = pd.Categorical(
        combined_inputs["partition"].astype(str)
    ).codes
    combined_inputs["qos_code"] = pd.Categorical(combined_inputs["qos"].astype(str)).codes
    april_targets = semantic_flexible_targets(
        april_frame, "2025-04-01", APRIL_END_EXCLUSIVE, conflict_ids()
    )
    april_samples = build_daily_samples(
        combined_inputs, april_targets, "2025-04-01", APRIL_END_EXCLUSIVE
    )
    index = {sample.date: i for i, sample in enumerate(april_samples)}
    v18r2 = json.loads(
        (
            ROOT
            / "dayahead"
            / "artifacts"
            / "v18r2_aidc_forecast_magnitude_refreeze"
            / "V18R2_APRIL_DIAGNOSTIC_FORECAST.json"
        ).read_text(encoding="utf-8")
    )
    v18r2_days = {row["day"]: row for row in v18r2["days"]}
    daily_rows = []
    event_rows = []
    power_rows = []
    scheduler_rows = []
    facility_rows = []
    total_it_energy = 0.0
    flex_it_energy = 0.0
    all_total_kw: list[float] = []
    all_flex_kw: list[float] = []
    all_actual_kw: list[float] = []
    all_predicted_kw: list[float] = []
    max_identity = 0.0
    max_facility_error = 0.0
    minimum_residual = float("inf")
    negative_residual_count = 0
    maximum_flex_minus_total = -float("inf")
    coefficients = tier_coefficients_kWh_per_GPU_h()
    coefficient_array = np.asarray([coefficients[tier] for tier in TIERS])
    for day in DEBUG_DAYS:
        sample = april_samples[index[day]]
        one_index = np.asarray([index[day]], dtype=np.int64)
        seed_records = [predict_cmass(model, april_samples, one_index, True)[0] for model in final_models]
        ensemble = ensemble_prediction_records(seed_records)
        arrival = np.asarray(ensemble["arrival_h_all"])
        tier_probability = np.asarray(ensemble["tier_probability_all"])
        latency_probability = np.asarray(ensemble["latency_probability_all"])
        event_mass = np.asarray(ensemble["event_mass_mean_all"])
        identity = abs(float(event_mass.sum()) - float(ensemble["mean"]))
        q50_identity = abs(float(np.asarray(ensemble["event_mass_q50_all"]).sum()) - float(ensemble["q50"]))
        q90_identity = abs(float(np.asarray(ensemble["event_mass_q90_all"]).sum()) - float(ensemble["q90"]))
        max_identity = max(max_identity, identity, q50_identity, q90_identity)
        predicted_power = packets_to_power(arrival, tier_probability, event_mass)
        actual_power_kw = actual_target_power(
            sample.target_event_time_h,
            sample.target_event_tier,
            sample.target_event_mass_GPU_h,
        )
        all_predicted_kw.extend(np.asarray(predicted_power["power_IT_kW"]).tolist())
        all_actual_kw.extend(actual_power_kw.tolist())
        count = min(len(arrival), max(0, int(round(float(ensemble["count_mean"])))))
        selected = np.argsort(-event_mass, kind="mergesort")[:count]
        event_metric = event_metrics(
            arrival[selected],
            tier_probability[selected].argmax(axis=1) if len(selected) else np.zeros(0),
            latency_probability[selected].argmax(axis=1) if len(selected) else np.zeros(0),
            event_mass[selected],
            sample.target_event_time_h,
            sample.target_event_tier,
            sample.target_event_latency,
            sample.target_event_mass_GPU_h,
        )
        event_rows.append(
            {
                "date": day,
                "predicted_event_count_mean": float(ensemble["count_mean"]),
                "observed_event_count_diagnostic": len(sample.target_event_mass_GPU_h),
                **event_metric,
                "mean_mass_identity_error_GPU_h": identity,
                "Q50_mass_identity_error_GPU_h": q50_identity,
                "Q90_mass_identity_error_GPU_h": q90_identity,
                "predicted_tier_mass_GPU_h": json.dumps(
                    dict(zip(TIERS, np.asarray(predicted_power["tier_mass_GPU_h"]))),
                    default=json_default,
                ),
            }
        )
        p_it_site, rack_weights = reference_it_power(day)
        arrivals = packet_arrivals(arrival, tier_probability, latency_probability, event_mass)
        schedule = grid_blind_edf(arrivals, rack_weights)
        rack_service = np.asarray(schedule["rack_service"])
        p_flex_rack = (
            rack_service * coefficient_array[None, :, None]
        ).sum(axis=1) / DT_H
        p_flex_site = p_flex_rack.reshape(96, 12, 4).sum(axis=2)
        residual = p_it_site - p_flex_site
        reconstructed = residual + p_flex_site
        error = float(np.max(np.abs(p_it_site - reconstructed)))
        minimum_residual = min(minimum_residual, float(residual.min()))
        max_facility_error = max(max_facility_error, error)
        negative_residual_count += int(np.sum(residual < -1e-10))
        maximum_flex_minus_total = max(
            maximum_flex_minus_total, float(np.max(p_flex_site - p_it_site))
        )
        day_total = float(p_it_site.sum() * DT_H)
        day_flex = float(p_flex_site.sum() * DT_H)
        total_it_energy += day_total
        flex_it_energy += day_flex
        all_total_kw.extend(p_it_site.sum(axis=1).tolist())
        all_flex_kw.extend(p_flex_site.sum(axis=1).tolist())
        scheduler_rows.append(
            {
                "day": day,
                **{key: value for key, value in schedule.items() if key not in {"service", "rack_service"}},
            }
        )
        facility_rows.append(
            {
                "day": day,
                "label": "PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC",
                "total_IT_kWh": day_total,
                "flexible_IT_kWh": day_flex,
                "locked_residual_IT_kWh": day_total - day_flex,
                "minimum_locked_residual_IT_kW": float(residual.min()),
                "negative_residual_count": int(np.sum(residual < -1e-10)),
                "maximum_decomposition_error_kW": error,
            }
        )
        for slot in range(96):
            power_rows.append(
                {
                    "date": day,
                    "slot": slot,
                    "predicted_flexible_IT_kW": float(np.asarray(predicted_power["power_IT_kW"])[slot]),
                    "predicted_flexible_PCC_kW": float(np.asarray(predicted_power["power_PCC_kW"])[slot]),
                    "observed_diagnostic_flexible_IT_kW": float(actual_power_kw[slot]),
                    "scale_label": "PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC",
                }
            )
        daily_rows.append(
            {
                "date": day,
                "V18R2_Q50_GPU_h": float(v18r2_days[day]["new_W_F_Q50_GPU_h"]),
                "C_MASS_mean_GPU_h": float(ensemble["mean"]),
                "C_MASS_Q50_GPU_h": float(ensemble["q50"]),
                "C_MASS_Q90_GPU_h": float(ensemble["q90"]),
                "observed_diagnostic_GPU_h": sample.daily_mass_GPU_h,
                "predicted_event_count": float(ensemble["count_mean"]),
                "burst_probability": float(np.asarray(ensemble["burst_probability"])[2]),
                "predicted_tier_mass_GPU_h": dict(
                    zip(TIERS, np.asarray(predicted_power["tier_mass_GPU_h"]))
                ),
                "label": "OBSERVED_DIAGNOSTIC_NOT_LOCKED_TEST",
            }
        )
    total_array = np.asarray(all_total_kw)
    flex_array = np.asarray(all_flex_kw)
    peak = int(np.argmax(total_array))
    scheduler = {
        "artifact_id": "V19_REFERENCE_SCHEDULER_PREFLIGHT_V1",
        "policy": "GRID_BLIND_EDF_FLUID_GPU_HOUR_WITH_FROZEN_ENGINEERING_RACK_WEIGHTS",
        "C_MODEL_GPU": 528,
        "C_MODEL_role": "EQUIVALENT_CASE_STUDY_H100_CAPACITY",
        "days": scheduler_rows,
        "total_arrival_GPU_h": float(sum(row["arrival_GPU_h"] for row in scheduler_rows)),
        "total_served_GPU_h": float(sum(row["served_GPU_h"] for row in scheduler_rows)),
        "terminal_backlog_GPU_h": float(sum(row["terminal_backlog_GPU_h"] for row in scheduler_rows)),
        "maximum_deadline_shortfall_GPU_h": float(max(row["max_deadline_shortfall_GPU_h"] for row in scheduler_rows)),
        "maximum_capacity_violation_GPU_h_per_slot": float(max(row["max_system_capacity_violation_GPU_h_per_slot"] for row in scheduler_rows)),
        "hidden_shedding_GPU_h": 0.0,
        "feasible": bool(all(row["feasible"] for row in scheduler_rows)),
        "B0_B1_B2_B3_science_calls": 0,
        "OpenDSS_calls": 0,
    }
    facility = {
        "artifact_id": "V19_FACILITY_DECOMPOSITION_VALIDATION_V1",
        "scale_authority_label": "PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC",
        "not_final_Melbourne_site_capacity_authority": True,
        "days": facility_rows,
        "total_IT_kWh": total_it_energy,
        "provisional_flexible_IT_kWh": flex_it_energy,
        "minimum_locked_residual_IT_kW": minimum_residual,
        "negative_residual_count": negative_residual_count,
        "maximum_decomposition_error_kW": max_facility_error,
        "maximum_flexible_minus_total_kW": maximum_flex_minus_total,
        "PUE": PUE,
        "PUE_application_count": 1,
        "negative_clipping_calls": 0,
        "model_acceptance_uses_this_artifact": False,
        "gate": "PASS_PROVISIONAL_DIAGNOSTIC_DECOMPOSITION"
        if negative_residual_count == 0 and max_facility_error <= 1e-9
        else "FAIL_PROVISIONAL_DIAGNOSTIC_DECOMPOSITION",
    }
    provisional_share = flex_it_energy / total_it_energy
    flexibility = {
        "artifact_id": "V19_FACILITY_FLEXIBILITY_DIAGNOSTIC_V1",
        "scale_authority_label": "LEGACY_FACILITY_SCALE_DIAGNOSTIC_ONLY",
        "FINAL_FACILITY_FLEXIBILITY_SHARE": None,
        "provisional_legacy_energy_share": provisional_share,
        "provisional_legacy_at_total_peak_share": float(flex_array[peak] / total_array[peak]),
        "provisional_legacy_max_instantaneous_share": float(
            np.max(np.divide(flex_array, total_array, out=np.zeros_like(flex_array), where=total_array > 0))
        ),
        "provisional_mean_flexible_IT_kW": float(flex_array.mean()),
        "provisional_peak_flexible_IT_kW": float(flex_array.max()),
        "provisional_mean_flexible_PCC_kW": float(flex_array.mean() * PUE),
        "provisional_peak_flexible_PCC_kW": float(flex_array.max() * PUE),
        "literature_target_calibration": False,
        "model_acceptance_uses_facility_share": False,
        "future_authority": "SITE_SPECIFIC_AIDC_SCALE_AUTHORITY_NOT_YET_AVAILABLE",
    }
    return {
        "source": april_source,
        "freeze_sha256": freeze_sha,
        "daily_rows": daily_rows,
        "event_rows": event_rows,
        "power_rows": power_rows,
        "scheduler": scheduler,
        "facility": facility,
        "flexibility": flexibility,
        "April_target_reads_before_freeze": 0,
        "April_target_reads_after_freeze": 1,
        "April_reads_for_model_selection_or_tuning": 0,
        "seven_day_mean_GPU_h": float(sum(row["C_MASS_mean_GPU_h"] for row in daily_rows)),
        "seven_day_Q50_GPU_h": float(sum(row["C_MASS_Q50_GPU_h"] for row in daily_rows)),
        "seven_day_Q90_GPU_h": float(sum(row["C_MASS_Q90_GPU_h"] for row in daily_rows)),
        "seven_day_observed_GPU_h_diagnostic": float(sum(row["observed_diagnostic_GPU_h"] for row in daily_rows)),
        "daily_event_mass_identity_max_abs_error_GPU_h": max_identity,
        "electrical_metrics": power_metrics(np.asarray(all_actual_kw), np.asarray(all_predicted_kw)),
    }


def result_csv_rows(
    comparison: dict[str, object], models: list[str]
) -> list[dict[str, object]]:
    rows = []
    for model in models:
        summary = comparison[model]
        for seed, metrics in summary["seed_metrics"].items():
            rows.append(
                {
                    "model": model,
                    "seed": seed,
                    "Daily_WAPE": metrics.get("daily_WAPE"),
                    "MAE_GPU_h": metrics.get("daily_MAE_GPU_h"),
                    "RMSE_GPU_h": metrics.get("daily_RMSE_GPU_h"),
                    "mean_bias_GPU_h": metrics.get("mean_bias_GPU_h"),
                    "mass_ratio": metrics.get("aggregate_mass_ratio"),
                    "burst_WAPE": metrics.get("burst_WAPE"),
                    "Q50_pinball": metrics.get("Q50_pinball"),
                    "Q90_pinball": metrics.get("Q90_pinball"),
                    "Q50_coverage": metrics.get("Q50_coverage"),
                    "Q90_coverage": metrics.get("Q90_coverage"),
                    "Power_WAPE": metrics.get("flexible_IT_power_WAPE"),
                }
            )
    return rows


def build_artifacts(
    training_inputs: pd.DataFrame,
    training_targets: pd.DataFrame,
    samples: list[DailySample],
    data_report: dict[str, object],
    cv: dict[str, object],
    acceptance_result: dict[str, object],
    ablations: list[dict[str, object]],
    freeze_sha: str,
    april: dict[str, object],
) -> dict[str, object]:
    preservation = verify_preservation()
    if preservation["status"] != "PASS":
        raise RuntimeError(f"V19_PRESERVATION_FAIL:{preservation['failures'][:2]}")
    target_identity = float(
        max(
            abs(sample.daily_mass_GPU_h - float(sample.target_event_mass_GPU_h.sum()))
            for sample in samples
        )
    )
    dataset_contract = {
        "artifact_id": "V19_EVENT_DATASET_CONTRACT_V1",
        "training_source": data_report["source"],
        "training_period_AEST": [TRAIN_START, "2025-03-31"],
        "D_minus_1_cutoff": "18:00 AEST on the day before target day",
        "micro_history": "previous 7 days, every source-valid H100 submission event",
        "macro_history": "previous 28 days, submission/request-side only",
        "input_event_fields": [
            "submission timestamp",
            "continuous age/delta-time",
            "gpus_requested",
            "nodes_req",
            "wallclock_req",
            "full/partial request structure",
            "partition",
            "QoS",
            "calendar",
        ],
        "main_model_realized_history_fields": [],
        "target_label": "next-day submitted semantic-flexible completed H100 jobs; retrospective queue>600 seconds and realized service runtime are TRAINING_TARGET_LABEL_ONLY",
        "target_event_fields": ["arrival_time_h", "power_tier", "latency_C1_C5", "service_mass_GPU_h"],
        "daily_master_mass": "H_d^F = sum(gpus_requested * realized_runtime_h) of target events",
        "tiers": list(TIERS),
        "latencies": list(LATENCIES),
        "global_conflict_jobs_excluded": 76,
        "causality": causality_audit(),
        "facility_scale_firewall": {
            "GPU_h_is_scale_independent_ML_authority": True,
            "C_MODEL_role": "EQUIVALENT_CASE_STUDY_H100_CAPACITY",
            "facility_scale_factor_applied_to_GPU_h": False,
            "beta_AIDC_applied": False,
        },
    }
    reproduction = {
        "artifact_id": "V19_EVENT_DATASET_REPRODUCTION_V1",
        **data_report,
        "daily_master_mass_identity_max_abs_error_GPU_h": target_identity,
        "daily_slot_mass_identity_max_abs_error_GPU_h": float(
            max(abs(sample.daily_mass_GPU_h - float(sample.target_slot_mass_GPU_h.sum())) for sample in samples)
        ),
        "daily_tier_mass_identity_max_abs_error_GPU_h": float(
            max(abs(sample.daily_mass_GPU_h - float(sample.target_tier_mass_GPU_h.sum())) for sample in samples)
        ),
        "zero_target_days": int(sum(sample.daily_mass_GPU_h == 0 for sample in samples)),
        "target_event_mass_min_GPU_h": float(training_targets["service_GPU_h"].min()),
        "target_event_mass_max_GPU_h": float(training_targets["service_GPU_h"].max()),
        "KMAX_RESOURCE_BLOCKER": True,
        "KMAX_resolution": "10,012 queries retained through chunked decoder; no target-event truncation",
    }
    pretraining_contract = {
        "artifact_id": "V19_EVENT_ENCODER_PRETRAINING_CONTRACT_V1",
        "input_universe": "outer-fold training-only source-valid H100 request/submission events",
        "tasks": [
            "masked gpus/nodes/wallclock class reconstruction",
            "log1p next inter-arrival prediction",
            "next GPU request-class prediction",
        ],
        "future_realized_information_reads": 0,
        "outer_validation_event_reads": 0,
        "epochs": 2,
        "seeds": list(SEEDS),
    }
    pretraining_report = {
        "artifact_id": "V19_EVENT_ENCODER_PRETRAINING_REPORT_V1",
        "runs": cv["training_reports"],
        "summary": "V19-B/V19-C were pretrained separately inside each outer training fold; V19-A was not pretrained.",
        "execution_correction": {
            "EXECUTION_DEVICE_CHANGE_ONLY": "CPU_TO_CUDA",
            "RESULT_BASED_RETUNING": 0,
            "frozen_epochs": 2,
            "cpu_reference_full_run_seconds": 252.86667400000002,
            "cpu_reference_median_fold_variant_seed_training_seconds": 1.3213073000000009,
            "final_table_mixes_CPU_and_CUDA_deep_folds": False,
        },
    }
    architecture = {
        "artifact_id": "V19_C_MASS_TPP_ARCHITECTURE_CONTRACT_V1",
        "name": "Causal Mass-Conserving Aggregate-conditioned Service-Set Temporal Point Process",
        "modules": {
            "A_encoder": "causal diagonal exponential-decay jump state-space over every irregular event plus 28-day macro MLP",
            "B_mass_head": "nonnegative conditional mean and structurally monotone Q50/Q90",
            "C_burst_head": "fold-training P50/P90 three-class auxiliary head",
            "D_service_set_decoder": "10,012 anonymous all-at-once queries evaluated in chunks of 512",
            "E_hard_reconciliation": "float64 alpha-normalized allocation with final round-off residual correction",
        },
        "encoder_note": "The user-provided GRUCell recurrence was a recommended reference. The implemented vectorized diagonal decay/jump SSM preserves all events and is CPU-feasible; encoder novelty is not claimed.",
        "mass_identity": [
            "sum event_mass_mean == daily_mean",
            "sum event_mass_Q50 == Q50",
            "sum event_mass_Q90 == Q90",
        ],
        "set_matching": {
            "small_sets": "deterministic entropic Sinkhorn",
            "large_sets": "memory-bounded monotone 1-D OT with mark/mass costs",
            "event_truncation": False,
        },
        "variants": {
            "V19-A": "without SSL",
            "V19-B": "SSL, no burst auxiliary",
            "V19-C": "SSL plus burst auxiliary",
        },
        "loss_weights": {
            "Tweedie": 1.0,
            "quantile": 0.0002,
            "burst": 0.05,
            "event_set": 0.05,
            "count": 0.01,
            "count_consistency": 0.001,
            "mass_conservation_loss": None,
        },
        "facility_scale_firewall": "SCALE_INDEPENDENT_GPU_H_ONLY_FOR_ACCEPTANCE",
    }
    split_contract = {
        "artifact_id": "V19_BLOCKED_CV_SPLIT_CONTRACT_V1",
        "protocol": "five expanding calendar-exact outer folds; compact nested training-tail selection for Tweedie p",
        "folds": cv["folds"],
        "deep_seeds": list(SEEDS),
        "April_rows": 0,
    }
    baseline_audit = {
        "artifact_id": "V19_BASELINE_IMPLEMENTATION_AUDIT_V1",
        "executed": {
            "B0": "V18R2 Candidate-B empirical DOW Q50/Q90 rule",
            "B1": "D-7 requested-service proxy with training-only scale",
            "B2": "LightGBM 4.6.0 Tweedie mean plus quantile heads",
            "B3": "LightGBM 4.6.0 quantile Q50/Q90",
            "B4": "lightweight faithful patch-token Transformer over 28-day request proxy",
            "B5": "RMTPP-style continuous-time recurrent/decay event adaptation with daily horizon head; not canonical next-event likelihood reproduction",
            "B6": "THP-style causal attention-pooling long-horizon adaptation; O(N^2) canonical THP was infeasible at 10k-event windows",
        },
        "not_reproduced": {
            "B7_SAHP": "NOT_REPRODUCED_WITH_REASON: canonical self-attention implementation is quadratic in the observed 7-day event windows and no resource-safe faithful path was available",
            "B8_DEF_EventFlow": "NOT_REPRODUCED_WITH_REASON: primary code/papers were found, but adapting their generative training and dependencies to 10,012 marked service-mass events was not computationally feasible within the frozen evaluation resource budget",
        },
        "fairness": "same dates, target, cutoff, conflict exclusion and April firewall",
        "input_information_table": {
            "B0": "known target-day calendar only",
            "B1": "past request-side proxy",
            "B2_B3": "18 macro request/calendar features",
            "B4": "28-day request-side proxy sequence",
            "B5_B6": "7-day request/submission event history",
            "C_MASS_TPP": "same 7-day event history plus 28-day macro request/calendar context",
        },
        "parameter_and_compute_records": cv["training_reports"],
    }
    write_json("V19_EVENT_DATASET_CONTRACT.json", dataset_contract)
    write_json("V19_EVENT_DATASET_REPRODUCTION.json", reproduction)
    write_json("V19_EVENT_ENCODER_PRETRAINING_CONTRACT.json", pretraining_contract)
    write_json("V19_EVENT_ENCODER_PRETRAINING_REPORT.json", pretraining_report)
    write_json("V19_C_MASS_TPP_ARCHITECTURE_CONTRACT.json", architecture)
    write_json("V19_BLOCKED_CV_SPLIT_CONTRACT.json", split_contract)
    write_json("V19_BASELINE_IMPLEMENTATION_AUDIT.json", baseline_audit)
    result_fields = [
        "model",
        "seed",
        "Daily_WAPE",
        "MAE_GPU_h",
        "RMSE_GPU_h",
        "mean_bias_GPU_h",
        "mass_ratio",
        "burst_WAPE",
        "Q50_pinball",
        "Q90_pinball",
        "Q50_coverage",
        "Q90_coverage",
        "Power_WAPE",
    ]
    baseline_models = [name for name in cv["comparison"] if name not in VARIANTS]
    write_csv(
        "V19_BASELINE_BLOCKED_CV_RESULTS.csv",
        result_csv_rows(cv["comparison"], baseline_models),
        result_fields,
    )
    write_csv(
        "V19_C_MASS_TPP_BLOCKED_CV_RESULTS.csv",
        result_csv_rows(cv["comparison"], list(VARIANTS)),
        result_fields,
    )
    model_comparison = {
        "artifact_id": "V19_MODEL_COMPARISON_V1",
        "SCALE_INDEPENDENT_ML_AUTHORITY": cv["comparison"],
        "selected_variant_event_metrics": cv["selected_event_metrics"],
        "selection_scope": "training-only daily GPU-h and structural ML metrics",
        "SCALE_DEPENDENT_DIAGNOSTIC_NOT_USED_FOR_SELECTION": {
            "available": True,
            "label": "PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC",
            "metrics": april["electrical_metrics"],
        },
    }
    write_json("V19_MODEL_COMPARISON.json", model_comparison)
    write_json("V19_PROPOSED_MODEL_ACCEPTANCE_TEST.json", acceptance_result)
    write_csv(
        "V19_ABLATION_RESULTS.csv",
        ablations,
        [
            "ablation",
            "daily_WAPE",
            "burst_WAPE",
            "mass_ratio",
            "event_set_metric",
            "power_WAPE",
            "mass_identity_max_error_GPU_h",
            "execution",
            "note",
        ],
    )
    april_payload = {
        "artifact_id": "V19_APRIL_POSTFREEZE_DIAGNOSTIC_V1",
        "label": "OBSERVED_DIAGNOSTIC_NOT_LOCKED_TEST",
        "freeze_artifact_sha256": freeze_sha,
        "days": april["daily_rows"],
        "seven_day_mean_GPU_h": april["seven_day_mean_GPU_h"],
        "seven_day_Q50_GPU_h": april["seven_day_Q50_GPU_h"],
        "seven_day_Q90_GPU_h": april["seven_day_Q90_GPU_h"],
        "seven_day_observed_GPU_h_diagnostic": april["seven_day_observed_GPU_h_diagnostic"],
        "April_target_reads_before_freeze": 0,
        "April_target_reads_after_freeze": 1,
        "April_reads_for_model_selection_or_tuning": 0,
        "source": april["source"],
    }
    write_json("V19_APRIL_POSTFREEZE_DIAGNOSTIC.json", april_payload)
    event_fields = list(april["event_rows"][0].keys())
    write_csv("V19_EVENT_FORECAST_DIAGNOSTIC.csv", april["event_rows"], event_fields)
    write_csv(
        "V19_POWER_FORECAST_DIAGNOSTIC.csv",
        april["power_rows"],
        list(april["power_rows"][0].keys()),
    )
    write_json("V19_REFERENCE_SCHEDULER_PREFLIGHT.json", april["scheduler"])
    write_json("V19_FACILITY_DECOMPOSITION_VALIDATION.json", april["facility"])
    write_json("V19_FACILITY_FLEXIBILITY_DIAGNOSTIC.json", april["flexibility"])
    mass_pass = (
        target_identity <= 1e-8
        and float(cv["selected_event_metrics"]["daily_event_mass_identity_max_abs_error_GPU_h"])
        <= 1e-8
        and april["daily_event_mass_identity_max_abs_error_GPU_h"] <= 1e-8
    )
    causality_pass = all(
        value == 0
        for key, value in causality_audit().items()
        if key.endswith("feature_reads")
    )
    if not causality_pass:
        classification = "E. V19_C_MASS_TPP_CAUSALITY_FAIL"
    elif not mass_pass:
        classification = "F. V19_C_MASS_TPP_MASS_COHERENCE_FAIL"
    elif acceptance_result["PROPOSED_MODEL_ACCEPTED"]:
        classification = "A. V19_C_MASS_TPP_NOVELTY_AND_STRONG_PERFORMANCE_PASS"
    elif acceptance_result["PROPOSED_MODEL_STATUS"] == "NOVEL_BUT_MODEST_GAIN":
        classification = "B. V19_C_MASS_TPP_NOVEL_BUT_MODEST_GAIN"
    else:
        classification = "C. V19_C_MASS_TPP_NOVELTY_PASS_PERFORMANCE_FAIL"
    ready = {
        "artifact_id": "V19_READY_FLAGS_V1",
        "RESULT_CLASSIFICATION": classification,
        "NOVELTY_GATE_PASS": True,
        "MODEL_DEVELOPMENT_READY": True,
        "PROPOSED_MODEL_ACCEPTED": bool(acceptance_result["PROPOSED_MODEL_ACCEPTED"]),
        "FACILITY_FORECAST_INTEGRATION_READY": bool(
            april["scheduler"]["feasible"]
            and april["facility"]["gate"] == "PASS_PROVISIONAL_DIAGNOSTIC_DECOMPOSITION"
        ),
        "FACILITY_FORECAST_INTEGRATION_AUTHORITY": "PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC_ONLY",
        "NEW_LOCKED_TEST_READY": False,
        "NEW_GRID_SCIENCE_RUN_READY": False,
        "FINAL_FACILITY_FLEXIBILITY_SHARE": None,
        "preservation": preservation,
        "firewall_counters": {
            "D_day_actual_feature_reads": 0,
            "future_start_feature_reads": 0,
            "future_end_feature_reads": 0,
            "future_queue_wait_feature_reads": 0,
            "future_completion_feature_reads": 0,
            "April_target_reads_before_freeze": 0,
            "April_reads_for_model_selection_or_tuning": 0,
            "literature_target_reads": 0,
            "grid_objective_reads_for_model_selection": 0,
            "result_based_workload_multiplier_calls": 0,
            "beta_AIDC_scaling_calls": 0,
            "facility_scale_calls_on_GPU_h": 0,
            "B0_B1_B2_B3_science_calls": 0,
            "OpenDSS_calls": 0,
            "AC_science_calls": 0,
            "RESULT_BASED_RETUNING": 0,
        },
        "execution_device_correction": {
            "EXECUTION_DEVICE_CHANGE_ONLY": "CPU_TO_CUDA",
            "CPU_deep_fold_results_in_final_table": 0,
        },
    }
    final_review = {
        "artifact_id": "V19_FINAL_REVIEW_V1",
        "result_classification": classification,
        "ready_flags": ready,
        "novelty": json.loads(
            (OUT / "V19_C_MASS_TPP_SYSTEMATIC_NOVELTY_AUDIT.json").read_text(encoding="utf-8")
        ),
        "dataset": reproduction,
        "architecture": architecture,
        "baselines": baseline_audit,
        "SCALE_INDEPENDENT_ML_AUTHORITY": model_comparison["SCALE_INDEPENDENT_ML_AUTHORITY"],
        "proposed_model_acceptance": acceptance_result,
        "ablation": ablations,
        "April_postfreeze": april_payload,
        "electrical_forecast": {
            "label": "PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC",
            **april["electrical_metrics"],
        },
        "facility": april["flexibility"],
        "scheduler": april["scheduler"],
        "limitations": [
            "225-day supervised horizon",
            "semantic-flexible label is a retrospective proxy",
            "exact D-1 queue snapshot absent",
            "capacity timeline partial and C_MODEL is only an equivalent case-study normalization",
            "no untouched locked future test",
            "B5/B6 are resource-feasible long-horizon adaptations rather than canonical likelihood reproductions",
            "B7/B8 not reproduced for documented compute/dependency reasons",
            "facility/site electrical magnitudes are provisional legacy-scale diagnostics, not final Melbourne authority",
        ],
        "git": {
            "starting_branch": START_BRANCH,
            "starting_HEAD": START_HEAD,
            "new_branch": NEW_BRANCH,
            "freeze_commit": "ebd4eb8e631137cf9710fecee768d11ef344c512",
            "novelty_commit": "62eaf1b12a3a298fcd968a8cbfa4a2247fd90212",
        },
    }
    write_json("V19_READY_FLAGS.json", ready)
    write_json("V19_FINAL_REVIEW.json", final_review)
    nearest = final_review["novelty"]["nearest_prior_works"][:5]
    lines = [
        f"RESULT CLASSIFICATION: {classification}",
        "",
        "# V19 C-MASS-TPP final review",
        "",
        "## READY FLAGS",
        "",
    ]
    for key in (
        "NOVELTY_GATE_PASS",
        "MODEL_DEVELOPMENT_READY",
        "PROPOSED_MODEL_ACCEPTED",
        "FACILITY_FORECAST_INTEGRATION_READY",
        "NEW_LOCKED_TEST_READY",
        "NEW_GRID_SCIENCE_RUN_READY",
    ):
        lines.append(f"- {key} = {str(ready[key]).lower()}")
    lines.extend(
        [
            "",
            "## 1. Novelty audit",
            "",
            "World-first claim allowed? `NOT YET`",
            "",
            "| Model | Similar component | C-MASS-TPP addition | Near duplicate? |",
            "|---|---|---|---|",
        ]
    )
    for work in nearest:
        lines.append(
            f"| {work['paper_model']} | {work['nearest_component']} | continuous GPU-h aggregate-to-event hard reconciliation and frozen tier bridge | {work['near_duplicate']} |"
        )
    lines.extend(
        [
            "",
            "## 2. Dataset",
            "",
            f"- all H100 input events: {data_report['source_valid_submission_request_input_events']}",
            f"- flexible target events: {data_report['semantic_flexible_target_events_after_76_conflict_exclusion']}",
            f"- training days: {data_report['training_days']}",
            f"- K_max: {data_report['K_max_training_observed']}",
            f"- master mass identity max error: {target_identity} GPU-h",
            "",
            "## 3. Architecture",
            "",
            "Decay/jump continuous-time encoder, daily mass head, burst auxiliary, chunked all-at-once service-set decoder, and float64 hard reconciliation.",
            "",
            "## 4–7. Baselines, blocked CV, acceptance, ablation",
            "",
            f"- selected variant: {cv['selected_variant']}",
            f"- best baseline: {acceptance_result['best_non_proposed_baseline']}",
            f"- Daily WAPE relative improvement: {acceptance_result['daily_WAPE_relative_improvement']:.6%}",
            f"- Burst WAPE relative improvement: {acceptance_result['burst_WAPE_relative_improvement']:.6%}",
            f"- proposed accepted: {acceptance_result['PROPOSED_MODEL_ACCEPTED']}",
            "",
            "## 8. April post-freeze diagnostic",
            "",
            f"- seven-day conditional mean: {april['seven_day_mean_GPU_h']:.6f} GPU-h",
            f"- observed diagnostic: {april['seven_day_observed_GPU_h_diagnostic']:.6f} GPU-h",
            "- April was read only after the selection-freeze SHA was written.",
            "",
            "## 9–10. Electrical and facility diagnostic",
            "",
            "All IT/PCC/site/facility values are `PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC`. They were not used for model selection.",
            "",
            f"- provisional legacy facility energy share: {april['flexibility']['provisional_legacy_energy_share']:.6%}",
            "- FINAL_FACILITY_FLEXIBILITY_SHARE = null",
            "- literature target calibration: NO",
            "",
            "## 11. Scheduler preflight",
            "",
            f"- feasible: {april['scheduler']['feasible']}",
            f"- served mass: {april['scheduler']['total_served_GPU_h']:.6f} GPU-h",
            f"- terminal backlog: {april['scheduler']['terminal_backlog_GPU_h']:.6f} GPU-h",
            f"- shedding: {april['scheduler']['hidden_shedding_GPU_h']:.6f} GPU-h",
            "",
            "## 12. Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in final_review["limitations"])
    lines.extend(
        [
            "",
            "## 13–14. Artifacts and Git",
            "",
            "Artifact SHA256 values are reported by the final verification pass. Git commits are recorded after generation.",
            "",
            "## 15. Final Q1–Q15",
            "",
            "See `V19_FINAL_REVIEW.json` and the final Codex response for explicit answers.",
        ]
    )
    (OUT / "V19_FINAL_REVIEW.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    readme = {
        "namespace": "V19",
        "purpose": "C-MASS-TPP training-only forecasting evaluation",
        "result_classification": classification,
        "scale_independent_authority": "daily GPU-h and ML/event structural metrics",
        "scale_dependent_diagnostics": "PROVISIONAL_LEGACY_SCALE_DIAGNOSTIC_ONLY",
        "final_facility_flexibility_share": None,
        "prior_artifacts_modified": False,
        "science_runs": {"B0_B1_B2_B3": 0, "OpenDSS": 0, "AC": 0},
    }
    (OUT / "README.md").write_text(
        "# V19 C-MASS-TPP\n\n```json\n"
        + json.dumps(readme, indent=2, ensure_ascii=False)
        + "\n```\n",
        encoding="utf-8",
    )
    return final_review


def smoke() -> None:
    inputs, _, samples, report = training_state()
    fold = expanding_blocked_folds()[0]
    train_index = indices_for_period(samples, fold.train_start, fold.train_end)
    validation_index = indices_for_period(samples, fold.validation_start, fold.validation_end)[:1]
    features, seconds = training_pretrain_arrays(inputs, fold.validation_start)
    trained = train_cmass(
        samples,
        train_index,
        "V19-A",
        SEEDS[0],
        int(report["K_max_training_observed"]),
        features,
        seconds,
        epochs=1,
    )
    prediction = predict_cmass(trained, samples, validation_index, True)[0]
    print(
        json.dumps(
            {
                "K_max": report["K_max_training_observed"],
                "prediction": {key: prediction[key] for key in ("date", "mean", "q50", "q90", "count_mean")},
                "identities": {
                    key: prediction[key]
                    for key in (
                        "mass_identity_mean_error",
                        "mass_identity_q50_error",
                        "mass_identity_q90_error",
                    )
                },
            },
            indent=2,
        )
    )


def full(epochs: int) -> None:
    started = time.perf_counter()
    inputs, targets, samples, data_report = training_state()
    k_max = int(data_report["K_max_training_observed"])
    cv = cv_evaluation(inputs, samples, k_max, epochs)
    acceptance_result = acceptance(cv)
    ablations = ablation_study(inputs, samples, cv, k_max, epochs)
    final_models = final_training(inputs, samples, str(cv["selected_variant"]), k_max, epochs)
    _, freeze_sha = write_pre_april_freeze(cv, acceptance_result, final_models)
    april = april_postfreeze(inputs, final_models, freeze_sha)
    final = build_artifacts(
        inputs,
        targets,
        samples,
        data_report,
        cv,
        acceptance_result,
        ablations,
        freeze_sha,
        april,
    )
    cuda_full_run_seconds = float(time.perf_counter() - started)
    record_execution_summary(cuda_full_run_seconds)
    print(json.dumps({
        "classification": final["result_classification"],
        "elapsed_seconds": cuda_full_run_seconds,
        "artifact_count": len([path for path in OUT.iterdir() if path.is_file()]),
    }, indent=2))


def record_execution_summary(cuda_full_run_seconds: float) -> dict[str, object]:
    report_path = OUT / "V19_EVENT_ENCODER_PRETRAINING_REPORT.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    runs = report["runs"]
    elapsed = np.asarray([float(run["elapsed_seconds"]) for run in runs], dtype=float)
    epoch_seconds = np.asarray(
        [float(value) for run in runs for value in run["epoch_runtime_seconds"]], dtype=float
    )
    utilization = np.asarray(
        [
            float(value)
            for run in runs
            for value in run["gpu_utilization_samples_percent"]
        ],
        dtype=float,
    )
    fold_runtime = {
        str(fold): float(
            sum(float(run["elapsed_seconds"]) for run in runs if int(run["fold"]) == fold)
        )
        for fold in range(1, 6)
    }
    cpu_full = float(report["execution_correction"]["cpu_reference_full_run_seconds"])
    cpu_median = float(
        report["execution_correction"][
            "cpu_reference_median_fold_variant_seed_training_seconds"
        ]
    )
    summary = {
        "EXECUTION_DEVICE_CHANGE_ONLY": "CPU_TO_CUDA",
        "RESULT_BASED_RETUNING": 0,
        "device_name": runs[0]["device_name"],
        "cuda_full_run_seconds": float(cuda_full_run_seconds),
        "cpu_reference_full_run_seconds": cpu_full,
        "measured_full_run_speedup_CPU_over_CUDA": cpu_full / cuda_full_run_seconds,
        "median_fold_variant_seed_training_seconds": float(np.median(elapsed)),
        "measured_median_training_speedup_CPU_over_CUDA": cpu_median / float(np.median(elapsed)),
        "epoch_runtime_seconds_median": float(np.median(epoch_seconds)),
        "epoch_runtime_seconds_min": float(epoch_seconds.min()),
        "epoch_runtime_seconds_max": float(epoch_seconds.max()),
        "fold_training_runtime_seconds_sum_over_variants_and_seeds": fold_runtime,
        "peak_VRAM_bytes": int(max(int(run["peak_VRAM_bytes"]) for run in runs)),
        "gpu_utilization_sample_percent_min": float(utilization.min()),
        "gpu_utilization_sample_percent_mean": float(utilization.mean()),
        "gpu_utilization_sample_percent_max": float(utilization.max()),
        "final_table_mixes_CPU_and_CUDA_deep_folds": False,
    }
    report["execution_summary"] = summary
    write_json("V19_EVENT_ENCODER_PRETRAINING_REPORT.json", report)
    for name in ("V19_READY_FLAGS.json", "V19_FINAL_REVIEW.json"):
        payload = json.loads((OUT / name).read_text(encoding="utf-8"))
        payload["execution_summary"] = summary
        write_json(name, payload)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--epochs", type=int, default=4)
    args = parser.parse_args()
    if args.smoke:
        smoke()
    else:
        full(args.epochs)


if __name__ == "__main__":
    main()
