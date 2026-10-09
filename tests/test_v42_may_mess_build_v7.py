"""Transition safety and exact source snapshots using small fixtures only."""
import ast
import hashlib
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from v42_pr134_b1.common import atomic, read, record, sha
from v42_may_mess_build_v7 import deferred_validation as gate
from v42_may_mess_build_v7.full_validation import semantic_digest
from v42_may_mess_build_v7.transition import hold_previous
from v42_b2_build_optimization.copy_elision import snapshot_before_dispose


COPY_FIXTURE = '''def build_case():
    captured = []
    model = Model()
    def capture(model):
        model.update()
        captured.append(model.copy())
    capture(model)
    model.dispose()
    model = captured[0]
    try:
        A, d = arrays(model)
    finally:
        model.dispose()
    return A, d
'''


def test_copy_elision_preserves_all_detached_values_and_original_disposal():
    counts = {'copies': 0, 'disposals': 0}
    class Model:
        def __init__(self): self.values = np.array([[1., -2.], [3., 4.]])
        def update(self): pass
        def copy(self):
            counts['copies'] += 1
            return Model()
        def dispose(self):
            counts['disposals'] += 1
            self.values[:] = 999
    def arrays(model):
        return model.values.copy(), {'lower': np.array([0., -5.]), 'upper': np.array([1., 7.]),
            'types': np.array(['B', 'C']), 'rhs': np.array([2., 3.]), 'sense': np.array(['=', '<']),
            'objective': np.array([0., 1.]), 'constant': np.array(0.)}
    original = {}
    exec(compile(COPY_FIXTURE, '<SMALL_FIXTURE>', 'exec'), dict(Model=Model, arrays=arrays), original)
    before = original['build_case']()
    assert counts == dict(copies=1, disposals=2)
    counts.update(copies=0, disposals=0)
    tree = ast.parse(COPY_FIXTURE)
    proof = snapshot_before_dispose(tree.body[0])
    optimized = {}
    exec(compile(ast.fix_missing_locations(tree), '<SMALL_FIXTURE>', 'exec'), dict(Model=Model, arrays=arrays), optimized)
    after = optimized['build_case']()
    assert proof['scientific_AST_roundtrip_identical']
    assert counts == dict(copies=0, disposals=1)
    assert semantic_digest(before) == semantic_digest(after)


def test_copy_elision_source_drift_fails_closed():
    tree = ast.parse(COPY_FIXTURE.replace('model = captured[0]', 'model = captured[-1]'))
    with pytest.raises(ValueError, match='SOURCE_SHAPE'):
        snapshot_before_dispose(tree.body[0])


def test_fingerprint_hashes_hidden_middle_array_entries():
    first = np.zeros(10000)
    second = first.copy()
    second[5000] = 1.
    assert str(first) == str(second)
    assert semantic_digest(first) != semantic_digest(second)
    assert semantic_digest({'graph': [1, 2]}) == semantic_digest({'graph': (1, 2)})


def test_fingerprint_unknown_types_are_not_promoted_to_pass():
    with pytest.raises(TypeError, match='UNPROVEN'):
        semantic_digest(object())


def test_handoff_holds_dispatch_and_preserves_live_worker_identity(tmp_path):
    identity = dict(PID=123, created=456, command=['FAKE_WORKER'])
    with patch('v42_may_build_v6.coordinator.read_actives', return_value={
            'B1/2025-05-23':dict(arm='B1', day='2025-05-23', worker=identity)}):
        value = hold_previous(tmp_path, source_version='FAKE_VERSION')
    assert value['healthy_worker_kill'] is False and value['dispatch_only']
    assert read(tmp_path / 'HOLD_V6.json')['active_worker_identities']['B1/2025-05-23']['worker'] == identity


def test_handoff_rejects_already_started_b2(tmp_path):
    with patch('v42_may_build_v6.coordinator.read_actives', return_value={'B2/2025-05-01':dict(arm='B2')}):
        with pytest.raises(PermissionError, match='RUNNING_B2'):
            hold_previous(tmp_path, source_version='FAKE_VERSION')
    assert not (tmp_path / 'HOLD_V6.json').exists()


def cp(terminal):
    return dict(state='RUNNING', dates={'B1/2025-05-%02d' % n:dict(arm='B1', status='PASS' if n <= terminal else 'RUNNING')
                                     for n in range(1,32)})


def test_full_model_preflight_cannot_overlap_last_b1_or_any_worker(tmp_path):
    with pytest.raises(PermissionError, match='ALL_B1_TERMINAL'):
        gate.ready(tmp_path, {}, cp(30), {})
    with pytest.raises(PermissionError, match='NO_WORKERS'):
        gate.ready(tmp_path, {}, cp(31), {'old': {'arm': 'B1'}})


