from dataclasses import replace
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
import inspect
import numpy as np
import scipy.sparse as sp
import pytest
from v44.common import read
from v44_recovery_r024a.adaptive_pricing import AdaptivePricing,choose,valid_candidates,collect_targeted,compile_adaptive,classification_atomic


def attribution(count=138):
    return dict(target_classes=['c0','c1'],classes_ranked=[dict(class_id=f'c{i}',inactive_candidates_available=True) for i in range(count)])


def candidate(i,kind='STAY',price='-1',class_id=None,axis=0):
    return dict(class_id=class_id or f'c{i}',kind=kind,price=Fraction(price),identity=(i,),coefficient_sha256=str(i),
        coupling=((axis,'-1'),),residual_score=1.,native_local_replay=dict(PASS=True),
        physical_membership_PASS=True,exact_coupling_PASS=True,independent_price_PASS=True,option={})


def test_focus_does_not_exclude_rotation_when_negatives_exist(tmp_path):
    a=AdaptivePricing(tmp_path);first=a.plan_classes(attribution());second=a.plan_classes(attribution())
    assert len(first['target_class_ids'])>2 and {'c0','c1'}<=set(first['target_class_ids'])
    assert set(second['target_class_ids'])-set(first['target_class_ids'])
    assert not first['full_STAY_migration_option_pricing_closure']


def test_slow_actual_full_phi_expands_then_full_explores_with_cooldown(tmp_path):
    a=AdaptivePricing(tmp_path)
    a.feedback=[dict(relative_decrease=.05),dict(relative_decrease=.06)]
    assert a.plan_classes(attribution())['mode']=='EXPANDED'
    a.feedback.append(dict(relative_decrease=.03))
    full=a.plan_classes(attribution())
    assert full['complete_eligible_class_exploration'] and len(full['target_class_ids'])==138
    assert a.plan_classes(attribution())['mode']!='FULL_ELIGIBLE'


def test_coverage_cycle_does_not_starve_other_classes(tmp_path):
    a=AdaptivePricing(tmp_path)
    plans=[a.plan_classes(attribution()) for _ in range(5)]
    assert plans[-1]['complete_eligible_class_exploration'] and len(a.visited)==138


@pytest.mark.parametrize('key',['physical_membership_PASS','exact_coupling_PASS','independent_price_PASS'])
def test_unverified_candidate_is_never_admitted(key):
    c=candidate(0);c[key]=False
    with pytest.raises(ValueError,match='UNVERIFIED'):choose([c],(('GPU','IDC01',24),))


def test_nonnegative_or_unreplayed_candidates_are_never_admitted():
    with pytest.raises(ValueError,match='PRICE'):valid_candidates([candidate(0,price='0')],True)
    c=candidate(0);c['native_local_replay']['PASS']=False
    with pytest.raises(ValueError,match='REPLAY'):valid_candidates([c],True)


def test_selection_preserves_prices_mixed_kinds_and_multiple_classes():
    cs=[candidate(i,class_id='dominant') for i in range(70)]+[candidate(71,kind='MIGRATION',price='-1/1000',class_id='other',axis=1)]
    chosen,report=choose(cs,(('GPU','IDC01',24),('GPU','IDC02',75)),8)
    assert len(chosen)==8 and {c['kind'] for c in chosen}=={'STAY','MIGRATION'}
    assert len({c['class_id'] for c in chosen})==2
    assert all(c in cs for c in chosen) and not report['exact_prices_changed']
    assert len({(c['class_id'],c['coefficient_sha256']) for c in chosen})==8


def test_routed_targeted_and_worker_share_the_new_native_namespace():
    from v42_a_stage_canary import targeted
    from v42_may_campaign_native90.a_routing import group
    ns=group(targeted,('worker','targeted'),HISTORY=Path('fixture'))
    compiled=collect_targeted(ns['targeted'])
    assert compiled.__globals__['worker'].__globals__ is compiled.__globals__
    assert compiled.__globals__['HISTORY']==Path('fixture')


