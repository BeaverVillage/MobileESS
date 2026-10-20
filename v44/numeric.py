"""Explicit numerical overlay; same models, routes, tolerances and AC checks.

May02 M Joint uses dual simplex to avoid the measured barrier/crossover stall.
K48, A stages, May01 and the remaining days retain their original parameters.
Fresh campaign attempts rebuild M and start both clocks at zero; no old bound
or incumbent is imported. The frozen scientific source stays byte-identical.
"""
from contextlib import contextmanager, ExitStack
from functools import wraps
from pathlib import Path
from types import FunctionType, SimpleNamespace
from unittest.mock import patch
import argparse
import subprocess

from . import cap300
from .common import RUNTIME, read, record, verify, atomic, digest, now

POLICY = 'V44_MAY02_JOINT_DUAL_SIMPLEX_FRESH_M_V1'
PERMIT = RUNTIME/'v43_planning_svr12_actual_v1/NUMERIC_EXECUTION_PERMIT002.json'
CAMPAIGN = RUNTIME/'v43_planning_svr12_actual_v1/campaign002'


def overlay():
    return dict(policy=POLICY, source=record(__file__),
        affected_day='2025-05-02', affected_stages=['M1', 'M2'],
        affected_solver='M_PR222_JOINT', parameter_changes={'Method': 1},
        unchanged_K48=True, unchanged_A_stages=True, unchanged_matrix_and_domain=True,
        unchanged_tolerances=True, unchanged_FULL_validation=True,
        K48_total=300., Joint_total=900., Joint_call_cap=300., Threads=1,
        fresh_restart_days=['2025-05-01', '2025-05-02'],
        fresh_M_build=True, prior_M_clocks_imported=False,
        prior_M_incumbents_imported=False, original_Raw_modified=False)


def validate(path=PERMIT):
    value=cap300.validate(path)
    if value.get('numerical_overlay') != overlay() or value.get('numerical_policy_sha') != digest(overlay()):
        raise PermissionError('EXACT_NUMERICAL_POLICY_REQUIRED')
    verify([value['numerical_overlay']['source']])
    return value


def make_permit():
    value=cap300.validate()
    value=dict(value, UTC=now(), numerical_overlay=overlay(), numerical_policy_sha=digest(overlay()),
        direct_numerical_instruction='5월 2일 병목 해결 후 5월 1일 2일 둘 다 처음부터 다시 실행',
        new_campaign=str(CAMPAIGN), original_campaign_preserved=True,
        new_K48_and_Joint_clocks_from_zero=True)
    if PERMIT.exists():
        raise FileExistsError('NUMERICAL_PERMIT_ALREADY_EXISTS')
    atomic(PERMIT,value)
    validate()
    return value


def parameters(original, day, stage):
    value=dict(original)
    if day == '2025-05-02' and stage in ('M1','M2'):
        value['Method']=1
    return value


@contextmanager
def install(path=PERMIT):
    permit=validate(path)
    from . import execution, worker
    from .frozen.v43_mess.library import load
    engine=load()['m_engine']
    with cap300.install(path):
        original_guard=execution.assert_current
        original_stage=worker.m_stage
        def guard():
            value=original_guard()
            validate(path)
            if value['request'].get('numerical_policy_sha') != permit['numerical_policy_sha']:
                raise PermissionError('NUMERICAL_WORKER_POLICY_REQUIRED')
            return value
        @wraps(original_stage)
        def stage(request, aidc):
            selected=parameters(engine.APPROVED_JOINT_PARAMETERS, request['day'], request['stage'])
            atomic(Path(request['case_root'])/(request['stage']+'.NUMERICAL_POLICY.json'),dict(
                UTC=now(), numerical_overlay=permit['numerical_overlay'],
                numerical_policy_sha=permit['numerical_policy_sha'], effective_Joint_parameters=selected,
                fresh_M_stage=not bool(request.get('resume_parent'))))
            with patch.object(engine,'APPROVED_JOINT_PARAMETERS',selected):
                return original_stage(request,aidc)
        with ExitStack() as stack:
            stack.enter_context(patch.object(execution,'assert_current',guard))
            stack.enter_context(patch.object(worker,'m_stage',stage))
            yield permit


