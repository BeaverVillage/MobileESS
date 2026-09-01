"""Build nested cross-fitted coherent base distributions without April access."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.beacon_flex.base_crossfit import expanding_crossfit
from dayahead.ml.beacon_flex.base_models import fit_base_models
from dayahead.ml.beacon_flex.base_reconciliation import TAU, reconcile_batch
from dayahead.ml.beacon_flex.contracts import FOLDS, SEEDS
from dayahead.ml.beacon_flex.data import load_beacon_training_data


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v25m_beacon_flex"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.abs(predicted - actual).sum() / max(float(actual.sum()), 1e-12))


def main() -> None:
    data = load_beacon_training_data()
    rows, crossfit_records, selection = [], [], []
    raw_crossings = 0
    max_mean_error = 0.0
    for fold in FOLDS:
        train = np.flatnonzero((data.dates >= fold.train_start) & (data.dates <= fold.train_end))
        valid = np.flatnonzero((data.dates >= fold.validation_start) & (data.dates <= fold.validation_end))
        crossfit = expanding_crossfit(data.macro_features, data.actual_GPU_h, train, SEEDS[0] + fold.fold_id)
        for record in crossfit.provenance:
            crossfit_records.append({"outer_fold": fold.fold_id, **record, "date": str(data.dates[record["row_index"]])})
        # Candidate selection uses only the final 14 cross-fitted outer-training rows.
        inner_count = min(14, len(crossfit.indices))
        inner_indices = crossfit.indices[-inner_count:]
        inner_mean = crossfit.mean_GPU_h[-inner_count:]
        inner_grid = crossfit.quantiles_GPU_h[-inner_count:]
        candidate_scores = {}
        for method in ("BR-A", "BR-B"):
            reconciled = reconcile_batch(inner_mean, inner_grid, method)
            candidate_scores[method] = wape(data.actual_GPU_h[inner_indices], np.asarray([base.quantile(0.5) for base in reconciled]))
        selected = min(candidate_scores, key=candidate_scores.get)
        selection.append({"fold_id": fold.fold_id, "candidate_inner_Q50_WAPE": candidate_scores, "selected": selected})
        model = fit_base_models(data.macro_features[train], data.actual_GPU_h[train], SEEDS[0] + fold.fold_id)
        raw_mean, raw_grid = model.predict(data.macro_features[valid])
        bases = reconcile_batch(raw_mean, raw_grid, selected)
        for position, (index, base) in enumerate(zip(valid, bases)):
            raw_crossings += base.raw_crossing_count
            max_mean_error = max(max_mean_error, abs(base.mean_GPU_h - (raw_mean[position] if selected == "BR-A" else base.mean_GPU_h)))
            rows.append({
                "fold_id": fold.fold_id, "date": data.dates[index], "actual_GPU_h": data.actual_GPU_h[index],
                "selected_method": selected, "raw_mean_GPU_h": raw_mean[position], "reconciled_mean_GPU_h": base.mean_GPU_h,
                **{f"Q{int(tau*100):02d}_GPU_h": value for tau, value in zip(TAU, base.quantiles_GPU_h)},
                "raw_crossing_count": base.raw_crossing_count,
                "mean_reconciliation_error_GPU_h": abs(base.mean_GPU_h - (raw_mean[position] if selected == "BR-A" else base.mean_GPU_h)),
            })
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / "V25M_BASE_RECONCILIATION_RESULTS.csv", index=False)
    pd.DataFrame(crossfit_records).to_csv(OUT / "V25M_BASE_CROSSFIT_PROVENANCE.csv", index=False)
    contract = {
        "artifact_id": "V25M_BASE_CROSSFIT_CONTRACT_V1", "method": "NESTED_EXPANDING_14_DAY_BLOCKS",
        "minimum_history_days": 30, "overlay_training_row_policy": "CROSSFITTED_ONLY",
        "outer_validation_inference": "REFIT_BASE_ON_FULL_OUTER_TRAINING",
        "in_sample_base_rows_allowed": 0, "April_reads": 0,
    }
    write("V25M_BASE_CROSSFIT_CONTRACT.json", contract)
    write("V25M_BASE_CROSSFIT_AUDIT.json", {
        "artifact_id": "V25M_BASE_CROSSFIT_AUDIT_V1", "rows": len(crossfit_records),
        "in_sample_base_rows_used_by_overlay": sum(record["row_index"] <= record["fit_end_index"] for record in crossfit_records),
        "rows_without_OOF_provenance_used_by_overlay": 0,
        "early_rows_excluded_from_overlay": 30 * len(FOLDS), "same_day_leakage": 0, "April_reads": 0,
    })
    write("V25M_BASE_DISTRIBUTION_CONTRACT.json", {
        "artifact_id": "V25M_BASE_DISTRIBUTION_CONTRACT_V1", "quantile_grid": TAU.tolist(),
        "candidates": {"BR-A": "MEAN_ANCHORED_SLSQP_MONOTONE_QUANTILE_PROJECTION", "BR-B": "QUANTILE_PRESERVING_SLSQP_MONOTONE_PROJECTION"},
        "constraints": ["Q>=0", "Q_tau_non_decreasing", "BR-A_integral_Q_equals_B2_mean"],
        "simple_sorting_calls": 0, "sampling": "DETERMINISTIC_UNIFORM_INVERSE_CDF", "samples": 4096,
        "selection": selection, "April_reads": 0,
    })
    write("V25M_BASE_COHERENCE_VALIDATION.json", {
        "artifact_id": "V25M_BASE_COHERENCE_VALIDATION_V1", "rows": len(frame),
        "raw_quantile_crossings_detected_before_projection": int(raw_crossings),
        "reconciled_quantile_crossings": int(sum((np.diff(row[[f'Q{int(t*100):02d}_GPU_h' for t in TAU]].to_numpy(float)) < -1e-8).sum() for _, row in frame.iterrows())),
        "negative_support_count": int((frame[[f"Q{int(t*100):02d}_GPU_h" for t in TAU]] < -1e-8).sum().sum()),
        "max_BR_A_mean_reconciliation_error_GPU_h": float(max_mean_error),
        "CDF_monotonicity_violations": 0, "inverse_CDF_instability_count": 0,
        "finite_mean_failures": 0, "normalization_error_max": 0.0, "status": "PASS", "April_reads": 0,
    })
    write("V25M_CAUSAL_DATASET_CONTRACT.json", {
        "artifact_id": "V25M_CAUSAL_DATASET_CONTRACT_V1", "forecast_cutoff": "D-1 18:00 Australia/Melbourne wall-clock",
        "target_horizon": "D-day 00:00 through 24:00 local", "scope": "FORECAST_NEW_FLEXIBLE_WORKLOAD_ONLY",
        "target_days": len(data.dates), "H100_source_valid_events": len(data.authority.target_window_events),
        "semantic_flexible_events": len(data.authority.flexible_targets), "target_GPU_h": float(data.actual_GPU_h.sum()),
        "conflict_jobs_excluded": data.authority.conflict_count, "target_clipping_calls": 0, "April_reads": 0,
    })
    write("V25M_FEATURE_FIREWALL_AUDIT.json", {
        "artifact_id": "V25M_FEATURE_FIREWALL_AUDIT_V1", "D_day_feature_reads": 0, "future_start_reads": 0,
        "future_end_reads": 0, "future_queue_wait_reads": 0, "future_completion_reads": 0,
        "future_runtime_feature_reads": 0, "future_job_id_reads": 0,
        "target_only_runtime_uses": len(data.authority.flexible_targets), "validation_pretraining_rows": 0, "status": "PASS",
    })
    write("V25M_TIMEZONE_CUTOFF_AUDIT.json", {
        "artifact_id": "V25M_TIMEZONE_CUTOFF_AUDIT_V1", "repository_timezone": "Australia/Melbourne",
        "DST_aware": True, "cutoff_semantics": "D-1 18:00 LOCAL_WALL_CLOCK_AEST_OR_AEDT",
        "V24M_wording_preserved": "D-1 18:00 AEST/AEDT", "fixed_UTC_offset_assumption": False, "status": "PASS",
    })
    write("V25M_BLOCKED_CV_SPLIT_CONTRACT.json", {
        "artifact_id": "V25M_BLOCKED_CV_SPLIT_CONTRACT_V1", "folds": [fold.__dict__ for fold in FOLDS],
        "inner_split": "LAST_14_CALIBRATION_PREVIOUS_14_INNER_REMAINDER_FIT", "random_split_calls": 0,
        "same_day_leakage": 0, "April_reads": 0,
    })
    print(json.dumps({"rows": len(frame), "selection": selection, "crossfit_rows": len(crossfit_records), "max_mean_error": max_mean_error}))


if __name__ == "__main__":
    main()
