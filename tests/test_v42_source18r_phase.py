from dataclasses import replace
import numpy as np
import scipy.sparse as sp
import pytest
from v42_a_stage_phase1.core import elastic_master,primal_replay,verify_zero
from v42_integration import table_v_phase_policy as policy
from v42_integration.table_v_phase_diagnostics import extend_basis,residual_report,basis_admission
from tests.test_v42_table_v_phase_policy import snapshot


def test_source18r_recorded_scaling_and_numeric_settings():
    p=policy.SOURCE18R_FAST.parameters()
    assert {k:p[k] for k in ('Presolve','Method','NumericFocus','FeasibilityTol','OptimalityTol','Threads','ScaleFlag','Crossover','BarHomogeneous')}==dict(
        Presolve=-1,Method=2,NumericFocus=0,FeasibilityTol=1e-6,OptimalityTol=1e-6,Threads=1,
        ScaleFlag=-1,Crossover=-1,BarHomogeneous=-1)


def test_relaxed_admission_does_not_change_original_objective_or_zero_certificate(tmp_path):
    s=snapshot();raw=dict(X=np.array([-7.63e-6]),Pi=np.array([1.]),RC=np.array([0.]))
    r=residual_report(s,raw,tmp_path)
    assert r['numerical_1e5']['PASS'] and not r['legacy_1e6']['PASS']
    assert r['certified_Global_LB'] is None
    assert (tmp_path/'ROW_RESIDUALS.csv').exists()
    wrapper=policy.phase_primal_replay(primal_replay)
    assert wrapper(s,raw['X'])['PASS']
    original=replace(s,objectives=(replace(s.objectives[0],name='rho'),))
    assert not wrapper(original,raw['X'])['PASS']
    master=elastic_master(original,[0]);point=np.array([-7.63e-6,0.])
    assert not policy.require_exact_zero(verify_zero)(master,point)['PASS']


def test_included_rows_and_artificial_columns_map_with_new_basic_slacks():
    original=snapshot();old=elastic_master(original,[0])
    bigger=replace(original,matrix=sp.csr_matrix([[1.],[2.]]),rhs=np.array([0.,1.]),senses=np.array(['>','=']))
    new=elastic_master(bigger,[0,1])
    raw=dict(VBasis=np.array([-1,0]),CBasis=np.array([-1]),X=np.array([0.,0.]))
    v,c,proof=extend_basis(old.snapshot,new.snapshot,raw)
    assert np.array_equal(v,[-1,0,0,-1]) and np.array_equal(c,[-1,-1])
    assert proof['exact_inclusion'] and proof['LPWarmStart']==2 and not proof['PStart_DStart_installed']
    assert proof['new_local_artificials_basic']==1 and proof['new_row_slacks_basic']==0
    assert not proof['uncompensated_prior_point_replay']['PASS']
    assert proof['extended_elastic_witness_replay']['PASS']
    B=new.snapshot.matrix[:,np.flatnonzero(v==0)].toarray()
    B=np.c_[B,np.eye(2)[:,np.flatnonzero(c==0)]]
    assert np.linalg.matrix_rank(B)==2


@pytest.mark.parametrize('sense,rhs,basic', [('=',-2.,3),('>',2.,2),('<',-2.,2),('<',2.,None)])
def test_basis_extension_uses_correct_signed_artificial_or_feasible_slack(sense,rhs,basic):
    original=snapshot();old=elastic_master(original,[0])
    bigger=replace(original,matrix=sp.csr_matrix([[1.],[2.]]),rhs=np.array([0.,rhs]),senses=np.array(['>',sense]))
    new=elastic_master(bigger,[0,1]);raw=dict(VBasis=np.array([-1,0]),CBasis=np.array([-1]),X=np.array([0.,0.]))
    v,c,proof=extend_basis(old.snapshot,new.snapshot,raw)
    assert np.array_equal(v[:2],raw['VBasis']) and c[0]==raw['CBasis'][0]
    assert proof['extended_elastic_witness_replay']['PASS']
    assert proof['original_FULL_feasible_claimed'] is False
    assert proof['elastic_witness_installed_as_start'] is False
    if basic is None:assert c[1]==0 and np.count_nonzero(v[2:]==0)==0
    else:assert c[1]==-1 and v[basic]==0 and np.count_nonzero(v[2:]==0)==1


