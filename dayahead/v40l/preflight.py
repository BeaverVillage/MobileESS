import numpy as np
import xgboost as xgb
from .common import *
from .protocol import SPLIT,REGISTRY,GATES,PARAMS,BUCKETS,THRESHOLDS
from .data import allowed_group,history,oof_authority

CONTRACTS=['V40L_TAIL_ESTIMAND_CONTRACT.json','V40L_TEMPORAL_SPLIT_CONTRACT.json','V40L_TAIL_CANDIDATE_REGISTRY.json','V40L_PREMAY_READ_FIREWALL.json']
def main():
    assert git('rev-parse','HEAD').decode().strip()==START
    OUT.mkdir(exist_ok=True)
    tracked=[p for p in git('ls-files','-z').decode().split('\0') if p and (ROOT/p).is_file()]
    stat={p:[(ROOT/p).stat().st_size,(ROOT/p).stat().st_mtime_ns] for p in tracked}
    protected={}
    for folder in [K,J,ROOT/'dayahead/v40k',ROOT/'dayahead/v40j']:
        for p in folder.rglob('*'):
            if p.is_file() and '__pycache__' not in str(p):protected[p.relative_to(ROOT).as_posix()]=sha(p)
    k0=verify_k0()
    write('V40L_START_STATE.json',{'HEAD':START,'created_at':now(),'initial_git_status':git('status','--porcelain').decode(),
      'protected_tracked_metadata':stat,'protected_V40J_V40K_SHA':protected,'V40K_receipt_SHA':sha(K/'V40K_FINAL_COMMIT_RECEIPT.json'),
      'V40K_classification':'V40K_POINT_MODEL_INSUFFICIENT','V40K_diagnostic':'CONDITIONAL_POINT_BIAS_REMAINS',
      'PF':.95,'Q_control':'NO','authority_missing':72,'electrical_generation':'HOLD','B0_B1_B2_B3':'NO','FULL_MAY':'NO'},immutable=True)
    with Firewall('preflight'):
        a=np.arange(32,dtype=float).reshape(16,2);y=np.arange(1,17,dtype=float)
        d=xgb.DMatrix(a,label=y,nthread=1)
        quant=xgb.train({**PARAMS,'objective':'reg:quantileerror','quantile_alpha':[.5,.9,.95]},d,num_boost_round=2)
        aft=xgb.DMatrix(a,nthread=1);aft.set_float_info('label_lower_bound',y);aft.set_float_info('label_upper_bound',np.r_[y[:-1],np.inf])
        m=xgb.train({**PARAMS,'objective':'survival:aft','aft_loss_distribution':'normal','aft_loss_distribution_scale':1.},aft,num_boost_round=2)
        assert np.isfinite(quant.predict(d)).all() and np.isfinite(m.predict(aft)).all()
        write('V40L_DEPENDENCY_REPORT.json',{'xgboost_version':xgb.__version__,'quantileerror_synthetic_probe':'PASS','survival_aft_synthetic_probe':'PASS','probe_data':'16 artificial rows; no scientific labels','CPU_only':True,'GPU_used':False,'package_installs':0,'main_python':str(XGB_PY),'hazard_existing_python':str(LGB_PY),
          'official_sources':['https://xgboost.readthedocs.io/en/release_3.2.0/parameter.html','https://xgboost.readthedocs.io/en/release_3.2.0/tutorials/aft_survival_analysis.html']})
        h=history();oof,authority=oof_authority(h);write('V40L_OOF_RESIDUAL_AUTHORITY.json',authority,immutable=True)
        write('V40L_K0_FREEZE_VERIFICATION.json',{'status':'PASS','source_final_commit':START,'verified_SHA':k0,'K0_refit':False,'K0_bias_offset':False,'K0_hyperparameter_change':False,'nominal_point':'frozen K0','V40K_winner_reinterpretation':False},immutable=True)
        meta=load(K/'V40K_APRIL_FOOTER_AVAILABILITY.json')
        write('V40L_METADATA_AVAILABILITY.json',{'source_footer_SHA':sha(K/'V40K_APRIL_FOOTER_AVAILABILITY.json'),'metadata_only':True,'new_raw_payload_opened':False,
          'eligible_groups':{s:[a['row_group'] for a in meta['row_groups'] if allowed_group(a,s)] for s in ['calibration','selection','shadow']},'shadow_complete_calendar_decodable':False},immutable=True)
        write('V40L_CENSORED_JOB_CENSUS.json',{'status':'CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE','censored_job_count':None,'GPU_count':None,'walltime_distribution':None,'hardware':None,'standby':None,'requested_GPU_hours':None,
          'not_zero':'Unknown, not zero. Static retrospective end timestamps cannot establish cutoff-time alive state without opening forbidden completion values. No causal status snapshot is in the registered authority.',
          'May_completion_values_read':0,'censored_training_rows':0,'general_quantile_missing_labels_imputed':False,'T5':'NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE'},immutable=True)
        write('V40L_T5_AFT_REPORT.json',{'status':'NOT_EVALUATED_CAUSAL_CENSOR_AUTHORITY_UNAVAILABLE','dependency_support':'PASS synthetic CPU probe','causal_censor_authority':'UNAVAILABLE','quantile_formula':REGISTRY['T5']['quantile_formula'],'May_completion_read':0,'scientific_fit':False},immutable=True)
        write('V40L_TAIL_ESTIMAND_CONTRACT.json',{'created_at':now(),'T_nom':'frozen K0','T90':'primary safe bound','T95':'extreme-risk diagnostic only','conditional_point_bias':'acknowledged, nominal not corrected','residual':'actual - blocked rolling OOF K0','positive_only':'permitted only in T7 conditional component with unconditional CDF reconstruction','features':FEATURES,'walltime_buckets_seconds':BUCKETS,'support_minimums':THRESHOLDS,'gates':GATES},immutable=True)
        write('V40L_TEMPORAL_SPLIT_CONTRACT.json',SPLIT,immutable=True)
        write('V40L_TAIL_CANDIDATE_REGISTRY.json',{'registry':REGISTRY,'XGBoost_parameters':PARAMS,'CPU_only':True,'K0_refit_prohibited':True,'architecture_changes_after_calibration_open':False,'family_addition_after_freeze':False},immutable=True)
        write('V40L_PREMAY_READ_FIREWALL.json',{'canonical_cutoff':CUTOFF,'May_runtime_status':0,'May_actual':0,'May_training':0,'May_calibration':0,'May_selection':0,
          'path_or_code_discovery':'NONZERO historical disclosures preserved; no total-read-zero claim','metadata_only':'Existing April footer includes post-cutoff bounds; separate metadata authority, not row values',
          'value_decoder':SPLIT['decoder'],'history_inputs':[str(J/'DEVELOPMENT_GPU_ROWS.parquet'),str(K/'RESIDUAL_OOF_ROWS.parquet')],
          'visible_development':'Previously opened April01-07; never called blind','writes_only':str(OUT),'shadow':'Winner freeze must be committed first'},immutable=True)
    print('PREREGISTRATION_READY',json.dumps({'OOF_rows':len(oof),'historical_GPU_rows':len(h),'K0_SHA':k0['models/K0_FINAL.pkl']}),flush=True)
if __name__=='__main__':main()
