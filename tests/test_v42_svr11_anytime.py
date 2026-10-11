"""Synthetic termination faults through real A/M and supervisor entry points.

These regressions prove orchestration behavior, not May electrical safety.
"""
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace as NS
from fractions import Fraction
import json
import numpy as np
import pytest
from v42_pr134_b1.common import atomic,read,record
from test_v42_common_mess import route_case,ParentBudget

@pytest.fixture(autouse=True)
def epoch():
    from v42_svr11.authority import _active
    token=_active.set(dict(A_anytime_FULL_feasible=True))
    try:yield
    finally:_active.reset(token)

def validator(case,path,evidence):
    from v42_m1_research.check_ub import vector_sha
    with np.load(path) as a:p=a['point']
    assert np.array_equal(case.A@p,case.d['rhs'])
    assert np.isin(p[case.original_d['types']=='B'],(0.,1.)).all()
    return dict(PASS=True,Global_UB=float(p[-1]),exact_Global_UB=str(Fraction(float(p[-1]))),
        point_vector_sha256=vector_sha(p),strict_raw_C3A_and_FULL_integer_and_binary_pattern_exact=True,
        original_matrix_and_96_slot_physical_replay=dict(PASS=True,case_sha=case.case_sha))

def exporter(case,point):
    p=dict(case_sha=case.case_sha,synthetic_fixture_only=True)
    atomic(case.output/'OPTIMIZED_MESS_PLAN.json',p);return p

@pytest.mark.parametrize('arm,stage',[('B2','M'),('B3','M1'),('B3','M2')])
def test_m_native_budget_preserves_full_feasible(route_case,monkeypatch,arm,stage):
    from v42_common_mess import engine
    from v42_common_mess.budget import NativeBudgetExhausted
    parent=ParentBudget()
    monkeypatch.setattr(engine,'current_grid',lambda *a:([dict(unit='U',site='B',slot=62,numeric_score=1.)],{}))
    def exhausted(case,budget,*a,**kw):
        parent.value=1800
        raise NativeBudgetExhausted('COMMON_M_NATIVE_BUDGET_EXHAUSTED')
    monkeypatch.setattr(engine,'_trial',exhausted)
    result,point=engine.optimize_case(route_case,parent,stage_identity=dict(arm=arm,stage=stage),
        strict_validator=validator,plan_exporter=exporter)
    assert result['PASS'] and result['classification']=='TIME_LIMIT_FEASIBLE_ACCEPTED'
    assert not result['global_gap_certified'] and result['LB'] is None
    assert np.array_equal(point,route_case.point) and result['native_seconds']==1800

def test_m_last_solcount_zero_preserves_previous_verified_point(route_case,monkeypatch):
    from v42_common_mess import engine
    from v42_common_mess.budget import StageBudget
    class Model:
        Params=NS();Status=9;SolCount=0;Work=1.;ObjBound=.9
        def dispose(self):self.disposed=True
    m=Model()
    monkeypatch.setattr(engine,'build',lambda *a,**kw:(m,NS(),{}))
    seed=route_case.output/'seed.npz';np.savez_compressed(seed,point=route_case.point)
    strict=validator(route_case,seed,{})
    point,newstrict,row=engine._trial(route_case,StageBudget(ParentBudget()),route_case.output/'zero',
        validator=validator,seconds=1.,point=route_case.point,strict=strict)
    assert np.array_equal(point,route_case.point) and newstrict==strict
    assert row['Native_SolCount']==0 and row['Native_status']==9

