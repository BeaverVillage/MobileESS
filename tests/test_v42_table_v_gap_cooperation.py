from copy import deepcopy
from types import SimpleNamespace
import pytest
from v42_integration.a_engine import digest
from v42_integration import table_v_global_control as gc
from v42_integration import table_v_mess as mess

def scope():
    return dict(source_sha='source',case_sha='case',day='2025-05-01',arm='B2',stage='M1',matrix_sha='matrix',domain_sha='domain',objective_sha='objective')

@pytest.mark.parametrize('target_met',[True,False])
def test_production_cooperation_orders_seed_then_K_then_needed_search(tmp_path,monkeypatch,target_met):
    calls=[];factory=object.__new__(mess.TableVMessStages);factory.manifest=dict(identity={'case':'identity'})
    case=SimpleNamespace(output=tmp_path,case_sha='case');monkeypatch.setattr(gc,'mess_scope',lambda c:scope())
    monkeypatch.setattr(mess,'require_m_acceptance',lambda *a,**k:True)
    def execute(arm,stage,current,aidc,parent,**kwargs):
        assert current.output==tmp_path  # Original proof packet authority is fixed.
        seed=getattr(current,'global_gap_seed_checkpoint',False);calls.append('SEED' if seed else 'SEARCH')
        control=current.global_gap_control
        control.offer_upper(1. if seed else .99,dict(PASS=True,binding=scope(),original_FULL_replayed=True,integer_point=True,point_sha='point'))
        return dict(incumbent_registry=[],adaptive_search=dict(termination_reason='NATIVE_BUDGET_EXHAUSTED')),dict(schema='fixture',Original_FULL={}),'point'
    def k48(arm,stage,current,*args,**kwargs):
        calls.append('K16');current.global_gap_control.offer_lower(.98 if target_met else .5,'K16',dict(PASS=True,binding=scope(),original_FULL_relaxation_proved=True,native_bound_valid=True,K=16))
        return dict(Global_LB_valid=True)
    factory.execute=execute;factory.execute_k48=k48
    result,accepted,point,lower=factory.execute_cooperative('B2','M1',case,{}, {},k48_budget=object(),k48_admission=lambda:{})
    assert calls==(['SEED','K16'] if target_met else ['SEED','K16','SEARCH'])
    assert result['global_gap_certified'] is target_met
    assert result['termination_reason']==('GLOBAL_GAP_TARGET_MET' if target_met else 'NATIVE_BUDGET_EXHAUSTED')
    assert accepted['result_sha']==digest(result)
    assert 'global_gap_control' not in vars(case)

def test_K_failure_preserves_full_feasible_seed_and_stops_search(tmp_path,monkeypatch):
    calls=[];factory=object.__new__(mess.TableVMessStages);factory.manifest=dict(identity={})
    case=SimpleNamespace(output=tmp_path,case_sha='case');monkeypatch.setattr(gc,'mess_scope',lambda c:scope())
    monkeypatch.setattr(mess,'require_m_acceptance',lambda *a,**k:True)
    def execute(*args,**kwargs):calls.append('SEED');return dict(incumbent_registry=[]),dict(Original_FULL={}), 'point'
    def fail(*args,**kwargs):raise RuntimeError('RAM_OR_NUMERIC_FAILURE')
    factory.execute=execute;factory.execute_k48=fail
    result,accepted,point,lower=factory.execute_cooperative('B2','M1',case,{}, {},k48_budget=object(),k48_admission=lambda:{})
    assert calls==['SEED'] and accepted is not None
    assert result['termination_reason']=='IMPLEMENTATION_OR_NUMERICAL_FAILURE'
    assert result['certified_Global_LB'] is None
