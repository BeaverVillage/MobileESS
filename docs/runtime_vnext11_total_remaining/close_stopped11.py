"""Close the predeclared negative stop; no Stage-C model, final fit or April access."""
from common11 import *
from checkpoint11 import checkpoints
import numpy as np,pandas as pd,platform,importlib.metadata as md,subprocess,re
REASON='USER_SECTION42_STOP: classifier fails preregistered temporal discrimination (fold3 AUC0.49475 <0.55); Brier skill negative'
def main():
    total=read(ROOT/'TOTAL_SELECTION_RESULT.json');classifier=read(ROOT/'TAIL_CLASSIFIER_VERDICT.json');stage=read(ROOT/'STAGE_A_VERDICT.json')
    assert not classifier['meaningful'];assert not (ROOT/'REMAINING_SELECTION_RESULT.json').exists()
    write('STOP_CONDITION_RECEIPT.json',dict(time=now(),trigger=REASON,authority='USER_REQUEST.txt section42: tail classifier cannot meaningfully distinguish long jobs',
        interpretation='Temporal robustness is required: the preregistered minimum supported fold ROC-AUC0.55 fails, despite pooled AUC0.793. No claim that every fold lacks discrimination.',
        classifier=classifier,Stage_A='COMPLETE',Stage_B='COMPLETED_DIAGNOSTICS_STOPPED_NONVALIDATED',Stage_C='NOT_RUN',final_model_fit='NOT_RUN',provider='NOT_BUILT',April='NOT_EVALUATED',May='UNOPENED'))
    # Read-only checkpoint/identity audit does not train or score a remaining model.
    audits=[];splits=[]
    for i in range(1,6):
        train=window(i,total['window']);cal=data(i,'CAL');val=data(i,'VALID');sets={r:set(f.job_id) for r,f in [('TRAIN',train),('CAL',cal),('VALID',val)]}
        pairs={a+'_'+b:len(sets[a]&sets[b]) for a,b in [('TRAIN','VALID'),('TRAIN','CAL'),('CAL','VALID')]};assert sum(pairs.values())==0;splits.append(dict(fold=i,intersections=pairs))
        for role,f in [('TRAIN',train),('VALID',val)]:
            g,ix,e,y=checkpoints(f)
            audits.append(dict(fold=i,role=role,completed_episode_N=len(g),checkpoint_episode_N=int(np.unique(ix).size),checkpoint_N=len(ix),excluded_censored_N=int(f.censored.sum()),excluded_pending_N=int((~(f.event|f.censored)).sum()),post_completion_rows=0,minimum_remaining_seconds=float(y.min()),maximum_elapsed_seconds=int(e.max()),future_checkpoint_count_feature=False))
    write('CHECKPOINT_SAMPLE_AUDIT.json',dict(time=now(),status='GENERATOR_VALIDATED_ONLY_NO_REMAINING_TRAINING',checkpoint_seconds=1800,rows=audits,all_mature_surviving_checkpoints=True,remaining_model_trained=False))
    write('CHECKPOINT_SPLIT_AUDIT.json',dict(time=now(),status='EPISODE_ROLE_AUDIT_ONLY',folds=splits,CHECKPOINT_EPISODE_LEAKAGE=0,JOB_EPISODE_CROSS_SPLIT_LEAKAGE=0,scope='Disjoint episode IDs within each inherited fold, before expansion. Chronologically earlier VALID may enter a later expanding TRAIN after outcome availability.'))
    write('OOF_TOTAL_FEATURE_AUDIT.json',dict(time=now(),OOF_TOTAL_PREDICTION_LEAKAGE=0,TOTAL_PREDICTION_FEATURE_USED=False,remaining_model_trained=False,reason='Optional total prediction feature path excluded in preregistration; Stage C not run'))
    for name in ['REMAINING_MODEL_COMPARISON.csv','REMAINING_FOLD_METRICS.csv','REMAINING_ELAPSED_STRATA.csv','REMAINING_LONG_RUNNING_METRICS.csv','APRIL_EXPOSED_TOTAL_METRICS.csv','APRIL_EXPOSED_REMAINING_METRICS.csv','APRIL2_EXPOSED_QUEUE_REGRESSION.csv']:
        pd.DataFrame([dict(status='NOT_RUN_USER_STOP_CONDITION',reason=REASON,metrics_available=False)]).to_csv(ROOT/name,index=False)
    # Keep inherited forecast and causal stress outcomes in explicitly separate rows.
    old=pd.read_csv(V10/'PREAPRIL_QUEUE_REPLAY.csv');old=old[old.arm.isin(['W0','B0','V8','T0_V9','T3_LOGISTIC_STATIC'])].copy();old.arm=old.arm.replace({'T0_V9':'V9','T3_LOGISTIC_STATIC':'V10'})
    new=pd.read_csv(ROOT/'TOTAL_SELECTED_STAGE_QUEUE.csv');new=new[new.arm.eq(total['selected']['arm'])].copy();new.arm='V11_STOPPED_TOTAL'
    source=pd.concat([old,new],ignore_index=True);out=[]
    for r in source.to_dict('records'):
        for phase in ['FORECAST_RESERVATION','CAUSAL_CURRENT_SLOT_STRESS']:
            d=dict(fold=int(r['fold']),arm=r['arm'],phase=phase,N=int(r['N']),remaining_model_used=False,
                baseline_causality='RETROSPECTIVE_REFERENCE' if r['arm'] in ['B0','V8'] else 'FOLD_CAUSAL_TRACE_PROXY')
            if phase=='FORECAST_RESERVATION':d.update(start_lt_H=r['start_lt_H'],start_ge_H=r['start_ge_H'],reserved_GPUh=r['reserved_GPUh'],actual_GPUh=r['realized_GPUh'],queue_wait_seconds=r['mean_queue_wait_seconds'],capacity_violations=0,overrun_extensions=None,forecast_horizon_exhausted=r['forecast_horizon_exhausted'])
            else:d.update(start_lt_H=r['causal_start_lt_H'],start_ge_H=r['causal_start_ge_H'],reserved_GPUh=None,actual_GPUh=r['realized_GPUh'],queue_wait_seconds=r['causal_mean_queue_wait_seconds'],capacity_violations=r['capacity_violations'],overrun_extensions=r['overrun_extensions'],unresolved_at_horizon=r['causal_unresolved_at_horizon'])
            out.append(d)
    replay=pd.DataFrame(out);replay.to_csv(ROOT/'PREAPRIL_TOTAL_QUEUE_REPLAY.csv',index=False)
    replay[replay.phase.eq('CAUSAL_CURRENT_SLOT_STRESS')].to_csv(ROOT/'OVERRUN_DIAGNOSTIC.csv',index=False)
    # Causal total-model baseline comparison only; no post-stop new inference.
    baseline=pd.read_csv(V10/'PREAPRIL_REFERENCE_METRICS.csv');baseline.arm=baseline.arm.replace({'T0_V9':'V9'})
    v10=pd.read_csv(V10/'CALIBRATION_COMPARISON.csv');v10=v10[v10.arm.eq('T3_LOGISTIC_STATIC')].copy();v10.arm='V10'
    v11=pd.read_csv(ROOT/'TOTAL_GATING_COMPARISON.csv');v11=v11[v11.arm.eq(total['selected']['arm'])].copy();v11.arm='V11_STOPPED_TOTAL'
    pd.concat([baseline,v10,v11],ignore_index=True).to_csv(ROOT/'TOTAL_REFERENCE_COMPARISON.csv',index=False)
    timing=pd.read_csv(ROOT/'TOTAL_BASE_FOLD_METRICS.csv');timing['backend']='CPU4';timing['concurrent_independent_fits']=2;timing['scope']='BASE_Q50_Q90_PAIR_MEASURED';timing[['fold','arm','backend','concurrent_independent_fits','TRAIN_N','fit_seconds','scope']].to_csv(ROOT/'COMPUTE_BACKEND_BENCHMARK.csv',index=False)
    write('INFERENCE_LATENCY.json',dict(time=now(),status='NOT_MEASURED_PROVIDER_NOT_BUILT',reason=REASON,GPU_benchmarked=False,CPU4_primary_training=True))
    write('EXECUTION_ENVIRONMENT.json',dict(time=now(),python=sys.version,platform=platform.platform(),CPU=platform.processor(),backend='CPU4 per fit, two independent fits at most',
        versions={p:md.version(p) for p in ['numpy','pandas','scipy','scikit-learn','lightgbm','pyarrow']},GPU_tested=False))
    bundle=ROOT/'RUNTIME_PROVIDER';bundle.mkdir(exist_ok=True)
    (bundle/'README.md').write_text('# V11 provider 미생성\n\n사용자 요청서42절과 사전 classifier 구분력 기준을 따라 Stage B 뒤 중단했다. 이 디렉터리는 상태 설명만 담으며 predict_total/predict_remaining 구현이나 final model bytes를 제공하지 않는다. FOLD_MODELS는 과학 진단 산출물이고 배포 provider가 아니다. NEW_JOB_TOTAL_CALLABLE=FALSE, RUNNING_REMAINING_CALLABLE=FALSE. Stage C나 April 실행에는 새 명시적 연구 계획이 필요하다.\n',encoding='utf-8')
    def freeze(name,names,status,**kw):write(name,dict(time=now(),status=status,READY_FOR_APRIL=False,files=[record(ROOT/n) for n in names],**kw))
    freeze('TOTAL_MODEL_SELECTION_FREEZE.json',['TOTAL_SELECTION_RESULT.json','BASE_SELECTION_RESULT.json','EXPERIMENT_PROTOCOL.json','TOTAL_GATING_COMPARISON.csv','TOTAL_GATING_GATES.csv'],'STOPPED_DIAGNOSTIC_ONLY_NO_FINAL_FIT')
    freeze('TAIL_SPECIALIST_FREEZE.json',['TAIL_CLASSIFIER_VERDICT.json','TAIL_CLASSIFIER_METRICS.csv','TAIL_CLASSIFIER_CALIBRATION.csv','TAIL_EXPERT_METRICS.csv','TOTAL_SELECTION_RESULT.json'],'CLASSIFIER_NOT_VALIDATED_TAIL_NOT_USED')
    freeze('REMAINING_MODEL_SELECTION_FREEZE.json',['STOP_CONDITION_RECEIPT.json','CHECKPOINT_SAMPLE_AUDIT.json','CHECKPOINT_SPLIT_AUDIT.json','OOF_TOTAL_FEATURE_AUDIT.json'],'NOT_RUN_NO_REMAINING_MODEL',selected_model=None)
    freeze('FEATURE_CONTRACT_FREEZE.json',['FEATURE_CONTRACT.json','EXPERIMENT_PROTOCOL.json','model11.py'],'REGISTERED_CONTRACT_ONLY',STRICT_CAUSAL_FEATURE_COUNT=0)
    freeze('PROVIDER_BUNDLE_FREEZE.json',['RUNTIME_PROVIDER/README.md'],'NOT_BUILT',callable=False)
    fields={k:bool(v) for k,v in total['selected'].items() if k.endswith('_PASS')}
    write('FINAL_VERDICT.json',dict(time=now(),status='STOPPED_AT_STAGE_B_USER_SECTION42',STRICT_CAUSAL_FEATURE_COUNT=0,REQUEST_VERSION_AUTHORITY_FOUND=False,STRICT_CAUSAL_RUNTIME_PROVIDER_READY=False,
        TEMPORAL_DRIFT_FORENSIC_COMPLETE=True,FOLD4_PRIMARY_SHIFT_CLASS=stage['fold_classifications'][3]['primary'],TOTAL_TRAINING_WINDOW_SELECTED=total['window'],
        TOTAL_SELECTION_SCOPE='Diagnostic fold candidate only; no final provider fit',TOTAL_RUNTIME_MODEL_VALIDATED=False,TAIL_CLASSIFIER_VALIDATED=False,TAIL_EXPERT_USED=False,**fields,
        CHECKPOINT_EPISODE_LEAKAGE=0,OOF_TOTAL_PREDICTION_LEAKAGE=0,REMAINING_RUNTIME_MODEL_VALIDATED=False,REMAINING_Q90_GATE_PASS=False,REMAINING_TEMPORAL_STABILITY_PASS=False,
        REMAINING_EVALUATION_STATUS='NOT_RUN_STOP_CONDITION',OVERRUN_CONTRACT_PASS=False,OVERRUN_CONTRACT_STATUS='Inherited total-only stress checked; V11 total+remaining system not built',
        V42_RESEARCH_RUNTIME_PROVIDER_READY=False,APRIL_USED_FOR_SELECTION=False,APRIL_STATUS='EXPOSED_REGRESSION_ONLY',APRIL_EVALUATED=False,APRIL_MODEL_CHANGED_AFTER_EVALUATION=False,
        MAY_PAYLOAD_OPENED=False,MAY_USED_FOR_SELECTION=False,MAY_USED_FOR_EVALUATION=False,NEW_JOB_TOTAL_CALLABLE=False,RUNNING_REMAINING_CALLABLE=False,ONLINE_MODEL_REFIT_REQUIRED=False,
        ACTUAL_LONG_LABEL_USED_AT_INFERENCE=False,FUTURE_END_USED_BEFORE_FOLD_CUTOFF=0,stop_reason=REASON))
    print('STOPPED_NEGATIVE_DELIVERY_PREPARED',now(),flush=True)
if __name__=='__main__':main()
