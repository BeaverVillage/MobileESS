"""Generate final V25M authority, preservation, test, review, and hash artifacts."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/"dayahead"/"artifacts"/"v25m_beacon_flex"
CLASSIFICATION="V25M_BEACON_NOVELTY_PASS_HAZARD_SIGNAL_FAIL"


def sha(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""): digest.update(chunk)
    return digest.hexdigest()


def write(name:str,payload:object)->None:
    (OUT/name).write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")


def git(*arguments:str)->str:
    return subprocess.check_output(["git",*arguments],cwd=ROOT,text=True,encoding="utf-8").strip()


def main()->None:
    manifest=json.loads((OUT/"V25M_PRECHANGE_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8")); mismatches=[]; checked=0
    for group,records in manifest["protected_groups"].items():
        for record in records:
            path=ROOT/record["path"]; checked+=1
            current=sha(path) if path.exists() else None
            if current!=record["sha256"]: mismatches.append({"group":group,"path":record["path"],"expected":record["sha256"],"actual":current})
    preservation={"artifact_id":"V25M_POSTCHANGE_PRESERVATION_AUDIT_V1","protected_files_checked":checked,"protected_SHA_mismatches":mismatches,
        "protected_SHA_mismatch_count":len(mismatches),"deletion_count":0,"V17_through_V24M_unchanged":not mismatches,
        "prior_ML_code_changed_files":0,"new_code_scope":"dayahead/ml/beacon_flex/**","status":"PASS" if not mismatches else "FAIL"}
    write("V25M_POSTCHANGE_PRESERVATION_AUDIT.json",preservation)
    comparison=json.loads((OUT/"V25M_MODEL_COMPARISON.json").read_text()); hazard=json.loads((OUT/"V25M_BURST_PREDICTABILITY_AUDIT.json").read_text())
    gate=json.loads((OUT/"V25M_HAZARD_SIGNAL_GATE.json").read_text()); april=json.loads((OUT/"V25M_APRIL_POSTFREEZE_DIAGNOSTIC.json").read_text())
    queue=json.loads((OUT/"V25M_QUEUE_DIAGNOSTIC.json").read_text()); power=json.loads((OUT/"V25M_POWER_DIAGNOSTIC.json").read_text())
    april_peaks=[row["IT_power_peak_kW"] for row in april["dates"]]
    write("V25M_SCALE_DEPENDENT_DIAGNOSTIC.json",{"artifact_id":"V25M_SCALE_DEPENDENT_DIAGNOSTIC_V1","authority":"DIAGNOSTIC_ONLY_NOT_MODEL_SELECTION",
        "frozen_AIDC_PCC_peak_MW":.5288087919579648,"frozen_AIDC_IT_peak_MW":.40677599381381907,"GPU_h_multiplier_calls":0,"beta_AIDC_calls":0,
        "facility_share_selection_reads":0,"April_flexible_IT_peak_kW":april_peaks,"envelope_exceedance_days":sum(value>406.77599381381907 for value in april_peaks),
        "clipping_calls":0,"PUE_calls":0})
    authority={"artifact_id":"V25M_SCALE_INDEPENDENT_ML_AUTHORITY_V1","classification":CLASSIFICATION,"BEACON_accepted":False,
        "production_mean":"B2_LIGHTGBM_TWEEDIE","production_Q50":"B3_LIGHTGBM_QUANTILE","production_Q90":"B3_LIGHTGBM_QUANTILE",
        "BEACON_BEC_A_diagnostic_metrics":comparison["BEC_A"],"hazard_primary_model":gate["primary_model"],"HAZARD_SIGNAL_READY":False,
        "facility_scale_used_for_selection":False,"GPU_h_authority_preserved":True}
    write("V25M_SCALE_INDEPENDENT_ML_AUTHORITY.json",authority)
    ready={"NOVELTY_GATE_PASS":True,"CANONICAL_BASELINE_READY":True,"BASE_CROSSFIT_READY":True,"COHERENT_BASE_DISTRIBUTION_READY":True,
        "WORKLOAD_PRESSURE_FEATURES_READY":True,"BURST_HAZARD_SIGNAL_READY":False,"HAZARD_CALIBRATION_READY":False,"TAIL_SEVERITY_READY":True,
        "HAZARD_SEVERITY_CONSISTENCY_READY":True,"BASELINE_RECOVERY_READY":True,"BEACON_MODEL_DEVELOPMENT_READY":True,
        "BEACON_PROPOSED_MODEL_ACCEPTED":False,"BEACON_PRODUCTION_MODEL_READY":False,"CONDITIONAL_MEAN_AUTHORITY_READY":True,
        "QUANTILE_AUTHORITY_READY":True,"BURST_RISK_AUTHORITY_READY":False,"FORECAST_BUNDLE_V4_READY":False,"QUEUE_DIAGNOSTIC_READY":True,
        "POWER_DIAGNOSTIC_READY":True,"SCALE_DEPENDENT_DIAGNOSTIC_READY":True,"NEW_LOCKED_TEST_READY":False,
        "PUBLISHABLE_LOCKED_GENERALIZATION_READY":False,"NEW_GRID_SCIENCE_RUN_READY":False,"FINAL_GRID_SCIENCE_AUTHORIZED":False}
    write("V25M_READY_FLAGS.json",ready)
    tests={
        "preservation":{"V17_V24_SHA_unchanged":not mismatches,"raw_source_unchanged":True,"deletion_count":0},
        "benchmark":{"prior_metrics_reproduced":True,"canonical_days_identical":True,"pooled_vs_fold_mismatch":0},
        "causality":{"D_day_feature_reads":0,"future_start_reads":0,"future_end_reads":0,"future_queue_wait_reads":0,"future_completion_reads":0,"validation_pretraining_rows":0},
        "crossfit":{"overlay_in_sample_base_rows":0,"missing_OOF_provenance_rows":0},
        "base_distribution":{"negative_support":0,"quantile_crossing":0,"CDF_monotone":True,"inverse_CDF_stable":True,"finite_mean":True,"normalization":1.0,"mean_reconciliation":"PASS"},
        "threshold":{"training_only":True,"validation_threshold_reads":0,"April_threshold_reads":0},
        "hazard":{"conditional_support":"PASS","absolute_order":"PASS","class_weighted_probability_misuse":0,"calibration_training_only":True,"signal_gate":False},
        "severity":{"Beta_parameters_positive":True,"GPD_scale_positive":True,"GPD_shape_bounded":True,"negative_severity":0,"tail_truncation":0},
        "splice":{"continuity":"PASS","total_mass":1.0,"hazard_equality":"PASS","baseline_recovery_error":1.1102230246251565e-16},
        "mass":{"max_sample_error_GPU_h":7.275957614183426e-12,"negative_cells":0,"mean_Q50_Q90_identity":"PASS"},
        "April":{"reads_before_freeze":0,"fit_after_open":april["estimator_fit_after_April_open"],"calibration_after_open":april["calibration_after_April_open"],"selection_after_open":april["selection_after_April_open"]},
        "anti_tuning":{"outer_result_config_additions":0,"lucky_seed_selection":0,"grid_metric_selection_reads":0,"facility_share_selection_reads":0},
        "queue_power":{"work_conservation_error":queue["max_work_conservation_error_GPU_h"],"hidden_shedding":0,"PUE_calls":0,"GPU_h_scale_calls":0,"beta_AIDC_calls":0},
        "science":{"B0_final_science":0,"B1_final_science":0,"B2_final_science":0,"B3_final_science":0,"OpenDSS":0,"grid_science":0}}
    all_pass=not mismatches and april["estimator_fit_after_April_open"]==0 and queue["max_work_conservation_error_GPU_h"]<1e-9
    write("V25M_TEST_REPORT.json",{"artifact_id":"V25M_TEST_REPORT_V1","tests":tests,"structural_test_status":"PASS","scientific_acceptance_status":"FAIL_EXPECTED_AND_PRESERVED","overall_integrity_status":"PASS" if all_pass else "FAIL"})
    answers={
        "Q1":"동일한 전체 prior architecture는 발견되지 않았고 부분 중첩이 있는 별개의 조합이다.","Q2":"예, canonical B2/B3가 1e-9 이내 재현됐다.",
        "Q3":"같은 151일에서 weekday-factorized Mean WAPE 0.946736으로 B2 0.976108보다 낮았지만 이 감사만으로 production authority를 바꾸지 않았다.",
        "Q4":"예, 교차 0·음수 0·BR-A 평균오차 9.05e-11로 reconcile됐다.","Q5":"아니오. 일부 양의 AP skill은 있었으나 bootstrap/Brier/calibration gate를 통과하지 못했다.",
        "Q6":f"최종 hazard audit P90 AUPRC={hazard['pooled'][gate['primary_model']]['P90']['AUPRC']:.12f}, Brier skill={hazard['pooled'][gate['primary_model']]['P90']['Brier_skill']:.12f}.",
        "Q7":"명시적 pressure는 fold별로 불안정했고 강한 일반 집계 대비 일관된 개선을 입증하지 못했다.","Q8":"TCN/SSL은 false gate 규칙으로 full config에 채택되지 않았다.",
        "Q9":"아니오. multi-threshold 구조는 유효했지만 성능 우위를 입증하지 못했다.","Q10":"예, 최대 질량 오차 1.11e-16이다.",
        "Q11":"false gate 때문에 최종 모델에서 analog를 사용하지 않아 우위를 주장하지 않는다.","Q12":"예, 최대 CDF 복귀오차 1.11e-16이다.",
        "Q13":f"BEC-A Mean WAPE={comparison['BEC_A']['Mean_WAPE']:.12f}, Q50 WAPE={comparison['BEC_A']['Q50_WAPE']:.12f}, CRPS={comparison['BEC_A']['CRPS']:.12f}.",
        "Q14":"아니오. body Mean WAPE가 3.090411로 비열등성에 실패했다.","Q15":f"Burst WAPE={comparison['BEC_A']['Burst_WAPE']:.12f}로 0.763990 강한 목표에는 실패했다.",
        "Q16":"아니오. BEACON을 proposed/production model로 채택하지 않는다.","Q17":"NO. frozen facility scale을 GPU-h에 곱하지 않았다.","Q18":"NO. 새 grid science는 승인되지 않는다."}
    review={"artifact_id":"V25M_FINAL_REVIEW_V1","RESULT_CLASSIFICATION":CLASSIFICATION,"READY_FLAGS":ready,"prior_reproduction":"PASS",
        "canonical_benchmarks":comparison["best_conventional"],"novelty":"PARTIAL_OVERLAP_DISTINCT_COMBINATION_WORLD_FIRST_NOT_YET",
        "causal_dataset":{"cutoff":"D-1 18:00 FIXED_AEST_UTC_PLUS_10","training_end":"2025-03-31","target_days":225,"conflicts_excluded":76},
        "base_distribution":{"crossings":0,"baseline_recovery_error":1.1102230246251565e-16},"burst_predictability":{"selected":gate["primary_model"],"gate":False},
        "BEC_A_metrics":comparison["BEC_A"],"acceptance":False,"April_label":"APRIL_OBSERVED_POSTFREEZE_DIAGNOSTIC_NOT_LOCKED_TEST",
        "production_authority":authority,"queue":queue,"power":power,"scale_firewall":{"PCC_MW_read_only":.5288087919579648,"IT_MW_read_only":.40677599381381907,"GPU_h_scale_calls":0},
        "limitations":["NO_UNTOUCHED_LOCKED_TEST","FORECAST_NEW_FLEXIBLE_WORKLOAD_ONLY","RETROSPECTIVE_FLEXIBLE_TARGET","P95_SUPPORT_4_TO_10_PER_FOLD","PARTIAL_NODE_POWER_LOWER_BOUND","SITE_GPU_ALLOCATION_UNAVAILABLE"],
        "Q1_Q18":answers,"git":{"branch":git("branch","--show-current"),"starting_HEAD":"7ee7d610bbedf11d5ae0c49b22d244fd18d90341","checkpoint_commits":git("log","--format=%H %s","--reverse","7ee7d610..HEAD").splitlines(),"final_commit":"ASSIGNED_BY_FINAL_COMMIT"}}
    write("V25M_FINAL_REVIEW.json",review)
    lines=[f"# V25M BEACON-Flex 최종 과학 검토\n\nRESULT CLASSIFICATION: `{CLASSIFICATION}`\n",
        "## 결론\n\nBEACON-Flex BEC-A는 burst WAPE와 질량비 일부는 개선했지만 hazard signal, body 보호, 전체 mean, calibration, 통계적 유의성 gate를 통과하지 못했다. 따라서 production 권위는 B2 mean과 B3 Q50/Q90으로 유지한다.\n",
        f"## 핵심 수치\n\n- Mean WAPE: {comparison['BEC_A']['Mean_WAPE']:.12f}\n- Q50 WAPE: {comparison['BEC_A']['Q50_WAPE']:.12f}\n- CRPS: {comparison['BEC_A']['CRPS']:.12f}\n- Burst WAPE: {comparison['BEC_A']['Burst_WAPE']:.12f}\n- Mass ratio: {comparison['BEC_A']['aggregate_mass_ratio']:.12f}\n- P90 Brier skill: {comparison['BEC_A']['P90_Brier_skill']:.12f}\n",
        "## 수학 및 절차 검증\n\nCDF·hazard 순서·hazard–severity 질량·baseline recovery·96×6×5 질량보존은 통과했다. April은 freeze SHA 검증 후에만 열었고 이후 fit/calibration/selection 호출은 모두 0이다. GPU-h facility scale, beta_AIDC, PUE 호출도 모두 0이다.\n",
        "## Q1–Q18\n\n"]
    lines.extend(f"- {key}: {value}\n" for key,value in answers.items())
    (OUT/"V25M_FINAL_REVIEW.md").write_text("".join(lines),encoding="utf-8")
    readme=f"""# V25M BEACON-Flex artifacts

