"""Native/model-denied original code/guard/ledger/restore tests."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace
from types import MethodType

import gurobipy as gp
import numpy as np
import pytest
from scipy import sparse
from v42_autonomous_b2 import rmp_presolve as draft
from v42_autonomous_b2.worker import ReceiptDateBudget
from v42_m1_hybrid import dw
from v42_m1_hybrid.blocks import build_blocks
from v42_may_campaign_native90 import execution
from v42_b2_seed_recovery_v19 import execution as original_guard


@pytest.fixture(autouse=True)
def deny_real_models(monkeypatch):
    attempts=[]
    def denied(*args,**kwargs):
        attempts.append((args,kwargs));raise AssertionError('V30_NO_REAL_GUROBI_MODEL_ALLOWED')
    monkeypatch.setattr(gp,'Model',denied)
    yield
    assert attempts==[]


def write(path,value):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    Path(path).write_text(json.dumps(value,sort_keys=True,allow_nan=False),encoding='utf-8')


class Variables:
    def __init__(self,raw,n,kwargs):
        self.raw=raw;self.n=n;self.names=None
        self.X=np.r_[np.zeros(n-4),np.ones(4)] if n>=4 else np.zeros(n)
    @property
    def VarName(self):return self.names
    @VarName.setter
    def VarName(self,value):self.names=value


class Raw:
    def __init__(self,name):
        self.Params=SimpleNamespace(OutputFlag=0,Method=1,Threads=1,TimeLimit=float('inf'),Presolve=-1,MIPGap=.0001,
            FeasibilityTol=1e-8,OptimalityTol=1e-8,NumericFocus=0,ScaleFlag=-1)
        self.attrs={};self.entries=[];self.disposed=False;self.error=None
        self.Status=2;self.SolCount=0;self.Runtime=2.25;self.ObjCon=0.;self.Work=3.
    def setParam(self,k,v):setattr(self.Params,k,v)
    def addMVar(self,n,**kwargs):
        self.NumVars=n;self.attrs.update(LB=np.array(kwargs['lb']),UB=np.array(kwargs['ub']),Obj=np.array(kwargs['obj']),VType=np.full(n,'C'))
        self.variables=Variables(self,n,kwargs);return self.variables
    def addMConstr(self,matrix,variables,sense,rhs):
        self.matrix=matrix.copy();self.NumConstrs=matrix.shape[0]
        self.attrs.update(Sense=np.array(sense),RHS=np.array(rhs))
        return SimpleNamespace(Pi=np.zeros(matrix.shape[0]))
    def update(self):pass
    def getA(self):return self.matrix.copy()
    def getAttr(self,key,*args):return self.attrs[key].copy()
    def optimize(self,callback=None):
        # Run unchanged original scope/Threads/date/P1 guard. No backend.
        original_guard.guard(self)
        self.entries.append(dict(params=vars(self.Params).copy(),scope=dict(execution._model.get())))
        if callback is not None:callback(self,gp.GRB.Callback.POLLING)
        if self.error:raise self.error
        return 'FAKE_BACKEND_ONLY_NOT_NATIVE'
    def dispose(self):self.disposed=True


class Model(draft.PresolveFreeRMP):
    def __init__(self,name):super().__init__(name,factory=Raw)


@pytest.fixture
def env(tmp_path,monkeypatch):
    root=tmp_path/'campaign';out=root/'dates/B2/2025-05-01/attempts/fresh/output';out.mkdir(parents=True)
    sources={k:draft._record(m.__file__)['sha256'] for k,m in (
        ('v42_m1_hybrid/dw.py',dw),('v42_autonomous_b2/dw_native.py',draft.dw_native),
        ('v42_b2_seed_recovery_v19/budget.py',draft.original_budget),
        ('v42_may_campaign_native90/execution.py',execution))}
    all_sources=draft.deployment.sources();source_sha=draft.deployment.digest(all_sources)
    input_folder=root/'input';input_folder.mkdir()
    manifest=dict(schema='V42_AUTONOMOUS_B2_V20',run_id='ownrun',execution_SHA=source_sha,
        builder_original_sources=sources,execution_sources=all_sources,prior_attempts={},inherited_B1_results={},
        input_folders={'2025-05-01':str(input_folder)},attempt_ids=['fresh'],attempt_id='fresh',
        initialization_native_limit_seconds=5400)
    mf=root/'manifest.json';write(mf,manifest)
    request=dict(root=str(root),output=str(out),run_id='ownrun',arm='B2',day='2025-05-01',attempt_id='fresh',worker_slot=1,
        Threads=1,P2_calls=0,native_budget_seconds=5400,wall_budget_seconds=None,target_gap=.03,
        input_folder=str(input_folder),manifest=str(mf),manifest_SHA=draft._record(mf)['sha256'],implementation_SHA=source_sha,
        result=str(out.parent/'RESULT.json'),progress=str(out.parent/'progress.json'),error=str(out.parent/'error.json'))
    token=execution._active.set(dict(request=request,manifest=manifest));old_model=execution._model.get()
    monkeypatch.setattr(original_guard,'assert_peers',lambda r:None)
    monkeypatch.setattr(draft,'PresolveFreeRMP',Model)
    monkeypatch.setattr(draft,'_APPROVED_WRAPPER_TYPE',Model)
    monkeypatch.setattr(draft,'_RAW_MODEL_TYPE',Raw)
    monkeypatch.setattr(draft,'_RAW_OPTIMIZE',Raw.optimize)
    monkeypatch.setattr(draft,'_RAW_CODE',Raw.optimize.__code__)
    budget=ReceiptDateBudget(out.parent/'NATIVE_RUNTIME_LEDGER.json')
    raw_matrix=np.zeros((7,6))
    for i in range(6):raw_matrix[i,i]=1.
    raw_matrix[6,4]=1.;raw_matrix[6,5]=-1.
    d=dict(names=np.array([f'route_flow[M{i},0]' for i in range(1,5)]+['Pch[M1,0,0]','rho_max']),
        lower=np.zeros(6),upper=np.array([1.,1.,1.,1.,1.,10.]),types=np.array(['B','B','B','B','C','C']),
        objective=np.array([0.,0.,0.,0.,0.,1.]),rhs=np.array([0.,0.,0.,0.,0.,10.,0.]),
        sense=np.array(['>','>','>','>','>','<','<']),row_names=np.array([str(i) for i in range(7)]),constant=np.array(.5))
    case=SimpleNamespace(A=sparse.csr_matrix(raw_matrix),d=d,point=np.array([1.,1.,1.,1.,1e-18,4.]),case_sha='tiny_same_case')
    decomp=build_blocks(case)
    def output(p):p=Path(p);p.mkdir(parents=True,exist_ok=True);return p
    runner=draft.scoped_runner(dw.run,output,write)
    model=runner.original_run.__globals__['build_master'](case,decomp,{},out/'master')[0]
    e=SimpleNamespace(root=root,out=out,mf=mf,request=request,manifest=manifest,budget=budget,
        case=case,decomp=decomp,runner=runner,model=model,proxy=draft.BudgetProxy(budget,write,runner.binding),output=output)
    try:yield e
    finally:
        execution._active.reset(token)
        assert execution._model.get() is old_model and draft._ENTRY.get() is None


def invoke(e,**changes):
    kwargs=dict(track='RMP',label=draft.LABEL,requested_seconds=30);kwargs.update(changes)
    return e.proxy.optimize(e.model,**kwargs)


def test_single_original_budget_native_guard_row_transport_and_measured_ledger(env):
    expected=env.model.getA();rhs=env.model.getAttr('RHS');exponents=env.model._exponents.copy()
    receipt=invoke(env)
    assert receipt==env.budget.calls[-1] and len(env.budget.calls)==1
    assert env.budget.used()==2.25 and json.loads(env.budget.path.read_text())['measured_Native_Runtime']==2.25
    assert env.model.Params.Presolve==0 and env.model.Params.Method==1
    assert env.model._model.entries[0]['scope']['model'] is env.model._model
    assert env.model._model.entries[0]['params']['TimeLimit']==30
    assert {k:env.model._model.entries[0]['params'][k] for k in draft.PRECISION}==draft.PRECISION
    assert (env.model.getA()-expected).nnz==0 and np.array_equal(env.model.getAttr('RHS'),rhs)
    assert np.array_equal(env.model._exponents,exponents) and draft._ENTRY.get() is None
    result=json.loads((env.out/'master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert result['Native_call_completed'] and result['completed_original_Native_call']['Native_Runtime']==2.25
    assert result['restricted_master_objective_is_Global_LB'] is False


@pytest.mark.parametrize('change',[
    dict(track='UB'),dict(label='OTHER'),dict(requested_seconds=31),dict(requested_seconds=0),
    dict(requested_seconds=True),dict(requested_seconds=float('nan')),dict(requested_seconds=120)])
def test_wrong_call_denied_before_original_budget_or_backend(env,change):
    with pytest.raises(PermissionError):invoke(env,**change)
    assert env.budget.calls==[] and env.model._model.entries==[] and env.budget.inflight is None


def test_second_budget_entry_denied_before_delegate(env):
    invoke(env)
    with pytest.raises(PermissionError):invoke(env)
    assert len(env.budget.calls)==1 and len(env.model._model.entries)==1


def test_direct_model_optimize_has_no_unscoped_opt_out(env):
    with execution.native_scope(env.model,'P1','RMP'):
        with pytest.raises(PermissionError,match='APPROVED_MODEL_ENTRY'):env.model.optimize()
    assert env.model._model.entries==[]


@pytest.mark.parametrize('field,value',[
    ('Threads',2),('P2_calls',1),('native_budget_seconds',5401),('wall_budget_seconds',5400),('target_gap',.05),('arm','B1')])
def test_original_request_policy_never_relaxed(env,field,value):
    env.request[field]=value
    with pytest.raises(PermissionError):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


@pytest.mark.parametrize('mutate',[
    lambda e:e.model._model.attrs['Obj'].__setitem__(0,2.),
    lambda e:e.model._model.attrs['UB'].__setitem__(0,2.),
    lambda e:e.model._model.matrix.data.__setitem__(0,2.),
    lambda e:e.model._model.attrs['RHS'].__setitem__(0,2.),
    lambda e:e.request.update(implementation_SHA='other'),
    lambda e:e.mf.write_text('{}'),
    lambda e:e.budget.path.write_text('{}')])
def test_source_matrix_domain_rhs_or_ledger_drift_denied_before_native(env,mutate):
    mutate(env)
    with pytest.raises((PermissionError,ValueError,KeyError)):invoke(env)
    assert env.model._model.entries==[] and env.budget.calls==[]


def test_unknown_native_prefix_is_never_replaced_with_zero(env):
    env.budget.calls=[dict(Native_Runtime=None,runtime_unavailable=True)];env.budget.persist()
    with pytest.raises(PermissionError,match='UNKNOWN_NATIVE'):invoke(env)
    assert env.model._model.entries==[]


def test_backend_failure_preserves_original_measured_runtime_and_restores_all_scopes(env):
    env.model._model.error=RuntimeError('MOCK_BACKEND_FAILURE')
    with pytest.raises(RuntimeError,match='MOCK_BACKEND_FAILURE'):invoke(env)
    assert draft._ENTRY.get() is None and execution._model.get() is None
    assert env.budget.inflight is None and env.budget.used()==2.25
    assert env.budget.calls[-1]['status']=='FAILED' and env.budget.calls[-1]['Native_Runtime']==2.25
    result=json.loads((env.out/'master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert result['status']=='FAILED' and result['Native_call_completed'] is False


def test_original_builder_run_code_local_replay_dispose_pi_and_context_restoration(env):
    assert env.runner.original_run.__code__ is dw.run.__code__
    assert env.runner.original_build.__code__ is dw.build_master.__code__
    assert env.runner.original_build.__globals__['matrix_replay'] is dw.matrix_replay
    assert env.runner.original_build.__globals__['verify_decomposition'] is dw.verify_decomposition
    result=env.runner(env.case,env.decomp,{},env.budget,env.out/'actual_original_path',seconds=30)
    assert result['native']['requested_seconds']==30 and result['native']['Native_Runtime']==2.25
    assert result['identity']['column_count_by_unit']=={'M1':1,'M2':1,'M3':1,'M4':1}
    assert result['dual_status']=='FINITE_ORIGINAL_ROW_DUAL_AVAILABLE_NOT_NATIVE_OBJECTIVE_PROOF'
    assert result['restricted_master_is_Global_LB'] is False
    assert draft._ENTRY.get() is None and execution._model.get() is None
    assert len(env.budget.calls)==1 and env.budget.used()==2.25


def test_original_preregistered_seconds_guard_remains_active(env):
    with pytest.raises(ValueError,match='30_SECOND_RMP'):env.runner(env.case,env.decomp,{},env.budget,env.out/'denied',seconds=31)
    assert env.budget.calls==[]


def test_replaced_original_run_code_is_not_admitted(env):
    with pytest.raises(PermissionError,match='ORIGINAL_RUN_CODE'):draft.scoped_runner(lambda *a:None,env.output,write)


def test_original_remaining_total_budget_caps_rmp_below_30_seconds(env):
    env.budget.calls=[dict(component='P1',track='EARLIER',label='OWN_MEASURED_CALL',
        Native_Runtime=5390.,runtime_unavailable=False)]
    env.budget.native_used=5390.;env.budget.persist()
    result=invoke(env)
    assert result['requested_seconds']==30 and result['effective_TimeLimit']==10
    assert env.model._model.entries[0]['params']['TimeLimit']==10
    assert env.budget.used()==5392.25 and len(env.budget.calls)==2


def test_original_exhausted_budget_denies_before_backend_and_scope_restores(env):
    env.budget.calls=[dict(Native_Runtime=5400.,runtime_unavailable=False)]
    env.budget.native_used=5400.;env.budget.persist()
    with pytest.raises(TimeoutError,match='EXHAUSTED'):invoke(env)
    assert len(env.budget.calls)==1 and env.model._model.entries==[]
    assert env.budget.used()==5400 and env.budget.inflight is None


@pytest.mark.parametrize('field,value',[
    ('Method',0),('Threads',2),('TimeLimit',31),('FeasibilityTol',1e-8),
    ('OptimalityTol',1e-8),('NumericFocus',2),('ScaleFlag',1)])
def test_live_actual_parameters_cannot_change_after_original_budget_admission(env,field,value):
    # The original budget calls this progress hook after setting/persisting
    # precision/cap but before its guarded Native delegation.
    env.model._model.Runtime=0.
    env.budget.progress=lambda value_:setattr(env.model.Params,field,value)
    with pytest.raises(PermissionError,match='ACTUAL_ORIGINAL|V19_B2_P1_THREADS_ONE_ONLY'):invoke(env)
    assert env.model._model.entries==[] and env.budget.used()==0
    assert draft._ENTRY.get() is None and execution._model.get() is None


@pytest.mark.parametrize('mutation',[
    lambda row:row.update(label='OTHER'),
    lambda row:row.update(Native_objective_basis='AUXILIARY_FEASIBILITY_ZERO'),
    lambda row:row.update(extra_nonoriginal_diagnostic=True)])
def test_only_original_unpersisted_objective_diagnostic_is_admitted(env,mutation):
    env.model._model.Runtime=0.
    def alter(value):
        if env.budget.inflight is not None:mutation(env.budget.inflight)
    env.budget.progress=alter
    with pytest.raises(PermissionError,match='PERSISTED_NATIVE_LEDGER_DRIFT'):invoke(env)
    assert env.model._model.entries==[] and env.budget.used()==0


def test_source_or_original_matrix_cannot_change_during_budget_progress(env):
    env.model._model.Runtime=0.
    def alter(value):env.model._model.matrix.data[0]*=2.
    env.budget.progress=alter
    with pytest.raises(ValueError,match='SCALED_NATIVE_MATRIX_DRIFT'):invoke(env)
    assert env.model._model.entries==[] and env.budget.used()==0


def test_wrong_original_native_accounting_code_denied_before_budget(env,monkeypatch):
    monkeypatch.setattr(env.budget,'native_optimize',lambda *args,**kwargs:None)
    with pytest.raises(PermissionError,match='ORIGINAL_DELEGATE'):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


def test_existing_original_row_scoped_builder_is_peeled_without_global_mutation(env):
    before=dw.build_master;original_run=dw.run
    row_builder=draft.dw_native.scoped_builder(before,env.output,write)
    scoped=draft.rebound(original_run,dict(original_run.__globals__,build_master=row_builder))
    runner=draft.scoped_runner(scoped,env.output,write)
    assert runner.original_build.__code__ is before.__code__
    result=runner(env.case,env.decomp,{},env.budget,env.out/'already_scoped')
    assert result['native']['effective_TimeLimit']==30 and env.budget.used()==2.25
    assert dw.build_master is before and dw.run is original_run
    assert draft._ENTRY.get() is None and execution._model.get() is None


@pytest.mark.parametrize('callback',[
    lambda model,where:None,
    lambda model,where:model.optimize(),
    lambda model,where:(_ for _ in ()).throw(RuntimeError('CALLBACK_FAILURE'))])
def test_external_callback_absent_from_original_dw_is_denied_before_budget(env,callback):
    with pytest.raises(PermissionError,match='EXACT_ORIGINAL_ONE_30_SECOND_CALL'):invoke(env,callback=callback)
    assert env.budget.calls==[] and env.model._model.entries==[]


@pytest.mark.parametrize('target', ['raw','wrapper','budget'])
def test_live_delegate_substitution_denied_before_raw_call(env,monkeypatch,target):
    env.model._model.Runtime=0.
    def alter(value):
        if env.budget.inflight is None:return
        replacement=MethodType(lambda *a,**k:None,env.model._model)
        if target=='raw':monkeypatch.setattr(env.model._model,'optimize',replacement)
        elif target=='wrapper':monkeypatch.setattr(Model,'optimize',lambda *a,**k:None)
        else:monkeypatch.setattr(env.budget,'optimize',replacement)
    env.budget.progress=alter
    with pytest.raises(PermissionError):invoke(env)
    assert env.model._model.entries==[] and env.budget.used()==0


@pytest.mark.parametrize('target', ['dw_run','dw_build','matrix_replay','native_budget','precision'])
def test_inplace_original_code_mutation_is_detected_before_native(env,monkeypatch,target):
    functions=dict(dw_run=draft._ORIGINAL_RUN,dw_build=draft._ORIGINAL_BUILD,
        matrix_replay=dw.matrix_replay,native_budget=draft._ORIGINAL_NATIVE_OPTIMIZE,
        precision=draft._ORIGINAL_PRECISION)
    func=functions[target]
    monkeypatch.setattr(func,'__code__',(lambda *a,**k:None).__code__)
    with pytest.raises(PermissionError,match='IMMUTABLE_ORIGINAL_CODE'):invoke(env)
    assert env.model._model.entries==[] and env.budget.calls==[]


def test_rebound_builder_helper_alias_mutation_during_progress_denied(env,monkeypatch):
    env.model._model.Runtime=0.
    def alter(value):
        if env.budget.inflight is not None:
            draft._ENTRY.get().raw_model.Runtime=0.
            monkeypatch.setitem(env.runner.original_build.__globals__,'matrix_replay',lambda *a:dict(PASS=True))
    env.budget.progress=alter
    with pytest.raises(PermissionError,match='REBOUND_CODE_OR_HELPER_DRIFT'):
        env.runner(env.case,env.decomp,{},env.budget,env.out/'helper_drift')
    assert env.budget.used()==0


@pytest.mark.parametrize('target',['wrapper','raw','inherited_optimizer','scope_generator'])
def test_code_mutation_in_original_pre_native_progress_cannot_bypass_entry(env,monkeypatch,target):
    choices=dict(wrapper=draft._WRAPPER_OPTIMIZE,raw=Raw.optimize,
        inherited_optimizer=draft._ORIGINAL_INHERITED_OPTIMIZE,
        scope_generator=draft._ORIGINAL_SCOPE_GENERATOR)
    original_progress=lambda value:None
    def closure_code():
        marker=None
        def replacement(*a,**k):return marker
        return replacement.__code__
    def alter(value):
        if env.budget.inflight is None:return
        env.model._model.Runtime=0.
        code=closure_code() if choices[target].__code__.co_freevars else (lambda *a,**k:None).__code__
        monkeypatch.setattr(choices[target],'__code__',code)
    env.budget.progress=alter
    with pytest.raises(PermissionError):invoke(env)
    assert env.model._model.entries==[] and env.budget.used()==0
    assert env.budget.progress is alter and draft._ENTRY.get() is None


def test_model_without_original_scoped_build_provenance_is_denied(env):
    object.__setattr__(env.model,'_rmp_build_binding',None)
    with pytest.raises(PermissionError,match='ORIGINAL_REBOUND_BUILD'):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


def test_initial_progress_guard_failure_preserves_unfinished_original_admission(env):
    def alter(value):
        if env.budget.inflight is not None:env.model._model.matrix.data[0]*=2.
    env.budget.progress=alter
    with pytest.raises(ValueError,match='MATRIX_DRIFT'):invoke(env)
    ledger=json.loads(env.budget.path.read_text(encoding='utf-8'))
    # Original v19 starts its try/finally after this first progress callback.
    # Keep its unfinished persisted admission for conservative quarantine;
    # do not clear it or fabricate a completed known-zero Native receipt.
    assert ledger['inflight']['status']=='IN_FLIGHT' and ledger['calls']==[]
    assert env.budget.inflight is not None and env.model._model.entries==[]
    assert env.budget.progress is alter and draft._ENTRY.get() is None


@pytest.mark.parametrize('mutation',[
    lambda m:m['execution_sources'].pop('v42_autonomous_b2/rmp_presolve.py'),
    lambda m:m['execution_sources'].pop('v42_b2_seed_recovery_v19/policy.py'),
    lambda m:m['execution_sources'].update({'v42_autonomous_b2/unowned_extra.py':'0'*64}),
    lambda m:m['execution_sources'].update({'v42_autonomous_b2/rmp_presolve.py':'0'*64})])
def test_complete_source_map_and_self_sha_required_before_native(env,mutation):
    m=copy.deepcopy(env.manifest);mutation(m);m['execution_SHA']=draft.deployment.digest(m['execution_sources'])
    write(env.mf,m);env.request.update(manifest_SHA=draft._record(env.mf)['sha256'],implementation_SHA=m['execution_SHA'])
    with pytest.raises(PermissionError):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


def test_declared_source_digest_cannot_be_replaced_with_equal_map_unrelated_digest(env):
    m=copy.deepcopy(env.manifest);m['execution_SHA']='0'*64;write(env.mf,m)
    env.request.update(manifest_SHA=draft._record(env.mf)['sha256'],implementation_SHA='0'*64)
    with pytest.raises(PermissionError):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


def test_equal_bytes_loaded_from_mutable_parallel_checkout_do_not_satisfy_source_root(env,monkeypatch):
    parallel=env.root/'parallel_checkout/v42_m1_hybrid/dw.py';parallel.parent.mkdir(parents=True)
    parallel.write_bytes(Path(dw.__file__).read_bytes())
    monkeypatch.setattr(dw,'__file__',str(parallel))
    with pytest.raises(PermissionError,match='ORIGINAL_SOURCE_PATH_OR_SHA'):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


@pytest.mark.parametrize('field,value',[
    ('attempt_id','unadmitted_attempt'),('day','2025-05-02'),('output','D:/unowned_rmp_output')])
def test_original_deployment_attempt_date_and_output_authorization_still_required(env,field,value):
    env.request[field]=value
    with pytest.raises(PermissionError):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


def test_source_verification_repeated_after_original_initial_progress(env):
    original_progress=lambda value:None
    def alter(value):
        if env.budget.inflight is not None:env.mf.write_text('{}',encoding='utf-8')
    env.budget.progress=alter
    with pytest.raises((PermissionError,KeyError)):invoke(env)
    assert env.model._model.entries==[] and env.budget.calls==[]
    assert env.budget.inflight is not None and env.budget.progress is alter


def test_complete_source_and_self_root_receipt_contains_real_declared_hashes(env):
    invoke(env)
    receipt=json.loads((env.out/'master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text(encoding='utf-8'))
    s=receipt['source']
    assert s['complete_declared_execution_sources_checked'] is True
    assert s['complete_declared_execution_source_count']==len(env.manifest['execution_sources'])
    assert s['computational_adapter_source']['sha256']==env.manifest['execution_sources']['v42_autonomous_b2/rmp_presolve.py']
    assert s['immutable_code_root']==str(draft._ROOT)
    assert s['exact_declared_package_files']==sorted(k for k in env.manifest['execution_sources'] if k.startswith('v42_autonomous_b2/'))
