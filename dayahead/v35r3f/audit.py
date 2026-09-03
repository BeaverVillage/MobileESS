"""Low-level, deterministic Dataset 312 audit helpers."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .contracts import (
    GAP_FACTOR,
    GPU_FIELDS_MW,
    GPU_TEMP_FIELDS_C,
    GPUS_PER_NODE,
    RAPL_CORE_FIELDS_W,
    RAPL_PACKAGE_FIELDS_W,
    SENSOR_LIMIT_W,
)


DATETIME_FORMAT = "%Y-%m-%d_%H:%M:%S.%f"
NVML_COLUMNS = ("timestamp", "reading-time[ns]", *GPU_FIELDS_MW, *GPU_TEMP_FIELDS_C)
RAPL_COLUMNS = (
    "timestamp",
    "reading-time[ns]",
    "cpu-0[uJ]",
    "cpu-0-core[uJ]",
    "cpu-1[uJ]",
    "cpu-1-core[uJ]",
    "cpu-0[W]",
    "cpu-0-core[W]",
    "cpu-1[W]",
    "cpu-1-core[W]",
)
SLURM_RE = re.compile(r"slurmid_(\d+)")
NODE_RE = re.compile(r"_node_(.+?)\.log$")
NODE_COUNT_RE = re.compile(r"(?:^|/)(1|2|4|8|16)node(?:/|$)")
RESULT_RE = re.compile(r"/results/(\d{6})\.parquet$")


def git(path: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), *args],
        text=True,
        encoding="utf-8",
        errors="replace",
    ).strip()


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def filesystem_path(path: Path) -> str:
    """Return a Windows extended-length path when required."""

    value = os.fspath(path.resolve())
    if os.name == "nt" and not value.startswith("\\\\?\\"):
        value = "\\\\?\\" + value
    return value


def file_size(path: Path) -> int:
    return int(os.stat(filesystem_path(path)).st_size)


def write_json(path: Path, value: Mapping[str, Any] | Sequence[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=json_default)
        + "\n",
        encoding="utf-8",
    )


def write_csv(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields: list[str] = []
    for row in rows:
        for field in row:
            if field not in fields:
                fields.append(field)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for raw in rows:
            row = dict(raw)
            for field, value in row.items():
                if isinstance(value, (dict, list, tuple, set)):
                    row[field] = json.dumps(value, ensure_ascii=False, sort_keys=True, default=json_default)
            writer.writerow(row)


def json_default(value: Any) -> Any:
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return None if not np.isfinite(value) else float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp, pd.Timedelta, Path)):
        return str(value)
    raise TypeError(f"Cannot serialize {type(value)!r}")


def source_category(relative_path: str) -> str:
    top = relative_path.replace("\\", "/").split("/", 1)[0]
    return {
        "00_raw_datasets": "raw",
        "01_aggregated_datasets": "aggregated",
        "02_analysis_scripts": "analysis",
        "03_whole-facility_profiles": "whole-facility",
    }.get(top, "repository-metadata")


def workload_identity(relative_path: str) -> tuple[str | None, str | None, str | None]:
    path = relative_path.lower().replace("\\", "/")
    if "inference_offline_llama3_70b" in path:
        return "INFERENCE_OFFLINE", "LLAMA3_70B", "LLM"
    if "inference_online_finite_llama3_70b" in path:
        return "INFERENCE_ONLINE_FINITE", "LLAMA3_70B", "LLM"
    if "inference_online_rate_llama3_70b" in path:
        return "INFERENCE_ONLINE_RATE", "LLAMA3_70B", "LLM"
    if "training_llama2_70b_lora" in path:
        return "FINE_TUNING_LORA", "LLAMA2_70B", "LLM"
    if "training_stable_diffusion" in path:
        return "TRAINING", "STABLE_DIFFUSION_V2", "DIFFUSION"
    if source_category(path) == "whole-facility":
        return "SYNTHETIC_FACILITY_PROFILE", None, None
    return None, None, None


def apparent_role(relative_path: str) -> str:
    path = relative_path.lower().replace("\\", "/")
    name = path.rsplit("/", 1)[-1]
    if "/00_raw_datasets/" in f"/{path}" and "nvml_wattameter" in name:
        return "raw_nvml_gpu_power_temperature_log"
    if "/00_raw_datasets/" in f"/{path}" and "rapl_wattameter" in name:
        return "raw_rapl_cpu_energy_power_log"
    if name == "metadata.csv":
        return "experiment_metadata"
    if "/results/" in path and name.endswith(".parquet"):
        return "dataset_supplied_resampled_component_sum_profile"
    if name == "postprocess.py":
        return "dataset_supplied_aggregation_script"
    if name.endswith(".ipynb"):
        return "dataset_supplied_analysis_notebook"
    if name.endswith(".png"):
        return "dataset_supplied_plot"
    if "/simulated_data/" in path:
        return "synthetic_whole_facility_profile"
    if name in {"config.json", "log.json", "log_vllm.json"}:
        return "experiment_configuration_or_benchmark_log"
    if name.endswith(".log"):
        return "auxiliary_benchmark_log"
    if name.endswith(".py"):
        return "dataset_supplied_analysis_utility"
    return "repository_or_documentation_file"


def inventory_record(relative_path: str, size: int, compressed_size: int | None = None) -> dict[str, Any]:
    normalized = relative_path.replace("\\", "/").lstrip("./")
    role = apparent_role(normalized)
    workload, model, family = workload_identity(normalized)
    node_match = NODE_COUNT_RE.search(normalized)
    nodes = int(node_match.group(1)) if node_match else (1 if "inference_" in normalized else None)
    slurm_match = SLURM_RE.search(normalized)
    result_match = RESULT_RE.search("/" + normalized)
    source = (
        "NVML"
        if "raw_nvml" in role
        else "RAPL"
        if "raw_rapl" in role
        else "DATASET_SUPPLIED_RESAMPLED"
        if "resampled" in role
        else "DIPLOEE_SYNTHETIC"
        if "synthetic_whole" in role
        else "NOT_APPLICABLE"
    )
    timestamp = role in {
        "raw_nvml_gpu_power_temperature_log",
        "raw_rapl_cpu_energy_power_log",
        "dataset_supplied_resampled_component_sum_profile",
        "synthetic_whole_facility_profile",
        "experiment_metadata",
    }
    return {
        "relative_path": normalized,
        "file_size_bytes": int(size),
        "compressed_size_bytes": compressed_size,
        "extension": Path(normalized).suffix.lower() or "<none>",
        "apparent_role": role,
        "category": source_category(normalized),
        "workload_identity": workload,
        "model_identity": model,
        "model_family": family,
        "experiment_identity": slurm_match.group(1) if slurm_match else result_match.group(1) if result_match else None,
        "node_count": nodes,
        "gpus_per_node": GPUS_PER_NODE if nodes and workload else None,
        "total_gpu_count": nodes * GPUS_PER_NODE if nodes and workload else None,
        "repetition_index": None,
        "sampling_source": source,
        "timestamp_available": timestamp,
    }


def archive_inventory(archive_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with zipfile.ZipFile(archive_path) as archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        rows = [inventory_record(info.filename, info.file_size, info.compress_size) for info in infos]
    rows.sort(key=lambda row: row["relative_path"])
    categories = pd.Series([row["category"] for row in rows]).value_counts().sort_index()
    roles = pd.Series([row["apparent_role"] for row in rows]).value_counts().sort_index()
    return rows, {
        "archive_file_count": len(rows),
        "archive_uncompressed_file_bytes": int(sum(row["file_size_bytes"] for row in rows)),
        "archive_compressed_member_bytes": int(sum(row["compressed_size_bytes"] or 0 for row in rows)),
        "category_counts": {str(key): int(value) for key, value in categories.items()},
        "role_counts": {str(key): int(value) for key, value in roles.items()},
        "inventory_scope": "ALL_NON_DIRECTORY_ZIP_MEMBERS",
    }


def read_power_log(path: Path) -> tuple[str, pd.DataFrame]:
    device = "NVML" if path.name.startswith("nvml_") else "RAPL" if path.name.startswith("rapl_") else "UNKNOWN"
    if device == "UNKNOWN":
        raise ValueError(f"Not a power log: {path}")
    columns = NVML_COLUMNS if device == "NVML" else RAPL_COLUMNS
    input_path = filesystem_path(path)
    frame = pd.read_csv(
        input_path,
        sep=r"\s+",
        comment="#",
        header=None,
        names=list(columns),
        engine="c",
        low_memory=False,
    )
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], format=DATETIME_FORMAT, errors="coerce")
    for column in columns[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return device, frame


def _dt_seconds(timestamps: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    values = pd.DatetimeIndex(timestamps).asi8
    if len(values) < 2:
        return np.array([], dtype=float)
    return np.diff(values).astype(float) / 1e9


def audit_timebase(relative_path: str, device: str, frame: pd.DataFrame) -> dict[str, Any]:
    timestamps = frame["timestamp"]
    valid = timestamps.dropna()
    delta = _dt_seconds(valid)
    positive = delta[delta > 0]
    nominal = float(np.median(positive)) if len(positive) else math.nan
    gaps = delta > nominal * GAP_FACTOR if np.isfinite(nominal) else np.zeros(len(delta), dtype=bool)
    return {
        "relative_path": relative_path,
        "measurement_family": device,
        "sample_count": int(len(frame)),
        "timestamp_valid_count": int(timestamps.notna().sum()),
        "start_timestamp": valid.min().isoformat() if len(valid) else None,
        "end_timestamp": valid.max().isoformat() if len(valid) else None,
        "duration_seconds": float((valid.max() - valid.min()).total_seconds()) if len(valid) > 1 else 0.0,
        "nominal_sampling_period_seconds": nominal,
        "median_dt_seconds": float(np.median(positive)) if len(positive) else math.nan,
        "p05_dt_seconds": float(np.quantile(positive, 0.05)) if len(positive) else math.nan,
        "p95_dt_seconds": float(np.quantile(positive, 0.95)) if len(positive) else math.nan,
        "max_gap_seconds": float(np.max(positive)) if len(positive) else math.nan,
        "duplicate_timestamp_count": int(np.sum(delta == 0)),
        "non_monotonic_timestamp_count": int(np.sum(delta < 0)),
        "missing_or_gap_count": int(np.sum(gaps)),
        "unparseable_timestamp_count": int(timestamps.isna().sum()),
        "timezone_convention": "NAIVE_LOCAL_Kestrel_TIMEZONE_NOT_EMBEDDED_UNKNOWN",
    }


def power_columns(device: str) -> tuple[str, ...]:
    return GPU_FIELDS_MW if device == "NVML" else (*RAPL_PACKAGE_FIELDS_W, *RAPL_CORE_FIELDS_W)


def audit_quality(relative_path: str, device: str, frame: pd.DataFrame) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    scale = 1e-3 if device == "NVML" else 1.0
    for column in power_columns(device):
        values = frame[column].to_numpy(dtype=float) * scale
        finite = np.isfinite(values)
        diff = np.abs(np.diff(values[finite])) if np.sum(finite) > 1 else np.array([], dtype=float)
        threshold = max(300.0, float(np.quantile(diff, 0.999)) if len(diff) else 300.0)
        invalid = ~finite | (values < 0) | (values > SENSOR_LIMIT_W)
        result.append(
            {
                "relative_path": relative_path,
                "measurement_family": device,
                "field": column,
                "unit_normalized": "W",
                "sample_count": int(len(values)),
                "nan_count": int(np.isnan(values).sum()),
                "inf_count": int(np.isinf(values).sum()),
                "negative_count": int(np.sum(finite & (values < 0))),
                "zero_count": int(np.sum(finite & (values == 0))),
                "above_800W_sensor_limit_count": int(np.sum(finite & (values > SENSOR_LIMIT_W))),
                "large_discontinuity_count_diagnostic": int(np.sum(diff > threshold)),
                "large_discontinuity_threshold_W": threshold,
                "classification": "SENSOR_INVALID_PRESENT" if np.sum(invalid) else "VALID_EXTREME_RETAINED" if len(values) else "STRUCTURAL_INVALID",
                "exclusion_action": "EXCLUDE_ONLY_NONFINITE_NEGATIVE_OR_ABOVE_800W_SAMPLES",
            }
        )
    return result


def clean_power(values: pd.Series, scale: float = 1.0) -> pd.Series:
    result = pd.to_numeric(values, errors="coerce").astype(float) * scale
    result[(~np.isfinite(result)) | (result < 0) | (result > SENSOR_LIMIT_W)] = np.nan
    return result


def component_series(device: str, frame: pd.DataFrame) -> dict[str, pd.Series]:
    valid = frame["timestamp"].notna()
    timestamps = pd.DatetimeIndex(frame.loc[valid, "timestamp"])
    if device == "NVML":
        clean = pd.concat([clean_power(frame.loc[valid, field], 1e-3) for field in GPU_FIELDS_MW], axis=1)
        clean.index = timestamps
        return {"GPU_ONLY_POWER": clean.sum(axis=1, min_count=len(GPU_FIELDS_MW))}
    package = pd.concat([clean_power(frame.loc[valid, field]) for field in RAPL_PACKAGE_FIELDS_W], axis=1)
    core = pd.concat([clean_power(frame.loc[valid, field]) for field in RAPL_CORE_FIELDS_W], axis=1)
    package.index = timestamps
    core.index = timestamps
    return {
        "RAPL_PACKAGE_POWER": package.sum(axis=1, min_count=len(RAPL_PACKAGE_FIELDS_W)),
        "RAPL_CORE_SUBDOMAIN_POWER": core.sum(axis=1, min_count=len(RAPL_CORE_FIELDS_W)),
    }


def collapse_duplicate_index(series: pd.Series) -> pd.Series:
    series = series.loc[series.index.notna()].sort_index()
    if series.index.has_duplicates:
        series = series.groupby(level=0, sort=True).mean()
    return series


def align_and_sum(series_list: Sequence[pd.Series], dt_seconds: float) -> pd.Series:
    prepared = [collapse_duplicate_index(series.dropna()) for series in series_list if len(series.dropna())]
    if not prepared:
        return pd.Series(dtype=float)
    start = max(series.index[0] for series in prepared)
    end = min(series.index[-1] for series in prepared)
    if end < start:
        return pd.Series(dtype=float)
    count = int(math.floor((end - start).total_seconds() / dt_seconds)) + 1
    target_ns = start.value + np.arange(count, dtype=np.int64) * int(round(dt_seconds * 1e9))
    total = np.zeros(count, dtype=float)
    coverage = np.ones(count, dtype=bool)
    for series in prepared:
        source_x = series.index.asi8.astype(np.int64)
        source_y = series.to_numpy(dtype=float)
        valid = np.isfinite(source_y)
        if np.sum(valid) < 2:
            coverage[:] = False
            continue
        total += np.interp(target_ns, source_x[valid], source_y[valid])
        coverage &= (target_ns >= source_x[valid][0]) & (target_ns <= source_x[valid][-1])
    output = pd.Series(total[coverage], index=pd.to_datetime(target_ns[coverage]))
    output.index.name = "timestamp"
    return output


def integrate_series_wh(series: pd.Series) -> float:
    clean = collapse_duplicate_index(series.dropna())
    if len(clean) < 2:
        return 0.0
    seconds = (clean.index.asi8 - clean.index.asi8[0]).astype(float) / 1e9
    return float(np.trapz(clean.to_numpy(dtype=float), seconds) / 3600.0)


def profile_statistics(
    experiment_id: str,
    workload_class: str,
    model: str,
    node_count: int,
    boundary: str,
    series: pd.Series,
    source_paths: Sequence[str],
    segmentation: str,
) -> dict[str, Any]:
    clean = collapse_duplicate_index(series.dropna())
    values = clean.to_numpy(dtype=float)
    quantiles = np.quantile(values, [0.01, 0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95, 0.99]) if len(values) else np.full(9, np.nan)
    duration = float((clean.index[-1] - clean.index[0]).total_seconds()) if len(clean) > 1 else 0.0
    return {
        "experiment_id": experiment_id,
        "workload_class": workload_class,
        "model_family": model,
        "node_count": int(node_count),
        "gpus_per_node": GPUS_PER_NODE,
        "total_gpu_count": int(node_count * GPUS_PER_NODE),
        "resource_state": "FULL_NODE_EXCLUSIVE_WORKLOAD",
        "power_boundary": boundary,
        "authority_status": "AUTHORITATIVE_COMPONENT" if boundary != "DATASET_PROVIDED_GPU_PLUS_RAPL_PACKAGE_PLUS_CORE_SUM" else "RECONCILIATION_ONLY_NONADDITIVE_RAPL_OVERLAP",
        "unit": "W",
        "sample_count": int(len(values)),
        "duration_seconds": duration,
        "mean_power_W": float(np.mean(values)) if len(values) else math.nan,
        "median_power_W": float(quantiles[4]),
        "std_power_W": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
        "p01_power_W": float(quantiles[0]),
        "p05_power_W": float(quantiles[1]),
        "p10_power_W": float(quantiles[2]),
        "p25_power_W": float(quantiles[3]),
        "p75_power_W": float(quantiles[5]),
        "p90_power_W": float(quantiles[6]),
        "p95_power_W": float(quantiles[7]),
        "p99_power_W": float(quantiles[8]),
        "min_power_W": float(np.min(values)) if len(values) else math.nan,
        "max_power_W": float(np.max(values)) if len(values) else math.nan,
        "energy_integral_Wh": integrate_series_wh(clean),
        "energy_method": "TRAPEZOID_ACTUAL_ALIGNED_TIMESTAMPS",
        "statistic_timebase": "NATIVE_FAMILY_INTERVAL_AFTER_CROSS_SENSOR_ALIGNMENT",
        "segmentation": segmentation,
        "source_relative_paths_json": json.dumps(sorted(source_paths)),
    }


def relative_error(actual: float, expected: float) -> float:
    if not np.isfinite(actual) or not np.isfinite(expected):
        return math.nan
    if expected == 0:
        return 0.0 if actual == 0 else math.inf
    return float(abs(actual - expected) / abs(expected))


def parquet_schema(path: Path) -> dict[str, Any]:
    parquet = pq.ParquetFile(path)
    return {
        "columns": {field.name: str(field.type) for field in parquet.schema_arrow},
        "rows": int(parquet.metadata.num_rows),
        "row_groups": int(parquet.metadata.num_row_groups),
    }


def dataframe_units(columns: Iterable[str]) -> dict[str, str]:
    units: dict[str, str] = {}
    for column in columns:
        match = re.search(r"\[([^\]]+)\]", str(column))
        suffix = str(column).lower()
        if match:
            units[str(column)] = match.group(1)
        elif suffix.endswith("_seconds") or suffix in {"elapsed", "duration"}:
            units[str(column)] = "s"
        elif suffix.endswith("_ms"):
            units[str(column)] = "ms"
        elif "timestamp" in suffix or suffix.endswith("_time") or suffix == "date":
            units[str(column)] = "datetime_or_relative_time"
        elif "rate" in suffix or "throughput" in suffix:
            units[str(column)] = "count_per_second_or_metadata_defined"
        elif "power" in suffix:
            units[str(column)] = "W_or_filename_defined"
        else:
            units[str(column)] = "UNKNOWN"
    return units
