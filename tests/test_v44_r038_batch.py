import inspect,json,sqlite3,sys,subprocess,os
from pathlib import Path
from unittest.mock import patch
import pytest
from v44.common import atomic,read,digest,record
from v44_recovery_r038 import cpu,phases,batch,operations as op

def topology():
    return [dict(group=0,core=2*c,logical=2*c+s,efficiency_class=1,flags=0) for c in range(6) for s in (0,1)]+[
        dict(group=0,core=i,logical=i,efficiency_class=0,flags=0) for i in range(12,16)]

def test_seven_workers_use_only_P_and_spread_physical_cores_before_SMT():
    plan=cpu.placement(topology())
    assert [r['logical'] for r in plan['slots']]==[0,2,4,6,8,10,1]
    assert len({r['core'] for r in plan['slots'][:6]})==6
    assert not plan['distinct_physical_cores'] and plan['E_core_workers']==0

def test_P_only_never_falls_back_to_E_when_capacity_is_insufficient():
    with pytest.raises(PermissionError,match='INSUFFICIENT_P'):cpu.placement(topology(),13)

def test_changed_topology_cannot_reuse_saved_affinity():
    with patch.object(cpu,'windows_cpu_sets',return_value=topology()[:-1]):
        altered=cpu.placement(topology());altered['slots'][0]['logical']=12
        with pytest.raises(PermissionError,match='TOPOLOGY_DRIFT'):cpu.validate_topology(altered)

@pytest.mark.parametrize('failed',['PENDING','PREPARING','PRE_FAILED','ACTUAL_RUNNING','PASS'])
def test_barrier_rejects_every_incomplete_preparation_state(failed):
    jobs=[dict(status='PREPARED') for _ in range(7)];jobs[3]['status']=failed
    assert not batch.all_prepared(jobs)

def test_barrier_only_accepts_all_ready_and_never_empty():
    assert batch.all_prepared([dict(status='PREPARED') for _ in range(7)])
    assert not batch.all_prepared([])

def test_preparation_boundary_changes_no_upstream_code():
    from v44 import campaign
    original=inspect.getsource(campaign.run_case)
    compiled=phases.compiled_prepare_case();source=inspect.getsource(compiled)
    expected=original.replace("result.update(stage_result(request,'ACTUAL',lambda r:worker.actual(dict(r,MESS_result=a['MESS_result']),folder,mess)))",
        "result.update(_r038_prepare_actual(dict(a,MESS_result=a['MESS_result']),folder,mess))").replace(
        "result['status']='COMPLETE' if result.get('PASS') else 'FAILED'","result['status']='PRE_ACTUAL_READY'")
    assert source==expected
    assert 'from .stages import require_a2' in source
    assert "if not m['allow_downstream']" in source
    assert compiled.__globals__ is campaign.run_case.__globals__

def make_handoff(tmp_path):
    folder=tmp_path/'case';folder.mkdir();atomic(folder/'START.json',dict(pid=2147483647,process_created=0))
    evidence=tmp_path/'plan.json';atomic(evidence,dict(plan=1))
    r=dict(day='2025-05-05',arm='B1',case_root=str(folder),source_sha='x',sources=[])
    v=dict(schema='V44_R038_PRE_ACTUAL_HANDOFF_V1',ready=True,**r,evidence=[record(evidence)],aidc_folder=str(tmp_path),MESS_result=None,MESS_plan=None)
    v['handoff_sha']=digest(v);p=folder/'PRE_ACTUAL_READY.json';atomic(p,v);r['R038_pre_actual_handoff']=record(p)
    return r,v,p,evidence

def test_same_case_handoff_checks_sources_and_plan_before_actual(tmp_path):
    r,v,p,e=make_handoff(tmp_path)
    with patch('v44.daily.load_aidc'):
        assert phases.load_handoff(r)['ready']
        e.write_text('changed')
        with pytest.raises(ValueError,match='SHA_DRIFT'):phases.load_handoff(r)

def test_handoff_cannot_change_day_or_scientific_case(tmp_path):
    r,v,p,e=make_handoff(tmp_path);r['day']='2025-05-06'
    with patch('v44.daily.load_aidc'):
        with pytest.raises(PermissionError,match='SAME_CASE'):phases.load_handoff(r)

def test_live_preparation_process_cannot_start_actual(tmp_path):
    r,v,p,e=make_handoff(tmp_path)
    with patch('v44.locks.alive',return_value=True):
        with pytest.raises(PermissionError,match='STILL_ALIVE'):phases.load_handoff(r)