@pytest.fixture
def a_executor(tmp_path,monkeypatch):
    from v42_may_campaign_native90 import a_stage as a
    from v42_a_stage_canary import phase,pricing,targeted
    from v42_a_stage_practical import integer_model
    from v42_a_stage_phase1 import core
    from v42_a_stage_lexfull import runner
    from v42_a_stage_acceptance import schedule_audit
    output=tmp_path/'A';output.mkdir()
    state={'_campaign':{'input_receipts':{}},'data':{1:{'job1':object()},7:{'classes':[1]}},'global_types':object()}
    typed=NS(vtypes=np.asarray(['B','C']),objectives=[NS(name='rho')])
    monkeypatch.setattr(a,'_paths',lambda request:('2025-05-01',tmp_path,output))
    monkeypatch.setattr(a,'prepare',lambda *args:state)
    monkeypatch.setattr(a,'_dump_state',lambda *args:None)
    monkeypatch.setattr(a,'rebound',lambda f,g:f)
    def group(module,names,**kw):
        if module is targeted:return {'targeted':lambda:None}
        def run(*args):
            atomic(output/'pricing.json',{'synthetic_fixture_only':True})
            atomic(output/'P1_RESULT.json',{'full_pricing':record(output/'pricing.json')})
            atomic(output/'PHASE_I_ZERO_CERTIFICATE.json',{'PASS':True})
            return state,None,None,dict(full_domain_phase1_lower_bound='1',complete_STAY_and_migration_coverage=True,
                no_negative_omitted_block_certified=True)
        return {'run':run}
    monkeypatch.setattr(a,'group',group)
    monkeypatch.setattr(integer_model,'restore_types',lambda *args:(typed,{'PASS':True}))
    # Independent tiny fixture has a complete binary job selection and rho.
    monkeypatch.setattr(core,'primal_replay',lambda model,p:{'PASS':bool(p[0]==1. and p[1]>=1.)})
    monkeypatch.setattr(runner,'objective_value',lambda model,p,name:Fraction(float(p[1])))
    monkeypatch.setattr(schedule_audit,'original_schedule_metrics',lambda *args:({},{}))
    config={'candidate':True,'status':9,'error':None,'point':np.asarray([1.,2.])}
    class Physical:
        def __init__(self,*args):pass
        def verify(self,p):return dict(PASS=True,selected_jobs={'job1':[1]},controls=[[2]],globals={},physical={'P1_rho':2.})
    monkeypatch.setattr(a,'_physical',lambda *args:(Physical,object()))
    def planning(*args):
        np.savez_compressed(output/'planning.npz',PCC_P_kw=np.full((96,12),2.))
        return record(output/'planning.npz')
    monkeypatch.setattr(a,'_planning',planning)
    class Budget:
        native_used=0.;calls=[]
        def check(self):pass
        def cost(self,*args):return nullcontext()
        def remaining(self):return max(0.,5400-self.native_used)
        def wall(self):return 1.
    budget=Budget()
    class Native:
        calls=[];live_model=None;freeze_path=output/'A_NATIVE_SOURCE_FREEZE.json'
        def solve(self,*args):
            if config['candidate']:self.incumbent_callback(config['point'],float(config['point'][1]))
            budget.native_used=5400 if config['status']==9 else 1.
            self.calls=[dict(status=config['status'])]
            if config['error']:raise config['error']
            # Last SolCount zero: callback incumbent remains the sole solution.
            return dict(status=config['status'],SolCount=0),{}
    atomic(Native.freeze_path,{'PASS':True})
    monkeypatch.setattr(a,'_native',lambda *args:Native())
    return lambda:a.run({},budget),config,output

@pytest.mark.parametrize('termination',['TIME_LIMIT','NATIVE_BUDGET'])
def test_a_time_limit_complete_integer_gap_miss_continues(a_executor,termination):
    execute,config,output=a_executor
    if termination=='NATIVE_BUDGET':
        from v42_may_campaign_native90.budget import BudgetStop
        config['error']=BudgetStop('DATE_NATIVE_RUNTIME_BUDGET_EXHAUSTED')
    result=execute()
    assert result['PASS'] and result['accepted']
    assert result['classification']=='TIME_LIMIT_FEASIBLE_ACCEPTED' and not result['global_gap_certified']
    assert result['FULL_feasible_certified'] and result['certified_gap']==.5 and result['native_seconds']==5400
    assert read(output/'A1_FREEZE.json')['selected_jobs']=={'job1':[1]}
    assert read(output/'A1_FREEZE.json')['A1_ACCEPTED'] is False

