"""Adversarial guard and acceptance tests; underlying optimize is never called."""
from types import SimpleNamespace
from pathlib import Path
from datetime import date, datetime, timezone
import ast
import pytest

from v42_a_stage_domain_v2.execution import (
    STRESS_DATES, BLOCK_REASON, day_from_authority, require_action_authorized,
    guarded_optimize, tag_model_for_day, install_gurobi_backstop,
    native_execution_scope, guard_model_optimize,
)
from v42_a_stage_domain_v2.status import (
    STATUS_FIELDS, initial_domain_status, close_feasibility, close_lp_pricing,
    close_integer_domain, accept_production_domain, validate_domain_status,
    require_production_domain_accepted,
)
from v42_a_stage_domain_v2.telemetry import FutureRunTelemetry


@pytest.mark.parametrize('day', sorted(STRESS_DATES))
@pytest.mark.parametrize('stage', ['P1','P2','FEASIBILITY_LP','FEASIBILITY_MIP',
    'A1','PLANNING_FREEZE','ACTUAL','FRESH_AC'])
def test_all_stress_dates_and_execution_stages_fail_closed(day, stage):
    with pytest.raises(PermissionError, match=BLOCK_REASON):
        require_action_authorized(dict(identity=dict(day=day)),stage)


def test_timestamp_date_objects_and_conflicting_identity():
    for value in ('2025-05-17T00:00:00+10:00',date(2025,5,17),
            datetime(2025,5,17,tzinfo=timezone.utc)):
        with pytest.raises(PermissionError,match=BLOCK_REASON):
            require_action_authorized(value)
    with pytest.raises(PermissionError,match=BLOCK_REASON):
        require_action_authorized(dict(day='2025-05-01',payload=dict(day='2025-05-19')))


def test_missing_date_fails_closed_at_production_boundary():
    with pytest.raises(PermissionError,match='A_STAGE_PRODUCTION_DAY_REQUIRED'):
        require_action_authorized(dict(stage='A1'))
    assert day_from_authority(dict(stage='SYNTHETIC_FIXTURE')) is None


def test_wrapper_does_not_enter_sentinel_optimizer():
    class Sentinel:
        calls=0
        def optimize(self,*args,**kwargs):
            self.calls+=1
            raise AssertionError('underlying native optimize must not run')
    model=Sentinel()
    for day in STRESS_DATES:
        with pytest.raises(PermissionError,match=BLOCK_REASON):
            guarded_optimize(model,day)
    assert model.calls==0


def test_backstop_blocks_direct_copied_and_relaxed_models_without_solver():
    class SentinelModel:
        calls=0
        def optimize(self,*args,**kwargs):
            SentinelModel.calls+=1
            raise AssertionError('underlying native optimize must not run')
        def copy(self):return SentinelModel()
        def relax(self):return SentinelModel()
        def presolve(self):return SentinelModel()
        def fixed(self):return SentinelModel()
    module=SimpleNamespace(Model=SentinelModel)
    install_gurobi_backstop(module)
    guarded=SentinelModel.optimize
    install_gurobi_backstop(module)
    assert SentinelModel.optimize is guarded
    for day in STRESS_DATES:
        original=tag_model_for_day(SentinelModel(),day)
        with pytest.raises(PermissionError,match=BLOCK_REASON):original.presolve()
        for model in (original,original.copy(),original.relax(),original.fixed()):
            assert model._v42_a_stage_day==day
            with pytest.raises(PermissionError,match=BLOCK_REASON):
                model.optimize()
    assert SentinelModel.calls==0


def test_static_model_tags_do_not_authorize_execution():
    model=SimpleNamespace()
    tag_model_for_day(model,'2025-05-17')
    assert model._v42_a_stage_day=='2025-05-17'
    with pytest.raises(PermissionError,match=BLOCK_REASON):guard_model_optimize(model)


def test_other_authority_cannot_relabel_a_stress_date_model():
    model=tag_model_for_day(SimpleNamespace(),'2025-05-17')
    with pytest.raises(PermissionError,match=BLOCK_REASON):tag_model_for_day(model,'2025-05-01')
    with pytest.raises(PermissionError,match=BLOCK_REASON):guarded_optimize(model,'2025-05-01')
    assert model._v42_a_stage_day=='2025-05-17'


