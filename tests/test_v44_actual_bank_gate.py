from copy import deepcopy
from types import SimpleNamespace
import pytest
from v44_actual_bank_gate import build
from v44_recovery_r029.current_ac_performance import bank_reader


def fixture(factory):
    state = dict(taps=[1.], caps=[1], queue=[], physical_seconds=0)
    volts = [1.,0.]
    inputs = {'load':[1.,0.]}
    calls = dict(state=0, measure=0)
    def read_state(engine):
        calls['state'] += 1
        return deepcopy(state)
    def measure(bank):
        calls['measure'] += 1
        return deepcopy(dict(state=state,volts=volts,inputs=inputs))
    engine = SimpleNamespace(Solution=SimpleNamespace(Hour=lambda:int(state['physical_seconds']//3600),
        Seconds=lambda:state['physical_seconds']%3600),Circuit=SimpleNamespace(AllBusVolts=lambda:volts))
    audit = SimpleNamespace(rows=[])
    bank = SimpleNamespace(engine=engine)
    oracle = SimpleNamespace(arm='B3',_bank=bank,_scenario_audit=audit,_state=read_state)
    return factory(measure,oracle),bank,oracle,audit,state,volts,inputs,calls


@pytest.fixture
def physical_inputs(monkeypatch):
    from v44.svr12 import scope
    with scope():
        import v42_voltage_control.integration as integration
        yield integration


def exercise(factory, integration, mutation=None):
    f,bank,o,a,state,volts,inputs,calls = fixture(factory)
    outputs=[]
    original=integration._physical_inputs
    integration._physical_inputs=lambda engine:deepcopy(inputs)
    try:
        for slot in range(4):
            state['physical_seconds']=(slot+1)*900
            outputs.append(f(bank))
            a.rows.append({})
            if mutation is not None:mutation(state,volts,inputs)
            outputs.append(f(bank))
        return outputs,calls,getattr(o,'_r029_duplicate_bank_reuses',0),getattr(o,'_r034_bank_gate_counts',{})
    finally:
        integration._physical_inputs=original


def test_clock_mismatch_skips_only_unused_full_cache_keys(physical_inputs):
    old=exercise(bank_reader,physical_inputs)
    new=exercise(build(),physical_inputs)
    assert old[0]==new[0]
    assert old[1]['measure']==new[1]['measure']==4
    assert old[2]==new[2]==4
    assert new[1]['state']<old[1]['state']
    assert new[3]['clock_mismatch']==3


@pytest.mark.parametrize('mutation',[
    lambda s,v,i:s['taps'].__setitem__(0,s['taps'][0]+.00625),
    lambda s,v,i:s['caps'].__setitem__(0,1-s['caps'][0]),
    lambda s,v,i:s['queue'].append({'hour':1}),
    lambda s,v,i:v.__setitem__(0,v[0]+1e-12),
    lambda s,v,i:i['load'].__setitem__(0,i['load'][0]+1),
])
def test_immediate_same_clock_changes_still_invalidate_full_cache(physical_inputs,mutation):
    old=exercise(bank_reader,physical_inputs,mutation)
    new=exercise(build(),physical_inputs,mutation)
    assert old[0]==new[0]
    assert old[1]['measure']==new[1]['measure']==8
    assert old[2]==new[2]==0


def test_non_matching_bank_bypasses_gate(physical_inputs):
    f,bank,oracle,a,s,v,i,calls=fixture(build())
    other=SimpleNamespace(engine=bank.engine)
    assert f(other)['state']==s
    assert not hasattr(oracle,'_r034_bank_gate_counts')
