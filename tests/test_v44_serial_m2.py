"""Single-case scheduling and M-only thread/guard scope; no Native calls."""
from types import SimpleNamespace
import pytest
from v44 import serial_m2,barrier,cap300
from v44.common import atomic,digest,read,record


@pytest.fixture
def permit(tmp_path):
    value=barrier.validate()
    value.update(serial_M_overlay=serial_m2.overlay(),serial_M_policy_sha=digest(serial_m2.overlay()))
    path=tmp_path/'PERMIT.json';atomic(path,value);return path


def test_scheduler_is_one_date_at_a_time_and_preserves_all_28_cases():
    states={};seen=[]
    while True:
        tasks=serial_m2.assignments(states,[])
        if not tasks:break
        assert len(tasks)==1 and tasks[0]['worker_slot']==1
        task=tasks[0];assert serial_m2.assignments(states,[task])==[]
        seen.append((task['day'],task['arm']));states[seen[-1]]='COMPLETE'
    assert seen[:7]==[(f'2025-05-{i:02d}','B2') for i in range(1,8)]
    assert seen[7:]==[(f'2025-05-{i:02d}',a) for i in range(1,8) for a in ('B0','B1','B3')]


@pytest.mark.parametrize('arm,stage',[('B2','M1'),('B3','M1'),('B3','M2')])
def test_m_parameters_and_original_sources_restore(arm,stage):
    from v44.frozen.v43_mess.library import load
    from v42_may_campaign_native90 import budget,execution
    modules=load();engine=modules['m_engine'];lower=modules['table_v_k48']
    before=(dict(engine.APPROVED_JOINT_PARAMETERS),dict(lower.ORIGINAL_NATIVE_PARAMETERS),budget.DateBudget.native_optimize,execution.guard)
    pins=[record(engine.__file__),record(lower.__file__),record(budget.__file__),record(execution.__file__)]
    with serial_m2.m_threads(dict(arm=arm,stage=stage,day='2025-05-02',Threads=2,worker_slot=1)) as selected:
        assert selected['Joint']['Threads']==selected['K48']['Threads']==2
        assert selected['Joint']['Method']==selected['K48']['Method']==2
        assert selected['Joint']['MIPGap']==.03
        assert budget.DateBudget.native_optimize is not before[2]
        assert execution.guard is not before[3]
        assert [record(p['path']) for p in pins]==pins
    assert (engine.APPROVED_JOINT_PARAMETERS,lower.ORIGINAL_NATIVE_PARAMETERS,budget.DateBudget.native_optimize,execution.guard)==before


@pytest.mark.parametrize('arm,stage,threads,slot',[('B1','A1',2,1),('B3','A2',2,1),('B2','M1',1,1),('B2','M1',2,2)])
def test_other_scope_cannot_acquire_two_thread_authority(arm,stage,threads,slot):
    with pytest.raises(PermissionError):
        with serial_m2.m_threads(dict(arm=arm,stage=stage,day='2025-05-01',Threads=threads,worker_slot=slot)):pass


def test_stage_request_and_source_policy(permit):
    from v44 import campaign
    case=dict(day='2025-05-02',arm='B3',worker_slot=1,case_root='D:/test_only')
    original=campaign.stage_request
    with serial_m2.install(permit):
        assert campaign.stage_request(case,'M1')['Threads']==2
        assert campaign.stage_request(case,'M2')['Threads']==2
        assert campaign.stage_request(case,'A2')['Threads']==1
        assert campaign.stage_request(case,'ACTUAL')['Threads']==1
    assert campaign.stage_request is original
    value=read(permit);value['serial_M_overlay']['Workers']=2
    value['serial_M_policy_sha']=digest(value['serial_M_overlay']);atomic(permit,value)
    with pytest.raises(PermissionError):serial_m2.validate(permit)
