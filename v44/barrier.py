"""Barrier-preserving numerical policy, explicitly requested by the user.

The failed/stalled original model is unchanged. May02 Joint retains Method=2
with homogeneous barrier and robust crossover basis construction. The previous
dual-simplex proposal is a separate diagnostic only, never this dispatcher.
"""
from contextlib import contextmanager, ExitStack
from functools import wraps
from pathlib import Path
from types import FunctionType, SimpleNamespace
import argparse
import subprocess
from unittest.mock import patch

from . import numeric,cap300
from .common import RUNTIME,read,record,verify,atomic,digest,now

POLICY='V44_B2_GAP3_MAY02_ROBUST_BARRIER_FRESH_M_V1'
PERMIT=RUNTIME/'v43_planning_svr12_actual_v1/BARRIER_GAP3_EXECUTION_PERMIT.json'
CAMPAIGN=RUNTIME/'v43_planning_svr12_actual_v1/campaign002'


def overlay():
    return dict(policy=POLICY,source=record(__file__),adapter_source=record(numeric.__file__),
        affected_day='2025-05-02',affected_stages=['M1'],affected_arm='B2',affected_solver='M_PR222_JOINT',
        May02_parameter_changes=dict(Method=2,BarHomogeneous=1,CrossoverBasis=1),
        all_B2_Joint_parameter_changes=dict(MIPGap=.03),
        unchanged_K48=True,unchanged_A_stages=True,unchanged_matrix_and_domain=True,
        unchanged_feasibility_tolerances=True,unchanged_FULL_validation=True,B3_inner_MIPGap_unchanged=.005,
        Root_algorithm='BARRIER',dual_simplex_production=False,
        K48_total=300.,Joint_total=900.,Joint_call_cap=300.,Threads=1,
        fresh_restart_days=['2025-05-01','2025-05-02'],fresh_M_build=True,
        prior_M_clocks_imported=False,prior_M_incumbents_imported=False,original_Raw_modified=False)


def validate(path=PERMIT):
    value=cap300.validate(path)
    if value.get('numerical_overlay')!=overlay() or value.get('numerical_policy_sha')!=digest(overlay()):
        raise PermissionError('EXACT_BARRIER_NUMERICAL_POLICY_REQUIRED')
    verify([value['numerical_overlay']['source'],value['numerical_overlay']['adapter_source']])
    return value


def make_permit():
    value=cap300.validate()
    value=dict(value,UTC=now(),numerical_overlay=overlay(),numerical_policy_sha=digest(overlay()),
        direct_numerical_instruction='병목 해결 후 5월 1일 2일 처음부터 재실행. Root Barrier 유지. B2 Joint MILP Gap 3%.',
        new_campaign=str(CAMPAIGN),original_campaign_preserved=True,new_K48_and_Joint_clocks_from_zero=True)
    if PERMIT.exists():raise FileExistsError('BARRIER_PERMIT_ALREADY_EXISTS')
    atomic(PERMIT,value);validate();return value


def parameters(original,day,stage,arm='B2'):
    value=dict(original)
    if arm=='B2' and stage=='M1':
        value['MIPGap']=.03
    if arm=='B2' and day=='2025-05-02' and stage=='M1':
        value.update(Method=2,BarHomogeneous=1,CrossoverBasis=1)
    return value


def routed(function,**overrides):
    result=FunctionType(function.__code__,dict(function.__globals__,**overrides),
        function.__name__,function.__defaults__,function.__closure__)
    result.__kwdefaults__=function.__kwdefaults__
    return result


@contextmanager
def install(path=PERMIT):
    permit=validate(path)
    from . import execution,worker
    from .frozen.v43_mess.library import load
    engine=load()['m_engine']
    with cap300.install(path):
        original_guard=execution.assert_current;original_stage=worker.m_stage
        def guard():
            value=original_guard();validate(path)
            if value['request'].get('numerical_policy_sha')!=permit['numerical_policy_sha']:
                raise PermissionError('BARRIER_WORKER_POLICY_REQUIRED')
            return value
        @wraps(original_stage)
        def stage(request,aidc):
            selected=parameters(engine.APPROVED_JOINT_PARAMETERS,request['day'],request['stage'],request['arm'])
            atomic(Path(request['case_root'])/(request['stage']+'.NUMERICAL_POLICY.json'),dict(
                UTC=now(),numerical_overlay=permit['numerical_overlay'],numerical_policy_sha=permit['numerical_policy_sha'],
                effective_Joint_parameters=selected,fresh_M_stage=not bool(request.get('resume_parent'))))
            with patch.object(engine,'APPROVED_JOINT_PARAMETERS',selected):return original_stage(request,aidc)
        with ExitStack() as stack:
            stack.enter_context(patch.object(execution,'assert_current',guard))
            stack.enter_context(patch.object(worker,'m_stage',stage))
            yield permit


def coordinator_run(root,path=PERMIT):
    def launch(command,**kwargs):
        command=list(command)
        index=command.index('-m')+1
        if command[index]!='v44.numeric':raise PermissionError('BARRIER_WORKER_ONLY')
        command[index]='v44.barrier'
        return subprocess.Popen(command,**kwargs)
    function=routed(numeric.coordinator_run,validate=validate,install=install,
        subprocess=SimpleNamespace(Popen=launch,CREATE_NO_WINDOW=getattr(subprocess,'CREATE_NO_WINDOW',0)))
    return function(root,path)


def benchmark(output,path=PERMIT,seconds=300.):
    return routed(numeric.benchmark,validate=validate,install=install,parameters=parameters)(output,path,seconds)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--permit',type=Path,default=PERMIT)
    parser.add_argument('--worker',type=Path)
    parser.add_argument('--execute',action='store_true')
    parser.add_argument('--benchmark',type=Path)
    parser.add_argument('--root',type=Path,default=CAMPAIGN)
    args=parser.parse_args()
    if args.worker:
        with install(args.permit):
            from .campaign import run_case
            run_case(read(args.worker))
    elif args.benchmark:benchmark(args.benchmark,args.permit)
    elif args.execute:coordinator_run(args.root,args.permit)
    else:raise PermissionError('EXPLICIT_BARRIER_EXECUTION_REQUIRED')


if __name__=='__main__':main()
