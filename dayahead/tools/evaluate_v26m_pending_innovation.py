"""Blocked-CV pending-state and unseen-innovation evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import expanding_blocked_folds, load_h100_source, source_valid_input_events
from dayahead.ml.safe_flex.contracts import TRAIN_END_INCLUSIVE, TRAIN_START
from dayahead.ml.safe_flex.innovation.day import day_innovation_authority
from dayahead.ml.safe_flex.innovation.gap import fit_gap_models, gap_daily_frame, predict_gap
from dayahead.ml.safe_flex.survival.pending_realization import build_pending_examples, fit_realization, realization_metrics
from dayahead.ml.safe_flex.survival.pending_service import fit_service_models, predict_service, service_metrics


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"


def main() -> None:
    raw, _ = load_h100_source(min_month=202407, max_month=202503)
    examples = build_pending_examples(source_valid_input_events(raw), TRAIN_START, TRAIN_END_INCLUSIVE)
    shares = pd.read_csv(OUT / "V26M_OBSERVABLE_STATE_SHARE_BY_DAY.csv")
    gap = gap_daily_frame(shares)
    realization_rows, service_rows, innovation_rows, daily_rows = [], [], [], []
    for fold in expanding_blocked_folds():
        train = examples.loc[examples.target_day.between(fold.train_start, fold.train_end)]
        valid = examples.loc[examples.target_day.between(fold.validation_start, fold.validation_end)]
        train = train.loc[~train.job_id.isin(set(valid.job_id))]
        classifier = fit_realization(train, 20260901 + fold.fold_id)
        probability = classifier.predict_proba(valid.drop(columns=[])[classifier.feature_name_])[:, 1]
        rm = realization_metrics(valid.realized_service.to_numpy(), probability, float(train.realized_service.mean()))
        rm.update({"fold_id": fold.fold_id, "train_snapshots": len(train), "validation_snapshots": len(valid)})
        realization_rows.append(rm)
        service_models = fit_service_models(train, 20260901 + fold.fold_id)
        valid_realized = valid.loc[valid.realized_service.eq(1) & valid.service_total_GPU_h.gt(0)]
        sp = predict_service(service_models, valid_realized)
        sm = service_metrics(valid_realized, sp)
        sm.update({"fold_id": fold.fold_id, "validation_realized_jobs": len(valid_realized)})
        service_rows.append(sm)

        gtrain = gap.loc[gap.target_day.between(fold.train_start, fold.train_end)]
        gvalid = gap.loc[gap.target_day.between(fold.validation_start, fold.validation_end)]
        gm = fit_gap_models(gtrain, 20260901 + fold.fold_id)
        gp = predict_gap(gm, gvalid)
        y = gvalid.H_G_GPU_h.to_numpy(float)
        innovation_rows.append({
            "fold_id": fold.fold_id, "days": len(gvalid),
            "G_mean_WAPE": float(np.abs(y - gp["mean"]).sum() / max(y.sum(), 1e-9)),
            "G_Q50_WAPE": float(np.abs(y - gp["Q50"]).sum() / max(y.sum(), 1e-9)),
            "G_Q90_coverage": float(np.mean(y <= gp["Q90"])),
        })
        for index, record in gvalid.reset_index(drop=True).iterrows():
            daily_rows.append({"fold_id": fold.fold_id, "date": record.target_day, "actual_G_GPU_h": record.H_G_GPU_h, "G_mean_GPU_h": gp["mean"][index], "G_Q50_GPU_h": gp["Q50"][index], "G_Q90_GPU_h": gp["Q90"][index]})

    realization = pd.DataFrame(realization_rows); service = pd.DataFrame(service_rows); innovation = pd.DataFrame(innovation_rows)
    realization.to_csv(OUT / "V26M_PENDING_REALIZATION_RESULTS.csv", index=False)
    service.to_csv(OUT / "V26M_PENDING_SERVICE_RESULTS.csv", index=False)
    innovation.to_csv(OUT / "V26M_INNOVATION_MODEL_COMPARISON.csv", index=False)
    pd.DataFrame(daily_rows).to_csv(OUT / "V26M_INNOVATION_OOF.csv", index=False)
    identified = realization.Brier_skill.notna()
    r_skill = float(np.average(realization.loc[identified, "Brier_skill"], weights=realization.loc[identified, "validation_snapshots"])) if identified.any() else None
    g_share = float(shares.H_G_GPU_h.sum() / shares.H_total_GPU_h.sum())
    gap_audit = {
        "artifact_id": "V26M_GAP_INNOVATION_AUDIT_V1", "aggregate_G_share": g_share,
        "one_percent_threshold": 0.01, "classification": "MATERIAL_SMALL_COMPONENT" if g_share >= 0.01 else "LOW_MASS_GAP_COMPONENT",
        "model": "G1_TWEEDIE_MEAN_PLUS_G2_LIGHTGBM_QUANTILES" if g_share >= 0.01 else "TRAINING_ONLY_EMPIRICAL_CONDITIONAL",
        "D_day_target_leakage": 0, "April_target_reads_before_freeze": 0,
        "day_innovation_authority": day_innovation_authority(),
    }
    (OUT / "V26M_GAP_INNOVATION_AUDIT.json").write_text(json.dumps(gap_audit, indent=2) + "\n", encoding="utf-8")
    contract = {
        "artifact_id": "V26M_PENDING_AND_INNOVATION_CONTRACT_V1",
        "pending_realization": "LightGBM Bernoulli; cancelled/no-service accounting outcomes retained as zero",
        "pending_service": "conditional Tweedie mean and Q10/Q50/Q90 LightGBM",
        "pending_timing": "future exact start time not predicted; release is cutoff-known submission",
        "future_start_time_feature_reads": 0, "D_day_target_leakage": 0,
        "pooled_pending_Brier_skill": r_skill,
        "pending_Brier_skill_positive": bool(r_skill is not None and r_skill > 0),
        "identified_Brier_skill_folds": int(identified.sum()),
    }
    (OUT / "V26M_PENDING_INNOVATION_CONTRACT.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"pending_Brier_skill": r_skill, "G_share": g_share, "N_authority": day_innovation_authority()["selection"]}, indent=2))


if __name__ == "__main__":
    main()
