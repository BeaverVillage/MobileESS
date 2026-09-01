"""Build raw and trajectory-calibrated SAFE/direct envelope OOF results."""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import conflict_ids, expanding_blocked_folds, load_h100_source, semantic_flexible_targets, source_valid_input_events
from dayahead.ml.safe_flex.conformal_set import calibrate_inner_set, calibration_scale, finite_sample_quantile, violation_scores
from dayahead.ml.safe_flex.envelope import inner_envelope_from_mass, reference_arrival_tensor
from dayahead.ml.safe_flex.metrics import envelope_metrics
from dayahead.ml.safe_flex.scenario import empirical_shape
from dayahead.ml.safe_flex.service_set import cumulative_bounds
from dayahead.ml.safe_flex.survival.pending_realization import build_pending_examples


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"
V25 = REPO / "dayahead/artifacts/v25m_beacon_flex/V25M_CANONICAL_BASELINE_DAILY_OOF.csv"
FEATURES = ["pending_jobs", "pending_gpus", "pending_requested_GPU_h", "pending_mean_age_h", "dow_sin", "dow_cos", "lag1_K", "lag7_K", "lag28_K_mean", "lag1_total", "lag7_total_mean"]


def daily_state_table(pending: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    aggregate = pending.groupby("target_day").agg(pending_jobs=("job_id", "size"), pending_gpus=("gpus_requested", "sum"), pending_requested_GPU_h=("wallclock_req_h", lambda x: 0.0), pending_mean_age_h=("pending_age_h", "mean")).reset_index()
    requested = pending.assign(requested=lambda d: d.gpus_requested * d.wallclock_req_h).groupby("target_day").requested.sum()
    aggregate["pending_requested_GPU_h"] = aggregate.target_day.map(requested)
    frame = shares.merge(aggregate, on="target_day", how="left").fillna(0.0)
    date = pd.to_datetime(frame.target_day)
    frame["dow_sin"] = np.sin(2 * np.pi * date.dt.dayofweek / 7); frame["dow_cos"] = np.cos(2 * np.pi * date.dt.dayofweek / 7)
    frame["lag1_K"] = frame.H_K_pending_GPU_h.shift(1); frame["lag7_K"] = frame.H_K_pending_GPU_h.shift(7)
    frame["lag28_K_mean"] = frame.H_K_pending_GPU_h.shift(1).rolling(28, min_periods=1).mean()
    frame["lag1_total"] = frame.H_total_GPU_h.shift(1); frame["lag7_total_mean"] = frame.H_total_GPU_h.shift(1).rolling(7, min_periods=1).mean()
    return frame.fillna(0.0)


def fit_quantiles(train: pd.DataFrame, target: str, seed: int) -> dict[str, lgb.LGBMRegressor]:
    common = dict(n_estimators=120, learning_rate=0.035, num_leaves=16, min_child_samples=15, verbosity=-1, random_state=seed, n_jobs=-1)
    result = {}
    for name, alpha in (("Q10", .1), ("Q50", .5), ("Q90", .9)):
        result[name] = lgb.LGBMRegressor(objective="quantile", alpha=alpha, **common).fit(train[FEATURES], train[target])
    return result


def predict_quantiles(models: dict[str, lgb.LGBMRegressor], valid: pd.DataFrame) -> np.ndarray:
    raw = np.column_stack([np.maximum(models[name].predict(valid[FEATURES]), 0) for name in ("Q10", "Q50", "Q90")])
    return np.sort(raw, axis=1)


def main() -> None:
    raw, _ = load_h100_source(min_month=202407, max_month=202503)
    shares = pd.read_csv(OUT / "V26M_OBSERVABLE_STATE_SHARE_BY_DAY.csv")
    pending = build_pending_examples(source_valid_input_events(raw), "2024-08-19", "2025-03-31")
    state = daily_state_table(pending, shares)
    jobs = semantic_flexible_targets(raw, "2024-07-01", "2025-04-01", conflict_ids()).reset_index(drop=True)
    days = list(pd.date_range("2024-08-19", "2025-03-31", freq="D"))
    tensors = {day.strftime("%Y-%m-%d"): reference_arrival_tensor(jobs, day) for day in days}
    canonical = pd.read_csv(V25)
    b3 = canonical.loc[canonical.model.eq("C-B1_B3_LIGHTGBM_QUANTILE"), ["date", "Q50_GPU_h", "Q90_GPU_h"]]
    gap = pd.read_csv(OUT / "V26M_INNOVATION_OOF.csv")
    predictions = []
    shape_by_fold = {}
    for fold in expanding_blocked_folds():
        train = state.loc[state.target_day.between(fold.train_start, fold.train_end)]
        valid = state.loc[state.target_day.between(fold.validation_start, fold.validation_end)].copy()
        k_models = fit_quantiles(train, "H_K_pending_GPU_h", 20260901 + fold.fold_id)
        total_target = "H_total_GPU_h"
        direct_models = fit_quantiles(train.assign(**{total_target: train.H_K_pending_GPU_h + train.H_G_GPU_h + train.H_N_GPU_h}), total_target, 20261901 + fold.fold_id)
        kq = predict_quantiles(k_models, valid); dq = predict_quantiles(direct_models, valid)
        training_tensors = np.stack([tensors[date] for date in train.target_day])
        shape_by_fold[fold.fold_id] = empirical_shape(training_tensors)
        for i, row in valid.reset_index(drop=True).iterrows():
            predictions.append({"fold_id": fold.fold_id, "date": row.target_day, "K_Q10": kq[i,0], "K_Q50": kq[i,1], "K_Q90": kq[i,2], "DIRECT_Q10": dq[i,0], "DIRECT_Q50": dq[i,1], "DIRECT_Q90": dq[i,2]})
    pred = pd.DataFrame(predictions).merge(b3, on="date").merge(gap[["date","G_Q50_GPU_h","G_Q90_GPU_h"]], on="date")
    pred["N_Q10"] = np.maximum(0, 2 * pred.Q50_GPU_h - pred.Q90_GPU_h); pred["G_Q10"] = np.maximum(0, 2 * pred.G_Q50_GPU_h - pred.G_Q90_GPU_h)
    records = []
    arrays = {}
    for row in pred.itertuples(index=False):
        reference = tensors[row.date]; ref_l, ref_u = cumulative_bounds(reference); shape = shape_by_fold[row.fold_id]
        cases = {
            "BL1_LEGACY_B2_B3": (row.N_Q10, row.Q90_GPU_h),
            "BL3_DIRECT_QUANTILE_LIGHTGBM": (row.DIRECT_Q10, row.DIRECT_Q90),
            "FULL_SAFE_FLEX_RAW": (row.K_Q10 + row.G_Q10 + row.N_Q10, row.K_Q90 + row.G_Q90_GPU_h + row.Q90_GPU_h),
        }
        for model, (q10, q90) in cases.items():
            lower, upper = inner_envelope_from_mass(shape, q10, q90)
            arrays[(row.date, model)] = (lower, upper, ref_l, ref_u)
            metric = envelope_metrics(lower, upper, ref_l, ref_u)
            records.append({"fold_id": row.fold_id, "date": row.date, "model": model, "Q10_total_GPU_h": q10, "Q90_total_GPU_h": q90, "reference_schedulable_GPU_h": float(reference.sum()), "phase": "RAW", **metric})
    raw_results = pd.DataFrame(records)
    raw_results.to_csv(OUT / "V26M_RAW_ENVELOPE_RESULTS.csv", index=False)

    ordered_dates = sorted(pred.date.unique()); calibration_dates = set(ordered_dates[:30]); evaluation_dates = set(ordered_dates[30:])
    calibrated_records = []
    calibration_summary = {}
    for model in raw_results.model.unique():
        cal_keys = [(date, model) for date in ordered_dates[:30]]
        pl = np.stack([arrays[key][0] for key in cal_keys]); pu = np.stack([arrays[key][1] for key in cal_keys])
        rl = np.stack([arrays[key][2] for key in cal_keys]); ru = np.stack([arrays[key][3] for key in cal_keys])
        scale = calibration_scale(ru); scores = violation_scores(pl, pu, rl, ru, scale); q = finite_sample_quantile(scores, 0.10)
        calibration_summary[model] = {"calibration_days": 30, "trajectory_score_Q90": q, "score_mean": float(scores.mean())}
        for date in sorted(evaluation_dates):
            lower, upper, ref_l, ref_u = arrays[(date, model)]
            cal_l, cal_u = calibrate_inner_set(lower, upper, q, scale)
            metric = envelope_metrics(cal_l, cal_u, ref_l, ref_u)
            reference_mass = float(tensors[date].sum()); nomination = float(max(cal_u[-1].sum() - cal_l[-1].sum(), 0.0))
            calibrated_records.append({"date": date, "model": model, "phase": "CALIBRATED_EVALUATION", "reserve_nomination_GPU_h": nomination, "reserve_shortfall_GPU_h": max(nomination - reference_mass, 0.0), **metric})
    calibrated = pd.DataFrame(calibrated_records)
    calibrated.to_csv(OUT / "V26M_SAFE_SET_CALIBRATION_RESULTS.csv", index=False)
    contract = {
        "artifact_id": "V26M_SAFE_SET_CALIBRATION_CONTRACT_V1", "method": "BLOCKED_TRAJECTORY_LEVEL_CONFORMAL_CALIBRATION",
        "alpha": 0.10, "chronological_calibration_days": ordered_dates[:30], "evaluation_days": ordered_dates[30:],
        "score": "max over all 96x6x5 of positive normalized L_reference-L_pred and U_pred-U_reference",
        "directions": "L calibrated upward; U calibrated downward", "empty_set_repair": "FORBIDDEN",
        "normalization_scale": "maximum calibration-day terminal reference GPU-hour mass, broadcast over trajectory",
        "numerical_scale_correction": "ZERO_SUPPORT_DIMENSION_EPSILON_DIVISION_REMOVED",
        "RESULT_BASED_RETUNING": 0,
        "calibration_training_only": True, "April_reads": 0, "model_summaries": calibration_summary,
    }
    (OUT / "V26M_SAFE_SET_CALIBRATION_CONTRACT.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    print(calibrated.groupby("model").agg(coverage=("simultaneous_inner_coverage","mean"), nonempty=("nonempty_set","mean"), score=("normalized_boundary_score","mean")).to_json())


if __name__ == "__main__":
    main()
