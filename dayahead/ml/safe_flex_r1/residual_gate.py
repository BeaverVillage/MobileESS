"""Blocked OOF residual predictability audit and mandatory stop gate."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import r2_score

from .bootstrap import paired_block_bootstrap
from .metrics import aggregate_day_metrics
from .residual_dataset import build_residual_dataset
from .residual_models import audit_specs, fit_predict


def evaluate_residual_signal(repo: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    out = repo / "dayahead/artifacts/v27m_safe_flex_r1"
    dataset, contract = build_residual_dataset(repo)
    mapping = json.loads((out / "V27M_BASELINE_REPRODUCTION.json").read_text(encoding="utf-8"))["aggregate_to_V26_score_mapping_factor"]
    daily_rows: list[dict[str, object]] = []
    residual_rows: list[dict[str, object]] = []
    for fold_id in range(1, 6):
        train = dataset.loc[(dataset.outer_fold == fold_id) & dataset.phase.eq("TRAIN")].copy()
        valid = dataset.loc[(dataset.outer_fold == fold_id) & dataset.phase.eq("VALID")].copy()
        for spec in audit_specs():
            delta_l = fit_predict(train, valid, spec, "eL", 20260901 + 10 * fold_id)
            delta_u = fit_predict(train, valid, spec, "eU", 20261901 + 10 * fold_id)
            residual_rows.append(
                {
                    "fold_id": fold_id, "model": spec.name,
                    "residual_MAE": float(np.mean(np.abs(np.r_[valid.eL.to_numpy() - delta_l, valid.eU.to_numpy() - delta_u]))),
                    "residual_R2": float(np.mean([r2_score(valid.eL, delta_l), r2_score(valid.eU, delta_u)])),
                    "sign_accuracy": float(np.mean(np.r_[np.sign(delta_l) == np.sign(valid.eL), np.sign(delta_u) == np.sign(valid.eU)])),
                    "lower_correction_MAE": float(np.mean(np.abs(valid.eL - delta_l))),
                    "upper_correction_MAE": float(np.mean(np.abs(valid.eU - delta_u))),
                }
            )
            work = valid[["date", "slot", "L0", "U0", "L_ref", "U_ref"]].copy()
            work["lower"] = work.L0.to_numpy() + delta_l
            work["upper"] = work.U0.to_numpy() + delta_u
            for date, day in work.groupby("date", sort=True):
                day = day.sort_values("slot")
                metric = aggregate_day_metrics(day.lower, day.upper, day.L_ref, day.U_ref)
                daily_rows.append(
                    {"fold_id": fold_id, "date": date, "model": spec.name,
                     "normalized_boundary_score": float(metric["aggregate_unmapped_boundary_score"] * mapping),
                     "lower_boundary_MAE_GPU_h": metric["lower_boundary_MAE_GPU_h"],
                     "upper_boundary_MAE_GPU_h": metric["upper_boundary_MAE_GPU_h"],
                     "nonempty_set": metric["nonempty_set"],
                     "lower_monotonicity_violations": int(np.sum(np.diff(day.lower) < -1e-9)),
                     "upper_monotonicity_violations": int(np.sum(np.diff(day.upper) < -1e-9)),
                     "lower_above_upper_slots": int(np.sum(day.lower.to_numpy() > day.upper.to_numpy() + 1e-9))}
                )
    daily = pd.DataFrame(daily_rows)
    residual = pd.DataFrame(residual_rows)
    summaries = []
    base_daily = daily.loc[daily.model.eq("R0_ZERO_CORRECTION")].sort_values("date")
    base_score = float(base_daily.normalized_boundary_score.mean())
    for model, group in daily.groupby("model"):
        ordered = group.sort_values("date")
        merged = ordered[["date", "normalized_boundary_score"]].merge(
            base_daily[["date", "normalized_boundary_score"]], on="date", suffixes=("", "_base")
        )
        fold_scores = group.groupby("fold_id").normalized_boundary_score.mean()
        base_folds = base_daily.groupby("fold_id").normalized_boundary_score.mean()
        fold_wins = int(sum(fold_scores.loc[index] < base_folds.loc[index] for index in fold_scores.index))
        summaries.append(
            {
                "model": model,
                "residual_MAE": float(residual.loc[residual.model.eq(model), "residual_MAE"].mean()),
                "residual_R2": float(residual.loc[residual.model.eq(model), "residual_R2"].mean()),
                "sign_accuracy": float(residual.loc[residual.model.eq(model), "sign_accuracy"].mean()),
                "lower_correction_MAE": float(residual.loc[residual.model.eq(model), "lower_correction_MAE"].mean()),
                "upper_correction_MAE": float(residual.loc[residual.model.eq(model), "upper_correction_MAE"].mean()),
                "raw_boundary_score": float(group.normalized_boundary_score.mean()),
                "relative_improvement_vs_R0": float((base_score - group.normalized_boundary_score.mean()) / base_score),
                "fold_wins_vs_R0": fold_wins,
                "nonempty_rate_before_projection": float(group.nonempty_set.mean()),
                "monotonicity_violations": int(group.lower_monotonicity_violations.sum() + group.upper_monotonicity_violations.sum()),
                "L_above_U_slots": int(group.lower_above_upper_slots.sum()),
            }
        )
    summary = pd.DataFrame(summaries)
    r4 = daily.loc[daily.model.eq("R4_STATE_RUNNING_LGBM_RESIDUAL")].sort_values("date")
    r2 = daily.loc[daily.model.eq("R2_BASE_ONLY_LGBM_RESIDUAL")].sort_values("date")
    boot = paired_block_bootstrap(r4.normalized_boundary_score.to_numpy() - base_daily.normalized_boundary_score.to_numpy())
    r4_row = summary.loc[summary.model.eq("R4_STATE_RUNNING_LGBM_RESIDUAL")].iloc[0]
    r2_score_value = float(summary.loc[summary.model.eq("R2_BASE_ONLY_LGBM_RESIDUAL"), "raw_boundary_score"].iloc[0])
    gates = {
        "A_pooled_improvement_at_least_1pct": bool(r4_row.relative_improvement_vs_R0 >= 0.01),
        "B_at_least_4_of_5_outer_folds_improve": bool(r4_row.fold_wins_vs_R0 >= 4),
        "C_bootstrap_point_estimate_negative": bool(boot["observed_mean_difference"] < 0),
        "D_R4_beats_base_only_R2": bool(r4_row.raw_boundary_score < r2_score_value),
    }
    ready = all(gates.values())
    gate = {
        "artifact_id": "V27M_RESIDUAL_SIGNAL_GATE_V1",
        "dataset_contract_PASS": contract["PASS"],
        "primary_model": "R4_STATE_RUNNING_LGBM_RESIDUAL",
        "primary_comparator": "R0_ZERO_CORRECTION_DIRECT_LIGHTGBM",
        "R0_score": base_score,
        "R4_score": float(r4_row.raw_boundary_score),
        "R2_base_only_score": r2_score_value,
        "R4_relative_improvement": float(r4_row.relative_improvement_vs_R0),
        "R4_fold_wins": int(r4_row.fold_wins_vs_R0),
        "seven_day_block_bootstrap": boot,
        "gates": gates,
        "RESIDUAL_STATE_SIGNAL_READY": ready,
        "classification_if_stop": None if ready else "V27M_SAFE_R1_RESIDUAL_SIGNAL_FAIL",
        "architecture_escalation_if_fail": "FORBIDDEN",
        "April_reads": 0,
    }
    daily.to_csv(out / "V27M_RESIDUAL_PREDICTABILITY_DAILY.csv", index=False)
    summary.to_csv(out / "V27M_RESIDUAL_PREDICTABILITY_RESULTS.csv", index=False)
    (out / "V27M_RESIDUAL_SIGNAL_GATE.json").write_text(json.dumps(gate, indent=2) + "\n", encoding="utf-8")
    return summary, gate