def test_scoped_identity_cannot_mask_a_stress_model():
    with native_execution_scope('2025-05-01'):
        with pytest.raises(PermissionError,match=BLOCK_REASON):
            guard_model_optimize(tag_model_for_day(SimpleNamespace(),'2025-05-19'))


def test_every_status_is_explicit_and_initially_unaccepted():
    status=initial_domain_status(hard_physical_domain_defined=True,authority='V2')
    assert all(type(status[k]) is bool for k in STATUS_FIELDS)
    assert status['ACTIVE_DOMAIN_SUBSET']
    assert not status['PRODUCTION_DOMAIN_ACCEPTED']
    with pytest.raises(PermissionError,match='PRODUCTION_DOMAIN_CLOSURE_REQUIRED'):
        require_production_domain_accepted(status)


def test_feasibility_and_complete_root_lp_pricing_do_not_close_integer_domain():
    status=initial_domain_status(hard_physical_domain_defined=True)
    status=close_feasibility(status,dict(PASS=True))
    status=close_lp_pricing(status,dict(PASS=True,full_omitted_lp_pool_priced=True))
    assert status['FEASIBILITY_CLOSED'] and status['LP_PRICING_CLOSED']
    assert not status['INTEGER_DOMAIN_CLOSURE_PROVEN']
    with pytest.raises(PermissionError,match='ROOT_LP_PRICING_IS_NOT_INTEGER_DOMAIN_CLOSURE'):
        close_integer_domain(status,dict(kind='ROOT_LP_REDUCED_COST',PASS=True),lambda proof:dict(PASS=True))
    with pytest.raises(PermissionError,match='PRODUCTION_DOMAIN_CLOSURE_REQUIRED'):
        accept_production_domain(status,physical_certificate=dict(PASS=True),objective_certificate=dict(PASS=True))


def test_bare_integer_closure_boolean_is_rejected():
    status=initial_domain_status(hard_physical_domain_defined=True)
    status['INTEGER_DOMAIN_CLOSURE_PROVEN']=True
    with pytest.raises(PermissionError,match='INTEGER_DOMAIN_CLOSURE_CERTIFICATE_REQUIRED'):
        validate_domain_status(status)


def test_integer_certificate_verifier_failure_cannot_accept():
    status=initial_domain_status(hard_physical_domain_defined=True)
    cert=dict(kind='COMPLETE_FINITE_DOMAIN_ACTIVATION',full_scientific_domain_covered=True,
        authority_sha256='a'*64,evidence_sha256='b'*64)
    with pytest.raises(PermissionError,match='INDEPENDENT_INTEGER_DOMAIN_VERIFICATION_REQUIRED'):
        close_integer_domain(status,cert,lambda proof:dict(PASS=False))


def test_acceptance_needs_independent_integer_physical_and_objective_certificates():
    # This is a small synthetic state-machine fixture, not a production proof.
    status=initial_domain_status(hard_physical_domain_defined=True)
    status=close_feasibility(status,dict(PASS=True,scope='SYNTHETIC_FIXTURE'))
    cert=dict(kind='COMPLETE_FINITE_DOMAIN_ACTIVATION',full_scientific_domain_covered=True,
        authority_sha256='a'*64,evidence_sha256='b'*64,scope='SYNTHETIC_FIXTURE')
    status=close_integer_domain(status,cert,lambda proof:dict(PASS=True,scope='SYNTHETIC_FIXTURE'))
    for physical,objective in ((False,True),(True,False)):
        with pytest.raises(PermissionError,match='PRODUCTION_DOMAIN_CLOSURE_REQUIRED'):
            accept_production_domain(status,physical_certificate=dict(PASS=physical),objective_certificate=dict(PASS=objective))
    accepted=accept_production_domain(status,physical_certificate=dict(PASS=True),objective_certificate=dict(PASS=True))
    assert require_production_domain_accepted(accepted)['PRODUCTION_DOMAIN_ACCEPTED']
    assert not status['PRODUCTION_DOMAIN_ACCEPTED']


