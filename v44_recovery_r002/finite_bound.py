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
    # A later approved thread adapter calls inspect.getsource on this clone.
    # Give it the actual cloned source instead of the original file's line 1.
    filename = '<v44_recovery_r002.' + function.__name__ + '>'
    linecache.cache[filename] = (len(source), None, source.splitlines(keepends=True), filename)
    namespace = dict(function.__globals__, _finite_diagnostic=finite, _nonfinite_diagnostic=nonfinite)
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
