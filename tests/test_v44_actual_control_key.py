"""First-key reduction must retain native and end-of-slot drift detection."""
from types import SimpleNamespace
import pytest
from v44_actual_control_key import build,from_controls
from v44_recovery_r029 import history


@pytest.fixture
def guarded_native(monkeypatch):
    from v44.svr12 import scope as hardware_scope
    import v44.svr11_ac as ac
    with hardware_scope():
        import v42_voltage_control.integration as integration
        engine=SimpleNamespace(phase=0,setting=120,rating=100,mutate_controls=False,mutate_ratings=False)
        audit=object()
        oracle=SimpleNamespace(hardware_record={'sha':'h'},scenario={'scenario_SHA':'s'},
            hardware={'source_SHA':'source'},mess_sha='m',sites=['A'],_scenario_audit=audit)
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
        yield oracle,engine,ac,build()


@pytest.mark.parametrize('mutate,exception',[
    ('mutate_controls','FINAL_LIVE_CONTROL_CERTIFICATE_DRIFT'),
    ('mutate_ratings','FINAL_LIVE_RATING_CERTIFICATE_DRIFT'),
])
def test_final_live_drift_still_rejected(guarded_native,mutate,exception):
    o,e,ac,scope=guarded_native;rows=[{'P':1},{'P':2}]
    with scope(o,rows):ac.SVR11CurrentAC._settle(o,e,0)
    e.phase=0;setattr(e,mutate,True)
    with pytest.raises(ValueError,match=exception):
        with scope(o,rows):ac.SVR11CurrentAC._settle(o,e,0)


def test_current_and_fresh_remain_original(guarded_native):
    o,e,ac,scope=guarded_native
    with scope(o,[{'P':1},{'P':2}]) as stats:
        assert ac.SVR11CurrentAC._settle(o,e,1)=='original-solve-result'
        o._independent_fresh=True;e.phase=0
        assert ac.SVR11CurrentAC._settle(o,e,0)=='original-solve-result'
        assert stats['historical_slots']==stats['reused_control_calls']==0
    assert not hasattr(o,'_r034_control_key_counts')


def test_unknown_schema_uses_complete_original_reader(guarded_native):
    o,e,_,_=guarded_native
    assert from_controls(o,e,{})==history.native_stamp(o,e)
    assert o._r034_control_key_counts==dict(live_inventory_rereads_elided=0,fallbacks=1)


def test_exception_restores_hooks(guarded_native):
    o,e,ac,scope=guarded_native;original=ac.SVR11CurrentAC._settle
    with pytest.raises(RuntimeError):
        with scope(o,[{'P':1},{'P':2}]):raise RuntimeError('abort')
    assert ac.SVR11CurrentAC._settle is original
