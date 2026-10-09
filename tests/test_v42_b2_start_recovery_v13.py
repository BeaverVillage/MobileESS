from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pytest
from v42_pr134_b1.common import atomic, read, record, sha
from v42_b2_start_recovery_v13 import storage, policy, coordinator as co, deferred_validation as gate
from v42_b2_start_recovery_v13.full_validation import semantic_digest


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
    with patch('v42_b2_start_recovery_v12.coordinator.read_actives', return_value={}):
        after = storage.initialize_checkpoint(tmp_path, manifest)
    assert policy.RETRY_DATES == ()
    assert before['dates'] == after['dates']
    assert sha(tmp_path/'boundary.json') == manifest['base_checkpoint']['sha256']


@pytest.mark.parametrize('key,status', [('B1/2025-05-31','NUMERICAL_FAILURE'), ('B2/2025-05-01','RUNNING')])
def test_unfinished_b1_or_started_b2_cannot_transition(tmp_path,key,status):
    before = fixture_checkpoint(); before['dates'][key]['status'] = status
    atomic(tmp_path/'boundary.json', before)
    with patch('v42_b2_start_recovery_v12.coordinator.read_actives', return_value={}):
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
    with patch('v42_b2_start_recovery_v12.coordinator.validate_request',side_effect=AssertionError('legacy admission called')):
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
    from v42_b2_start_recovery_v13 import m_stage
    from v42_b2_build_authority_v13 import builder
    import inspect
    from v42_may_campaign_native90 import m_stage as original
    assert m_stage.original is original
    assert 'build_case=build_case' in inspect.getsource(m_stage.prepare)
    assert 'prepare=prepare' in inspect.getsource(m_stage.run)
    assert builder.VERSION == policy.BUILD_VERSION
    assert gate.ORDER == tuple((d,m) for d in ('2025-05-01','2025-05-23') for m in ('BASELINE','OPTIMIZED'))


def passed_gate_fixture(root):
    builds={}
    for day,mode in gate.ORDER:
        p=root/(day+'_'+mode+'.json');atomic(p,dict(PASS=True,Native_calls=0))
        builds[day+'/'+mode]=dict(receipt=record(p))
    atomic(root/'B2_BUILD_FULL_VALIDATION_V13.json',dict(status='PASS',PASS=True,
        implementation_SHA='fixture',builds=builds,
        comparisons={d:dict(PASS=True) for d in ('2025-05-01','2025-05-23')}))


def test_passed_full_gate_allows_live_three_workers(tmp_path):
    passed_gate_fixture(tmp_path);cp=fixture_checkpoint()
    active={f'B2/2025-05-0{i}':dict(worker_slot=i) for i in (1,2,3)}
    assert gate.ready(tmp_path,dict(implementation=dict(source_SHA='fixture')),cp,active)
    assert cp['state']=='RUNNING'


def test_unpassed_full_gate_cannot_build_with_active_workers(tmp_path):
    with pytest.raises(PermissionError,match='REQUIRES_NO_WORKERS'):
        gate.ready(tmp_path,{},fixture_checkpoint(),{'B2/2025-05-01':{}})


def test_parallel_artifact_hashes_verify_every_byte_and_reject_mutation(tmp_path):
    files=[]
    for i in range(20):
        p=tmp_path/(str(i)+'.json');atomic(p,dict(science=i));files.append(record(p))
    request=dict(run_id='fixture',arm='B1',day='2025-05-01')
    receipt=dict(identity=request,status='PASS',PASS=True,files=files)
    assert co.receipt_valid(tmp_path,{},request,receipt)
    atomic(Path(files[11]['path']),dict(science=99))
    assert not co.receipt_valid(tmp_path,{},request,receipt)
    outside=tmp_path.parent/'outside.json';atomic(outside,dict(science=1));files.append(record(outside))
    assert not co.receipt_valid(tmp_path,{},request,receipt)


def test_actual_original_source_lookup_uses_sealed_base_implementation():
    import sys
    from v42_b2_build_authority_v13.builder import AdmittedSourceGateway
    from v42_b2_start_recovery_v13.source_authority import original_sources
    from v42_pr134_b1.common import ROOT
    campaign=ROOT/'runtime/v42_may_campaign/native90_build_reuse_20261009_01'
    sources=original_sources(campaign)
    request=dict(arm='B2',day='2025-05-01',run_id='fixture',Threads=1,P2_calls=0,
        native_budget_seconds=5400,wall_budget_seconds=None,target_gap=.03)
    manifest=dict(run_id='fixture',sources={},builder_original_sources=sources,
        implementation=dict(version=policy.BUILD_VERSION,sources=policy.source_files()))
    execution=SimpleNamespace(current=lambda:dict(request=request,manifest=manifest),authorize=lambda *args:None)
    with patch.dict(sys.modules,{'v42_may_campaign_native90.execution':execution}):
        gateway=AdmittedSourceGateway(request)
        for relative in ('v42_may_campaign_native90/m_model.py','v42_bootstrap/m1.py','v42_native/mess.py'):
            assert gateway.source_sha(relative)==sha(ROOT/relative)
            module=gateway.resolve(relative[:-3].replace('/','.'))
            assert Path(module.__file__).resolve()==ROOT/relative
        manifest['builder_original_sources']['v42_may_campaign_native90/m_model.py']='0'*64
        with pytest.raises(ValueError,match='SHA_DRIFT'):
            gateway.source_sha('v42_may_campaign_native90/m_model.py')
