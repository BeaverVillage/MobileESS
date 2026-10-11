"""Scheduler mechanics only; these fixtures are not scientific AC validation."""
import copy,json,tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from v42_svr11 import batch,resources
from v42_pr134_b1.common import atomic,sha

DAYS=batch.DAYS
MEM=dict(RAM_available=24*1024**3,Commit_available=32*1024**3,Commit_total=10*1024**3)

def terminal(state,stage,status='PASS'):
    for row in state['stages'][stage].values():row['status']=status

def test_m1_running_worker_prevents_a2_even_all_dates_terminal():
    state=batch.initial();terminal(state,'M1')
    assert batch.next_stage(state,[dict(PID=1)],MEM)=='M1'
    assert not state['barriers']

def test_m1_barrier_requires_ram_and_commit_return():
    state=batch.initial();terminal(state,'M1');state['last_active_memory']=MEM
    assert batch.next_stage(state,[],dict(MEM,RAM_available=MEM['RAM_available']-1))=='M1'
    assert batch.next_stage(state,[],dict(MEM,Commit_total=MEM['Commit_total']+1))=='M1'
    assert batch.next_stage(state,[],dict(MEM,RAM_available=MEM['RAM_available']+1,Commit_total=MEM['Commit_total']-1))=='A2'
    assert state['barriers'][0]['worker_processes_exited']

def test_a2_worker_prevents_m2():
    state=batch.initial();state['stage']='A2';terminal(state,'A2')
    assert batch.next_stage(state,[dict(PID=1)],MEM)=='A2'
    assert batch.next_stage(state,[],MEM)=='M2'

@pytest.mark.parametrize('stage,capacity',[('M1',3),('A2',1),('M2',3)])
def test_actual_dispatch_count_and_restart_dedup(stage,capacity,tmp_path):
    state=batch.initial();state['stage']=stage
    for prior in batch.ORDER[:batch.ORDER.index(stage)]:terminal(state,prior)
    ledger=dict(B3_batch=state,dates={'B3/'+d:dict(status='NOT_EXECUTED',attempts=[]) for d in DAYS})
    manifest=dict(run_id='FIXTURE',execution_SHA='a'*64,B3_memory_admission={})
    atomic(tmp_path/'CAMPAIGN_MANIFEST.json',manifest)
    spawned=[]
    def spawn(path,request):
        peer=dict(PID=100+len(spawned),b3_stage=stage,arm='B3',day=request['day'],worker_slot=request['worker_slot'])
        spawned.append(peer);return peer
    with patch.object(resources,'admits',return_value=True):
        peers=batch.tick(tmp_path,manifest,ledger,[],memory=MEM,spawn=spawn)
        assert len(peers)==len(spawned)==capacity
        batch.tick(tmp_path,manifest,ledger,peers,memory=MEM,spawn=spawn)
    assert len(spawned)==capacity
    assert len({r['day'] for r in spawned})==capacity

def test_dependency_failure_isolated_and_next_dates_not_blocked():
    state=batch.initial();terminal(state,'M1');state['stages']['M1'][DAYS[0]]['status']='FAIL'
    batch.dependencies(state,'A2')
    assert state['stages']['A2'][DAYS[0]]['status']=='DEPENDENCY_FAILED'
    assert state['stages']['A2'][DAYS[1]]['status']=='NOT_EXECUTED'

def test_reconcile_stage_failure_does_not_convert_into_success(tmp_path):
    state=batch.initial();row=state['stages']['M1'][DAYS[0]]
    request=tmp_path/'request.json';result=tmp_path/'RESULT.json'
    atomic(request,dict(result=str(result),source_SHA='a'*64))
    row.update(status='RUNNING',request=str(request))
    batch.reconcile(state,[])
    assert row['status']=='FAIL' and row['reason']=='B3_STAGE_WORKER_EXITED_WITHOUT_RESULT'
    assert state['stages']['M1'][DAYS[1]]['status']=='NOT_EXECUTED'

def test_different_stage_worker_is_global_overlap_error():
    with pytest.raises(PermissionError,match='STAGE_OVERLAP'):
        batch.reconcile(batch.initial(),[dict(day=DAYS[0],arm='B3',b3_stage='A2')])

def test_memory_admission_defers_new_worker():
    contract=dict(system_reserve_bytes=2*1024**3,worker_reservation_bytes=dict(M1=5*1024**3))
    assert not resources.admits(dict(MEM,RAM_available=6*1024**3),[],'M1',contract)
    assert not resources.admits(dict(MEM,Commit_available=6*1024**3),[],'M1',contract)
    assert resources.admits(MEM,[],'M1',contract)

def test_missing_scientific_validation_blocks_release(tmp_path):
    from v42_svr11.model_release import validate
    with pytest.raises(PermissionError,match='NOT_VALIDATED'):validate(tmp_path,{})

def test_stage_stop_resumes_verified_prefix_without_native_duplicate(tmp_path):
    from tests.test_v42_b3_source_coordinator import FixtureLedger,FixtureBridge
    from v42_b3_joint.dry_run import fixture_authority
    from v42_b3_joint.source_runtime import RealStageContext,FakeSourceRegistry
    from v42_b3_joint.source_coordinator import SourceCoordinator
    from v42_b3_joint.contracts import canonical
    bridge=FixtureBridge();authority=fixture_authority();registry=FakeSourceRegistry()
    grid=object()
    def factory(request,packets,path):return RealStageContext(request,tmp_path/'input',path,canonical({'day':authority.day}),registry,grid,packets,authority.source_sha,'FIXTURE')
    def coordinator():return SourceCoordinator(tmp_path/'output',factory,bridge,bridge,ledger_factory=FixtureLedger)
    assert coordinator().run(authority,stop_after='M1')['status']=='STAGE_COMPLETE'
    assert bridge.executions==['A1','M1']
    assert coordinator().run(authority,stop_after='A2')['status']=='STAGE_COMPLETE'
    assert bridge.executions==['A1','M1','A2']
    assert coordinator().run(authority,stop_after='M2')['status']=='STAGE_COMPLETE'
    assert bridge.executions==['A1','M1','A2','M2']
