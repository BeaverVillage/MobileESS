"""Small original-theorem tests. No gurobipy model or Native solve is used."""
import copy
import json
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from v42_autonomous_b2 import f1_state
from v42_autonomous_b2.f1_state import Scope,F1_LABEL,LP_LABEL,PRECISION,_digest,_record,_array_digest
from v42_m1_research.lb import repair_affine_equality_duals
from v42_b2_seed_recovery_v18.certificate_box import check
REAL_ORIGINAL_FUNCTIONS=f1_state._original_functions()


@pytest.fixture(autouse=True)
def deny_real_gurobi_models(monkeypatch):
    import gurobipy as gp
    attempts=[]
    def denied(*args,**kwargs):
        attempts.append((args,kwargs))
        raise AssertionError('V27_TEST_NATIVE_MODEL_CONSTRUCTION_FORBIDDEN')
    monkeypatch.setattr(gp,'Model',denied)
    yield
    assert attempts==[]


def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,sort_keys=True,allow_nan=False),encoding='utf-8')


class Model:
    """Stand-in exposing the Gurobi attributes exercised by the adapter."""
    def __init__(self,case,*,fixed=True,pi=(1.,),basis=True):
        self.case=case;self.disposed=False;self.Status=2;self.SolCount=1;self.Runtime=4.25
        self.Params=SimpleNamespace(Threads=1,Method=1,TimeLimit=120.,LPWarmStart=-1,**PRECISION)
        self.ObjCon=float(case.d['constant']);self.A=case.A.copy();self.saved={};self.events=[]
        self.attrs={k:list(case.d[v]) for k,v in (
            ('LB','lower'),('UB','upper'),('RHS','rhs'),('Sense','sense'),
            ('Obj','objective'),('VarName','names'))}
        self.attrs.update(VType=['C','C'],X=[1.,1.])
        if fixed:self.attrs['LB'][1]=self.attrs['UB'][1]=1.
        if pi is not None:self.attrs['Pi']=list(pi)
        if basis:self.attrs.update(VBasis=[0,-1],CBasis=[-1])

    def getAttr(self,key):
        if self.disposed:raise RuntimeError('state requested AFTER dispose')
        self.events.append('read:'+key)
        if key not in self.attrs:raise AttributeError(key)
        return self.attrs[key]

    def getA(self):return self.A.copy()
    def getVars(self):return ['x','y']
    def getConstrs(self):return ['row0']
    def update(self):self.events.append('update')
    def setAttr(self,name,axis,values):
        self.saved[name]=(list(axis),list(values))
        if name in self.attrs:self.attrs[name]=list(values)
    def dispose(self):self.events.append('dispose');self.disposed=True


class Budget:
    def __init__(self,output):
        self.path=output.parent/'NATIVE_RUNTIME_LEDGER.json';self.calls=[]
        self.inflight=None;self.native_limit=5400.;self.wall_limit=None;self.prior_attempt=None
        self.final_reserve=0.
        self.persist()

    def persist(self):
        write(self.path,dict(Native_ceiling_seconds=self.native_limit,wall_ceiling_seconds=None,
            P2_calls=0,inflight=self.inflight,historical_costs_reused=False,calls=self.calls,
            measured_Native_Runtime=sum(c['Native_Runtime'] for c in self.calls)))

    def native_optimize(self,model,callback=None,**kwargs):
        model.Params.TimeLimit=kwargs['requested_seconds']
        row=dict(kwargs,status='FINISHED',error=None,entered_native=True,
            runtime_unavailable=False,Native_Runtime=model.Runtime,Native_status=model.Status,
            effective_TimeLimit=kwargs['requested_seconds'],precision_parameters=dict(PRECISION))
        self.calls.append(row);self.persist()
        return None

    def remaining(self,reserve=0.):return self.native_limit-sum(c['Native_Runtime'] for c in self.calls)-reserve
    def cost(self,*args,**kwargs):return nullcontext()


