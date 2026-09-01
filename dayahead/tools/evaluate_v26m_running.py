"""Blocked-CV evaluation of V26M running residual-service survival."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from dayahead.ml.c_mass_tpp.data import expanding_blocked_folds, load_h100_source, source_valid_input_events
from dayahead.ml.safe_flex.contracts import TRAIN_END_INCLUSIVE, TRAIN_START
from dayahead.ml.safe_flex.survival.running_residual import build_running_examples, fit_running_models, predict_running, survival_metrics


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"


def main() -> None:
    raw, _ = load_h100_source(min_month=202407, max_month=202503)
    events = source_valid_input_events(raw)
    examples = build_running_examples(events, TRAIN_START, TRAIN_END_INCLUSIVE)
    rows = []
    calibration = []
    for fold in expanding_blocked_folds():
        train = examples.loc[examples.target_day.between(fold.train_start, fold.train_end)]
        valid = examples.loc[examples.target_day.between(fold.validation_start, fold.validation_end)]
        valid_ids = set(valid.job_id)
        train = train.loc[~train.job_id.isin(valid_ids)]
        model = fit_running_models(train, seed=20260901 + fold.fold_id)
        pred = predict_running(model, valid)
        metric = survival_metrics(valid, pred)
        metric.update({"fold_id": fold.fold_id, "train_snapshots": len(train), "validation_snapshots": len(valid), "validation_unique_jobs": valid.job_id.nunique()})
        rows.append(metric)
        for slot_h in (1, 2, 4, 8, 12, 24):
            idx = int(slot_h / 0.25) - 1
            actual = valid.remaining_h.to_numpy(float) > slot_h
            calibration.append({
                "fold_id": fold.fold_id, "horizon_h": slot_h,
                "actual_survival_rate": float(actual.mean()),
                "SR1_predicted_survival": float(pred["SR1_survival"][:, idx].mean()),
                "SAFE_predicted_survival": float(pred["SAFE_survival"][:, idx].mean()),
            })
    result = pd.DataFrame(rows)
    result.to_csv(OUT / "V26M_RUNNING_SURVIVAL_RESULTS.csv", index=False)
    pd.DataFrame(calibration).to_json(OUT / "V26M_RUNNING_SURVIVAL_CALIBRATION.json", orient="records", indent=2)
    pooled = {
        key: float((result[key] * result.validation_snapshots).sum() / result.validation_snapshots.sum())
        for key in ["SR1_integrated_Brier", "SAFE_integrated_Brier", "SR1_NLL", "SAFE_NLL", "SR0_MAE_h", "SR1_Q50_MAE_h", "SAFE_Q50_MAE_h", "SR1_Q90_coverage", "SAFE_Q90_coverage"]
    }
    pooled["SAFE_IBS_relative_improvement_vs_SR1"] = (pooled["SR1_integrated_Brier"] - pooled["SAFE_integrated_Brier"]) / pooled["SR1_integrated_Brier"]
    contract = {
        "artifact_id": "V26M_RUNNING_SURVIVAL_CONTRACT_V1",
        "state": "RUNNING at D-1 18:00 EVENT_CENSORED_RECONSTRUCTED_STATE",
        "policy": "LOCKED_RESIDUAL",
        "target": "remaining runtime censored at 24 h",
        "slot_h": 0.25,
        "SR0": "requested-walltime residual heuristic",
        "SR1": "LightGBM log-duration Q50/Q90 with empirical lognormal survival",
        "SAFE_candidate": "LightGBM discrete hazard fitted by proper person-period Bernoulli likelihood",
        "features": "request, observed age, category codes, calendar only",
        "raw_account_identity_used": False,
        "future_runtime_feature_reads": 0,
        "right_censoring": "explicit 24-hour horizon",
        "validation": "five expanding blocked folds; any validation job ID removed from fold training",
        "pooled_metrics": pooled,
        "state_quality_gate_5pct_IBS": pooled["SAFE_IBS_relative_improvement_vs_SR1"] >= 0.05,
    }
    (OUT / "V26M_RUNNING_SURVIVAL_CONTRACT.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(pooled, indent=2))


if __name__ == "__main__":
    main()
