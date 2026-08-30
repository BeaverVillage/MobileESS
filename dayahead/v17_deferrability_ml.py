"""Causal Direct96 RC-MQT training and April validation for V17.

The command is intentionally phased.  ``prepare-training`` opens no April
Kestrel member and returns no post-March ESIF row.  ``train-freeze`` reads only
the prepared arrays and writes the immutable model weights.  Only then may
``prepare-april`` and ``validate-april`` open the April validation inputs.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import shutil
import tempfile
import zipfile
from dataclasses import asdict
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
from .aidc_ml_data import AEST, Direct96Samples, NODE_CLASSES, calendar_features
from .authority import DEFAULT_RAW_ROOT, NLR_SOURCE_SHA256, sha256_file
from .reproduce_nlr_authority import object_empty
from .v17_deferrability_semantics import LATENCY_CLASSES, latency_class, write_json


AXIS_START = "2024-08-01"
TRAIN_START = "2024-08-19"
TRAIN_END = "2025-03-31"
TRAIN_END_EXCLUSIVE = "2025-04-01"
APRIL_END_EXCLUSIVE = "2025-05-01"
VALIDATION_START = "2025-04-02"
VALIDATION_END = "2025-04-30"
LOOKBACK = 1344
SELECTED_CANDIDATE_ID = "C02"
TARGET_NAMES = (
    "P_IT_REF",
    "G_FIXED",
    *(
        f"W_F_{latency_name}::N{node_class:02d}"
        for latency_name in LATENCY_CLASSES
        for node_class in NODE_CLASSES
    ),
)
FEATURE_NAMES = (*TARGET_NAMES, "P_IT_REF_observed", "tod_sin", "tod_cos", "dow_sin", "dow_cos", "doy_sin", "doy_cos")


def _find_exact(raw_root: Path, filename: str, expected_sha: str) -> Path:
    exact = [
        path
        for path in sorted(raw_root.rglob(filename))
        if path.is_file() and sha256_file(path) == expected_sha
    ]
    if not exact:
        raise FileNotFoundError(f"EXACT_RAW_SOURCE_NOT_FOUND:{filename}")
    return exact[0]


def _h100(value: object) -> bool:
    return any(token.strip().casefold().startswith("gpu-h100") for token in str(value).split(","))


def _add_interval_average(
    difference: np.ndarray,
    partial: np.ndarray,
    *,
    start_seconds: float,
    end_seconds: float,
    magnitude: float,
    slot_count: int,
) -> None:
    if end_seconds <= 0 or start_seconds >= slot_count * 900:
        return
    start_seconds = max(0.0, start_seconds)
    end_seconds = min(slot_count * 900.0, end_seconds)
    if end_seconds <= start_seconds:
        return
    first = int(start_seconds // 900)
    last = int(math.nextafter(end_seconds, -math.inf) // 900)
    if first == last:
        partial[first] += magnitude * (end_seconds - start_seconds) / 900.0
        return
    partial[first] += magnitude * ((first + 1) * 900.0 - start_seconds) / 900.0
    partial[last] += magnitude * (end_seconds - last * 900.0) / 900.0
    if last > first + 1:
        difference[first + 1] += magnitude
        difference[last] -= magnitude


def _load_esif(path: Path, timestamps: Any) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    import pandas as pd
    import pyarrow.parquet as pq

    frame = pq.read_table(path, columns=["ts", "it_power_kw"]).to_pandas()
    ts = pd.to_datetime(frame["ts"], errors="coerce")
    if getattr(ts.dt, "tz", None) is None:
        ts = ts.dt.tz_localize("UTC")
    else:
        ts = ts.dt.tz_convert("UTC")
    values = pd.to_numeric(frame["it_power_kw"], errors="coerce")
    start_utc = timestamps[0].tz_convert("UTC")
    end_utc = (timestamps[-1] + pd.Timedelta(minutes=15)).tz_convert("UTC")
    keep = ts.ge(start_utc) & ts.lt(end_utc) & values.notna() & np.isfinite(values) & values.ge(0)
    clipped = pd.Series(np.asarray(values[keep], dtype=float), index=pd.DatetimeIndex(ts[keep]))
    quarter_hour = clipped.groupby(clipped.index.floor("15min")).mean()
    quarter_hour.index = quarter_hour.index.tz_convert(AEST)
    result = quarter_hour.reindex(timestamps)
    observed = np.asarray(result.notna(), dtype=bool)
    filled = np.asarray(result, dtype=np.float64).copy()
    for index in np.flatnonzero(~observed):
        same_slot = [
            filled[index - 96 * lag]
            for lag in range(1, 8)
            if index - 96 * lag >= 0 and observed[index - 96 * lag]
        ]
        if same_slot:
            filled[index] = float(np.median(same_slot))
        else:
            prior = np.flatnonzero(observed[:index])
            if not len(prior):
                raise RuntimeError(f"ESIF_CAUSAL_IMPUTATION_NO_PRIOR:{index}")
            filled[index] = float(filled[prior[-1]])
    if not np.isfinite(filled).all():
        raise RuntimeError("ESIF_CAUSAL_IMPUTATION_NONFINITE")
    return filled, observed, {
        "returned_min_timestamp_AEST": timestamps[0].isoformat(),
        "returned_max_timestamp_AEST": timestamps[-1].isoformat(),
        "raw_15min_missing_count": int((~observed).sum()),
        "causal_history_imputation_count": int((~observed).sum()),
    }


def _load_semantic_kestrel(path: Path, timestamps: Any, max_month: int) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    import pandas as pd
    import pyarrow.parquet as pq

    required = {
        "partition", "state_simple", "submit_time", "start_time", "end_time",
        "gpu_nodes_occupied", "gpus_requested", "shared_job_count", "nodes_shared",
        "jobs_shared",
    }
    retained: list[Any] = []
    members: list[str] = []
    with zipfile.ZipFile(path) as archive, tempfile.TemporaryDirectory(prefix="v17-rcmqt-labels-") as temporary:
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
                raise RuntimeError(f"KESTREL_REQUIRED_SCHEMA_MISSING:{sorted(required-schema)}")
            retained.append(pq.read_table(local, columns=sorted(required)).to_pandas())
            members.append(info.filename)
    if not retained:
        raise RuntimeError("KESTREL_LABEL_MEMBERS_EMPTY")
    frame = pd.concat(retained, ignore_index=True)
    submit = pd.to_datetime(frame["submit_time"], utc=True, errors="coerce", format="mixed")
    start = pd.to_datetime(frame["start_time"], utc=True, errors="coerce", format="mixed")
    end = pd.to_datetime(frame["end_time"], utc=True, errors="coerce", format="mixed")
    nodes = pd.to_numeric(frame["gpu_nodes_occupied"], errors="coerce")
    gpus = pd.to_numeric(frame["gpus_requested"], errors="coerce")
    sharing = pd.to_numeric(frame["shared_job_count"], errors="coerce")
    queue_seconds = (start - submit).dt.total_seconds()
    valid = (
        frame["partition"].apply(_h100)
        & frame["state_simple"].astype(str).str.upper().eq("COMPLETED")
        & submit.notna() & start.notna() & end.notna() & end.gt(start)
        & nodes.gt(0) & gpus.gt(0) & queue_seconds.ge(0) & np.isfinite(queue_seconds)
    )
    no_share = (
        (sharing.isna() | sharing.eq(0))
        & frame["nodes_shared"].apply(object_empty)
        & frame["jobs_shared"].apply(object_empty)
    )
    modelable = valid & nodes.isin(NODE_CLASSES) & np.isclose(gpus, 4.0 * nodes) & no_share
    classes = queue_seconds.apply(lambda value: latency_class(float(value)) if pd.notna(value) else None)
    fixed = modelable & classes.eq("FIXED")
    slot_count = len(timestamps)
    origin = timestamps[0].tz_convert("UTC").timestamp()
    difference = np.zeros(slot_count + 1, dtype=np.float64)
    partial = np.zeros(slot_count, dtype=np.float64)
    for index in np.flatnonzero(np.asarray(fixed, dtype=bool)):
        _add_interval_average(
            difference,
            partial,
            start_seconds=start.iloc[index].timestamp() - origin,
            end_seconds=end.iloc[index].timestamp() - origin,
            magnitude=float(nodes.iloc[index]),
            slot_count=slot_count,
        )
    g_fixed = partial + np.cumsum(difference[:-1])
    workload = np.zeros((slot_count, len(LATENCY_CLASSES) * len(NODE_CLASSES)), dtype=np.float64)
    target_index = {
        (name, node): index
        for index, (name, node) in enumerate(
            (pair for name in LATENCY_CLASSES for pair in ((name, node) for node in NODE_CLASSES))
        )
    }
    flexible = modelable & classes.isin(LATENCY_CLASSES)
    for index in np.flatnonzero(np.asarray(flexible, dtype=bool)):
        slot = int((submit.iloc[index].timestamp() - origin) // 900)
        if 0 <= slot < slot_count:
            runtime_hours = float((end.iloc[index] - start.iloc[index]).total_seconds() / 3600.0)
            workload[slot, target_index[(str(classes.iloc[index]), int(nodes.iloc[index]))]] += float(nodes.iloc[index]) * runtime_hours
    if np.any(g_fixed < -1e-12) or np.any(workload < -1e-12):
        raise RuntimeError("SEMANTIC_LABEL_NEGATIVE")
    return g_fixed, workload, {
        "members_opened": members,
        "max_member_month_opened": max_month,
        "modelable_jobs": int(modelable.sum()),
        "fixed_jobs": int(fixed.sum()),
        "flexible_jobs": int(flexible.sum()),
        "future_individual_job_expost_inference_reads": 0,
    }


def load_labels(raw_root: Path, *, include_april: bool) -> dict[str, Any]:
    import pandas as pd

    end_exclusive = APRIL_END_EXCLUSIVE if include_april else TRAIN_END_EXCLUSIVE
    max_month = 202504 if include_april else 202503
    timestamps = pd.date_range(
        pd.Timestamp(AXIS_START, tz=AEST),
        pd.Timestamp(end_exclusive, tz=AEST),
        freq="15min",
        inclusive="left",
    )
    esif = _find_exact(raw_root, "esif.influx.buildingData.PUE.combined.parquet", NLR_SOURCE_SHA256["esif_parquet"])
    kestrel = _find_exact(raw_root, "esif.hpc.kestrel.job-anon.zip", NLR_SOURCE_SHA256["kestrel_jobs_zip"])
    p_it, p_observed, esif_audit = _load_esif(esif, timestamps)
    g_fixed, workload, kestrel_audit = _load_semantic_kestrel(kestrel, timestamps, max_month)
    values = np.column_stack((p_it, g_fixed, workload))
    if values.shape != (len(timestamps), len(TARGET_NAMES)) or not np.isfinite(values).all() or np.any(values < 0):
        raise RuntimeError("V17_LABEL_MATRIX_INVALID")
    return {
        "timestamps": timestamps,
        "values": values,
        "p_observed": p_observed,
        "source_paths": {"esif": str(esif.resolve()), "kestrel": str(kestrel.resolve())},
        "source_sha256": {"esif": sha256_file(esif), "kestrel": sha256_file(kestrel)},
        "access_audit": {
            "include_april": include_april,
            "April_Kestrel_member_reads": 1 if include_april else 0,
            "April_result_reads": 0,
            "May_scientific_input_reads": 0,
            "June_scientific_input_reads": 0,
            "esif": esif_audit,
            "kestrel": kestrel_audit,
        },
    }


def _scales(values: np.ndarray, timestamps: Any) -> np.ndarray:
    import pandas as pd

    train = values[(timestamps >= pd.Timestamp(TRAIN_START, tz=AEST)) & (timestamps < pd.Timestamp(TRAIN_END_EXCLUSIVE, tz=AEST))]
    result = np.ones(values.shape[1], dtype=np.float64)
    for index in range(values.shape[1]):
        positive = train[:, index][train[:, index] > 0]
        if positive.size:
            result[index] = max(float(np.quantile(positive, 0.95)), 1e-6)
    if np.any(result <= 0) or not np.isfinite(result).all():
        raise RuntimeError("V17_TARGET_SCALE_INVALID")
    return result


def _build_samples(labels: Mapping[str, Any], scales: np.ndarray, *, phase: str) -> Direct96Samples:
    import pandas as pd

    timestamps = labels["timestamps"]
    values = np.asarray(labels["values"], dtype=np.float64)
    scaled = values / scales
    features = np.column_stack((scaled, np.asarray(labels["p_observed"], dtype=np.float32)[:, None], calendar_features(timestamps))).astype(np.float32)
    lookup = {timestamp: index for index, timestamp in enumerate(timestamps)}
    x_values: list[np.ndarray] = []
    future_values: list[np.ndarray] = []
    y_values: list[np.ndarray] = []
    days: list[str] = []
    excluded: list[str] = []
    if phase == "training":
        day_axis = pd.date_range(TRAIN_START, TRAIN_END, freq="D")
    elif phase == "validation":
        day_axis = pd.date_range(VALIDATION_START, VALIDATION_END, freq="D")
    else:
        raise ValueError("UNKNOWN_SAMPLE_PHASE")
    calendar = calendar_features(timestamps)
    for day in day_axis:
        day_start = pd.Timestamp(day.date(), tz=AEST)
        cutoff = day_start - pd.Timedelta(hours=6)
        history_start = cutoff - pd.Timedelta(minutes=15 * LOOKBACK)
        first = lookup.get(history_start)
        cutoff_index = lookup.get(cutoff)
        target_first = lookup.get(day_start)
        if first is None or cutoff_index is None or target_first is None:
            raise RuntimeError(f"DIRECT96_AXIS_LOOKUP_FAILED:{day.date()}")
        target_end = target_first + 96
        if not bool(np.asarray(labels["p_observed"][target_first:target_end]).all()):
            excluded.append(day.date().isoformat())
            continue
        x = features[first:cutoff_index]
        future = calendar[target_first:target_end]
        y = scaled[target_first:target_end]
        if x.shape != (LOOKBACK, len(FEATURE_NAMES)) or future.shape != (96, 6) or y.shape != (96, len(TARGET_NAMES)):
            raise RuntimeError("DIRECT96_SEMANTIC_SHAPE_FAILED")
        days.append(day.date().isoformat())
        x_values.append(x)
        future_values.append(future)
        y_values.append(y.astype(np.float32))
    if not x_values:
        raise RuntimeError(f"DIRECT96_{phase.upper()}_SAMPLES_EMPTY")
    x_array = np.stack(x_values)
    future_array = np.stack(future_values)
    y_array = np.stack(y_values)
    empty_x = np.empty((0, LOOKBACK, len(FEATURE_NAMES)), dtype=np.float32)
    empty_future = np.empty((0, 96, 6), dtype=np.float32)
    empty_y = np.empty((0, 96, len(TARGET_NAMES)), dtype=np.float32)
    if phase == "training":
        return Direct96Samples(LOOKBACK, FEATURE_NAMES, TARGET_NAMES, scales, tuple(days), (), tuple(excluded), (), x_array, future_array, y_array, empty_x, empty_future, empty_y)
    return Direct96Samples(LOOKBACK, FEATURE_NAMES, TARGET_NAMES, scales, (), tuple(days), (), tuple(excluded), empty_x, empty_future, empty_y, x_array, future_array, y_array)


def _dataset_fingerprint(values: np.ndarray) -> str:
    digest = hashlib.sha256()
    digest.update("|".join(TARGET_NAMES).encode("utf-8"))
    digest.update(np.asarray(values, dtype="<f8").tobytes(order="C"))
    return digest.hexdigest()


def _save_samples(path: Path, samples: Direct96Samples) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        train_x=np.asarray(samples.train_x), train_future=np.asarray(samples.train_future), train_y=np.asarray(samples.train_y),
        validation_x=np.asarray(samples.validation_x), validation_future=np.asarray(samples.validation_future), validation_y=np.asarray(samples.validation_y),
        target_scales=np.asarray(samples.target_scales),
    )


def _load_samples(path: Path, metadata: Mapping[str, Any]) -> Direct96Samples:
    arrays = np.load(path)
    return Direct96Samples(
        LOOKBACK, FEATURE_NAMES, TARGET_NAMES, np.asarray(arrays["target_scales"]),
        tuple(metadata.get("training_days", [])), tuple(metadata.get("validation_days", [])),
        tuple(metadata.get("excluded_training_days", [])), tuple(metadata.get("excluded_validation_days", [])),
        np.asarray(arrays["train_x"]), np.asarray(arrays["train_future"]), np.asarray(arrays["train_y"]),
        np.asarray(arrays["validation_x"]), np.asarray(arrays["validation_future"]), np.asarray(arrays["validation_y"]),
    )


def prepare_training(raw_root: Path, cache: Path) -> dict[str, Any]:
    labels = load_labels(raw_root, include_april=False)
    scales = _scales(np.asarray(labels["values"]), labels["timestamps"])
    samples = _build_samples(labels, scales, phase="training")
    _save_samples(cache / "V17_RCMQT_V2_TRAINING_SAMPLES.npz", samples)
    metadata = {
        "artifact_id": "V17_RCMQT_V2_TRAINING_PREPARATION",
        "status": "PASS_TRAINING_ONLY",
        "target_names": list(TARGET_NAMES),
        "feature_names": list(FEATURE_NAMES),
        "target_scales": {name: float(value) for name, value in zip(TARGET_NAMES, scales)},
        "training_days": list(samples.train_days),
        "excluded_training_days": list(samples.excluded_training_target_days),
        "dataset_fingerprint": _dataset_fingerprint(np.asarray(labels["values"])),
        "access_audit": labels["access_audit"],
        "source_paths": labels["source_paths"],
        "source_sha256": labels["source_sha256"],
        "April_result_reads_before_model_freeze": 0,
    }
    write_json(cache / "V17_RCMQT_V2_TRAINING_PREPARATION.json", metadata)
    return metadata


def train_freeze(cache: Path, output: Path) -> dict[str, Any]:
    metadata = json.loads((cache / "V17_RCMQT_V2_TRAINING_PREPARATION.json").read_text(encoding="utf-8"))
    if metadata["access_audit"]["April_Kestrel_member_reads"] != 0:
        raise RuntimeError("APRIL_INPUT_ACCESSED_BEFORE_MODEL_FREEZE")
    samples = _load_samples(cache / "V17_RCMQT_V2_TRAINING_SAMPLES.npz", metadata)
    selected = next(candidate for candidate in FROZEN_HPO_CANDIDATES if candidate.candidate_id == SELECTED_CANDIDATE_ID)
    weights = output / "V17_RCMQT_V2_TRAINING_ONLY_SEED20260828.pt"
    if weights.exists():
        raise RuntimeError("V17_RCMQT_V2_REFIT_REENTRY_PROHIBITED")
    model, training = train_transformer(selected, samples, proposed=True, seed=PRODUCTION_SEED, include_validation_in_fit=False, epochs=HPO_EPOCHS)
    config = {
        "authority_id": "V17_RCMQT_V2_REVEALED_LATENCY_COHERENT",
        "model": "Proposed AIDC RC-MQT V2",
        "seed": PRODUCTION_SEED,
        "fit_period": [TRAIN_START, TRAIN_END],
        "April_in_fit": False,
        "candidate": selected.to_dict(),
        "epochs": HPO_EPOCHS,
        "targets": list(TARGET_NAMES),
        "aggregate_workload_targets": [f"W_F_{name}" for name in LATENCY_CLASSES],
        "quantiles": list(QUANTILES),
        "feature_schema": list(FEATURE_NAMES),
        "target_scales": metadata["target_scales"],
        "target_scaling": "POSITIVE_ONLY_NO_MEAN_SUBTRACTION",
        "posthoc_quantile_calibration": "NONE_V1",
        "decoder": "ONE_PASS_NON_AUTOREGRESSIVE_DIRECT96",
        "coupling": "AIDC_RESOURCE_COUPLING_BLOCK_V1_G_FIXED_TO_POWER_GATED_ONLY",
        "dataset_fingerprint": metadata["dataset_fingerprint"],
        "selection_rule": "REUSE_V16_FROZEN_C02_NO_APRIL_MODEL_SELECTION",
    }
    output.mkdir(parents=True, exist_ok=True)
    fingerprints = save_production_weights(weights, model, config)
    verified = verify_saved_weight_fingerprint(weights)
    if fingerprints != verified:
        raise RuntimeError("V17_WEIGHT_FINGERPRINT_REPRODUCTION_FAILED")
    delta = architecture_delta_contract(selected, len(FEATURE_NAMES), len(TARGET_NAMES))
    report = {
        "artifact_id": "V17_RCMQT_V2_TRAINING_REPORT_V1",
        "status": "PASS_MODEL_FROZEN_BEFORE_APRIL",
        "training": training,
        "config": config,
        "architecture_delta": delta,
        "weights_file": weights.name,
        **fingerprints,
        "fingerprint_recomputed_equal": fingerprints == verified,
        "direct96_output_slots": 96,
        "future_expost_field_inference_reads": 0,
        "April_result_reads_before_model_freeze": 0,
        "April_Kestrel_member_reads_before_model_freeze": 0,
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "effect_tuning_calls": 0,
    }
    write_json(output / "V17_RCMQT_V2_TRAINING_REPORT.json", report)
    return report


def prepare_april(raw_root: Path, cache: Path, output: Path) -> dict[str, Any]:
    training_report_path = output / "V17_RCMQT_V2_TRAINING_REPORT.json"
    weights = output / "V17_RCMQT_V2_TRAINING_ONLY_SEED20260828.pt"
    if not training_report_path.is_file() or not weights.is_file():
        raise RuntimeError("APRIL_ACCESS_REQUIRES_FROZEN_MODEL")
    training = json.loads(training_report_path.read_text(encoding="utf-8"))
    if sha256_file(weights) != training["weights_file_sha256"]:
        raise RuntimeError("FROZEN_MODEL_CHANGED_BEFORE_APRIL")
    labels = load_labels(raw_root, include_april=True)
    scales = np.asarray([training["config"]["target_scales"][name] for name in TARGET_NAMES], dtype=np.float64)
    samples = _build_samples(labels, scales, phase="validation")
    _save_samples(cache / "V17_RCMQT_V2_APRIL_VALIDATION_SAMPLES.npz", samples)
    metadata = {
        "artifact_id": "V17_RCMQT_V2_APRIL_VALIDATION_PREPARATION",
        "status": "PASS_MODEL_WAS_FROZEN_BEFORE_APRIL_ACCESS",
        "validation_days": list(samples.validation_days),
        "excluded_validation_days": list(samples.excluded_validation_target_days),
        "target_names": list(TARGET_NAMES),
        "target_scales": training["config"]["target_scales"],
        "access_audit": labels["access_audit"],
        "frozen_weights_sha256": training["weights_file_sha256"],
        "model_freeze_report_sha256": sha256_file(training_report_path),
        "April_result_reads_before_model_freeze": 0,
    }
    write_json(cache / "V17_RCMQT_V2_APRIL_VALIDATION_PREPARATION.json", metadata)
    return metadata


def validate_april(cache: Path, output: Path) -> dict[str, Any]:
    metadata = json.loads((cache / "V17_RCMQT_V2_APRIL_VALIDATION_PREPARATION.json").read_text(encoding="utf-8"))
    training = json.loads((output / "V17_RCMQT_V2_TRAINING_REPORT.json").read_text(encoding="utf-8"))
    weights = output / training["weights_file"]
    if sha256_file(weights) != metadata["frozen_weights_sha256"]:
        raise RuntimeError("FROZEN_MODEL_CHANGED_DURING_APRIL_VALIDATION")
    samples = _load_samples(cache / "V17_RCMQT_V2_APRIL_VALIDATION_SAMPLES.npz", metadata)
    selected = next(candidate for candidate in FROZEN_HPO_CANDIDATES if candidate.candidate_id == SELECTED_CANDIDATE_ID)
    model = build_transformer(selected, feature_count=len(FEATURE_NAMES), target_count=len(TARGET_NAMES), proposed=True)
    import torch
    payload = torch.load(weights, map_location="cpu", weights_only=False)
    model.load_state_dict(payload["state_dict"], strict=True)
    if torch.cuda.is_available():
        model = model.to(torch.device("cuda"))
    prediction = predict_transformer(model, samples)
    target = np.asarray(samples.validation_y, dtype=np.float64)
    if prediction.shape != (len(samples.validation_days), 96, len(TARGET_NAMES), 3):
        raise RuntimeError("V17_APRIL_DIRECT96_SHAPE")
    if np.any(prediction[..., 0] > prediction[..., 1]) or np.any(prediction[..., 1] > prediction[..., 2]):
        raise RuntimeError("V17_APRIL_QUANTILE_ORDER")
    np.savez_compressed(output / "V17_RCMQT_V2_APRIL_PREDICTIONS.npz", prediction=prediction, target=target)
    metrics: dict[str, Any] = {
        "ALL": {"normalized_mean_pinball": normalized_mean_pinball(prediction, target)},
        "P_IT_REF": {"normalized_mean_pinball": normalized_mean_pinball(prediction[:, :, 0:1, :], target[:, :, 0:1])},
        "G_FIXED": {"normalized_mean_pinball": normalized_mean_pinball(prediction[:, :, 1:2, :], target[:, :, 1:2])},
    }
    for class_index, name in enumerate(LATENCY_CLASSES):
        first = 2 + class_index * len(NODE_CLASSES)
        last = first + len(NODE_CLASSES)
        metrics[f"W_F_{name}"] = {"normalized_mean_pinball": normalized_mean_pinball(prediction[:, :, first:last, :], target[:, :, first:last])}
    report = {
        "artifact_id": "V17_RCMQT_V2_APRIL_MODEL_VALIDATION_V1",
        "status": "PASS_APRIL_MODEL_VALIDATION",
        "validation_days": list(samples.validation_days),
        "excluded_days": list(samples.excluded_validation_target_days),
        "validation_day_count": len(samples.validation_days),
        "metrics": metrics,
        "direct96_output_slots": 96,
        "finite_outputs": bool(np.isfinite(prediction).all()),
        "quantile_monotonicity": True,
        "positive_only_inverse_transform": True,
        "frozen_weights_sha256": metadata["frozen_weights_sha256"],
        "April_result_reads_before_model_freeze": 0,
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
    }
    write_json(output / "V17_RCMQT_V2_APRIL_MODEL_VALIDATION.json", report)
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("prepare-training", "train-freeze", "prepare-april", "validate-april"))
    parser.add_argument("--raw-root", type=Path, default=DEFAULT_RAW_ROOT)
    parser.add_argument("--cache", type=Path, default=Path("dayahead/artifacts/v17_candidate/cache"))
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    if args.phase == "prepare-training":
        result = prepare_training(args.raw_root, args.cache)
    elif args.phase == "train-freeze":
        result = train_freeze(args.cache, args.output)
    elif args.phase == "prepare-april":
        result = prepare_april(args.raw_root, args.cache, args.output)
    else:
        result = validate_april(args.cache, args.output)
    print(json.dumps({"phase": args.phase, "status": result["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

