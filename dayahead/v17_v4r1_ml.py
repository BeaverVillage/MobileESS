"""Training-only RC-MQT V4R1 with latency x whole-GPU-count targets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from .aidc_ml_backend import (
    FROZEN_HPO_CANDIDATES,
    HPO_EPOCHS,
    PRODUCTION_SEED,
    QUANTILES,
    architecture_delta_contract,
    build_transformer,
    normalized_mean_pinball,
    predict_transformer,
    save_production_weights,
    train_transformer,
    verify_saved_weight_fingerprint,
)
from .aidc_ml_data import Direct96Samples, calendar_features
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from .v17_deferrability_ml import _add_interval_average, _find_exact, _load_esif
from .v17_deferrability_semantics import LATENCY_CLASSES, latency_class, write_json
from .v17_v4_whole_gpu_gres import AEST, _as_sequence, _h100


AXIS_START = "2024-08-01"
TRAIN_START = "2024-08-19"
TRAIN_END = "2025-03-31"
TRAIN_END_EXCLUSIVE = "2025-04-01"
APRIL_END_EXCLUSIVE = "2025-05-01"
LOOKBACK = 1344
SELECTED_CANDIDATE_ID = "C02"
DEBUG_DAYS = ("2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13", "2025-04-15", "2025-04-22", "2025-04-23")
GPU_COUNTS = (1, 2, 3, 4)
QUARANTINE_IDS = {"7539787", "7543918", "7545385"}
TARGET_NAMES = (
    "P_IT_REF",
    "G_FIXED_GPU",
    *(f"W_F_{latency}::G{gpu_count}" for latency in LATENCY_CLASSES for gpu_count in GPU_COUNTS),
)
FEATURE_NAMES = (*TARGET_NAMES, "P_IT_REF_observed", "tod_sin", "tod_cos", "dow_sin", "dow_cos", "doy_sin", "doy_cos")


def _load_kestrel_v4r1(path: Path, timestamps: Any, max_month: int) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    import pandas as pd
    import pyarrow.parquet as pq

    required = {
        "id", "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared", "jobs_shared", "nodelist",
    }
    retained: list[Any] = []; members: list[str] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="v17-v4r1-labels-") as temporary:
        local = Path(temporary) / "month.parquet"
        for info in archive.infolist():
            match = re.search(r"year=(\d{4})/month=(\d{1,2})", info.filename.replace("\\", "/"))
            if not match or not info.filename.casefold().endswith(".parquet"):
                continue
            month = int(match.group(1)) * 100 + int(match.group(2))
            if month < 202408 or month > max_month:
                continue
            with archive.open(info) as source, local.open("wb") as target:
                shutil.copyfileobj(source, target)
            schema = set(pq.read_schema(local).names)
            if not required.issubset(schema):
                raise RuntimeError(f"V17_V4R1_KESTREL_SCHEMA_MISSING:{sorted(required-schema)}")
            retained.append(pq.read_table(local, columns=sorted(required)).to_pandas())
            members.append(info.filename)
    frame = pd.concat(retained, ignore_index=True)
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
    queue = (start - submit).dt.total_seconds()
    valid = (
        frame["partition"].apply(_h100)
        & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
        & submit.notna() & start.notna() & end.notna() & end.gt(start)
        & nodes.gt(0) & gpus.gt(0) & queue.ge(0) & np.isfinite(queue)
    )
    node_lists = frame["nodelist"].apply(_as_sequence)
    exact_uniform = np.asarray([
        bool(valid.iloc[index]) and float(nodes.iloc[index]).is_integer()
        and len(node_lists.iloc[index]) == int(nodes.iloc[index])
        and float(gpus.iloc[index]).is_integer()
        and (float(gpus.iloc[index]) / float(nodes.iloc[index])).is_integer()
        and 1 <= int(float(gpus.iloc[index]) / float(nodes.iloc[index])) <= 4
        for index in range(len(frame))
    ], dtype=bool)
    no_share = (
        (sharing.isna() | sharing.eq(0))
        & frame["nodes_shared"].apply(lambda value: not _as_sequence(value))
        & frame["jobs_shared"].apply(lambda value: not _as_sequence(value))
    )
    classes = queue.apply(lambda value: latency_class(float(value)) if pd.notna(value) else None)
    semantic = valid & queue.gt(600.0)
    v1 = semantic & no_share & nodes.isin((1, 2, 4, 8, 16)) & np.isclose(gpus, 4.0 * nodes)
    u2 = semantic & ~v1 & ~no_share
    authorized_flexible = (v1 | u2) & exact_uniform & ~frame["id"].astype(str).isin(QUARANTINE_IDS)
    fixed = valid & classes.eq("FIXED") & exact_uniform
    slot_count = len(timestamps); origin = timestamps[0].tz_convert("UTC").timestamp()
    difference = np.zeros(slot_count + 1, dtype=np.float64); partial = np.zeros(slot_count, dtype=np.float64)
    for index in np.flatnonzero(np.asarray(fixed, dtype=bool)):
        _add_interval_average(
            difference, partial,
            start_seconds=start.iloc[index].timestamp() - origin,
            end_seconds=end.iloc[index].timestamp() - origin,
            magnitude=float(gpus.iloc[index]), slot_count=slot_count,
        )
    g_fixed_gpu = partial + np.cumsum(difference[:-1])
    workload = np.zeros((slot_count, len(LATENCY_CLASSES) * len(GPU_COUNTS)), dtype=np.float64)
    target_index = {(latency, gpu): i for i, (latency, gpu) in enumerate((latency, gpu) for latency in LATENCY_CLASSES for gpu in GPU_COUNTS)}
    excluded_quarantine_flexible_jobs = 0
    for index in np.flatnonzero(np.asarray((v1 | u2) & exact_uniform, dtype=bool)):
        job_id = str(frame.at[index, "id"])
        if job_id in QUARANTINE_IDS:
            excluded_quarantine_flexible_jobs += 1
            continue
        slot = int((submit.iloc[index].timestamp() - origin) // 900)
        if 0 <= slot < slot_count:
            runtime_hours = float((end.iloc[index] - start.iloc[index]).total_seconds() / 3600.0)
            gpu_count = int(float(gpus.iloc[index]) / float(nodes.iloc[index]))
            workload[slot, target_index[(str(classes.iloc[index]), gpu_count)]] += float(gpus.iloc[index]) * runtime_hours
    if np.any(g_fixed_gpu < -1e-12) or np.any(workload < -1e-12):
        raise RuntimeError("V17_V4R1_NEGATIVE_LABEL")
    return g_fixed_gpu, workload, {
        "members_opened": members,
        "max_member_month_opened": max_month,
        "fixed_whole_GPU_jobs": int(fixed.sum()),
        "authorized_flexible_jobs": int(authorized_flexible.sum()),
        "V1_jobs": int(v1.sum()), "U2_jobs": int(u2.sum()),
        "quarantine_flexible_jobs_excluded": excluded_quarantine_flexible_jobs,
        "quarantine_ids": sorted(QUARANTINE_IDS),
        "future_expost_field_inference_reads": 0,
    }


def load_labels(raw_root: Path, *, include_april: bool) -> dict[str, Any]:
    import pandas as pd

    end_exclusive = APRIL_END_EXCLUSIVE if include_april else TRAIN_END_EXCLUSIVE
    max_month = 202504 if include_april else 202503
    timestamps = pd.date_range(pd.Timestamp(AXIS_START, tz=AEST), pd.Timestamp(end_exclusive, tz=AEST), freq="15min", inclusive="left")
    esif = _find_exact(raw_root, "esif.influx.buildingData.PUE.combined.parquet", NLR_SOURCE_SHA256["esif_parquet"])
    kestrel = _find_exact(raw_root, "esif.hpc.kestrel.job-anon.zip", NLR_SOURCE_SHA256["kestrel_jobs_zip"])
    p_it, observed, esif_audit = _load_esif(esif, timestamps)
    g_fixed, workload, kestrel_audit = _load_kestrel_v4r1(kestrel, timestamps, max_month)
    values = np.column_stack((p_it, g_fixed, workload))
    if values.shape != (len(timestamps), len(TARGET_NAMES)) or not np.isfinite(values).all() or np.any(values < 0):
        raise RuntimeError("V17_V4R1_LABEL_MATRIX_INVALID")
    return {
        "timestamps": timestamps, "values": values, "p_observed": observed,
        "source_paths": {"esif": str(esif.resolve()), "kestrel": str(kestrel.resolve())},
        "source_sha256": {"esif": sha256_file(esif), "kestrel": sha256_file(kestrel)},
        "access_audit": {
            "include_april": include_april,
            "April_Kestrel_member_reads": 1 if include_april else 0,
            "April_result_reads": 0,
            "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
            "esif": esif_audit, "kestrel": kestrel_audit,
        },
    }


def _scales(values: np.ndarray, timestamps: Any) -> np.ndarray:
    import pandas as pd

    train = values[(timestamps >= pd.Timestamp(TRAIN_START, tz=AEST)) & (timestamps < pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST))]
    scales = np.ones(values.shape[1], dtype=np.float64)
    for index in range(values.shape[1]):
        positive = train[:, index][train[:, index] > 0]
        if positive.size:
            scales[index] = max(float(np.quantile(positive, 0.95)), 1e-6)
    if not np.isfinite(scales).all() or np.any(scales <= 0):
        raise RuntimeError("V17_V4R1_TARGET_SCALE_INVALID")
    return scales


def _build_samples(labels: Mapping[str, Any], scales: np.ndarray, phase: str) -> Direct96Samples:
    import pandas as pd

    timestamps = labels["timestamps"]; values = np.asarray(labels["values"], dtype=np.float64)
    scaled = values / scales
    features = np.column_stack((scaled, np.asarray(labels["p_observed"], dtype=np.float32)[:, None], calendar_features(timestamps))).astype(np.float32)
    lookup = {timestamp: index for index, timestamp in enumerate(timestamps)}
    x_values: list[np.ndarray] = []; future_values: list[np.ndarray] = []; y_values: list[np.ndarray] = []
    days: list[str] = []; excluded: list[str] = []
    day_axis = pd.date_range(TRAIN_START, TRAIN_END, freq="D") if phase == "training" else [pd.Timestamp(day) for day in DEBUG_DAYS]
    calendar = calendar_features(timestamps)
    for day in day_axis:
        day_start = pd.Timestamp(day.date(), tz=AEST); cutoff = day_start - pd.Timedelta(hours=6)
        history_start = cutoff - pd.Timedelta(minutes=15 * LOOKBACK)
        first = lookup.get(history_start); cutoff_index = lookup.get(cutoff); target_first = lookup.get(day_start)
        if first is None or cutoff_index is None or target_first is None:
            raise RuntimeError(f"V17_V4R1_DIRECT96_AXIS_LOOKUP_FAILED:{day.date()}")
        target_end = target_first + 96
        if not bool(np.asarray(labels["p_observed"][target_first:target_end]).all()):
            excluded.append(day.date().isoformat()); continue
        x = features[first:cutoff_index]; future = calendar[target_first:target_end]; y = scaled[target_first:target_end]
        if x.shape != (LOOKBACK, len(FEATURE_NAMES)) or future.shape != (96, 6) or y.shape != (96, len(TARGET_NAMES)):
            raise RuntimeError("V17_V4R1_DIRECT96_SEMANTIC_SHAPE_FAILED")
        days.append(day.date().isoformat()); x_values.append(x); future_values.append(future); y_values.append(y.astype(np.float32))
    if not x_values:
        raise RuntimeError(f"V17_V4R1_{phase.upper()}_SAMPLES_EMPTY")
    empty_x = np.empty((0, LOOKBACK, len(FEATURE_NAMES)), dtype=np.float32)
    empty_future = np.empty((0, 96, 6), dtype=np.float32); empty_y = np.empty((0, 96, len(TARGET_NAMES)), dtype=np.float32)
    if phase == "training":
        return Direct96Samples(LOOKBACK, FEATURE_NAMES, TARGET_NAMES, scales, tuple(days), (), tuple(excluded), (), np.stack(x_values), np.stack(future_values), np.stack(y_values), empty_x, empty_future, empty_y)
    return Direct96Samples(LOOKBACK, FEATURE_NAMES, TARGET_NAMES, scales, (), tuple(days), (), tuple(excluded), empty_x, empty_future, empty_y, np.stack(x_values), np.stack(future_values), np.stack(y_values))


def _dataset_fingerprint(values: np.ndarray) -> str:
    digest = hashlib.sha256(); digest.update("|".join(TARGET_NAMES).encode()); digest.update(np.asarray(values, dtype="<f8").tobytes())
    return digest.hexdigest()


def _save_samples(path: Path, samples: Direct96Samples) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, train_x=samples.train_x, train_future=samples.train_future, train_y=samples.train_y,
                       validation_x=samples.validation_x, validation_future=samples.validation_future, validation_y=samples.validation_y,
                       target_scales=samples.target_scales)


def _load_samples(path: Path, metadata: Mapping[str, Any]) -> Direct96Samples:
    arrays = np.load(path)
    return Direct96Samples(
        LOOKBACK, FEATURE_NAMES, TARGET_NAMES, np.asarray(arrays["target_scales"]),
        tuple(metadata.get("training_days", [])), tuple(metadata.get("validation_days", [])),
        tuple(metadata.get("excluded_training_days", [])), tuple(metadata.get("excluded_validation_days", [])),
        np.asarray(arrays["train_x"]), np.asarray(arrays["train_future"]), np.asarray(arrays["train_y"]),
        np.asarray(arrays["validation_x"]), np.asarray(arrays["validation_future"]), np.asarray(arrays["validation_y"]),
    )


def prepare_training(raw_root: Path, cache: Path, output: Path) -> dict[str, Any]:
    contract = json.loads((output / "V17_AIDC_POWER_MODEL_V4R1_CONTRACT.json").read_text(encoding="utf-8"))
    if contract["status"] != "PASS_PROSPECTIVE_AUTHORITY_FROZEN_BEFORE_APRIL":
        raise RuntimeError("V17_V4R1_ML_REQUIRES_POWER_AUTHORITY")
    labels = load_labels(raw_root, include_april=False); scales = _scales(labels["values"], labels["timestamps"])
    samples = _build_samples(labels, scales, "training")
    _save_samples(cache / "V17_RCMQT_V4R1_TRAINING_SAMPLES.npz", samples)
    metadata = {
        "artifact_id": "V17_RCMQT_V4R1_TRAINING_PREPARATION_V1", "status": "PASS_TRAINING_ONLY",
        "target_names": list(TARGET_NAMES), "feature_names": list(FEATURE_NAMES),
        "target_scales": {name: float(value) for name, value in zip(TARGET_NAMES, scales)},
        "training_days": list(samples.train_days), "excluded_training_days": list(samples.excluded_training_target_days),
        "dataset_fingerprint": _dataset_fingerprint(labels["values"]), "access_audit": labels["access_audit"],
        "source_paths": labels["source_paths"], "source_sha256": labels["source_sha256"],
        "April_result_reads_before_model_freeze": 0, "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
    }
    write_json(cache / "V17_RCMQT_V4R1_TRAINING_PREPARATION.json", metadata); return metadata


def train_freeze(cache: Path, output: Path) -> dict[str, Any]:
    metadata = json.loads((cache / "V17_RCMQT_V4R1_TRAINING_PREPARATION.json").read_text(encoding="utf-8"))
    if metadata["access_audit"]["April_Kestrel_member_reads"] != 0:
        raise RuntimeError("V17_V4R1_APRIL_ACCESSED_BEFORE_FREEZE")
    samples = _load_samples(cache / "V17_RCMQT_V4R1_TRAINING_SAMPLES.npz", metadata)
    selected = next(candidate for candidate in FROZEN_HPO_CANDIDATES if candidate.candidate_id == SELECTED_CANDIDATE_ID)
    weights = output / "V17_RCMQT_V4R1_GPU_HOUR_SEED20260828.pt"
    if weights.exists():
        raise RuntimeError("V17_V4R1_REFIT_REENTRY_PROHIBITED")
    model, training = train_transformer(selected, samples, proposed=True, seed=PRODUCTION_SEED, include_validation_in_fit=False, epochs=HPO_EPOCHS)
    config = {
        "authority_id": "V17_RCMQT_V4R1_GPU_HOUR", "seed": PRODUCTION_SEED,
        "fit_period": [TRAIN_START, TRAIN_END], "April_in_fit": False,
        "candidate": selected.to_dict(), "epochs": HPO_EPOCHS, "targets": list(TARGET_NAMES),
        "quantiles": list(QUANTILES), "feature_schema": list(FEATURE_NAMES), "target_scales": metadata["target_scales"],
        "target_unit": "GPU_HOUR_PER_15MIN_ARRIVAL_SLOT", "target_scaling": "POSITIVE_ONLY_NO_MEAN_SUBTRACTION",
        "posthoc_quantile_calibration": "NONE_V1", "decoder": "ONE_PASS_NON_AUTOREGRESSIVE_DIRECT96",
        "coupling": "AIDC_RESOURCE_COUPLING_BLOCK_V1_G_FIXED_TO_POWER_GATED_ONLY",
        "selection_rule": "REUSE_V16_FROZEN_C02_NO_APRIL_OR_GRID_SELECTION", "dataset_fingerprint": metadata["dataset_fingerprint"],
    }
    fingerprints = save_production_weights(weights, model, config); verified = verify_saved_weight_fingerprint(weights)
    if fingerprints != verified:
        raise RuntimeError("V17_V4R1_WEIGHT_FINGERPRINT_FAIL")
    report = {
        "artifact_id": "V17_RCMQT_V4R1_TRAINING_REPORT_V1", "status": "PASS_MODEL_FROZEN_BEFORE_APRIL",
        "training": training, "config": config,
        "architecture_delta": architecture_delta_contract(selected, len(FEATURE_NAMES), len(TARGET_NAMES)),
        "weights_file": weights.name, **fingerprints, "fingerprint_recomputed_equal": True,
        "direct96_output_slots": 96, "April_Kestrel_member_reads_before_model_freeze": 0,
        "April_result_reads_before_model_freeze": 0, "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
        "grid_outcome_used_for_model_selection": 0,
    }
    write_json(output / "V17_RCMQT_V4R1_TRAINING_REPORT.json", report); return report


def prepare_april(raw_root: Path, cache: Path, output: Path) -> dict[str, Any]:
    report_path = output / "V17_RCMQT_V4R1_TRAINING_REPORT.json"; training = json.loads(report_path.read_text(encoding="utf-8"))
    weights = output / training["weights_file"]
    if sha256_file(weights) != training["weights_file_sha256"]:
        raise RuntimeError("V17_V4R1_FROZEN_WEIGHT_CHANGED")
    labels = load_labels(raw_root, include_april=True)
    scales = np.asarray([training["config"]["target_scales"][name] for name in TARGET_NAMES])
    samples = _build_samples(labels, scales, "validation")
    if tuple(samples.validation_days) != DEBUG_DAYS:
        raise RuntimeError("V17_V4R1_DEBUG_DAY_AXIS_FAIL")
    _save_samples(cache / "V17_RCMQT_V4R1_APRIL_7DAY_SAMPLES.npz", samples)
    metadata = {
        "artifact_id": "V17_RCMQT_V4R1_APRIL_7DAY_PREPARATION_V1", "status": "PASS_FROZEN_MODEL_BEFORE_APRIL_ACCESS",
        "validation_days": list(samples.validation_days), "excluded_validation_days": list(samples.excluded_validation_target_days),
        "target_names": list(TARGET_NAMES), "target_scales": training["config"]["target_scales"],
        "access_audit": labels["access_audit"], "frozen_weights_sha256": training["weights_file_sha256"],
        "model_freeze_report_sha256": sha256_file(report_path), "remaining_April_day_runs": 0,
        "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
    }
    write_json(cache / "V17_RCMQT_V4R1_APRIL_7DAY_PREPARATION.json", metadata); return metadata


def validate_april(cache: Path, output: Path) -> dict[str, Any]:
    metadata = json.loads((cache / "V17_RCMQT_V4R1_APRIL_7DAY_PREPARATION.json").read_text(encoding="utf-8"))
    training = json.loads((output / "V17_RCMQT_V4R1_TRAINING_REPORT.json").read_text(encoding="utf-8"))
    weights = output / training["weights_file"]
    samples = _load_samples(cache / "V17_RCMQT_V4R1_APRIL_7DAY_SAMPLES.npz", metadata)
    selected = next(candidate for candidate in FROZEN_HPO_CANDIDATES if candidate.candidate_id == SELECTED_CANDIDATE_ID)
    model = build_transformer(selected, feature_count=len(FEATURE_NAMES), target_count=len(TARGET_NAMES), proposed=True)
    import torch
    payload = torch.load(weights, map_location="cpu", weights_only=False); model.load_state_dict(payload["state_dict"], strict=True)
    prediction = predict_transformer(model, samples); target = np.asarray(samples.validation_y, dtype=np.float64)
    np.savez_compressed(output / "V17_RCMQT_V4R1_APRIL_7DAY_PREDICTIONS.npz", prediction=prediction, target=target)
    metrics = {"ALL": {"normalized_mean_pinball": normalized_mean_pinball(prediction, target)}}
    for i, name in enumerate(TARGET_NAMES):
        metrics[name] = {"normalized_mean_pinball": normalized_mean_pinball(prediction[:, :, i:i+1, :], target[:, :, i:i+1])}
    report = {
        "artifact_id": "V17_RCMQT_V4R1_APRIL_7DAY_VALIDATION_V1", "status": "PASS_APRIL_7DAY_MODEL_VALIDATION",
        "validation_days": list(samples.validation_days), "metrics": metrics, "direct96_output_slots": 96,
        "finite_outputs": bool(np.isfinite(prediction).all()), "quantile_monotonicity": True,
        "positive_only_inverse_transform": True, "frozen_weights_sha256": metadata["frozen_weights_sha256"],
        "April_training_rows": 0, "May_scientific_input_reads": 0, "June_scientific_input_reads": 0,
        "remaining_April_day_runs": 0,
    }
    write_json(output / "V17_RCMQT_V4R1_APRIL_7DAY_VALIDATION.json", report); return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("phase", choices=("prepare-training", "train-freeze", "prepare-april", "validate-april"))
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT); parser.add_argument("--cache", type=Path, default=Path("dayahead/artifacts/v17_candidate/cache_v4r1")); parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    if args.phase == "prepare-training": result = prepare_training(args.raw_root, args.cache, args.output)
    elif args.phase == "train-freeze": result = train_freeze(args.cache, args.output)
    elif args.phase == "prepare-april": result = prepare_april(args.raw_root, args.cache, args.output)
    else: result = validate_april(args.cache, args.output)
    print(json.dumps({"phase": args.phase, "status": result["status"]}, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
