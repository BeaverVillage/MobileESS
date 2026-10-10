"""Exact representation and original production-seam regressions, no Native."""
from fractions import Fraction
import json
from types import SimpleNamespace

import gurobipy as gp
import numpy as np
import pytest
from scipy import sparse

from test_v42_autonomous_b2_rmp_presolve import env, Raw, invoke, rebuild
from v42_autonomous_b2 import rmp_presolve as draft
from v42_m1_hybrid.blocks import build_blocks


def represented(env):
    matrix=env.case.A.toarray()
    matrix[5,5]=2.**-10;matrix[6,5]=-2.**-8
    env.case.A=sparse.csr_matrix(matrix)
    env.case.d['objective'][5]=2.**-5
    env.decomp=build_blocks(env.case)
    result=rebuild(env)
    assert env.model._representation['adopted_computational_representation']
    assert np.any(env.model._column_exponents[:len(env.decomp.nonunit_columns)])
    return result


def no_entry(env):
    assert env.budget.calls==[] and env.budget.inflight is None
    assert env.model._model.entries==[] and env.model._model.start_events==[]


def test_exact_native_construction_start_and_original_model_facade(env):
    model,variables,rows,identity,source_rows=represented(env)
    raw=model._model;original=model.getA();r=model._exponents;s=model._column_exponents
    shifts=np.repeat(r,np.diff(original.indptr))+s[original.indices]
    assert draft._same_bits(raw.matrix.data,np.ldexp(original.data,shifts))
    for name,key,exponents in [('RHS','_rhs',r),('LB','_domain',-s),('UB','_domain',-s),('Obj','_domain',s)]:
        source=getattr(model,key) if name=='RHS' else model._domain[dict(LB='lb',UB='ub',Obj='obj')[name]]
        assert draft._same_bits(raw.attrs[name],np.ldexp(source,exponents))
        assert draft._same_bits(model.getAttr(name),source)
    assert np.all(s[len(env.decomp.nonunit_columns):]==0) and np.all(r[-4:]==0)
    assert tuple(raw.variables.VarName)==tuple(identity_name for identity_name in model._names)
    assert all(raw.attrs['VType']=='C') and raw.ObjCon==.5
    receipt=invoke(env)
    assert receipt['Native_Runtime']==2.25 and len(raw.entries)==len(env.budget.calls)==1
    native=raw.entries[0]
    assert native['params']['TimeLimit']==30 and native['params']['Method']==0
    assert draft._same_bits(native['starts']['PStart'],np.ldexp(model._rmp_warm_plan.pstart,-s))
    assert draft._same_bits(native['starts']['DStart'],np.ldexp(model._rmp_warm_plan.dstart,-r))
    assert model._rmp_warm_plan.diagnostic['Native_scaled_RMP_residual']['maximum_row_violation']<=1e-9
    assert draft._same_bits(model.getA().data,original.data)
    meta=json.loads((env.out/'next_master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert meta['computational_exact_representation']['Native_calls_added']==0
    assert meta['restricted_master_objective_is_Global_LB'] is False


def test_original_primal_and_row_dual_pullback_preserve_exact_lagrangian(env):
    model,variables,rows,*_=represented(env)
    original=model.getA();r=model._exponents;s=model._column_exponents;raw=model._model
    z=np.ldexp(model._rmp_warm_plan.pstart,-s)
    p=np.full(len(r),2.**-32)
    raw.variables.X=z;model._raw_rows.Pi=p
    x=np.asarray(variables.X);pi=np.asarray(rows.Pi)
    assert draft._same_bits(x,np.ldexp(z,s)) and draft._same_bits(pi,np.ldexp(p,r))
    assert draft._same_bits(x,model._rmp_warm_plan.pstart)
    # Exact rational arithmetic checks the coordinate identity independently
    # of the representation kernel; this is not a scientific certificate.
    def lag(a,b,c,point,dual):
        result=sum((Fraction(float(q))*Fraction(float(v)) for q,v in zip(c,point)),Fraction())
        for i in range(a.shape[0]):
            dot=sum((Fraction(float(q))*Fraction(float(point[j])) for j,q in
                     zip(a.indices[a.indptr[i]:a.indptr[i+1]],a.data[a.indptr[i]:a.indptr[i+1]])),Fraction())
            result+=Fraction(float(dual[i]))*(dot-Fraction(float(b[i])))
        return result
    assert lag(original,model._rhs,model._domain['obj'],x,pi)==lag(raw.matrix,raw.attrs['RHS'],raw.attrs['Obj'],z,p)


def test_original_dw_producer_receives_original_row_pi(env,monkeypatch):
    represented(env)
    add=Raw.addMConstr
    def provide(self,*args):
        result=add(self,*args);result.Pi[:]=2.**-32;return result
    monkeypatch.setattr(Raw,'addMConstr',provide)
    result=env.runner(env.case,env.decomp,{},env.budget,env.out/'original_producer',seconds=30)
    with np.load(env.out/'original_producer/RMP_RAW_DUAL.npz',allow_pickle=False) as saved:
        pi=saved['dual']
    meta=json.loads((env.out/'original_producer/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert result['dual_status']=='FINITE_ORIGINAL_ROW_DUAL_AVAILABLE_NOT_NATIVE_OBJECTIVE_PROOF'
    assert np.any(pi!=2.**-32) and np.all(pi[-4:]==2.**-32)
    assert meta['Native_call_completed'] and len(env.budget.calls)==1
    assert result['restricted_master_is_Global_LB'] is False


def test_tiny_lambda_scaled_start_declines_before_single_native_construction(env,monkeypatch):
    env.case.d['sense'][6]='=';env.case.point[-2:]=[1e-25,1e-10]
    env.decomp=build_blocks(env.case)
    calls=[];addvar=Raw.addMVar;addrow=Raw.addMConstr
    def var(self,*args,**kwargs):calls.append('variables');return addvar(self,*args,**kwargs)
    def row(self,*args,**kwargs):calls.append('rows');return addrow(self,*args,**kwargs)
    monkeypatch.setattr(Raw,'addMVar',var);monkeypatch.setattr(Raw,'addMConstr',row)
    rebuild(env);model=env.model
    assert calls==['variables','rows'] and not model._representation['adopted_computational_representation']
    assert model._representation['decline_reason']=='SCALED_CURRENT_RMP_START_NOT_ELIGIBLE'
    original,native,rhs,r,receipt=draft.dw_native.scale_rows(model._expected,model._rhs)
    assert draft.dw_native._same_matrix(native,model._scaled) and draft._same_bits(r,model._exponents)
    assert np.all(model._column_exponents==0)
    invoke(env)
    assert model._model.entries[0]['params']['Method']==1 and len(env.budget.calls)==1
    assert calls==['variables','rows'] and model._rmp_warm_plan.diagnostic['original_RMP_residual']['maximum_row_violation']<1e-9


@pytest.mark.parametrize('mutate',[
    lambda m:setattr(m._native_variables,'VarName',tuple('wrong' if i==0 else v for i,v in enumerate(m._names))),
    lambda m:setattr(m._pending,'owner',object()),
    lambda m:setattr(m._pending,'native',object()),
    lambda m:setattr(m._rows_proxy,'owner',object()),
    lambda m:setattr(m._rows_proxy,'rows',SimpleNamespace(Pi=np.zeros(len(m._rhs)))),
    lambda m:setattr(m,'_rows_proxy',SimpleNamespace(Pi=np.zeros(len(m._rhs)))),
    lambda m:setattr(m._scaled.data.flags,'writeable',True),
    lambda m:setattr(m._expected.indptr.flags,'writeable',True),
    lambda m:setattr(m._native_domain['ub'].flags,'writeable',True),
    lambda m:setattr(m._domain['obj'].flags,'writeable',True),
    lambda m:setattr(m._column_exponents.flags,'writeable',True),
])
def test_native_and_private_axis_or_mutability_drift_fails_before_admission(env,mutate):
    represented(env);mutate(env.model)
    with pytest.raises((PermissionError,ValueError)):invoke(env)
    no_entry(env)


def test_new_method_table_cannot_be_mutated_or_replaced(env,monkeypatch):
    represented(env)
    with pytest.raises(TypeError):draft._REPRESENTATION_METHODS['getA']=lambda self:self._expected
    monkeypatch.setattr(draft,'_REPRESENTATION_METHODS',dict(draft._REPRESENTATION_METHODS))
    with pytest.raises(PermissionError,match='IMMUTABLE_ORIGINAL_CODE'):invoke(env)
    no_entry(env)


@pytest.mark.parametrize('target',['kernel','pullback_property','start_property'])
def test_new_delegate_and_property_replacement_cannot_bypass_entry(env,monkeypatch,target):
    represented(env)
    if target=='kernel':monkeypatch.setattr(draft,'_dyadic_shift',lambda *a,**k:np.asarray(a[0]))
    elif target=='pullback_property':monkeypatch.setattr(draft.PulledRows,'Pi',property(lambda self:np.zeros(len(self.owner._rhs))))
    else:monkeypatch.setattr(draft.PendingVariables,'X',property(lambda self:np.zeros(self.count)))
    with pytest.raises(PermissionError,match='IMMUTABLE_ORIGINAL_CODE'):invoke(env)
    no_entry(env)


@pytest.mark.parametrize('value,shift,bounds',[
    ([np.nextafter(0.,1.)],[-1],False),([1e300],[100],False),([1e90],[40],True),
    ([1e100],[0],True),([gp.GRB.UNDEFINED],[1],False),
])
def test_lossy_or_native_infinity_numeric_transport_declines_without_native(value,shift,bounds):
    # UNDEFINED is a separate start authority guard, not a generic number.
    if value[0]==gp.GRB.UNDEFINED:
        with pytest.raises(draft.RepresentationDeclined):
            matrix=sparse.csr_matrix(np.vstack((np.eye(5),np.zeros((4,5)))))
            draft._dyadic_plan(matrix,np.zeros(9),np.full(9,'='),
                dict(lb=np.zeros(5),ub=np.ones(5),obj=np.zeros(5),vtype='C'),np.array(value*5),1)
    else:
        with pytest.raises(draft.RepresentationDeclined):draft._dyadic_shift(np.array(value),np.array(shift),'NUMERIC',bounds=bounds)


def test_post_native_pi_transport_overflow_is_unavailable_to_original_producer(env,monkeypatch):
    represented(env);add=Raw.addMConstr
    def provide(self,*args):
        result=add(self,*args);result.Pi[:]=1e308;return result
    monkeypatch.setattr(Raw,'addMConstr',provide)
    result=env.runner(env.case,env.decomp,{},env.budget,env.out/'unsafe_pi',seconds=30)
    assert result['dual_status']=='NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN'
    assert result['full_original_dual'] is None and result['convexity_duals'] is None
    assert len(env.budget.calls)==1 and env.budget.calls[0]['Native_Runtime']==2.25


def test_post_native_point_transport_loss_fails_without_rewriting_native_receipt(env):
    model,variables,*_=represented(env);invoke(env)
    model._native_variables.X=np.full(len(model._names),1e308)
    with pytest.raises(draft.RepresentationDeclined):variables.X
    assert len(env.budget.calls)==1 and env.budget.calls[0]['Native_Runtime']==2.25
    assert env.budget.calls[0]['status']=='FINISHED' and env.budget.used()==2.25


def test_original_integer_nonunit_domain_never_receives_column_transform(env):
    env.case.d['types'][5]='B';env.case.point[5]=1.;env.decomp=build_blocks(env.case)
    rebuild(env)
    assert not env.model._representation['adopted_computational_representation']
    assert env.model._representation['decline_reason']=='ORIGINAL_NONUNIT_INTEGER_VARIABLE_SCALING_FORBIDDEN'
    assert np.all(env.model._column_exponents==0)
    invoke(env)
    assert len(env.budget.calls)==1 and all(env.model._model.attrs['VType']=='C')


def test_admitted_remaining_point_one_actual_point_eleven_retains_budget_stop_and_terminal_truth(env):
    env.budget.calls=[dict(Native_Runtime=5399.9,runtime_unavailable=False)]
    env.budget.native_used=5399.9;env.budget.persist();env.model._model.Runtime=.11
    with pytest.raises(draft.original_budget.BudgetStop,match='NATIVE_RUNTIME_CEILING_EXCEEDED'):invoke(env)
    assert len(env.model._model.entries)==1 and len(env.budget.calls)==2
    assert env.model._model.entries[0]['params']['TimeLimit']==5400.-5399.9
    assert env.budget.calls[-1]['status']=='FINISHED' and env.budget.calls[-1]['Native_Runtime']==.11
    assert env.budget.used()==5399.9+.11 and env.budget.inflight is None
    meta=json.loads((env.out/'master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert meta['status']=='FAILED' and meta['Native_call_completed']
    assert not meta['adapter_validation_completed'] and not meta['scientific_PASS']
    assert meta['original_BudgetStop_preserved']
    assert meta['exact_finished_terminal_truth']['measured_ceiling_overshoot_seconds']==env.budget.used()-5400.
    with pytest.raises(PermissionError):draft._known_ledger(env.budget,env.request)
    with pytest.raises(PermissionError):invoke(env)
    proxy=draft.BudgetProxy(env.budget,env.proxy._write,env.runner.binding)
    with pytest.raises(PermissionError):proxy.optimize(env.model,track='RMP',label=draft.LABEL,requested_seconds=30)
    assert len(env.model._model.entries)==1 and len(env.budget.calls)==2


@pytest.mark.parametrize('change',['unknown','forged','nonreturned'])
def test_budget_stop_cannot_claim_unknown_forged_or_nonreturned_terminal(env,change):
    env.budget.calls=[dict(Native_Runtime=5399.9,runtime_unavailable=False)]
    env.budget.native_used=5399.9;env.budget.persist();raw=env.model._model;raw.Runtime=.11
    if change=='nonreturned':raw.error=draft.original_budget.BudgetStop('NATIVE_RUNTIME_CEILING_EXCEEDED')
    original_progress=env.budget.progress
    def corrupt(value):
        original_progress(value)
        if len(env.budget.calls)==2:
            if change=='unknown':env.budget.calls[-1].update(Native_Runtime=None,runtime_unavailable=True)
            if change=='forged':env.budget.calls[0]['Native_Runtime']=5399.8
            env.budget.persist()
    env.budget.progress=corrupt
    with pytest.raises(draft.original_budget.BudgetStop):invoke(env)
    meta=json.loads((env.out/'master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert not meta['Native_call_completed'] and meta['exact_finished_terminal_truth'] is None
    assert not meta['adapter_validation_completed'] and not meta['scientific_PASS']
    assert meta['terminal_truth_validation_error'] is not None and len(raw.entries)==1


def test_pending_model_axes_are_unavailable_before_original_builder_final_matrix(env,monkeypatch):
    add=draft.PresolveFreeRMP.addMVar
    observed=[]
    def inspect_pending(self,*a,**k):
        result=add(self,*a,**k)
        for key in ('NumVars','NumConstrs'):
            with pytest.raises(PermissionError,match='PENDING_ATTRIBUTE_READ'):getattr(self,key)
            observed.append(key)
        return result
    # Exercise this read during the original construction, before the Native
    # arrays exist; never change the closed method used during admission.
    monkeypatch.setattr(draft.PresolveFreeRMP,'addMVar',inspect_pending)
    with pytest.raises(PermissionError,match='OWN_ORIGINAL_DELEGATE'):
        rebuild(env)
    assert observed==['NumVars','NumConstrs']
    no_entry(env)

