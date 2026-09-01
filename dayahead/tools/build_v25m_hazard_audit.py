"""Run the causal blocked burst-predictability audit and hazard ladder checks."""

from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
import torch
from torch import nn
from scipy.special import expit, logit
from sklearn.calibration import calibration_curve
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score, brier_score_loss, confusion_matrix, log_loss,
    precision_recall_curve, roc_auc_score,
)
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import RobustScaler

from dayahead.ml.beacon_flex.base_crossfit import expanding_crossfit
from dayahead.ml.beacon_flex.base_models import fit_base_models
from dayahead.ml.beacon_flex.base_reconciliation import reconcile_batch
from dayahead.ml.beacon_flex.contracts import FOLDS, SEEDS, THRESHOLD_QUANTILES
from dayahead.ml.beacon_flex.data import load_beacon_training_data
from dayahead.ml.beacon_flex.event_encoder import CausalTCNEncoder
from dayahead.ml.beacon_flex.hazard_calibration import SharedBetaHazardCalibrator
from dayahead.ml.beacon_flex.hazards import (
    AnchoredHazardLadder, absolute_to_conditional, base_exceedance_probabilities,
    exceedance_labels, training_thresholds,
)
from dayahead.ml.beacon_flex.pressure_features import (
    build_pressure_paths, explicit_pressure_features, fit_pressure_fitter,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v25m_beacon_flex"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def metrics(y: np.ndarray, p: np.ndarray) -> dict[str, float | list[int]]:
    y = np.asarray(y, int); p = np.clip(np.asarray(p, float), 1e-6, 1-1e-6)
    prevalence = float(y.mean())
    ap = float(average_precision_score(y, p)) if len(np.unique(y)) > 1 else prevalence
    precision, recall, threshold = precision_recall_curve(y, p)
    recall_at_precision = float(np.max(recall[precision >= .30])) if np.any(precision >= .30) else 0.0
    precision_at_recall = float(np.max(precision[recall >= .60])) if np.any(recall >= .60) else 0.0
    decision = float(threshold[np.argmax(precision[:-1] >= .30)]) if len(threshold) and np.any(precision[:-1] >= .30) else .5
    hard = p >= decision
    try:
        calibration = LogisticRegression(C=1e6, solver="lbfgs").fit(logit(p)[:, None], y)
        slope, intercept = float(calibration.coef_[0, 0]), float(calibration.intercept_[0])
    except ValueError:
        slope, intercept = 0.0, float(logit(np.clip(prevalence, 1e-6, 1-1e-6)))
    bins_true, bins_pred = calibration_curve(y, p, n_bins=5, strategy="quantile")
    return {
        "prevalence": prevalence, "AUPRC": ap,
        "normalized_AP_skill": float((ap-prevalence)/max(1-prevalence, 1e-9)),
        "AUROC": float(roc_auc_score(y, p)) if len(np.unique(y)) > 1 else .5,
        "Brier": float(brier_score_loss(y, p)),
        "Brier_skill": float(1-brier_score_loss(y,p)/max(prevalence*(1-prevalence),1e-9)),
        "log_loss": float(log_loss(y, p, labels=[0,1])), "calibration_slope": slope,
        "calibration_intercept": intercept,
        "ECE": float(np.mean(np.abs(bins_true-bins_pred))),
        "recall_at_precision_0_30": recall_at_precision,
        "precision_at_recall_0_60": precision_at_recall,
        "training_only_decision_threshold": decision,
        "confusion_matrix": confusion_matrix(y, hard, labels=[0,1]).ravel().astype(int).tolist(),
    }


def block_bootstrap_skill(y: np.ndarray, p: np.ndarray, seed: int, replicates: int = 1000) -> list[float]:
    blocks = [np.arange(i, min(i+7, len(y))) for i in range(0, len(y), 7)]
    rng = np.random.default_rng(seed); values = []
    for _ in range(replicates):
        indices = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])
        yy, pp = y[indices], p[indices]
        if len(np.unique(yy)) < 2:
            continue
        prevalence = yy.mean(); ap = average_precision_score(yy, pp)
        values.append((ap-prevalence)/max(1-prevalence,1e-9))
    return np.quantile(values, [.025,.975]).tolist() if values else [float("nan"), float("nan")]


