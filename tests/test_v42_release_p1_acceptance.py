from copy import deepcopy
from contextlib import contextmanager
import inspect

import pytest

from v42_integration.a_engine import digest
from v42_integration.release_p1_acceptance import (
    accept_a,accept_m,require_acceptance,prohibit_p2,saved_a1)
from v42_integration.release_p1_production import (
    production_backend,StageSolveBridge,require_production_acceptance,OriginalP1Stages)

IDENTITY={k:(str(i)*64) for i,k in enumerate(
    ('science_sha','case_sha','initial_state_sha','cc4_sha','runtime_sha'),1)}


def a_fixture(stage='A1',mess_anchor='initial',case='a1'):
    full=dict(PASS=True,FULL_max_residual=3e-12,point_sha256='point',rows=3,columns=2)
    r=dict(stage=stage,case_sha=case,source_identity=IDENTITY,D0_input_sha='input',
        input_MESS_anchor=mess_anchor,FULL_feasible=True,FULL_point_replay=full,P2_calls=0,
        objective=.64,bound=.64,gap=0.,selected_jobs={'j':{'start':24}},
        AIDC_P_by_site={'AIDC01':[1.]},AIDC_Q_by_site={'AIDC01':[.2]},
        CC4_service={},CC4_carryout={},anonymous_resource_envelope=[])
    r['aidc_anchor']=digest({k:r[k] for k in ('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site',
        'CC4_service','CC4_carryout','anonymous_resource_envelope')})
    kw=dict(stage=stage,stage_case_sha=case,source_identity=IDENTITY,source_sha='source',
        input_sha='input',input_mess_anchor=mess_anchor,native_binding=dict(objective_sense=1,rows=3,columns=2),
        point_sha='point',original_full=full,evidence_scope='NAMED_FIXTURE')
    return r,kw


def m_fixture(parent_result,parent_receipt,stage='M1',case='m1'):
    plan=dict(routes={'u':[0]},P_by_site={'s':[0]},Q_by_site={'s':[0]},SOC={'u':[1,1]},Mode={'u':[0]},case_sha=case)
    plan['plan_sha']=digest(plan)
    r=dict(stage=stage,case_sha=case,FULL_validated=True,mess=plan,P2_calls=0,
        D0_source_identity=IDENTITY,D0_fixed_AIDC_anchor=parent_receipt['AIDC_anchor'],
        binding=dict(aidc_anchor=parent_receipt['AIDC_anchor']))
    cert=dict(PASS=True,original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha=case),
        strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True)
    receipt=accept_m(r,stage=stage,source_identity=IDENTITY,source_sha='source',parent_a=parent_receipt,
        parent_result=parent_result,stage_case_sha=case,full_certificate=cert)
    return r,receipt


def test_fixture_four_stage_p1_only_handoff_preserves_parent_anchor():
    a1,kw=a_fixture();ra1=accept_a(a1,**kw)
    m1,rm1=m_fixture(a1,ra1)
    a2,kw=a_fixture('A2',rm1['MESS_anchor'],'a2')
    ra2=accept_a(a2,parent_acceptance=rm1,**kw)
    m2,rm2=m_fixture(a2,ra2,'M2','m2')
    assert rm2['parent_acceptance_sha']==ra2['acceptance_sha']
    assert ra2['parent_acceptance_sha']==rm1['acceptance_sha']
    assert rm1['parent_acceptance_sha']==ra1['acceptance_sha']
    assert all(r['P2_calls']==0 and not r['P2_optimized'] for r in (ra1,rm1,ra2,rm2))
    assert rm2['K48_Global_LB'] is None
    assert not ra1['whole_original_unpriced_domain_global_optimality']


@pytest.mark.parametrize('field,value',[('P2_calls',1),('P2','EXECUTED'),('P2_contract_certified',True),('P2_certified',True)])
def test_p2_result_or_fabricated_certificate_rejected(field,value):
    r,kw=a_fixture();r[field]=value
    with pytest.raises(ValueError,match='P2_ABSOLUTELY_FORBIDDEN'):accept_a(r,**kw)


def test_p2_native_trace_cannot_hide_behind_zero_top_counter():
    with pytest.raises(ValueError,match='P2_ABSOLUTELY_FORBIDDEN'):
        prohibit_p2(dict(P2_calls=0,lexicographic_trace=[dict(group='P2',Native_call={'Runtime':1})]))


@pytest.mark.parametrize('field,value',[
    ('source_identity',dict(science_sha='wrong')),('D0_input_sha','wrong'),
    ('case_sha','wrong'),('input_MESS_anchor','wrong'),('FULL_feasible',False),
    ('stage','A2')])
def test_source_case_stage_anchor_or_full_failure_blocks_a(field,value):
    r,kw=a_fixture();r[field]=value
    with pytest.raises(ValueError,match='FULL_P1_SOURCE_POINT_DOMAIN'):accept_a(r,**kw)


def test_integer_or_original_row_residual_not_replaced_by_native_gap_zero():
    r,kw=a_fixture();kw['original_full']=dict(kw['original_full'],FULL_max_residual=1e-3)
    with pytest.raises(ValueError,match='ORIGINAL_FULL'):accept_a(r,**kw)


