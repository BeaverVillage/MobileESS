#!/usr/bin/env python3
"""Fit and freeze the already-selected V28 LightGBM authority variants."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DATA_SPEC = importlib.util.spec_from_file_location(
    "v28_cmass_data", REPO / "dayahead/ml/c_mass_tpp/data.py"
)
if DATA_SPEC is None or DATA_SPEC.loader is None:
    raise RuntimeError("V28_CANNOT_LOAD_FROZEN_CMASSTPP_DATA_MODULE")
DATA = importlib.util.module_from_spec(DATA_SPEC)
sys.modules[DATA_SPEC.name] = DATA
DATA_SPEC.loader.exec_module(DATA)
TRAIN_START = DATA.TRAIN_START
build_daily_samples = DATA.build_daily_samples


OUT = REPO / "dayahead" / "artifacts" / "v28_final_dayahead_actual"
MODELS = OUT / "V28_FINAL_LIGHTGBM_FORECAST_MODELS"
SEED = 20260901
COMMON = {
    "n_estimators": 120,
    "learning_rate": 0.035,
    "num_leaves": 7,
    "min_child_samples": 12,
    "max_depth": 3,
    "reg_lambda": 1.0,
    "random_state": SEED,
    "deterministic": True,
    "verbosity": -1,
    "n_jobs": 1,
}
FEATURES = [
    "job_count_6h", "job_count_12h", "job_count_24h",
    "requested_gpus_6h", "requested_gpus_12h", "requested_gpus_24h",
    "requested_GPU_h_D1", "requested_GPU_h_D2", "requested_GPU_h_D7",
    "requested_GPU_h_mean_7d", "requested_GPU_h_std_7d", "requested_GPU_h_mean_14d",
    "weekday_sin", "weekday_cos", "weekend", "victoria_holiday", "month_sin", "month_cos",
]


def load_training_authority() -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Open July 2024 through March 2025 only without importing rejected model code."""

    raw, source = DATA.load_h100_source(min_month=202407, max_month=202503)
    if pd.api.types.is_timedelta64_dtype(raw["wallclock_req"].dtype):
        raw["wallclock_req_h"] = raw["wallclock_req"].dt.total_seconds() / 3600.0
    else:
        raw["wallclock_req_h"] = pd.to_numeric(raw["wallclock_req"], errors="coerce") / 3600.0
    events = DATA.source_valid_input_events(raw)
    flexible = DATA.semantic_flexible_targets(
        raw, TRAIN_START, "2025-04-01", DATA.conflict_ids()
    )
    source = {**source, "April_members_opened": 0, "target_month_max": 202503}
    return events, flexible, source


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def fit_variant(samples: list, training_end: str, variant: str) -> dict[str, object]:
    selected = [sample for sample in samples if sample.date <= training_end]
    x = np.stack([sample.macro_features for sample in selected])
    y = np.asarray([sample.daily_mass_GPU_h for sample in selected], dtype=np.float64)
    MODELS.mkdir(parents=True, exist_ok=True)
    definitions = {
        "mean": {"objective": "tweedie", "tweedie_variance_power": 1.5},
        "q50": {"objective": "quantile", "alpha": 0.5},
        "q90": {"objective": "quantile", "alpha": 0.9},
    }
    hashes = {}
    for statistic, special in definitions.items():
        model = LGBMRegressor(**special, **COMMON)
        model.fit(x, y)
        path = MODELS / f"{variant}_{statistic}.txt"
        # LightGBM's Windows C API cannot write through this repository's
        # Korean path, while Python can preserve the exact model text safely.
        path.write_text(model.booster_.model_to_string(), encoding="utf-8", newline="\n")
        hashes[statistic] = sha256(path)
    return {"variant": variant, "training_end": training_end, "training_rows": len(selected), "model_sha256": hashes}


