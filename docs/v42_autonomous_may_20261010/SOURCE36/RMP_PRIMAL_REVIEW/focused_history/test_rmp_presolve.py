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
            FeasibilityTol=1e-8,OptimalityTol=1e-8,NumericFocus=0,ScaleFlag=-1,LPWarmStart=1,Crossover=-1)
        self.attrs={};self.entries=[];self.disposed=False;self.error=None
        self.start_events=[];self.backend_entered=False;self.invalidate_starts_after_optimize=False
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
    def getVars(self):return list(range(self.NumVars))
    def getConstrs(self):return list(range(self.NumConstrs))
    def setAttr(self,key,axis,values):
        assert not self.backend_entered,'NO_START_SETTER_AFTER_NATIVE_ENTRY'
        self.start_events.append(key);self.attrs[key]=np.asarray(values,dtype=np.float64).copy()
    def optimize(self,callback=None):
        # Run unchanged original scope/Threads/date/P1 guard. No backend.
        original_guard.guard(self)
        self.backend_entered=True
        self.entries.append(dict(params=vars(self.Params).copy(),scope=dict(execution._model.get()),
            starts={k:v.copy() for k,v in self.attrs.items() if k in ('PStart','DStart')}))
        if self.invalidate_starts_after_optimize:
            self.attrs['PStart']=np.full(self.NumVars,gp.GRB.UNDEFINED)
            self.attrs['DStart']=np.full(self.NumConstrs,gp.GRB.UNDEFINED)
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
    assert env.model.Params.Presolve==0 and env.model.Params.Method==0
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


def rebuild(env,*,columns=None):
    result=env.runner.original_run.__globals__['build_master'](env.case,env.decomp,columns or {},env.out/'next_master')
    env.model=result[0];env.proxy=draft.BudgetProxy(env.budget,write,env.runner.binding)
    return result


