from .common import *
import sys

def main():
    assert git('rev-parse','HEAD')==BASE
    assert not (OUT/'cal_rolling_predictions.parquet').exists()
    correction={'user_choice':'날짜 종료와 정답 확정 시각을 모두 지난 뒤 편입 — 실제 가용성을 지키는 기준 (권장)',
        'rule':'max(target_day_end, target_label_available_at) < current issue_time',
        'rationale':'159 of 172 frozen OOS day labels mature after their calendar day ends',
        'explicit_user_clarification':True,'before_CAL_candidate_evaluation':True,
        'partial_day_residuals':False,'future_runtime_or_label_information_used':False}
    dump('RESIDUAL_AVAILABILITY_CONTRACT',correction)
    discovery=read('LABEL_AVAILABILITY_DISCOVERY'); discovery['resolution']=correction['rule']; dump('LABEL_AVAILABILITY_DISCOVERY',discovery)
    frozen={}
    for p in (ROOT/'dayahead/v40r6r1').glob('*.py'): frozen[p.relative_to(ROOT).as_posix()]=sha(p)
    for name in ['V40R6R1_OPERATING_POINT.json','V40R6R1_TARGET_IDENTITY_AUDIT.json','V40R6R1_BASE_PREDICTION_IDENTITY.json',
        'V40R6R1_RESIDUAL_AVAILABILITY_CONTRACT.json','V40R6R1_R6_REFERENCE_FREEZE.json']:
        p=OUT/name; frozen[p.relative_to(ROOT).as_posix()]=sha(p)
    for name in ['V40R6_CUMULATIVE_TARGET.parquet','development_baselines.npz','fits/L0/development_q.npy',
        'calibration_predictions.npz','exposed_predictions.npz','V40R6_SELECTION_FREEZE.json','V40R6_HYPERPARAMETER_FREEZE.json',
        'V40R6_PREREGISTRATION.json','V40R6_FINAL_COMMIT_RECEIPT.json']:
        p=R6/name; frozen[p.relative_to(ROOT).as_posix()]=sha(p)
    for name in ['data.npz','inputs/V40R3_LABEL_MATURITY_LEDGER.parquet']:
        p=R5/name; frozen[p.relative_to(ROOT).as_posix()]=sha(p)
    dump('PREREGISTRATION',{'working_name':'V40R6R1_RISK_CALIBRATED_ROLLING_GPUWORK','time_UTC':utc(),'base':BASE,
        'before_R6R1_candidate_outcomes':True,'service_level':.85,'alpha':.15,'term':'85% WORKLOAD-RESERVE SERVICE LEVEL',
        'grid_security_probability':False,'physical_electrical_feasibility_separate':True,'horizons':HORIZONS,
        'candidate_registry':CANDIDATES,'new_models_features_targets':False,
        'base_identity':'Exact saved R6 B1 and common-L0 B2 repaired Q90; Q50 diagnostics frozen',
        'residual':'log1p(actual)-log1p(max(frozen_base_Q90,0))',
        'calibration':{'policy':'FULL_EXPANDING_CAUSAL_HISTORY','initial_source':'DEVELOPMENT_OOS',
            'allowed_source_roles':['DEVELOPMENT','CALIBRATION','EXPOSED_EVALUATION'],'TRAIN_residuals':False,
            'availability':correction,'full_day_membership':True,'drop_old_residuals':False,'decay':False,'smoothing':False,
            'order_statistic':'k=min(max(ceil((n+1)*17/20),1),n); kth smallest residual; integer arithmetic',
            'interpolation':False,'delta':'max(0,q85_residual)','upper':'expm1(log1p(max(base_Q90,0))+delta)',
            'H4_min_days':20,'H4_min_rows':500,'H24_min_days':30,'insufficient':'No static fallback; candidate fails support gate',
            'per_issue_per_horizon_per_base':True},
        'role_scope':'Use exactly R6 mature DEV58/CAL26/EXPOSED88 days and their original saved arrays; preserve maturity exclusions',
        'CAL':'Full 26-day CAL prequential selection; R6 CAL_FIT/CAL_SELECT static procedure not reused',
        'gates':{'positive_coverage_band':[.85,.925],'mean_day_positive_coverage_min':.8,
            'supported_month_positive_coverage_min':.8,'supported_month_mean_day_coverage_min':.8,
            'day_min_positive_windows':1,'month_min_positive_days':5,'block_min_positive_days':5,
            'miss_severity':'under_GPUh strictly below own frozen raw base Q90',
            'over_anchor_A':'strictly below exact frozen R6 TRAIN per-horizon unconditional Q95 anchor on same evaluation rows',
            'over_anchor_B':'strictly below frozen R6 static U2-90 over on same rows','positive_upper_WAPE_strict_max':2.},
        'selection':{'scope':'CAL_ONLY','all_gates_required':True,'ranking':'minimum CAL over_GPUh',
            'tie':'If max(over)-min(over) <= .02*min(over), choose R85_B1; equality included',
            'no_pass':'NONE','joint_requires':['H4','H24'],'partial_success_not_promoted':True},
        'comparators_only':['R6_U0_STATIC_B1_Q90','R6_U1_STATIC_B2_Q90','R6_U2_STATIC_90_CALIBRATED'],
        'R6_BASE_SKILL_LIMITATION':'PRESENT','R6_raw_Q90_skill_gate_automatic_disqualification':False,
        'exposed':{'after_selection_freeze_commit':True,'same_prequential_rule':True,'earlier_exposed_may_enter_only_after_maturity':True,
            'no_reselection':True,'NONE':'Remains NONE; both preregistered candidates may be diagnostic-only',
            'gates':'Identical to CAL','TRUE_CONFIRMATORY_AVAILABLE':'NO'},
        'classification_precedence':['joint pass => 85PCT_GPUWORK_RESERVE_PREVALIDATED','all exposed candidates unsupported => CALIBRATION_SUPPORT_INSUFFICIENT',
            'H4 fails and H24 selected passes => H4_RESERVE_SAFETY_FAIL','H4 selected passes and selected H24 efficiency fails => H24_RESERVE_EFFICIENCY_FAIL',
            'otherwise => JOINT_GPUWORK_RESERVE_FAIL'],
        'miss_metrics':'positive shortfall amount per missed window; mean/P90/P95/max conditional on actual>upper; diagnostic percentiles linear',
        'overlap':'H4 rolling-window loss sums count overlapping atomic work repeatedly; calendar-day clusters required',
        'reproducibility':'Repeat the entire CAL+EXPOSED calibration exactly once after original exposed run; require exact deltas/uppers/membership/metrics; no better-repeat selection',
        'bootstrap':{'only_joint_exposed_pass':True,'draws':1000,'seed':SEED,'unit':'calendar day',
            'metrics':['under_GPUh','over_GPUh','positive_coverage'],'comparison':'selected rolling85 minus R6 static U2-90'},
        'interface':{'only_joint_success':True,'H4':'81-element arrays aligned to window starts 0..80','H24':'daily scalar',
            'proposal_only':True,'optimizer_use_allowed':False,'failure_recommended_rows':[]},
        'physical_semantics':'Arriving GPU-service work [GPUh]; not instantaneous GPU occupancy/count/IT/PCC power',
        'backlog_equation':'Future proposal only: B[t+1]=B[t]+A[t]-S[t], S[t]=0.25*r[t]; not implemented',
        'H1_H8':'Frozen R6 diagnostics only; not recalibrated or used in selection','15min':'Frozen SHAPE_ONLY; no new model or burst safety claim',
        'no_new_fit':{'LightGBM':0,'statistical_models':0,'classifiers':0,'feature_engineering':0,'target_construction':0},
        'firewall':{'optimizer_calls':0,'Gurobi_calls':0,'OpenDSS_calls':0,'Fresh_calls':0,'May_scientific_reads':0,'shadow_scientific_reads':0},
        'system_changes':False,'synthetic_jobs':False,'event_trigger':False,'local_repair':False,'rolling_MPC':False,
        'holds':HOLDS,'closure':{'mandatory':True,'NO_R6R2':True,'NO_R7':True,'no_new_calibration_family_or_service_level_search':True,
            'FURTHER_FUTURE_WORKLOAD_MODEL_WORK':'DEFER_UNTIL_NEW_DATA_OR_AUTHORITY'},'frozen_hashes':frozen})
    print('Preregistration ready; explicit user label-maturity clarification frozen; no candidate outcomes computed.',flush=True)

def receipt(stage):
    name='PREREGISTRATION' if stage=='pre' else 'SELECTION_FREEZE'
    commit=git('rev-parse','HEAD'); assert git('status','--porcelain')==''
    verify_commit_file(commit,OUT/('V40R6R1_'+name+'.json'))
    dump(name+'_COMMIT_RECEIPT',{'commit':commit,'SHA256':sha(OUT/('V40R6R1_'+name+'.json')),'time_UTC':utc(),'clean_commit_verified':True})

if __name__=='__main__': main() if len(sys.argv)==1 else receipt(sys.argv[1])
