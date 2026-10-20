from pathlib import Path
from unittest.mock import patch
from contextlib import contextmanager
from types import SimpleNamespace
import copy
import pytest
from v44.common import read,atomic,record
from v44_recovery_r042 import operations as op
from tests.test_v44_r040_isolation import scope,QUEUE

@pytest.fixture
def local(scope,monkeypatch):
    monkeypatch.setattr(op,'OPS',op.actual.OPS);monkeypatch.setattr(op,'CAMPAIGN',op.actual.CAMPAIGN)
    monkeypatch.setattr(op,'STATE',op.actual.STATE);monkeypatch.setattr(op,'AMENDMENT',op.actual.AMENDMENT)
    monkeypatch.setattr(op,'RELEASE',op.OPS/'release.json')
    scope['phase']='PRE_ACTUAL_USER_HOLD';atomic(op.STATE,scope)
    atomic(op.CAMPAIGN/'COORDINATOR_LEASE.json',{})
    atomic(op.OPS/'CURRENT_HANDOFF.json',{})
    return scope

@pytest.mark.parametrize('unready',['PENDING','PREPARING','ACTUAL_RUNNING'])
def test_one_unresolved_preparation_cannot_release_actual(local,unready):
    local['jobs'][3]['status']=unready
    assert not op.resolved_state(local)

def test_all_success_and_resolved_exclusion_both_allow_barrier(local):
    assert op.resolved_state(local)
    local['jobs'][2]['status']='EXCLUDED'
    assert op.resolved_state(local)
    local['phase']='PREPARE_SERIAL'
    assert not op.resolved_state(local)

def test_actual_worker_cannot_start_without_sealed_release(local):
    with pytest.raises(FileNotFoundError):op.release_authorized(dict(lease={}))

def test_new_user_stop_blocks_even_an_otherwise_valid_release(local):
    atomic(op.RELEASE,dict(authorization=record(op.AMENDMENT),lease={},all_preparations_resolved=True))
    atomic(op.OPS/'STOP_AUTONOMY.json',dict(reason='NEW_USER_STOP'))
    with patch.object(op,'alive',return_value=True),pytest.raises(PermissionError,match='NEW_USER_STOP'):op.release_authorized(dict(lease={}))

def test_worker_refuses_preparation_route_and_never_enters_actual(local):
    p=op.OPS/'request.json';atomic(p,dict(R042_sources=[],R041_sources=[],R042_authorization=record(op.AMENDMENT),r038_phase='PREPARE_SERIAL'))
    with patch.object(op,'authority'),patch.object(op.actual,'worker') as call,pytest.raises(PermissionError,match='ACTUAL_ONLY_AFTER_BARRIER'):op.worker(p)
    call.assert_not_called()

def test_prepare_launch_is_not_available_in_actual_only_supervisor():
    with pytest.raises(PermissionError,match='FENCED_R041'):op.launch(Path('never'),'prepare')

def test_actual_request_cannot_reenter_legacy_a1_or_a2_resume_routes(local):
    original=dict(wall_resume_parent='saved A1',planning_repair_parent='saved P1',fresh_a2_parent='saved M1',actual_resume_parent='old Actual',sources=['unchanged'],source_sha='original frozen digest',case_root='same original case')
    with patch.object(op.preparation,'attach',side_effect=lambda r:dict(r)):
        r=op.attach(original)
    for key in ('wall_resume_parent','planning_repair_parent','fresh_a2_parent','actual_resume_parent'):assert key not in r
    assert r['R042_preparation_routing_preserved']['wall_resume_parent']=='saved A1'
    assert r['sources']==original['sources'] and r['source_sha']==original['source_sha'] and r['case_root']==original['case_root']

def test_watchdog_only_releases_hold_after_complete_preflight(local):
    stop=op.OPS/'STOP_AUTONOMY.json';atomic(stop,dict(reason=op.preparation.HOLD,allow_preparation=True,authorization=record(op.preparation.AMENDMENT)))
    seen=[]
    @contextmanager
    def lock(*a):yield
    @contextmanager
    def coordinator(*a):yield dict(pid=1)
    def run(lease,prepared):
        assert not stop.exists();assert prepared[0]['lease']==lease;seen.append(prepared[1])
    with patch.object(op,'authority'),patch.object(op,'exclusive_lock',lock),patch.object(op,'coordinator',coordinator),patch.object(op,'workers',return_value=[]),patch.object(op,'alive',return_value=False),patch.object(op.batch,'check_ready'),patch.object(op,'run_wave',side_effect=run):
        op.watchdog()
    assert len(seen)==1 and len(seen[0]['ready'])==7

def test_preflight_global_error_keeps_actual_stop_intact(local):
    stop=op.OPS/'STOP_AUTONOMY.json';atomic(stop,dict(reason=op.preparation.HOLD,allow_preparation=True,authorization=record(op.preparation.AMENDMENT)))
    @contextmanager
    def lock(*a):yield
    @contextmanager
    def coordinator(*a):yield {}
    with patch.object(op,'authority'),patch.object(op,'exclusive_lock',lock),patch.object(op,'coordinator',coordinator),patch.object(op,'workers',return_value=[]),patch.object(op,'alive',return_value=False),patch.object(op.batch,'preflight',side_effect=PermissionError('global source drift')),pytest.raises(PermissionError):op.watchdog()
    assert stop.exists()

def test_all_seven_actual_dispatches_use_new_entry_and_one_failure_is_local(local):
    with patch.object(op.batch,'check_ready'):manifest=op.batch.preflight(local)
    calls=[]
    def launch(pointer,label):
        r=read(pointer);calls.append((r['day'],r['arm']))
        if len(calls)==3:raise OSError('injected launch failure')
        atomic(Path(r['case_root'])/'RESULT.json',dict(PASS=True,status='COMPLETE'))
        return SimpleNamespace(pid=100+len(calls),returncode=0,poll=lambda:0)
    @contextmanager
    def pool(*a):yield
    with patch.object(op,'attach',side_effect=lambda r:r),patch.object(op,'launch',side_effect=launch),patch.object(op.actual,'authorize'),patch.object(op.batch,'reserve_when_available',pool),patch.object(op.batch.inherited,'background_to_E'),patch.object(op.batch.time,'sleep'):
        op.run_wave({},(local,manifest))
    state=read(op.STATE)
    assert len(calls)==7 and sum(j['status']=='PASS' for j in state['jobs'])==6
    assert sum(j['status']=='ACTUAL_FAILED' for j in state['jobs'])==1
    assert state['phase']=='COMPLETE' and not state['all_PASS']