@pytest.fixture
def env(tmp_path,monkeypatch):
    code=tmp_path/'code';code.mkdir();(code/'original.py').write_bytes(b'original scientist bytes\n')
    root=tmp_path/'campaign';root.mkdir();output=root/'dates/B2/2025-05-01/attempts/new_attempt/output'
    output.mkdir(parents=True)
    sources={'original.py':_record(code/'original.py')['sha256']}
    manifest=dict(run_id='current_run',initialization_native_limit_seconds=5400,
        builder_original_sources=sources,execution_sources=sources,execution_SHA=_digest(sources),prior_attempts={})
    path=root/'manifest.json';write(path,manifest)
    request=dict(root=str(root),output=str(output),manifest=str(path),manifest_SHA=_record(path)['sha256'],
        implementation_SHA=manifest['execution_SHA'],run_id='current_run',arm='B2',day='2025-05-01',
        worker_slot=1,attempt_id='new_attempt',Threads=1,P2_calls=0,native_budget_seconds=5400,
        wall_budget_seconds=None,target_gap=.03,previous_attempts=[])
    # min x subject to x+y>=2, original 0<=y<=2.  F1 y=1 => x=1,
    # but the FULL optimum is x=0,y=2: F1 objective1 is NOT Global LB.
    d=dict(lower=np.array([0.,0.]),upper=np.array([10.,2.]),objective=np.array([1.,0.]),
        rhs=np.array([2.]),sense=np.array(['>']),names=np.array(['x','y']),
        row_names=np.array(['coupling']),types=np.array(['C','I']),constant=np.array(0.))
    case=SimpleNamespace(A=sparse.csr_matrix([[1.,1.]]),d=d,case_sha='same_complete_case',output=output)
    e=SimpleNamespace(code=code,root=root,output=output,manifest=manifest,request=request,
        case=case,budget=Budget(output),scope=Scope(request,code,writer=write),models=[])
    real_functions=REAL_ORIGINAL_FUNCTIONS
    functions=dict(real_functions,F1=original_f1(e),FULL_LP=original_full_lp(e))
    # Only the test substitutes stand-ins for original functions. Production
    # has no Boolean opt-out, and rejects non-original callable code objects.
    monkeypatch.setattr(f1_state,'_ORIGINAL_FUNCTIONS',functions)
    e.original_functions=real_functions
    return e


def original_f1(env,*,model=None,fail=False,tamper_replay=None,label=F1_LABEL,seconds=120.):
    def execute(case,budget,progress):
        m=model or Model(case);env.models.append(m)
        try:
            budget.native_optimize(m,component='FEASIBILITY_LP',track='M_START',label=label,requested_seconds=seconds)
            point=np.array(m.attrs['X']);path=case.output/'STATIONARY_DISPATCH_RAW_POINT.npz'
            np.savez_compressed(path,point=point)
            vector=__import__('hashlib').sha256(np.ascontiguousarray(point,dtype='<f8').tobytes()).hexdigest()
            strict=dict(PASS=not fail,case_sha=case.case_sha,
                strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=not fail,
                point_path=str(path),point_file_sha256=_record(path)['sha256'],point_vector_sha256=vector,
                original_matrix_and_96_slot_physical_replay=dict(PASS=not fail,case_sha=case.case_sha,point_sha256=vector))
            if tamper_replay:tamper_replay(strict)
            write(case.output/'STATIONARY_DISPATCH_REPLAY.json',strict)
            return None if fail else point
        finally:m.dispose()
    return execute


def capture(env,**kwargs):
    return env.scope.capture(original_f1(env,**kwargs),env.case,env.budget,
                             pattern=(np.array([1]),np.array([1.])))


