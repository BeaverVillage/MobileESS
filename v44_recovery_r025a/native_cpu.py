"""Place single-thread A native calls on P cores; preserve build/M affinity."""
from contextlib import contextmanager, ExitStack
from contextvars import ContextVar
from functools import wraps
from pathlib import Path
from unittest.mock import patch
from .cpu_placement import actual_cpu_scope

_stage=ContextVar('R025A_SINGLE_THREAD_NATIVE_PLACEMENT',default=None)


def native_wrapper(function,method):
    @wraps(function)
    def run(model,*args,**kwargs):
        context=_stage.get()
        if context is None or int(model.Params.Threads)!=1:
            return function(model,*args,**kwargs)
        # Authority is established by the case/stage wrapper. The original
        # Native guard and accounting remain outside this exact call boundary.
        row=dict(stage=context['stage'],method=method,configured_Threads=1)
        try:
            with actual_cpu_scope() as placement:
                row['placement']=placement
                return function(model,*args,**kwargs)
        finally:
            context['calls'].append(row)
    return run


@contextmanager
def install():
    import gurobipy as gp
    from v44 import worker
    from v44.execution import assert_current
    from v44.common import read,atomic,now
    original=worker.a_stage
    @wraps(original)
    def a_stage(request,*args,**kwargs):
        case=assert_current()['request']
        if request['stage'] not in ('A1','A2') or any(request[k]!=case[k] for k in ('case_root','day','arm','source_sha')):
            raise PermissionError('R025A_NATIVE_CPU_CASE_STAGE_BINDING_REQUIRED')
        policy=read(request['execution_permit']['path'])['autonomous_recovery_overlay']
        if policy.get('single_thread_processor_placement')!='A1_A2_NATIVE1_AND_ALL_ARMS_ACTUAL_FRESH1_P_FIRST_E_ONLY_IF_P_UNAVAILABLE':
            raise PermissionError('R025A_NATIVE_CPU_EXPLICIT_POLICY_REQUIRED')
        context=dict(stage=request['stage'],calls=[])
        token=_stage.set(context)
        try:return original(request,*args,**kwargs)
        finally:
            _stage.reset(token)
            root=Path(request['root'])
            if root.exists():atomic(root/'R025A_NATIVE_CPU_PLACEMENT.json',dict(UTC=now(),**context,
                Native_Threads_changed=False,outer_stage_affinity_restored_after_each_call=True))
    with ExitStack() as stack:
        for name in ('optimize','presolve'):
            stack.enter_context(patch.object(gp.Model,name,native_wrapper(getattr(gp.Model,name),name)))
        stack.enter_context(patch.object(worker,'a_stage',a_stage))
        yield
