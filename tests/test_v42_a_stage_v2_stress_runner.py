"""Permit/policy/control-flow fixtures; no Gurobi optimizer backend is invoked."""
from pathlib import Path
from types import SimpleNamespace
import json
import os
import subprocess
import sys
import textwrap
import pytest
import gurobipy as gp
from v42_a_stage_domain_v2.execution import (REQUIRED_STRESS_GATES,REQUIRED_RUN_SOURCE_NAMES,
    create_stress_run_permit,stress_run_scope,require_action_authorized,guard_model_optimize,
    tag_model_for_day,STRESS_RUN_ORDER,accepted_pipeline_scope)
from v42_a_stage_domain_v2.status import initial_domain_status,close_feasibility,close_integer_domain,accept_production_domain
from v42_a_stage_domain_v2.solver_policy import solver_policy,apply_policy
from v42_a_stage_domain_v2.stress_runner import run_date,StageBuild


def permit_fixture(folder):
    folder.mkdir(exist_ok=True)
    gates={}
    for key in REQUIRED_STRESS_GATES:
        path=folder/(key+'.json');path.write_text(json.dumps(dict(PASS=True,scope='SYNTHETIC_CONTROL_FLOW_FIXTURE')))
        gates[key]=path
    package=Path(__file__).resolve().parents[1]/'v42_a_stage_domain_v2'
    sources=[package/name for name in REQUIRED_RUN_SOURCE_NAMES]
    return create_stress_run_permit(gates,sources),gates


def fake_gurobi():
    specs={'NodeMethod':('NodeMethod',int,-1,-1,5,-1),
        'MIPFocus':('MIPFocus',int,0,0,3,0),'Crossover':('Crossover',int,-1,-1,5,-1)}
    return SimpleNamespace(gurobi=SimpleNamespace(version=lambda:(13,0,2)),getParamInfo=lambda name:specs[name])


def test_gate_missing_false_corrupt_or_source_drift_rejected(tmp_path):
    permit,gates=permit_fixture(tmp_path/'permit')
    assert permit.verify()
    with pytest.raises(PermissionError,match='STRESS4_ALL_PRE_RUN_GATES_REQUIRED'):
        create_stress_run_permit({},[])
    key=next(iter(gates));gates[key].write_text(json.dumps(dict(PASS=False)))
    with pytest.raises(PermissionError,match='STRESS4_GATE_RECEIPT_DRIFT'):permit.verify()


def test_verified_scope_permits_only_four_dates_and_blocks_premature_pipeline(tmp_path):
    permit,_=permit_fixture(tmp_path/'permit')
    with stress_run_scope(permit):
        for day in STRESS_RUN_ORDER:
            assert require_action_authorized(day,'A1')==day
            guard_model_optimize(tag_model_for_day(SimpleNamespace(),day))
            for action in ('PLANNING_FREEZE','ACTUAL','FRESH_AC'):
                with pytest.raises(PermissionError,match='PRODUCTION_DOMAIN_CLOSURE_REQUIRED'):
                    require_action_authorized(day,action)
        for date in ('2025-05-01','2025-05-31','2025-06-01'):
            with pytest.raises(PermissionError,match='OTHER_27_MAY_DATES_NOT_AUTHORIZED'):
                require_action_authorized(date,'A1')
    with pytest.raises(PermissionError,match='STRESS_DATE_OPTIMIZATION_NOT_AUTHORIZED'):
        require_action_authorized('2025-05-17')


def test_policy_is_global_preserves_scientific_thresholds_and_auto_crossover():
    policy=solver_policy(fake_gurobi())
    assert policy['parameters']['Threads']==1
    assert policy['parameters']['Method']==2
    assert policy['parameters']['NodeMethod']==1
    assert policy['parameters']['MIPFocus']==3
    assert policy['parameters']['Crossover']==-1
    assert not policy['parameter_sweep']
    for name,value in policy['preserved_scientific_settings'].items():assert policy['parameters'][name]==value
    with pytest.raises(PermissionError,match='DIAGNOSTIC_CROSSOVER0_NOT_PRODUCTION_POLICY'):
        solver_policy(fake_gurobi(),frozen_settings=dict(policy['original_authority_parameters'],Crossover=0))


def test_policy_rejects_solver_version_drift():
    policy=solver_policy(fake_gurobi())
    changed=SimpleNamespace(gurobi=SimpleNamespace(version=lambda:(12,0,0)))
    with pytest.raises(PermissionError,match='FROZEN_GUROBI_VERSION_DRIFT'):
        apply_policy(SimpleNamespace(),policy,changed)


