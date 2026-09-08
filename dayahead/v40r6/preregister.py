from .common import *
import re
import sys
import platform
import lightgbm

def main():
    assert git('rev-parse','HEAD')==BASE and not (OUT/'fits').exists()
    assert read('HORIZON_DISTRIBUTION_AUDIT')['before_fit'] and read('EVALUATION_GATE_FEASIBILITY_AUDIT')['before_fit']
    request=Path('C:/Users/kjw39/.codex/attachments/208157d9-1a08-4c0c-a170-070665cf15ed/pasted-text.txt')
    body=request.read_text(encoding='utf-8')
    section=body.split('# B48. REQUIRED R6 ARTIFACTS')[1].split('# B49. MINIMUM TESTS')[0]
    names=re.findall(r'^V40R6_[A-Z0-9_]+\.(?:json|parquet|csv|md)$',section,re.M)
    dump('REQUIREMENTS_MANIFEST',{'request_SHA256':sha(request),'required_artifacts':names,'required_count':len(names),'minimum_tests':84})
    frozen={}
    for p in (ROOT/'dayahead/v40r6').glob('*.py'): frozen[p.relative_to(ROOT).as_posix()]=sha(p)
    for name in ['V40R6_CUMULATIVE_TARGET.parquet','V40R6_CUMULATIVE_TARGET_AUDIT.json','V40R6_CUMULATIVE_TARGET_IDENTITY_AUDIT.json',
        'V40R6_HORIZON_DISTRIBUTION_AUDIT.json','V40R6_ZERO_INFLATION_AUDIT.json','V40R6_EVALUATION_GATE_FEASIBILITY_AUDIT.json',
        'V40R6_TEMPORAL_SPLIT_CONTRACT.json','V40R6_CAL_SUBSPLIT_CONTRACT.json','V40R6_FEATURE_AUTHORITY_AUDIT.json',
        'V40R6_FEATURE_CONTRACT.json','V40R6_FEATURE_MATURITY_PROOF.parquet','features.npz','V40R6_R5_TARGET_AUTHORITY_FREEZE.json']:
        p=OUT/name; frozen[p.relative_to(ROOT).as_posix()]=sha(p)
    for name in ['data.npz','feature_availability.npz','seasonal_maturity_proof.parquet','V40R5_15MIN_TARGET_RECONSTRUCTION.parquet',
        'V40R5_TEMPORAL_SPLIT_CONTRACT.json','inputs/V40R3_LABEL_MATURITY_LEDGER.parquet','inputs/causal_dataset.npz','fits/B3/selected_q.npy']:
        p=R5/name; frozen[p.relative_to(ROOT).as_posix()]=sha(p)
    reg={'working_name':'V40R6_MULTI_HORIZON_CUMULATIVE_GPUWORK','base':BASE,'created_at_UTC':utc(),'before_any_R6_fit':True,
        'target':'Frozen native DeltaW15 sum; no target transform until training; no label clipping/smoothing/winsorization',
        'horizons':HORIZONS,'within_day':True,'primary':PRIMARY,'secondary':SECONDARY,'issue_time':'Exact R5 D-1 18:00 fixed AEST (UTC+10)',
        'split':'Exact R5 roles plus original stage maturity; CAL calendar first15/last14 with 15/11 eligible days',
        'feature_contract':read('FEATURE_CONTRACT'),'families':['B0','B1','B2'],
        'B0':{'central_only':True,'weekly_lags':[7,14,21,28],'fallback':['mature_TRAIN_same_window_median','mature_TRAIN_horizon_median','zero_no_history']},
        'B1':{'source':'TRAIN only AND target full-day available_at < issue_time','quantiles':[.5,.9],
            'hierarchy':['horizon_start_weekday','horizon_start','horizon','global_TRAIN_horizon'],
            'support_thresholds':[8,20,50,1],'quantile_method':'linear','global_fallback':'Still conditions on horizon; no duration mixing'},
        'B2':{'configs':CONFIGS,'quantiles':[.5,.9],'target_transform':'log1p','inverse':'expm1','negative_epsilon_tolerance':1e-10,
            'large_prediction_clipping':False,'CPU':True,'threads':1,'seed':SEED,'deterministic':True,'force_col_wise':True,
            'fit_scope':'TRAIN only; no refit with DEV/CAL','common_config_selection':'DEVELOPMENT only',
            'score':'Mean of eight per-H/quantile pinball means normalized by TRAIN mean GPUh of that horizon',
            'tie_break':['mean normalized Q90 pinball','mean Q50 MAE','L0 before L1 before L2'],
            'skill_gate':'Per horizon DEV Q50 MAE <= B1 and positive Q90 pinball <= B1; at least one strict improvement'},
        'crossing_repair':'Q90=max(raw Q90,raw Q50)',
        'calibration':{'name':'HORIZON_SPECIFIC_LOG_RESIDUAL_UPPER_CALIBRATION','scope':'CAL_FIT only',
            'delta':'max(0, quantile(log1p(y)-log1p(repaired Q90), .90, method=linear))',
            'upper':'expm1(log1p(repaired Q90)+delta_H)','one_delta_per_horizon':True,'guaranteed_conformal_validity':False},
        'candidates':{'U0':'B1 seasonal Q90','U1':'B2 repaired raw Q90','U2':'B2 calibrated U90'},
        'metrics':{'positive':'y>0; coverage/pinball/MAE/WAPE/under/over','overall_coverage':'DIAGNOSTIC_ONLY_NO_UPPER_GATE',
            'day_coverage':'Positive windows only, average equally over calendar days having >=1 positive window',
            'overlap':'Pooled window sums reuse atomic work and are not distinct GPUh totals; cluster reporting mandatory'},
        'gates':{'positive_coverage':[.9,.975],'mean_day_coverage_min':.88,'minimum_positive_days':5,
            'monthly_support_min_positive_days':5,'supported_month_mean_day_coverage_min':.88,
            'catastrophic_month':'Supported month positive pooled coverage <.80 OR mean day positive coverage <.80',
            'positive_upper_WAPE_strict_max':3.,'over_GPUh':'Strictly below TRAIN unconditional per-horizon Q95 anchor over_GPUh on same evaluated rows',
            'secondary':'Same gates; failure does not invalidate primary'},
        'selection':{'scope':'CAL_SELECT only','hierarchy':['U1','U2','U0','NONE'],'B2_requires_DEV_skill':True,'all_horizons_frozen':True},
        'exposed':{'only_after_selection_freeze_commit':True,'same_safety_efficiency_gates':True,
            'additional_under_GPUh':'B2 strictly lower than B1; selected B1 equals same B1 baseline',
            'no_reselection_recalibration_refit':True,'NONE':'Remains NONE; all three preregistered candidates reported as diagnostics',
            'TRUE_CONFIRMATORY_AVAILABLE':'NO','only_historical_diagnostic_evidence':True},
        'classification_precedence':['primary fail => SAFETY_FAIL','both primary select B1 and pass => SEASONAL_BASELINE_REMAINS_SELECTED',
            'all four selected pass => FULL_PREVALIDATED','only primary pass => PRIMARY_PREVALIDATED'],
        '15min_shape':{'source':'Frozen R5 DEV-selected full-target B3 selected_q.npy column Q50','purpose':'SHAPE_ONLY',
            'new_model_fit':False,'new_R6_family':False,'safety_claim':False},
        'bootstrap':{'only_if_primary_exposed_pass':True,'unit':'calendar day','draws':1000,'seed':SEED,'comparison':'selected minus B1'},
        'interface':{'only_if_primary_success':True,'rows':'Historical EXPOSED day, all horizons window_start_slot=0',
            'secondary_NONE_upper':None,'optimizer_use_allowed':False,'synthetic_jobs':False},
        'physical_semantics':'GPUh service-work mass; no instantaneous occupancy/count/IT/PCC power inference; future backlog equation proposal only',
        'reproducibility':'Independent same-seed final8 refit once before selection freeze; compare CAL and later EXPOSED outputs; no replicate selection',
        'optimizer_firewall':{'optimizer_calls':0,'Gurobi_calls':0,'OpenDSS_calls':0,'Fresh_calls':0},
        'May_firewall':{'scientific_reads':0,'Apr24_30_shadow_scientific_reads':0,'shadow':'SEALED','metadata':'NONZERO disclosed'},
        'system_sequence':'A0 -> M1 route+P/Q -> A1 feedback -> MF fixed-route P/Q -> Joint Freeze -> Fresh OpenDSS',
        'system_changes':False,'holds':HOLDS,'frozen_hashes':frozen,
        'runtime':{'Python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,'lightgbm':lightgbm.__version__}}
    dump('PREREGISTRATION',reg)
    print('Preregistration prepared; no fits exist; required artifacts:',len(names),flush=True)

def receipt(stage):
    name='PREREGISTRATION' if stage=='prereceipt' else 'SELECTION_FREEZE'
    commit=git('rev-parse','HEAD'); verify_commit_file(commit,OUT/('V40R6_'+name+'.json'))
    assert git('status','--porcelain')==''
    dump(name+'_COMMIT_RECEIPT',{'commit':commit,'artifact_SHA256':sha(OUT/('V40R6_'+name+'.json')),
        'time_UTC':utc(),'clean_commit_verified':True})

if __name__=='__main__':
    main() if len(sys.argv)==1 else receipt(sys.argv[1])