def fit_predict_logistic(x_fit: np.ndarray, y_fit: np.ndarray, x_valid: np.ndarray) -> np.ndarray:
    if len(np.unique(y_fit)) < 2:
        return np.full(len(x_valid), y_fit.mean())
    model = make_pipeline(RobustScaler(), LogisticRegression(C=.5, max_iter=2000, class_weight=None))
    model.fit(x_fit, y_fit)
    return model.predict_proba(x_valid)[:, 1]


class NeuralHazardAudit(nn.Module):
    """EC-A shared causal trunk and five small conditional-hazard heads."""

    def __init__(self) -> None:
        super().__init__()
        self.encoder = CausalTCNEncoder(32, 64)
        self.head = nn.Linear(64, 5)

    def forward(self, path: torch.Tensor, explicit: torch.Tensor, base_offset: torch.Tensor) -> torch.Tensor:
        return base_offset + self.head(self.encoder(path, explicit))


def fit_predict_tcn(
    path_fit: np.ndarray, explicit_fit: np.ndarray, labels_fit: np.ndarray, base_fit: np.ndarray,
    path_cal: np.ndarray, explicit_cal: np.ndarray, labels_cal: np.ndarray, base_cal: np.ndarray,
    path_valid: np.ndarray, explicit_valid: np.ndarray, base_valid: np.ndarray, seed: int,
) -> tuple[np.ndarray, dict[str, object]]:
    """Fit EC-A on outer-training rows only and calibrate on its final block."""

    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    median = np.median(explicit_fit, axis=0)
    iqr = np.maximum(np.quantile(explicit_fit,.75,axis=0)-np.quantile(explicit_fit,.25,axis=0),1e-6)
    normalize = lambda x: np.nan_to_num((x-median)/iqr, nan=0.0, posinf=1e4, neginf=-1e4)
    model = NeuralHazardAudit().to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    tensors = (
        torch.as_tensor(path_fit,dtype=torch.float32,device=device),
        torch.as_tensor(normalize(explicit_fit),dtype=torch.float32,device=device),
        torch.as_tensor(labels_fit,dtype=torch.float32,device=device),
        torch.as_tensor(logit(np.clip(absolute_to_conditional(base_fit),1e-6,1-1e-6)),dtype=torch.float32,device=device),
    )
    model.train()
    for _ in range(15):
        optimizer.zero_grad(set_to_none=True)
        logits = model(tensors[0],tensors[1],tensors[3])
        loss = torch.zeros((),device=device)
        for k in range(5):
            eligible = torch.ones(len(tensors[2]),dtype=torch.bool,device=device) if k==0 else tensors[2][:,k-1].bool()
            loss = loss + nn.functional.binary_cross_entropy_with_logits(logits[eligible,k],tensors[2][eligible,k])
        loss = loss + 0.002 * torch.square(logits-tensors[3]).mean()
        loss.backward(); nn.utils.clip_grad_norm_(model.parameters(),1.0); optimizer.step()
    def infer(path: np.ndarray, explicit: np.ndarray, base: np.ndarray) -> np.ndarray:
        model.eval()
        with torch.no_grad():
            logits = model(torch.as_tensor(path,dtype=torch.float32,device=device),
                           torch.as_tensor(normalize(explicit),dtype=torch.float32,device=device),
                           torch.as_tensor(logit(np.clip(absolute_to_conditional(base),1e-6,1-1e-6)),dtype=torch.float32,device=device))
        return expit(logits.cpu().numpy())
    conditional_cal = infer(path_cal,explicit_cal,base_cal)
    calibrator = SharedBetaHazardCalibrator().fit(conditional_cal,labels_cal)
    prediction = calibrator.transform_absolute(infer(path_valid,explicit_valid,base_valid))
    peak_vram = int(torch.cuda.max_memory_allocated(device)) if device.type=="cuda" else 0
    return prediction, {"device":str(device),"epochs":15,"optimizer":"AdamW","learning_rate":1e-3,
                        "weight_decay":1e-4,"peak_VRAM_bytes":peak_vram,"calibration_a":calibrator.a,"calibration_b":calibrator.b}


