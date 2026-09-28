"""Audit frozen delivery and numerical records, with no fitting."""
from common8 import *
import ast,subprocess,re,pandas as pd,numpy as np

REQUIRED=['RUNTIME_TARGET_AUTHORITY_AUDIT.json','RAW_FEATURE_INVENTORY.csv','RESEARCH_TRACE_RUNTIME_FEATURE_CONTRACT.json','FEATURE_ENGINEERING_SPEC.md','FEATURE_SET_ABLATION.csv','MODEL_COMPARISON.csv','STRATIFIED_RUNTIME_METRICS.csv','LONG_JOB_METRICS.csv','GPU_WEIGHTED_METRICS.csv','CALIBRATION_COMPARISON.csv','PAIRED_UNCERTAINTY.csv','MODEL_SELECTION_FREEZE.json','FEATURE_CONTRACT_FREEZE.json','PROVIDER_BUNDLE_FREEZE.json','CHECKPOINT_SUBTRACTION_DIAGNOSTIC.csv','OVERRUN_DIAGNOSTIC.csv','APRIL_LOCKED_RUNTIME_METRICS.csv','APRIL_WALLTIME_VS_RUNTIME_QUEUE_REPLAY.csv','COMPUTE_BACKEND_BENCHMARK.csv','INFERENCE_LATENCY.json','SOURCE_MANIFEST.json','FINAL_REVIEW_KO.md','FINAL_VERDICT.json']
def main():
    checks={}
    def check(k,v):checks[k]=bool(v)
    for name in REQUIRED:check('required:'+name,(ROOT/name).is_file() and (ROOT/name).stat().st_size>0)
    sf=read(ROOT/'MODEL_SELECTION_FREEZE.json');ff=read(ROOT/'FEATURE_CONTRACT_FREEZE.json');pf=read(ROOT/'PROVIDER_BUNDLE_FREEZE.json');op=read(ROOT/'APRIL_OPEN_RECEIPT.json');v=read(ROOT/'FINAL_VERDICT.json')
    for r in pf['files']:check('provider_frozen:'+r['relative'],sha(ROOT/r['relative'])==r['sha256'])
    for r in ff['files']:check('features_frozen:'+Path(r['path']).name,sha(r['path'])==r['sha256'])
    for r in sf['source_code']:check('selection_code_frozen:'+Path(r['path']).name,sha(r['path'])==r['sha256'])
    check('all_three_freezes_before_April',max(sf['time'],ff['time'],pf['time'])<op['time'])
    check('April_open_receipt_hashes',all(sha(op[k]['path'])==op[k]['sha256'] for k in ['provider_freeze','feature_freeze','selection_freeze']))
    check('May_not_used',op['May_partition_reads']==0 and not v['MAY_USED_FOR_SELECTION'] and not v['APRIL_USED_FOR_SELECTION'])
    check('authority_still_false',v['STRICT_CAUSAL_FEATURE_COUNT']==0 and not v['REQUEST_VERSION_AUTHORITY_FOUND'] and not v['STRICT_CAUSAL_RUNTIME_PROVIDER_READY'])
    check('negative_result_not_promoted',not v['TRACE_DESCRIPTOR_RUNTIME_MODEL_VALIDATED'] and not v['V42_RESEARCH_RUNTIME_PROVIDER_READY'] and not v['TOTAL_RUNTIME_MODEL_SELECTED'])
    a=read(ROOT/'RUNTIME_TARGET_AUTHORITY_AUDIT.json');check('target_exact_execution_interval',a['TARGET_IS_EXECUTION_RUNTIME'] and a['normalized_equivalence_max_abs_seconds']==0 and not a['QUEUE_WAIT_INCLUDED_IN_TARGET'] and not a['REQUESTED_WALLTIME_USED_AS_LABEL'])
    f=pd.read_parquet(ROOT/'PREAPRIL_JOBS.parquet');p=read(ROOT/'EXPERIMENT_PROTOCOL.json');ds=roles(f)
    for role,g in ds.items():
        cutoff=p['TRAIN']['end_before'] if role=='TRAIN' else p[role]['mature_before']
        check('label_maturity:'+role,g.end_time.lt(pd.Timestamp(cutoff)).all() and (g.runtime_seconds>=0).all())
        check('membership:'+role,ids(g)==read(V6/'DATA_SPLIT_AND_MATURITY.json')['roles'][role]['mature_membership'])
    check('disjoint_chronological_membership',sum(len(g) for g in ds.values())==len(set().union(*(set(g.job_id) for g in ds.values()))))
    source=read(ROOT/'SOURCE_MANIFEST.json');failedsources=[]
    for r in source['target_sources']+source['baseline']['B0_model_files']+source['baseline']['Bconst_model_files']+source['queue_sources']+source['source_code']:
        if sha(r['path'])!=r['sha256']:failedsources.append(r['path'])
    check('source_bytes_unchanged',not failedsources)
    preserved=0
    for folder in [V6,V7]:
        manifest=read(folder/'DELIVERY_MANIFEST.json');check('preserve:'+folder.name,all(sha(folder/r['relative'])==r['sha256'] for r in manifest['files']));preserved+=len(manifest['files'])
    diff=subprocess.run(['git','diff',BASE,'--name-only'],cwd=REPO,capture_output=True,text=True,encoding='utf-8');check('changes_new_namespace_only',diff.returncode==0 and all(x.startswith('docs/runtime_vnext8_trace_feature_total/') for x in diff.stdout.splitlines()))
    check('no_new_model_bytes_after_April',all(datetime.datetime.fromtimestamp(x.stat().st_mtime,datetime.timezone.utc).isoformat()<op['time'] for folder in ['DEVELOPMENT_MODELS','ABLATION_MODELS','RUNTIME_PROVIDER/model'] for x in (ROOT/folder).rglob('*.txt')))
    columns=read(ROOT/'RUNTIME_PROVIDER/model/model.json')['columns'];forbidden={'runtime_seconds','start_time','end_time','queue_wait','job_id','id','submit_hour','submit_dow','state'}
    check('no_forbidden_model_features',not set(columns)&forbidden and len(columns)==29)
    for filename in ['provider.py','features8.py','model8.py']:
        tree=ast.parse((ROOT/'RUNTIME_PROVIDER'/filename).read_text(encoding='utf-8'))
        calls=[x.func.attr for x in ast.walk(tree) if isinstance(x,ast.Call) and isinstance(x.func,ast.Attribute)]
        check('no_inference_fit:'+filename,not {'fit','fit_transform','train','partial_fit'}.intersection(calls))
    check('callable_and_unknown_tests',read(ROOT/'NEW_JOB_CALLABLE_TEST.json')['PASS'] and read(ROOT/'NEW_JOB_CALLABLE_TEST.json')['exact_serialization_max_abs_seconds']==0)
    check('baseline_exact',read(ROOT/'BASELINE_REPRODUCTION.json')['PASS'] and read(ROOT/'BASELINE_REPRODUCTION.json')['B0_vNext6_preapril_max_absolute_error']==0)
    april=pd.read_parquet(ROOT/'APRIL_JOBS.parquet');check('locked_april_counts',len(april)==51499 and int(april.label_valid.sum())==49712)
    check('no_May_labels',april.end_time.dropna().lt(pd.Timestamp('2025-05-01T00Z')).all())
    m=pd.read_csv(ROOT/'APRIL_LOCKED_RUNTIME_METRICS.csv').set_index('model');g=april[april.label_valid];pred=pd.read_parquet(ROOT/'APRIL_PREDICTIONS.parquet').set_index('job_id').loc[g.job_id]
    calc=float((np.ceil(pred.V8_Q90.to_numpy()/900)*g.num_gpus_req.to_numpy()*.25).sum());check('rounded_reservation_exact',abs(calc-m.loc['V8','reservation_GPUh'])<1e-8)
    check('quantile_monotonic_finite',np.isfinite(pred[['V8_Q50','V8_Q90']]).all().all() and pred.V8_Q90.ge(pred.V8_Q50).all() and pred.V8_Q50.ge(0).all())
    check('job_specific_outputs',pred.V8_Q90.nunique()>10)
    q=read(ROOT/'APRIL_QUEUE_REPLAY_AUDIT.json');check('W0_replay_exact',q['W0_exact'] and q['reference_admitted']==2340 and q['summary'][0]['start_lt_H']==150)
    check('capacity_safe_restricted_stress',all(x['capacity_violations']==0 for x in q['causal_stress']))
    check('overrun_occupancy',read(ROOT/'OVERRUN_CONTRACT_TEST.json')['PASS'] and q['missing_truth_never_completed_by_prediction'])
    check('remaining_inconclusive_total_failed',v['REMAINING_RUNTIME_MODEL_RESEARCH_NEEDED']=='INCONCLUSIVE')
    c=pd.read_parquet(ROOT/'APRIL_RUNNING_CHECKPOINTS.parquet');check('all_checkpoints_alive',(c.actual_remaining_seconds>0).all() and c.elapsed_seconds.mod(1800).eq(0).all())
    check('30_questions',len(re.findall(r'^## \d+\.',(ROOT/'FINAL_REVIEW_KO.md').read_text(encoding='utf-8'),flags=re.M))==30)
    failures=[k for k,value in checks.items() if not value]
    result=dict(status='PASS' if not failures else 'FAIL',time=now(),checks=checks,failed=failures,prior_files_hashed=preserved,source_hash_failures=failedsources,
      task_validation='Delivery/scientific-integrity validation, NOT predictive PASS. Model gates remain failed.',device_attribution_limit='OpenCL device-name not logged during benchmark; inventory and static default-device interpretation only.')
    if not (ROOT/'VERIFICATION.json').exists():write('VERIFICATION.json',result)
    print(result['status'],len(checks),'checks',failures,flush=True)
    if failures:raise SystemExit(1)
if __name__=='__main__':main()
