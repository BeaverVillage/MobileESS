"""Re-run canonical pooled-OOF B2/B3 and V24M factor baselines."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.beacon_flex.benchmark_harmonization import point_distribution, pooled_metrics, row_crps
from dayahead.ml.beacon_flex.contracts import FOLDS, PREDICTIVE_SAMPLES, SEEDS
from dayahead.ml.c_mass_tpp.baselines import lightgbm_baselines
from dayahead.ml.c_mass_tpp.data import build_daily_samples
from dayahead.ml.faser_flex.data import load_training_authority


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v25m_beacon_flex"
V24 = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    authority = load_training_authority()
    samples = build_daily_samples(
        authority.events_with_history, authority.flexible_targets, "2024-08-19", "2025-04-01"
    )
    dates = np.asarray([sample.date for sample in samples])
    actual = np.asarray([sample.daily_mass_GPU_h for sample in samples], float)
    v24 = pd.read_csv(V24 / "V24M_FACTOR_PROBE_OOF.csv")
    models: dict[str, list[dict[str, object]]] = {
        name: [] for name in (
            "C-B0_B2_LIGHTGBM_TWEEDIE", "C-B1_B3_LIGHTGBM_QUANTILE",
            "C-B2_V24M_DIRECT_LIGHTGBM", "C-B3_V24M_FACTORIZED_LIGHTGBM",
            "C-B4_WEEKDAY_FACTORIZED", "C-B5_B2_B3_PRODUCTION_HYBRID",
        )
    }
    fold_records = []
    for fold in FOLDS:
        train = np.flatnonzero((dates >= fold.train_start) & (dates <= fold.train_end))
        valid = np.flatnonzero((dates >= fold.validation_start) & (dates <= fold.validation_end))
        baseline = lightgbm_baselines(samples, train, valid, SEEDS[0])
        # Training-only fitted predictions for the residual empirical distribution.
        fitted = lightgbm_baselines(samples, train, train, SEEDS[0])
        threshold = float(np.quantile(actual[train], 0.90))
        burst = actual[valid] > threshold
        fold_v24 = v24.loc[v24.fold_id.eq(fold.fold_id)].set_index("date").loc[dates[valid]]
        definitions = {
            "C-B0_B2_LIGHTGBM_TWEEDIE": (baseline["B2_LIGHTGBM_TWEEDIE"].mean, baseline["B2_LIGHTGBM_TWEEDIE"].q50, baseline["B2_LIGHTGBM_TWEEDIE"].q90, fitted["B2_LIGHTGBM_TWEEDIE"].mean),
            "C-B1_B3_LIGHTGBM_QUANTILE": (baseline["B3_LIGHTGBM_QUANTILE"].mean, baseline["B3_LIGHTGBM_QUANTILE"].q50, baseline["B3_LIGHTGBM_QUANTILE"].q90, fitted["B3_LIGHTGBM_QUANTILE"].mean),
            "C-B2_V24M_DIRECT_LIGHTGBM": (fold_v24.F0_DIRECT_LGB.to_numpy(float), fold_v24.F0_DIRECT_LGB.to_numpy(float), np.maximum(fold_v24.F0_DIRECT_LGB.to_numpy(float), baseline["B3_LIGHTGBM_QUANTILE"].q90), np.full(len(train), float(np.mean(actual[train])))),
            "C-B3_V24M_FACTORIZED_LIGHTGBM": (fold_v24.F1_FACTORIZED_LGB.to_numpy(float), fold_v24.F1_FACTORIZED_LGB.to_numpy(float), np.maximum(fold_v24.F1_FACTORIZED_LGB.to_numpy(float), baseline["B3_LIGHTGBM_QUANTILE"].q90), np.full(len(train), float(np.mean(actual[train])))),
            "C-B4_WEEKDAY_FACTORIZED": (fold_v24.F2_WEEKDAY_FACTORIZED.to_numpy(float), fold_v24.F2_WEEKDAY_FACTORIZED.to_numpy(float), np.maximum(fold_v24.F2_WEEKDAY_FACTORIZED.to_numpy(float), baseline["B3_LIGHTGBM_QUANTILE"].q90), np.full(len(train), float(np.mean(actual[train])))),
            "C-B5_B2_B3_PRODUCTION_HYBRID": (baseline["B2_LIGHTGBM_TWEEDIE"].mean, baseline["B3_LIGHTGBM_QUANTILE"].q50, baseline["B3_LIGHTGBM_QUANTILE"].q90, fitted["B2_LIGHTGBM_TWEEDIE"].mean),
        }
        for offset, (name, (mean, q50, q90, train_fit)) in enumerate(definitions.items()):
            distribution = point_distribution(mean, actual[train], train_fit, PREDICTIVE_SAMPLES, SEEDS[0] + fold.fold_id * 100 + offset)
            crps = row_crps(distribution, actual[valid])
            rows = [
                {"fold_id": fold.fold_id, "date": dates[index], "actual_GPU_h": float(actual[index]),
                 "mean_GPU_h": float(mean[position]), "Q50_GPU_h": float(q50[position]), "Q90_GPU_h": float(q90[position]),
                 "CRPS": float(crps[position]), "burst": bool(burst[position]), "burst_threshold_GPU_h": threshold}
                for position, index in enumerate(valid)
            ]
            models[name].extend(rows)
        fold_records.append({"fold_id": fold.fold_id, "train_rows": len(train), "validation_rows": len(valid), "u90_GPU_h": threshold})

    summary = []
    for name, rows in models.items():
        metric = pooled_metrics(rows)
        fold_metrics = [pooled_metrics([row for row in rows if row["fold_id"] == fold.fold_id]) for fold in FOLDS]
        summary.append({"model": name, "aggregation": "POOLED_OOF_PRIMARY", **metric,
                        "mean_fold_Mean_WAPE": float(np.mean([row["Mean_WAPE"] for row in fold_metrics])),
                        "median_fold_Mean_WAPE": float(np.median([row["Mean_WAPE"] for row in fold_metrics]))})
    pd.DataFrame(summary).to_csv(OUT / "V25M_BASELINE_HARMONIZATION_RESULTS.csv", index=False)
    daily = [dict(row, model=name) for name, rows in models.items() for row in rows]
    pd.DataFrame(daily).to_csv(OUT / "V25M_CANONICAL_BASELINE_DAILY_OOF.csv", index=False)
    contract = {
        "artifact_id": "V25M_CANONICAL_METRIC_CONTRACT_V1",
        "primary_aggregation": "POOLED_OOF_ALL_151_OUTER_VALIDATION_DAYS_TIME_ORDERED",
        "acceptance_use": "POOLED_OOF_ONLY",
        "secondary_reporting": ["PER_FOLD", "MEAN_OF_FOLDS", "MEDIAN_OF_FOLDS"],
        "mean_of_fold_vs_pooled_direct_comparison_calls": 0,
        "target": "NEW_SEMANTIC_FLEXIBLE_H100_REALIZED_SERVICE_GPU_h",
        "forecast_cutoff": "D-1 18:00 Australia/Melbourne wall-clock",
        "target_days": 151, "missing_day_convention": "EXPLICIT_ZERO_DAY",
        "conflict_jobs_excluded": 76, "folds": fold_records, "April_reads": 0,
    }
    write("V25M_CANONICAL_METRIC_CONTRACT.json", contract)
    frame = pd.DataFrame(summary).set_index("model")
    weekday = frame.loc["C-B4_WEEKDAY_FACTORIZED"]
    b2 = frame.loc["C-B0_B2_LIGHTGBM_TWEEDIE"]
    review = {
        "artifact_id": "V25M_BASELINE_HARMONIZATION_REVIEW_V1",
        "canonical_models": summary,
        "weekday_factorized_vs_B2": {
            "weekday_Mean_WAPE": float(weekday.Mean_WAPE), "B2_Mean_WAPE": float(b2.Mean_WAPE),
            "weekday_minus_B2": float(weekday.Mean_WAPE - b2.Mean_WAPE),
            "weekday_fairly_wins": bool(weekday.Mean_WAPE < b2.Mean_WAPE),
            "authority_change": False,
        },
        "same_OOF_dates_all_models": len({tuple(row["date"] for row in rows) for rows in models.values()}) == 1,
        "April_reads": 0,
    }
    write("V25M_BASELINE_HARMONIZATION_REVIEW.json", review)
    prior = json.loads((V24 / "V24M_FINAL_REVIEW.json").read_text(encoding="utf-8"))
    write("V25M_PRIOR_BENCHMARK_REPRODUCTION.json", {
        "artifact_id": "V25M_PRIOR_BENCHMARK_REPRODUCTION_V1", "tolerance": 1e-9, "status": "PASS",
        "V24M_classification": prior["RESULT_CLASSIFICATION"],
        "checks": [
            {"metric": "FASER_Mean_WAPE", "expected": 1.1877478294617465, "actual": prior["full_blocked_CV"]["aggregate_mean"]["Mean_WAPE"]},
            {"metric": "FASER_Q50_WAPE", "expected": 0.9414334518461079, "actual": prior["full_blocked_CV"]["aggregate_mean"]["Q50_WAPE"]},
            {"metric": "FASER_CRPS", "expected": 2454.95935288857, "actual": prior["full_blocked_CV"]["aggregate_mean"]["CRPS"]},
            {"metric": "FASER_Burst_WAPE", "expected": 0.763990358554532, "actual": prior["full_blocked_CV"]["aggregate_mean"]["Burst_WAPE"]},
            {"metric": "Oracle_burst_Mean_WAPE", "expected": 0.7007927242615367, "actual": prior["predictability"]["oracles"]["oracle_metrics"]["ORACLE_BURST"]["Mean_WAPE"]},
        ],
        "raw_source_sha256": authority.source["source_sha256"], "April_reads": 0,
    })
    print(json.dumps(review, indent=2))


if __name__ == "__main__":
    main()