def test_a_lp_or_partial_solution_cannot_be_promoted(a_executor):
    execute,config,output=a_executor;config['point']=np.asarray([.5,2.])
    result=execute();assert not result['PASS'] and not (output/'A1_FREEZE.json').exists()

def test_a_no_solution_timeout_fail_and_next_date(a_executor):
    execute,config,output=a_executor;config['candidate']=False
    result=execute();assert result['classification']=='TIME_LIMIT_NO_FEASIBLE' and not result['PASS']
    from v42_svr11.controller import initial,dispatch_rows
    ledger=initial();ledger['dates']['B0/2025-05-01']['status']='FAIL'
    assert dispatch_rows(ledger,'B0')[0]['day']=='2025-05-02'

def test_a_solver_exception_is_not_timeout_acceptance(a_executor):
    execute,config,output=a_executor;config['error']=RuntimeError('REAL_SOLVER_EXCEPTION')
    result=execute();assert not result['PASS'] and result['classification']=='IMPLEMENTATION_FAILURE'
    assert not (output/'A1_FREEZE.json').exists()

def test_retry_queue_next_date_first_evidence_retained(tmp_path):
    from v42_svr11.controller import initial,reconcile,dispatch_rows
    ledger=initial();row=ledger['dates']['B0/2025-05-01'];attempt=tmp_path/'attempt';attempt.mkdir()
    request=attempt/'request.json';result=attempt/'RESULT.json'
    atomic(request,dict(result=str(result)));atomic(result,dict(PASS=False,reason='WIN32_SHARING',Native_Runtime=0,
        retryable_pre_native_technical_error=True,native_ledgers=[]))
    row.update(status='RUNNING',request=str(request),attempts=[str(request)])
    reconcile(tmp_path,{'retry_new_attempt_starts_zero':True},ledger,[])
    assert row['status']=='FAIL' and row['retry_pending'] and len(row['terminal_history'])==1
    assert dispatch_rows(ledger,'B0')[0]['day']=='2025-05-02'
    ledger['dates']['B0/2025-05-02'].update(status='PASS',attempts=['next-date'])
    assert dispatch_rows(ledger,'B0')[0]['day']=='2025-05-01'
    assert result.exists() and row['terminal_history'][0]['status']=='FAIL'

def test_physical_fail_after_feasible_timeout_still_continues(tmp_path):
    from v42_svr11.controller import initial,record_terminal,dispatch_rows
    ledger=initial();p=tmp_path/'RESULT.json';atomic(p,dict(PASS=False,reason='ACTUAL:VOLTAGE_VIOLATION',
        optimization_status='TIME_LIMIT · FEASIBLE',AC_status='AC FAIL',metrics={'voltage_violations':2}))
    record_terminal(ledger['dates']['B0/2025-05-01'],p)
    assert ledger['dates']['B0/2025-05-01']['status']=='FAIL'
    assert dispatch_rows(ledger,'B0')[0]['day']=='2025-05-02'

def test_worker_fail_exit_does_not_gate_all_124():
    from v42_svr11.regression import fail_continue
    proof=fail_continue();assert proof['PASS'] and proof['attempts']==124 and proof['last']=='B3/2025-05-31'