def test_production_profile_wrapper_preserves_routed_targeted_identity(tmp_path):
    from v42_a_stage_canary import targeted
    from v42_may_campaign_native90.a_routing import group
    from v44_recovery_r024a.phase_speed import Profile
    ns=group(targeted,('worker','targeted'),HISTORY=tmp_path)
    timed=Profile(tmp_path).wrap('targeted',ns['targeted'])
    assert inspect.unwrap(timed) is ns['targeted']
    compiled=collect_targeted(timed)
    assert compiled.__globals__['worker'].__globals__ is compiled.__globals__
    assert compiled.__globals__['HISTORY']==tmp_path


def test_original_p1_text_and_full_row_certificates_remain_verbatim():
    from v42_a_stage_canary import phase
    from v44_recovery_r024a.row_generation import compile_phase
    ns=dict(vars(phase));before=compile_phase(phase.run,ns)
    after=compile_adaptive(before,ns,AdaptivePricing(Path('fixture')))
    anchor='    # Original P1:'
    assert inspect.getsource(after).split(anchor)[1]==inspect.getsource(phase.run).split(anchor)[1]
    text=inspect.getsource(after)
    for expression in ['inclusion_witness','PREVIOUS_PHI_INCLUSION_NOT_PRESERVED','certified_separate(s,x,included)','rowgen.evaluate','rowgen.rebind']:assert expression in text


def test_no_candidate_is_not_a_mathematical_or_implementation_failure():
    saved=[];f=classification_atomic(lambda p,v:saved.append(dict(v)))
    result=dict(PASS=False,error="RuntimeError('R024A_FIXED_M1_FEASIBILITY_NOT_CERTIFIED_NO_RECOVERED_NEGATIVE_COLUMN')",classification='IMPLEMENTATION_FAILURE')
    f(None,result)
    assert result['classification']=='NOT_CERTIFIED' and not result['scientific_infeasibility_proven']
    unrelated=dict(PASS=False,error='OTHER_RAW_REPLAY_FAILURE',classification='IMPLEMENTATION_FAILURE');f(None,unrelated)
    assert unrelated['classification']=='IMPLEMENTATION_FAILURE'


def test_feedback_uses_full_phi_and_original_voltage_rows(tmp_path):
    from v42_a_stage_domain_v2.lexstage import LinearSnapshot,Objective
    from v42_a_stage_phase1.core import elastic_master,phase_objective
    from v42_a_stage_phase1.backend import artificial_point
    s=LinearSnapshot(sp.csr_matrix([[1.]]),np.zeros(1),np.ones(1),np.array(['>']),np.ones(1),np.array(['C']),(Objective('rho',(),0),)).require()
    master=elastic_master(s,(0,));a=AdaptivePricing(tmp_path)
    state=dict(axes={},atlas=dict(rf=np.array([0]),rf_names=np.array(['voltage_lower']),voltage_lower_rows=np.array([0]),node_names=np.array(['mess_idc02_pcc.1'])))
    for i,x in enumerate([0.,.5]):
        p=artificial_point(master,np.array([x]))[0];before=p.copy()
        a.observe(state,master,p,phase_objective(master,p),dict(Pi=np.zeros(1)),(0,),dict(native_seconds=.1),tmp_path/f'S{i}',None)
        assert np.array_equal(before,p)
    r=a.feedback[-1]
    assert r['relative_decrease']==.5 and r['voltage_rows'][0]['original_constraint_shortfall']==.5
    assert not r['dual_stabilization_applied'] and r['fixed_M1_feasibility']=='NOT_CERTIFIED'


@pytest.mark.parametrize('arm,stage',[('B1','A1'),('B1','A2'),('B3','A1'),('B3','A2')])
def test_all_B1_B3_A_stages_compile_the_same_adaptive_phase(tmp_path,monkeypatch,arm,stage):
    from v44_recovery_r024a import phase_rebuild,adaptive_pricing
    from v42_may_campaign_native90 import a_stage
    from v42_a_stage_canary import phase
    calls=[]
    monkeypatch.setattr(adaptive_pricing,'compile_adaptive',lambda fn,ns,controller:calls.append(controller) or fn)
    with phase_rebuild.stage_scope(dict(root=str(tmp_path),day='2025-05-03',arm=arm,stage=stage)):
        a_stage.group(phase,('activate','run'))
    assert len(calls)==1