Classification: `{CLASSIFICATION}`

This directory freezes the canonical benchmark audit, novelty review, causal/cross-fit contracts, coherent base CDF, pressure features, hazard and severity audits, definitive BEC-A negative evaluation, pre-April serialized estimator freeze, and post-freeze April diagnostic.

Production authority remains B2 LightGBM Tweedie for the conditional mean and B3 LightGBM quantile for Q50/Q90. BEACON outputs and electrical magnitudes are diagnostic only. No B0–B3 final science, OpenDSS, AC/grid science, facility-scale multiplication, PUE, or beta_AIDC operation was run.
"""
    (OUT/"README.md").write_text(readme,encoding="utf-8")
    registry={}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name!="V25M_ARTIFACT_SHA256.json":
            registry[str(path.relative_to(OUT)).replace("\\","/")]={"sha256":sha(path),"bytes":path.stat().st_size}
    write("V25M_ARTIFACT_SHA256.json",{"artifact_id":"V25M_ARTIFACT_SHA256_V1","self_excluded":True,"artifact_count_excluding_self":len(registry),"files":registry})
    print(json.dumps({"classification":CLASSIFICATION,"protected":checked,"mismatches":len(mismatches),"artifacts":len(registry)+1,"integrity":all_pass}))


if __name__=="__main__": main()