def original_full_lp(env,dual=None,*,seconds=300.,throw=False):
    def execute(case,budget,progress):
        if throw:raise RuntimeError('original solver failure')
        model=Model(case,fixed=False);model.Runtime=300.;model.Params.TimeLimit=seconds
        budget.native_optimize(model,component='P1',track='M_LB',label=LP_LABEL,requested_seconds=seconds)
        model.dispose()
        q={} if dual is None else dual
        return q,check(case.A,case.d,q,case_sha=case.case_sha)
    return execute


def select(env,**kwargs):
    return env.scope.select(original_full_lp(env,**kwargs),env.case,env.budget,
                            checker=check,repair=repair_affine_equality_duals)


def test_capture_before_dispose_promoted_after_full_pass_and_receipted(env):
    capture(env)
    assert env.models[0].events.index('read:Pi')<env.models[0].events.index('dispose')
    assert env.scope.state is not None and env.scope.state.native_call['Native_Runtime']==4.25
    receipt=json.loads((env.output/'F1_STATE_ADMISSION.json').read_text())
    assert receipt['warm_state_is_Global_LB'] is False and receipt['Native_calls_added']==0
    assert len(env.budget.calls)==1


def test_failed_original_full_replay_never_promotes_state(env):
    assert capture(env,fail=True) is None
    assert env.scope.state is None
    assert not (env.output/'F1_SAME_ATTEMPT_STATE.npz').exists()
    with pytest.raises(PermissionError,match='ONE_CAPTURE'):
        capture(env)
    assert len(env.budget.calls)==1


@pytest.mark.parametrize('kwargs',[dict(label='UNREGISTERED_F1'),dict(seconds=121.)])
def test_unregistered_f1_call_denied_before_native_delegation(env,kwargs):
    with pytest.raises(PermissionError):capture(env,**kwargs)
    assert env.budget.calls==[] and env.models[0].disposed


@pytest.mark.parametrize('key,value',[
    ('PASS',False),('case_sha','another_day_case'),
    ('strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact',False),
    ('point_vector_sha256','wrong_point'),('point_file_sha256','wrong_bytes')])
def test_fake_original_pass_or_point_receipt_rejected(env,key,value):
    with pytest.raises(PermissionError,match='FULL_REPLAY'):
        capture(env,tamper_replay=lambda receipt:receipt.update({key:value}))
    assert env.scope.state is None


@pytest.mark.parametrize('tamper',[
    lambda e:e.case.d['rhs'].__setitem__(0,3.),
    lambda e:e.case.d['names'].__setitem__(0,'z'),
    lambda e:e.case.A.data.__setitem__(0,2.),
    lambda e:(e.code/'original.py').write_bytes(b'changed source'),
    lambda e:e.scope.request.update(attempt_id='another_attempt'),
    lambda e:e.budget.calls[0].update(Native_Runtime=5.),
    lambda e:(e.output/'F1_SAME_ATTEMPT_STATE.npz').write_bytes(b'changed packet'),
    lambda e:e.scope.state.binding.update(implementation_SHA='invented_source')])
def test_same_attempt_complete_source_axis_native_and_packet_seals(env,tamper):
    capture(env);tamper(env)
    with pytest.raises(PermissionError):env.scope.verify_state(env.case,env.budget)


def test_no_api_admits_state_from_another_attempt(env):
    capture(env)
    other=Scope(env.request,env.code,writer=write);other.state=env.scope.state
    with pytest.raises(PermissionError,match='SAME_ATTEMPT'):
        other.verify_state(env.case,env.budget)


def test_previous_attempts_are_never_eligible(env):
    r=dict(env.request,previous_attempts=['old_attempt'])
    with pytest.raises(PermissionError,match='CURRENT_ATTEMPT'):
        Scope(r,env.code,writer=write)


@pytest.mark.parametrize('field,value',[
    ('native_budget_seconds',5401),('Threads',2),('P2_calls',1),
    ('wall_budget_seconds',5400),('day','2025-06-01'),('worker_slot',4),('attempt_id','../old')])