def coordinator_run(root, path=PERMIT):
    from . import campaign
    permit=validate(path)
    original_atomic=campaign.atomic
    def write(path,value):
        if Path(path).parent.name == 'requests' and isinstance(value,dict) and 'case_root' in value:
            value=dict(value,execution_policy_sha=permit['execution_policy_sha'],
                operational_overlay=permit['operational_overlay'], Joint_call_cap_seconds=300.,
                numerical_overlay=permit['numerical_overlay'], numerical_policy_sha=permit['numerical_policy_sha'])
        original_atomic(path,value)
    def launch(command,**kwargs):
        command=list(command)
        if '-m' not in command or command[command.index('-m')+1] != 'v44.campaign':
            raise PermissionError('NUMERICAL_ONLY_ORIGINAL_CAMPAIGN_WORKER')
        command[command.index('-m')+1]='v44.numeric'
        command+=['--permit',str(path)]
        return subprocess.Popen(command,**kwargs)
    fn=campaign.run
    ns=dict(fn.__globals__,atomic=write,subprocess=SimpleNamespace(Popen=launch,
        CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    run=FunctionType(fn.__code__,ns,fn.__name__,fn.__defaults__,fn.__closure__)
    run.__kwdefaults__=fn.__kwdefaults__
    with install(path):
        return run(root,path,resume=False)


def benchmark(output, path=PERMIT, seconds=150.):
    """One explicit pre-campaign May02 solve of the identical saved first pool."""
    from .locks import coordinator,worker_slot,process_identity
    from .execution import case_scope,native_stage
    from .planning import scope as planning_scope
    from .daily import load_aidc
    from .frozen.v43_mess.library import load
    from .frozen.v43_mess.performance import install as caches
    from .budget import StageBudget
    root=Path(output)
    root.mkdir(parents=True,exist_ok=False)
    permit=validate(path)
    old=RUNTIME/'v43_planning_svr12_actual_v1/campaign001'
    parent=old/'2025-05-02/B2/attempt001/M1'
    request=read(parent/'request.json')
    request['scientific_case_root']=read(parent/'BINARY_STAGE_CHECKPOINT.json')['key']['case_root']
    request.update(case_root=str(root/'case'),campaign_root=str(root),root=str(root/'M1'),
        output=str(root/'M1'),execution_permit=record(path),
        execution_policy_sha=permit['execution_policy_sha'],numerical_policy_sha=permit['numerical_policy_sha'])
    out=Path(request['output']);out.mkdir()
    atomic(root/'PHASE.json',dict(lane='B2',UTC=now()))
    with coordinator(root) as lease:
        request['lease']=lease
        who=dict(**process_identity(),day=request['day'],arm='B2',worker_slot=request['worker_slot'])
        with worker_slot(request['day'],'B2',request['worker_slot'],root=root,lease=lease),case_scope(request,lease,who),install(path),native_stage(request),planning_scope(request['day']):
            modules=load();m=modules['m_engine']
            aidc,_=load_aidc(old/'references/2025-05-02','2025-05-02')
            from .m_restore import restore
            case=restore(parent,out,request,aidc,modules)
            caches(case,modules)
            source_pool=old/'2025-05-02/B2/attempt003/M1/COMMON_M_PR222/ITERATION_0001/POOL.json'
            pools=read(source_pool)['pools']
            packet=m.direct_joint(case,None,pools)
            atomic(out/'EXACT_INTEGER_AND_ROW_EQUIVALENCE.json',packet[-1])
            parent_budget=StageBudget(out/'JOINT_NATIVE_LEDGER.json',case=case,kind='PLANNING_NATIVE',
                progress=lambda v:atomic(out/'progress.json',dict(v,UTC=now())))
            adapter=m._BudgetAdapter(parent_budget,limit=seconds)
            chosen=parameters(m.APPROVED_JOINT_PARAMETERS,'2025-05-02','M1')
            with patch.object(m,'APPROVED_JOINT_PARAMETERS',chosen):
                result,captures=m._native_joint(case,adapter,packet,out/'JOINT',seconds)
            validated=[]
            # Use the engine's exact original validator, identical to production.
            for i,capture in enumerate(captures):
                certificate=m._validate(case,capture['point'],out/f'CAPTURE_{i:03d}.npz',m.strict_full)
                if certificate is not None:validated.append(certificate)
            result.update(UTC=now(),numerical_policy_sha=permit['numerical_policy_sha'],
                old_pool=record(source_pool),Native_calls=len(parent_budget.calls),
                same_original_case_sha=case.case_sha,parameters=chosen,FULL_verified_count=len(validated),
                FULL_certificates=validated,prior_incumbents_imported=False,
                production_K48_calls=0,pre_campaign_diagnostic=True)
            atomic(root/'RESULT.json',result)
            return result


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--permit',type=Path,default=PERMIT)
    p.add_argument('--worker',type=Path)
    p.add_argument('--execute',action='store_true')
    p.add_argument('--benchmark',type=Path)
    p.add_argument('--root',type=Path,default=CAMPAIGN)
    a=p.parse_args()
    if a.worker:
        with install(a.permit):
            from .campaign import run_case
            run_case(read(a.worker))
    elif a.benchmark:
        benchmark(a.benchmark,a.permit)
    elif a.execute:
        coordinator_run(a.root,a.permit)
    else:
        raise PermissionError('EXPLICIT_NUMERICAL_EXECUTION_REQUIRED')


if __name__ == '__main__':
    main()
