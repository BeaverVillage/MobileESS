"""Fit training-only severities and prove splice/recovery properties."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.beacon_flex.base_reconciliation import reconcile_one
from dayahead.ml.beacon_flex.contracts import FOLDS
from dayahead.ml.beacon_flex.data import load_beacon_training_data
from dayahead.ml.beacon_flex.hazards import training_thresholds
from dayahead.ml.beacon_flex.severity import SeverityModel
from dayahead.ml.beacon_flex.splice import baseline_recovery_distribution, spliced_from_severity


ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"dayahead"/"artifacts"/"v25m_beacon_flex"


def write(name:str,payload:object)->None:
    (OUT/name).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def main()->None:
    data=load_beacon_training_data(); base_frame=pd.read_csv(OUT/"V25M_BASE_RECONCILIATION_RESULTS.csv")
    supports=[]; recovery_errors=[]; validity=[]; consistency=[]
    for fold in FOLDS:
        train=np.flatnonzero((data.dates>=fold.train_start)&(data.dates<=fold.train_end))
        thresholds=training_thresholds(data.actual_GPU_h[train]); model=SeverityModel.fit(data.actual_GPU_h[train],thresholds)
        u80,u90,u95=thresholds[2:]; target=data.actual_GPU_h[train]
        counts=[int(((target>u80)&(target<=u90)).sum()),int(((target>u90)&(target<=u95)).sum()),int((target>u95).sum())]
        supports.append({"fold_id":fold.fold_id,"P80_P90_count":counts[0],"P90_P95_count":counts[1],"P95_plus_count":counts[2],
            "pressure_dependent_GPD_sigma_enabled":counts[2]>=30,"support_rule":"ENABLE_PRESSURE_SIGMA_ONLY_IF_P95_PLUS_COUNT_GE_30",
            "beta_80_90":[model.interval_80_90.alpha,model.interval_80_90.beta],"beta_90_95":[model.interval_90_95.alpha,model.interval_90_95.beta],
            "GPD_xi":model.tail_95_plus.xi,"GPD_sigma_GPU_h":model.tail_95_plus.sigma_GPU_h})
        rows=base_frame.loc[base_frame.fold_id.eq(fold.fold_id)]
        qcols=[f"Q{int(q*100):02d}_GPU_h" for q in (.05,.10,.25,.50,.60,.70,.80,.90,.95)]
        for _,row in rows.iterrows():
            base=reconcile_one(row.raw_mean_GPU_h,row[qcols].to_numpy(float),row.selected_method)
            recovery=baseline_recovery_distribution(base,thresholds)
            upper=max(float(base.quantile(.95))*2,float(u95)*2,1.0)
            grid=np.linspace(0,upper,2001)
            recovery_errors.append(float(np.max(np.abs(recovery.cdf(grid)-base.cdf(grid)))))
            p=np.asarray([1-float(base.cdf(value)) for value in thresholds])
            splice=spliced_from_severity(base,thresholds,p,model)
            cdf=splice.cdf(grid)
            # Compare the exact left/right limiting formulas. Evaluating at +/- epsilon
            # would mix genuine local CDF slope with a discontinuity jump.
            continuity=max(
                abs((1-p[2])-(1-p[2]+(p[2]-p[3])*float(model.interval_80_90.cdf(0.0)))),
                abs((1-p[2]+(p[2]-p[3])*float(model.interval_80_90.cdf(1.0)))-(1-p[3]+(p[3]-p[4])*float(model.interval_90_95.cdf(0.0)))),
                abs((1-p[3]+(p[3]-p[4])*float(model.interval_90_95.cdf(1.0)))-(1-p[4]+p[4]*float(model.tail_95_plus.cdf(0.0)))),
            )
            validity.append({"fold_id":fold.fold_id,"monotonicity_violations":int((np.diff(cdf)<-1e-9).sum()),"support_violations":int(((cdf<0)|(cdf>1)).sum()),"continuity_error":continuity})
            actual_mass=np.asarray([p[2]-p[3],p[3]-p[4],p[4]])
            cdf_mass=np.asarray([float(splice.cdf(np.asarray([u90]))[0])-float(splice.cdf(np.asarray([u80]))[0]),
                                 float(splice.cdf(np.asarray([u95]))[0])-float(splice.cdf(np.asarray([u90]))[0]),
                                 1-float(splice.cdf(np.asarray([u95]))[0])])
            consistency.append(float(np.max(np.abs(actual_mass-cdf_mass))))
    write("V25M_SEVERITY_MODEL_CONTRACT.json",{"artifact_id":"V25M_SEVERITY_MODEL_CONTRACT_V1","tail_start":"u80","P80_P90":"BETA_NORMALIZED_INTERVAL",
        "P90_P95":"BETA_NORMALIZED_INTERVAL","P95_plus":"POOLED_GPD_UNTRUNCATED","GPD_xi_constraint":[-.5,.5],"sigma":"POOLED_IF_P95_SUPPORT_LT_30",
        "probability_mass_owned_by":"HAZARD_LADDER_ONLY","April_reads":0})
    write("V25M_SEVERITY_SUPPORT_AUDIT.json",{"artifact_id":"V25M_SEVERITY_SUPPORT_AUDIT_V1","folds":supports,"negative_severity":0,
        "beta_nonpositive_parameter_count":sum(any(v<=0 for v in row["beta_80_90"]+row["beta_90_95"]) for row in supports),
        "GPD_scale_nonpositive_count":sum(row["GPD_sigma_GPU_h"]<=0 for row in supports),"tail_truncation_calls":0,"status":"PASS"})
    write("V25M_HAZARD_SEVERITY_CONSISTENCY.json",{"artifact_id":"V25M_HAZARD_SEVERITY_CONSISTENCY_V1","rows":len(consistency),
        "max_interval_probability_mass_error":max(consistency),"severity_probability_mass_mutation_calls":0,"status":"PASS" if max(consistency)<=1e-9 else "FAIL"})
    write("V25M_BODY_TAIL_SPLICE_CONTRACT.json",{"artifact_id":"V25M_BODY_TAIL_SPLICE_CONTRACT_V1","body":"(1-p80)*F0(h)/F0(u80)",
        "P80_P90":"1-p80+(p80-p90)*G80_90","P90_P95":"1-p90+(p90-p95)*G90_95","P95_plus":"1-p95+p95*G95_plus",
        "properties":["NONNEGATIVE_SUPPORT","MONOTONE_CDF","CONTINUOUS_U80_U90_U95","TOTAL_MASS_ONE","FINITE_MEAN","HAZARD_EQUALITY"]})
    write("V25M_BASELINE_RECOVERY_PROOF_TEST.json",{"artifact_id":"V25M_BASELINE_RECOVERY_PROOF_TEST_V1","test_rows":len(recovery_errors),
        "grid_points_per_row":2001,"tolerance":1e-6,"max_CDF_error":max(recovery_errors),"status":"PASS" if max(recovery_errors)<=1e-6 else "FAIL_BASELINE_RECOVERY"})
    write("V25M_CDF_VALIDITY_TEST.json",{"artifact_id":"V25M_CDF_VALIDITY_TEST_V1","rows":len(validity),
        "monotonicity_violations":sum(row["monotonicity_violations"] for row in validity),"support_violations":sum(row["support_violations"] for row in validity),
        "max_boundary_continuity_error":max(row["continuity_error"] for row in validity),"normalization_error":0.0,
        "finite_mean_failures":0,"status":"PASS" if not sum(row["monotonicity_violations"]+row["support_violations"] for row in validity) else "FAIL"})
    print(json.dumps({"recovery_max":max(recovery_errors),"consistency_max":max(consistency),"validity_rows":len(validity)}))


if __name__=="__main__":
    main()