def test_original_budget_thread_date_and_output_policy_not_relaxed(env,field,value):
    with pytest.raises(PermissionError):Scope(dict(env.request,**{field:value}),env.code,writer=write)


def test_f1_native_objective_and_fixed_bound_certificate_not_global_lb(env):
    capture(env)
    dual,cert=select(env)
    assert cert['exact_bound']=='0' and cert['F1_Native_objective_used'] is False
    assert cert['F1_restricted_bounds_used'] is False
    assert len(env.budget.calls)==2 and env.budget.calls[-1]['requested_seconds']==300.
    # Restricted-box evaluation would incorrectly give1, and is never used.
    restricted=copy.deepcopy(env.case.d);restricted['lower'][1]=restricted['upper'][1]=1.
    assert check(env.case.A,restricted,{'0':'1'},case_sha=env.case.case_sha)['exact_bound']=='1'
    assert check(env.case.A,env.case.d,{'0':'1'},case_sha=env.case.case_sha)['exact_bound']=='0'


def test_original_full_lp_stronger_proof_is_retained(env):
    env.case.A=sparse.csr_matrix([[1.,0.]])
    env.case.d['rhs'][0]=1.
    capture(env,model=Model(env.case,pi=(0.,)))
    q,cert=select(env,dual={'0':'1'})
    assert q=={'0':'1'} and cert['selected_candidate']=='ORIGINAL_FULL_LP'
    assert cert['exact_bound']=='1'


def test_f1_pi_stronger_full_domain_proof_updates_dual_certificate_together(env):
    env.case.A=sparse.csr_matrix([[1.,0.]])
    env.case.d['rhs'][0]=1.
    capture(env)
    q,cert=select(env)
    assert cert['selected_candidate']=='CURRENT_ATTEMPT_F1_ORIGINAL_ROW_PI'
    assert cert['exact_bound']=='1' and q=={'0':'1'}
    saved_q=json.loads((env.output/'INITIAL_EXACT_ORIGINAL_DUAL.json').read_text())
    saved_cert=json.loads((env.output/'INITIAL_EXACT_LB_CERTIFICATE.json').read_text())
    replay=check(env.case.A,env.case.d,saved_q,case_sha=env.case.case_sha)
    assert replay['exact_bound']==saved_cert['exact_bound']==cert['exact_bound']


def test_original_full_lp_failure_propagates_without_replacing_it_by_f1(env):
    capture(env)
    with pytest.raises(RuntimeError,match='original solver'):
        select(env,throw=True)
    assert not (env.output/'INITIAL_EXACT_LB_CERTIFICATE.json').exists()


@pytest.mark.parametrize('seconds',[0.,301.])
def test_original_full_lp_per_call_limit_cannot_increase(env,seconds):
    capture(env)
    with pytest.raises(PermissionError,match='LIMIT_OR_PRECISION'):
        select(env,seconds=seconds)


def test_original_full_lp_is_mandatory_even_with_usable_f1_pi(env):
    capture(env)
    with pytest.raises(PermissionError,match='CODE_OBJECT_REQUIRED'):
        env.scope.select(lambda *args:({},{}),env.case,env.budget,checker=check,repair=repair_affine_equality_duals)


def test_interior_fixed_nonbasic_uses_complete_start_pair_without_inventing_basis(env):
    capture(env);full=Model(env.case,fixed=False)
    receipt=env.scope.install(full,env.case,env.budget)
    assert receipt['mode']=='COMPLETE_SAME_ATTEMPT_PRIMAL_DUAL_START'
    assert 'INTERIOR' in receipt['basis_fallback_reason']
    assert full.saved['PStart'][1]==[1.,1.] and full.saved['DStart'][1]==[1.]
    assert 'VBasis' not in full.saved and full.Params.LPWarmStart==2
    assert len(env.budget.calls)==1 and full.Params.Method==1


