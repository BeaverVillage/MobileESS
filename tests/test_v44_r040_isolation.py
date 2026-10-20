from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import copy,json
import pytest
from v44.common import atomic,read,record
from v44_recovery_r040 import operations as op,batch,actual
from tests.test_v44_r038_batch import topology

QUEUE=[dict(day=d,arm=a) for d,a in [('2025-05-04','B3'),('2025-05-05','B1'),('2025-05-05','B3'),('2025-05-06','B1'),('2025-05-06','B3'),('2025-05-07','B1'),('2025-05-07','B3')]]

@pytest.fixture
def scope(tmp_path,monkeypatch):
    auth=tmp_path/'auth.json';atomic(auth,dict(user_authorized=True))
    ops=tmp_path/'ops';ops.mkdir()
    monkeypatch.setattr(op,'OPS',ops);monkeypatch.setattr(op,'CAMPAIGN',tmp_path)
    monkeypatch.setattr(op,'AMENDMENT',auth);monkeypatch.setattr(op,'STATE',tmp_path/'state.json')
    monkeypatch.setattr(op,'MANIFEST',ops/'manifest.json');monkeypatch.setattr(op,'queue',lambda:copy.deepcopy(QUEUE))
    monkeypatch.setattr(batch,'windows_cpu_sets',topology)
    jobs=[]
    for i,j in enumerate(QUEUE):
        root=tmp_path/str(i);root.mkdir();pointer=tmp_path/f'request{i}.json'
        atomic(pointer,dict(**j,case_root=str(root),sources=[]))
        handoff=root/'PRE_ACTUAL_READY.json';atomic(handoff,dict(ready=True))
        atomic(root/'RESULT.json',dict(status='PRE_ACTUAL_READY',PASS=False))
        jobs.append(dict(j,status='PREPARED',case_root=str(root),prepare_request=str(pointer),handoff=record(handoff)))
    return dict(jobs=jobs,lease={},phase='PREPARE_SERIAL')

@pytest.mark.parametrize('bad',range(7))
def test_one_bad_handoff_excludes_only_that_case_and_preserves_six(scope,bad):
    def check(job):
        if op.key(job)==op.key(QUEUE[bad]):raise ValueError('damaged evidence')
    with patch.object(batch,'check_ready',side_effect=check):manifest=batch.preflight(scope)
    assert len(manifest['ready'])==6 and len(manifest['excluded'])==1
    assert op.key(manifest['excluded'][0])==op.key(QUEUE[bad])
    assert all(op.key(j)!=op.key(QUEUE[bad]) for j in manifest['ready'])

@pytest.mark.parametrize('healthy',range(8))
def test_any_healthy_subset_from_zero_to_seven_is_authorized(scope,healthy):
    for j in scope['jobs'][healthy:]:batch.exclude(j,'PREPARATION_FAILED')
    with patch.object(batch,'check_ready'):manifest=batch.preflight(scope)
    assert len(manifest['ready'])==healthy and len(manifest['excluded'])==7-healthy
    assert batch.resolved(scope['jobs'])
    if healthy:
        assert len(manifest['cpu_placement']['slots'])==healthy
        assert all(r['logical']<12 for r in manifest['cpu_placement']['slots'])

def test_unattempted_planning_does_not_start_actual_early(scope):
    scope['jobs'][-1]['status']='PENDING'
    with patch.object(batch,'check_ready'),pytest.raises(PermissionError,match='PENDING_PREPARATION'):batch.preflight(scope)

def test_duplicate_or_missing_case_cannot_forge_resolved_subset(scope):
    with patch.object(batch,'check_ready'):m=batch.preflight(scope)
    m['ready'][1]=m['ready'][0]
    with pytest.raises(PermissionError,match='RESOLVED_ONCE'):batch.validate_manifest(m,QUEUE)

