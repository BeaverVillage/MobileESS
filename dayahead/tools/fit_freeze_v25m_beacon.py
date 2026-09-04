"""Fit and serialize every final V25M estimator before any April member is opened."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import numpy as np

from dayahead.ml.beacon_flex.base_crossfit import expanding_crossfit
from dayahead.ml.beacon_flex.base_models import fit_base_models
from dayahead.ml.beacon_flex.base_reconciliation import reconcile_batch
from dayahead.ml.beacon_flex.contracts import SEEDS
from dayahead.ml.beacon_flex.data import load_beacon_training_data
from dayahead.ml.beacon_flex.hazard_calibration import SharedBetaHazardCalibrator
from dayahead.ml.beacon_flex.hazards import AnchoredHazardLadder,base_exceedance_probabilities,exceedance_labels,training_thresholds
from dayahead.ml.beacon_flex.pressure_features import build_pressure_paths,explicit_pressure_features,fit_pressure_fitter
from dayahead.ml.beacon_flex.severity import SeverityModel
from dayahead.ml.beacon_flex.shape import normalize_shapes
from dayahead.ml.beacon_flex.tail_analog import build_library
from dayahead.ml.faser_flex.shape import target_shapes


ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"dayahead"/"artifacts"/"v25m_beacon_flex"; MODELS=OUT/"models"


def sha(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()


def tree_hash(paths:list[Path])->str:
    digest=hashlib.sha256()
    for path in sorted(paths,key=lambda item:str(item)):
        digest.update(str(path.relative_to(ROOT)).replace("\\","/").encode()); digest.update(path.read_bytes())
    return digest.hexdigest()


def main()->None:
    MODELS.mkdir(exist_ok=True); data=load_beacon_training_data()
    if data.authority.source.get("April_members_opened")!=0 or data.authority.source.get("target_month_max")!=202503:
        raise RuntimeError("V25M_PREAPRIL_DATA_FIREWALL")
    indices=np.arange(len(data.dates)); thresholds=training_thresholds(data.actual_GPU_h)
    fitter=fit_pressure_fitter(data.authority.events_with_history,data.dates.tolist())
    raw,normalized=build_pressure_paths(data.authority.events_with_history,data.dates.tolist(),fitter)
    explicit=explicit_pressure_features(raw,fitter); labels=exceedance_labels(data.actual_GPU_h,thresholds)
    crossfit=expanding_crossfit(data.macro_features,data.actual_GPU_h,indices,SEEDS[0])
    cross_bases=reconcile_batch(crossfit.mean_GPU_h,crossfit.quantiles_GPU_h,"BR-A"); cross_p=base_exceedance_probabilities(cross_bases,thresholds)
    positions=crossfit.indices; calibration_count=14; fit=np.arange(len(positions)-calibration_count); calibration=np.arange(len(positions)-calibration_count,len(positions))
    ladder=AnchoredHazardLadder().fit(explicit[positions[fit]],labels[positions[fit]],cross_p[fit])
    calibrator=SharedBetaHazardCalibrator().fit(ladder.predict_conditional(explicit[positions[calibration]],cross_p[calibration]),labels[positions[calibration]])
    severity=SeverityModel.fit(data.actual_GPU_h,thresholds); base_models=fit_base_models(data.macro_features,data.actual_GPU_h,SEEDS[0])
    tensors=target_shapes(data.authority.flexible_targets,data.dates.tolist()); shapes,positive=normalize_shapes(tensors)
    shape=np.mean(shapes[positive],axis=0); shape/=shape.sum()
    tail_library=build_library(data.dates,normalized,explicit,data.actual_GPU_h,thresholds,shapes)
    state={"schema":"V25M_SERIALIZED_STATE_V1","training_cutoff":"2025-03-31","production_authority":{"mean":"B2_LIGHTGBM_TWEEDIE","Q50":"B3_LIGHTGBM_QUANTILE","Q90":"B3_LIGHTGBM_QUANTILE"},
        "diagnostic_config":"BEC-A","base_models":base_models,"pressure_fitter":fitter,"hazard_ladder":ladder,"hazard_calibrator":calibrator,
        "severity":severity,"thresholds_GPU_h":thresholds,"shape":shape,"tail_analog_library":tail_library,"event_encoder":None,
        "event_encoder_reason":"HAZARD_GATE_FALSE_BEC_A_EXPLICIT_ONLY","April_reads_before_serialization":0}
    model_path=MODELS/"V25M_FINAL_SERIALIZED_STATE.pkl"
    with model_path.open("wb") as stream: pickle.dump(state,stream,protocol=pickle.HIGHEST_PROTOCOL)
    config_path=MODELS/"V25M_EXACT_CONFIG.json"
    config_path.write_text(json.dumps({"selected_production":"B2_B3_FALLBACK","diagnostic":"BEC-A","base":"BR-A","event_encoder":None,
        "hazard":"ANCHORED_EXPLICIT","calibration":"SHARED_POSITIVE_SLOPE_BETA","severity":"BETA_BETA_POOLED_GPD","shape":"S0","analog":"NOT_USED"},indent=2)+"\n")
    code_files=list((ROOT/"dayahead"/"ml"/"beacon_flex").rglob("*.py"))+list((ROOT/"dayahead"/"tools").glob("*v25m*.py"))
    hashes={"serialized_state_sha256":sha(model_path),"exact_config_sha256":sha(config_path),"code_tree_sha256":tree_hash(code_files),
            "raw_data_sha256":data.authority.source["source_sha256"]}
    payload={"artifact_id":"V25M_MODEL_SELECTION_PRE_APRIL_FREEZE_V1","freeze_complete":True,"selected_base":"BR-A_DIAGNOSTIC_WITH_B2_B3_PRODUCTION_FALLBACK",
        "selected_BEACON_config":"BEC-A_DEFINITIVE_NEGATIVE_ONLY","selected_hazard":"ANCHORED_EXPLICIT","selected_calibration":"SHARED_POSITIVE_SLOPE_BETA",
        "selected_severity":"BETA_BETA_POOLED_GPD","selected_shape":"S0_FROZEN_BASE","selected_event_encoder":None,"selected_tail_analog":None,
        "novelty_result":"PARTIAL_OVERLAP_DISTINCT_COMBINATION","acceptance_result":"REJECTED_HAZARD_SIGNAL_AND_PERFORMANCE",
        "production_mean":"B2_LIGHTGBM_TWEEDIE","production_Q50_Q90":"B3_LIGHTGBM_QUANTILE","model_hashes":hashes,"data_month_max":202503,
        "April_reads_before_freeze":0,"all_estimators_fit_before_April":True,"post_April_fit_calls":0,"post_April_calibration_calls":0,"post_April_selection_calls":0}
    freeze=OUT/"V25M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"; freeze.write_text(json.dumps(payload,indent=2)+"\n")
    freeze_sha=sha(freeze); (OUT/"V25M_MODEL_SELECTION_PRE_APRIL_FREEZE.sha256").write_text(freeze_sha+"\n")
    print(json.dumps({"freeze_sha256":freeze_sha,**hashes}))


if __name__=="__main__": main()
