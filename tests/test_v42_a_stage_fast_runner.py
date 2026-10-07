"""Pure Python control-flow fixtures; production native optimize is forbidden."""
from pathlib import Path
from types import SimpleNamespace
import json
import csv
import os
import subprocess
import sys
import textwrap
import pytest
import gurobipy as gp

from v42_a_stage_domain_v2.fast_execution import (REQUIRED_FAST_GATES,REQUIRED_FAST_SOURCES,
    create_fast_run_permit,fast_run_scope,fast_native_scope,canonical_hash,require_may19_tractable)
from v42_a_stage_domain_v2.execution import guard_model_optimize,tag_model_for_day,require_action_authorized
from v42_a_stage_domain_v2.fast_runner import run_fast_date,StageBuild
from v42_a_stage_domain_v2.fast_status import verified_pricing_certificate,validate_fast_status,initial_fast_status
from v42_a_stage_domain_v2.solver_policy import solver_policy,validate_frozen_policy
from v42_a_stage_domain_v2.fast_telemetry import fill_in_metrics


def fake_gurobi():
    specs={'NodeMethod':('NodeMethod',int,-1,-1,5,-1),
        'MIPFocus':('MIPFocus',int,0,0,3,0),'Crossover':('Crossover',int,-1,-1,5,-1)}
    return SimpleNamespace(gurobi=SimpleNamespace(version=lambda:(13,0,2)),getParamInfo=lambda name:specs[name])


def permit_fixture(folder,*,mode='CANARY',budget=300,extra_sources=()):
    folder.mkdir(parents=True,exist_ok=True);gates={}
    for key in REQUIRED_FAST_GATES:
        path=folder/(key+'.json');path.write_text(json.dumps(dict(PASS=True,scope='SYNTHETIC_FIXTURE')));gates[key]=path
    package=Path(__file__).resolve().parents[1]/'v42_a_stage_domain_v2'
    sources=[package/name for name in REQUIRED_FAST_SOURCES]+list(extra_sources)
    policy=solver_policy(fake_gurobi());policy_path=folder/'POLICY.json';policy_path.write_text(json.dumps(policy))
    active_path=folder/'ACTIVE.json';active_path.write_text(json.dumps(dict(PASS=True,scientific_domain_cap=False,
        max_activation_batch=8,max_pricing_iterations=4,scope='SYNTHETIC_FIXTURE')))
    canary=create_fast_run_permit(gates,sources,policy_path,active_path,native_budget_seconds=budget)
    if mode=='CANARY':return canary,policy
    doc=canary.document;kwargs={}
    for label,day in [('may17_canary','2025-05-17'),('may19_canary','2025-05-19')]:
        path=folder/(label+'.json');path.write_text(json.dumps(dict(day=day,mode='CANARY',root_completed=True,
            execution_sources_sha256=canonical_hash(doc['execution_sources']),solver_policy_sha256=doc['solver_policy']['sha256'],
            activation_policy_sha256=doc['activation_policy']['sha256'],domain_status=dict(LP_PRICING_CLOSED=True))))
        kwargs[label]=path
    speed=folder/'SPEED.json';speed.write_text(json.dumps(dict(PASS=True,classification='SPEED_GATE_PASS',canary_source_bound=True,
        execution_sources_sha256=canonical_hash(doc['execution_sources']),solver_policy_sha256=doc['solver_policy']['sha256'],
        activation_policy_sha256=doc['activation_policy']['sha256'])))
    return create_fast_run_permit(gates,sources,policy_path,active_path,mode='PRODUCTION',native_budget_seconds=3600,
        speed_gate=speed,**kwargs),policy


class MockModel:
    NumVars=1;NumConstrs=1;NumBinVars=0;NumNZs=1
    NumQConstrs=0;NumQNZs=0;NumSOS=0;NumGenConstrs=0
    Status=gp.GRB.OPTIMAL;SolCount=1;Runtime=.25;Work=.01;NodeCount=0
    ObjVal=0.;ObjBound=0.;MIPGap=0.
    def __init__(self,phase):self.NumIntVars=0 if phase=='LP' else 1;self.Params=SimpleNamespace();self.phase=phase;self.calls=0;self.disposed=False
    def update(self):pass
    def setObjective(self,*args):pass
    def setParam(self,name,value):setattr(self.Params,name,value)
    def optimize(self,callback):guard_model_optimize(self);self.calls+=1
    def getAttr(self,name):return [0.]
    def dispose(self):self.disposed=True


