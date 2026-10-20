import copy,json,pickle
from types import SimpleNamespace
import pytest
from v44_recovery_r022.immutable import freeze,FrozenDict,FrozenList
from v44_recovery_r022.history import HistoryProofs,prefix_keys,physical_copy,scope


def test_immutable_graph_aliases_and_JSON_bytes_and_copy_share():
    child={'x':[1.,-0.,True,None]};value={'a':child,'b':child}
    frozen=freeze(value)
    assert json.dumps(frozen,sort_keys=True)==json.dumps(value,sort_keys=True)
    assert frozen['a'] is frozen['b']
    assert copy.deepcopy(frozen) is frozen
    assert pickle.loads(pickle.dumps(frozen))==value
    child['x'].append(9)
    assert len(frozen['a']['x'])==4
    with pytest.raises(TypeError):frozen['a']['x'].append(2)
    with pytest.raises(TypeError):frozen['a']['x'][0]=2
    with pytest.raises(TypeError):frozen.update(x=1)
    with pytest.raises(TypeError):frozen['a']|={'q':1}


def test_freeze_cycles_and_unknown_types():
    value=[];value.append(value);frozen=freeze(value)
    assert frozen[0] is frozen
    with pytest.raises(TypeError):freeze({'x':object()})
    with pytest.raises(TypeError):freeze({1:'key'})


def test_proof_store_exact_keys_and_bounded_memory():
    store=HistoryProofs(max_slots=2,max_bytes=10000)
    first=store.put('a',b'1',{'tap':1.})
    assert store.get('a',b'1') is first
    assert store.get('a',b'2') is None
    store.put('b',b'1',{'tap':2.});store.put('c',b'1',{'tap':3.})
    assert store.get('a',b'1') is None and len(store.slots)==2
    tiny=HistoryProofs(max_bytes=1)
    tiny.put('a',b'1',{'x':'large'})
    assert not tiny.slots and tiny.bytes==0


def test_same_native_stamp_cannot_hide_a_changed_control_setting():
    proofs=HistoryProofs();proofs.put('prefix',b'native',{'Vreg':'120'})
    with pytest.raises(ValueError,match='CONTROL_CERTIFICATE_DRIFT'):
        proofs.put('prefix',b'native',{'Vreg':'126'})


def test_prefix_identity_ignores_only_current_candidate_and_invalidates_changed_past():
    engine=SimpleNamespace(hardware_record={'sha':'h'},scenario={'scenario_SHA':'s'},hardware={'source_SHA':'source'},mess_sha='m',sites=['A'])
    rows=[{'P':[1.]},{'P':[2.]},{'P':[3.]}]
    original=prefix_keys(engine,rows)
    assert prefix_keys(engine,[*rows[:-1],{'P':[4.]}])[:-1]==original[:-1]
    changed=prefix_keys(engine,[rows[0],{'P':[2.5]},rows[2]])
    assert changed[0]==original[0] and changed[1:]!=original[1:]
    engine.mess_sha='other'
    assert prefix_keys(engine,rows)[0]!=original[0]


def test_physical_copy_freezes_only_physics_graphs():
    original={'nodes':[],'currents':[],'transformers':[]}
    value=physical_copy(original)
    assert type(value) is FrozenDict and physical_copy(value) is value
    other={'x':[]};copied=physical_copy(other)
    assert type(copied) is dict and copied['x'] is not other['x']


def test_independent_fresh_bypasses_all_hooks():
    oracle=SimpleNamespace(_independent_fresh=True)
    with scope(oracle,[]) as result:
        assert result=={'bypassed_independent_Fresh':True}
    assert not hasattr(oracle,'_prefix_history_proofs')


@pytest.fixture
def guarded_native(monkeypatch):
    from v44.svr12 import scope as hardware_scope
    import v44.svr11_ac as ac
    import v44_recovery_r022.history as history
    with hardware_scope():
        import v42_voltage_control.integration as integration
        engine=SimpleNamespace(phase=0,setting=120,rating=100,mutate_controls=False,mutate_ratings=False)
        audit=object()
        oracle=SimpleNamespace(hardware_record={'sha':'h'},scenario={'scenario_SHA':'s'},hardware={'source_SHA':'source'},mess_sha='m',sites=['A'],_scenario_audit=audit)
        def controls(e,scenario,authority=None):return {'setting':e.setting,'phase':e.phase}
        def ratings(owner,e):return {'rating':e.rating}
        def settle(owner,e,slot):
            integration._controls(e,owner.scenario)
            e.phase=1
            for _ in range(3):integration._controls(e,owner.scenario)
            for _ in range(3):integration.PhysicalScenario._ratings(audit,e)
            if e.mutate_controls:e.setting+=1
            if e.mutate_ratings:e.rating+=1
            return 'original-solve-result'
        monkeypatch.setattr(integration,'_controls',controls)
        monkeypatch.setattr(integration.PhysicalScenario,'_ratings',ratings)
        monkeypatch.setattr(ac.SVR11CurrentAC,'_settle',settle)
        monkeypatch.setattr(history,'native_stamp',lambda owner,e:bytes([e.phase]))
        yield oracle,engine,ac


