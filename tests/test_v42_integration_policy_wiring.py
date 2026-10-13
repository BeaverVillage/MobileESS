"""No-solver tests for final-plan policy construction and coordinator binding."""
from copy import deepcopy
import json
from types import SimpleNamespace

import numpy as np
import pytest

from v42_integration.a_engine import digest
from v42_integration.coordinator import run_arm
from v42_integration.fixture_validation import build_fixture
from v42_integration.mess_actual import consume_frozen_mess
from v42_integration.policy import compile_policy
from v42_integration.production_case import compile_production_control_policy, RESOURCE_DISTRIBUTION_FIELDS


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf8')


def inputs(tmp_path, stage='A2'):
    case=build_fixture(tmp_path/'INPUT')
    a_case=case.make_a_case('B3',stage,case.initial_mess,tmp_path/stage)
    grid=a_case.grid
    sites=sorted(case.actual_arguments['capacities'])
    nominal={s:[1.]*96 for s in sites}
    aidc=dict(selected_jobs={},AIDC_P_by_site=deepcopy(nominal),
        AIDC_Q_by_site={s:(np.asarray(row)*np.tan(np.arccos(.95))).tolist() for s,row in nominal.items()},
        CC4_service={'GPUh':48.},CC4_carryout={'GPUh':0.},
        anonymous_resource_envelope=[dict(site=s,slot_start=t*900.,slot_end=(t+1)*900.,
            gpu_capacity=1.,source_variable=f'anonymous_GPU[{s},{t}]',carryout_end=86400.)
            for t in range(96) for s in sites],
        FULL_feasible=True,FULL_max_residual=0.,evidence_kind='NAMED_SYNTHETIC_TRANSPORT_FIXTURE',
        nominal_site_GPU=deepcopy(nominal),reserve_site_GPU={s:[0.]*96 for s in sites},
        known_site_GPU={s:[0.]*96 for s in sites},resource_sites=sites,
        CC4_reserve_service={'GPUh':0.},CC4_reserve_carryout={'GPUh':0.})
    old_fields=('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')
    aidc['aidc_anchor']=digest({key:aidc[key] for key in old_fields})
    aidc['resource_distribution_sha']=digest({key:aidc[key] for key in RESOURCE_DISTRIBUTION_FIELDS})
    write(tmp_path/stage/'A_RESULT.json',aidc)
    binding=dict(science_sha='FIXTURE_SCIENCE',qos_sha=case.qos_provider.stats.sha,case_sha=case.case_sha,
                 aidc_anchor=aidc['aidc_anchor'],mess_anchor=case.initial_mess['plan_sha'])
    cc4=dict(model_id='LGBM_weighted_c1_s20260924',q50_hourly_GPUh=[2.]*24,
        q90_hourly_GPUh=[2.]*24,kernel=[1.],prediction_sha='1'*64,runtime_sha='2'*64,kernel_sha='3'*64,
        prediction_index=412,source_receipts=[],convolution={'scope':'NAMED_SYNTHETIC_INPUT_INTERFACE'})
    args=dict(arm='B3',aidc=aidc,mess=case.initial_mess,bindings=binding,
        envelope=aidc['anonymous_resource_envelope'],output=tmp_path,
        mess_validation=consume_frozen_mess(case.initial_mess,day_begin_seconds=0,evidence_kind='SYNTHETIC_FIXTURE'),
        coefficients=grid.coefficients,power=grid.power,idle_kw=0.,swing_kw=1.,
        capacities=case.actual_arguments['capacities'],grid_authority=grid.authority,
        cc4_inputs=cc4,initial_state_sha='4'*64)
    return args


