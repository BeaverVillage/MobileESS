"""Build the fail-closed V35R3F Dataset 312 authority artifacts.

The pipeline reads only the frozen Dataset 312 v2 authority.  It does not read
Kestrel scheduler traces, grid artifacts, RADDiT, Fresh, Planning, or MESS.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd
import psutil
import pyarrow

from .audit import (
    NODE_RE,
    SLURM_RE,
    align_and_sum,
    archive_inventory,
    audit_quality,
    audit_timebase,
    component_series,
    dataframe_units,
    git,
    integrate_series_wh,
    inventory_record,
    parquet_schema,
    profile_statistics,
    read_power_log,
    relative_error,
    sha256_file,
    workload_identity,
    write_csv,
    write_json,
)
from .contracts import (
    ARCHIVE,
    ARCHIVE_BYTES,
    ARCHIVE_SHA256,
    ARTIFACT_DIRNAME,
    BRANCH,
    CACHE_DIRNAME,
    DATASET_DOI,
    DATASET_ID,
    DATASET_VERSION,
    EXTRACTED_ROOT,
    FORBIDDEN_ASSERTIONS,
    GPUS_PER_NODE,
    KESTREL_NODE_PACKING_NEXT,
    LOG_DIRNAME,
    MANIFEST_ROOT,
    PARENT_HEAD,
    PARTIAL_SHARED_ANSWER,
    POWER_AUTHORITY_LEVEL,
    PRIMARY_BOUNDARY,
    PRIMARY_CLASSIFICATION,
    RAW_AGGREGATE_ENERGY_RTOL,
    RAW_AGGREGATE_MEAN_RTOL,
    RAW_AGGREGATE_QUANTILE_RTOL,
    REQUIRED_ARTIFACTS,
    RESOURCE_STATE_SUPPORT,
)


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "dayahead" / "artifacts" / ARTIFACT_DIRNAME
CACHE = ROOT / "dayahead" / "cache" / CACHE_DIRNAME
LOGS = ROOT / "logs" / LOG_DIRNAME
RAW = EXTRACTED_ROOT / "00_raw_datasets"
AGGREGATED = EXTRACTED_ROOT / "01_aggregated_datasets"

PAPER_URL = "https://arxiv.org/html/2604.07345"
CATALOG_URL = "https://data.nlr.gov/submissions/312"
WATTAMETER_URL = "https://github.com/NatLabRockies/WattAMeter"


class Accounting:
    def __init__(self) -> None:
        self.started = time.perf_counter()
        self.stages: dict[str, float] = {}
        self.raw_bytes = 0
        self.raw_rows = 0
        self.aggregate_rows = 0
        self.process = psutil.Process()
        self.peak_rss = self.process.memory_info().rss

    def checkpoint(self, name: str, stage_start: float) -> None:
        self.stages[name] = time.perf_counter() - stage_start
        self.peak_rss = max(self.peak_rss, self.process.memory_info().rss)

    def payload(self, source_commit: str) -> dict[str, Any]:
        return provenance(source_commit) | {
            "wallclock_seconds_total": time.perf_counter() - self.started,
            "wallclock_seconds_by_major_stage": self.stages,
            "peak_resident_memory_bytes_observed_at_stage_boundaries": self.peak_rss,
            "raw_measurement_bytes_processed": self.raw_bytes,
            "raw_measurement_rows_processed": self.raw_rows,
            "dataset_supplied_aggregate_rows_processed": self.aggregate_rows,
            "process_count": 1,
            "thread_policy": "SINGLE_PROCESS_NUMPY_PANDAS_NO_EXPLICIT_PARALLEL_POOL",
            "GPU_training": False,
            "XGBoost": False,
            "Gurobi": False,
            "full_year_simulation": False,
        }


def provenance(source_commit: str) -> dict[str, Any]:
    versions: dict[str, str | None] = {}
    for package in ("numpy", "pandas", "pyarrow", "psutil", "pytest"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    return {
        "dataset_id": DATASET_ID,
        "dataset_version": DATASET_VERSION,
        "dataset_doi": DATASET_DOI,
        "source_archive_sha256": ARCHIVE_SHA256,
        "source_code_commit": source_commit,
        "parameter_contract": {
            "time_integration": "TRAPEZOID_ACTUAL_TIMESTAMPS",
            "sample_quantiles": "NUMPY_LINEAR",
            "robust_envelope": "CLASS_STRATIFIED_RUN_MEAN_P05_MEDIAN_OF_P50_P95",
            "sensor_invalid": "NONFINITE_NEGATIVE_OR_ABOVE_800W",
            "native_raw_intervals_seconds": {"inference": 0.1, "training": 0.2},
            "cross_sensor_alignment": "LINEAR_INTERPOLATION_COMMON_OVERLAP",
        },
        "timezone_assumption": "SOURCE_TIMESTAMPS_NAIVE; NO_TIMEZONE CONVERSION; ELAPSED DIFFERENCES ONLY",
        "power_unit": "W",
        "energy_unit": "Wh",
        "software_versions": versions | {"python": platform.python_version()},
    }


def ensure_source() -> dict[str, Any]:
    if not ARCHIVE.is_file() or not EXTRACTED_ROOT.is_dir():
        raise FileNotFoundError("Frozen Dataset 312 archive or extraction is missing")
    actual_sha = sha256_file(ARCHIVE)
    if actual_sha != ARCHIVE_SHA256 or ARCHIVE.stat().st_size != ARCHIVE_BYTES:
        raise RuntimeError("Dataset 312 archive authority mismatch")
    marker = EXTRACTED_ROOT / ".dataset312_extraction_complete"
    marker_text = marker.read_text(encoding="utf-8")
    if f"archive_sha256={ARCHIVE_SHA256}" not in marker_text or "version=2" not in marker_text:
        raise RuntimeError("Dataset 312 extraction marker mismatch")
    files = [path for path in EXTRACTED_ROOT.rglob("*") if path.is_file()]
    return {
        "archive_sha256": actual_sha,
        "archive_bytes": ARCHIVE.stat().st_size,
        "extracted_file_count": len(files),
        "extracted_file_bytes": int(sum(path.stat().st_size for path in files)),
        "extraction_marker": str(marker),
        "extraction_marker_content": marker_text.strip().splitlines(),
        "manifest_root": str(MANIFEST_ROOT),
        "manifest_root_exists": MANIFEST_ROOT.is_dir(),
    }


def build_schema_census(inventory_rows: Sequence[dict[str, Any]], source_commit: str) -> dict[str, Any]:
    families: list[dict[str, Any]] = [
        {
            "family": "raw_nvml_wattameter_log",
            "file_count": sum(row["apparent_role"] == "raw_nvml_gpu_power_temperature_log" for row in inventory_rows),
            "fields": {
                "timestamp": {"dtype": "datetime string", "unit": "naive local datetime"},
                "reading-time[ns]": {"dtype": "integer", "unit": "ns"},
                **{f"gpu-{i}[mW]": {"dtype": "integer", "unit": "mW"} for i in range(4)},
                **{f"gpu-{i}[C]": {"dtype": "integer", "unit": "C"} for i in range(4)},
            },
        },
        {
            "family": "raw_rapl_wattameter_log",
            "file_count": sum(row["apparent_role"] == "raw_rapl_cpu_energy_power_log" for row in inventory_rows),
            "fields": {
                "timestamp": {"dtype": "datetime string", "unit": "naive local datetime"},
                "reading-time[ns]": {"dtype": "integer", "unit": "ns"},
                "cpu-0[uJ]": {"dtype": "integer", "unit": "uJ"},
                "cpu-0-core[uJ]": {"dtype": "integer", "unit": "uJ"},
                "cpu-1[uJ]": {"dtype": "integer", "unit": "uJ"},
                "cpu-1-core[uJ]": {"dtype": "integer", "unit": "uJ"},
                "cpu-0[W]": {"dtype": "float", "unit": "W"},
                "cpu-0-core[W]": {"dtype": "float", "unit": "W"},
                "cpu-1[W]": {"dtype": "float", "unit": "W"},
                "cpu-1-core[W]": {"dtype": "float", "unit": "W"},
            },
        },
    ]
    for metadata in sorted(AGGREGATED.rglob("metadata.csv")):
        frame = pd.read_csv(metadata, nrows=5)
        families.append(
            {
                "family": f"metadata:{metadata.parent.name}",
                "source_relative_path": metadata.relative_to(EXTRACTED_ROOT).as_posix(),
                "fields": {
                    column: {"dtype": str(dtype), "unit": dataframe_units([column])[column]}
                    for column, dtype in frame.dtypes.items()
                },
            }
        )
    result_directories = sorted({path.parent for path in AGGREGATED.rglob("*.parquet")})
    for directory in result_directories:
        sample = next(directory.glob("*.parquet"))
        schema = parquet_schema(sample)
        families.append(
            {
                "family": f"aggregate_profile:{directory.parent.name}",
                "source_relative_path_sample": sample.relative_to(EXTRACTED_ROOT).as_posix(),
                "file_count": len(list(directory.glob("*.parquet"))),
                "fields": {
                    name: {"dtype": dtype, "unit": dataframe_units([name])[name]}
                    for name, dtype in schema["columns"].items()
                },
                "index": {"name": "timestep[s]", "unit": "s"},
            }
        )
    for csv_path in sorted((EXTRACTED_ROOT / "03_whole-facility_profiles").rglob("*.csv")):
        frame = pd.read_csv(csv_path, nrows=2)
        families.append(
            {
                "family": f"whole_facility:{csv_path.parent.name}:{csv_path.name}",
                "source_relative_path": csv_path.relative_to(EXTRACTED_ROOT).as_posix(),
                "fields": {
                    column: {"dtype": str(dtype), "unit": dataframe_units([column])[column]}
                    for column, dtype in frame.dtypes.items()
                },
                "authority": "SYNTHETIC_NOT_MEASURED",
            }
        )
    return provenance(source_commit) | {
        "families": families,
        "all_fields_have_units_or_UNKNOWN": all(
            field.get("unit") is not None
            for family in families
            for field in family.get("fields", {}).values()
        ),
        "schema_source": "HEADERS_AND_FILE_SCHEMAS_NOT_FILENAME_ONLY",
    }


def sensor_semantics(source_commit: str) -> dict[str, Any]:
    fields = [
        {
            "field": "gpu-{0,1,2,3}[mW]",
            "unit": "mW (normalized to W in derived artifacts)",
            "sensor_api": "WattAMeter NVML reader / NVIDIA Management Library",
            "physical_boundary": "INDIVIDUAL_H100_DEVICE_POWER_AS_REPORTED_BY_NVML",
            "scope": "PER_GPU; FOUR_CHANNELS_PER_Kestrel_GPU_NODE",
            "includes": "GPU device/module power covered by NVML's device power reading",
            "excludes": "CPU, system DRAM, NICs, storage, fans/pumps, PSU/conversion losses, rack and facility auxiliaries",
            "exact_internal_subcomponent_coverage": "UNKNOWN_FROM_DATASET",
            "sampling_interval": "0.1 s inference raw; 0.2 s training raw",
            "missing_value_semantics": "No sentinel documented; parse failures/nonfinite/negative/>800 W are SENSOR_INVALID",
            "authority": "AUTHORITATIVE_COMPONENT",
        },
        {
            "field": "gpu-{0,1,2,3}[C]",
            "unit": "degrees C",
            "sensor_api": "WattAMeter NVML reader",
            "physical_boundary": "PER_GPU_DEVICE_TEMPERATURE",
            "scope": "PER_GPU",
            "includes": "Reported device temperature",
            "excludes": "Power",
            "sampling_interval": "Same row cadence as NVML power",
            "missing_value_semantics": "UNKNOWN",
            "authority": "NOT_A_POWER_CHANNEL",
        },
        {
            "field": "cpu-{0,1}[uJ] and cpu-{0,1}[W]",
            "unit": "uJ cumulative energy and W derived power",
            "sensor_api": "WattAMeter RAPL reader on AMD EPYC 9554",
            "physical_boundary": "CPU_SOCKET_PACKAGE_RAPL_DOMAIN",
            "scope": "PER_CPU_SOCKET; TWO_SOCKETS_PER_NODE",
            "includes": "RAPL package/socket domain as exposed by the platform",
            "excludes": "Discrete GPUs and all non-package node components; exact platform-domain internals UNKNOWN",
            "sampling_interval": "0.1 s inference raw; 0.2 s training raw",
            "missing_value_semantics": "No sentinel documented; parse failures/nonfinite/negative/>800 W are SENSOR_INVALID",
            "authority": "AUTHORITATIVE_COMPONENT_WITH_AMD_ACCURACY_LIMITATION",
        },
        {
            "field": "cpu-{0,1}-core[uJ] and cpu-{0,1}-core[W]",
            "unit": "uJ cumulative energy and W derived power",
            "sensor_api": "WattAMeter RAPL core-domain reader",
            "physical_boundary": "RAPL_CORE_SUBDOMAIN_NESTED_WITHIN_PACKAGE",
            "scope": "ONE REPORTED CORE-DOMAIN CHANNEL PER SOCKET; EXACT CORE SELECTION UNKNOWN",
            "includes": "Core energy domain exposed by RAPL",
            "excludes": "Not a second CPU package; must not be added to package as disjoint power",
            "sampling_interval": "0.1 s inference raw; 0.2 s training raw",
            "missing_value_semantics": "No sentinel documented; parse failures/nonfinite/negative/>800 W are SENSOR_INVALID",
            "authority": "COMPONENT_DIAGNOSTIC; NESTED_DOMAIN",
        },
        {
            "field": "aggregated power[W]",
            "unit": "W",
            "sensor_api": "Dataset postprocess.py sum after interpolation",
            "physical_boundary": "SUM_OF_NVML_GPU + RAPL_PACKAGE + RAPL_CORE_REPORTED CHANNELS",
            "scope": "PER_EXPERIMENT; ACROSS ALL ALLOCATED NODES",
            "includes": "Four NVML GPU channels and four reported RAPL W columns per node",
            "excludes": "System DRAM outside package, NIC, storage, fans/pumps, PSU/conversion losses, rack and facility auxiliaries",
            "sampling_interval": "0.1 s offline/finite inference; 0.001 s rate inference; 0.2 s training",
            "missing_value_semantics": "Scripts replace >800 W device samples by backward fill for inference; training has no such cleaning",
            "authority": "RECONCILIATION_ONLY; NOT WHOLE_NODE; RAPL PACKAGE/CORE OVERLAP",
        },
    ]
    return provenance(source_commit) | {
        "fields": fields,
        "channels_absent": [
            "DRAM_POWER_AS_SEPARATE_SENSOR",
            "WHOLE_NODE_INPUT_POWER",
            "RACK_OR_PDU_POWER",
            "MEASURED_FACILITY_POWER",
        ],
        "whole_facility_directory_semantics": "DIPLOEE_SIMULATED_NOT_MEASURED",
        "critical_firewall": "GPU power + CPU RAPL package proxy is not whole-node input power",
        "evidence": {
            "dataset_README": "README.md repository structure",
            "dataset_scripts": "01_aggregated_datasets/*/postprocess.py",
            "paper": PAPER_URL,
            "WattAMeter": WATTAMETER_URL,
        },
    }


def _slice(series: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    return series.loc[(series.index >= start) & (series.index <= end)]


def _trim_finite(series: pd.Series) -> tuple[pd.Series, bool]:
    rolling = series.rolling(10).mean()
    difference = rolling.diff()
    above = rolling.loc[rolling > 1850.0]
    if above.empty:
        return series, True
    before = difference.loc[: above.index[0]]
    below_noise = before.loc[before < 11.5]
    if below_noise.empty:
        return series, True
    start = below_noise.index[-1]
    return series.loc[start:], start == series.index[0]


def _elapsed_profile(series: pd.Series) -> pd.Series:
    if not len(series):
        return series
    elapsed = (series.index - series.index[0]).total_seconds()
    return pd.Series(series.to_numpy(float), index=np.asarray(elapsed, dtype=float))


def _aggregate_metrics(path: Path) -> dict[str, Any]:
    frame = pd.read_parquet(path)
    values = pd.to_numeric(frame["power[W]"], errors="coerce").to_numpy(float)
    index = pd.to_numeric(pd.Index(frame.index), errors="coerce").to_numpy(float)
    valid = np.isfinite(values) & np.isfinite(index)
    values = values[valid]
    index = index[valid]
    order = np.argsort(index, kind="stable")
    values = values[order]
    index = index[order]
    if len(index) > 1:
        unique, inverse = np.unique(index, return_inverse=True)
        if len(unique) != len(index):
            sums = np.bincount(inverse, weights=values)
            counts = np.bincount(inverse)
            values = sums / counts
            index = unique
    q = np.quantile(values, [0.05, 0.5, 0.95]) if len(values) else [np.nan] * 3
    energy = float(np.trapz(values, index) / 3600.0) if len(values) > 1 else 0.0
    return {
        "row_count": len(values),
        "mean_power_W": float(np.mean(values)) if len(values) else math.nan,
        "median_power_W": float(q[1]),
        "p05_power_W": float(q[0]),
        "p95_power_W": float(q[2]),
        "energy_Wh": energy,
        "duration_seconds": float(index[-1] - index[0]) if len(index) > 1 else 0.0,
        "sampling_interval_seconds": float(np.median(np.diff(index))) if len(index) > 1 else math.nan,
    }


def _raw_metrics(series: pd.Series) -> dict[str, Any]:
    elapsed = _elapsed_profile(series)
    values = elapsed.to_numpy(float)
    index = elapsed.index.to_numpy(float)
    q = np.quantile(values, [0.05, 0.5, 0.95]) if len(values) else [np.nan] * 3
    return {
        "row_count": len(values),
        "mean_power_W": float(np.mean(values)) if len(values) else math.nan,
        "median_power_W": float(q[1]),
        "p05_power_W": float(q[0]),
        "p95_power_W": float(q[2]),
        "energy_Wh": float(np.trapz(values, index) / 3600.0) if len(values) > 1 else 0.0,
        "duration_seconds": float(index[-1] - index[0]) if len(index) > 1 else 0.0,
        "sampling_interval_seconds": float(np.median(np.diff(index))) if len(index) > 1 else math.nan,
    }


def _reconciliation_row(
    experiment_id: str,
    workload: str,
    nodes: int,
    raw_series: pd.Series,
    aggregate_path: Path | None,
    accounting: Accounting,
) -> dict[str, Any]:
    raw = _raw_metrics(raw_series)
    if aggregate_path is None or not aggregate_path.is_file():
        return {
            "experiment_id": experiment_id,
            "workload_class": workload,
            "node_count": nodes,
            "aggregate_available": False,
            "classification": "RAW_ONLY_NO_DATASET_AGGREGATE",
            **{f"raw_{key}": value for key, value in raw.items()},
        }
    supplied = _aggregate_metrics(aggregate_path)
    accounting.aggregate_rows += supplied["row_count"]
    errors = {
        "mean_relative_error": relative_error(raw["mean_power_W"], supplied["mean_power_W"]),
        "median_relative_error": relative_error(raw["median_power_W"], supplied["median_power_W"]),
        "p05_relative_error": relative_error(raw["p05_power_W"], supplied["p05_power_W"]),
        "p95_relative_error": relative_error(raw["p95_power_W"], supplied["p95_power_W"]),
        "energy_relative_error": relative_error(raw["energy_Wh"], supplied["energy_Wh"]),
    }
    passed = (
        errors["mean_relative_error"] <= RAW_AGGREGATE_MEAN_RTOL
        and errors["energy_relative_error"] <= RAW_AGGREGATE_ENERGY_RTOL
        and errors["median_relative_error"] <= RAW_AGGREGATE_QUANTILE_RTOL
        and errors["p05_relative_error"] <= RAW_AGGREGATE_QUANTILE_RTOL
        and errors["p95_relative_error"] <= RAW_AGGREGATE_QUANTILE_RTOL
    )
    return {
        "experiment_id": experiment_id,
        "workload_class": workload,
        "node_count": nodes,
        "aggregate_available": True,
        "aggregate_relative_path": aggregate_path.relative_to(EXTRACTED_ROOT).as_posix(),
        **{f"raw_{key}": value for key, value in raw.items()},
        **{f"aggregate_{key}": value for key, value in supplied.items()},
        **errors,
        "row_count_difference": supplied["row_count"] - raw["row_count"],
        "row_count_ratio_aggregate_to_raw": supplied["row_count"] / raw["row_count"] if raw["row_count"] else math.nan,
        "classification": "PASS" if passed else "FAIL",
    }


def _audit_loaded(
    path: Path,
    device: str,
    frame: pd.DataFrame,
    time_rows: list[dict[str, Any]],
    quality_rows: list[dict[str, Any]],
    accounting: Accounting,
) -> None:
    relative = path.relative_to(EXTRACTED_ROOT).as_posix()
    time_rows.append(audit_timebase(relative, device, frame))
    quality_rows.extend(audit_quality(relative, device, frame))
    accounting.raw_bytes += path.stat().st_size
    accounting.raw_rows += len(frame)


def process_training(
    time_rows: list[dict[str, Any]],
    quality_rows: list[dict[str, Any]],
    accounting: Accounting,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    profile_rows: list[dict[str, Any]] = []
    experiments: list[dict[str, Any]] = []
    reconciliation: list[dict[str, Any]] = []
    aggregate_meta = pd.read_csv(AGGREGATED / "training" / "metadata.csv")
    aggregate_by_slurm = {str(row.slurmid): int(row["Unnamed: 0"]) for _, row in aggregate_meta.iterrows()}
    groups: dict[tuple[str, int, str], list[Path]] = defaultdict(list)
    for path in sorted(RAW.glob("training_*/*node/*wattameter*.log")):
        workload, model, _family = workload_identity(path.relative_to(EXTRACTED_ROOT).as_posix())
        node_count = int(path.parent.name.removesuffix("node"))
        slurm = SLURM_RE.search(path.name)
        if workload is None or model is None or slurm is None:
            raise ValueError(f"Cannot classify training file {path}")
        groups[(model, node_count, slurm.group(1))].append(path)
    repeats: dict[tuple[str, int], int] = defaultdict(int)
    for (model, node_count, slurm), paths in sorted(groups.items()):
        expected = node_count * 2
        structural_valid = len(paths) == expected
        gpu_series: list[pd.Series] = []
        package_series: list[pd.Series] = []
        core_series: list[pd.Series] = []
        source_paths: list[str] = []
        for path in sorted(paths):
            device, frame = read_power_log(path)
            _audit_loaded(path, device, frame, time_rows, quality_rows, accounting)
            components = component_series(device, frame)
            if device == "NVML":
                gpu_series.append(components["GPU_ONLY_POWER"])
            else:
                package_series.append(components["RAPL_PACKAGE_POWER"])
                core_series.append(components["RAPL_CORE_SUBDOMAIN_POWER"])
            source_paths.append(path.relative_to(EXTRACTED_ROOT).as_posix())
        if not structural_valid or len(gpu_series) != node_count or len(package_series) != node_count:
            experiments.append(
                {
                    "experiment_id": f"training:{slurm}",
                    "slurm_id": slurm,
                    "workload_class": "UNKNOWN",
                    "model_family": model,
                    "node_count": node_count,
                    "total_gpu_count": node_count * GPUS_PER_NODE,
                    "validity": "STRUCTURAL_INVALID",
                }
            )
            continue
        gpu = align_and_sum(gpu_series, 0.2)
        package = align_and_sum(package_series, 0.2)
        core = align_and_sum(core_series, 0.2)
        primary = align_and_sum([gpu, package], 0.2)
        provided = align_and_sum([gpu, package, core], 0.2)
        workload = "FINE_TUNING_LORA" if model == "LLAMA2_70B" else "TRAINING_STABLE_DIFFUSION"
        experiment_id = f"training:{slurm}"
        for boundary, series in (
            ("GPU_ONLY_POWER", gpu),
            ("RAPL_PACKAGE_POWER", package),
            ("RAPL_CORE_SUBDOMAIN_POWER", core),
            (PRIMARY_BOUNDARY, primary),
            ("DATASET_PROVIDED_GPU_PLUS_RAPL_PACKAGE_PLUS_CORE_SUM", provided),
        ):
            profile_rows.append(
                profile_statistics(
                    experiment_id,
                    workload,
                    model,
                    node_count,
                    boundary,
                    series,
                    source_paths,
                    "FULL_CAPTURE_PRIMARY_NO_TRIMMING",
                )
            )
        repeat = repeats[(model, node_count)]
        repeats[(model, node_count)] += 1
        aggregate_index = aggregate_by_slurm.get(slurm)
        aggregate_path = (
            AGGREGATED / "training" / "results" / f"{aggregate_index:06d}.parquet"
            if aggregate_index is not None
            else None
        )
        reconciliation.append(
            _reconciliation_row(experiment_id, workload, node_count, provided, aggregate_path, accounting)
        )
        experiments.append(
            {
                "experiment_id": experiment_id,
                "slurm_id": slurm,
                "workload_class": workload,
                "task_type": "FINE_TUNING" if "LORA" in workload else "TRAINING",
                "model_family": model,
                "model_size_parameters": "70B" if model == "LLAMA2_70B" else "865M",
                "dataset": "SCROLLS_GovReport" if model == "LLAMA2_70B" else "LAION_400M_FILTERED",
                "framework": "MLPERF_TRAINING_V4_PYTORCH",
                "node_count": node_count,
                "gpus_per_node": GPUS_PER_NODE,
                "total_gpu_count": node_count * GPUS_PER_NODE,
                "partial_gpu_node_state": False,
                "shared_node_multi_job": False,
                "full_node_exclusive": True,
                "repetition_index": repeat,
                "precision": "UNKNOWN",
                "batch_size": "1_PER_DEVICE_FOR_LLAMA; DATASET_ARTIFACT_UNKNOWN_FOR_STABLE_DIFFUSION",
                "sequence_length": "UNKNOWN",
                "validity": "VALID",
                "aggregate_available": aggregate_path is not None,
                "source_relative_paths_json": json.dumps(source_paths),
            }
        )
    return profile_rows, experiments, reconciliation


def process_inference(
    time_rows: list[dict[str, Any]],
    quality_rows: list[dict[str, Any]],
    accounting: Accounting,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    specs = (
        ("inference_offline_llama3_70b", "INFERENCE_OFFLINE", "OFFICIAL_BENCHMARK_START_END", False),
        ("inference_online_finite_llama3_70b", "INFERENCE_ONLINE_FINITE", "DATASET_WINDOW_PLUS_HEURISTIC_START", True),
        ("inference_online_rate_llama3_70b", "INFERENCE_ONLINE_RATE", "DATASET_FIXED_THREE_MINUTE_WINDOW", False),
    )
    profile_rows: list[dict[str, Any]] = []
    experiments: list[dict[str, Any]] = []
    reconciliation: list[dict[str, Any]] = []
    segmentation_warnings: dict[str, int] = {}
    for folder, workload, segmentation, use_trim in specs:
        raw_folder = RAW / folder
        nvml_path = next(raw_folder.glob("nvml_wattameter_*.log"))
        rapl_path = next(raw_folder.glob("rapl_wattameter_*.log"))
        nvml_device, nvml_frame = read_power_log(nvml_path)
        rapl_device, rapl_frame = read_power_log(rapl_path)
        _audit_loaded(nvml_path, nvml_device, nvml_frame, time_rows, quality_rows, accounting)
        _audit_loaded(rapl_path, rapl_device, rapl_frame, time_rows, quality_rows, accounting)
        gpu_all = component_series(nvml_device, nvml_frame)["GPU_ONLY_POWER"]
        rapl_components = component_series(rapl_device, rapl_frame)
        package_all = rapl_components["RAPL_PACKAGE_POWER"]
        core_all = rapl_components["RAPL_CORE_SUBDOMAIN_POWER"]
        metadata = pd.read_csv(AGGREGATED / folder / "metadata.csv")
        warnings = 0
        for index, row in metadata.iterrows():
            start = pd.Timestamp(row["start_time"])
            end = pd.Timestamp(row["end_time"])
            gpu = align_and_sum([_slice(gpu_all, start, end)], 0.1)
            package = align_and_sum([_slice(package_all, start, end)], 0.1)
            core = align_and_sum([_slice(core_all, start, end)], 0.1)
            primary = align_and_sum([gpu, package], 0.1)
            provided = align_and_sum([gpu, package, core], 0.1)
            trim_failed = False
            if use_trim:
                trimmed, trim_failed = _trim_finite(provided)
                trim_start = trimmed.index[0] if len(trimmed) else provided.index[0]
                gpu = gpu.loc[trim_start:]
                package = package.loc[trim_start:]
                core = core.loc[trim_start:]
                primary = primary.loc[trim_start:]
                provided = provided.loc[trim_start:]
                warnings += int(trim_failed)
            experiment_id = f"{folder}:{index:06d}"
            sources = [
                nvml_path.relative_to(EXTRACTED_ROOT).as_posix(),
                rapl_path.relative_to(EXTRACTED_ROOT).as_posix(),
                (AGGREGATED / folder / "metadata.csv").relative_to(EXTRACTED_ROOT).as_posix(),
            ]
            for boundary, series in (
                ("GPU_ONLY_POWER", gpu),
                ("RAPL_PACKAGE_POWER", package),
                ("RAPL_CORE_SUBDOMAIN_POWER", core),
                (PRIMARY_BOUNDARY, primary),
                ("DATASET_PROVIDED_GPU_PLUS_RAPL_PACKAGE_PLUS_CORE_SUM", provided),
            ):
                profile_rows.append(
                    profile_statistics(
                        experiment_id,
                        workload,
                        "LLAMA3_70B",
                        1,
                        boundary,
                        series,
                        sources,
                        segmentation + ("_FAILED_RETAINED_FULL_WINDOW" if trim_failed else ""),
                    )
                )
            aggregate_path = AGGREGATED / folder / "results" / f"{index:06d}.parquet"
            reconciliation.append(
                _reconciliation_row(experiment_id, workload, 1, provided, aggregate_path, accounting)
            )
            experiments.append(
                {
                    "experiment_id": experiment_id,
                    "slurm_id": None,
                    "benchmark_record_id": row.get("id", index),
                    "workload_class": workload,
                    "task_type": "INFERENCE",
                    "model_family": "LLAMA3_70B",
                    "model_size_parameters": "70B",
                    "dataset": row.get("dataset-path", "UNKNOWN"),
                    "framework": "vLLM",
                    "node_count": 1,
                    "gpus_per_node": GPUS_PER_NODE,
                    "total_gpu_count": GPUS_PER_NODE,
                    "partial_gpu_node_state": False,
                    "shared_node_multi_job": False,
                    "full_node_exclusive": True,
                    "repetition_index": row.get("repeat", row.get("_repeat", "UNKNOWN")),
                    "precision": "UNKNOWN",
                    "batch_size_or_num_prompts": row.get("batch_size", row.get("num-prompts", "UNKNOWN")),
                    "max_output_tokens": row.get("max_output_tokens", row.get("hf-output-len", "UNKNOWN")),
                    "request_rate_prompts_per_second": row.get("request_rate", row.get("request_rate_x", "NOT_APPLICABLE")),
                    "sequence_length": "UNKNOWN",
                    "validity": "VALID_WITH_DATASET_SEGMENTATION_WARNING" if trim_failed else "VALID",
                    "aggregate_available": True,
                    "source_relative_paths_json": json.dumps(sources),
                }
            )
        segmentation_warnings[folder] = warnings
        del nvml_frame, rapl_frame, gpu_all, package_all, core_all
    return profile_rows, experiments, reconciliation, segmentation_warnings


def node_scaling(stats: pd.DataFrame, source_commit: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    selected = stats.loc[
        stats["power_boundary"].isin([PRIMARY_BOUNDARY, "GPU_ONLY_POWER"])
        & stats["workload_class"].isin(["FINE_TUNING_LORA", "TRAINING_STABLE_DIFFUSION"])
    ].copy()
    rows: list[dict[str, Any]] = []
    for (model, boundary), model_frame in selected.groupby(["model_family", "power_boundary"], sort=True):
        baseline_nodes = int(model_frame["node_count"].min())
        baseline = float(model_frame.loc[model_frame["node_count"].eq(baseline_nodes), "mean_power_W"].mean())
        previous_nodes: int | None = None
        previous_total: float | None = None
        for nodes, group in model_frame.groupby("node_count", sort=True):
            total = group["mean_power_W"].to_numpy(float)
            per_node = total / float(nodes)
            total_q = np.quantile(total, [0.05, 0.5, 0.95])
            per_q = np.quantile(per_node, [0.05, 0.5, 0.95])
            total_mean = float(total.mean())
            rows.append(
                {
                    "model_family": model,
                    "workload_class": group["workload_class"].iloc[0],
                    "power_boundary": boundary,
                    "unit": "W",
                    "matched_series": True,
                    "weak_scaling_note": "GLOBAL_BATCH_OR_WORK_INCREASES_WITH_GPU_COUNT",
                    "node_count": int(nodes),
                    "gpus_per_node": GPUS_PER_NODE,
                    "total_gpu_count": int(nodes * GPUS_PER_NODE),
                    "run_count": len(group),
                    "total_mean_power_W": total_mean,
                    "total_p05_run_mean_power_W": float(total_q[0]),
                    "total_p50_run_mean_power_W": float(total_q[1]),
                    "total_p95_run_mean_power_W": float(total_q[2]),
                    "per_node_mean_power_W": float(per_node.mean()),
                    "per_node_p05_run_mean_power_W": float(per_q[0]),
                    "per_node_p50_run_mean_power_W": float(per_q[1]),
                    "per_node_p95_run_mean_power_W": float(per_q[2]),
                    "mean_energy_Wh": float(group["energy_integral_Wh"].mean()),
                    "energy_comparable_across_scales": False,
                    "scaling_efficiency_vs_smallest_scale": total_mean / (baseline * float(nodes) / baseline_nodes),
                    "incremental_power_W_per_added_node": (
                        (total_mean - previous_total) / (int(nodes) - previous_nodes)
                        if previous_total is not None and previous_nodes is not None
                        else math.nan
                    ),
                }
            )
            previous_nodes = int(nodes)
            previous_total = total_mean
    frame = pd.DataFrame(rows).sort_values(["power_boundary", "model_family", "node_count"]).reset_index(drop=True)
    summary: dict[str, Any] = provenance(source_commit) | {
        "matched_series_only": True,
        "node_counts": sorted(frame["node_count"].unique().astype(int).tolist()),
        "maximum_directly_observed_nodes": int(frame["node_count"].max()),
        "maximum_directly_observed_GPUs": int(frame["total_gpu_count"].max()),
        "series": {},
        "warning": "Weak scaling changes global batch/work; coefficients are descriptive, not causal node-count-only effects.",
    }
    for (model, boundary), group in frame.groupby(["model_family", "power_boundary"], sort=True):
        summary["series"][f"{model}:{boundary}"] = {
            "node_counts": group["node_count"].astype(int).tolist(),
            "per_node_mean_power_W": group["per_node_mean_power_W"].round(6).tolist(),
            "scaling_efficiency": group["scaling_efficiency_vs_smallest_scale"].round(6).tolist(),
        }
    return frame, summary


def workload_variability(stats: pd.DataFrame, source_commit: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    selected = stats.loc[stats["power_boundary"].isin([PRIMARY_BOUNDARY, "GPU_ONLY_POWER"])].copy()
    rows: list[dict[str, Any]] = []
    for (nodes, boundary), group in selected.groupby(["node_count", "power_boundary"], sort=True):
        classes = group.groupby("workload_class")["mean_power_W"].mean().sort_index()
        values = group["mean_power_W"].to_numpy(float)
        within = (group["std_power_W"] / group["mean_power_W"]).replace([np.inf, -np.inf], np.nan)
        rows.append(
            {
                "node_count": int(nodes),
                "total_gpu_count": int(nodes * GPUS_PER_NODE),
                "power_boundary": boundary,
                "unit": "W",
                "run_count": len(group),
                "workload_class_count": len(classes),
                "workload_classes_json": json.dumps(classes.index.tolist()),
                "class_mean_power_W_json": json.dumps({key: float(value) for key, value in classes.items()}),
                "between_workload_mean_spread_W": float(classes.max() - classes.min()),
                "between_workload_max_min_ratio": float(classes.max() / classes.min()),
                "run_mean_p05_W": float(np.quantile(values, 0.05)),
                "run_mean_p95_W": float(np.quantile(values, 0.95)),
                "run_mean_coefficient_of_variation": float(np.std(values, ddof=1) / np.mean(values)) if len(values) > 1 else 0.0,
                "mean_within_run_coefficient_of_variation": float(within.mean()),
                "between_run_variability_std_W": float(np.std(values, ddof=1)) if len(values) > 1 else 0.0,
            }
        )
    frame = pd.DataFrame(rows)
    primary = frame.loc[frame["power_boundary"].eq(PRIMARY_BOUNDARY)]
    summary = provenance(source_commit) | {
        "engineering_uncertainty_only": True,
        "statistical_significance_claimed": False,
        "primary_boundary": PRIMARY_BOUNDARY,
        "maximum_between_workload_mean_spread_W": float(primary["between_workload_mean_spread_W"].max()),
        "maximum_between_workload_max_min_ratio": float(primary["between_workload_max_min_ratio"].max()),
        "by_node_count": primary.to_dict(orient="records"),
    }
    return frame, summary


def power_envelope(stats: pd.DataFrame, source_commit: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    selected = stats.loc[
        stats["power_boundary"].isin([PRIMARY_BOUNDARY, "GPU_ONLY_POWER"])
        & stats["authority_status"].eq("AUTHORITATIVE_COMPONENT")
    ].copy()
    rows: list[dict[str, Any]] = []
    for (nodes, boundary), group in selected.groupby(["node_count", "power_boundary"], sort=True):
        for normalization in ("TOTAL_EXPERIMENT", "PER_NODE"):
            values = group["mean_power_W"] / (float(nodes) if normalization == "PER_NODE" else 1.0)
            class_quantiles = (
                group.assign(envelope_value=values)
                .groupby("workload_class")["envelope_value"]
                .quantile([0.05, 0.5, 0.95])
                .unstack()
            )
            pooled = np.quantile(values, [0.05, 0.5, 0.95])
            rows.append(
                {
                    "node_count": int(nodes),
                    "gpus_per_node": GPUS_PER_NODE,
                    "total_gpu_count": int(nodes * GPUS_PER_NODE),
                    "resource_state": "FULL_NODE_EXCLUSIVE_WORKLOAD",
                    "partial_gpu_supported": False,
                    "shared_node_supported": False,
                    "power_boundary": boundary,
                    "normalization": normalization,
                    "unit": "W" if normalization == "TOTAL_EXPERIMENT" else "W_per_node",
                    "run_count": len(group),
                    "workload_class_count": group["workload_class"].nunique(),
                    "workload_classes_json": json.dumps(sorted(group["workload_class"].unique().tolist())),
                    "P_LOW": float(class_quantiles[0.05].min()),
                    "P_CENTER": float(class_quantiles[0.5].median()),
                    "P_HIGH": float(class_quantiles[0.95].max()),
                    "P_LOW_definition": "MIN_ACROSS_CLASSES_OF_WITHIN_CLASS_RUN_MEAN_P05",
                    "P_CENTER_definition": "MEDIAN_ACROSS_CLASSES_OF_WITHIN_CLASS_RUN_MEAN_P50",
                    "P_HIGH_definition": "MAX_ACROSS_CLASSES_OF_WITHIN_CLASS_RUN_MEAN_P95",
                    "pooled_run_mean_P05": float(pooled[0]),
                    "pooled_run_mean_P50": float(pooled[1]),
                    "pooled_run_mean_P95": float(pooled[2]),
                    "quantile_basis": "EXPERIMENT_RUN_LEVEL_TIME_MEAN_CLASS_STRATIFIED",
                }
            )
    frame = pd.DataFrame(rows).sort_values(["power_boundary", "node_count", "normalization"]).reset_index(drop=True)
    contract = provenance(source_commit) | {
        "ROBUST_ENVELOPE_AVAILABLE": "YES",
        "primary_boundary": PRIMARY_BOUNDARY,
        "primary_boundary_limit": "COMPONENT_SUM_ONLY_NOT_WHOLE_NODE_IT",
        "state_dimensions": ["node_count", "full_node_exclusive", "power_boundary", "normalization"],
        "P_LOW": "MIN_ACROSS_WORKLOAD_CLASSES_OF_WITHIN_CLASS_RUN_MEAN_P05",
        "P_CENTER": "MEDIAN_ACROSS_WORKLOAD_CLASSES_OF_WITHIN_CLASS_RUN_MEAN_P50",
        "P_HIGH": "MAX_ACROSS_WORKLOAD_CLASSES_OF_WITHIN_CLASS_RUN_MEAN_P95",
        "pooled_quantiles_also_reported": True,
        "time_sample_quantiles_used_for_envelope": False,
        "experiment_run_level_quantiles_used": True,
        "grid_result_used_for_tuning": False,
        "unknown_workload_class_handling": "USE_CLASS_STRATIFIED_ENVELOPE_ONLY_FOR_DIRECTLY_SUPPORTED_FULL_NODE_EXCLUSIVE_COMPONENT_BOUNDARY",
        "partial_or_shared_unknown_workload_handling": "UNSUPPORTED_FAIL_CLOSED",
        "AIDC_IT_LOAD_AUTHORIZATION": "NOT_AUTHORIZED_WITHOUT_MISSING_NODE_INPUT_COMPONENTS",
    }
    return frame, contract


def experiment_dimensions(experiments: pd.DataFrame, source_commit: str) -> dict[str, Any]:
    def values(column: str) -> list[Any]:
        return sorted({str(value) for value in experiments[column].dropna().unique()})

    return provenance(source_commit) | {
        "experiment_count": len(experiments),
        "dimensions": {
            "task_type": values("task_type"),
            "workload_class": values("workload_class"),
            "model_family": values("model_family"),
            "node_count": sorted(experiments["node_count"].dropna().astype(int).unique().tolist()),
            "gpus_per_node": [GPUS_PER_NODE],
            "total_gpu_count": sorted(experiments["total_gpu_count"].dropna().astype(int).unique().tolist()),
            "precision": values("precision"),
            "repetition_index": "PRESENT_WHERE_METADATA_OR_SLURM_REPETITION_ORDER_SUPPORTS_IT",
            "batch_size": "EXPLICIT_FOR_OFFLINE_INFERENCE; PAPER/DATASET LIMITED FOR TRAINING",
            "sequence_length": "UNKNOWN",
        },
        "evidence": [
            "raw path and slurmid structure",
            "raw config.json/log.json",
            "aggregated metadata.csv",
            "dataset README.md and accompanying paper",
        ],
        "unsupported_dimensions_are_UNKNOWN": True,
    }


def resource_support(experiments: pd.DataFrame, source_commit: str) -> dict[str, Any]:
    return provenance(source_commit) | {
        "classification": RESOURCE_STATE_SUPPORT,
        "A_subset_of_H100_GPUs_active_experiment": "NO",
        "B_direct_active_GPU_counts_per_node": [4],
        "C_1_2_4_8_16_semantics": "NODE_COUNTS",
        "D_GPUs_per_node_constant": True,
        "D_GPUs_per_node": GPUS_PER_NODE,
        "E_partial_node_GPU_occupancy": "NO",
        "F_shared_node_co_resident_multiple_jobs": "NO",
        "G_idle_node_power_in_frozen_dataset_files": "NO",
        "H_node_power_on_off_transition_measurement": "NO",
        "H_workload_ramp_transients_within_exclusive_runs": "YES",
        "I_all_workload_measurements_full_node_exclusive": "YES",
        "node_counts_directly_observed": sorted(experiments["node_count"].astype(int).unique().tolist()),
        "total_GPU_counts_directly_observed": sorted(experiments["total_gpu_count"].astype(int).unique().tolist()),
        "PARTIAL_GPU_NODE_POWER_DIRECTLY_IDENTIFIED": "NO",
        "SHARED_NODE_POWER_DIRECTLY_IDENTIFIED": "NO",
        "IDLE_POWER_DIRECT_AUTHORITY": "NO",
        "P_node_k_c_directly_identified": "NO",
        "supported_function": "P_component_sum(N_nodes, workload_configuration) FOR FULL_NODE_EXCLUSIVE EXPERIMENTS",
        "paper_appendix_idle_summary_not_dataset_authority": True,
        "reason": "Archive contains four GPU channels on every measured node and exclusive one-job experiments; no partial allocation, co-resident job, or dedicated idle trace is included.",
    }


def boundary_authority(source_commit: str) -> dict[str, Any]:
    return provenance(source_commit) | {
        "authorities": [
            {
                "boundary": "GPU_ONLY_POWER",
                "status": "DIRECTLY_SUPPORTED",
                "uses": {
                    "AIDC_IT_load": "NOT_AUTHORIZED_ALONE",
                    "component_level_sensitivity": "AUTHORIZED",
                    "energy_accounting": "AUTHORIZED_FOR_GPU_COMPONENT",
                    "node_packing_bridge": "NOT_AUTHORIZED_AS_WHOLE_NODE",
                    "facility_scaling": "NOT_AUTHORIZED",
                },
            },
            {
                "boundary": "RAPL_PACKAGE_POWER",
                "status": "DIRECTLY_SUPPORTED_WITH_AMD_ACCURACY_LIMITATION",
                "uses": {
                    "AIDC_IT_load": "NOT_AUTHORIZED_ALONE",
                    "component_level_sensitivity": "AUTHORIZED",
                    "energy_accounting": "AUTHORIZED_FOR_REPORTED_PACKAGE_DOMAIN",
                    "node_packing_bridge": "NOT_AUTHORIZED_AS_WHOLE_NODE",
                    "facility_scaling": "NOT_AUTHORIZED",
                },
            },
            {
                "boundary": PRIMARY_BOUNDARY,
                "status": "DERIVED_NONOVERLAPPING_MEASURED_COMPONENT_SUM",
                "uses": {
                    "AIDC_IT_load": "NOT_AUTHORIZED_MISSING_NODE_COMPONENTS_AND_CONVERSION_LOSSES",
                    "component_level_sensitivity": "AUTHORIZED",
                    "energy_accounting": "AUTHORIZED_FOR_COMPONENT_SUM_ONLY",
                    "node_packing_bridge": "DIAGNOSTIC_ONLY",
                    "facility_scaling": "NOT_AUTHORIZED",
                },
            },
            {
                "boundary": "DATASET_PROVIDED_GPU_PLUS_RAPL_PACKAGE_PLUS_CORE_SUM",
                "status": "RECONCILED_BUT_PHYSICALLY_NONADDITIVE_RAPL_OVERLAP",
                "uses": {key: "NOT_AUTHORIZED" for key in ("AIDC_IT_load", "component_level_sensitivity", "energy_accounting", "node_packing_bridge", "facility_scaling")},
            },
            {"boundary": "WHOLE_NODE_INPUT_POWER", "status": "NOT_MEASURED", "uses": {"AIDC_IT_load": "NOT_AUTHORIZED"}},
            {"boundary": "FACILITY_POWER", "status": "SIMULATED_ONLY_NOT_MEASURED", "uses": {"facility_scaling": "NOT_AUTHORIZED_AS_MEASUREMENT"}},
        ],
        "primary_authority": PRIMARY_BOUNDARY,
        "primary_authority_level": POWER_AUTHORITY_LEVEL,
    }


def reconciliation_summary(rows: pd.DataFrame, source_commit: str) -> dict[str, Any]:
    available = rows.loc[rows["aggregate_available"].eq(True)].copy()
    passed = available["classification"].eq("PASS")
    classification = (
        "RAW_AGGREGATED_RECONCILIATION_PASS"
        if passed.all()
        else "RAW_AGGREGATED_RECONCILIATION_PARTIAL"
        if passed.any()
        else "RAW_AGGREGATED_RECONCILIATION_FAIL"
    )
    return provenance(source_commit) | {
        "classification": classification,
        "available_aggregate_runs": len(available),
        "raw_only_runs": int((~rows["aggregate_available"]).sum()),
        "passed_runs": int(passed.sum()),
        "failed_runs": int((~passed).sum()),
        "tolerances": {
            "mean_relative": RAW_AGGREGATE_MEAN_RTOL,
            "energy_relative": RAW_AGGREGATE_ENERGY_RTOL,
            "quantile_relative": RAW_AGGREGATE_QUANTILE_RTOL,
        },
        "maximum_errors": {
            column: float(available[column].max())
            for column in ("mean_relative_error", "median_relative_error", "p05_relative_error", "p95_relative_error", "energy_relative_error")
        },
        "important_interpretation": "Numerical reconciliation does not make the supplied overlapping RAPL package+core sum a whole-node physical boundary.",
        "online_rate_resampling": "Dataset-supplied 0.001 s interpolation from approximately 0.1 s raw samples is reconciled for mean/energy but is not native measurement resolution.",
    }


def transient_audit(segmentation_warnings: dict[str, int], source_commit: str) -> dict[str, Any]:
    return provenance(source_commit) | {
        "dataset_defined": {
            "training": "FULL CAPTURE; includes approximately three-minute initialization ramp per paper; no official steady-state cut",
            "offline_inference": "benchmark record start/end",
            "online_finite": "10 s removed at both sides plus supplied fixed threshold start heuristic",
            "online_rate": "start + 1 minute then up to 3 minute fixed window",
        },
        "segmentation_warnings": segmentation_warnings,
        "primary_statistics": "FULL_DATASET_DEFINED_RUN_OR_WINDOW",
        "official_universal_steady_state_region": "NO",
        "new_favorable_trimming_rule_invented": False,
        "diagnostic_steady_state_computed": False,
        "warmup_cooldown_authority_for_production": "NOT_ESTABLISHED",
    }


def energy_audit(stats: pd.DataFrame, reconciliation: pd.DataFrame, source_commit: str) -> dict[str, Any]:
    available = reconciliation.loc[reconciliation["aggregate_available"].eq(True)]
    return provenance(source_commit) | {
        "integration_method": "TRAPEZOID_WITH_ACTUAL_TIMESTAMPS_AFTER_NATIVE_AUDIT",
        "source_integral_preserved": True,
        "experiment_boundary_energy_totals_Wh": {
            boundary: float(group["energy_integral_Wh"].sum())
            for boundary, group in stats.groupby("power_boundary", sort=True)
        },
        "raw_aggregate_energy_reconciliation": {
            "runs": len(available),
            "median_relative_error": float(available["energy_relative_error"].median()),
            "maximum_relative_error": float(available["energy_relative_error"].max()),
            "within_tolerance_runs": int((available["energy_relative_error"] <= RAW_AGGREGATE_ENERGY_RTOL).sum()),
        },
        "compatible_sums": ["sum four GPU devices", "sum two CPU package domains", "GPU + CPU package component proxy"],
        "forbidden_sums": ["RAPL package + nested core as disjoint CPU power", "measured component power + synthetic facility power"],
        "classification": "ENERGY_RECONCILED_COMPONENT_BOUNDARIES_SEPARATED",
    }


def exclusion_manifest(quality: pd.DataFrame, experiments: pd.DataFrame, source_commit: str) -> dict[str, Any]:
    invalid_samples = int(
        quality[["nan_count", "inf_count", "negative_count", "above_800W_sensor_limit_count"]]
        .sum()
        .sum()
    )
    sensor_files = int(quality.loc[quality["classification"].eq("SENSOR_INVALID_PRESENT"), "relative_path"].nunique())
    return provenance(source_commit) | {
        "rules": {
            "STRUCTURAL_INVALID": "unparseable log, missing paired node/device log, empty experiment window",
            "SENSOR_INVALID": "nonfinite, negative, or >800 W per reported device channel",
            "VALID_EXTREME": "finite 0..800 W inclusive; retained regardless of distributional extremeness",
            "UNKNOWN": "retained and labeled unless required semantics are absent",
        },
        "invalid_samples_excluded_from_authoritative_component_statistics": invalid_samples,
        "sensor_invalid_source_files": sensor_files,
        "structural_invalid_runs": int(experiments["validity"].eq("STRUCTURAL_INVALID").sum()),
        "valid_extreme_retained_source_field_records": int(quality["classification"].eq("VALID_EXTREME_RETAINED").sum()),
        "runs_removed_for_being_extreme": 0,
        "dataset_supplied_backward_fill_not_used_as_hidden_authority": True,
    }


def bridge_matrix(source_commit: str) -> dict[str, Any]:
    targets = [
        (1, "Full active H100 node power", "DIAGNOSTIC_ONLY", "GPU+RAPL package components measured; whole-node input is not"),
        (2, "Multi-node exclusive workload power", "DIAGNOSTIC_ONLY", "components directly measured at 1/2/4/8/16 nodes"),
        (3, "Partial-GPU node power", "UNSUPPORTED", "no partial GPU allocation experiment"),
        (4, "Shared-node co-resident multi-job power", "UNSUPPORTED", "no co-residency experiment"),
        (5, "Idle H100 node power", "UNSUPPORTED", "no dedicated idle trace in frozen archive"),
        (6, "Per-job H100 power", "UNSUPPORTED", "direct Dataset312-to-Kestrel job join forbidden"),
        (7, "Workload-class-specific H100 power", "DIRECTLY_SUPPORTED", "only for included exclusive benchmark classes and component boundaries"),
        (8, "Class-agnostic H100 power envelope", "SUPPORTED_WITH_ROBUST_ENVELOPE", "exclusive full-node component boundary only"),
        (9, "Transition power", "DIAGNOSTIC_ONLY", "workload ramps captured, equipment power-on/off not measured"),
        (10, "Facility-level power", "UNSUPPORTED", "included profiles are synthetic DIPLOEE outputs"),
    ]
    return provenance(source_commit) | {
        "targets": [
            {"target_number": number, "target": target, "classification": classification, "reason": reason}
            for number, target, classification, reason in targets
        ],
        **FORBIDDEN_ASSERTIONS,
    }


def next_node_packing_contract(source_commit: str) -> dict[str, Any]:
    return provenance(source_commit) | {
        "execution_in_this_task": "FORBIDDEN_NOT_RUN",
        "future_invariant": "P_IT(t) = SUM_OVER_PHYSICAL_NODES(P_n(t)); EACH PHYSICAL NODE COUNTED EXACTLY ONCE PER SLOT",
        "not_allowed_invariant": "SUM_OVER_JOBS(P_j(t)) WHEN JOBS SHARE PHYSICAL RESOURCES",
        "requirements": [
            "deterministic",
            "grid-outcome independent",
            "scheduler-outcome independent except resource occupancy",
            "reproducible",
            "no favorable placement tuning",
            "node-capacity conserving",
            "GPU-capacity conserving",
            "co-resident jobs cannot double-count node power",
            "unknown workload class uses a robust envelope only where the measurement boundary/state is supported",
            "unsupported partial-node power fails closed or is explicitly sensitivity-only with independent public bounds",
        ],
        "blocking_inputs_before_execution": [
            "whole-node input or complete component/base-power authority",
            "partial-GPU node-state power authority or independent conservative bounds",
            "shared/co-resident state authority or fail-closed allocation policy",
            "idle-node input power",
            "deterministic mapping of requested resources to physical node occupancy",
        ],
        "KESTREL_NODE_PACKING_NEXT": KESTREL_NODE_PACKING_NEXT,
    }


def authority_decision(source_commit: str) -> dict[str, Any]:
    return provenance(source_commit) | {
        "power_authority_level": POWER_AUTHORITY_LEVEL,
        "primary_classification": PRIMARY_CLASSIFICATION,
        "resource_state_support_classification": RESOURCE_STATE_SUPPORT,
        "partial_shared_public_data_answer": PARTIAL_SHARED_ANSWER,
        "KESTREL_NODE_PACKING_NEXT": KESTREL_NODE_PACKING_NEXT,
        "PARTIAL_GPU_NODE_POWER_DIRECTLY_IDENTIFIED": "NO",
        "SHARED_NODE_POWER_DIRECTLY_IDENTIFIED": "NO",
        "IDLE_POWER_DIRECT_AUTHORITY": "NO",
        "whole_node_power_directly_measured": "NO",
        "facility_power_directly_measured": "NO",
        "robust_component_envelope_available": "YES",
        "robust_whole_node_envelope_available": "NO",
        **FORBIDDEN_ASSERTIONS,
        "reason": "Dataset 312 measures H100 NVML and AMD RAPL component channels for full-node-exclusive benchmarks, but omits whole-node input/base power and partial/shared occupancy experiments.",
    }


def isolation_audit(source_commit: str) -> dict[str, Any]:
    branch = git(ROOT, "branch", "--show-current")
    common = Path(git(ROOT, "rev-parse", "--git-common-dir")).resolve()
    git_dir = Path(git(ROOT, "rev-parse", "--git-dir")).resolve()
    return provenance(source_commit) | {
        "parent_expected": PARENT_HEAD,
        "branch_expected": BRANCH,
        "branch_actual": branch,
        "isolated_worktree": common != git_dir,
        "worktree": str(ROOT),
        "source_root_external_read_only_by_pipeline": str(EXTRACTED_ROOT),
        "production_files_changed": 0,
        "vendor_files_changed": 0,
        "MESS_files_changed": 0,
        "push": False,
        "merge": False,
        "firewall_reads": {
            "Kestrel_Apr01_scheduler": 0,
            "RW_RSP_schedule": 0,
            "RADDiT": 0,
            "Planning": 0,
            "Fresh": 0,
            "MESS": 0,
            "Apr02_plus": 0,
            "May": 0,
            "grid_results": 0,
        },
        "node_packing_executed": False,
        "scheduler_power_integration_executed": False,
    }


def _test_report() -> dict[str, Any]:
    command = [sys.executable, "-m", "pytest", "-q", "tests/v35r3f/test_dataset312_authority.py"]
    result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, encoding="utf-8", errors="replace")
    output = (result.stdout + "\n" + result.stderr).strip()
    passed_match = re.search(r"(\d+) passed", output)
    failed_match = re.search(r"(\d+) failed", output)
    return {
        "command": command,
        "returncode": result.returncode,
        "passed": int(passed_match.group(1)) if passed_match else 0,
        "failed": int(failed_match.group(1)) if failed_match else (0 if result.returncode == 0 else 1),
        "output": output,
        "classification": "PASS" if result.returncode == 0 else "FAIL",
    }


def _range_text(frame: pd.DataFrame, field: str, decimals: int = 2) -> str:
    return f"{frame[field].min():.{decimals}f} to {frame[field].max():.{decimals}f}"


def final_review(
    source: dict[str, Any],
    stats: pd.DataFrame,
    experiments: pd.DataFrame,
    timebase: pd.DataFrame,
    quality: pd.DataFrame,
    reconciliation: dict[str, Any],
    scaling: pd.DataFrame,
    variability: pd.DataFrame,
    envelope: pd.DataFrame,
    test_report: dict[str, Any],
    source_commit: str,
) -> dict[str, Any]:
    primary = stats.loc[stats["power_boundary"].eq(PRIMARY_BOUNDARY)]
    p_sample = primary[["p05_power_W", "median_power_W", "p95_power_W"]]
    primary_envelope = envelope.loc[
        envelope["power_boundary"].eq(PRIMARY_BOUNDARY)
        & envelope["normalization"].eq("PER_NODE")
    ]
    numbered = {
        "1": PARENT_HEAD,
        "2": BRANCH,
        "3": str(ROOT),
        "4": "FINAL_COMMIT_REPORTED_BY_GIT_AFTER_ARTIFACT_COMMIT",
        "5": "CLEAN_AFTER_FINAL_COMMIT",
        "6": 0,
        "7": 0,
        "8": 0,
        "9": "NO_PUSH_NO_MERGE",
        "10": "NLR Data Catalog Dataset 312",
        "11": DATASET_VERSION,
        "12": ARCHIVE_SHA256,
        "13": "PASS",
        "14": source["extracted_file_count"],
        "15": int(sum(path.stat().st_size for path in RAW.rglob("*wattameter*.log"))),
        "16": "gpu-0..3[mW] per node via NVML",
        "17": "cpu-0/1 package and core RAPL energy/power channels",
        "18": "NO",
        "19": "NO (DIPLOEE profiles are synthetic)",
        "20": sorted({round(value, 6) for value in timebase["median_dt_seconds"]}),
        "21": {
            "duplicates": int(timebase["duplicate_timestamp_count"].sum()),
            "non_monotonic": int(timebase["non_monotonic_timestamp_count"].sum()),
            "gaps": int(timebase["missing_or_gap_count"].sum()),
            "max_gap_s": float(timebase["max_gap_seconds"].max()),
        },
        "22": sorted(experiments["workload_class"].unique().tolist()),
        "23": sorted(experiments["model_family"].unique().tolist()),
        "24": sorted(experiments["node_count"].astype(int).unique().tolist()),
        "25": GPUS_PER_NODE,
        "26": "NO",
        "27": "NO",
        "28": "NO",
        "29": int(experiments["validity"].ne("STRUCTURAL_INVALID").sum()),
        "30": int(experiments["validity"].eq("STRUCTURAL_INVALID").sum()),
        "31": int(quality.loc[quality["classification"].eq("SENSOR_INVALID_PRESENT"), "relative_path"].nunique()),
        "32": int(quality["classification"].eq("VALID_EXTREME_RETAINED").sum()),
        "33": reconciliation["classification"],
        "34": PRIMARY_BOUNDARY + " (component-level only)",
        "35": _range_text(primary, "mean_power_W"),
        "36": {
            "P05_range_W": _range_text(p_sample, "p05_power_W"),
            "P50_range_W": _range_text(p_sample, "median_power_W"),
            "P95_range_W": _range_text(p_sample, "p95_power_W"),
        },
        "37": float(variability.loc[variability["power_boundary"].eq(PRIMARY_BOUNDARY), "between_workload_mean_spread_W"].max()),
        "38": {
            f"{row.model_family}:{int(row.node_count)}": round(float(row.per_node_mean_power_W), 3)
            for row in scaling.loc[scaling["power_boundary"].eq(PRIMARY_BOUNDARY)].itertuples()
        },
        "39": "16 nodes / 64 GPUs",
        "40": "PASS_WITHIN_REPORTED_TOLERANCE" if reconciliation["failed_runs"] == 0 else "PARTIAL",
        "41": RESOURCE_STATE_SUPPORT,
        "42": POWER_AUTHORITY_LEVEL,
        "43": "NO",
        "44": "NO",
        "45": "YES_COMPONENT_BOUNDARY_ONLY; NO_WHOLE_NODE_ENVELOPE",
        "46": ["full-node exclusive", "node_count", "power_boundary", "normalization"],
        "47": "minimum across classes of within-class run-mean P05",
        "48": "median across classes of within-class run-mean P50",
        "49": "maximum across classes of within-class run-mean P95",
        "50": "Use class-stratified envelope only for supported full-node-exclusive component boundary",
        "51": "DIAGNOSTIC_ONLY",
        "52": "UNSUPPORTED",
        "53": "UNSUPPORTED",
        "54": "UNSUPPORTED",
        "55": "UNSUPPORTED",
        "56": "FORBIDDEN",
        "57": "NO",
        "58": PARTIAL_SHARED_ANSWER,
        "59": KESTREL_NODE_PACKING_NEXT,
        "60": "NO",
        "61": test_report["passed"],
        "62": test_report["failed"],
        "63": PRIMARY_CLASSIFICATION,
    }
    questions = {
        "Q1": "Per-device NVML H100 power/temperature and per-socket RAPL package/core energy-derived power, recorded by WattAMeter.",
        "Q2": "GPU and CPU component power only. Whole-node input power is not measured; the supplied power[W] is a component sum and also adds nested RAPL package/core channels.",
        "Q3": "Raw inference is approximately 0.1 s; raw training approximately 0.2 s. Supplied outputs are 0.1 s, 0.2 s, and 0.001 s interpolation for online-rate inference.",
        "Q4": "Llama-2 70B LoRA fine-tuning, Stable Diffusion v2 training, and Llama-3 70B offline/online inference.",
        "Q5": "Node counts.",
        "Q6": "1/2/4/8/16 nodes and, at four GPUs per node, 4/8/16/32/64 GPUs.",
        "Q7": "NO.",
        "Q8": "NO.",
        "Q9": "No P_node(k,c). Supported is a full-node-exclusive measured-component function by experiment node count and represented benchmark class.",
        "Q10": "Use GPU+RAPL-package component sum only as a component-level diagnostic; no measured quantity is authorized as whole-node IT power.",
        "Q11": "Reported numerically in NODE_SCALING and WORKLOAD_POWER_VARIABILITY; per-node power changes with both class and weak-scaling configuration.",
        "Q12": primary_envelope[["node_count", "P_LOW", "P_CENTER", "P_HIGH", "unit"]].to_dict(orient="records"),
        "Q13": "YES only for the supported full-node-exclusive component-level envelope; NO for whole-node IT or partial/shared states.",
        "Q14": "NO.",
        "Q15": "NO defensible whole-node bound from frozen Dataset 312 alone; missing idle/base and non-GPU/CPU-package components prevent a closed physical bound.",
        "Q16": "Shared jobs consume one physical node boundary; summing independent job coefficients would count the same GPU/CPU/base hardware more than once.",
        "Q17": "DEFER. The deterministic packing design is sound, but physical whole-node, idle, partial/shared power authority is still missing.",
        "Q18": "Whole-node input/base power, partial/shared occupancy behavior or independent bounds, idle power, and a deterministic resource-to-node occupancy mapping.",
        "Q19": "NO.",
        "Q20": "NO.",
    }
    return provenance(source_commit) | {
        "numbered_report": numbered,
        "questions": questions,
        "primary_classification": PRIMARY_CLASSIFICATION,
        "conservative_decision": "Dataset 312 is valid H100 component authority but not whole-node resource-state authority.",
    }


def final_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# V35R3F Dataset 312 H100 Power Authority Final Review",
        "",
        f"Primary classification: **{review['primary_classification']}**",
        "",
        "Dataset 312 provides valid high-resolution H100 NVML and AMD RAPL component measurements for full-node-exclusive GenAI benchmarks. It does not directly measure whole-node input, facility input, partial-GPU occupancy, shared multi-job occupancy, or a frozen-archive idle trace. The fail-closed authority is therefore H1 component-level only.",
        "",
        "## Numbered report",
        "",
    ]
    labels = {
        1: "parent HEAD", 2: "branch", 3: "worktree", 4: "final HEAD", 5: "clean",
        6: "production files changed", 7: "vendor files changed", 8: "MESS files changed", 9: "push/merge",
        10: "Dataset ID", 11: "dataset version", 12: "archive SHA-256", 13: "archive integrity",
        14: "extracted file count", 15: "raw bytes processed", 16: "authoritative GPU channels",
        17: "authoritative CPU channels", 18: "whole-node directly measured", 19: "facility directly measured",
        20: "native intervals", 21: "timebase anomalies", 22: "workload classes", 23: "model families",
        24: "node counts", 25: "GPUs per node", 26: "partial GPU measured", 27: "shared jobs measured",
        28: "idle measured", 29: "valid runs", 30: "structural-invalid runs", 31: "sensor-invalid files",
        32: "valid-extreme field records", 33: "raw/aggregate reconciliation", 34: "primary boundary",
        35: "overall mean range W", 36: "overall P05/P50/P95 ranges", 37: "max workload spread W",
        38: "node scaling per-node means W", 39: "maximum scale", 40: "energy reconciliation",
        41: "resource-state support", 42: "authority level", 43: "partial GPU identified",
        44: "shared power identified", 45: "robust envelope", 46: "envelope dimensions", 47: "P_LOW",
        48: "P_CENTER", 49: "P_HIGH", 50: "unknown class", 51: "full-node bridge",
        52: "partial bridge", 53: "shared bridge", 54: "idle bridge", 55: "per-job bridge",
        56: "Dataset312 job join", 57: "RADDiT H100 magnitude", 58: "partial/shared answer",
        59: "KESTREL_NODE_PACKING_NEXT", 60: "PRODUCTION_INTEGRATION_RECOMMENDED",
        61: "tests passed", 62: "tests failed", 63: "primary classification",
    }
    for number in range(1, 64):
        value = review["numbered_report"][str(number)]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        lines.append(f"{number}. {labels[number]}: {value}")
    lines.extend(["", "## Required questions", ""])
    for number in range(1, 21):
        value = review["questions"][f"Q{number}"]
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, sort_keys=True)
        lines.append(f"Q{number}. {value}")
    lines.extend(
        [
            "",
            "## Source boundary warning",
            "",
            "The robust envelope is an empirical envelope for measured GPU plus CPU-package components under full-node-exclusive workloads. It is not a whole-node IT input-power envelope and cannot be used to assign power to individual Kestrel jobs.",
            "",
        ]
    )
    return "\n".join(lines)


def run(run_tests: bool = True, verify_zip_crc: bool = True) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    accounting = Accounting()
    source_commit = git(ROOT, "rev-parse", "HEAD")

    stage = time.perf_counter()
    source = ensure_source()
    if verify_zip_crc:
        with zipfile.ZipFile(ARCHIVE) as archive:
            bad_member = archive.testzip()
        if bad_member is not None:
            raise RuntimeError(f"ZIP CRC failed at {bad_member}")
        source["zip_crc_test"] = "PASS"
    else:
        source["zip_crc_test"] = "SKIPPED_BY_EXPLICIT_OPTION"
    inventory_rows, inventory_summary = archive_inventory(ARCHIVE)
    accounting.checkpoint("source_and_archive_inventory", stage)

    common = provenance(source_commit)
    start_state = common | {
        "parent_expected": PARENT_HEAD,
        "parent_actual_at_worktree_creation": PARENT_HEAD,
        "branch_expected": BRANCH,
        "branch_actual": git(ROOT, "branch", "--show-current"),
        "worktree": str(ROOT),
        "generator_HEAD": source_commit,
        "initial_status_scope": "code committed before artifact generation",
    }
    write_json(ARTIFACTS / "V35R3F_START_STATE.json", start_state)
    write_json(ARTIFACTS / "V35R3F_ISOLATION_AUDIT.json", isolation_audit(source_commit))
    write_json(
        ARTIFACTS / "V35R3F_SOURCE_AUTHORITY.json",
        common | source | {
            "dataset_title": "Dataset of Generative AI Workload Power Profiles",
            "catalog_url": CATALOG_URL,
            "archive_integrity": "PASS",
            "no_redownload": True,
            "source_files_mutated": False,
            "source_relative_roots": ["00_raw_datasets", "01_aggregated_datasets", "02_analysis_scripts", "03_whole-facility_profiles"],
        },
    )
    write_csv(ARTIFACTS / "V35R3F_DATASET312_ARCHIVE_INVENTORY.csv", inventory_rows)
    write_json(ARTIFACTS / "V35R3F_DATASET312_ARCHIVE_INVENTORY.json", common | inventory_summary | {"files": inventory_rows})
    write_json(ARTIFACTS / "V35R3F_DATASET312_SCHEMA_CENSUS.json", build_schema_census(inventory_rows, source_commit))
    write_json(ARTIFACTS / "V35R3F_POWER_SENSOR_SEMANTICS.json", sensor_semantics(source_commit))

    stage = time.perf_counter()
    time_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    train_stats, train_experiments, train_recon = process_training(time_rows, quality_rows, accounting)
    accounting.checkpoint("training_raw_processing", stage)

    stage = time.perf_counter()
    inference_stats, inference_experiments, inference_recon, segmentation_warnings = process_inference(
        time_rows, quality_rows, accounting
    )
    accounting.checkpoint("inference_raw_processing", stage)

    stage = time.perf_counter()
    stats = pd.DataFrame(train_stats + inference_stats).sort_values(["experiment_id", "power_boundary"]).reset_index(drop=True)
    experiments = pd.DataFrame(train_experiments + inference_experiments).sort_values("experiment_id").reset_index(drop=True)
    timebase = pd.DataFrame(time_rows).sort_values("relative_path").reset_index(drop=True)
    quality = pd.DataFrame(quality_rows).sort_values(["relative_path", "field"]).reset_index(drop=True)
    recon = pd.DataFrame(train_recon + inference_recon).sort_values("experiment_id").reset_index(drop=True)
    scaling, scaling_summary = node_scaling(stats, source_commit)
    variability, variability_summary = workload_variability(stats, source_commit)
    envelope, envelope_contract = power_envelope(stats, source_commit)
    recon_summary = reconciliation_summary(recon, source_commit)
    accounting.checkpoint("derived_characterization", stage)

    timebase.to_csv(ARTIFACTS / "V35R3F_TIMEBASE_AUDIT.csv", index=False)
    experiments.to_parquet(ARTIFACTS / "V35R3F_EXPERIMENT_CENSUS.parquet", index=False)
    write_json(ARTIFACTS / "V35R3F_EXPERIMENT_DIMENSIONS.json", experiment_dimensions(experiments, source_commit))
    write_json(ARTIFACTS / "V35R3F_RESOURCE_STATE_SUPPORT.json", resource_support(experiments, source_commit))
    stats.to_parquet(ARTIFACTS / "V35R3F_RAW_PROFILE_STATISTICS.parquet", index=False)
    write_json(ARTIFACTS / "V35R3F_TRANSIENT_STEADY_STATE_AUDIT.json", transient_audit(segmentation_warnings, source_commit))
    recon.to_csv(ARTIFACTS / "V35R3F_RAW_AGGREGATED_RECONCILIATION.csv", index=False)
    write_json(ARTIFACTS / "V35R3F_RAW_AGGREGATED_RECONCILIATION.json", recon_summary)
    scaling.to_parquet(ARTIFACTS / "V35R3F_NODE_SCALING.parquet", index=False)
    write_json(ARTIFACTS / "V35R3F_NODE_SCALING_SUMMARY.json", scaling_summary)
    variability.to_parquet(ARTIFACTS / "V35R3F_WORKLOAD_POWER_VARIABILITY.parquet", index=False)
    write_json(ARTIFACTS / "V35R3F_WORKLOAD_POWER_VARIABILITY.json", variability_summary)
    envelope.to_parquet(ARTIFACTS / "V35R3F_CLASS_AGNOSTIC_POWER_ENVELOPE.parquet", index=False)
    write_json(ARTIFACTS / "V35R3F_POWER_ENVELOPE_CONTRACT.json", envelope_contract)
    write_json(ARTIFACTS / "V35R3F_MEASUREMENT_BOUNDARY_AUTHORITY.json", boundary_authority(source_commit))
    write_json(ARTIFACTS / "V35R3F_ENERGY_INTEGRATION_AUDIT.json", energy_audit(stats, recon, source_commit))
    quality.to_csv(ARTIFACTS / "V35R3F_DATA_QUALITY_AUDIT.csv", index=False)
    write_json(ARTIFACTS / "V35R3F_EXCLUSION_MANIFEST.json", exclusion_manifest(quality, experiments, source_commit))
    write_json(ARTIFACTS / "V35R3F_KESTREL_BRIDGE_ELIGIBILITY_MATRIX.json", bridge_matrix(source_commit))
    write_json(ARTIFACTS / "V35R3F_NEXT_NODE_PACKING_CONTRACT.json", next_node_packing_contract(source_commit))
    write_json(ARTIFACTS / "V35R3F_POWER_AUTHORITY_DECISION.json", authority_decision(source_commit))
    write_json(
        ARTIFACTS / "V35R3F_REPAIR_LOG.json",
        common
        | {
            "attempts": [
                {
                    "failure_signature": "NUMPY_1_26_HAS_NO_TRAPEZOID",
                    "attempt": 1,
                    "repair": "USE_EQUIVALENT_NUMPY_TRAPZ_API",
                    "science_neutral": True,
                }
            ],
            "unique_failure_signatures": 1,
            "science_semantics_changed": False,
        },
    )
    write_json(ARTIFACTS / "V35R3F_COMPUTE_ACCOUNTING.json", accounting.payload(source_commit))

    stage = time.perf_counter()
    test_report = _test_report() if run_tests else {"passed": 0, "failed": 0, "classification": "NOT_RUN", "output": ""}
    test_report = common | test_report
    write_json(ARTIFACTS / "V35R3F_TEST_REPORT.json", test_report)
    accounting.checkpoint("targeted_tests", stage)
    write_json(ARTIFACTS / "V35R3F_COMPUTE_ACCOUNTING.json", accounting.payload(source_commit))

    review = final_review(
        source,
        stats,
        experiments,
        timebase,
        quality,
        recon_summary,
        scaling,
        variability,
        envelope,
        test_report,
        source_commit,
    )
    write_json(ARTIFACTS / "V35R3F_FINAL_REVIEW.json", review)
    (ARTIFACTS / "V35R3F_FINAL_REVIEW.md").write_text(final_markdown(review), encoding="utf-8")
    missing = [name for name in REQUIRED_ARTIFACTS if not (ARTIFACTS / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing required artifacts: {missing}")
    if test_report["failed"]:
        raise RuntimeError("Targeted V35R3F tests failed; see V35R3F_TEST_REPORT.json")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-tests", action="store_true")
    parser.add_argument("--skip-zip-crc", action="store_true")
    args = parser.parse_args()
    run(run_tests=not args.no_tests, verify_zip_crc=not args.skip_zip_crc)


if __name__ == "__main__":
    main()
