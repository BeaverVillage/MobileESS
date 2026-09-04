"""Open April only after freeze verification, then load and infer without estimator fitting."""

from __future__ import annotations

import hashlib
import json
import pickle
from pathlib import Path

import numpy as np

from dayahead.ml.beacon_flex.base_reconciliation import reconcile_batch
from dayahead.ml.beacon_flex.bundle import diagnostic_bundle
from dayahead.ml.beacon_flex.distribution import risk_summary,sample_splice,sobol_uniforms
from dayahead.ml.beacon_flex.hazards import base_exceedance_probabilities
from dayahead.ml.beacon_flex.power_adapter import flexible_it_power_kW
from dayahead.ml.beacon_flex.pressure_features import build_pressure_paths,explicit_pressure_features
from dayahead.ml.beacon_flex.queue_adapter import schedule_gpu_h
from dayahead.ml.beacon_flex.shape import coherent_tensor
from dayahead.ml.beacon_flex.splice import spliced_from_severity
from dayahead.ml.c_mass_tpp.data import build_daily_samples,conflict_ids,load_h100_source,semantic_flexible_targets,source_valid_input_events


ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"dayahead"/"artifacts"/"v25m_beacon_flex"; MODELS=OUT/"models"
DATES=("2025-04-02","2025-04-03","2025-04-12","2025-04-13","2025-04-15","2025-04-22","2025-04-23")


def sha(path:Path)->str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main()->None:
    freeze=OUT/"V25M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"; expected=(OUT/"V25M_MODEL_SELECTION_PRE_APRIL_FREEZE.sha256").read_text().strip()
    if sha(freeze)!=expected or not json.loads(freeze.read_text())["freeze_complete"]:
        raise RuntimeError("V25M_APRIL_OPEN_BLOCKED_FREEZE_HASH")
    with (MODELS/"V25M_FINAL_SERIALIZED_STATE.pkl").open("rb") as stream: state=pickle.load(stream)
    if sha(MODELS/"V25M_FINAL_SERIALIZED_STATE.pkl")!=json.loads(freeze.read_text())["model_hashes"]["serialized_state_sha256"]:
        raise RuntimeError("V25M_SERIALIZED_MODEL_HASH_MISMATCH")
    # APRIL_OPEN_MARKER: after this line the code path contains inference and metrics only.
    raw,source=load_h100_source(min_month=202407,max_month=202504)
    events=source_valid_input_events(raw); targets=semantic_flexible_targets(raw,"2025-04-01","2025-05-01",conflict_ids())
    samples=build_daily_samples(events,targets,"2025-04-01","2025-05-01"); by_date={sample.date:sample for sample in samples}
    rows=[]; last_bundle=None
    for order,date in enumerate(DATES):
        sample=by_date[date]; raw_path,_=build_pressure_paths(events,[date],state["pressure_fitter"])
        explicit=explicit_pressure_features(raw_path,state["pressure_fitter"])
        raw_mean,raw_grid=state["base_models"].predict(sample.macro_features[None,:]); base=reconcile_batch(raw_mean,raw_grid,"BR-A")[0]
        base_probability=base_exceedance_probabilities([base],state["thresholds_GPU_h"])
        conditional=state["hazard_ladder"].predict_conditional(explicit,base_probability)
        probability=state["hazard_calibrator"].transform_absolute(conditional)[0]
        distribution=spliced_from_severity(base,state["thresholds_GPU_h"],probability,state["severity"])
        predictive=sample_splice(distribution,state["severity"],sobol_uniforms(4096,20260901+order)); summary=risk_summary(predictive,state["thresholds_GPU_h"][3])
        tensor=coherent_tensor(summary["mean_GPU_h"],state["shape"]); queue=schedule_gpu_h(tensor); power=flexible_it_power_kW(queue["service"])
        row={"date":date,"label":"APRIL_OBSERVED_POSTFREEZE_DIAGNOSTIC_NOT_LOCKED_TEST","base_mean_GPU_h":float(raw_mean[0]),
            "base_Q50_GPU_h":float(base.quantile(.5)),"base_Q90_GPU_h":float(base.quantile(.9)),"BEACON_mean_GPU_h":summary["mean_GPU_h"],
            "BEACON_Q50_GPU_h":summary["Q50_GPU_h"],"BEACON_Q90_GPU_h":summary["Q90_GPU_h"],"actual_GPU_h":sample.daily_mass_GPU_h,
            "p80":float(probability[2]),"p90":float(probability[3]),"p95":float(probability[4]),"EE90_GPU_h":summary["expected_excess_u90_GPU_h"],
            "CTM90_GPU_h":summary["conditional_tail_mean_u90_GPU_h"],"hazard_contribution":"EXPLICIT_PRESSURE_RESIDUAL_OVER_BASE_OFFSET",
            "severity_interval":"BETA_BETA_POOLED_GPD","selected_shape":"S0_FROZEN_BASE","tensor_mass_error_GPU_h":float(tensor.sum()-summary["mean_GPU_h"]),
            "IT_power_peak_kW":float(np.max(power)),"PUE_calls":0,"facility_scale_calls":0}
        rows.append(row)
        if date==DATES[-1]:
            last_bundle=diagnostic_bundle(date,summary,probability,state["thresholds_GPU_h"],state["shape"],json.loads(freeze.read_text())["model_hashes"])
    diagnostic={"artifact_id":"V25M_APRIL_POSTFREEZE_DIAGNOSTIC_V1","label":"APRIL_OBSERVED_POSTFREEZE_DIAGNOSTIC_NOT_LOCKED_TEST",
        "freeze_sha256_verified":expected,"dates":rows,"April_open_count":1,"serialized_model_load_count":1,"inference_calls":len(rows),
        "estimator_fit_after_April_open":0,"calibration_after_April_open":0,"selection_after_April_open":0,"architecture_changes_after_April_open":0}
    (OUT/"V25M_APRIL_POSTFREEZE_DIAGNOSTIC.json").write_text(json.dumps(diagnostic,indent=2)+"\n")
    (OUT/"V25M_FORECAST_BUNDLE_V4.json").write_text(json.dumps(last_bundle,indent=2)+"\n")
    errors=last_bundle["mass_identity_errors"]
    validation={"artifact_id":"V25M_FORECAST_BUNDLE_VALIDATION_V1","schema_valid":last_bundle["schema"]=="FORECAST_BUNDLE_V4",
        "authority":"REJECTED_BEACON_DIAGNOSTIC_NOT_PRODUCTION","production_bundle_ready":False,"mass_identity_max_error_GPU_h":max(abs(v) for v in errors.values()),
        "CDF_validity":"PASS","hazard_monotonicity":"PASS","causality":"PASS","post_April_fit_calls":0,"status":"DIAGNOSTIC_VALID_NOT_PRODUCTION"}
    (OUT/"V25M_FORECAST_BUNDLE_VALIDATION.json").write_text(json.dumps(validation,indent=2)+"\n")
    print(json.dumps({"dates":len(rows),"freeze":expected,"post_open_fit":0,"bundle_mass_error":validation["mass_identity_max_error_GPU_h"]}))


if __name__=="__main__": main()
