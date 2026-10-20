"""Serialize unavailable solver diagnostic bounds without changing numerical policy."""
from contextlib import contextmanager, ExitStack
import inspect
import linecache
import math
import textwrap
from unittest.mock import patch


def finite(value):
    return value if value is None or math.isfinite(float(value)) else None


def nonfinite(value):
    return None if value is None or math.isfinite(float(value)) else repr(float(value))


def adapted(function, old, new):
    source = textwrap.dedent(inspect.getsource(function))
    if source.count(old) != 1:
        raise ValueError('FINITE_DIAGNOSTIC_SOURCE_BOUNDARY_DRIFT:' + function.__name__)
    source = source.replace(old, new)
    dynamic_parameters = function.__name__ == '_native_joint'
    if dynamic_parameters:
        boundary='params = dict(APPROVED_JOINT_PARAMETERS,'
        if source.count(boundary)!=1:raise ValueError('JOINT_PARAMETER_LOOKUP_BOUNDARY_DRIFT')
        source=source.replace(boundary,'params = dict(_current_joint_parameters(),')
    # A later approved thread adapter calls inspect.getsource on this clone.
    # Give it the actual cloned source instead of the original file's line 1.
    filename = '<v44_recovery_r007.' + function.__name__ + '>'
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    namespace = dict(function.__globals__, _finite_diagnostic=finite, _nonfinite_diagnostic=nonfinite)
    if dynamic_parameters:
        # q250_m4_v2 applies its M-only parameters after this adapter loads.
        # Observe that exact live scope, including May02 robust Barrier knobs.
        namespace['_current_joint_parameters']=lambda:function.__globals__['APPROVED_JOINT_PARAMETERS']
    exec(compile(source, filename, 'exec'), namespace)
    return namespace[function.__name__]


@contextmanager
def install():
    from v42_may_campaign_native90.budget import DateBudget
    from v44.frozen.v43_mess.library import load
    modules = load()
    engine, adaptive = modules['m_engine'], modules['m_adaptive']
    native = adapted(DateBudget.native_optimize,
        "Native_BestBd=attr('ObjBound'),",
        "Native_BestBd=_finite_diagnostic(attr('ObjBound')), "
        "Native_BestBd_nonfinite=_nonfinite_diagnostic(attr('ObjBound')),")
    joint = adapted(engine._native_joint,
        'result["restricted_ObjBound_diagnostic"] = float(model.ObjBound)',
        'result["restricted_ObjBound_diagnostic"] = _finite_diagnostic(model.ObjBound)\n'
        '                result["restricted_ObjBound_nonfinite"] = _nonfinite_diagnostic(model.ObjBound)')
    with ExitStack() as stack:
        stack.enter_context(patch.object(DateBudget, 'native_optimize', native))
        stack.enter_context(patch.object(engine, '_native_joint', joint))
        stack.enter_context(patch.object(adaptive, '_native_joint', joint))
        yield