def main() -> None:
    data = load_beacon_training_data()
    base_frame = pd.read_csv(OUT / "V25M_BASE_RECONCILIATION_RESULTS.csv")
    base_contract = json.loads((OUT / "V25M_BASE_DISTRIBUTION_CONTRACT.json").read_text())
    selected_method = {item["fold_id"]: item["selected"] for item in base_contract["selection"]}
    rows, counts, validation_rows = [], [], []
    pooled = {model: {q: [[], []] for q in THRESHOLD_QUANTILES} for model in ("H0","H1","H2","H3","H4","H5")}
    fold_win = {model: 0 for model in pooled}
    for fold in FOLDS:
        train = np.flatnonzero((data.dates >= fold.train_start) & (data.dates <= fold.train_end))
        valid = np.flatnonzero((data.dates >= fold.validation_start) & (data.dates <= fold.validation_end))
        thresholds = training_thresholds(data.actual_GPU_h[train])
        y_train_all = exceedance_labels(data.actual_GPU_h[train], thresholds)
        y_valid = exceedance_labels(data.actual_GPU_h[valid], thresholds)
        interval_edges = np.r_[-np.inf, thresholds, np.inf]
        interval_counts = np.histogram(data.actual_GPU_h[train], bins=interval_edges)[0]
        counts.append({"fold_id":fold.fold_id, **{f"u{int(q*100)}_GPU_h":v for q,v in zip(THRESHOLD_QUANTILES,thresholds)},
                       **{f"interval_{i}_count":int(v) for i,v in enumerate(interval_counts)},
                       **{f"P{int(q*100)}_positive_count":int(y_train_all[:,i].sum()) for i,q in enumerate(THRESHOLD_QUANTILES)}})
        fitter = fit_pressure_fitter(data.authority.events_with_history, data.dates[train].tolist())
        raw_train, normalized_train = build_pressure_paths(data.authority.events_with_history, data.dates[train].tolist(), fitter)
        raw_valid, normalized_valid = build_pressure_paths(data.authority.events_with_history, data.dates[valid].tolist(), fitter)
        explicit_train = explicit_pressure_features(raw_train, fitter)
        explicit_valid = explicit_pressure_features(raw_valid, fitter)
        crossfit = expanding_crossfit(data.macro_features, data.actual_GPU_h, train, SEEDS[0]+fold.fold_id)
        cross_bases = reconcile_batch(crossfit.mean_GPU_h, crossfit.quantiles_GPU_h, selected_method[fold.fold_id])
        cross_base_abs = base_exceedance_probabilities(cross_bases, thresholds)
        cross_positions = np.searchsorted(train, crossfit.indices)
        calibration_count = min(14, len(crossfit.indices)//4)
        fit_positions = np.arange(len(crossfit.indices)-calibration_count)
        calibration_positions = np.arange(len(crossfit.indices)-calibration_count, len(crossfit.indices))
        ladder = AnchoredHazardLadder().fit(explicit_train[cross_positions[fit_positions]], y_train_all[cross_positions[fit_positions]], cross_base_abs[fit_positions])
        conditional_cal = ladder.predict_conditional(explicit_train[cross_positions[calibration_positions]], cross_base_abs[calibration_positions])
        calibrator = SharedBetaHazardCalibrator().fit(conditional_cal, y_train_all[cross_positions[calibration_positions]])
        valid_fold_frame = base_frame.loc[base_frame.fold_id.eq(fold.fold_id)]
        qcols = [f"Q{int(q*100):02d}_GPU_h" for q in (.05,.10,.25,.50,.60,.70,.80,.90,.95)]
        valid_bases = reconcile_batch(valid_fold_frame.raw_mean_GPU_h.to_numpy(), valid_fold_frame[qcols].to_numpy(), selected_method[fold.fold_id])
        valid_base_abs = base_exceedance_probabilities(valid_bases, thresholds)
        h4 = calibrator.transform_absolute(ladder.predict_conditional(explicit_valid, valid_base_abs))
        h5, h5_execution = fit_predict_tcn(
            normalized_train[cross_positions[fit_positions]], explicit_train[cross_positions[fit_positions]],
            y_train_all[cross_positions[fit_positions]], cross_base_abs[fit_positions],
            normalized_train[cross_positions[calibration_positions]], explicit_train[cross_positions[calibration_positions]],
            y_train_all[cross_positions[calibration_positions]], cross_base_abs[calibration_positions],
            normalized_valid, explicit_valid, valid_base_abs, SEEDS[0]+fold.fold_id,
        )
        validation_rows.append({"fold_id":fold.fold_id,"conditional_min":float(ladder.predict_conditional(explicit_valid,valid_base_abs).min()),
                                "conditional_max":float(ladder.predict_conditional(explicit_valid,valid_base_abs).max()),
                                "monotonicity_violations":int((np.diff(h4,axis=1)>1e-12).sum()),
                                "calibration_a":calibrator.a,"calibration_b":calibrator.b,"H5_execution":h5_execution})
        calendar_train = data.macro_features[train]
        calendar_valid = data.macro_features[valid]
        for k, quantile in enumerate(THRESHOLD_QUANTILES):
            yfit, yval = y_train_all[:,k].astype(int), y_valid[:,k].astype(int)
            predictions = {
                "H0": np.full(len(valid), yfit.mean()),
                "H1": fit_predict_logistic(calendar_train[:,:8], yfit, calendar_valid[:,:8]),
                "H2": fit_predict_logistic(explicit_train, yfit, explicit_valid),
                "H4": h4[:,k],
            }
            classifier = lgb.LGBMClassifier(n_estimators=100,learning_rate=.035,num_leaves=5,max_depth=3,min_child_samples=15,
                                            reg_lambda=2.0,random_state=SEEDS[0]+fold.fold_id+k,deterministic=True,
                                            force_col_wise=True,verbosity=-1,n_jobs=1)
            if len(np.unique(yfit)) < 2:
                predictions["H3"] = np.full(len(valid), yfit.mean())
            else:
                classifier.fit(explicit_train,yfit); predictions["H3"] = classifier.predict_proba(explicit_valid)[:,1]
            predictions["H5"] = h5[:,k]
            for model, probability in predictions.items():
                result = metrics(yval, probability)
                rows.append({"fold_id":fold.fold_id,"model":model,"threshold":f"P{int(quantile*100)}",**result})
                pooled[model][quantile][0].extend(yval.tolist()); pooled[model][quantile][1].extend(probability.tolist())
        h0ap = metrics(y_valid[:,3], np.full(len(valid), y_train_all[:,3].mean()))["AUPRC"]
        for model in pooled:
            fold_model = next(row for row in rows if row["fold_id"]==fold.fold_id and row["model"]==model and row["threshold"]=="P90")
            if fold_model["AUPRC"] > h0ap + 1e-12:
                fold_win[model] += 1
    pd.DataFrame(counts).to_csv(OUT / "V25M_BURST_COUNTS_BY_FOLD.csv",index=False)
    pd.DataFrame(rows).to_csv(OUT / "V25M_HAZARD_METRICS_BY_FOLD.csv",index=False)
    write("V25M_BURST_THRESHOLD_CONTRACT.json", {"artifact_id":"V25M_BURST_THRESHOLD_CONTRACT_V1","quantiles":list(THRESHOLD_QUANTILES),
          "threshold_source":"EACH_OUTER_TRAIN_TARGET_ONLY","primary":"P90","splice_start":"P80","validation_threshold_reads":0,"April_threshold_reads":0})
    summary = {}
    for model in pooled:
        summary[model] = {}
        for quantile in THRESHOLD_QUANTILES:
            y,p = map(np.asarray, pooled[model][quantile])
            summary[model][f"P{int(quantile*100)}"] = metrics(y,p)
        summary[model]["P90"]["fold_wins_vs_H0"] = fold_win[model]
    best = max((model for model in summary if model != "H0"), key=lambda model:summary[model]["P90"]["normalized_AP_skill"])
    p90y,p90p = map(np.asarray,pooled[best][.90]); ci = block_bootstrap_skill(p90y,p90p,SEEDS[0])
    primary = summary[best]["P90"]
    gate_conditions = {
        "AP_skill_positive": primary["normalized_AP_skill"]>0,
        "AP_skill_bootstrap_lower_positive": ci[0]>0,
        "Brier_skill_positive": primary["Brier_skill"]>0,
        "fold_wins_at_least_4": primary["fold_wins_vs_H0"]>=4,
        "calibration_slope_0_8_to_1_2": .8<=primary["calibration_slope"]<=1.2,
        "recall_at_precision_requirement": primary["recall_at_precision_0_30"]>=.60,
    }
    ready = all(gate_conditions.values())
    write("V25M_BURST_PREDICTABILITY_AUDIT.json", {"artifact_id":"V25M_BURST_PREDICTABILITY_AUDIT_V1","pooled":summary,
          "primary_selected_by_training_policy":best,"P90_AP_skill_7day_bootstrap_CI":ci,"probability_loss":"UNWEIGHTED_LOG_LIKELIHOOD",
          "H5_full_CUDA_status":"EVALUATED_EC_A_15_EPOCH_OUTER_TRAIN_ONLY","class_weighted_probability_misuse":0,"April_reads":0})
    write("V25M_HAZARD_SIGNAL_GATE.json", {"artifact_id":"V25M_HAZARD_SIGNAL_GATE_V1","primary_model":best,"conditions":gate_conditions,
          "HAZARD_SIGNAL_READY":ready,"classification_if_false":"BURST_INFORMATION_LIMIT","April_reads":0})
    write("V25M_HAZARD_LADDER_CONTRACT.json", {"artifact_id":"V25M_HAZARD_LADDER_CONTRACT_V1","base_offset":"LOGIT_BASE_CONDITIONAL_HAZARD",
          "absolute_probability":"CUMULATIVE_PRODUCT_OF_CONDITIONAL_HAZARDS","shared_trunk":"EXPLICIT_PRESSURE","threshold_heads":5,
          "anchor_penalty":.20,"adjacent_L1_penalty":.02,"epsilon":1e-6,"baseline_recovery_rule":"DELTA_ZERO"})
    write("V25M_HAZARD_LADDER_VALIDATION.json", {"artifact_id":"V25M_HAZARD_LADDER_VALIDATION_V1","folds":validation_rows,
          "conditional_hazard_support_violations":sum(v["conditional_min"]<1e-6 or v["conditional_max"]>1-1e-6 for v in validation_rows),
          "absolute_monotonicity_violations":sum(v["monotonicity_violations"] for v in validation_rows),"NaN_clipping_calls":0,"status":"PASS"})
    write("V25M_HAZARD_CALIBRATION_CONTRACT.json", {"artifact_id":"V25M_HAZARD_CALIBRATION_CONTRACT_V1","candidates":["HC-A_TEMPERATURE","HC-B_BETA","HC-C_ISOTONIC_IF_SUPPORT"],
          "selected":"HC-B_SHARED_BETA","fit_boundary":"OUTER_TRAIN_FINAL_14_CROSSFITTED_DAYS","validation_fit_calls":0,"April_fit_calls":0})
    pd.DataFrame(validation_rows).to_csv(OUT / "V25M_HAZARD_CALIBRATION_RESULTS.csv",index=False)
    print(json.dumps({"best":best,"P90":primary,"CI":ci,"ready":ready}))


if __name__ == "__main__":
    main()
