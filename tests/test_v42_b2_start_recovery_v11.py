from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from v42_pr134_b1.common import atomic, read, record, sha
from v42_b2_start_recovery_v11 import storage, policy, coordinator as co, deferred_validation as gate
from v42_b2_start_recovery_v11.full_validation import semantic_digest


def test_namespace_all_fields_and_nested_middle_array_are_hashed():
    a = SimpleNamespace(matrix=np.zeros(10000), nested=SimpleNamespace(power=2.0))
    b = deepcopy(a)
    assert semantic_digest(a) == semantic_digest(b)
    b.matrix[5000] = 1
    assert str(a.matrix) == str(b.matrix)
    assert semantic_digest(a) != semantic_digest(b)
    b = deepcopy(a); b.nested.power = 3
    assert semantic_digest(a) != semantic_digest(b)
    b = deepcopy(a); b.extra_field = 0
    assert semantic_digest(a) != semantic_digest(b)
    assert semantic_digest(a) != semantic_digest(vars(a))


def test_unproven_objects_still_rejected():
    with pytest.raises(TypeError, match='UNPROVEN'):
        semantic_digest(object())
    class Derived(SimpleNamespace):
        pass
    with pytest.raises(TypeError, match='UNPROVEN'):
        semantic_digest(Derived(power=1))


def fixture_checkpoint():
    return dict(run_id='fixture', dates={co.key(arm, day):dict(arm=arm, day=day,
        status='PASS' if arm == 'B1' else 'PENDING', attempts=int(arm == 'B1'))
        for arm, day in co.AXIS})


def test_all_62_rows_preserved_without_any_retry(tmp_path):
    before = fixture_checkpoint()
    atomic(tmp_path/'boundary.json', before)
    manifest = dict(run_id='fixture', base_checkpoint=record(tmp_path/'boundary.json'))
    with patch('v42_may31_recovery_v10.coordinator.read_actives', return_value={}):
        after = storage.initialize_checkpoint(tmp_path, manifest)
    assert policy.RETRY_DATES == ()
    assert before['dates'] == after['dates']
    assert sha(tmp_path/'boundary.json') == manifest['base_checkpoint']['sha256']


@pytest.mark.parametrize('key,status', [('B1/2025-05-31','NUMERICAL_FAILURE'), ('B2/2025-05-01','RUNNING')])
def test_unfinished_b1_or_started_b2_cannot_transition(tmp_path,key,status):
    before = fixture_checkpoint(); before['dates'][key]['status'] = status
    atomic(tmp_path/'boundary.json', before)
    with patch('v42_may31_recovery_v10.coordinator.read_actives', return_value={}):
        with pytest.raises(PermissionError, match='ALL_31_B1'):
            storage.initialize_checkpoint(tmp_path,dict(run_id='fixture',base_checkpoint=record(tmp_path/'boundary.json')))


def inherited_fixture(root):
    day='2025-05-31'; folder=root/'dates/B1'/day/'attempts/old'; folder.mkdir(parents=True)
    old_manifest=root/'CONTINUATION_V10_MANIFEST.json'; atomic(old_manifest,{'fixture':True})
    request=dict(root=str(root), run_id='fixture',arm='B1',day=day,result=str(folder/'RESULT.json'),
        input_folder=str(root/'inputs/B1'/day),manifest=str(old_manifest),manifest_SHA=sha(old_manifest),
        Threads=1,P2_calls=0,native_budget_seconds=5400,wall_budget_seconds=None,target_gap=.005)
    atomic(folder/'request.json',request)
    boundary=root/'boundary.json'
    atomic(boundary,dict(dates={'B1/'+day:dict(status='PASS', attempts=1, request=str(folder/'request.json'))}))
    manifest=dict(run_id='fixture',base_checkpoint=record(boundary),input_folders={'B1/'+day:request['input_folder']},
        inherited_request_receipts={'B1/'+day:record(folder/'request.json')})
    return manifest,request


def test_sealed_inherited_request_uses_no_legacy_native_admission(tmp_path):
    manifest,request=inherited_fixture(tmp_path)
    with patch('v42_may31_recovery_v10.coordinator.validate_request',side_effect=AssertionError('legacy admission called')):
        assert storage.validate_inherited_request(tmp_path,manifest,request) is None


@pytest.mark.parametrize('field,value', [('day','2025-05-30'), ('Threads',2), ('root','D:/wrong'),
    ('manifest_SHA','wrong'), ('input_folder','D:/other'), ('target_gap',.03)])
def test_inherited_request_mutations_fail_closed(tmp_path,field,value):
    manifest,request=inherited_fixture(tmp_path);request[field]=value
    with pytest.raises(PermissionError):
        storage.validate_inherited_request(tmp_path,manifest,request)


def test_failed_build_preserves_actual_diagnostic(tmp_path):
    result=tmp_path/'RESULT.json'
    atomic(result,dict(PASS=False,error='TypeError: coefficient schema drift'))
    with pytest.raises(PermissionError, match='coefficient schema drift'):
        gate.validate_receipt(result,{})


def test_current_production_uses_same_accelerated_original_m_port():
    from v42_b2_start_recovery_v11 import m_stage
    from v42_b2_build_optimization import builder
    import inspect
    from v42_may_campaign_native90 import m_stage as original
    assert m_stage.original is original
    assert 'build_case=build_case' in inspect.getsource(m_stage.prepare)
    assert 'prepare=prepare' in inspect.getsource(m_stage.run)
    assert builder.VERSION == policy.BUILD_VERSION
    assert gate.ORDER == tuple((d,m) for d in ('2025-05-01','2025-05-23') for m in ('BASELINE','OPTIMIZED'))