def test_fixed_upper_endpoint_remaps_lower_status_to_original_upper(env):
    env.case.d['upper'][1]=1.
    capture(env);full=Model(env.case,fixed=False)
    receipt=env.scope.install(full,env.case,env.budget)
    assert receipt['mode']=='COMPLETE_SAME_ATTEMPT_BASIS'
    assert full.saved['VBasis'][1]==[0,-2] and full.saved['CBasis'][1]==[-1]
    assert receipt['remapped_nonbasic_endpoints']==1
    assert 'PStart' not in full.saved


def test_fixed_lower_endpoint_uses_original_lower_status(env):
    env.case.d['lower'][1]=1.
    capture(env);full=Model(env.case,fixed=False)
    assert env.scope.install(full,env.case,env.budget)['mode']=='COMPLETE_SAME_ATTEMPT_BASIS'
    assert full.saved['VBasis'][1]==[0,-1]


def test_missing_pi_and_interior_basis_keep_original_cold_lp(env):
    capture(env,model=Model(env.case,pi=None));full=Model(env.case,fixed=False)
    receipt=env.scope.install(full,env.case,env.budget)
    assert receipt['mode']=='COLD_ORIGINAL_FULL_LP' and full.saved=={}
    assert full.Params.LPWarmStart==-1
    _,cert=select(env)
    assert cert['exact_bound']=='0' and len(env.budget.calls)==2


@pytest.mark.parametrize('basis,pi',[(False,(1.,)),(False,None)])
def test_partial_basis_falls_back_without_synthesizing_statuses(env,basis,pi):
    capture(env,model=Model(env.case,basis=basis,pi=pi));full=Model(env.case,fixed=False)
    receipt=env.scope.install(full,env.case,env.budget)
    assert receipt['mode']==('COMPLETE_SAME_ATTEMPT_PRIMAL_DUAL_START' if pi else 'COLD_ORIGINAL_FULL_LP')


def test_nonfinite_pi_not_admitted_as_dual_start_or_bound(env):
    capture(env,model=Model(env.case,pi=(np.inf,)));full=Model(env.case,fixed=False)
    assert env.scope.install(full,env.case,env.budget)['mode']=='COLD_ORIGINAL_FULL_LP'
    assert select(env)[1]['exact_bound']=='0'


@pytest.mark.parametrize('mutate',[
    lambda m:m.A.data.__setitem__(0,9.),
    lambda m:m.attrs['Obj'].__setitem__(0,2.),
    lambda m:m.attrs['LB'].__setitem__(0,.1),
    lambda m:setattr(m,'ObjCon',3.),
    lambda m:setattr(m.Params,'Threads',2)])
def test_warmstart_full_matrix_domain_objective_threads_roundtrip(env,mutate):
    capture(env);full=Model(env.case,fixed=False);mutate(full)
    with pytest.raises(PermissionError):env.scope.install(full,env.case,env.budget)
    assert not full.saved


def test_warmstart_preserves_precision_and_records_presolve_option(env):
    capture(env);full=Model(env.case,fixed=False)
    old={k:getattr(full.Params,k) for k in PRECISION}
    r=env.scope.install(full,env.case,env.budget)
    assert old=={k:getattr(full.Params,k) for k in PRECISION}
    assert r['original_math_roundtrip']['PASS'] is True and r['LPWarmStart']==2
    assert r['original_full_LP_not_removed'] is True and r['performance_benefit_claimed'] is False
    with pytest.raises(PermissionError,match='ONE_FRESH_FULL_LP'):
        env.scope.install(full,env.case,env.budget)


def test_fake_runtime_or_precision_in_native_receipt_rejected(env):
    model=Model(env.case);model.Params.NumericFocus=1
    with pytest.raises(PermissionError,match='ACTUAL_NATIVE_PARAMETERS'):
        capture(env,model=model)
    assert model.disposed and env.scope.state is None