def test_failed_full_validation_blocks_dispatch_and_never_retries(tmp_path):
    atomic(tmp_path/'B2_BUILD_FULL_VALIDATION_V7R2.json', dict(status='FAIL', PASS=False, error='UNCHANGED_SOURCE_MODEL_MISMATCH'))
    checkpoint = cp(31)
    with patch.object(gate.subprocess, 'Popen', side_effect=AssertionError('UNSAFE_RETRY')):
        assert gate.ready(tmp_path, {}, checkpoint, {}) is False
    assert checkpoint['state'] == 'B2_BUILD_VALIDATION_FAILED'


def test_full_gate_packet_hash_and_version_are_required(tmp_path):
    result = tmp_path/'RESULT.json';atomic(result, dict(PASS=True, Native_calls=0))
    receipt = record(result)
    atomic(tmp_path/'B2_BUILD_FULL_VALIDATION_V7R2.json', dict(status='PASS', PASS=True,
        implementation_SHA='SOURCE_SHA',
        comparisons={d:dict(PASS=True) for d in ('2025-05-01','2025-05-23')},
        builds={d+'/'+m:dict(receipt=receipt) for d,m in gate.ORDER}))
    with pytest.raises(PermissionError, match='SOURCE_DRIFT'):
        gate.ready(tmp_path, {'implementation':{'source_SHA':'OTHER'}}, cp(31), {})
    assert gate.ready(tmp_path, {'implementation':{'source_SHA':'SOURCE_SHA'}}, cp(31), {})
    atomic(result, dict(PASS=True, Native_calls=1))
    with pytest.raises(PermissionError, match='PACKET_SHA'):
        gate.ready(tmp_path, {'implementation':{'source_SHA':'SOURCE_SHA'}}, cp(31), {})


def test_preflight_order_is_one_model_and_one_date_at_a_time():
    assert gate.ORDER == (('2025-05-01','BASELINE'), ('2025-05-01','OPTIMIZED'),
                         ('2025-05-23','BASELINE'), ('2025-05-23','OPTIMIZED'))


def test_native_zero_gate_restart_adopts_live_validation_without_duplicate(tmp_path):
    atomic(tmp_path/'B2_BUILD_FULL_VALIDATION_V7R2.json', dict(status='RUNNING', builds={},
        active=dict(process={'PID':123}, result=str(tmp_path/'RESULT.json'), request='UNREAD')))
    with patch.object(gate, 'same_process', return_value=True), patch.object(
            gate.subprocess, 'Popen', side_effect=AssertionError('DUPLICATE_VALIDATION')):
        assert not gate.ready(tmp_path, {'implementation':{'source_SHA':'SOURCE'}}, cp(31), {})


def test_missing_full_model_comparison_cannot_be_forged_as_pass(tmp_path):
    atomic(tmp_path/'B2_BUILD_FULL_VALIDATION_V7R2.json', dict(status='PASS', builds={},
        implementation_SHA='SOURCE', comparisons={}))
    with pytest.raises(PermissionError, match='COVERAGE_OR_COMPARISON'):
        gate.ready(tmp_path, {'implementation':{'source_SHA':'SOURCE'}}, cp(31), {})


def test_original_and_v7_authorizers_share_scope_and_block_validation_native():
    from v42_may_mess_build_v7 import execution
    from v42_may_campaign_native90 import execution as original
    assert execution._active is original._active
    token = execution._active.set(dict(preflight_native_zero=True))
    try:
        with pytest.raises(PermissionError, match='MODEL_COMPARISON_NATIVE_OPTIMIZE_FORBIDDEN'):
            execution.guard(object())
    finally:
        execution._active.reset(token)


def test_b1_functions_are_the_frozen_v6_functions():
    from v42_may_mess_build_v7 import a_stage
    from v42_may_build_v6 import a_stage as frozen
    assert a_stage.run is frozen.run and a_stage.prepare is frozen.prepare


def test_activation_uses_real_scheduler_api_and_preserves_failed_admission(tmp_path):
    from v42_may_mess_build_v7 import transition, windows, policy
    failed = tmp_path / 'CONTINUATION_V7_MANIFEST.json'
    atomic(failed, dict(status='FAILED_ADMISSION', original_source='IMMUTABLE'))
    original_sha = sha(failed)
    tasks = {role:'MobileESS_V42_B1B2_P1_fixture_MessBuildV7R2_'+role.title()
             for role in ('monitor', 'coordinator', 'watchdog')}
    atomic(tmp_path / policy.MANIFEST, dict(tasks=tasks))
    assert policy.DEPLOYMENT_REVISION == 2
    assert policy.MANIFEST != failed.name
    with patch.object(windows, 'register_campaign_tasks', return_value={'fixture':True}), patch.object(
            windows, 'run_task', side_effect=lambda name:dict(name=name, dispatch_requested=True)) as run:
        value = transition.activate(tmp_path)
    assert [call.args[0] for call in run.call_args_list] == list(tasks.values())
    assert value['worker_kills'] == 0
    assert sha(failed) == original_sha
    assert (tmp_path/'SOURCE_TRANSITION_ACTIVATION_V7R2.json').exists()
