import ast
import inspect
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from v44_recovery_r009.actual_wall import adapted


def test_only_wall_guard_and_v44_authority_entry_change():
    import v43_corrective.compare as old
    source = textwrap.dedent(inspect.getsource(old.run))
    function = adapted(old.run, guard=lambda: None)
    actual = inspect.getsource(function)
    actual = actual.replace('wall_limit_seconds=None,known_window_policy=None):\n    _require_v44_wall_policy()',
                            'wall_limit_seconds=2400.,known_window_policy=None):')
    actual = actual.replace('if wall_limit_seconds is not None and not 0<float(wall_limit_seconds)<=2400:',
                            'if not 0<float(wall_limit_seconds)<=2400:')
    actual = actual.replace('if wall_limit_seconds is not None and perf_counter()-began>=wall_limit_seconds:',
                            'if perf_counter()-began>=wall_limit_seconds:')
    assert ast.dump(ast.parse(actual)) == ast.dump(ast.parse(source))


@pytest.mark.parametrize('limit,should_raise', [(None, False), (2400., True), (24000., False)])
def test_wall_deadline_none_and_explicit_finite_semantics(limit, should_raise, tmp_path):
    import v43_corrective.compare as old
    tree = ast.parse(inspect.getsource(adapted(old.run, guard=lambda: None)))
    node = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == 'check_deadline')
    module = ast.Module(body=[node], type_ignores=[])
    namespace = dict(perf_counter=lambda: 10000., began=0., wall_limit_seconds=limit,
                     atomic=lambda *a: None, output=tmp_path, now=lambda: 'UTC',
                     traceback=__import__('traceback'))
    exec(compile(module, '<deadline-test>', 'exec'), namespace)
    if should_raise:
        with pytest.raises(RuntimeError, match='40_MINUTE'):
            namespace['check_deadline']()
    else:
        namespace['check_deadline']()


def test_unleased_call_cannot_use_v44_wall_override(tmp_path):
    from v44_recovery_r009.actual_wall import require_policy
    with pytest.raises(RuntimeError, match='LIVE_CASE_LEASE'):
        require_policy()


def test_inherited_driver_can_inspect_generated_source():
    import v43_corrective.compare as old
    import v43_actual.compare as shared
    from v44.svr12_policy import corrective_driver
    from types import SimpleNamespace
    function = corrective_driver(adapted(old.run, guard=lambda: None), shared,
                                 SimpleNamespace(arm='B1'), 1746021600.)
    assert function.__kwdefaults__['wall_limit_seconds'] is None
    assert callable(function.__globals__['_require_v44_wall_policy'])


def test_wall_retry_is_diagnosed_bounded_and_only_once(tmp_path):
    from v44_recovery_r009.operations import needs_retry
    p = tmp_path/'2025-05-01/B1/attempt001'
    p.mkdir(parents=True)
    error = dict(error="RuntimeError('V43_ACTUAL_USER_40_MINUTE_WALL_LIMIT_REACHED')")
    assert needs_retry(p, error)
    assert not needs_retry(p, dict(error='OTHER_UNDIAGNOSED_FAILURE'))
    (p/'RECOVERY_R009_APPLIED.json').write_text('{}')
    assert not needs_retry(p, error)
    assert not needs_retry(p.with_name('attempt003'), error)


def test_b1_parent_replay_blocks_mismatched_day_or_arm(tmp_path):
    from v44_recovery_r009.wall_resume import validate_parent
    from v44.common import atomic
    parent=tmp_path/'2025-05-01/B1/attempt001'
    atomic(parent/'START.json',dict(day='2025-05-02',arm='B1'))
    with pytest.raises(PermissionError,match='SAME_DATE'):
        validate_parent(parent,tmp_path/'audit')
