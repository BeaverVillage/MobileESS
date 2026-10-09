"""Native-denied guard and original-code-path tests for production V31."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_autonomous_b2.f1_basis import transport_basis,Scope
from v42_autonomous_b2 import f1_state as v27

spec = importlib.util.spec_from_file_location('v28_v27_test_helpers',
    Path(__file__).resolve().with_name('test_v42_autonomous_b2_f1_state.py'))
base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
deny_real_gurobi_models = base.deny_real_gurobi_models


@pytest.fixture
def env(tmp_path,monkeypatch):
    e = base.env.__wrapped__(tmp_path,monkeypatch)
    e.scope = Scope(e.request,e.code,writer=base.write)
    return e


def free_case(**changes):
    d = dict(vbasis=np.array([0,-1,-3]),cbasis=np.array([-1]),
        point=np.array([2.,0.,0.]),lower=np.array([0.,0.,-np.inf]),
        upper=np.array([10.,2.,np.inf]),types=np.array(['C','I','C']),
        fixed_ids=np.array([1]),fixed_values=np.array([0.]),rows=1)
    d.update(changes)
    return d


def test_narrow_original_free_zero_superbasic_preserves_basis_and_rhs_contribution():
    source=free_case();result=transport_basis(**source)
    assert result['eligible'] and result['free_continuous_exact_zero_superbasics_retained']==1
    assert np.array_equal(result['vbasis'],source['vbasis'])
    assert np.array_equal(result['cbasis'],source['cbasis'])
    assert result['Global_LB_authority'] is False
    # B and its nonbasic zero contribution are identical after relaxation.
    A=np.array([[1.,1.,7.]])
    old_B=A[:,source['vbasis']==0];new_B=A[:,result['vbasis']==0]
    assert np.array_equal(old_B,new_B) and np.linalg.det(new_B)==1
    assert (A[:,source['vbasis']!=0]@source['point'][source['vbasis']!=0]).item()==0


@pytest.mark.parametrize('change',[
    dict(point=np.array([2.,0.,1.])),dict(types=np.array(['C','I','I'])),
    dict(lower=np.array([0.,0.,0.])),dict(upper=np.array([10.,2.,0.])),
    dict(lower=np.array([0.,0.,-2.]),upper=np.array([10.,2.,2.])),
    dict(fixed_ids=np.array([1,2]),fixed_values=np.array([0.,0.]))])
def test_superbasic_exception_rejects_nonzero_noncontinuous_finite_or_fixed(change):
    assert transport_basis(**free_case(**change))['eligible'] is False


@pytest.mark.parametrize('change',[
    dict(vbasis=np.array([0,-1,-3,-1])),dict(cbasis=np.array([0])),
    dict(vbasis=np.array([0.,-1.,-3.])),dict(cbasis=np.array([-3])),
    dict(point=np.array([2.,1.,0.])),dict(vbasis=np.array([0,-4,-3])),
    dict(point=np.array([np.nan,0.,0.])),dict(fixed_ids=np.array([1,1]),fixed_values=np.array([0.,0.])),
    dict(fixed_ids=np.array([7]),fixed_values=np.array([0.])),
    dict(vbasis=None),dict(cbasis=None)])
def test_incomplete_axis_status_count_and_seals_never_invent_basis(change):
    assert transport_basis(**free_case(**change))['eligible'] is False


def test_fixed_upper_endpoint_remap_retains_original_basic_columns():
    result=transport_basis(**free_case(point=np.array([0.,2.,0.]),fixed_values=np.array([2.])))
    assert result['eligible'] and result['vbasis'].tolist()==[0,-2,-3]
    assert result['remapped_nonbasic_endpoints']==1


def test_interior_fixed_nonbasic_has_no_invented_basis():
    result=transport_basis(**free_case(point=np.array([1.,1.,0.]),fixed_values=np.array([1.])))
    assert result['eligible'] is False and 'INTERIOR' in result['reason']


def admitted_basis(env):
    env.case.d['upper'][1]=1.
    base.capture(env)
    full=base.Model(env.case,fixed=False);full.Runtime=300.
    result=env.scope.install(full,env.case,env.budget)
    assert result['mode']=='COMPLETE_SAME_ATTEMPT_ORIGINAL_BASIS'
    return full


def lp_kwargs(env,**overrides):
    kwargs=dict(component='P1',track='M_LB',label=v27.LP_LABEL,
                requested_seconds=min(300.,env.budget.remaining(reserve=env.budget.final_reserve)))
    kwargs.update(overrides);return kwargs


def test_method_zero_selected_only_after_original_reset_at_exact_one_delegate(env):
    full=admitted_basis(env)
    assert full.Params.Method==1 and full.Params.LPWarmStart==1
    calls=[];original=env.budget.native_optimize
    def actual(model,*args,**kwargs):
        calls.append((model.Params.Method,model.Params.LPWarmStart,model.Params.Threads,
                      model.Params.TimeLimit,{k:getattr(model.Params,k) for k in v27.PRECISION}))
        return original(model,*args,**kwargs)
    env.budget.native_optimize=actual
    proxy=env.scope._budget_proxy(env.case,env.budget)
    proxy.native_optimize(full,**lp_kwargs(env))
    assert calls==[(0,2,1,300.,v27.PRECISION)] and len(env.budget.calls)==2
    receipt=json.loads((env.output/'F1_FULL_LP_COMPUTATIONAL_ENTRY.json').read_text())
    assert receipt['Native_call_completed'] and receipt['completed_original_Native_call']['Native_Runtime']==300.
    assert receipt['actual_parameters']['LPWarmStart']==2
    with pytest.raises(PermissionError,match='EXACT_ORIGINAL_FULL_LP'):
        proxy.native_optimize(full,**lp_kwargs(env))
    assert len(calls)==1


@pytest.mark.parametrize('overrides',[
    dict(component='P2'),dict(track='M_START'),dict(label='another'),
    dict(requested_seconds=301.),dict(requested_seconds=0.),dict(requested_seconds=True),
    dict(requested_seconds=float('nan')),dict(requested_seconds=120.)])
def test_wrong_label_budget_or_component_rejected_before_delegate(env,overrides):
    full=admitted_basis(env)
    with pytest.raises(PermissionError,match='EXACT_ORIGINAL_FULL_LP'):
        env.scope._budget_proxy(env.case,env.budget).native_optimize(full,**lp_kwargs(env,**overrides))
    assert len(env.budget.calls)==1 and full.Params.Method==1


@pytest.mark.parametrize('mutate',[
    lambda e,m:setattr(m.Params,'Threads',2),lambda e,m:setattr(m.Params,'Method',0),
    lambda e,m:setattr(m.Params,'LPWarmStart',2),lambda e,m:m.attrs['VBasis'].__setitem__(0,-1),
    lambda e,m:m.A.data.__setitem__(0,2.),lambda e,m:m.attrs['Obj'].__setitem__(0,2.),
    lambda e,m:e.scope.request.update(attempt_id='old_attempt'),
    lambda e,m:(e.output/'F1_FULL_LP_WARMSTART.json').write_text('{}')])
def test_state_math_settings_and_receipt_drift_rejected_before_delegate(env,mutate):
    full=admitted_basis(env);mutate(env,full)
    with pytest.raises(PermissionError):
        env.scope._budget_proxy(env.case,env.budget).native_optimize(full,**lp_kwargs(env))
    assert len(env.budget.calls)==1


def test_different_model_not_admitted_at_current_basis_entry(env):
    admitted_basis(env);other=base.Model(env.case,fixed=False)
    with pytest.raises(PermissionError,match='CURRENT_MODEL'):
        env.scope._budget_proxy(env.case,env.budget).native_optimize(other,**lp_kwargs(env))
    assert len(env.budget.calls)==1


def test_interior_fallback_remains_v27_method_one_primal_dual_two(env):
    base.capture(env);full=base.Model(env.case,fixed=False);full.Runtime=300.
    receipt=env.scope.install(full,env.case,env.budget)
    assert receipt['mode']=='COMPLETE_SAME_ATTEMPT_PRIMAL_DUAL_START'
    env.scope._budget_proxy(env.case,env.budget).native_optimize(full,**lp_kwargs(env))
    assert full.Params.Method==1 and full.Params.LPWarmStart==2
    assert not (env.output/'F1_FULL_LP_COMPUTATIONAL_ENTRY.json').exists()


def test_original_full_domain_checker_still_rejects_fixed_f1_objective_as_lb(env):
    base.capture(env)
    _,cert=env.scope.select(base.original_full_lp(env),env.case,env.budget)
    assert cert['exact_bound']=='0' and cert['F1_restricted_bounds_used'] is False
    assert len(env.budget.calls)==2 and env.budget.calls[-1]['requested_seconds']==300.


def test_actual_original_full_lp_bytecode_builder_reset_delegate_dispose_and_checker(env,monkeypatch):
    from v42_may_campaign_native90.a_routing import rebound
    # Admit original endpoint basis using the small stand-in F1 only.
    env.case.d['upper'][1]=1.;base.capture(env)
    full=base.Model(env.case,fixed=False);full.Runtime=300.
    full.attrs['Pi']=[0.];env.case.bundle=dict(day='2025-05-01')
    original=env.original_functions['FULL_LP']
    rebound_original=rebound(original,dict(original.__globals__,
        _model=lambda case,continuous=False:(full,dict(original_model=True)),atomic=base.write))
    monkeypatch.setattr(v27,'_ORIGINAL_FUNCTIONS',dict(env.original_functions,F1=v27._ORIGINAL_FUNCTIONS['F1']))
    original_code=original.__code__
    dual,cert=env.scope.full_lp_adapter(rebound_original,env.case,env.budget)
    assert rebound_original.__code__ is original_code
    assert full.disposed and full.Params.Method==0 and full.Params.LPWarmStart==2
    assert len(env.budget.calls)==2 and env.budget.calls[-1]['requested_seconds']==300.
    # Original y<=1 means original optimum x=1. Independent full-box proof1
    # is retained; the adapter never treats a fixed-box objective as proof.
    assert cert['exact_bound']=='1' and cert['F1_Native_objective_used'] is False
    assert json.loads((env.output/'F1_FULL_LP_COMPUTATIONAL_ENTRY.json').read_text())['Native_call_completed']


def test_mutating_cached_decision_and_native_basis_together_cannot_invent_basis(env):
    full=admitted_basis(env)
    env.scope._primal_basis['vbasis'][:]=[-1,0]
    full.attrs['VBasis'][:]=[-1,0]
    with pytest.raises(PermissionError,match='INSTALLED_BASIS_CHANGED'):
        env.scope._budget_proxy(env.case,env.budget).native_optimize(full,**lp_kwargs(env))
    assert len(env.budget.calls)==1


def test_builder_receipt_plans_presolved_start_without_claiming_presolved_basis_identity(env):
    full=admitted_basis(env)
    receipt=json.loads((env.output/'F1_FULL_LP_WARMSTART.json').read_text())
    assert full.Params.Method==1 and full.Params.LPWarmStart==1
    assert receipt['LPWarmStart_at_builder_return']==1
    assert receipt['LPWarmStart_at_approved_Native_entry']==2
    assert receipt['original_basis_installed_before_Native_entry'] is True
    assert receipt['original_basis_to_presolved_start_transport_planned'] is True
    assert receipt['original_unpresolved_basis_computational_start'] is False
    assert receipt['presolved_basis_identity_unchanged_claimed'] is False
    assert receipt['Global_LB_authority'] is False
    assert receipt['performance_benefit_claimed'] is False
    assert len(env.budget.calls)==1


@pytest.mark.parametrize('changed',[
    ('LPWarmStart',0),('LPWarmStart',1),('Method',1),('Threads',2)])
def test_completed_original_native_cost_remains_recorded_when_post_parameters_tampered(env,changed):
    full=admitted_basis(env);original=env.budget.native_optimize
    def completed_then_tampered(model,*args,**kwargs):
        assert model.Params.Method==0 and model.Params.LPWarmStart==2
        returned=original(model,*args,**kwargs)
        setattr(model.Params,*changed)
        return returned
    env.budget.native_optimize=completed_then_tampered
    with pytest.raises(PermissionError,match='COMPLETED_CALL_PARAMETER_DRIFT'):
        env.scope._budget_proxy(env.case,env.budget).native_optimize(full,**lp_kwargs(env))
    assert len(env.budget.calls)==2
    assert env.budget.calls[-1]['Native_Runtime']==300.
    assert env.budget.inflight is None
    receipt=json.loads((env.output/'F1_FULL_LP_COMPUTATIONAL_ENTRY.json').read_text())
    assert receipt['Native_call_completed'] is False
    assert receipt['actual_parameters']['LPWarmStart']==2
