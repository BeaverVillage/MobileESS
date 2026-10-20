"""Actual stays sequential; independent Planning coefficient rows use 4 threads."""
from contextlib import contextmanager, ExitStack, nullcontext
from contextvars import copy_context
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from unittest.mock import patch
import inspect
import linecache
import textwrap
import threading

BUILD_THREADS=4
ACTUAL_THREADS=1


def coefficient_reader(function, telemetry):
    source=textwrap.dedent(inspect.getsource(function))
    old="return [bind_coefficient(c,arrays['current']['rating_a']) for c in coefficients]"
    if source.count(old)!=1:raise ValueError('R025A_COEFFICIENT_BUILD_BOUNDARY_DRIFT')
    source=source.replace(old,"return _r025a_bind_rows(bind_coefficient,coefficients,arrays['current']['rating_a'])")
    def bind_rows(bind, coefficients, ratings):
        # Warm the immutable authority on the owning thread. No worker may
        # compile or manipulate a native electrical context.
        from v42_thermal.authority import current_authority
        current_authority()
        def one(coefficient):
            telemetry.add(threading.get_ident())
            return bind(coefficient,ratings)
        with ThreadPoolExecutor(max_workers=BUILD_THREADS,thread_name_prefix='V44Model') as pool:
            futures=[pool.submit(copy_context().run,one,c) for c in coefficients]
            return [future.result() for future in futures]
    filename=__file__+'.coefficient.generated'
    linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    namespace=dict(function.__globals__,_r025a_bind_rows=bind_rows)
    exec(compile(source,filename,'exec'),namespace)
    return namespace[function.__name__]


@contextmanager
def numerical_threads(count):
    from threadpoolctl import threadpool_limits,threadpool_info
    with threadpool_limits(limits=count,user_api='blas'):
        info=threadpool_info()
        if any(row['num_threads']!=count for row in info if row['user_api']=='blas'):
            raise ValueError('R025A_NUMERICAL_THREAD_LIMIT_NOT_APPLIED')
        yield info


@contextmanager
def build_scope(telemetry):
    import v42_may01.prepare as original
    import v42_pr134_b1.native as dated
    import v42_temporal.native as temporal
    source=dated._coefficient_constructor or original.native_coefficients
    adapted=coefficient_reader(source,telemetry)
    with ExitStack() as stack:
        stack.enter_context(numerical_threads(BUILD_THREADS))
        stack.enter_context(patch.object(original,'native_coefficients',adapted))
        stack.enter_context(patch.object(temporal,'native_coefficients',adapted))
        stack.enter_context(patch.object(dated,'_coefficient_constructor',adapted))
        yield


@contextmanager
def install():
    from v44 import worker,campaign
    from v44.execution import assert_current
    from v44.common import read,atomic,now
    from pathlib import Path
    def wrapper(function, kind):
        @wraps(function)
        def run(request,*args,**kwargs):
            if request['arm'] not in ('B0','B1','B2','B3'):return function(request,*args,**kwargs)
            context=assert_current();case=context['request']
            if any(request[k]!=case[k] for k in ('case_root','day','arm','source_sha')):
                raise PermissionError('R025A_THREAD_POLICY_CASE_BINDING_REQUIRED')
            overlay=read(request['execution_permit']['path'])['autonomous_recovery_overlay']
            if overlay.get('Actual_numerical_threads')!=1 or overlay.get('model_build_threads')!=4:
                raise PermissionError('R025A_EXPLICIT_THREAD_POLICY_REQUIRED')
            if request['day']=='2025-05-01' and request['arm']=='B1' and Path(request['case_root']).name=='attempt002':
                raise PermissionError('USER_PROTECTED_MAY01_B1_MUST_REMAIN_UNCHANGED')
            ids=set();count=ACTUAL_THREADS if kind=='ACTUAL' else BUILD_THREADS
            scope=numerical_threads(count) if kind=='ACTUAL' else build_scope(ids)
            from .cpu_placement import compute_cpu_scope
            placement_scope=compute_cpu_scope(count,Path(request['output'])/'R025A_CPU_PLACEMENT.json')
            with scope,placement_scope as placement:
                try:return function(request,*args,**kwargs)
                finally:
                    output=Path(request['output'])
                    if output.exists():
                        from threadpoolctl import threadpool_info
                        atomic(output/'R025A_THREAD_POLICY.json',dict(UTC=now(),stage=request['stage'],
                            numerical_threads=count,native_TIME_contexts_parallelized=False,
                            coefficient_build_max_threads=4 if kind=='BUILD' else 0,
                            coefficient_worker_thread_ids=sorted(ids),libraries=threadpool_info(),
                            cpu_placement=placement,
                            model_addVars_addConstr_owning_thread_only=True,
                            Native_solver_Threads_changed=False))
        return run
    old_request=campaign.stage_request
    def stage_request(case,stage):
        request=old_request(case,stage)
        if case['arm'] in ('B0','B1','B2','B3'):
            if stage=='ACTUAL':request['Threads']=1
            request['Actual_numerical_threads']=1;request['model_build_threads']=4
        return request
    with ExitStack() as stack:
        stack.enter_context(patch.object(campaign,'stage_request',stage_request))
        for name,kind in [('actual','ACTUAL'),('a_stage','BUILD'),('m_stage','BUILD')]:
            stack.enter_context(patch.object(worker,name,wrapper(getattr(worker,name),kind)))
        yield
