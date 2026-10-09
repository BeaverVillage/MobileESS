"""Independent zero-start initialization experiment; frozen Adaptive is not run."""
from pathlib import Path
from copy import deepcopy
import argparse
from .common import read,atomic,record,sha,digest,now,same_process
from .policy import VERSION,MANIFEST,source_files,MODEL_FIELDS

def prepare(root,*,code_commit,diagnostics=False,diagnostic_attempt=1,benchmark_attempt=1):
    if not isinstance(benchmark_attempt,int) or not 1<=benchmark_attempt<=99:raise ValueError('INVALID_BENCHMARK_ATTEMPT')
    campaign=Path(root).resolve();root=campaign/(f'feasibility_diagnostics_v19_{diagnostic_attempt:02d}' if diagnostics else f'initialization_benchmark_v19_{benchmark_attempt:02d}')
    if (root/MANIFEST).exists():raise PermissionError('BENCHMARK_NEVER_RESET_OR_OVERWRITTEN')
    previous=campaign/'initialization_benchmark_v18r2_01'
    previous_cp=read(previous/'CHECKPOINT_V18R2.json')
    previous_result=previous/'dates/B2/2025-05-03/attempts/seed_policy_v18r2_01/RESULT.json'
    if previous_cp.get('workers') or not previous_result.exists():
        raise PermissionError('PRIOR_BENCHMARK_MUST_FINISH_NATURALLY')
    old=read(campaign/'CONTINUATION_V18_MANIFEST.json');cp=read(campaign/'CHECKPOINT_V18.json')
    q=read(campaign/'QUARANTINE_V18_DATES.json')
    for history in q['dates'].values():
        if same_process(read(history['result']['path']).get('worker',{})):
            raise PermissionError('PREVIOUS_NATIVE_WORKER_STILL_ACTIVE')
    sources=source_files();root.mkdir(parents=True,exist_ok=True)
    doc=dict(schema=VERSION,run_id=old['run_id']+'_INITIALIZATION_BENCHMARK_V19',user_authorized=True,
        user_instruction='예산 0초부터 처음부터 초기해 찾을 때 까지 돌려봐야 ... 그런 뒤 성능을 봐야지',
        UTC=now(),source_commit=code_commit,previous_manifest=record(campaign/'CONTINUATION_V18_MANIFEST.json'),
        inherited_B1_results=old['inherited_B1_results'],builder_original_sources=old['builder_original_sources'],
        implementation=dict(version=old['implementation']['version'],sources=sources),
        execution_sources=sources,execution_SHA=digest(sources),seed_MIPGap=.03,seed_requested_seconds=300,
        native_budget_seconds=5400,target_gap=.03,Threads=1,P2_calls=0,prior_attempts={},
        input_folders={d:old['input_folders'][d] for d in ('2025-05-03','2025-05-04')},
        model_identity=old['model_identity'],canary_days=['2025-05-03','2025-05-04'],
        benchmark_initialization_only=True,benchmark_start_Native_Runtime=0.,
        campaign_root=str(campaign),campaign_runtime_reset=False,campaign_results_immutable=True,
        historical_bound_point_reuse=False,date_native_runtime_reset=False,
        preserved_quarantine=record(campaign/'QUARANTINE_V18_DATES.json'))
    doc['previous_initialization_benchmark']=record(previous_result)
    doc['initialization_native_limit_seconds']=120. if diagnostics else 1500.
    doc['diagnostics_only']=diagnostics
    doc['attempt_id']=f'seed_policy_v19_{benchmark_attempt:02d}'
    if diagnostics:
        doc['canary_days']=['2025-05-03']
        doc['input_folders']={'2025-05-03':old['input_folders']['2025-05-03']}
    atomic(root/MANIFEST,doc)
    from .policy import verify_manifest
    verify_manifest(root/MANIFEST)
    dates=deepcopy(cp['dates'])
    for row in dates.values():
        if row['arm']=='B2':
            row.update(status='CANARY_PENDING' if row['day'] in doc['canary_days'] else 'HELD_FOR_INITIALIZATION_BENCHMARK',current_attempt=None)
    dates['B2/2025-05-02']=deepcopy(previous_cp['dates']['B2/2025-05-02'])
    atomic(root/'CHECKPOINT_V19.json',dict(schema=VERSION,run_id=doc['run_id'],state='CANARY_READY',
        dates=dates,workers={},UTC=now(),benchmark_initialization_only=True))
    return root,doc