class MockBackend:
    def __init__(self,*,closed=True,activate_once=False,runtime=.25):
        self.closed=closed;self.activate_once=activate_once;self.runtime=runtime;self.models=[];self.events=[]
    def _build(self,day,component,locks,phase):
        self.events.append((phase,component,len(locks)))
        model=MockModel(phase);model.Runtime=self.runtime;self.models.append(model)
        meta=dict(scientific_identity_PASS=True,physical_authority_sha256='a'*64,lp_snapshot_sha256='b'*64,
            relaxed_lp_snapshot_sha256='b'*64,objective_sha256='c'*64,stage_equivalence=dict(PASS=True),
            pool_partition=dict(PASS=True,active_subset_physical=True,active_union_pool_equals_physical=True,
                permanent_speed_deletion=False,inactive_candidates_materialized=False),
            active_counts=dict(stay=2,inactive_stay=3,migration=0),incumbent_support=dict(scope='SYNTHETIC'))
        return StageBuild(model,None,[(name,0) for name in ('rho','migration_count','shift_magnitude','prestart_relocation')],
            None,None,(dict(day=day),),None,meta)
    def build_lp(self,day,folder,component,locks,active_state):return self._build(day,component,locks,'LP')
    def build_milp(self,day,folder,component,locks,previous,active_state):return self._build(day,component,locks,'MILP')
    def verify_lp(self,*args):return dict(PASS=True,scope='SYNTHETIC_RAW_LP_ROWS')
    def price(self,build,mode,iteration):
        self.events.append(('PRICE',mode,iteration))
        if self.activate_once and iteration==0:
            return dict(mode=mode,candidates_activated=1,improving_candidates=1,candidates_scanned=3,
                classification='PARTIAL_CERTIFIED_ACTIVATION',certificate=dict(PASS=False))
        if not self.closed:
            return dict(mode=mode,candidates_activated=0,classification='LP_PRICING_UNRESOLVED',certificate=dict(PASS=False))
        return dict(mode=mode,candidates_activated=0,candidates_scanned=3,improving_candidates=0,LP_PRICING_CLOSED=True,
            classification='LP_PRICING_CLOSED',certificate=dict(PASS=True,kind='EXACT_ORIGINAL_ROW_LP_PRICING',
                mode='OPTIMALITY',lp_status='OPTIMAL',full_omitted_lp_pool_priced=True,
                inactive_stay_covered=True,inactive_migration_covered=True,original_rows_and_objective=True,
                native_full_direction_coverage_verified=True,independent_full_native_producer_verified=True,
                negative_price_candidates=0,physical_authority_sha256='a'*64,lp_snapshot_sha256='b'*64,
                objective_sha256='c'*64,pricing_evidence_sha256='d'*64))
    def verify_pricing(self,*args):return dict(PASS=True,activated_candidates_hard_valid=True,scope='SYNTHETIC_PRICING')
    def activate(self,state,pricing):self.events.append(('ACTIVATE',pricing['candidates_activated']));return dict(active=True)
    def verify(self,*args):return dict(PASS=True,physical=dict(PASS=True),selected_jobs={},controls=[])
    def integer_certificate(self,*args):return dict(PASS=True,scope='SYNTHETIC_INTEGER_CERTIFICATE')


@pytest.fixture(autouse=True)
def no_production_native(monkeypatch):
    import v42_a_stage_domain_v2.fast_runner as runner
    monkeypatch.setattr(runner,'other_heavy_optimizers',lambda:[])
    def reject(*args,**kwargs):raise AssertionError('PRODUCTION_NATIVE_OPTIMIZE_FORBIDDEN')
    monkeypatch.setattr(gp.Model,'optimize',reject)
    # The installer wraps methods reversibly; restore the original class and
    # installed flag together so a fixture sentinel cannot poison later tests.
    for name in ('copy','relax','presolve','fixed'):
        monkeypatch.setattr(gp.Model,name,getattr(gp.Model,name))
    monkeypatch.setattr(gp.Model,'_v42_stress_guard_installed',False,raising=False)