def test_basis_extension_cannot_invent_old_point_or_elasticize_new_hard_row():
    original=snapshot();old=elastic_master(original,[0])
    bigger=replace(original,matrix=sp.csr_matrix([[1.],[2.]]),rhs=np.array([0.,1.]),senses=np.array(['>','=']))
    new=elastic_master(bigger,[0]);raw=dict(VBasis=np.array([-1,0]),CBasis=np.array([-1]))
    with pytest.raises(ValueError,match='ACTUAL_NATIVE_PRIMAL_REQUIRED'):extend_basis(old.snapshot,new.snapshot,raw)
    raw['X']=np.array([0.,0.])
    with pytest.raises(ValueError,match='NEW_HARD_ROW'):extend_basis(old.snapshot,new.snapshot,raw)
    raw['X']=np.array([-1.,0.])
    with pytest.raises(ValueError,match='OLD_NATIVE_BASIS_POINT_NOT_PRIMAL_FEASIBLE'):extend_basis(old.snapshot,new.snapshot,raw)


@pytest.mark.parametrize('rhs,sense,primal',[(1.,'=',True),(-1.,'>',False)])
def test_positive_elastic_extension_uses_original_primal_basis_and_safe_extension_can_reuse(rhs,sense,primal):
    original=snapshot();old=elastic_master(original,[0])
    bigger=replace(original,matrix=sp.csr_matrix([[1.],[2.]]),rhs=np.array([0.,rhs]),senses=np.array(['>',sense]))
    new=elastic_master(bigger,[0,1]);raw=dict(VBasis=np.array([-1,0]),CBasis=np.array([-1]),X=np.array([0.,0.]))
    _,_,proof=extend_basis(old.snapshot,new.snapshot,raw);decision=basis_admission(proof)
    params=dict(policy.SOURCE18R_FAST.parameters(),**decision['parameters'])
    assert not decision['barrier_required'] and decision['reuse']
    assert decision['primal_simplex_required']==primal
    assert params['Method']==(0 if primal else 2) and params['LPWarmStart']==(1 if primal else 2)
    assert params['Presolve']==(0 if primal else -1)
    assert decision['native_basis_preserved_as_evidence'] and not decision['original_FULL_UB_claimed']


def test_failed_basis_install_restores_cold_profile_instead_of_primal_without_basis():
    from v42_integration.table_v_phase_diagnostics import restore_cold_phase_policy
    class PartialInstall:
        def __init__(self):self.params=dict(Method=0,LPWarmStart=1,Presolve=0);self.reset_called=False
        def reset(self):self.reset_called=True
        def setParam(self,key,value):self.params[key]=value
    model=PartialInstall();restore_cold_phase_policy(model,policy.SOURCE18R_FAST.parameters())
    assert model.reset_called
    assert {k:model.params[k] for k in ('Method','LPWarmStart','Presolve')}==dict(Method=2,LPWarmStart=0,Presolve=-1)


def test_basis_admission_does_not_promote_unverified_rank_or_primal_proof():
    with pytest.raises(ValueError,match='VERIFIED_NATIVE_BASIS_EXTENSION'):basis_admission(dict(PASS=True,new_local_artificials_basic=0))


def test_basis_rejects_changed_row_and_incomplete_native_basis():
    master=elastic_master(snapshot(),[0]);raw=dict(VBasis=np.array([-1,0]),CBasis=np.array([-1]))
    changed=replace(master.snapshot,rhs=np.array([1.]))
    with pytest.raises(ValueError,match='NOT_EXACTLY_INCLUDED'):extend_basis(master.snapshot,changed,raw)
    with pytest.raises(ValueError,match='INCOMPLETE'):extend_basis(master.snapshot,master.snapshot,dict(VBasis=np.array([-1,-1]),CBasis=np.array([-1])))