def test_b3_a1_m1_a2_m2_handoff_with_uncertified_complete_a(tmp_path):
    from dataclasses import replace
    from test_v42_b3_source_coordinator import FixtureBridge,FixtureLedger
    from v42_b3_joint.dry_run import fixture_authority
    from v42_b3_joint.contracts import canonical
    from v42_b3_joint.source_runtime import FakeSourceRegistry,RealStageContext
    from v42_b3_joint.source_coordinator import SourceCoordinator
    authority=fixture_authority();registry=FakeSourceRegistry();grid=object()
    class Bridge(FixtureBridge):
        def execute(self,context,ledger,progress=None):
            output=super().execute(context,ledger,progress)
            if context.request.stage.startswith('A'):
                output=replace(output,source_result=dict(output.source_result,FULL_feasible_certified=True,
                    classification='TIME_LIMIT_FEASIBLE_ACCEPTED',global_gap_certified=False))
            return output
        def verify(self,context,output):
            proof=super().verify(context,output)
            if context.request.stage.startswith('A'):
                proof['global'].update(exact_UB='2',global_gap_certified=False)
            return proof
    bridge=Bridge()
    def factory(request,packets,path):
        return RealStageContext(request,tmp_path/'input',path,canonical({'day':authority.day}),registry,grid,
            packets,authority.source_sha,'ANYTIME_HANDOFF_FIXTURE')
    coordinator=SourceCoordinator(tmp_path/'pipeline',factory,bridge,bridge,ledger_factory=FixtureLedger)
    result=coordinator.run(authority)
    assert bridge.executions==['A1','M1','A2','M2']
    assert all(not result['outputs'][i].global_evidence['global_gap_certified'] for i in (0,2))
    assert result['outputs'][1].aidc==result['outputs'][0].aidc
    assert result['outputs'][2].mess==result['outputs'][1].mess

def test_explicit_zero_restart_preserves_unknown_prior_runtime(tmp_path):
    from v42_svr11.controller import initial,reconcile,make_request
    from v42_pr134_b1.common import sha
    ledger=initial();row=ledger['dates']['B0/2025-05-01'];attempt=tmp_path/'first';attempt.mkdir()
    request=attempt/'request.json';result=attempt/'RESULT.json'
    atomic(request,dict(result=str(result)))
    native=attempt/'NATIVE_RUNTIME_LEDGER.json';atomic(native,dict(calls=[{'Native_Runtime':5.}],inflight={'status':'IN_FLIGHT'}))
    before=sha(native);row.update(status='RUNNING',request=str(request),attempts=[str(request)])
    m={'retry_new_attempt_starts_zero':True,'run_id':'explicit_retry','execution_SHA':'a'*64}
    reconcile(tmp_path,m,ledger,[])
    assert read(result)['unknown_inflight_runtime'] and row['retry_pending']
    atomic(tmp_path/'CAMPAIGN_MANIFEST.json',m)
    path,next_request=make_request(tmp_path,m,row,1)
    assert next_request['attempt_id']=='attempt_02' and next_request['retry_starts_from_native_zero']
    assert next_request['previous_attempts']==[str(request)] and sha(native)==before

@pytest.mark.parametrize('normal_status',['TIME_LIMIT_FEASIBLE_ACCEPTED','TIME_LIMIT_NO_FEASIBLE','ACTUAL_PHYSICAL_FAIL'])
def test_watchdog_never_kills_or_restarts_healthy_worker(tmp_path,monkeypatch,normal_status):
    from v42_svr11 import watchdog as w
    source='a'*64;manifest={'execution_SHA':source};supervisor={'PID':123,'normal_status':normal_status}
    atomic(tmp_path/'SUPERVISOR_PROCESS.json',supervisor);atomic(tmp_path/'MONITOR_PROCESS.json',{'PID':456})
    atomic(tmp_path/'CAMPAIGN_LEDGER.json',dict(status='RUNNING'))
    monkeypatch.setattr(w,'verify',lambda p:manifest)
    monkeypatch.setattr(w,'live',lambda p:True)
    monkeypatch.setattr(w,'workers',lambda *args:[{'PID':789}])
    monkeypatch.setattr(w,'identity',lambda:supervisor)
    monkeypatch.setattr(w,'launch',lambda *args:pytest.fail('Healthy process cannot be restarted'))
    class Response:
        status=200
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps({'source_SHA':source,'root':str(tmp_path)}).encode()
    monkeypatch.setattr(w.urllib.request,'urlopen',lambda *args,**kwargs:Response())
    result=w.check(tmp_path)
    assert result['actions']==[] and result['healthy_workers_terminated']==0 and result['Native_ledger_reset']==0