def test_may19_canary_lp_only_no_integer_or_full_acceptance(tmp_path):
    permit,policy=permit_fixture(tmp_path/'permit');backend=MockBackend()
    result=run_fast_date('2025-05-19',backend,permit,policy,tmp_path/'run')
    assert result['classification']=='CANARY_LP_PRICING_CLOSED'
    assert result['native_seconds']==.25 and result['root_completed']
    assert result['domain_status']['LP_PRICING_CLOSED']
    assert not result['domain_status']['INTEGER_DOMAIN_CLOSURE_PROVEN']
    assert not result['domain_status']['FULL_DOMAIN_ACCEPTED']
    assert not result['Actual'] and not result['Planning_freeze']
    assert [model.phase for model in backend.models]==['LP']
    assert backend.models[0].Params.InfUnbdInfo==1


def test_unresolved_pricing_never_reaches_milp(tmp_path):
    permit,policy=permit_fixture(tmp_path/'permit');backend=MockBackend(closed=False)
    result=run_fast_date('2025-05-17',backend,permit,policy,tmp_path/'run')
    assert result['classification']=='LP_PRICING_UNRESOLVED'
    assert result['domain_status']['ACTIVE_DOMAIN_FEASIBLE']
    assert not result['domain_status']['LP_PRICING_CLOSED']
    assert not result['domain_status']['ACTIVE_DOMAIN_SOLUTION_VALID']
    assert result['initial_LP_bound']==result['final_LP_bound']==0.
    assert [model.phase for model in backend.models]==['LP']


def test_physical_score_arithmetic_pass_is_not_full_native_pricing_closure(tmp_path):
    permit,policy=permit_fixture(tmp_path/'permit')
    class WitnessBackend(MockBackend):
        def price(self,*args):
            return dict(certificate=dict(PASS=True,score_arithmetic_exact=True,
                native_full_direction_coverage_verified=False),candidates_activated=0,LP_PRICING_CLOSED=False)
    result=run_fast_date('2025-05-17',WitnessBackend(),permit,policy,tmp_path/'run')
    assert result['classification']=='LP_PRICING_UNRESOLVED' and not result['global_scientific_stop']
    assert not result['domain_status']['LP_PRICING_CLOSED'] and not result['passes']


def test_activation_growth_uses_actual_next_native_matrix_census(tmp_path):
    permit,policy=permit_fixture(tmp_path/'permit')
    class GrowthBackend(MockBackend):
        def build_lp(self,*args):
            build=super().build_lp(*args)
            if len(self.models)==2:
                build.model.NumConstrs=4;build.model.NumVars=6;build.model.NumNZs=9
            return build
    result=run_fast_date('2025-05-19',GrowthBackend(activate_once=True),permit,policy,tmp_path/'run')
    assert result['classification']=='CANARY_LP_PRICING_CLOSED'
    with (tmp_path/'run/ACTIVATION_TRACE.csv').open(newline='') as stream:rows=list(csv.DictReader(stream))
    assert rows[0]['rows_added']=='3' and rows[0]['cols_added']=='5' and rows[0]['nnz_added']=='8'
    assert rows[1]['rows_added']=='0' and rows[1]['candidates_activated']=='0'