def test_accepted_pipeline_still_forbids_every_native_reoptimization(tmp_path):
    permit,_=permit_fixture(tmp_path/'permit')
    status=close_feasibility(initial_domain_status(hard_physical_domain_defined=True),dict(PASS=True,scope='SYNTHETIC_FIXTURE'))
    certificate=dict(kind='COMPLETE_FINITE_DOMAIN_ACTIVATION',full_scientific_domain_covered=True,
        authority_sha256='a'*64,evidence_sha256='b'*64,scope='SYNTHETIC_FIXTURE')
    status=close_integer_domain(status,certificate,lambda proof:dict(PASS=True,scope='SYNTHETIC_FIXTURE'))
    status=accept_production_domain(status,physical_certificate=dict(PASS=True),objective_certificate=dict(PASS=True))
    with stress_run_scope(permit),accepted_pipeline_scope('2025-05-17',status):
        assert require_action_authorized('2025-05-17','ACTUAL')=='2025-05-17'
        with pytest.raises(PermissionError,match='ACTUAL_OR_FRESH_REOPTIMIZATION_FORBIDDEN'):
            guard_model_optimize(tag_model_for_day(SimpleNamespace(),'2025-05-17'))


class MockModel:
    """Pure Python state-machine fixture: optimize does not enter a solver."""
    NumVars=1;NumConstrs=1;NumBinVars=0;NumIntVars=1;NumNZs=1
    NumQConstrs=0;NumQNZs=0;NumSOS=0;NumGenConstrs=0
    Status=gp.GRB.OPTIMAL;SolCount=1;Runtime=.25;Work=.01;NodeCount=0.
    ObjVal=0.;ObjBound=0.;MIPGap=0.
    def __init__(self):self.Params=SimpleNamespace();self.calls=0
    def update(self):pass
    def setObjective(self,*args):pass
    def setParam(self,name,value):setattr(self.Params,name,value)
    def optimize(self,callback):self.calls+=1
    def getAttr(self,name):return [0.]
    def dispose(self):pass


class MockBackend:
    def __init__(self):self.models=[];self.locks=[];self.pipeline_calls=0
    def build(self,day,folder,component,locks,previous):
        self.locks.append(list(locks));model=MockModel();self.models.append(model)
        return StageBuild(model,None,[('rho',0),('migration_count',0),('shift_slots',0),('prestart_changes',0)],
            None,None,(dict(day=day),),None,dict(scientific_identity_PASS=True,STAY_DOMAIN_COMPLETE=True,stage_equivalence=dict(PASS=True,scope='SYNTHETIC_CONTROL_FLOW_FIXTURE'),
                input_identity=dict(PASS=True,scope='SYNTHETIC_CONTROL_FLOW_FIXTURE'),domain_census=dict(scope='SYNTHETIC_CONTROL_FLOW_FIXTURE'),
                static_artifacts=[dict(path='SYNTHETIC_CONTROL_FLOW_FIXTURE',sha256='a'*64,bytes=0)],base_matrix_sha256='b'*64))
    def verify(self,build,point,component):
        return dict(PASS=True,physical=dict(PASS=True,scope='SYNTHETIC_CONTROL_FLOW_FIXTURE'),selected_jobs={},controls=[])
    def integer_certificate(self,*args):return dict(PASS=True,scope='SYNTHETIC_CONTROL_FLOW_FIXTURE')
    def production_pipeline(self,*args):self.pipeline_calls+=1;raise AssertionError('No unresolved domain may call physical pipeline')


def test_runner_cumulative_budget_new_locks_and_honest_unresolved_domain(tmp_path,monkeypatch):
    import v42_a_stage_domain_v2.stress_runner as runner
    monkeypatch.setattr(runner,'other_heavy_optimizers',lambda:[])
    permit,_=permit_fixture(tmp_path/'permit');policy=solver_policy(fake_gurobi());backend=MockBackend()
    # Only the pure-Python mock Model.optimize method is called. Production
    # Gurobi Model.optimize remains uninvoked throughout this fixture.
    result=run_date('2025-05-17',backend,permit,policy,tmp_path/'run')
    assert result['native_seconds']==1.
    assert len(result['passes'])==4
    assert result['classification']=='A1_ACTIVE_DOMAIN_SOLVED_DOMAIN_CLOSURE_UNRESOLVED'
    assert result['A1_active_domain_feasible'] and not result['A1_full_domain_accepted']
    assert not result['integer_domain_closure_proven']
    assert backend.pipeline_calls==0
    assert [len(locks) for locks in backend.locks]==[0,1,2,3]
    assert all(lock['current_new_run_only'] and not lock['historical_lock_imported'] for lock in backend.locks[-1])
    assert all(model.Params.Crossover==-1 for model in backend.models)
    assert all(model.Params.TimeLimit<=3600 for model in backend.models)
    external=json.loads((tmp_path/'run/EXTERNAL_STATIC_ARTIFACTS.json').read_text())
    assert external['written_before_optimize'] and external['base_matrix_sha256']=='b'*64
    assert (tmp_path/'run/rho/BUILD_RESOURCE_TELEMETRY.json').exists()