def test_changed_settings_at_slot_end_reject_cached_proof(guarded_native):
    oracle,engine,ac=guarded_native;rows=[{'P':1},{'P':2}]
    with scope(oracle,rows):assert ac.SVR11CurrentAC._settle(oracle,engine,0)=='original-solve-result'
    engine.phase=0;engine.mutate_controls=True
    with pytest.raises(ValueError,match='FINAL_LIVE_CONTROL_CERTIFICATE_DRIFT'):
        with scope(oracle,rows):ac.SVR11CurrentAC._settle(oracle,engine,0)


def test_changed_ratings_at_slot_end_reject_cached_proof(guarded_native):
    oracle,engine,ac=guarded_native;rows=[{'P':1},{'P':2}]
    engine.mutate_ratings=True
    with pytest.raises(ValueError,match='FINAL_LIVE_RATING_CERTIFICATE_DRIFT'):
        with scope(oracle,rows):ac.SVR11CurrentAC._settle(oracle,engine,0)


def test_current_candidate_and_nested_fresh_take_original_path(guarded_native):
    oracle,engine,ac=guarded_native;rows=[{'P':1},{'P':2}]
    with scope(oracle,rows) as stats:
        assert ac.SVR11CurrentAC._settle(oracle,engine,1)=='original-solve-result'
        oracle._independent_fresh=True;engine.phase=0
        assert ac.SVR11CurrentAC._settle(oracle,engine,0)=='original-solve-result'
        assert stats['historical_slots']==stats['reused_control_calls']==0


def test_low_cost_slots_take_original_path_and_exception_restores_hooks(guarded_native):
    oracle,engine,ac=guarded_native;rows=[{'P':1},{'P':2}]
    original=ac.SVR11CurrentAC._settle
    proofs=oracle._prefix_history_proofs=HistoryProofs()
    proofs.costs[prefix_keys(oracle,rows)[0]]=3
    with pytest.raises(RuntimeError,match='caller failed'):
        with scope(oracle,rows) as stats:
            assert ac.SVR11CurrentAC._settle(oracle,engine,0)=='original-solve-result'
            assert stats['historical_low_cost_bypasses']==1 and stats['historical_slots']==0
            raise RuntimeError('caller failed')
    assert ac.SVR11CurrentAC._settle is original


def test_nested_fresh_also_bypasses_immutable_copy_hook(guarded_native):
    oracle,engine,ac=guarded_native
    graph={'nodes':[],'currents':[],'transformers':[]}
    original=ac.deepcopy
    with scope(oracle,[{'P':1}]) as stats:
        assert isinstance(ac.deepcopy(graph),FrozenDict)
        oracle._independent_fresh=True
        copied=ac.deepcopy(graph)
        assert type(copied) is dict and copied is not graph
    assert ac.deepcopy is original


def test_arm_and_clock_identity_invalidate_history_proofs(guarded_native):
    oracle,_,_=guarded_native;rows=[{'P':1}]
    before=prefix_keys(oracle,rows)
    for key,value in [('arm','B3'),('day_start',900),('issue',0)]:
        setattr(oracle,key,value)
        after=prefix_keys(oracle,rows)
        assert before!=after
        before=after


def test_native_stamp_distinguishes_voltage_queue_tap_and_counter_changes(monkeypatch):
    from v44_recovery_r022.history import native_stamp
    state={'queue':[],'taps':[1.],'physical_seconds':0}
    values=[1.,0.];counter=[1]
    names=('ControlActionsDone','Converged','ControlIterations','Iterations','TotalIterations',
        'MostIterationsDone','MaxControlIterations','MaxIterations','ControlMode')
    engine=SimpleNamespace(Circuit=SimpleNamespace(AllBusVolts=lambda:values),
        Solution=SimpleNamespace(**{name:lambda:counter[0] for name in names}))
    oracle=SimpleNamespace(_state=lambda engine:state)
    before=native_stamp(oracle,engine)
    for mutate in (lambda:values.__setitem__(0,1.0000000000000002),
        lambda:state['queue'].append({'hour':1}),lambda:state['taps'].__setitem__(0,1.00625),
        lambda:counter.__setitem__(0,2)):
        mutate();after=native_stamp(oracle,engine)
        assert before!=after
        before=after