def test_bounded_exact_activation_then_fresh_lp_before_milp(tmp_path):
    permit,policy=permit_fixture(tmp_path/'permit');backend=MockBackend(activate_once=True)
    result=run_fast_date('2025-05-17',backend,permit,policy,tmp_path/'run')
    assert result['native_seconds']==3.
    assert len(result['passes'])==4
    assert result['domain_status']['ACTIVE_INTEGER_SOLVED']
    assert result['domain_status']['ACTIVE_DOMAIN_SOLUTION_VALID']
    assert not result['domain_status']['INTEGER_DOMAIN_CLOSURE_PROVEN']
    assert [x[:2] for x in backend.events[:6]]==[('LP','rho'),('PRICE','OPTIMALITY'),('ACTIVATE',1),
        ('LP','rho'),('PRICE','OPTIMALITY'),('MILP','rho')]
    assert all(model.disposed for model in backend.models)
    assert [e[2] for e in backend.events if e[0]=='MILP']==[0,1,2,3]


def test_native_budget_overshoot_is_charged_without_second_call(tmp_path):
    permit,policy=permit_fixture(tmp_path/'permit');backend=MockBackend(activate_once=True,runtime=301.)
    result=run_fast_date('2025-05-19',backend,permit,policy,tmp_path/'run')
    assert result['native_seconds']==301 and result['budget_overshoot_seconds']==1
    assert len(backend.models)==1 and backend.models[0].Params.TimeLimit==300
    assert result['classification']=='LP_NATIVE_BUDGET_EXHAUSTED'


def test_error_runtime_accounted_once_and_resource_failures_honest(tmp_path):
    permit,policy=permit_fixture(tmp_path/'permit')
    class ErrorBackend(MockBackend):
        def build_lp(self,*args):
            build=super().build_lp(*args)
            def fail(callback):build.model.Runtime=1.75;raise gp.GurobiError(10001,'SYNTHETIC_OOM')
            build.model.optimize=fail;return build
    result=run_fast_date('2025-05-19',ErrorBackend(),permit,policy,tmp_path/'native')
    assert result['native_seconds']==1.75 and not result['global_scientific_stop']
    assert len(result['native_calls'])==1 and result['native_calls'][0]['native_seconds']==1.75
    class ResourceBackend:
        def build_lp(self,*args):raise MemoryError('SYNTHETIC_BUILD_OOM')
    result=run_fast_date('2025-05-17',ResourceBackend(),permit,policy,tmp_path/'build')
    assert result['native_seconds']==0 and result['computational_resource_failure']
    assert not result['global_scientific_stop']


def test_date_and_model_phase_guard_cannot_be_bypassed(tmp_path):
    permit,_=permit_fixture(tmp_path/'permit');lp=tag_model_for_day(MockModel('LP'),'2025-05-19')
    with fast_run_scope(permit):
        with pytest.raises(PermissionError,match='FAST_EXPLICIT_NATIVE_MODEL_PHASE_REQUIRED'):guard_model_optimize(lp)
        with pytest.raises(PermissionError,match='FAST_DATE_NOT_AUTHORIZED'):require_action_authorized('2025-05-12','A1')
        with pytest.raises(PermissionError,match='FAST_DATE_NOT_AUTHORIZED'):require_action_authorized('2025-05-01','A1')
        with fast_native_scope(lp,'2025-05-19','LP'):
            guard_model_optimize(lp)
            with pytest.raises(PermissionError,match='FAST_EXPLICIT_NATIVE_MODEL_PHASE_REQUIRED'):
                guard_model_optimize(tag_model_for_day(MockModel('LP'),'2025-05-19'))
        with pytest.raises(PermissionError,match='CONTINUOUS_MODEL'):
            with fast_native_scope(tag_model_for_day(MockModel('MILP'),'2025-05-19'),'2025-05-19','LP'):pass
        with pytest.raises(PermissionError,match='FULL_POOL_LP_PRICING'):
            with fast_native_scope(lp,'2025-05-19','MILP',pricing_proof=dict(PASS=True)):pass


def test_boolean_only_or_missing_migration_pricing_proof_is_rejected(tmp_path):
    backend=MockBackend();build=backend.build_lp('2025-05-17',tmp_path,'rho',[],None)
    pricing=backend.price(build,'OPTIMALITY',0)
    for field in ('inactive_migration_covered','full_omitted_lp_pool_priced','original_rows_and_objective'):
        changed=json.loads(json.dumps(pricing));changed['certificate'][field]=False
        with pytest.raises(PermissionError,match='FULL_POOL_LP_PRICING'):
            verified_pricing_certificate(build,changed,dict(PASS=True),day='2025-05-17',component='rho',locks=[])
    status=initial_fast_status();status['INTEGER_DOMAIN_CLOSURE_PROVEN']=True
    with pytest.raises(PermissionError,match='INTEGER_DOMAIN_CERTIFICATE'):validate_fast_status(status)