def test_other_27_dates_and_budget_extension_never_reach_backend(tmp_path):
    permit,_=permit_fixture(tmp_path/'permit');backend=MockBackend();policy=solver_policy(fake_gurobi())
    with pytest.raises(PermissionError,match='OTHER_27_MAY_DATES_NOT_AUTHORIZED'):
        run_date('2025-05-01',backend,permit,policy,tmp_path/'run')
    with pytest.raises(PermissionError,match='FROZEN_CUMULATIVE_A1_BUDGET_REQUIRED'):
        run_date('2025-05-17',backend,permit,policy,tmp_path/'run',budget_seconds=7200)
    assert not backend.models


@pytest.mark.parametrize('failure',[MemoryError('fixture allocation failed'),OSError(12,'fixture allocation failed')])
def test_resource_exhaustion_does_not_become_global_scientific_failure(tmp_path,monkeypatch,failure):
    import v42_a_stage_domain_v2.stress_runner as runner
    monkeypatch.setattr(runner,'other_heavy_optimizers',lambda:[])
    permit,_=permit_fixture(tmp_path/'permit')
    class ResourceBackend:
        def build(self,*args):raise failure
    result=run_date('2025-05-17',ResourceBackend(),permit,solver_policy(fake_gurobi()),tmp_path/'run')
    assert result['classification']=='UNRESOLVED'
    assert result['computational_resource_failure']
    assert not result['global_scientific_stop']
    observation=json.loads((tmp_path/'run/rho/BUILD_RESOURCE_TELEMETRY.json').read_text())
    assert observation['phase']=='BUILD' and observation['observational_only']


def test_native_error_accounts_only_failed_current_call_once(tmp_path,monkeypatch):
    import v42_a_stage_domain_v2.stress_runner as runner
    monkeypatch.setattr(runner,'other_heavy_optimizers',lambda:[])
    permit,_=permit_fixture(tmp_path/'permit')
    class ErrorBackend(MockBackend):
        def build(self,*args):
            build=super().build(*args)
            if len(self.models)==2:
                def failed(callback):
                    build.model.Runtime=.5
                    raise gp.GurobiError(10001,'SYNTHETIC_NATIVE_MEMORY_ERROR')
                build.model.optimize=failed
            return build
    result=run_date('2025-05-17',ErrorBackend(),permit,solver_policy(fake_gurobi()),tmp_path/'run')
    assert result['native_seconds']==.75
    assert len(result['passes'])==1 and not result['global_scientific_stop']
    assert result['classification']=='UNRESOLVED'
    receipt=json.loads((tmp_path/'run/migration_count/NATIVE_TELEMETRY.json').read_text())
    assert receipt['objective_stage_timings'][0]['native_seconds']==.5


