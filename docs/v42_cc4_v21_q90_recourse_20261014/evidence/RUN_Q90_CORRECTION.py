"""Compile the existing May candidate ledger and replay the strict QoS route."""
from pathlib import Path
import sys,json,time,importlib.util,csv,gzip,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.q90_policy import compile_queue_aware_policy,FrozenQueueAwarePolicy
from v42_integration.actual import run_actual

OUT=ROOT/'audit/final'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def serial(v):
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    raise TypeError(type(v).__name__)
def run():
    freeze=read(ROOT/'audit/CONTROL_POLICY_SOURCE_SHA_MANIFEST.json')
    if not all(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in freeze['files']):
        raise ValueError('D_SOURCE_FREEZE_DRIFT_BEFORE')
    spec=importlib.util.spec_from_file_location('v42_integration._frozen_reference',ROOT/'audit/reference_source.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    source=module.load_conditional_source()
    nominal=read(ROOT/'audit/recourse/FROZEN_A2_NOMINAL_SERVICE.json')
    packet=read(ROOT/'audit/cc4_service/A2_SERVICE_TIMING_SOURCE_PACKET.json')
    print('PACKET_KEYS',list(packet),flush=True)
    # The literal timing array keys are deliberately asserted below rather
    # than inferred from an approximate kernel schedule.
    lower=packet['TRAIN_CDF_lower'];upper=packet['TRAIN_CDF_upper']
    authority=nominal['source_authority']
    bindings=dict(source['bindings'],science_sha=freeze['source_sha'])
    result=compile_queue_aware_policy(source['original_policy'],source['packet'],nominal,
        source['q90_hourly'],lower,upper,bindings=bindings,source_authority=authority)
    OUT.mkdir(parents=True,exist_ok=True)
    result['policy'].save(OUT/'Q90_QUEUE_AWARE_RECOURSE_POLICY.json')
    policy=FrozenQueueAwarePolicy.load(OUT/'Q90_QUEUE_AWARE_RECOURSE_POLICY.json',bindings=bindings)
    fields=list(result['funnel'][0])
    with (OUT/'CONTROL_POLICY_CANDIDATE_FUNNEL_BEFORE_AFTER.csv').open('w',encoding='utf8',newline='') as stream:
        w=csv.DictWriter(stream,fieldnames=fields);w.writeheader();w.writerows(result['funnel'])
    with gzip.open(OUT/'ALL_CANDIDATE_RECOURSE_ENDPOINTS.json.gz','wt',encoding='utf8') as stream:
        json.dump(result['evaluations'],stream,sort_keys=True)
    summary=dict(source_sha=freeze['source_sha'],before=result['before'],new_approved=result['new_approved'],
        q50_hard_pass=sum(r['q50_hard_pass'] for r in result['funnel']),
        recourse_evaluated=sum(r['q90_peak'] is not None for r in result['funnel']),
        timing_risk_candidates=sum(r['q90_queue_aware_status']=='PHYSICAL_PASS_TIMING_RISK' for r in result['funnel']),
        actions=result['approved_action_counts'],compile_metrics=policy.document['metrics'],
        source_only_QoS_unchanged=True,new_Job_or_GPU_or_forecast_created=False,
        Native_Optimize_calls=0,Fresh_AC='NOT_RUN',new_A_M_optimum=False)
    write(OUT/'Q90_HARD_GUARD_BEFORE_AFTER.json',summary)
    print('COMPILE',json.dumps(summary),flush=True)
    prepared,planning=source['fresh_actual_inputs']();arguments=prepared['arguments']
    arguments.update(arm='B3',known_schedule=source['known_commands'],frozen_policy=policy,expected_bindings=bindings)
    began=time.perf_counter();actual=run_actual(**arguments)
    with gzip.open(OUT/'SOURCE_ONLY_CORRECTED_ACTUAL_FULL96.json.gz','wt',encoding='utf8') as stream:
        json.dump(actual,stream,default=serial,sort_keys=True)
    np.savez_compressed(OUT/'SOURCE_ONLY_CORRECTED_ACTUAL_ARRAYS.npz',**{
        k:actual[k] for k in ('occupancy_GPU','compute_occupancy_GPU')},**{
        'physical_'+k:v for k,v in actual['physical'].items() if isinstance(v,np.ndarray)})
    receipt=dict(source_sha=freeze['source_sha'],policy_sha=policy.sha,slots=96,Full96_event_replay=True,
        execution_kind='SOURCE_ONLY_Q90_CORRECTION_FIXED_A2_M2_REFERENCE',wall_seconds=time.perf_counter()-began,
        Actual_receipt=actual['receipt'],rule_records=len(actual['rule_consumption_receipt']),
        new_A_M_optimization='NOT_RUN',Fresh_AC='NOT_RUN',Actual_Maximum_Line_Loading=None,
        Native_Optimize_calls=0,original_V5_Fresh_result_reissued=False)
    write(OUT/'ACTUAL_POLICY_LOOKUP_QUEUE_REPLAY.json',receipt)
    after=all(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in freeze['files'])
    write(OUT/'SOURCE_FREEZE_AFTER.json',dict(PASS=after,source_sha=freeze['source_sha']))
    if not after:raise ValueError('D_SOURCE_FREEZE_DRIFT_AFTER')
    print('ACTUAL',json.dumps(receipt),flush=True)
if __name__=='__main__':run()