def test_no_production_before_speed_or_may12_before_may19(tmp_path):
    canary,policy=permit_fixture(tmp_path/'canary')
    with pytest.raises(PermissionError,match='FAST_DATE_NOT_AUTHORIZED'):
        run_fast_date('2025-05-12',MockBackend(),canary,policy,tmp_path/'blocked')
    permit,policy=permit_fixture(tmp_path/'production',mode='PRODUCTION')
    predecessor=dict(day='2025-05-19',mode='PRODUCTION',permit_sha256=permit.identity)
    with pytest.raises(PermissionError,match='MAY19_TRACTABILITY'):
        run_fast_date('2025-05-12',MockBackend(),permit,policy,tmp_path/'blocked',predecessor_receipt=predecessor)
    speed=Path(permit.document['speed_gate']['path']);speed.write_text(json.dumps(dict(PASS=True)))
    with pytest.raises(PermissionError,match='FAST_RECEIPT_DRIFT'):permit.verify()


def test_policy_tolerance_or_method_changes_rejected():
    policy=solver_policy(fake_gurobi());assert validate_frozen_policy(policy)
    for name,value in [('Method',1),('MIPGap',.1),('Crossover',0)]:
        changed=json.loads(json.dumps(policy));changed['parameters'][name]=value
        with pytest.raises(PermissionError):validate_frozen_policy(changed)


def test_fill_in_metrics_keep_unavailable_values_null():
    parsed=fill_in_metrics('Ordering time: 149.50s\nFactor NZ : 1.562e+09 (roughly 15 GB)\nFactor Ops : 2.42e+12\n')
    assert parsed['factor_nnz']==1562000000 and parsed['factor_memory_printed']==15
    assert parsed['factor_memory_unit']=='GB' and parsed['ordering_seconds']==149.5
    assert parsed['barrier_seconds'] is None and parsed['root_completed'] is None


def test_real_cli_canonical_stagebuild_and_mock_lp_only(tmp_path):
    adapter=tmp_path/'fast_cli_fixture.py'
    adapter.write_text(textwrap.dedent('''
        import gurobipy as gp
        import v42_a_stage_domain_v2.fast_runner as runner
        from test_v42_a_stage_fast_runner import MockBackend
        def reject(*args,**kwargs):raise AssertionError('REAL_NATIVE_OPTIMIZER_FORBIDDEN')
        gp.Model.optimize=reject
        runner.other_heavy_optimizers=lambda:[]
        class Backend(MockBackend):pass
    '''))
    permit,policy=permit_fixture(tmp_path/'permit',extra_sources=[adapter,Path(__file__)])
    path=tmp_path/'permit.json';path.write_text(permit.canonical_json)
    environment=os.environ.copy()
    environment['PYTHONPATH']=str(tmp_path)+os.pathsep+str(Path(__file__).parent)+os.pathsep+environment.get('PYTHONPATH','')
    command=[sys.executable,'-B','-m','v42_a_stage_domain_v2.fast_runner','--day','2025-05-19',
        '--permit',str(path),'--policy',permit.document['solver_policy']['path'],
        '--backend','fast_cli_fixture:Backend','--output',str(tmp_path/'cli')]
    child=subprocess.run(command,env=environment,capture_output=True,text=True,cwd=Path(__file__).resolve().parents[1],timeout=30)
    assert child.returncode==0,child.stdout+child.stderr
    result=json.loads((tmp_path/'cli/FAST_RESULT.json').read_text())
    assert result['classification']=='CANARY_LP_PRICING_CLOSED'
    assert len(result['native_calls'])==1 and result['native_calls'][0]['phase']=='LP'
    assert result['native_seconds']==.25 and not result['passes']