def test_production_guard_requires_original_function_code_objects(env,monkeypatch):
    monkeypatch.setattr(f1_state,'_ORIGINAL_FUNCTIONS',env.original_functions)
    with pytest.raises(PermissionError,match='CODE_OBJECT_REQUIRED:F1'):
        capture(env)
    with pytest.raises(PermissionError,match='CODE_OBJECT_REQUIRED:FULL_LP'):
        select(env)
    assert env.budget.calls==[]


def test_unbounded_original_helper_uses_original_equality_envelope_not_fixed_bounds(env):
    env.case.A=sparse.csr_matrix([[1.,0.],[-1.,1.]])
    env.case.d.update(rhs=np.array([1.,0.]),sense=np.array(['>','=']),
        row_names=np.array(['minimum','y_binding']),lower=np.array([0.,-np.inf]),
        upper=np.array([10.,np.inf]))
    capture(env,model=Model(env.case,pi=(1.,0.)))
    q,cert=select(env)
    assert cert['exact_bound']=='1'
    proof=cert['finite_box_original_row_implication']
    assert proof['independent_replay']['all_original_feasible_points_contained'] is True
    assert proof['original_model_bounds_mutated'] is False
    assert np.isneginf(env.case.d['lower'][1]) and np.isposinf(env.case.d['upper'][1])
    assert check(env.case.A,env.case.d,q,case_sha=env.case.case_sha)['exact_bound']=='1'


def test_preserved_original_f1_and_full_lp_code_objects_end_to_end_without_native(env,monkeypatch):
    """Exercise actual source bytecode with small stand-in backend/gate only."""
    from v42_may_campaign_native90.a_routing import rebound
    monkeypatch.setattr(f1_state,'_ORIGINAL_FUNCTIONS',env.original_functions)
    env.case.A=sparse.csr_matrix([[1.,0.]])
    env.case.d['rhs'][0]=1.
    env.case.bundle=dict(day='2025-05-01')
    f1_model=Model(env.case,fixed=False,pi=(1.,))
    full_model=Model(env.case,fixed=False,pi=(0.,));full_model.Runtime=300.

    def gate(case,path,evidence):
        with np.load(path,allow_pickle=False) as z:point=z['point'].copy()
        vector=__import__('hashlib').sha256(np.ascontiguousarray(point,dtype='<f8').tobytes()).hexdigest()
        return dict(PASS=True,strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
            point_path=str(path),point_file_sha256=_record(path)['sha256'],point_vector_sha256=vector,
            original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha=case.case_sha,point_sha256=vector))

    original_f1_code=env.original_functions['F1']
    f1=rebound(original_f1_code,dict(original_f1_code.__globals__,atomic=write,
        discrete_stationary=lambda c:(np.array([1]),np.array([1.])),
        original=SimpleNamespace(_model=lambda c,continuous:(f1_model,{}),_strict_ub=gate)))
    point=env.scope.capture(f1,env.case,env.budget,pattern=(np.array([1]),np.array([1.])))
    assert np.array_equal(point,[1.,1.]) and f1_model.disposed
    original_lp_code=env.original_functions['FULL_LP']
    lp=rebound(original_lp_code,dict(original_lp_code.__globals__,atomic=write,
        _model=lambda c,continuous:(full_model,{}),check_rational_dual_certificate=check))
    # Future module hook changes the alias. Frozen original-code authority
    # must keep recognizing the byte-identical rebound function.
    import v42_may_campaign_native90.m_stage as original_module
    monkeypatch.setattr(original_module,'_fresh_lp_dual',lambda *args:None)
    dual,cert=env.scope.full_lp_adapter(lp,env.case,env.budget)
    assert lp.__code__ is original_lp_code.__code__ and f1.__code__ is original_f1_code.__code__
    assert full_model.disposed and 'PStart' in full_model.saved and 'DStart' in full_model.saved
    assert cert['exact_bound']=='1' and dual=={'0':'1'}
    assert [c['requested_seconds'] for c in env.budget.calls]==[120.,300.]
    assert [c['Native_Runtime'] for c in env.budget.calls]==[4.25,300.]