@pytest.mark.parametrize('healthy',range(1,8))
def test_actual_authorization_accepts_resolved_subset_without_old_all_seven_success_gate(scope,healthy):
    for j in scope['jobs'][healthy:]:batch.exclude(j,'FAILED')
    with patch.object(batch,'check_ready'):manifest=batch.preflight(scope)
    manifest.update(authorization=record(op.AMENDMENT));atomic(op.MANIFEST,manifest)
    job=scope['jobs'][0];request=read(job['prepare_request'])
    request.update(R040_authorization=record(op.AMENDMENT),R040_sources=[],R039_sources=[],
        R039_latency_authorization=record(op.previous.AMENDMENT),worker_slot=1,r038_phase='ACTUAL_PARALLEL',
        parallel_actual_slot=1,R040_resolved_manifest=record(op.MANIFEST),R038_pre_actual_handoff=job['handoff'],lease={})
    with patch.object(op,'authority'),patch.object(op,'sources',return_value=[]),patch.object(op.original.previous,'authorize') as scientific,patch.object(op.original,'authorize',side_effect=AssertionError('old all-seven gate')):
        op.authorize(request)
    scientific.assert_called_once_with(request)

def test_actual_authorization_cannot_dispatch_an_excluded_case(scope):
    batch.exclude(scope['jobs'][0],'FAILED')
    with patch.object(batch,'check_ready'):manifest=batch.preflight(scope)
    manifest.update(authorization=record(op.AMENDMENT));atomic(op.MANIFEST,manifest)
    job=scope['jobs'][0];r=read(job['prepare_request']);r.update(R040_resolved_manifest=record(op.MANIFEST),parallel_actual_slot=1,lease={},R038_pre_actual_handoff=job['handoff'])
    with pytest.raises(PermissionError,match='HEALTHY_SUBSET'):op.subset(r)

def test_existing_pass_is_preserved_and_never_dispatched(scope):
    j=scope['jobs'][0];path=Path(j['case_root'])/'RESULT.json';atomic(path,dict(PASS=True,status='COMPLETE'))
    before=path.read_bytes();batch.reconcile(j)
    assert j['status']=='PASS' and path.read_bytes()==before
    with patch.object(batch,'check_ready'):m=batch.preflight(scope)
    assert len(m['ready'])==6 and op.key(m['already_complete'][0])==op.key(j)

def test_preparing_case_finished_during_handover_is_reused(scope):
    j=scope['jobs'][0];j['status']='PREPARING'
    atomic(Path(j['case_root'])/'RESULT.json',dict(PASS=False,status='PRE_ACTUAL_READY',preparation_PASS=True,pre_actual_handoff=j['handoff']))
    batch.reconcile(j);assert j['status']=='PREPARED'

def test_stopped_actual_is_excluded_with_partial_context_preserved(scope):
    j=scope['jobs'][0];j['status']='ACTUAL_RUNNING'
    folder=Path(j['case_root'])/'ACTUAL';folder.mkdir();(folder/'private').write_text('preserve')
    batch.reconcile(j)
    assert j['status']=='EXCLUDED' and (folder/'private').read_text()=='preserve'

def test_launch_failure_and_one_actual_failure_do_not_stop_other_cases(scope):
    with patch.object(batch,'check_ready'):manifest=batch.preflight(scope)
    launches=[]
    def launch(pointer,label):
        r=read(pointer);launches.append(op.key(r))
        if op.key(r)==op.key(QUEUE[1]):raise OSError('injected launch failure')
        okay=op.key(r)!=op.key(QUEUE[4]);atomic(Path(r['case_root'])/'RESULT.json',dict(PASS=okay,status='COMPLETE' if okay else 'FAILED'))
        return SimpleNamespace(pid=100+len(launches),returncode=0,poll=lambda:0)
    with patch.object(op,'attach',side_effect=lambda r:r),patch.object(op,'authorize'),patch.object(op,'launch',side_effect=launch),patch.object(batch,'status'),patch.object(batch.time,'sleep'):
        batch.run_wave(scope,manifest)
    assert len(launches)==7
    assert sum(j['status']=='PASS' for j in scope['jobs'])==5
    assert sum(j['status']=='ACTUAL_FAILED' for j in scope['jobs'])==2

