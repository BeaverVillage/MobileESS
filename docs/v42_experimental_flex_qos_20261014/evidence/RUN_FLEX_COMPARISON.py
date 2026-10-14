"""Execute independent fixed-anchor Full96 research counterfactuals, Native0."""
from pathlib import Path
import sys,json,hashlib,gzip,time,itertools,gc
import numpy as np
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from v42_integration.a_engine import digest
from v42_integration.experimental_replay import load_conditional_source
from v42_integration.experimental_actual import run_conditional_case
from v42_integration.experimental_qos import ExperimentalQoSProvider
from v42_integration.experimental_policy import ExperimentalControlPolicy,load_experimental_migration_authority
OUT=ROOT/'audit/control/FINAL_FLEX_COMPARISON'
def read(p):return json.loads(Path(p).read_text(encoding='utf8'))
def write(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def serial(v):
    if isinstance(v,np.ndarray):return v.tolist()
    if isinstance(v,np.generic):return v.item()
    raise TypeError(type(v).__name__)
def source_ok(f):return all(hashlib.sha256((ROOT/r['path']).read_bytes()).hexdigest()==r['sha256'] for r in f['files'])
def retrospective_service_audit(source,result):
    # Read private realization only after the experiment has finished. This
    # audit is never fed back to a controller, selector or participation rule.
    prepared,_=source['fresh_actual_inputs']();arguments=prepared['arguments']
    begin=arguments['begin'];env=arguments['environment']
    running={r.uid:r for r,_,_ in arguments['running']}
    requests={r.uid:r for r in arguments['requests']};requests.update(running)
    true_remaining={uid:(env.running_completion(uid)-begin if uid in running else env.started(uid,begin)-begin)
        for uid in requests}
    private=result['carryout']['simulator_only_remaining_compute_seconds']
    terminal=sum(requests[uid].gpu*private.get(uid,true_remaining[uid])/3600 for uid in requests)
    initial=sum(requests[uid].gpu*seconds/3600 for uid,seconds in true_remaining.items())
    served=result['receipt']['actual_compute_GPUh'];error=abs(initial-served-terminal)
    return dict(scope='POST_EXECUTION_PRIVATE_SIMULATOR_AUDIT_NEVER_CONTROLLER_INPUT',jobs=len(requests),
        initial_realized_remaining_GPUh=initial,within_day_compute_GPUh=served,terminal_remaining_GPUh=terminal,
        mass_error_GPUh=error,PASS=error<=1e-6,controller_private_reads=result['receipt']['future_duration_controller_reads']+
            result['receipt']['future_completion_controller_reads'])
def frozen_program(source,case,science_sha):
    prepared,_=source['fresh_actual_inputs']();strict=prepared['arguments']['qos_window_provider']
    provider=ExperimentalQoSProvider(strict,scenario=case['scenario'],participation=case['participation'],
        case_sha=case['case_sha'],provider_sha=strict.provider_sha)
    bindings=dict(source['bindings'],case_sha=case['case_sha'],qos_sha=provider.stats.sha,science_sha=science_sha)
    selector=ExperimentalControlPolicy(source['packet'],bindings,qos_provider=provider,
        q50_hourly=source['q50_hourly'],q90_hourly=source['q90_hourly'],kernel=source['kernel'],
        queue_authority=source['queue_authority'],frozen_anonymous_gpu=source['frozen_anonymous_gpu'],
        algorithm=case['algorithm'],nominal_service=source['nominal_service'],
        train_cdf_lower=source['train_cdf_lower'],train_cdf_upper=source['train_cdf_upper'],
        recourse_source_authority=source['recourse_source_authority'],migration_authority=load_experimental_migration_authority())
    return selector.document
def run(only=None):
    freeze=read(ROOT/'audit/SOURCE_FREEZE_C.json');assert source_ok(freeze),'C_SOURCE_DRIFT_BEFORE_EXECUTION'
    seed=read(ROOT/'audit/PREREGISTRATION.json')['seed']
    source=load_conditional_source()
    input_identity=dict(original_planning_case_sha=source['planning_freeze']['case_sha'],
        original_A2_aidc_anchor=source['aidc']['aidc_anchor'],original_MESS_plan_sha=source['mess']['plan_sha'],
        nominal_service_sha=source['nominal_service']['nominal_service_sha'],
        raw_source_receipts_sha=digest(source['source_receipts']))
    cells=list(itertools.product(('E1','E2'),('FLEX20','FLEX30','FLEX40'),('FIXED','GREEDY','GRID_SENSITIVITY_AWARE')))
    main=('E1','FLEX30','GRID_SENSITIVITY_AWARE');cells.remove(main);cells.insert(0,main)
    cases=[dict(scenario=e,participation=f,algorithm=a,case_sha=digest(dict(science=freeze['science_version'],
        source_sha=freeze['source_sha'],contract=e,participation=f,algorithm=a,seed=seed,
        original_input_identity=input_identity,
        frozen_A2_M2='V5_FIXED_NUMERICAL_REFERENCE_NOT_NEW_OPTIMUM',Q90_recourse_commit='97da5c097f0eefc30a057c51378676c6402138c8'))) for e,f,a in cells]
    manifest=dict(science_version=freeze['science_version'],source_sha=freeze['source_sha'],seed=seed,cases=cases,
        original_input_identity=input_identity,execution_driver_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        source_frozen_before_new_case_performance=True,preregistered_seed_unchanged=True,
        Native_Optimize_calls=0,Fresh_AC='NOT_RUN',Actual_Maximum_Line_Loading=None)
    manifest_path=OUT/'CASE_MANIFEST.json'
    if manifest_path.is_file():assert read(manifest_path)==manifest,'CASE_MANIFEST_REBIND_FORBIDDEN'
    else:write(manifest_path,manifest)
    if only=='MANIFEST_ONLY':print('MANIFEST_READY '+freeze['source_sha'],flush=True);return
    shard=None
    if only and only.startswith('SHARD_'):
        parts=only.split('_');shard=(int(parts[1]),int(parts[3]));only=None
    for index,case in enumerate(cases):
        if shard and index%shard[1]!=shard[0]:continue
        name='_'.join(case[k] for k in ('scenario','participation','algorithm'))
        if only and name!=only:continue
        folder=OUT/name;receipt=folder/'EXECUTION_RECEIPT.json'
        if receipt.is_file():
            old=read(receipt);assert old['case_sha']==case['case_sha'] and old['source_freeze_sha']==freeze['source_sha']
            print('REUSE '+name,flush=True);continue
        began=time.perf_counter()
        doc=frozen_program(source,case,freeze['source_sha'])
        compile_wall=time.perf_counter()-began
        folder.mkdir(parents=True,exist_ok=True)
        write(folder/'FROZEN_CONDITIONAL_POLICY_PROGRAM.json',doc)
        print('BEGIN '+name+' '+case['case_sha'],flush=True)
        result=run_conditional_case(source,**case,source_freeze_sha=freeze['source_sha'],end_slots=96)
        assert doc['policy_sha']==result['conditional_case']['policy_sha'],'FROZEN_EXECUTED_PROGRAM_SHA_MISMATCH'
        service_audit=retrospective_service_audit(source,result)
        assert service_audit['PASS'],'REALIZED_SERVICE_MASS_FAILURE'
        folder.mkdir(parents=True,exist_ok=True)
        # Stream serialization without retaining a second huge text document.
        with gzip.open(folder/'CONDITIONAL_ACTUAL_RESULT.json.gz','wt',encoding='utf8') as stream:
            json.dump(result,stream,default=serial,sort_keys=True,ensure_ascii=False)
        arrays={k:result[k] for k in ('occupancy_GPU','compute_occupancy_GPU')}
        arrays.update({'physical_'+k:v for k,v in result['physical'].items() if isinstance(v,np.ndarray)})
        np.savez_compressed(folder/'ACTUAL_PHYSICAL_ARRAYS.npz',**arrays)
        receipt_value=dict(result['conditional_case'],actual_receipt=result['receipt'],writer_inclusive_wall_seconds=time.perf_counter()-began,
            frozen_program_compile_wall_seconds=compile_wall,retrospective_service_audit=service_audit,source_bytes_PASS_after=source_ok(freeze),
            result_sha256=hashlib.sha256((folder/'CONDITIONAL_ACTUAL_RESULT.json.gz').read_bytes()).hexdigest())
        write(receipt,receipt_value);assert receipt_value['source_bytes_PASS_after'],'C_SOURCE_DRIFT_AFTER_EXECUTION'
        print('DONE '+name+' '+json.dumps(receipt_value,default=serial),flush=True)
        del result;gc.collect()
    write(OUT/'EXECUTION_SCOPE.json',dict(source_sha=freeze['source_sha'],expected_unique_E1_E2_cases=18,
        completed_cases=[p.parent.name for p in OUT.glob('*/EXECUTION_RECEIPT.json')],Native_calls=0,AC_calls=0,
        B2_B3_HOLD=True,May31_HOLD=True))
if __name__=='__main__':run(sys.argv[1] if len(sys.argv)>1 else None)