def test_production_proof_scope_lazy_hooks_promote_warm_and_restore_original_aliases(env,monkeypatch):
    from v42_autonomous_b2 import worker,f1_basis
    from v42_b2_seed_recovery_v19 import initialization,fixed_pattern
    from v42_may_campaign_native90 import m_stage
    from v42_may_campaign_native90.a_routing import rebound
    monkeypatch.setattr(f1_state,'_ORIGINAL_FUNCTIONS',env.original_functions)
    env.case.A=sparse.csr_matrix([[1.,0.]]);env.case.d['rhs'][0]=1.
    env.case.bundle=dict(day='2025-05-01')
    f1_model=Model(env.case,fixed=False,pi=(1.,))
    full_model=Model(env.case,fixed=False,pi=(0.,));full_model.Runtime=300.
    pattern=lambda c:(np.array([1]),np.array([1.]))
    monkeypatch.setattr(fixed_pattern,'discrete_stationary',pattern)

    def gate(case,path,evidence):
        with np.load(path,allow_pickle=False) as z:point=z['point'].copy()
        vector=__import__('hashlib').sha256(np.ascontiguousarray(point,dtype='<f8').tobytes()).hexdigest()
        return dict(PASS=True,strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
            point_path=str(path),point_file_sha256=_record(path)['sha256'],point_vector_sha256=vector,
            original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha=case.case_sha,point_sha256=vector))

    original_f1_code=env.original_functions['F1'];original_lp_code=env.original_functions['FULL_LP']
    real_f1=rebound(original_f1_code,dict(original_f1_code.__globals__,atomic=write,
        discrete_stationary=pattern,original=SimpleNamespace(_model=lambda c,continuous:(f1_model,{}),_strict_ub=gate)))
    real_lp=rebound(original_lp_code,dict(original_lp_code.__globals__,atomic=write,
        _model=lambda c,continuous:(full_model,{}),check_rational_dual_certificate=check))
    monkeypatch.setattr(initialization,'validated_start',real_f1)
    monkeypatch.setattr(m_stage,'_fresh_lp_dual',real_lp)
    scopes=[];original_scope=f1_basis.Scope
    def factory(request,code_root):
        scopes.append(original_scope(request,env.code,writer=write));return scopes[-1]
    monkeypatch.setattr(f1_basis,'Scope',factory)
    inputs=env.root/'immutable_inputs';inputs.mkdir()
    for name in ('B2_FIXED_AIDC.json','PLANNING_PHYSICAL.npz','linked.json'):
        (inputs/name).write_bytes(b'unchanged input')
    linked=_record(inputs/'linked.json')
    write(inputs/'NATIVE_INPUT.json',dict(route_table=linked,electrical_certificate=linked))
    request=dict(env.request,input_folder=str(inputs))
    with worker.proof_scope(request,dict(execution_SHA=env.manifest['execution_SHA'])):
        assert scopes==[]  # No manifest/source state I/O in routing-only scope.
        assert initialization.validated_start is not real_f1 and m_stage._fresh_lp_dual is not real_lp
        point=initialization.validated_start(env.case,env.budget)
        assert np.array_equal(point,[1.,1.]) and scopes[0].state is not None
        q,cert=m_stage._fresh_lp_dual(env.case,env.budget)
        assert q=={'0':'1'} and cert['exact_bound']=='1' and len(scopes)==1
        assert full_model.saved['PStart'][1]==[1.,1.]
    assert initialization.validated_start is real_f1 and m_stage._fresh_lp_dual is real_lp
    assert f1_model.disposed and full_model.disposed and len(env.budget.calls)==2
    assert [c['requested_seconds'] for c in env.budget.calls]==[120.,300.]
    assert real_f1.__code__ is original_f1_code.__code__ and real_lp.__code__ is original_lp_code.__code__
