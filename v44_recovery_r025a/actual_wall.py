"""Bind the inherited Actual wall guard to the dated V44 execution request.

V44 stage_request explicitly declares wall_budget_seconds=None. The V43
corrective runner accidentally retained its unrelated 2400-second default.
Native budgets, complete AC probes and all physical guards stay unchanged.
"""
from contextlib import contextmanager
import inspect
import linecache
import textwrap
from unittest.mock import patch


def require_policy():
    from v44.execution import assert_current
    from v44.common import read
    from v44.campaign import stage_request
    context = assert_current()
    request = context['request']
    permit = read(request['execution_permit']['path'])
    overlay = permit['autonomous_recovery_overlay']
    if (overlay['policy'] != 'V44_AUTONOMOUS_RECOVERY_R025A'
            or overlay.get('Actual_wall_budget_seconds', 'MISSING') is not None
            or stage_request(request, 'ACTUAL')['wall_budget_seconds'] is not None):
        raise PermissionError('DATED_V44_ACTUAL_WALL_POLICY_REQUIRED')


def adapted(function, guard=require_policy):
    body = textwrap.dedent(inspect.getsource(function))
    replacements = {
        "variants=('C0',),wall_limit_seconds=2400.,known_window_policy=None):":
        "variants=('C0',),wall_limit_seconds=None,known_window_policy=None):\n    _require_v44_wall_policy()",
        "if not 0<float(wall_limit_seconds)<=2400:":
        "if wall_limit_seconds is not None and not 0<float(wall_limit_seconds)<=2400:",
        "if perf_counter()-began>=wall_limit_seconds:":
        "if wall_limit_seconds is not None and perf_counter()-began>=wall_limit_seconds:",
    }
    for old, new in replacements.items():
        if body.count(old) != 1:
            raise ValueError('EXACT_ACTUAL_WALL_ADAPTER_BOUNDARY_DRIFT:' + old)
        body = body.replace(old, new)
    filename = __file__ + '.generated'
    linecache.cache[filename] = (len(body), None, body.splitlines(True), filename)
    namespace = dict(function.__globals__, _require_v44_wall_policy=guard)
    exec(compile(body, filename, 'exec'), namespace)
    return namespace[function.__name__]


@contextmanager
def install():
    import v43_corrective.compare as original
    with patch.object(original, 'run', adapted(original.run)):
        yield