def test_handoff_internal_sha_cannot_be_resealed_by_only_updating_outer_receipt(tmp_path):
    r,v,p,e=make_handoff(tmp_path);v['MESS_plan']={'changed':True};atomic(p,v);r['R038_pre_actual_handoff']=record(p)
    with pytest.raises(PermissionError,match='HANDOFF_SHA'):phases.load_handoff(r)

def test_actual_only_entry_never_calls_Planning_or_M_and_does_not_overwrite_start(tmp_path):
    from contextlib import contextmanager
    from v44 import worker,campaign
    r,v,p,e=make_handoff(tmp_path);r.update(parallel_actual_slot=7,lease={},campaign_root=str(tmp_path),r038_phase='ACTUAL_PARALLEL')
    start=(Path(r['case_root'])/'START.json').read_bytes()
    @contextmanager
    def lock(*a):yield {'logical':1}
    @contextmanager
    def scope(*a):yield
    with patch.object(cpu,'actual_slot',lock),patch.object(op,'authority',return_value={'cpu_placement':{}}),patch('v44.execution.case_scope',scope),patch.object(phases,'load_handoff',return_value=v),patch.object(campaign,'stage_request',return_value=dict(output=str(tmp_path/'actual'))),patch.object(worker,'actual',return_value={'PASS':True}) as actual,patch.object(worker,'a_stage',side_effect=AssertionError('Planning rerun')),patch.object(worker,'m_stage',side_effect=AssertionError('M rerun')):
        result=phases.actual_case(r)
    assert result['PASS'] and actual.call_count==1
    assert (Path(r['case_root'])/'START.json').read_bytes()==start

def test_actual_affinity_scope_rejects_E_or_other_worker_affinity():
    plan=cpu.placement(topology());r={'parallel_actual_slot':7}
    with patch.object(cpu.psutil,'Process') as process:
        process.return_value.cpu_affinity.return_value=[12]
        with pytest.raises(PermissionError,match='AFFINITY_DRIFT'):
            with cpu.compute_scope(r,1,None,plan):pass

def test_existing_actual_directory_is_never_overwritten(tmp_path):
    from contextlib import contextmanager
    r,v,p,e=make_handoff(tmp_path);r.update(parallel_actual_slot=1,lease={},campaign_root=str(tmp_path),r038_phase='ACTUAL_PARALLEL')
    actual=Path(r['case_root'])/'ACTUAL';actual.mkdir();sentinel=actual/'keep';sentinel.write_text('old')
    @contextmanager
    def lock(*a):yield {}
    @contextmanager
    def scope(*a):yield
    with patch.object(cpu,'actual_slot',lock),patch.object(op,'authority',return_value={'cpu_placement':{}}),patch('v44.execution.case_scope',scope),patch.object(phases,'load_handoff',return_value=v):
        result=phases.actual_case(r)
    assert not result['PASS'] and 'CANNOT_BE_RESTARTED' in result['error'] and sentinel.read_text()=='old'

def test_completed_PASS_is_never_replaced_by_a_failed_restart(tmp_path):
    r,v,p,e=make_handoff(tmp_path);r.update(parallel_actual_slot=1)
    result=Path(r['case_root'])/'RESULT.json';atomic(result,dict(PASS=True,status='COMPLETE'))
    before=result.read_bytes()
    with pytest.raises(PermissionError,match='COMPLETED_PASS'):phases.actual_case(r)
    assert result.read_bytes()==before

def test_seven_processes_can_concurrently_write_shared_chunks_without_collision(tmp_path):
    script="""import sys,json,os
from pathlib import Path
from v44_audit_chunk_store import ChunkStore
from v44_actual_record_light import SharedControlEncoding
s=ChunkStore(sys.argv[1]);i=int(sys.argv[2]);rows=[dict(slot=t,frozen_trajectory_SHA=str(i),v=[1.0]*100) for t in range(16)]
canonical=lambda v:json.dumps(v,sort_keys=True,separators=(',',':'))
p=Path(sys.argv[1])/str(i)/'SLOTS_MANIFEST.json';s.write(p,rows,SharedControlEncoding(),canonical)
assert s.restore(p)==(canonical(rows)+os.linesep).encode()
"""
    processes=[subprocess.Popen([sys.executable,'-c',script,str(tmp_path),str(i)],stdout=subprocess.PIPE,stderr=subprocess.PIPE) for i in range(7)]
    for p in processes:
        out,err=p.communicate(timeout=30);assert p.returncode==0,err.decode()
    assert len(list((tmp_path/'RAW_CHUNKS_V1').glob('*/*.z')))==16
