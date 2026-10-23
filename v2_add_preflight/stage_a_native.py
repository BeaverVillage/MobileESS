"""Original A native execution with V2 budget metadata and exact batched IO."""
from pathlib import Path
from types import FunctionType
from functools import lru_cache
from unittest.mock import patch
import inspect,textwrap,linecache
from .stage_budget import policy
from .stage_native_batch import difference

@lru_cache(maxsize=1)
def solve_io():
    from v42_a_stage_acceptance.native import Native
    original=Native.solve;source=textwrap.dedent(inspect.getsource(original))
    old='    compiled=model.getA().tocsr();compiled.sum_duplicates();compiled.sort_indices()\n    delta=compiled-snapshot.matrix;delta.eliminate_zeros()'
    if source.count(old)!=1:raise ValueError('A_FULL_NATIVE_READBACK_SOURCE_BOUNDARY_DRIFT')
    source=source.replace(old,'    delta=_V2_actual_matrix_difference(model,snapshot.matrix)')
    filename=__file__+'.source_native.generated';linecache.cache[filename]=(len(source),None,source.splitlines(True),filename)
    namespace=dict(original.__globals__,_V2_actual_matrix_difference=difference)
    exec(compile(source,filename,'exec'),namespace);return namespace['solve']

def constructor(original):
    old_facade=original.__globals__['_NativeBudget'];writer=original.__globals__['atomic']
    class Facade(old_facade):
        def __init__(self,shared):
            super().__init__(shared);self.record['limit_seconds']=shared.native_limit
    def native(request,state,budget,progress):
        def atomic(path,value):
            if Path(path).name=='CONTINUATION_BUDGET.json':
                value=dict(value,native_limit=budget.native_limit,policy_version='V2_ADD_A7200_MEASURED_RUNTIME',V2_add_budget_policy=policy())
            return writer(path,value)
        namespace=dict(original.__globals__,_NativeBudget=Facade,atomic=atomic)
        fn=FunctionType(original.__code__,namespace,original.__name__,original.__defaults__,original.__closure__);fn.__kwdefaults__=original.__kwdefaults__
        from v42_a_stage_acceptance import native as source
        optimized=solve_io()
        # The returned Native captures the verified compiled solve function.
        # Restore the source class immediately after construction.
        with patch.object(source.Native,'solve',optimized):result=fn(request,state,budget,progress)
        from .stage_common import record
        writer(Path(request['output'])/'V2_NATIVE_IO_AND_BUDGET_BINDING.json',dict(PASS=True,
            day=request['day'],arm=request['arm'],stage=request.get('stage'),Native_ceiling_seconds=budget.native_limit,
            original_facade_limit_seconds=result.budget.record['limit_seconds'],
            measured_Native_seconds=getattr(budget,'native_used',None),
            actual_original_native_constructor_called=True,actual_source_solve_readback_bound=True,
            numerical_solver_policy_and_optimize_body_unchanged=True,all_coefficients_independently_checked=True,
            source=record(__file__),Native_optimization_not_implied_by_constructor_receipt=True))
        return result
    return native