def test_production_policy_consumes_final_resource_mass_and_reload_source_bindings(tmp_path):
    args=inputs(tmp_path)
    policy=compile_production_control_policy(**args)
    assert policy.bindings['aidc_anchor']==args['aidc']['aidc_anchor']
    assert policy.bindings['mess_anchor']==args['mess']['plan_sha']
    assert policy.bindings['cc4_sha']=='1'*64 and policy.bindings['initial_state_sha']=='4'*64
    assert policy.document['scenario_audit']['source_authority']['stress_allocation_source']=='A_STAGE_OPTIMIZED_RESERVE'
    assert not policy.document['scenario_audit']['Q90_actual_load_addition']
    assert policy.document['metrics']['Native_Optimize_calls']==0
    assert (tmp_path/'A_STAGE_RESOURCE_ENVELOPE.json').is_file()
    assert (tmp_path/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json').is_file()
    restored=type(policy).load(tmp_path/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json',bindings=policy.bindings)
    assert restored.sha==policy.sha
    with pytest.raises(ValueError,match='ANCHOR_MISMATCH'):
        restored.require_bindings(dict(policy.bindings,initial_state_sha='5'*64))


@pytest.mark.parametrize('defect,reason',[
    ('missing','NOT_EXPORTED'),('sha','DISTRIBUTION_SHA_DRIFT'),
    ('mass','FULL_GPUH_MASS_DRIFT'),('power','FINAL_POWER_DRIFT')])
def test_production_rejects_missing_stale_or_double_counted_allocation(tmp_path,defect,reason):
    args=inputs(tmp_path)
    aidc=args['aidc']
    if defect=='missing':del aidc['reserve_site_GPU']
    elif defect=='sha':aidc['reserve_site_GPU']['A'][0]=1.
    elif defect=='mass':
        aidc['CC4_reserve_carryout']['GPUh']=48.
        aidc['resource_distribution_sha']=digest({key:aidc[key] for key in RESOURCE_DISTRIBUTION_FIELDS})
        write(tmp_path/'A2/A_RESULT.json',aidc)
    else:aidc['AIDC_P_by_site']['A'][0]+=1.
    with pytest.raises(ValueError,match=reason):compile_production_control_policy(**args)


class NoSolver:
    def remaining(self):return 0.


def install_transport(monkeypatch, case):
    """Stage output transport stubs, never evidence of Optimize or feasibility."""
    def a(current,mess,qos,budget):
        result=deepcopy(case.reference_aidc)
        result['CC4_service']={'transport_'+current.stage:0.}
        fields=('selected_jobs','AIDC_P_by_site','AIDC_Q_by_site','CC4_service','CC4_carryout','anonymous_resource_envelope')
        result.update(aidc_anchor=digest({key:result[key] for key in fields}),FULL_feasible=True,
            arm=current.arm,stage=current.stage,case_sha='TRANSPORT_'+current.stage,
            engine='TEST_OUTPUT_TRANSPORT_NO_NATIVE')
        return result
    case.make_m_case=lambda arm,stage,aidc,folder:SimpleNamespace(
        identity={'aidc_anchor':aidc['aidc_anchor']},stage=stage,arm=arm)
    def m(current,initial,registry,budget):
        plan=deepcopy(case.initial_mess)
        plan.pop('plan_sha');plan['transport_marker']=current.stage;plan['plan_sha']=digest(plan)
        return dict(FULL_validated=True,mess=plan,incumbent_registry=[],case_sha='TRANSPORT_'+current.stage,
                    engine='TEST_OUTPUT_TRANSPORT_NO_NATIVE'),None
    monkeypatch.setattr('v42_integration.coordinator.optimize_aidc',a)
    monkeypatch.setattr('v42_integration.coordinator.optimize_mess',m)


def test_coordinator_b3_factory_receives_a2_m2_and_expanded_bindings(tmp_path,monkeypatch):
    case=build_fixture(tmp_path/'INPUT')
    install_transport(monkeypatch,case)
    observed={}
    def factory(**args):
        observed.update(args)
        bindings=dict(args['bindings'],cc4_sha='1'*64,runtime_sha='2'*64,response_sha='3'*64,initial_state_sha='4'*64)
        return compile_policy(args['envelope'],bindings,case.signed_grid_coefficients)
    case.control_policy_factory=factory
    result=run_arm('B3',case,NoSolver(),tmp_path/'OUTPUT',planning_only=True)
    assert observed['aidc']['stage']=='A2' and observed['mess']['transport_marker']=='M2'
    assert result['freeze']['sensitivity_policy_enabled']
    assert result['freeze']['cc4_sha']=='1'*64
    assert result['freeze']['aidc_anchor']==observed['aidc']['aidc_anchor']
    manifest=json.loads((tmp_path/'OUTPUT/CONTROL_POLICY_SHA_MANIFEST.json').read_text())
    assert manifest['final_A_stage']=='A2' and manifest['final_MESS_stage']=='M2'
    assert not manifest['stale_A1_policy_reused']


def test_coordinator_actual_consumer_receives_all_expanded_policy_bindings(tmp_path,monkeypatch):
    case=build_fixture(tmp_path/'INPUT')
    install_transport(monkeypatch,case)
    observed={}
    def factory(**args):
        binding=dict(args['bindings'],cc4_sha='1'*64,runtime_sha='2'*64,response_sha='3'*64,initial_state_sha='4'*64)
        return compile_policy(args['envelope'],binding,case.signed_grid_coefficients)
    def actual(**args):
        observed.update(args)
        result={key:[] for key in ('job_event_ledger','reservation_ledger','cc4_depletion_ledger',
            'migration_receipts','qos_ledger','qos_budget_ledger','queue_ledger','carryout','rule_consumption_receipt')}
        return dict(result,receipt=dict(capacity_violations=0,actual_occupation_GPUh=0.,
            actual_compute_GPUh=0.,actual_global_reoptimization=0,actual_power_recomputed=False),physical=None)
    case.control_policy_factory=factory
    monkeypatch.setattr('v42_integration.coordinator.run_actual',actual)
    run_arm('B1',case,NoSolver(),tmp_path/'OUTPUT')
    assert observed['expected_bindings']==observed['frozen_policy'].bindings
    assert observed['expected_bindings']['initial_state_sha']=='4'*64
    assert observed['expected_bindings']['response_sha']=='3'*64


@pytest.mark.parametrize('arm',['B0','B2'])
def test_coordinator_b0_b2_never_call_grid_policy_factory(tmp_path,monkeypatch,arm):
    case=build_fixture(tmp_path/'INPUT')
    install_transport(monkeypatch,case)
    def forbidden(**kwargs):raise AssertionError('GRID_AWARE_FACTORY_WAS_CALLED')
    case.control_policy_factory=forbidden
    result=run_arm(arm,case,NoSolver(),tmp_path/'OUTPUT',planning_only=True)
    assert not result['freeze']['sensitivity_policy_enabled']
    assert not (tmp_path/'OUTPUT/OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json').exists()
