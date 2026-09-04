"""Definitive nested blocked evaluation of preregistered BEC-A after a false hazard gate."""

from __future__ import annotations

import json
import time
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score,brier_score_loss

from dayahead.ml.beacon_flex.base_crossfit import expanding_crossfit
from dayahead.ml.beacon_flex.base_models import fit_base_models
from dayahead.ml.beacon_flex.base_reconciliation import reconcile_batch
from dayahead.ml.beacon_flex.bootstrap import paired_block_CI
from dayahead.ml.beacon_flex.contracts import FOLDS,SEEDS
from dayahead.ml.beacon_flex.data import load_beacon_training_data
from dayahead.ml.beacon_flex.distribution import ensemble_crps,risk_summary,sample_splice,sobol_uniforms
from dayahead.ml.beacon_flex.evaluate import point_metrics
from dayahead.ml.beacon_flex.hazard_calibration import SharedBetaHazardCalibrator
from dayahead.ml.beacon_flex.hazards import AnchoredHazardLadder,base_exceedance_probabilities,exceedance_labels,training_thresholds
from dayahead.ml.beacon_flex.pressure_features import build_pressure_paths,explicit_pressure_features,fit_pressure_fitter
from dayahead.ml.beacon_flex.severity import SeverityModel
from dayahead.ml.beacon_flex.shape import coherent_tensor,normalize_shapes
from dayahead.ml.beacon_flex.splice import spliced_from_severity
from dayahead.ml.faser_flex.power_adapter import flexible_it_power_kW
from dayahead.ml.faser_flex.queue_adapter import schedule_gpu_h
from dayahead.ml.faser_flex.shape import target_shapes


ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"dayahead"/"artifacts"/"v25m_beacon_flex"


def write(name:str,payload:object)->None:
    (OUT/name).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def baseline_row(model:str,status:str,metrics:dict|None=None,reason:str|None=None)->dict:
    return {"model":model,"status":status,"reason":reason,**({} if metrics is None else metrics)}