def test_bound_scope_never_becomes_unpriced_global_even_native_gap_zero():
    r,kw=a_fixture();receipt=accept_a(r,**kw)
    assert receipt['native_matrix_target_met']
    assert not receipt['whole_original_unpriced_domain_global_optimality']
    assert receipt['AIDC_MESS_joint_Global_LB'] is None
    assert not receipt['minimum_control_timeshift_migration_cost_claimed']


def test_feasible_but_unclosed_numeric_target_stays_explicit():
    r,kw=a_fixture();r['gap']=.2;r['bound']=.5
    receipt=accept_a(r,**kw)
    assert receipt['status']=='FULL_PASS'
    assert receipt['optimality_status']=='OPTIMALITY_TARGET_UNMET'
    assert not receipt['native_matrix_target_met']


def test_a2_requires_current_m1_complete_anchor():
    r,kw=a_fixture('A2','new_mess','a2')
    with pytest.raises(ValueError,match='ACCEPTANCE_REQUIRED'):accept_a(r,**kw)


def test_mutated_parent_result_or_resealed_wrong_stage_rejected():
    r,kw=a_fixture();receipt=accept_a(r,**kw);r['CC4_service']={'new':1}
    with pytest.raises(ValueError,match='ACCEPTANCE_REQUIRED'):require_acceptance(receipt,result=r)
    with pytest.raises(ValueError,match='ACCEPTANCE_REQUIRED'):require_acceptance(receipt,stage='M1')


def test_fixture_cannot_be_promoted_to_production():
    r,kw=a_fixture();receipt=accept_a(r,**kw)
    with pytest.raises(ValueError,match='FIXTURE_RESULT_FORBIDDEN'):
        require_production_acceptance(receipt,stage='A1',identity=IDENTITY,result=r)
    with pytest.raises(ValueError,match='DUMMY_EXECUTOR_FORBIDDEN'):production_backend('DUMMY')
    with pytest.raises(ValueError,match='REAL_BUDGET_REQUIRED'):
        OriginalP1Stages({},BudgetFixture())


def test_source_uses_original_a_builder_single_solve_and_no_lex_solver():
    text=inspect.getsource(OriginalP1Stages._execute_a)
    assert "dict(built[2])['rho']" in text
    assert 'solve_d0_native_model' not in text
    assert 'passes(' not in text
    assert text.count('.solve(')==1
    assert '.optimize(' not in text


def test_may01_successful_a1_cannot_be_optimized_twice():
    instance=object.__new__(OriginalP1Stages);instance.day='2025-05-01'
    with pytest.raises(ValueError,match='ALREADY_EXECUTED_IMPORT_SAVED'):
        instance.execute_a1(None,build_admission={},cap=120.)


def test_date_a1_reads_bound_case_anchor_and_explicit_phase_day():
    source=inspect.getsource(OriginalP1Stages._execute_a)
    assert "self.context['initial_mess']" not in source
    assert "case.grid.fixed_mess['plan_sha']" in source
    assert 'day=self.day' in source


class BudgetFixture:
    def __init__(self):self.calls=[];self.cost_calls=[]
    def solve(self,model,**kw):self.calls.append(kw);return kw
    def remaining(self,reserve=0):return 10.-reserve
    def used(self):return 0.
    def record_external(self,*a,**kw):self.calls.append((a,kw))


def test_stage_budget_prefix_and_no_unbudgeted_optimize():
    budget=BudgetFixture();bridge=StageSolveBridge(budget,'M1')
    row=bridge.native_optimize(object(),track='M_START',label='INITIALIZE',requested_seconds=3.)
    assert row['label']=='RELEASE_P1:M1:M_START:INITIALIZE'
    with pytest.raises(ValueError,match='P2_ABSOLUTELY_FORBIDDEN'):
        bridge.solve(object(),label='P2_reserve',cap=3.)
    assert len(budget.calls)==1


def test_m_build_wall_nested_not_added_to_native_or_score_budget():
    budget=BudgetFixture();bridge=StageSolveBridge(budget,'M2')
    with bridge.cost('model_build','COLD_INITIALIZER'):pass
    assert not budget.calls
    assert bridge.build_costs[0]['labels']==['model_build','COLD_INITIALIZER']
    assert bridge.build_costs[0]['nested_in_stage_wall']
    assert not bridge.build_costs[0]['charged_as_native_or_score_seconds']
    bridge.record_external('M_PR222_SCORE_ONLY',.02,solver='HIGHS')
    assert budget.calls[0][0][0]=='RELEASE_P1:M2:M_PR222_SCORE_ONLY'


def test_saved_real_a1_accepted_without_p2_and_without_new_native():
    saved=saved_a1();r=saved['result'];receipt=saved['acceptance']
    assert receipt['evidence_scope']=='REAL_PRODUCTION'
    assert r['stage']=='A1' and r['P2_calls']==0
    assert receipt['native_matrix_objective']==pytest.approx(.64211779208034)
    assert receipt['Original_FULL']['FULL_max_residual']<1e-10
    assert receipt['native_matrix_gap']==0.
    assert not receipt['original_unrestricted_migration_pricing_certificate']