def test_corrupt_completed_case_telemetry_cannot_break_other_workers(scope):
    (Path(scope['jobs'][0]['case_root'])/'RESULT.json').write_text('{broken')
    batch.status(scope,[])
    status=read(op.CAMPAIGN/'CAMPAIGN_STATUS.json')
    assert len(status['cases'])==28

def test_actual_worker_replaces_only_old_batch_gate_and_keeps_base_install(scope):
    r=read(scope['jobs'][0]['prepare_request']);r.update(r038_phase='ACTUAL_PARALLEL',parallel_actual_slot=1)
    p=Path(scope['jobs'][0]['prepare_request']);atomic(p,r)
    plan=batch.cpu.placement(topology(),1);seen=[]
    @contextmanager
    def installed():seen.append('inherited_science');yield
    @contextmanager
    def latency(guard):seen.append('latency_removal');yield
    def base_worker(request):
        from v44_recovery_r029 import conditional_campaign
        assert conditional_campaign.run_case is actual.actual_case
        seen.append('worker');return 42
    with patch.object(op,'authorize'),patch.object(op,'subset',return_value=dict(cpu_placement=plan)),patch.object(op.cpu,'validate_topology'),patch.object(op.psutil,'Process'),patch.object(op.original.previous,'install',installed),patch.object(op.previous.latency,'install',latency),patch.object(op.base,'worker',side_effect=base_worker):
        assert op.worker(p)==42
    assert seen==['inherited_science','latency_removal','worker']

def test_actual_only_reuses_plan_and_never_calls_a_or_m(scope):
    from v44 import worker,campaign
    j=scope['jobs'][0];r=read(j['prepare_request']);r.update(parallel_actual_slot=1,lease={},R039_sources=[],R040_sources=[],source_sha='fixed',R038_pre_actual_handoff=j['handoff'],R040_resolved_manifest={})
    @contextmanager
    def slot(*args):yield dict(logical=0)
    @contextmanager
    def case(*args):yield
    handoff=dict(aidc_folder=j['case_root'],MESS_result='old M2 result',MESS_plan={'frozen':True})
    with patch.object(op,'subset',return_value={'cpu_placement':{}}),patch.object(actual,'actual_slot',slot),patch('v44.execution.case_scope',case),patch.object(actual,'load_handoff',return_value=handoff),patch.object(campaign,'stage_request',return_value={}),patch.object(worker,'actual',return_value={'PASS':True}) as call,patch.object(worker,'a_stage',side_effect=AssertionError('A rerun')),patch.object(worker,'m_stage',side_effect=AssertionError('M rerun')):
        result=actual.actual_case(r)
    assert result['PASS'] and call.call_count==1 and call.call_args.args[2]==handoff['MESS_plan']

def test_completed_pass_cannot_be_overwritten(scope):
    j=scope['jobs'][0];path=Path(j['case_root'])/'RESULT.json';atomic(path,dict(PASS=True,status='COMPLETE'))
    r=read(j['prepare_request']);r.update(parallel_actual_slot=1)
    with patch.object(op,'subset',return_value={'cpu_placement':{}}),pytest.raises(PermissionError,match='PASS_PROTECTED'):actual.actual_case(r)

def test_existing_actual_directory_is_never_overwritten(scope):
    from v44 import worker
    j=scope['jobs'][0];root=Path(j['case_root']);(root/'ACTUAL').mkdir();(root/'ACTUAL/keep').write_text('original')
    r=read(j['prepare_request']);r.update(parallel_actual_slot=1,lease={})
    @contextmanager
    def slot(*a):yield {}
    @contextmanager
    def case(*a):yield
    with patch.object(op,'subset',return_value={'cpu_placement':{}}),patch.object(actual,'actual_slot',slot),patch('v44.execution.case_scope',case),patch.object(actual,'load_handoff',return_value={}),patch.object(worker,'actual') as call:
        result=actual.actual_case(r)
    assert 'ACTUAL_CONTEXT_PROTECTED' in result['error'] and call.call_count==0 and (root/'ACTUAL/keep').read_text()=='original'