def test_production_entrypoints_reject_before_files_build_or_native_solver(tmp_path):
    from v42_pr134_b1.worker import execute
    from v42_pr134_b1.native import run_a1
    from v42_pr134_b1.replay import freeze_planning,actual,fresh
    from v42_pr134_adaptive.solve_snapshot import main as snapshot
    from v42_pr134_adaptive.capacity_master import main as master
    from v42_pr134_adaptive.minimum_probe import main as minimum
    from v42_pr134_adaptive.restricted import execute as restricted
    from v42_pr134_may19.solve import main as shell_solve
    from v42_pr134_may19.production import main as shell_production
    from v42_pr134_repair.original_diagnosis import run as original_diagnosis
    from v42_pr134_repair.certificate import run as original_certificate
    from v42_root.worker import optimize as root_optimize
    from v42_root.start import validate_source
    from v42_exact.worker import optimize as exact_optimize
    from v42_native.aidc import solve as native_solve
    for day in sorted(STRESS_DATES):
        calls=(lambda:execute(dict(day=day,stage='A1')),
            lambda:run_a1(dict(day=day),tmp_path,tmp_path,None),
            lambda:freeze_planning(tmp_path,day,tmp_path,tmp_path,None),
            lambda:actual(tmp_path,dict(day=day),tmp_path),
            lambda:fresh(tmp_path,day,tmp_path,tmp_path,tmp_path,None,None),
            lambda:snapshot(day,'NO_RUN'),lambda:master(day),lambda:minimum(day),
            lambda:restricted(day,[],'NO_RUN'),lambda:original_diagnosis(day),lambda:original_certificate(day),
            lambda:root_optimize(None,None,None,None,None,(dict(day=day),),None),
            lambda:validate_source(None,None,(dict(day=day),),None,None,None),
            lambda:exact_optimize(None,None,None,None,None,(dict(day=day),)),
            lambda:native_solve('A1',SimpleNamespace(stage='A1'),{},None,None,None,day=day))
        for call in calls:
            with pytest.raises(PermissionError,match=BLOCK_REASON):call()
    for call in (lambda:shell_solve('NO_RUN'),lambda:shell_production('NO_RUN')):
        with pytest.raises(PermissionError,match=BLOCK_REASON):call()
    assert list(tmp_path.iterdir())==[]


def test_telemetry_is_passive_and_distinguishes_observation_from_root_duration():
    class Model:
        Params=SimpleNamespace(Method=1,Threads=1)
        Runtime=.25
        def cbGet(self,name):return 0.
    callback=SimpleNamespace(SIMPLEX=1,BARRIER=2,MIPNODE=3,SPX_ITRCNT=4,
        SPX_OBJVAL=5,SPX_PRIMINF=6,SPX_DUALINF=7,BARRIER_ITRCNT=8,
        BARRIER_PRIMINF=9,BARRIER_DUALINF=10,BARRIER_COMPL=11,MIPNODE_NODCNT=12,
        MIPNODE_STATUS=13,MIPNODE_OBJBND=14)
    telemetry=FutureRunTelemetry(Model(),day='SYNTHETIC_FIXTURE',sample_interval=0.,max_samples=2)
    telemetry.begin_objective('rho',group='P1',remaining_seconds=1.)
    for where in (1,2,3):telemetry.callback(Model(),where,SimpleNamespace(Callback=callback))
    telemetry.finish_objective(Model())
    receipt=telemetry.receipt()
    assert len(receipt['root_and_solver_observations'])==2
    assert receipt['dropped_samples']==1
    assert receipt['objective_stage_timings'][0]['group']=='P1'
    assert receipt['extra_relaxations_or_optimization_calls']==0
    assert receipt['exact_condition_number_computed'] is False
    assert receipt['synthetic_root_duration_claimed'] is False


def test_model_tags_are_present_in_all_native_a_stage_builders():
    root=Path(__file__).resolve().parents[1]
    for path in ('v42_root/native.py','v42_exact/native.py','v42_compact/native.py',
            'v42_boundary/model.py','v42_temporal/native.py','v42_native/aidc.py'):
        tree=ast.parse((root/path).read_text(encoding='utf8'))
        assert any(isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
            and node.func.id=='tag_model_for_day' for node in ast.walk(tree)),path

