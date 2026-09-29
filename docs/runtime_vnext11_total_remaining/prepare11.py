from common11 import *
import shutil
def main():
    ROOT.mkdir(exist_ok=True);LOCAL.mkdir(exist_ok=True)
    prior=[]
    for name in ['runtime_vnext6_callable_total','runtime_vnext7_feature_authority_recovery','runtime_vnext8_trace_feature_total','runtime_vnext9_distributional_runtime','runtime_vnext10_tail_calibrated_hazard']:
        folder=REPO/'docs'/name;m=read(folder/'DELIVERY_MANIFEST.json')
        for r in m['files']:assert sha(folder/r['relative'])==r['sha256']
        prior.append(dict(namespace=name,N=len(m['files']),manifest=record(folder/'DELIVERY_MANIFEST.json')))
    write('BASE_PRESERVATION_RECEIPT.json',dict(time=now(),base=BASE,prior=prior,April_read=False,May_read=False))
    shutil.copyfile('C:/Users/kjw39/.codex/attachments/86ab73e4-0a3e-4c38-aee9-660a4407783d/붙여넣은 텍스트.txt',ROOT/'USER_REQUEST.txt')
    for name in ['FEATURE_CONTRACT.json','TEMPORAL_FOLD_CONTRACT.json','TEMPORAL_FOLD_SUPPORT.csv','FOLD_MEMBERSHIP_REFERENCE.json','RUNTIME_TARGET_AUTHORITY_AUDIT.json','RIGHT_CENSORING_AUDIT.json']:shutil.copyfile(V10/name,ROOT/name)
    protocol=dict(time=now(),before_forensic=True,before_training=True,April_status='EXPOSED_REGRESSION_ONLY',May_allowed=False,
      stage_order=['A forensic complete before any new training','B15 base window/target cells','B selected base window/target: L1/L2 tail experts and fixed risk gates','C direct raw/log remaining, no-total-feature, no-elapsed ablation','final fit and six freezes','April once'],
      learner=dict(n_estimators=300,learning_rate=.05,num_leaves=31,max_depth=8,min_child_samples=200,reg_lambda=2,max_bin=127,random_state=4011,n_jobs=4,verbosity=-1,deterministic=True,force_col_wise=True),
      backend='CPU4 across all folds and final; no GPU trial needed, CPU inference1',
      total=dict(windows=WINDOWS,window_key='submit_time within latest D days before TRAIN cutoff; exact completion known before same cutoff',
        targets=['RAW','LOG','REL'],relative='log((T+1)/(requested_seconds+1)); V8 exact transform; missing walltime uses TRAIN-median walltime denominator',
        raw_features=RAW,engineered_count=29,mappings='fit only to each window TRAIN descriptor support; deterministic category sort; unknown0',
        support_min=dict(completed=5000,long4=200,long12=100),censoring='direct quantiles trained on exact completed labels only; report censored exclusions and maturity-selection limitation',
        selection='First select one of15 base models, then compare5 unique gated candidates on selected base. No exhaustive target/window/weight interactions. Eligibility first; if none, fewest failed gates then rank; diagnostic only.',
        ranking=['Q90_pinball','reservation_actual_GPUh','Q50_MAE','coverage_std'],
        tail=dict(classifier='binary T>14400, same CPU4 params/window',threshold=.5,smooth_alpha='raw predicted p_long4, alpha=p',weights={'L0':'1','L1':'2 if T>4h else1','L2':'4 if T>12h else2 if T>4h else1'},max_weight=4,
          gates=['GATE0 base only','GATE1 p>=.5 hard tail','GATE2 (1-p)*base+p*tail'],L3=False,
          classifier_meaningful=dict(ROC_AUC_min=.65,PR_AUC_prevalence_lift_min=1.5,min_supported_fold_AUC=.55),
          classifier_validation='meaningful discrimination plus pooled Brier skill>0 and recall_at_fixed_threshold>=.50; raw probability bins10, no probability recalibration'),
        order_repair='Q50=max(Q50,0);Q90=max(Q90,Q50,0); no walltime cap or global multiplier'),
      total_gates=dict(pooled_coverage=[.88,.92],min_fold=.85,pooled_long4=.85,min_fold_long4=.80,pooled_long12=.80,min_fold_long12=.70,support_N=100,reservation_to_W0_max=.80,
        queue_starts_relative_W0_min=.95,queue_capacity_violations=0,queue_horizon_exhaustion=0,queue_extensions_max='max(2*W0, W0+1000) per fold',future_outcome_leakage=0),
      remaining=dict(window='selected TOTAL window, no new window search',models=['R3_RAW','R4_LOG'],diagnostic_ablation='R3_NO_ELAPSED same TRAIN rows/window/params, not eligible',
        features='same29 + elapsed_seconds,elapsed_hours,log_elapsed,elapsed_walltime_ratio,walltime_minus_elapsed,checkpoint_index',
        total_prediction_features=False,OOF_TOTAL_PREDICTION_LEAKAGE=0,checkpoint_seconds=1800,checkpoint='start+1800*k strictly before observed completion; no postcompletion rows',
        train='completed labels known before TRAIN cutoff only; every checkpoint, unit row weight; censored remaining targets not fabricated',
        split='Episode identity assigned by inherited submit-time role before checkpoint expansion; disjoint within each fold. Earlier VALID can causally enter later expanding TRAIN after completion, not within-fold leakage.',
        selection='eligible first, then remaining Q90 pinball,Q50 MAE,fold std; if none, fewest failed gates then rank; raw/log only',
        gates=dict(pooled_coverage=[.88,.92],min_fold=.85,max_fold=.95,min_supported_elapsed_bin=.80,max_supported_elapsed_bin=.97,elapsed_support=1000,long_elapsed_gt12=.85,
          pinball_ratio_vs_total_minus_elapsed_max=1.,Q50_MAE_ratio_vs_total_minus_elapsed_max=1.05),
        classification='remaining Q90>threshold, as V9/V10; not a0.5 probability classifier',
        optional_R4=True),
      overrun='RUNNING retains GPU; recompute at each30min checkpoint/control extension; extend exactly900s when expired; STAY; never terminate',
      queue='V9 empty-background bounded preApril forecast ledger and separately labeled causal stress; remaining calls receive only request descriptors and observed elapsed, completion observer isolated',
      final_fit='same final V9 TRAIN cutoff2025-03-17T08Z, available2025-03-31T08Z; no CAL outcome adaptation, all frozen through April',
      forensic=dict(PSI='TRAIN decile edges, probabilities epsilon1e-6 only descriptive metric',KS=.1,JS_divergence=.1,total_variation=.1,label_tail_abs_change=.05,rare_category_train_count=100,
        conditional='exact raw descriptor cells with TRAIN>=50 VALID>=30; report common-support mass, weighted within-cell KS and prevalence changes; no proof solely from marginals',
        recency='Compare recent30d TRAIN label CDF distance to VALID vs expanding; descriptive only, model family/window set unchanged'))
    write('EXPERIMENT_PROTOCOL.json',protocol)
    write('PREREGISTRATION.json',dict(time=now(),files=[record(ROOT/n) for n in ['EXPERIMENT_PROTOCOL.json','FEATURE_CONTRACT.json','TEMPORAL_FOLD_CONTRACT.json','FOLD_MEMBERSHIP_REFERENCE.json']],April_read=False,May_read=False))
    (ROOT/'.gitignore').write_text('.local/\n__pycache__/\n',encoding='utf-8')
    (ROOT/'.gitattributes').write_text('* -text\nFOLD_MODELS/** linguist-generated=true\nRUNTIME_PROVIDER/models/** linguist-generated=true\n',encoding='utf-8')
    print('V11_PREREGISTERED',now(),sum(p['N'] for p in prior))
if __name__=='__main__':main()