def run(request,budget,progress):
    import numpy as np
    from .m_stage import prepare as prepare_case
    
    from v42_may_campaign_native90.m_stage import _strict_ub
    from v42_m1_research.check_ub import vector_sha
    request=dict(request,_budget=budget)
    with budget.cost('model_preparation','ORIGINAL_FULL_MODEL_AND_NEW_INITIALIZATION'):
        case=prepare_case(request,progress)
    point=case.point
    if point is None:failure=read(case.output/'INITIALIZATION_FAILURE.json')
    first_full=budget.wall() if point is not None else None
    bypass=case.output/'SEED_BYPASS_CERTIFIED_DISPATCH.json'
    if bypass.exists():first_full=read(bypass)['first_FULL_verified_wall_seconds']
    if point is None:
        result=dict(PASS=False,status='NO_FULL_VALIDATED_INITIAL_POINT',failure=failure)
    else:
        packet=case.output/'BENCHMARK_FIRST_FULL_VALID_POINT.npz';np.savez_compressed(packet,point=point)
        with budget.cost('integer_physical_validation','BENCHMARK_INDEPENDENT_FULL_REPLAY'):
            strict=_strict_ub(case,packet,{})
        atomic(case.output/'BENCHMARK_FULL_CERTIFICATE.json',dict(strict,case_sha=case.case_sha))
        result=dict(PASS=True,status='INITIALIZATION_BENCHMARK_FULL_PASS',UB=strict['Global_UB'],exact_UB=strict['exact_Global_UB'],
            point_SHA=vector_sha(point),point_file=record(packet),FULL_certificate=record(case.output/'BENCHMARK_FULL_CERTIFICATE.json'))
    result.update(case_sha=case.case_sha,Native_Runtime=budget.used(),first_FULL_stage=read(bypass).get('first_initialization_stage') if bypass.exists() else None,initialization_native_limit_seconds=budget.native_limit,wall_seconds=budget.wall(),
        first_FULL_pass_wall_seconds=first_full,
        model_generation=read(case.output/'ORIGINAL_MODEL_BUILD_TIMING.json'),
        seed_MILP_calls=sum(c['track']=='F5' for c in budget.calls),
        seed_MILP_Runtime=sum(c['Native_Runtime'] for c in budget.calls if c['track']=='F5'),
        LP_Runtime=sum(c['Native_Runtime'] for c in budget.calls if c['component']=='FEASIBILITY_LP'),
        independently_validated_Global_LB=None,Global_Gap=None,Adaptive_entered=False,
        stop_policy='STOP_AFTER_FIRST_INDEPENDENT_FULL_VALID_INTEGER_POINT',benchmark_initialization_only=True,
        campaign_runtime_reset=False,original_model_identity=case.identity)
    if point is not None:
        from .dispatch import export
        export(case,point,strict)
    atomic(case.output/'INITIALIZATION_BENCHMARK_RESULT.json',result)
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('root');p.add_argument('--code-commit',required=True);p.add_argument('--diagnostics',action='store_true');p.add_argument('--diagnostic-attempt',type=int,default=1);p.add_argument('--benchmark-attempt',type=int,default=1)
    a=p.parse_args();root,doc=prepare(a.root,code_commit=a.code_commit,diagnostics=a.diagnostics,diagnostic_attempt=a.diagnostic_attempt,benchmark_attempt=a.benchmark_attempt);print(root);print(doc['execution_SHA'])
