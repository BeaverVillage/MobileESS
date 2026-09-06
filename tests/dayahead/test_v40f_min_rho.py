from types import SimpleNamespace
from dataclasses import replace
import numpy as np
import pytest
from dayahead.v28r2.electrical_subproblem import SlotCoefficients
from dayahead.v38.authority import CapacityAuthority,RackPool
from dayahead.v40f.optimizer import solve


def setup(equal=False):
    cap=CapacityAuthority(site_capacity={'AIDC01':2,'AIDC02':2},historical_site_capacity={'AIDC01':2.,'AIDC02':2.},
        rack_pools=(RackPool('AIDC01','AIDC01_LP01',2.),RackPool('AIDC02','AIDC02_LP01',2.)),source_sha256='toy')
    w=np.array([.4,.4 if equal else .1,0.])
    c=SlotCoefficients(slot=0,control_names=('aidc_load_kw[AIDC01]','aidc_load_kw[AIDC02]','mess_p_kw[STA01]'),
        branch_names=('line.test::A','transformer.test::A'),anchor=np.zeros(3),
        voltage_constant=np.ones(1),voltage_matrix=np.zeros((3,1)),
        current_constant=np.array([.1,.1]),current_matrix=np.column_stack([w/10,w/10]),
        flow_p_constant=np.ones(2),flow_q_constant=np.zeros(2),flow_p_matrix=np.array([w,w]),flow_q_matrix=np.zeros((2,3)),
        branch_limits=(10.,10.),transformer_ratings=(None,10.),coefficient_sha256='a'*64)
    ctx=SimpleNamespace(capacity=cap,coefficients=(c,),nodes=['bus.1'],tables={s:np.array([[0.,1.,2.]]) for s in cap.aidc_ids})
    row={'job_uid':'one','state_at_issue':'PENDING','qos':'standby','requested_GPU':1,'safe_duration_slots':1,'safe_duration_seconds':900.,
        'duration_authority':'SAFE_CAUSAL_RUNTIME_PENDING','start_slot':24,'end_slot':25,'AIDC_site':'AIDC01','Rack_label':'AIDC01_LP01',
        'post_H_site':None,'eligible_standby':False,'RSP_start_slot':24,'RW_completion_slot':25,'migration_selected':False}
    return ctx,row


def test_primary_uses_actual_inherited_grid_rows_and_reassigns_for_rho(tmp_path):
    ctx,row=setup();result=solve([row],[row],np.array([[1.,0.]]),ctx,tmp_path)
    assert result['status']=='PASS' and result['B1_PRIMARY_OBJECTIVE']=='MIN_RHO_MAX'
    assert result['primary_gain_vs_reference']>.01
    assert result['jobs'][0]['AIDC_site']=='AIDC02'
    assert result['B1_MESS_ENABLED']=='NO' and not result['complete_RW_reference_selected']
    assert all(x>0 for x in result['grid_rows'].values())


def test_zero_gain_selects_complete_reference_despite_different_seed_site(tmp_path):
    ctx,row=setup(equal=True);seed={**row,'AIDC_site':'AIDC02','Rack_label':'AIDC02_LP01'}
    result=solve([row],[seed],np.array([[1.,0.]]),ctx,tmp_path)
    assert result['complete_RW_reference_selected'] and result['jobs']==[row]
    assert result['secondary_reference_deviation_GPU_slots']==0
    assert abs(result['primary_gain_vs_reference'])<1e-9


def test_different_duration_models_are_rejected_before_solving(tmp_path):
    ctx,row=setup(equal=True)
    reference={**row,'end_slot':125,'safe_duration_slots':101,'safe_duration_seconds':90900.,'post_H_site':'AIDC01'}
    with pytest.raises(ValueError,match='CASE_DEPENDENT_DA_SERVICE'):
        solve([reference],[row],np.array([[1.,0.]]),ctx,tmp_path)


def test_common_terminal_obligation_preserves_reference_tail(tmp_path):
    ctx,row=setup(equal=True)
    reference={**row,'end_slot':125,'safe_duration_slots':101,'safe_duration_seconds':90900.,'post_H_site':'AIDC01'}
    result=solve([reference],[reference],np.array([[1.,0.]]),ctx,tmp_path)
    assert result['complete_RW_reference_selected'] and result['jobs']==[reference]
    assert result['terminal_audit']['decision_exact_equal']
    assert result['B1_REFERENCE_CANDIDATE_INCLUDED']=='PASS'


def test_coordinated_running_restriction_keeps_running_site(tmp_path):
    ctx,row=setup();row={**row,'state_at_issue':'RUNNING'}
    result=solve([row],[row],np.array([[1.,0.]]),ctx,tmp_path)
    assert result['complete_RW_reference_selected']
    assert result['jobs'][0]['AIDC_site']=='AIDC01'