def test_current_nonunit_and_first_unit_seed_projected_with_complete_zero_dual(env):
    plan=env.model._rmp_warm_plan
    n=len(env.decomp.nonunit_columns)
    assert np.array_equal(plan.pstart[:n],env.case.point[env.decomp.nonunit_columns])
    assert np.array_equal(plan.pstart[n:],np.ones(4))
    assert np.array_equal(plan.dstart,np.zeros(env.model.NumConstrs))
    assert not plan.pstart.flags.writeable and not plan.dstart.flags.writeable
    invoke(env)
    raw=env.model._model;native=raw.entries[0]
    assert raw.start_events==['PStart','DStart'] and native['params']['LPWarmStart']==2
    assert native['params']['Method']==0 and native['params']['Presolve']==0 and native['params']['Crossover']==-1
    assert np.array_equal(native['starts']['PStart'],plan.pstart)
    assert np.array_equal(native['starts']['DStart'],plan.dstart)
    receipt=json.loads((env.out/'master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())['current_attempt_warm_start']
    assert receipt['installed'] and receipt['exact_complete_start_readback_before_Native']
    assert receipt['backend_actual_start_use_or_basis_proved'] is False
    assert receipt['computational_zero_DStart_is_Native_Pi'] is False
    assert receipt['start_is_basis_or_feasibility_or_dual_or_UB_or_Global_LB_authority'] is False


def test_extra_unit_catalog_columns_receive_zero_without_using_past_point(env):
    unit=next(iter(env.decomp.units));block=env.decomp.units[unit]
    alternate=env.case.point[block.original_columns].copy();alternate[:]=0.
    path=env.out/'own_alternate.npz';np.savez_compressed(path,point=alternate,original_columns=block.original_columns)
    result=rebuild(env,columns={unit:[dict(path=str(path),sha256=dw.sha(path),admission=dict(PASS=True))]})
    plan=env.model._rmp_warm_plan;n=len(env.decomp.nonunit_columns)
    assert len(result[3]['catalog'])==5 and plan.pstart[n+1]==0.
    for u in env.decomp.units:
        positions=[j for j,v in enumerate(result[3]['catalog']) if v['unit']==u]
        assert plan.pstart[n+positions[0]]==1.
        assert all(plan.pstart[n+j]==0. for j in positions[1:])
    invoke(env)
    assert len(env.budget.calls)==1 and env.model._model.start_events==['PStart','DStart']


def test_full_coupling_point_ineligible_uses_unchanged_cold_method1_call(env):
    env.case.point[-2:]=[1.,0.]
    rebuild(env)
    plan=env.model._rmp_warm_plan
    assert not plan.diagnostic['eligible'] and not plan.diagnostic['current_full_matrix_replay']['PASS']
    invoke(env)
    assert env.model.Params.LPWarmStart==1 and env.model.Params.Method==1
    assert env.model._model.start_events==[] and len(env.budget.calls)==1
    receipt=json.loads((env.out/'next_master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert receipt['Native_call_completed'] and not receipt['current_attempt_warm_start']['installed']


def test_scaled_residual_is_separately_recorded_and_never_claimed_feasible(env):
    env.case.d['sense'][6]='=';env.case.point[-2:]=[1e-25,1e-10]
    env.decomp=build_blocks(env.case);rebuild(env)
    hint=env.model._rmp_warm_plan.diagnostic
    assert hint['eligible'] and hint['current_full_matrix_replay']['PASS']
    assert hint['original_RMP_residual']['maximum_row_violation']<1e-9
    assert hint['Native_scaled_RMP_residual']['maximum_row_violation']>1.
    invoke(env)
    assert len(env.budget.calls)==1 and env.model._model.entries[0]['params']['LPWarmStart']==2
    assert env.model._model.entries[0]['params']['Method']==1
    assert hint['primal_simplex_selection']['eligible'] is False
    assert not hint['start_is_basis_or_feasibility_or_dual_or_UB_or_Global_LB_authority']


@pytest.mark.parametrize('mutation',[
    lambda e:e.case.point.__setitem__(-1,3.),
    lambda e:setattr(e.case,'case_sha','wrong_case'),
    lambda e:e.decomp.nonunit_columns.__setitem__(0,0),
    lambda e:e.model._rmp_warm_plan.identity['catalog'][0].update(point_vector_sha256='0'*64),
    lambda e:e.model._rmp_warm_plan.diagnostic.update(eligible=False),
    lambda e:setattr(e.model._rmp_warm_plan.pstart.flags,'writeable',True),
    lambda e:setattr(e.model,'_rmp_warm_plan',None),
    lambda e:Path(e.model._rmp_warm_plan.seed_receipts[0]['path']).write_bytes(b'changed_seed')])
def test_current_case_seed_catalog_and_readonly_plan_tamper_denied_before_budget(env,mutation):
    mutation(env)
    with pytest.raises(PermissionError):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[] and env.model._model.start_events==[]


@pytest.mark.parametrize('target',['install','verify','seal','binding_warm'])
def test_instance_delegate_substitution_cannot_bypass_warm_guards(env,monkeypatch,target):
    if target=='binding_warm':monkeypatch.setattr(env.runner.binding,'warm',lambda *a:env.model._rmp_warm_plan)
    else:monkeypatch.setattr(env.model._rmp_warm_plan,target,lambda *a:True)
    with pytest.raises(PermissionError):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


@pytest.mark.parametrize('target',['warm_install','warm_verify','case_hash','vector_sha'])
def test_inplace_warm_or_vector_code_drift_denied_before_budget(env,monkeypatch,target):
    function=dict(warm_install=draft.WarmPlan.install,warm_verify=draft.WarmPlan.verify,
        case_hash=draft._case_sha,vector_sha=dw.vector_sha)[target]
    monkeypatch.setattr(function,'__code__',(lambda *a,**k:None).__code__)
    with pytest.raises(PermissionError):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


def test_pre_native_start_readback_drift_denied_without_extra_backend(env,monkeypatch):
    raw=env.model._model;raw.Runtime=0.
    original=raw.getAttr
    def get(key,*args):
        value=original(key,*args)
        if key=='PStart':value[0]+=1.
        return value
    monkeypatch.setattr(raw,'getAttr',get)
    with pytest.raises(PermissionError,match='EXACT_PRE_NATIVE_START_READBACK'):invoke(env)
    assert raw.entries==[] and len(env.budget.calls)==1
    receipt=json.loads((env.out/'master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert receipt['status']=='FAILED' and receipt['Native_call_completed'] is False


@pytest.mark.parametrize('failed_key',['PStart','DStart'])
def test_start_install_exception_preserves_original_unknown_runtime_and_disposes(env,monkeypatch,failed_key):
    created=[]
    initial=Raw.__init__
    def init(self,*a,**k):initial(self,*a,**k);created.append(self);self.Runtime=float('nan')
    original_set=Raw.setAttr
    def fail(self,key,*args):
        if key==failed_key:raise RuntimeError('SYNTHETIC_START_INSTALL_FAILURE')
        return original_set(self,key,*args)
    monkeypatch.setattr(Raw,'__init__',init);monkeypatch.setattr(Raw,'setAttr',fail)
    with pytest.raises(RuntimeError,match='NATIVE_RUNTIME_UNAVAILABLE_QUARANTINE'):
        env.runner(env.case,env.decomp,{},env.budget,env.out/'install_failure')
    ledger=json.loads(env.budget.path.read_text())
    assert created[-1].disposed and created[-1].entries==[]
    assert len(ledger['calls'])==1 and ledger['calls'][0]['runtime_unavailable'] is True
    assert ledger['calls'][0]['Native_Runtime'] is None
    assert ledger['calls'][0]['error']=='SYNTHETIC_START_INSTALL_FAILURE'
    receipt=json.loads((env.out/'install_failure/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert receipt['status']=='FAILED' and not receipt['Native_call_completed']
    assert draft._ENTRY.get() is None


def test_no_start_setter_update_or_readback_after_native_even_if_undefined(env,monkeypatch):
    created=[];initial=Raw.__init__;old_get=Raw.getAttr
    def init(self,*a,**k):
        initial(self,*a,**k);self.invalidate_starts_after_optimize=True;created.append(self)
    def get(self,key,*args):
        if self.backend_entered and key in ('PStart','DStart'):raise AssertionError('NO_POST_NATIVE_START_READ')
        return old_get(self,key,*args)
    def update(self):assert not self.backend_entered,'NO_POST_NATIVE_UPDATE'
    monkeypatch.setattr(Raw,'__init__',init);monkeypatch.setattr(Raw,'getAttr',get);monkeypatch.setattr(Raw,'update',update)
    result=env.runner(env.case,env.decomp,{},env.budget,env.out/'undefined_after')
    assert result['native']['Native_Runtime']==2.25 and created[-1].disposed
    assert created[-1].Params.LPWarmStart==2 and created[-1].start_events==['PStart','DStart']
    assert np.all(created[-1].attrs['PStart']==gp.GRB.UNDEFINED)


@pytest.mark.parametrize('key,value',[('LPWarmStart',0),('Crossover',0)])
def test_pre_native_warm_or_crossover_param_tamper_remains_strict(env,key,value):
    env.budget.progress=lambda row:setattr(env.model.Params,key,value)
    with pytest.raises(PermissionError):invoke(env)
    assert env.model._model.entries==[]


def test_builder_post_return_warm_validation_failure_disposes_owned_model(env,monkeypatch):
    created=[];initial=Raw.__init__
    def init(self,*a,**k):initial(self,*a,**k);created.append(self)
    monkeypatch.setattr(Raw,'__init__',init)
    def drift(path,value):
        write(path,value)
        if Path(path).name=='RMP_IDENTITY.json':env.case.point[-1]=3.
    runner=draft.scoped_runner(dw.run,env.output,drift)
    with pytest.raises(PermissionError,match='CURRENT_BUILD_CASE_OR_POINT_DRIFT'):
        runner(env.case,env.decomp,{},env.budget,env.out/'build_drift')
    assert created[-1].disposed and created[-1].entries==[] and env.budget.calls==[]


def test_ineligible_missing_partial_or_undefined_point_never_installs_hint(env):
    model=env.model;identity=model._rmp_warm_plan.identity
    for point in (None,np.array([0.]),np.full(env.case.A.shape[1],gp.GRB.UNDEFINED)):
        env.case.point=point
        current=draft._point(env.case)
        plan=draft.WarmPlan(env.case,env.decomp,(model,None,None,identity),current,
            draft._case_sha(env.case,env.decomp),env.request,env.out/'master')
        assert not plan.diagnostic['eligible'] and plan.install() is False
    assert model._model.start_events==[] and model.Params.LPWarmStart==1


def test_computational_zero_dstart_does_not_create_absent_native_pi(env,monkeypatch):
    original=Raw.addMConstr
    class NoPi:
        @property
        def Pi(self):raise gp.GurobiError(10005,'SYNTHETIC_TIME_LIMIT_NO_PI')
    def add(self,*a,**k):original(self,*a,**k);self.Status=11;return NoPi()
    monkeypatch.setattr(Raw,'addMConstr',add)
    result=env.runner(env.case,env.decomp,{},env.budget,env.out/'no_pi')
    assert result['native']['Native_status']==11 and result['full_original_dual'] is None
    assert result['convexity_duals'] is None and result['dual_status']=='NO_FINITE_PI_FOLLOWUP_PRICING_NOT_RUN'
    assert result['restricted_master_is_Global_LB'] is False and env.budget.calls[-1]['Native_SolCount']==0


def test_native_done_parameter_tamper_is_denied_without_start_restoration(env,monkeypatch):
    original=Raw.optimize
    def alter(self,*a,**k):
        result=original(self,*a,**k);self.Params.LPWarmStart=1;return result
    monkeypatch.setattr(Raw,'optimize',alter);monkeypatch.setattr(draft,'_RAW_OPTIMIZE',alter)
    monkeypatch.setattr(draft,'_RAW_CODE',alter.__code__)
    with pytest.raises(PermissionError,match='SINGLE_COMPLETED_NATIVE'):invoke(env)
    assert len(env.budget.calls)==1 and len(env.model._model.entries)==1
    assert env.model._model.start_events==['PStart','DStart'] and env.model.Params.LPWarmStart==1


def test_primal_choice_sealed_current_complete_starts_math_caps_and_receipt(env):
    hint=env.model._rmp_warm_plan.diagnostic
    choice=hint['primal_simplex_selection']
    assert choice['eligible'] and choice['candidate_Method']==0 and choice['original_FeasibilityTol']==1e-9
    for key in ('original_RMP_residual','Native_scaled_RMP_residual'):
        assert hint[key]['maximum_row_violation']<=1e-9
    for key in ('original_RMP_bounds','Native_RMP_bounds'):
        assert hint[key]['maximum_bound_violation']<=1e-9
    before=env.model.getA();rhs=env.model.getAttr('RHS');bounds=(env.model.getAttr('LB'),env.model.getAttr('UB'))
    assert env.model.Params.Method==1
    invoke(env)
    raw=env.model._model
    assert len(raw.entries)==1 and raw.entries[0]['params']['Method']==0
    assert raw.entries[0]['params']['Presolve']==0 and raw.entries[0]['params']['TimeLimit']==30
    assert raw.entries[0]['params']['Threads']==1 and raw.entries[0]['params']['LPWarmStart']==2
    assert {k:raw.entries[0]['params'][k] for k in draft.PRECISION}==draft.PRECISION
    assert (env.model.getA()-before).nnz==0 and np.array_equal(env.model.getAttr('RHS'),rhs)
    assert np.array_equal(env.model.getAttr('LB'),bounds[0]) and np.array_equal(env.model.getAttr('UB'),bounds[1])
    receipt=json.loads((env.out/'master/RMP_PRESOLVE0_COMPUTATIONAL_ENTRY.json').read_text())
    assert receipt['schema'].endswith('V36') and receipt['exact_selected_computational_Method']==0
    assert receipt['actual_parameters']['Method']==0 and receipt['Native_calls_added']==0
    assert not receipt['restricted_master_objective_is_Global_LB']
    assert not receipt['computational_performance_or_Global_LB_improvement_proved']
    assert not choice['start_is_Native_basis_or_certified_feasibility_or_Global_LB']


@pytest.mark.parametrize('key,field,value',[
    ('original_RMP_residual','maximum_row_violation',1.0000001e-9),
    ('Native_scaled_RMP_residual','maximum_row_violation',1.0000001e-9),
    ('original_RMP_bounds','maximum_bound_violation',1.0000001e-9),
    ('Native_RMP_bounds','maximum_bound_violation',1.0000001e-9),
    ('original_RMP_residual','finite',False),
    ('Native_scaled_RMP_residual','finite',False),
    ('original_RMP_bounds','finite',False),
    ('Native_RMP_bounds','finite',False)])
def test_primal_choice_requires_each_original_and_native_residual_bound(key,field,value):
    diagnostic=dict(eligible=True,
        **{k:dict(finite=True,maximum_row_violation=0.) for k in ('original_RMP_residual','Native_scaled_RMP_residual')},
        **{k:dict(finite=True,maximum_bound_violation=0.) for k in ('original_RMP_bounds','Native_RMP_bounds')})
    diagnostic[key][field]=value
    choice=draft._primal_method_eligibility(diagnostic)
    assert not choice['eligible'] and choice['candidate_Method']==1
    assert choice['original_FeasibilityTol']==1e-9


def test_bound_residual_unbounded_valid_and_nan_or_violated_infinite_denied():
    point=np.array([0.,1.])
    valid=draft._bound_residual(np.array([-np.inf,0.]),np.array([np.inf,1.]),point)
    assert valid['finite'] and valid['maximum_bound_violation']==0.
    assert not draft._bound_residual(np.array([np.nan,0.]),np.array([np.inf,1.]),point)['finite']
    assert not draft._bound_residual(np.array([np.inf,0.]),np.array([np.inf,1.]),point)['finite']


def test_exact_original_method1_required_before_original_budget(env):
    env.model.Params.Method=0
    with pytest.raises(PermissionError,match='EXACT_ORIGINAL_ONE'):invoke(env)
    assert env.budget.calls==[] and env.budget.inflight is None and env.model._model.entries==[]


def test_first_progress_cannot_prematurely_select_primal_preserves_inflight_unknown(env):
    env.budget.progress=lambda row:setattr(env.model.Params,'Method',0)
    with pytest.raises(PermissionError,match='EXACT_COMPUTATIONAL_METHOD'):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]
    assert env.budget.inflight is not None and json.loads(env.budget.path.read_text())['inflight'] is not None


@pytest.mark.parametrize('key',['PStart','DStart','Method'])
def test_receipt_writer_cannot_mutate_start_or_exact_method_before_raw_delegate(env,monkeypatch,key):
    def altered(path,value):
        write(path,value)
        if value.get('status')=='ABOUT_TO_DELEGATE':
            if key=='Method':env.model.Params.Method=1
            else:env.model._model.attrs[key][0]+=1.
    env.proxy._write=altered
    with pytest.raises(PermissionError):invoke(env)
    assert env.model._model.entries==[] and len(env.budget.calls)==1
    assert env.model._model.start_events==['PStart','DStart']


def test_post_native_method_change_denied_without_post_native_parameter_repair(env,monkeypatch):
    original=Raw.optimize
    def alter(self,*a,**k):
        result=original(self,*a,**k);self.Params.Method=1;return result
    monkeypatch.setattr(Raw,'optimize',alter);monkeypatch.setattr(draft,'_RAW_OPTIMIZE',alter)
    monkeypatch.setattr(draft,'_RAW_CODE',alter.__code__)
    with pytest.raises(PermissionError,match='EXACT_COMPUTATIONAL_METHOD'):invoke(env)
    assert len(env.budget.calls)==1 and len(env.model._model.entries)==1
    assert env.model._model.entries[0]['params']['Method']==0 and env.model.Params.Method==1
    assert env.model._model.start_events==['PStart','DStart']


@pytest.mark.parametrize('key',['_selected_method','_primal_method_eligibility','_bound_residual','_verify_installed_start'])
def test_primal_choice_helper_identity_and_code_substitution_denied_before_budget(env,monkeypatch,key):
    function=getattr(draft,key)
    from types import FunctionType
    replaced=FunctionType(function.__code__,dict(function.__globals__),function.__name__)
    monkeypatch.setattr(draft,key,replaced)
    with pytest.raises(PermissionError,match='IMMUTABLE_ORIGINAL_CODE'):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]


def test_primal_sealed_decision_mutation_denied_before_original_budget(env):
    env.model._rmp_warm_plan.diagnostic['primal_simplex_selection']['eligible']=False
    with pytest.raises(PermissionError):invoke(env)
    assert env.budget.calls==[] and env.model._model.entries==[]