def diagnostic_budget(tmp_path,monkeypatch):
    from v42_integration.table_v_budget import TableVStageBudget
    from v42_integration import table_v_launch
    from v42_integration.m_engine import file_record
    monkeypatch.setattr(table_v_launch,'release_identity',lambda:dict(release_sha='current'))
    records=[]
    for i in range(3):
        p=tmp_path/str(i);p.write_text('frozen');records.append(file_record(p))
    label='RELEASE_P1:A1:DW:PHASE_I:SOURCE18R_AUDIT:SOURCE18R_FAST'
    context=dict(day='2025-05-01',arm='B1',stage='A1',stage_case_sha='case',source_sha='historical',parent_result_sha='parent')
    d=dict(schema='TABLE_V_SAVED_PHASE_DIAGNOSTIC_V1',approved=True,production_result_promoted=False,
        current_release=dict(release_sha='current'),snapshot_sha=snapshot().fingerprint(),frozen_records=records,
        allowed_labels=[label],context=context,native_binding=dict(matrix_sha='saved'))
    budget=TableVStageBudget.__new__(TableVStageBudget)
    budget.authorization=dict(saved_phase_i_diagnostic=d,human_approval_reference='user',carry_forward_ledgers=[records[0]],
        authorized_arm_stages=['B1:A1'],stage_caps_seconds={'B1:A1':5400.})
    budget.derived_bindings=[];budget.context=context;budget.path=tmp_path/'ledger.json'
    budget.document=dict(calls=[]);budget._refresh=lambda:None
    budget.remaining=lambda:4100.;budget.check_historical=lambda:None
    return budget,label


def test_saved_diagnostic_rejects_source_drift_and_modified_matrix(tmp_path,monkeypatch):
    budget,label=diagnostic_budget(tmp_path,monkeypatch)
    assert budget.bind_saved_phase_diagnostic(snapshot())==budget.context
    with pytest.raises(PermissionError,match='AUTHORITY'):budget.bind_saved_phase_diagnostic(replace(snapshot(),rhs=np.array([1.])))
    (tmp_path/'0').write_text('changed')
    with pytest.raises(PermissionError,match='AUTHORITY'):budget.bind_saved_phase_diagnostic(snapshot())


def test_saved_diagnostic_never_authorizes_production_or_reset(tmp_path,monkeypatch):
    budget,label=diagnostic_budget(tmp_path,monkeypatch)
    budget._call_gate(label)
    with pytest.raises(PermissionError,match='NO_PRODUCTION'):budget._call_gate('RELEASE_P1:A1:ORIGINAL_P1')
    budget.authorization['carry_forward_ledgers']=[]
    with pytest.raises(PermissionError,match='AUTHORITY'):budget.bind_saved_phase_diagnostic(snapshot())


def test_saved_diagnostic_cannot_reopen_phase_clock_or_change_native_model(tmp_path,monkeypatch):
    from v42_integration import d0_resource
    budget,label=diagnostic_budget(tmp_path,monkeypatch)
    budget.document['calls']=[dict(solver='GUROBI',label=label,Native_Runtime=900.,stage_context=budget.context)]
    with pytest.raises(PermissionError,match='ALLOWANCE_EXHAUSTED'):budget._call_gate(label)
    monkeypatch.setattr(d0_resource,'native_binding',lambda _:dict(matrix_sha='other'))
    with pytest.raises(PermissionError,match='MATRIX_DOMAIN_OBJECTIVE'):budget.solve(None,label=label,cap=1.)


def test_diagnostic_cli_requires_latest_descendant_and_blocks_drift(tmp_path):
    import json
    from tools.benchmark_v42_source18r_phase import predecessor
    from v42_integration.m_engine import file_record
    e08=tmp_path/'e08.json';e08.write_text(json.dumps(dict(calls=[],inflight=None)))
    child=tmp_path/'child.json';child.write_text(json.dumps(dict(calls=[dict(Native_Runtime=84.)],inflight=None)))
    head=tmp_path/'head.json';head.write_text(json.dumps(dict(state='COMPLETE',ledger=file_record(child))))
    r,prior=predecessor(head,e08)
    assert r['path']==str(child.resolve()) and prior['calls'][0]['Native_Runtime']==84.
    child.write_text('changed')
    with pytest.raises(RuntimeError,match='LEDGER_DRIFT'):predecessor(head,e08)
    head.write_text(json.dumps(dict(state='IN_PROGRESS',ledger_path=str(child))))
    with pytest.raises(RuntimeError,match='RECONCILIATION'):predecessor(head,e08)


def test_relaxed_elastic_point_replay_cannot_replace_strict_zero_check():
    from v42_a_stage_canary import phase
    from v42_may_campaign_native90.a_routing import rebound
    s=snapshot();master=elastic_master(s,[])
    backend=rebound(phase.point_with_replay,dict(phase.point_with_replay.__globals__,primal_replay=policy.phase_primal_replay(primal_replay)))
    point,replay=backend(master,np.array([-7.63e-6]))
    assert replay['PASS'] and np.array_equal(point,[-7.63e-6])
    assert not policy.require_exact_zero(verify_zero)(master,point)['PASS']