def main()->None:
    if json.loads((OUT/"V25M_HAZARD_SIGNAL_GATE.json").read_text())["HAZARD_SIGNAL_READY"]:
        raise RuntimeError("V25M_THIS_EVALUATOR_IS_FALSE_GATE_BEC_A_ONLY")
    started=time.perf_counter(); data=load_beacon_training_data(); tensors=target_shapes(data.authority.flexible_targets,data.dates.tolist())
    normalized_shapes,positive=normalize_shapes(tensors); daily=[]; base_daily=[]; b4_daily=[]; b5_daily=[]; b6_daily=[]
    predicted_tensors=[]; actual_tensors=[]; queue_records=[]; power_pred=[]; power_actual=[]
    for fold in FOLDS:
        train=np.flatnonzero((data.dates>=fold.train_start)&(data.dates<=fold.train_end)); valid=np.flatnonzero((data.dates>=fold.validation_start)&(data.dates<=fold.validation_end))
        thresholds=training_thresholds(data.actual_GPU_h[train]); labels_train=exceedance_labels(data.actual_GPU_h[train],thresholds)
        fitter=fit_pressure_fitter(data.authority.events_with_history,data.dates[train].tolist())
        raw_train,_=build_pressure_paths(data.authority.events_with_history,data.dates[train].tolist(),fitter)
        raw_valid,_=build_pressure_paths(data.authority.events_with_history,data.dates[valid].tolist(),fitter)
        explicit_train=explicit_pressure_features(raw_train,fitter); explicit_valid=explicit_pressure_features(raw_valid,fitter)
        crossfit=expanding_crossfit(data.macro_features,data.actual_GPU_h,train,SEEDS[0]+fold.fold_id)
        cross_bases=reconcile_batch(crossfit.mean_GPU_h,crossfit.quantiles_GPU_h,"BR-A")
        cross_base_p=base_exceedance_probabilities(cross_bases,thresholds); positions=np.searchsorted(train,crossfit.indices)
        calibration_count=min(14,len(crossfit.indices)//4); fit=np.arange(len(crossfit.indices)-calibration_count); calibration=np.arange(len(crossfit.indices)-calibration_count,len(crossfit.indices))
        ladder=AnchoredHazardLadder().fit(explicit_train[positions[fit]],labels_train[positions[fit]],cross_base_p[fit])
        cal_conditional=ladder.predict_conditional(explicit_train[positions[calibration]],cross_base_p[calibration])
        calibrator=SharedBetaHazardCalibrator().fit(cal_conditional,labels_train[positions[calibration]])
        base_model=fit_base_models(data.macro_features[train],data.actual_GPU_h[train],SEEDS[0]+fold.fold_id)
        raw_mean,raw_grid=base_model.predict(data.macro_features[valid]); bases=reconcile_batch(raw_mean,raw_grid,"BR-A")
        base_p=base_exceedance_probabilities(bases,thresholds); probabilities=calibrator.transform_absolute(ladder.predict_conditional(explicit_valid,base_p))
        severity=SeverityModel.fit(data.actual_GPU_h[train],thresholds)
        shape=np.mean(normalized_shapes[train][positive[train]],axis=0); shape/=shape.sum()
        feature_all_train=np.column_stack((data.macro_features[train],explicit_train)); feature_valid=np.column_stack((data.macro_features[valid],explicit_valid))
        b4=lgb.LGBMRegressor(objective="tweedie",tweedie_variance_power=1.5,n_estimators=120,learning_rate=.035,num_leaves=7,max_depth=3,min_child_samples=12,reg_lambda=1.0,random_state=SEEDS[0]+fold.fold_id,deterministic=True,force_col_wise=True,verbosity=-1,n_jobs=1)
        b4.fit(feature_all_train,data.actual_GPU_h[train]); b4_prediction=np.maximum(b4.predict(feature_valid),0)
        classifier=lgb.LGBMClassifier(n_estimators=100,learning_rate=.035,num_leaves=5,max_depth=3,min_child_samples=15,reg_lambda=2.0,random_state=SEEDS[0]+fold.fold_id,deterministic=True,force_col_wise=True,verbosity=-1,n_jobs=1)
        classifier.fit(explicit_train,labels_train[:,3]); burst_probability=classifier.predict_proba(explicit_valid)[:,1]
        low_mean=float(data.actual_GPU_h[train][~labels_train[:,3]].mean()); high_mean=float(data.actual_GPU_h[train][labels_train[:,3]].mean())
        b5_prediction=(1-burst_probability)*low_mean+burst_probability*high_mean
        base_p90=base_p[:,3]; b6_prediction=np.maximum(0,raw_mean+(probabilities[:,3]-base_p90)*(high_mean-low_mean))
        for local,index in enumerate(valid):
            uniforms=sobol_uniforms(4096,SEEDS[0]+int(index)); distribution=spliced_from_severity(bases[local],thresholds,probabilities[local],severity)
            samples=sample_splice(distribution,severity,uniforms); summary=risk_summary(samples,thresholds[3]); crps=ensemble_crps(samples,data.actual_GPU_h[index])
            base_samples=bases[local].sample(uniforms); base_summary=risk_summary(base_samples,thresholds[3]); base_crps=ensemble_crps(base_samples,data.actual_GPU_h[index])
            row={"fold_id":fold.fold_id,"date":str(data.dates[index]),"actual_GPU_h":data.actual_GPU_h[index],**summary,"CRPS":crps,
                 "p60":probabilities[local,0],"p70":probabilities[local,1],"p80":probabilities[local,2],"p90":probabilities[local,3],"p95":probabilities[local,4],
                 "u80_GPU_h":thresholds[2],"u90_GPU_h":thresholds[3],"u95_GPU_h":thresholds[4],"burst":bool(data.actual_GPU_h[index]>thresholds[3]),"body":bool(data.actual_GPU_h[index]<=thresholds[2])}
            daily.append(row); base_daily.append({"fold_id":fold.fold_id,"date":str(data.dates[index]),"actual_GPU_h":data.actual_GPU_h[index],**base_summary,"CRPS":base_crps,"burst":row["burst"],"body":row["body"]})
            b4_daily.append(b4_prediction[local]); b5_daily.append(b5_prediction[local]); b6_daily.append(b6_prediction[local])
            pred_tensor=coherent_tensor(summary["mean_GPU_h"],shape); predicted_tensors.append(pred_tensor); actual_tensors.append(tensors[index])
            pred_queue=schedule_gpu_h(pred_tensor); actual_queue=schedule_gpu_h(tensors[index])
            queue_records.append({"date":str(data.dates[index]),"predicted":{k:v for k,v in pred_queue.items() if k not in ("service","rack_service")},"actual":{k:v for k,v in actual_queue.items() if k not in ("service","rack_service")}})
            power_pred.append(flexible_it_power_kW(pred_queue["service"])); power_actual.append(flexible_it_power_kW(actual_queue["service"]))
    frame=pd.DataFrame(daily); base_frame=pd.DataFrame(base_daily); frame.to_csv(OUT/"V25M_DAILY_OOF_RESULTS.csv",index=False)
    actual=frame.actual_GPU_h.to_numpy(); burst=frame.burst.to_numpy(bool); body=frame.body.to_numpy(bool)
    beacon_metrics=point_metrics(actual,frame.mean_GPU_h.to_numpy(),frame.Q50_GPU_h.to_numpy(),frame.Q90_GPU_h.to_numpy(),frame.Q95_GPU_h.to_numpy(),frame.CRPS.to_numpy(),burst,body)
    base_metrics=point_metrics(actual,base_frame.mean_GPU_h.to_numpy(),base_frame.Q50_GPU_h.to_numpy(),base_frame.Q90_GPU_h.to_numpy(),base_frame.Q95_GPU_h.to_numpy(),base_frame.CRPS.to_numpy(),burst,body)
    prevalence=burst.mean(); beacon_metrics["P90_AUPRC"]=float(average_precision_score(burst,frame.p90)); beacon_metrics["P90_Brier_skill"]=float(1-brier_score_loss(burst,frame.p90)/max(prevalence*(1-prevalence),1e-9))
    predicted_tensors=np.asarray(predicted_tensors); actual_tensors=np.asarray(actual_tensors)
    beacon_metrics["15min_GPU_h_WAPE"]=float(np.abs(predicted_tensors-actual_tensors).sum()/max(actual_tensors.sum(),1e-12))
    pp=np.asarray(power_pred); pa=np.asarray(power_actual); beacon_metrics["IT_power_WAPE"]=float(np.abs(pp-pa).sum()/max(np.abs(pa).sum(),1e-12))
    canonical=pd.read_csv(OUT/"V25M_BASELINE_HARMONIZATION_RESULTS.csv")
    baseline_rows=[]
    for model in ("C-B0_B2_LIGHTGBM_TWEEDIE","C-B1_B3_LIGHTGBM_QUANTILE","C-B4_WEEKDAY_FACTORIZED"):
        baseline_rows.append(baseline_row(model,"REPRODUCED",canonical.loc[canonical.model.eq(model)].iloc[0].dropna().to_dict()))
    baseline_rows.extend([baseline_row("B2_COHERENT_F0_BR_A","REPRODUCED",base_metrics),
        baseline_row("B4_DIRECT_LIGHTGBM_EXPLICIT","REPRODUCED",{"Mean_WAPE":float(np.abs(np.asarray(b4_daily)-actual).sum()/actual.sum())}),
        baseline_row("B5_LIGHTGBM_BINARY_P90_CORRECTION","REPRODUCED",{"Mean_WAPE":float(np.abs(np.asarray(b5_daily)-actual).sum()/actual.sum()),"Burst_WAPE":float(np.abs(np.asarray(b5_daily)[burst]-actual[burst]).sum()/actual[burst].sum())}),
        baseline_row("B6_SINGLE_P90_RESIDUAL","REPRODUCED",{"Mean_WAPE":float(np.abs(np.asarray(b6_daily)-actual).sum()/actual.sum()),"Burst_WAPE":float(np.abs(np.asarray(b6_daily)[burst]-actual[burst]).sum()/actual[burst].sum())}),
        baseline_row("B7_MULTI_THRESHOLD_NO_ENCODER_BEC_A","REPRODUCED",beacon_metrics),
        baseline_row("B8_EQRN_STYLE_P95","NOT_REPRODUCED_WITH_REASON",reason="FALSE_HAZARD_GATE_AND_P95_SUPPORT_4_TO_10_PER_FOLD"),
        baseline_row("B9_TAIL_ONLY_FASER_ADAPTATION","NOT_REPRODUCED_WITH_REASON",reason="FALSE_HAZARD_GATE_PROHIBITS_ANALOG_CONFIG"),
        baseline_row("B10_FASER_V24M","SERIALIZED_REFERENCE",{"Mean_WAPE":1.1877478294617465,"Q50_WAPE":.9414334518461079,"CRPS":2454.95935288857,"Burst_WAPE":.763990358554532,"aggregate_mass_ratio":1.1200518371982742}),
        baseline_row("B11_BEACON_EXPLICIT_ONLY","REPRODUCED",beacon_metrics),baseline_row("B12_FULL_BEACON","NOT_RUN_HAZARD_GATE_FALSE",reason="PREREGISTERED_RULE_BEC_A_ONLY")])
    pd.DataFrame(baseline_rows).to_csv(OUT/"V25M_BASELINE_BLOCKED_CV_RESULTS.csv",index=False)
    per_fold=[]
    for fold_id,part in frame.groupby("fold_id"):
        per_fold.append({"fold_id":int(fold_id),**point_metrics(part.actual_GPU_h.to_numpy(),part.mean_GPU_h.to_numpy(),part.Q50_GPU_h.to_numpy(),part.Q90_GPU_h.to_numpy(),part.Q95_GPU_h.to_numpy(),part.CRPS.to_numpy(),part.burst.to_numpy(bool),part.body.to_numpy(bool))})
    pd.DataFrame([{"aggregation":"POOLED_OOF_PRIMARY",**beacon_metrics},*[{"aggregation":f"FOLD_{row.pop('fold_id')}",**row} for row in per_fold]]).to_csv(OUT/"V25M_BEACON_BLOCKED_CV_RESULTS.csv",index=False)
    best_mean=float(canonical.Mean_WAPE.min()); best_crps=float(canonical.CRPS.min()); best_q50=float(canonical.Q50_WAPE.min())
    abs_difference=np.abs(frame.mean_GPU_h-actual)-np.abs(pd.read_csv(OUT/"V25M_CANONICAL_BASELINE_DAILY_OOF.csv").query("model == 'C-B4_WEEKDAY_FACTORIZED'").mean_GPU_h.to_numpy()-actual)
    crps_difference=frame.CRPS.to_numpy()-pd.read_csv(OUT/"V25M_CANONICAL_BASELINE_DAILY_OOF.csv").query("model == 'C-B1_B3_LIGHTGBM_QUANTILE'").CRPS.to_numpy()
    bootstrap={"absolute_error_difference_CI":paired_block_CI(abs_difference),"CRPS_difference_CI":paired_block_CI(crps_difference)}
    gates={"novelty":True,"hazard_signal":False,"mean_historical":beacon_metrics["Mean_WAPE"]<=.927302659814271,
        "mean_5pct_vs_best":beacon_metrics["Mean_WAPE"]<=.95*best_mean,"Q50_noninferiority":beacon_metrics["Q50_WAPE"]<=1.01*best_q50,
        "CRPS_5pct":beacon_metrics["CRPS"]<=.95*best_crps,"burst_noninferiority":beacon_metrics["Burst_WAPE"]<=.847146966830785,
        "mass_0_9_1_1":.9<=beacon_metrics["aggregate_mass_ratio"]<=1.1,"P90_Brier_skill":beacon_metrics["P90_Brier_skill"]>0,
        "bootstrap_absolute_error":bootstrap["absolute_error_difference_CI"][1]<0,"bootstrap_CRPS":bootstrap["CRPS_difference_CI"][1]<0}
    accepted=all(gates.values())
    write("V25M_MODEL_COMPARISON.json",{"artifact_id":"V25M_MODEL_COMPARISON_V1","canonical_days":151,"BEC_A":beacon_metrics,"coherent_F0":base_metrics,"best_conventional":{"Mean_WAPE":best_mean,"Q50_WAPE":best_q50,"CRPS":best_crps},"bootstrap":bootstrap,"April_reads":0})
    write("V25M_BEACON_ACCEPTANCE_TEST.json",{"artifact_id":"V25M_BEACON_ACCEPTANCE_TEST_V1","gates":gates,"BEACON_PROPOSED_MODEL_ACCEPTED":accepted,"decisive_failure":"HAZARD_SIGNAL_GATE_FALSE","classification":"V25M_BEACON_NOVELTY_PASS_HAZARD_SIGNAL_FAIL"})
    ablations=[]
    for label,description,status,metric in [
        ("A0","raw B2/B3","REPRODUCED",canonical.loc[canonical.model.eq("C-B5_B2_B3_PRODUCTION_HYBRID")].iloc[0].dropna().to_dict()),
        ("A1","coherent F0 only","REPRODUCED",base_metrics),("A4","hazard ladder + explicit","REPRODUCED",beacon_metrics),
        ("A8","without hazard calibration","NOT_RUN_FALSE_GATE_MINIMAL_CONFIG_ONLY",{}),("A11","without tail analog","SAME_AS_BEC_A",beacon_metrics),
        ("A12","without SSL","SAME_AS_BEC_A",beacon_metrics),("A13","without regime shape","SAME_AS_BEC_A",beacon_metrics),
        ("A14","simple LightGBM binary correction","REPRODUCED",baseline_rows[5]),("A15","Full BEACON","NOT_RUN_HAZARD_GATE_FALSE",{})]:
        ablations.append({"ablation":label,"description":description,"status":status,**metric})
    for label in ("A2","A3","A5","A6","A7","A9","A10"):
        ablations.append({"ablation":label,"status":"NOT_RUN_HAZARD_GATE_FALSE_MINIMAL_BEC_A_RULE"})
    pd.DataFrame(ablations).to_csv(OUT/"V25M_ABLATION_RESULTS.csv",index=False)
    write("V25M_QUEUE_DIAGNOSTIC.json",{"artifact_id":"V25M_QUEUE_DIAGNOSTIC_V1","evaluation_only":True,"days":len(queue_records),
        "predicted_submitted_GPU_h":float(predicted_tensors.sum()),"predicted_served_GPU_h":sum(r["predicted"]["served_GPU_h"] for r in queue_records),
        "terminal_backlog_GPU_h":sum(r["predicted"]["terminal_backlog_GPU_h"] for r in queue_records),"hidden_shedding_GPU_h":0.0,
        "max_work_conservation_error_GPU_h":max(r["predicted"]["work_conservation_abs_error_GPU_h"] for r in queue_records)})
    write("V25M_POWER_DIAGNOSTIC.json",{"artifact_id":"V25M_POWER_DIAGNOSTIC_V1","boundary":"IT_SIDE","PUE_calls":0,"GPU_h_scale_calls":0,"beta_AIDC_calls":0,
        "IT_power_WAPE":beacon_metrics["IT_power_WAPE"],"facility_scale_model_selection_reads":0})
    print(json.dumps({"BEC_A":beacon_metrics,"accepted":accepted,"runtime_s":time.perf_counter()-started}))


if __name__=="__main__": main()