def main() -> None:
    events, flexible, source = load_training_authority()
    samples = build_daily_samples(events, flexible, TRAIN_START, "2025-04-01")
    variants = [
        fit_variant(samples, "2025-03-30", "APRIL_01_CAUSAL_FIT"),
        fit_variant(samples, "2025-03-31", "GENERAL_THROUGH_MARCH_31_FIT"),
    ]
    benchmark_source = REPO / "dayahead/artifacts/v25m_beacon_flex/V25M_BASELINE_HARMONIZATION_RESULTS.csv"
    oof_source = REPO / "dayahead/artifacts/v25m_beacon_flex/V25M_CANONICAL_BASELINE_DAILY_OOF.csv"
    shutil.copyfile(benchmark_source, OUT / "V28_FINAL_LIGHTGBM_BENCHMARKS.csv")
    shutil.copyfile(oof_source, OUT / "V28_FINAL_LIGHTGBM_OOF.csv")
    benchmark = pd.read_csv(benchmark_source).set_index("model")
    mean = benchmark.loc["C-B0_B2_LIGHTGBM_TWEEDIE"]
    quantile = benchmark.loc["C-B1_B3_LIGHTGBM_QUANTILE"]
    config = {
        "artifact_id": "V28_FINAL_LIGHTGBM_CONFIG_V1",
        "seed": SEED,
        "common": COMMON,
        "mean": {"model_id": "B2_LIGHTGBM_TWEEDIE", "objective": "tweedie", "tweedie_variance_power": 1.5},
        "Q50": {"model_id": "B3_LIGHTGBM_QUANTILE", "objective": "quantile", "alpha": 0.5},
        "Q90": {"model_id": "B3_LIGHTGBM_QUANTILE", "objective": "quantile", "alpha": 0.9},
        "inner_temporal_CV_tweedie_power_candidates": [1.1, 1.3, 1.5, 1.7, 1.9],
        "maximum_HPO_trials_per_target": 50,
        "new_V28_HPO_trials": 0,
        "reason": "V27 already froze the accepted conventional authority; V28 does not reopen model development",
        "variants": variants,
    }
    calibration = {
        "artifact_id": "V28_FINAL_LIGHTGBM_CALIBRATION_V1",
        "Q50_coverage": float(quantile.Q50_coverage),
        "Q90_coverage": float(quantile.Q90_coverage),
        "Q50_preferred_range": [0.45, 0.55],
        "Q90_preferred_range": [0.85, 0.95],
        "selected": "RAW_LIGHTGBM_QUANTILES",
        "post_March_calibration_rows": 0,
    }
    features = {
        "artifact_id": "V28_FINAL_LIGHTGBM_FEATURES_V1",
        "feature_names": FEATURES,
        "feature_count": len(FEATURES),
        "causal_boundary": "strictly before D-1 18:00 fixed AEST",
        "future_job_information": False,
    }
    schema = {
        "artifact_id": "V28_FINAL_AIDC_FORECAST_SCHEMA_V1",
        "resolution_minutes": 15,
        "slots_per_day": 96,
        "daily_statistics": ["conditional_mean_GPU_h", "Q50_GPU_h", "Q90_GPU_h"],
        "mean_is_Q50_copy": False,
        "optimizer_channels": ["IT_reference_load", "fixed_compute_load", "flexible_workload_arrivals", "time_power_tier_latency_tensor"],
        "site_axis": [f"AIDC{i:02d}" for i in range(1, 13)],
        "site_disaggregation_claim": "ENGINEERING_AIDC_ALLOCATION_BY_FROZEN_SITE_WEIGHT",
        "mass_tolerance_GPU_h": 1e-9,
    }
    final = {
        "artifact_id": "V28_FINAL_LIGHTGBM_AUTHORITY_V1",
        "status": "FINAL_LIGHTGBM_AUTHORITY_READY",
        "training_start": TRAIN_START,
        "general_training_end": "2025-03-31",
        "April_01_training_end": "2025-03-30",
        "April_training_rows": 0,
        "May_training_rows": 0,
        "mean_authority": "B2_LIGHTGBM_TWEEDIE",
        "mean_pooled_OOF_daily_WAPE": float(mean.Mean_WAPE),
        "Q50_authority": "B3_LIGHTGBM_QUANTILE_RAW",
        "Q90_authority": "B3_LIGHTGBM_QUANTILE_RAW",
        "Q50_pinball_proxy_selection_source": "V21/V25 canonical blocked OOF authority",
        "flexibility_envelope": "BL2_DIRECT_LIGHTGBM_AGGREGATE_ENVELOPE",
        "rejected_production_models": ["C-MASS-TPP", "RACQ-Flex", "ACQ-Flex", "FASER-Flex", "BEACON-Flex", "SAFE-Flex", "SAFE-Flex R1"],
        "model_variants": variants,
        "source_sha256": source["source_sha256"],
        "FINAL_LIGHTGBM_AUTHORITY_READY": True,
    }
    write_json("V28_FINAL_LIGHTGBM_CONFIG.json", config)
    write_json("V28_FINAL_LIGHTGBM_FEATURES.json", features)
    write_json("V28_FINAL_LIGHTGBM_CALIBRATION.json", calibration)
    write_json("V28_FINAL_AIDC_FORECAST_SCHEMA.json", schema)
    write_json("V28_FINAL_LIGHTGBM_AUTHORITY.json", final)
    (OUT / "V28_FINAL_LIGHTGBM_AUTHORITY.md").write_text(
        "# V28 final LightGBM authority\n\n"
        "Conditional mean: B2 LightGBM Tweedie. Q50/Q90: raw B3 LightGBM Quantile. "
        "The mean is never copied from Q50. April 1 uses the March 30 causal-fit variant; "
        "all later April and May dates use the March 31 variant. No April or May target is used for fitting, HPO, or calibration.\n",
        encoding="utf-8", newline="\n",
    )
    hashes = {}
    for path in sorted(OUT.glob("V28_FINAL_LIGHTGBM*")):
        if path.name == "V28_FINAL_LIGHTGBM_SHA256.json" or path.is_dir():
            continue
        hashes[path.relative_to(REPO).as_posix()] = sha256(path)
    for path in sorted(MODELS.glob("*.txt")):
        hashes[path.relative_to(REPO).as_posix()] = sha256(path)
    write_json("V28_FINAL_LIGHTGBM_SHA256.json", {"artifact_id": "V28_FINAL_LIGHTGBM_SHA256_V1", "files": hashes})


if __name__ == "__main__":
    main()
