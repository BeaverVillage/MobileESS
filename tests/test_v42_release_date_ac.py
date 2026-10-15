"""Static and named clock-stop fixtures; no real engine/AC solve is entered."""
from collections import OrderedDict
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from types import ModuleType,SimpleNamespace
import sys

import pytest

from v42_integration import release_date_ac as api
from v42_integration import rc02_prefix_cache as prefix
from v42_integration.m_engine import file_record


def test_static_original_methods_change_exactly_one_clock_argument_each():
    proof=api.date_ac_static_equivalence()
    assert proof['status']=='PASS_STATIC_CLOCK_DAY_ONLY'
    assert len(proof['methods'])==2 and all(r['changed_expressions']==1 for r in proof['methods'])
    assert not proof['runtime_source_execution'] and not proof['global_or_original_method_patch']
    assert proof['Native_calls']==proof['AC_calls']==0


def test_research_and_prefix_MRO_preserves_original_scoring_and_cache():
    assert api.DateResearchCurrentAC.predicted_score is api.ResearchCurrentAC.predicted_score
    assert api.DateResearchCurrentAC._probe is prefix.PrefixCachedCurrentAC._probe
    assert api.DateResearchCurrentAC._replay_current is api.DatePrefixCachedCurrentAC._replay_current
    mro=api.DateResearchCurrentAC.__mro__
    assert mro.index(prefix.PrefixCachedCurrentAC)<mro.index(api.DateCurrentAC)<mro.index(api.CurrentACAdmission)


class ClockReached(Exception):pass


def clock_fixture(monkeypatch,day):
    from v42_regcontrol import authority
    import v42_regcontrol.runner as runner
    import v42_voltage_control.timecontrol as timecontrol
    import v42_voltage_control.svr as svr
    import v42_voltage_control.integration as integration
    seen=[];cleared=[]
    engine=SimpleNamespace(Circuit=SimpleNamespace(AllNodeNames=lambda:['N.1']),
        Basic=SimpleNamespace(ClearAll=lambda:cleared.append(True)))
    native=SimpleNamespace(validate_native_engine=lambda engine:None)
    allocation=SimpleNamespace(from_adapter=lambda adapter:native)
    monkeypatch.setattr(authority,'source',lambda:dict(NativeAllocation=allocation))
    monkeypatch.setattr(authority,'compile_verified',lambda:(engine,{},{}))
    monkeypatch.setattr(runner,'background',lambda *args:SimpleNamespace())
    monkeypatch.setattr(integration,'_equipment',lambda engine:{})
    monkeypatch.setattr(svr,'install',lambda *args:None)
    class Clock:
        def __init__(self,namespace,clockday):seen.append((namespace,clockday))
        def bind(self,engine):raise ClockReached('BEFORE_ANY_REAL_AC_OR_SOLVE')
    monkeypatch.setattr(timecontrol,'CommonClock',Clock)
    mapping=ModuleType('dayahead.v28r2.opendss_mapping')
    mapping._set_generator=mapping._set_load=mapping.mess_injection_mapping=lambda *args:None
    monkeypatch.setitem(sys.modules,'dayahead.v28r2.opendss_mapping',mapping)
    instance=object.__new__(api.DateResearchCurrentAC)
    instance.begin=datetime.fromisoformat(day).replace(tzinfo=api.AEST).timestamp()
    instance._background_cache=OrderedDict()
    @contextmanager
    def hardware():yield dict(svr={})
    instance._hardware_context=hardware
    current=dict(slot=0,observations=dict(demand=dict(values=dict(demand_mw=1.)),pv=dict(values=dict(pv_mw=0.))))
    return instance,current,seen,cleared


@pytest.mark.parametrize('day',['2025-05-01','2025-05-02','2025-05-10','2025-05-12','2025-05-31'])
@pytest.mark.parametrize('method',[api.DateCurrentAC._probe,api.DatePrefixCachedCurrentAC._replay_current])
def test_date_reaches_original_clock_with_correct_AEST_day_before_solve(monkeypatch,day,method):
    instance,current,seen,cleared=clock_fixture(monkeypatch,day)
    with pytest.raises(ClockReached,match='BEFORE_ANY_REAL_AC'):
        method(instance,[],current)
    assert seen==[('ACTUAL',day)] and cleared==[True]


def test_prefix_conditional_super_dispatches_to_date_probe_and_preserves_cache(tmp_path,monkeypatch):
    source=tmp_path/'NAMED_SOURCE_ONLY';source.write_text('SOURCE')
    oracle=api.DateResearchCurrentAC(begin=1746108000.,sites=['A'],power_model=None,observations=None,
        source_freeze=dict(source_sha='s'),mess=dict(plan_sha='m'),proof_records=[file_record(source)])
    assert file_record(api.__file__) in oracle.prefix_proofs.material
    monkeypatch.setattr(prefix,'memory_gate',lambda:None)
    calls=[]
    def date_probe(self,history,current,future_rows=None):
        calls.append('DATE_PROBE')
        return dict(PASS=False,physical_steps=[dict(PASS=False)],status='NAMED_PHYSICAL_FAIL')
    monkeypatch.setattr(api.DateCurrentAC,'_probe',date_probe)
    current=dict(slot=0,observations=dict(current=True))
    first=oracle._probe([],current,future_rows=[current])
    second=oracle._probe([],current,future_rows=[current])
    assert calls==['DATE_PROBE'] and first['PASS'] is False and second['PASS'] is False
    assert second['conditional_proof_cache_hit'] is True


def test_changed_date_and_clock_history_cannot_reuse_prefix_proof(tmp_path):
    source=tmp_path/'NAMED_SOURCE_ONLY';source.write_text('SOURCE')
    oracle=api.DateResearchCurrentAC(begin=1746108000.,sites=['A'],power_model=None,observations=None,
        source_freeze=dict(source_sha='s'),mess=dict(plan_sha='m'),proof_records=[file_record(source)])
    history=[dict(slot=0,start_seconds=oracle.begin,end_seconds=oracle.begin+900)]
    fields=dict(history=history,current_slot=1,current_observations=dict(asof_seconds=oracle.begin+900),
        source_sha='s',MESS_plan_sha='m')
    original=oracle.prefix_proofs.key(**fields)
    history[0].update(start_seconds=oracle.begin+86400,end_seconds=oracle.begin+87300)
    assert oracle.prefix_proofs.key(**fields)!=original
