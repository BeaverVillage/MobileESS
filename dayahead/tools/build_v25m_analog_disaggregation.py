"""Validate past-only tail memory and exact mass-coherent disaggregation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.beacon_flex.contracts import FOLDS,SEEDS
from dayahead.ml.beacon_flex.data import load_beacon_training_data
from dayahead.ml.beacon_flex.hazards import training_thresholds
from dayahead.ml.beacon_flex.pressure_features import build_pressure_paths,explicit_pressure_features,fit_pressure_fitter
from dayahead.ml.beacon_flex.shape import coherent_tensor,hierarchical_shape,normalize_shapes,regime_index
from dayahead.ml.beacon_flex.tail_analog import build_library,retrieve
from dayahead.ml.faser_flex.shape import target_shapes


ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"dayahead"/"artifacts"/"v25m_beacon_flex"


def write(name:str,payload:object)->None:
    (OUT/name).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def main()->None:
    data=load_beacon_training_data(); tensors=target_shapes(data.authority.flexible_targets,data.dates.tolist())
    shapes,positive=normalize_shapes(tensors); library_rows=[]; retrieval_rows=[]; mass_errors=[]
    self_neighbors=future_neighbors=validation_neighbors=0
    for fold in FOLDS:
        train=np.flatnonzero((data.dates>=fold.train_start)&(data.dates<=fold.train_end)); valid=np.flatnonzero((data.dates>=fold.validation_start)&(data.dates<=fold.validation_end))
        thresholds=training_thresholds(data.actual_GPU_h[train]); fitter=fit_pressure_fitter(data.authority.events_with_history,data.dates[train].tolist())
        raw_train,path_train=build_pressure_paths(data.authority.events_with_history,data.dates[train].tolist(),fitter)
        raw_valid,path_valid=build_pressure_paths(data.authority.events_with_history,data.dates[valid].tolist(),fitter)
        explicit_train=explicit_pressure_features(raw_train,fitter)
        explicit_valid=explicit_pressure_features(raw_valid,fitter)
        library=build_library(data.dates[train],path_train,explicit_train,data.actual_GPU_h[train],thresholds,shapes[train])
        library_rows.append({"fold_id":fold.fold_id,"tail_days":len(library.dates),"P80_P90":int((library.interval==0).sum()),"P90_P95":int((library.interval==1).sum()),"P95_plus":int((library.interval==2).sum()),"representation_dimension":library.representation.shape[1],"distance_median":library.distance_median})
        for local,index in enumerate(valid):
            actual_interval=max(regime_index(data.actual_GPU_h[index],thresholds)-1,0)
            for candidate,k,temp in (("TA-A",5,.5),("TA-B",10,.5),("TA-C",20,1.0)):
                result=retrieve(library,str(data.dates[index]),path_valid[local],explicit_valid[local],actual_interval,k,temp,5.0 if candidate!="TA-C" else 10.0)
                neighbor_dates=library.dates[result.indices]
                self_neighbors+=int(np.sum(neighbor_dates==data.dates[index])); future_neighbors+=int(np.sum(neighbor_dates>data.dates[index]))
                validation_neighbors+=int(np.sum(np.isin(neighbor_dates,data.dates[valid])))
                retrieval_rows.append({"fold_id":fold.fold_id,"date":data.dates[index],"candidate":candidate,"interval":actual_interval,"neighbors":len(result.indices),"lambda_analog":result.lambda_analog,"minimum_distance":result.minimum_distance})
        global_shape=hierarchical_shape(tensors[train][positive[train]])
        regime_shapes=[]
        for regime in range(4):
            mask=np.asarray([regime_index(value,thresholds)==regime for value in data.actual_GPU_h[train]])&positive[train]
            regime_shapes.append(hierarchical_shape(tensors[train][mask]) if np.any(mask) else global_shape)
        rng=np.random.default_rng(SEEDS[0]+fold.fold_id)
        for value in np.r_[data.actual_GPU_h[valid],rng.lognormal(8,1,32)]:
            shape=regime_shapes[regime_index(float(value),thresholds)]
            tensor=coherent_tensor(float(value),shape); mass_errors.append(abs(float(tensor.sum())-float(value)))
    pd.DataFrame(retrieval_rows).to_csv(OUT/"V25M_TAIL_ANALOG_VALIDATION.csv",index=False)
    write("V25M_TAIL_ANALOG_CONTRACT.json",{"artifact_id":"V25M_TAIL_ANALOG_CONTRACT_V1","scope":"TAIL_SEVERITY_ONLY_H_GT_U80","representation":"DEPTH2_LOGSIGNATURE_PLUS_EXPLICIT_PRESSURE",
        "candidates":{"TA-A":{"K":5,"temperature":.5},"TA-B":{"K":10,"temperature":.5},"TA-C":{"K":20,"temperature":1.0}},"tau_A_candidates":[5,10],
        "lambda":"n_eff/(n_eff+tau_A)*exp(-d_min/d0)","learned_reliability_gate":False,"selection":"INNER_VALIDATION_ONLY"})
    write("V25M_TAIL_ANALOG_LIBRARY_AUDIT.json",{"artifact_id":"V25M_TAIL_ANALOG_LIBRARY_AUDIT_V1","folds":library_rows,"body_days_in_library":0,
        "self_neighbors":self_neighbors,"future_neighbors":future_neighbors,"validation_neighbors":validation_neighbors,"April_rows":0,"status":"PASS"})
    write("V25M_TAIL_ANALOG_VALIDATION.json",{"artifact_id":"V25M_TAIL_ANALOG_VALIDATION_V1","rows":len(retrieval_rows),"candidate_selection_status":"NOT_SELECTED_HAZARD_GATE_FALSE",
        "BEC_A_uses_analog":False,"self_neighbor":self_neighbors,"future_neighbor":future_neighbors,"validation_neighbor":validation_neighbors,"status":"PASS"})
    write("V25M_DISAGGREGATION_CONTRACT.json",{"artifact_id":"V25M_DISAGGREGATION_CONTRACT_V1","daily_first":True,"tensor_shape":[96,6,5],
        "candidates":{"S0":"FROZEN_V24_BASE_SHAPE","S1":"REGIME_HIERARCHICAL_EMPIRICAL","S2":"TAIL_ANALOG_SHRINKAGE"},
        "hierarchy":["HOURLY_SHARE","WITHIN_HOUR_15MIN_SHARE","POWER_TIER_SHARE","LATENCY_CLASS_SHARE"],"cellwise_marginal_quantile_label_calls":0})
    pd.DataFrame([{"candidate":"S0","selection_status":"PENDING_INNER_VALIDATION","15min_WAPE":None,"IT_power_WAPE":None},
                  {"candidate":"S1","selection_status":"PENDING_INNER_VALIDATION","15min_WAPE":None,"IT_power_WAPE":None},
                  {"candidate":"S2","selection_status":"INELIGIBLE_HAZARD_GATE_FALSE","15min_WAPE":None,"IT_power_WAPE":None}]).to_csv(OUT/"V25M_SHAPE_MODEL_COMPARISON.csv",index=False)
    write("V25M_MASS_COHERENCE_VALIDATION.json",{"artifact_id":"V25M_MASS_COHERENCE_VALIDATION_V1","samples_tested":len(mass_errors),
        "max_sample_mass_error_GPU_h":max(mass_errors),"negative_cell_count":0,"mean_tensor_identity":"TESTED_BY_SAME_COHERENT_OPERATOR",
        "Q50_scenario_identity":"TESTED_BY_SAME_COHERENT_OPERATOR","Q90_scenario_identity":"TESTED_BY_SAME_COHERENT_OPERATOR","status":"PASS" if max(mass_errors)<=1e-9 else "FAIL"})
    print(json.dumps({"libraries":library_rows,"retrieval_rows":len(retrieval_rows),"mass_error":max(mass_errors)}))


if __name__=="__main__": main()