def subprocess_fixture(tmp_path):
    """Freeze a separate mock adapter for the real python -m entrypoint."""
    _,gates=permit_fixture(tmp_path/'gates')
    adapter=tmp_path/'cli_mock_adapter.py'
    adapter.write_text(textwrap.dedent('''
        from pathlib import Path
        from types import SimpleNamespace
        import json, os
        import gurobipy as gp
        import v42_a_stage_domain_v2.stress_runner as runner
        from v42_a_stage_domain_v2.execution import guard_model_optimize

        evidence_path=Path(os.environ['V42_CLI_MOCK_EVIDENCE'])
        evidence=dict(scope='SYNTHETIC_SUBPROCESS_ONLY',native_optimizer_calls=0,
            builds=[],mock_optimize_calls=[],disposed=[],stagebuild_module=runner.StageBuild.__module__)
        def save():evidence_path.write_text(json.dumps(evidence))
        save()
        def reject_native(*args,**kwargs):
            evidence['native_optimizer_calls']+=1;save()
            raise AssertionError('REAL_NATIVE_OPTIMIZER_FORBIDDEN_IN_CLI_FIXTURE')
        gp.Model.optimize=reject_native
        runner.other_heavy_optimizers=lambda:[]

        class MockModel:
            NumVars=1;NumConstrs=1;NumBinVars=0;NumIntVars=1;NumNZs=1
            NumQConstrs=0;NumQNZs=0;NumSOS=0;NumGenConstrs=0
            Status=gp.GRB.OPTIMAL;SolCount=1;Runtime=.25;Work=.01;NodeCount=0.
            ObjVal=0.;ObjBound=0.;MIPGap=0.
            def __init__(self,component):self.Params=SimpleNamespace();self.component=component
            def update(self):pass
            def setObjective(self,*args):pass
            def setParam(self,name,value):setattr(self.Params,name,value)
            def optimize(self,callback):
                guard_model_optimize(self)
                evidence['mock_optimize_calls'].append(self.component);save()
            def getAttr(self,name):return [0.]
            def dispose(self):evidence['disposed'].append(self.component);save()

        class Backend:
            def __init__(self):self.models=[]
            def build(self,day,folder,component,locks,previous):
                if previous is not None:previous['native_model'].dispose()
                model=MockModel(component)
                assert all(model is not old for old in self.models)
                self.models.append(model)
                evidence['builds'].append(dict(component=component,locks=len(locks),fresh=True,
                    previous_new_run_only=previous is None or all(l['current_new_run_only'] for l in locks)))
                save()
                return runner.StageBuild(model,None,[('rho',0),('migration_count',0),('shift_slots',0),('prestart_changes',0)],
                    None,None,(dict(day=day),),None,dict(scientific_identity_PASS=True,STAY_DOMAIN_COMPLETE=True,
                        stage_equivalence=dict(PASS=True,scope='SYNTHETIC_SUBPROCESS_ONLY'),
                        input_identity=dict(PASS=True,scope='SYNTHETIC_SUBPROCESS_ONLY'),
                        domain_census=dict(scope='SYNTHETIC_SUBPROCESS_ONLY'),
                        static_artifacts=[dict(path='SYNTHETIC_SUBPROCESS_ONLY',sha256='a'*64,bytes=0)],base_matrix_sha256='b'*64))
            def verify(self,*args):
                return dict(PASS=True,physical=dict(PASS=True,scope='SYNTHETIC_SUBPROCESS_ONLY'),selected_jobs={},controls=[])
            def integer_certificate(self,*args):return dict(PASS=True,scope='SYNTHETIC_SUBPROCESS_ONLY')
            def production_pipeline(self,*args):raise AssertionError('UNRESOLVED_SYNTHETIC_DOMAIN_CANNOT_RUN_PIPELINE')
        '''),encoding='utf8')
    package=Path(__file__).resolve().parents[1]/'v42_a_stage_domain_v2'
    permit=tmp_path/'permit.json'
    create_stress_run_permit(gates,[package/name for name in REQUIRED_RUN_SOURCE_NAMES]+[adapter],output=permit)
    policy=tmp_path/'policy.json';policy.write_text(json.dumps(solver_policy(gp)),encoding='utf8')
    environment=os.environ.copy()
    environment['PYTHONPATH']=str(tmp_path)+os.pathsep+environment.get('PYTHONPATH','')
    environment['V42_CLI_MOCK_EVIDENCE']=str(tmp_path/'evidence.json')
    command=[sys.executable,'-B','-m','v42_a_stage_domain_v2.stress_runner',
        '--permit',str(permit),'--policy',str(policy),'--backend','cli_mock_adapter:Backend',
        '--output',str(tmp_path/'run')]
    return command,environment


def test_real_cli_mock_adapter_completes_four_fresh_stages_without_native_optimizer(tmp_path):
    command,environment=subprocess_fixture(tmp_path)
    child=subprocess.run(command+['--day','2025-05-17'],env=environment,capture_output=True,text=True,
        cwd=Path(__file__).resolve().parents[1],timeout=30)
    assert child.returncode==0,child.stdout+child.stderr
    result=json.loads((tmp_path/'run/A1_RESULT.json').read_text())
    evidence=json.loads((tmp_path/'evidence.json').read_text())
    assert result['classification']=='A1_ACTIVE_DOMAIN_SOLVED_DOMAIN_CLOSURE_UNRESOLVED'
    assert len(result['passes'])==4 and result['native_seconds']==1.
    assert not result['A1_full_domain_accepted'] and not result['Planning_freeze']
    assert not result['Actual'] and not result['Fresh_OpenDSS']
    assert evidence['native_optimizer_calls']==0
    assert evidence['stagebuild_module']=='v42_a_stage_domain_v2.stress_runner'
    assert [row['locks'] for row in evidence['builds']]==[0,1,2,3]
    assert all(row['fresh'] and row['previous_new_run_only'] for row in evidence['builds'])
    assert evidence['mock_optimize_calls']==list(('rho','migration_count','shift_magnitude','prestart_relocation'))
    assert evidence['disposed']==evidence['mock_optimize_calls']


def test_real_cli_other_may_date_never_imports_mock_adapter(tmp_path):
    command,environment=subprocess_fixture(tmp_path)
    child=subprocess.run(command+['--day','2025-05-01'],env=environment,capture_output=True,text=True,
        cwd=Path(__file__).resolve().parents[1],timeout=30)
    assert child.returncode==2 and 'invalid choice' in child.stderr
    assert not (tmp_path/'evidence.json').exists()
    assert not (tmp_path/'run').exists()
