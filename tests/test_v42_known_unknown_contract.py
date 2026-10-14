"""Native0 architecture regressions; named toy equations, never May AC."""
from copy import deepcopy
from dataclasses import replace, asdict
import json
import numpy as np
import pytest

from v42_integration.actual import JobEventController,run_actual
from v42_capacity.actual import Environment
from v42_integration.policy import ReservationLedger
from v42_integration.frozen_unknown import compile_unknown_policy,coverage_grammar,FrozenUnknownPolicy
from v42_integration.experimental_actual import ExperimentalJobEventController,run_experimental_actual
from v42_integration.known_commands import compile_known_commands
from test_v42_integration_actual import request,qos,capability
from test_v42_experimental_control import research_provider,observed,policy,metadata


def participant(provider):
    for i in range(100):
        job=replace(observed('SYNTHETIC_UID_'+str(i)),origin_unknown=True)
        receipt=provider.issue(job)
        if receipt.participant:return job,receipt
    raise AssertionError('Fixture participant missing')


def frozen(*,conditions=None,profile='placement',migration_authority=None,service_reallocation=False,scenario='E1'):
    provider=research_provider(scenario);old=policy(provider,profile=profile)
    packet=deepcopy(old.packet)
    packet.bindings=dict(packet.bindings,qos_sha=provider.stats.sha,case_sha=provider.case_sha)
    if conditions is None:
        conditions=coverage_grammar(packet,gpu_gangs=(1,),runtime_bounds=(900.,),time_slots=(0,1,2))
    envelope=[dict(site=s,slot_start=t*900.,slot_end=(t+1)*900.,gpu_capacity=8.,source_variable='TOY_ANONYMOUS')
        for s in packet.sites for t in range(96)]
    result=compile_unknown_policy(packet,packet.bindings,qos_provider=provider,nominal_service=old.nominal,
        q90_hourly=old.q90,timing_lower=old.cdf_lower,timing_upper=old.cdf_upper,
        source_authority=old.recourse_authority,conditions=conditions,envelope=envelope,
        migration_authority=migration_authority,service_reallocation=service_reallocation,
        evidence_kind='NAMED_SYNTHETIC_TWO_AIDC_TEMPLATE_NOT_MAY01')
    return provider,result


class NeverUnknown:
    bindings={'case_sha':'case'}
    sha='SPY_KNOWN_DISPATCH_ONLY'
    def select(self,*args,**kwargs):raise AssertionError('Known entered Unknown select')
    def select_migration(self,*args,**kwargs):raise AssertionError('Known entered Unknown migration')


@pytest.mark.parametrize('command,start,site,action',[
    ({'start_seconds':0,'site':'A'},0,'A','START'),
    ({'start_seconds':0,'site':'B'},0,'B','PREPLACE'),
    ({'start_seconds':900,'site':'A'},900,'A','DELAY')],ids=[
        'KNOWN_PLANNING_START_PRESERVED','KNOWN_PLANNING_PREPLACE_PRESERVED','KNOWN_PLANNING_DELAY_PRESERVED'])
def test_known_commands(command,start,site,action):
    result=run_actual({'A':8,'B':8},[request('K',origin_unknown=False,qos='normal',protected=False,can_prestart_place=True)],
        Environment({'K':900}),arm='B1',qos_window_provider=qos(),frozen_policy=NeverUnknown(),
        known_schedule={'K':command},begin=0,end=3600)
    row=result['queue_ledger'][0]
    assert (row['admitted_time'],row['site'],row['policy_action'])==(start,site,action)
    assert not result['rule_consumption_receipt']


def test_KNOWN_NEVER_ENTERS_UNKNOWN_POLICY():
    controller=JobEventController({'A':8,'B':8},arm='B3',qos_window_provider=qos(),frozen_policy=NeverUnknown())
    r=request('UNMODELED_KNOWN',origin_unknown=False)
    controller.submit(r,0);assert controller.admit(0)==['UNMODELED_KNOWN']
    controller.metadata[r.uid]['accumulated_compute_seconds']=1800
    assert controller.migration(r.uid,1800,1800) is None
    assert not controller.rule_ledger


def test_KNOWN_PLANNING_MIGRATION_PRESERVED():
    controller=JobEventController({'A':8,'B':8},arm='B3',qos_window_provider=qos(),frozen_policy=NeverUnknown(),
        wan_capacities={'AB':100},known_schedule={'K':dict(start_seconds=0,site='A',migration_destination='B',
            checkpoint_control_seconds=1800,physical_checkpoint_seconds=1800,
            planned_migration_times=dict(transfer_start=1800,transfer_end=2700,restart_end=3600))})
    controller.submit(request('K',origin_unknown=False,q50=5400,qos='normal',protected=False,
        migration_capability=capability()),0)
    assert controller.admit(0)==['K']
    controller.metadata['K']['accumulated_compute_seconds']=1800
    assert controller.migration('K',900,900) is None
    moved=controller.migration('K',1800,1800)
    assert moved['destination']=='B' and moved['policy_rule_id']=='KNOWN_FROZEN_EXECUTION_COMMAND'


def test_native_axis_and_WAN_command_conversion():
    option=dict(start=24,initial_site='A',checkpoint=26,physical_checkpoint_seconds=23400.,destination='B',
        transfer_start=26,transfer_end=27,restart_end=28,wan=[['L',26,90000]])
    c=compile_known_commands({'K':option},slot_zero_seconds=-21600)['K']
    assert c['start_seconds']==0 and c['checkpoint_control_seconds']==1800 and c['physical_checkpoint_seconds']==1800
    assert c['planned_wan']==option['wan']


def test_UNKNOWN_NOT_PRESENT_AT_PLANNING():
    with pytest.raises(ValueError,match='UNKNOWN_NOT_PRESENT_AT_PLANNING'):
        frozen(conditions=[dict(uid='FUTURE_UID')])


def test_UNKNOWN_CONDITIONAL_LOOKUP_ONLY_AFTER_OBSERVATION(monkeypatch):
    provider,p=frozen();job,receipt=participant(provider);m=metadata(provider,job,receipt)
    p.set_current_resources(0,{'A':0,'B':0})
    before=p.packet.evaluation_calls
    monkeypatch.setattr(p.packet,'evaluate',lambda *a,**k:(_ for _ in ()).throw(AssertionError('Online horizon score')))
    d=p.select(m,receipt,0,ReservationLedger({'A':8,'B':8}),reserve=False)
    assert d['action'] in ('START','PREPLACE','DELAY') and d['online_grid_horizon_evaluations']==0
    assert before==p.packet.evaluation_calls
    m['submit_seconds']=900
    assert p.select(m,receipt,0,ReservationLedger({'A':8,'B':8}),reserve=False)['action']=='QUEUE'
    previous=deepcopy(p.references)
    assert p.select(m,receipt,0,ReservationLedger({'A':8,'B':8}),reserve=True)['action']=='QUEUE'
    assert p.references==previous
    m['origin_unknown']=False
    with pytest.raises(ValueError,match='KNOWN_NEVER'):p.select(m,receipt,900,ReservationLedger({'A':8,'B':8}))


def test_UNKNOWN_POLICY_FREEZE_RELOAD_SHA(tmp_path):
    provider,p=frozen();path=tmp_path/'unknown.json';p.save(path)
    loaded=FrozenUnknownPolicy.load(path,bindings=p.bindings);loaded.bind_runtime_packet(p.packet)
    assert p.sha==loaded.sha and p.document==loaded.document
    body=json.loads(path.read_text());body['coverage'][0]['gpu']=999;path.write_text(json.dumps(body))
    with pytest.raises(ValueError,match='SHA_MISMATCH'):FrozenUnknownPolicy.load(path)


def test_UNKNOWN_QOS_BUDGET_PRESERVED():
    provider,p=frozen();job,receipt=participant(provider);m=metadata(provider,job,receipt)
    p.set_current_resources(0,{'A':0,'B':0});original=receipt.to_dict()
    m['cumulative_migration_interruption_seconds']=receipt.budget_seconds
    rows,_=p.candidates(m,receipt,0)
    assert all(r['additional_start_delay_seconds']==0 for r in rows)
    assert receipt.to_dict()==original


def test_UNKNOWN_Q90_QUEUE_CARRYOVER_CONSERVATION():
    _,p=frozen()
    mass=[r for t in p.expanded_document()['templates'] for a in t['ordered_actions'] for r in a['q90_mass_conservation']]
    assert mass and all(r['conservation_PASS'] for r in mass)


def test_PHYSICAL_GPU_RACK_WAN_GRID_GUARDS():
    provider,p=frozen();job,receipt=participant(provider);m=metadata(provider,job,receipt)
    p.set_current_resources(0,{'A':8,'B':8});ledger=ReservationLedger({'A':8,'B':8})
    ledger.retain_running('a','A',0,86400,8);ledger.retain_running('b','B',0,86400,8)
    assert p.select(m,receipt,0,ledger)['action']=='QUEUE'
    assert any(r['reason']=='NO_CAPACITY' for r in p.audit[-1]['rejected'])
    assert p.current_guard(dict(m,gpu=9),[dict(resource='gpu:A',begin=0,end=900,quantity=9)],0,{'A':0,'B':0})=='RACK_GANG_INCOMPATIBLE'
    wan=ReservationLedger({'A':8,'B':8},{'AB':100})
    assert wan.feasible([dict(resource='wan:AB',begin=0,end=900,quantity=101)])
    p.packet.voltage_lower=2.
    assert 'VOLTAGE' in p.current_guard(m,[dict(resource='gpu:A',begin=0,end=900,quantity=1)],0,{'A':0,'B':0})


def test_NO_FUTURE_LEAKAGE_NO_DUPLICATE_CC4_DEPLETION_KNOWN_UNKNOWN_DISJOINT_ACTION_LEDGER():
    from v42_final.workload import ForecastBook
    provider,p=frozen();job,receipt=participant(provider)
    unknown=request(job.uid,qos='UNCONFIRMED',protected=None,batch_eligible=None,partition='',requested_walltime_seconds=None,
        representation_starts_seconds=tuple(range(0,86400,900)))
    known=request('K',origin_unknown=False,qos='high',protected=True,batch_eligible=False)
    result=run_experimental_actual({'A':8,'B':8},[unknown,known],Environment({job.uid:900,'K':900}),
        arm='B1',qos_window_provider=provider,frozen_policy=p,known_schedule={'K':dict(start_seconds=0,site='A')},
        begin=0,end=1800,forecast=ForecastBook(tuple([1.]*24),tuple([2.]*24),0))
    assert all(r['uid']==job.uid for r in result['rule_consumption_receipt'])
    assert len(result['cc4_depletion_ledger'])==1
    assert result['receipt']['future_duration_controller_reads']==0 and result['receipt']['future_completion_controller_reads']==0
    assert result['receipt']['capacity_violations']==0
    from v42_integration.action_metrics import unknown_actual_metrics
    metrics=unknown_actual_metrics(result)
    assert metrics['Unknown_Observed_UID']==1 and metrics['Unknown_Feasible_Frozen_Alternative_UID']==1
    assert metrics['Unknown_First_Alternative_Executed_UID']+metrics['Unknown_Later_Alternative_Executed_UID']==1
    assert metrics['QoS_intentional_budget_excess_UID']==0 and metrics['Actual_AIDC_IT_PCC_PQ'] is None


def test_experimental_online_selector_requires_explicit_legacy_diagnostic():
    provider=research_provider();p=policy(provider)
    with pytest.raises(ValueError,match='FROZEN_LOOKUP_ONLY'):
        ExperimentalJobEventController({'A':8,'B':8},arm='B3',qos_window_provider=provider,frozen_policy=p)


def test_candidate_coverage_has_all_feasible_gangs_sites_times_and_E2_delay():
    provider,p=frozen();grammar=coverage_grammar(p.packet,runtime_bounds=(900.,))
    assert {r['gpu'] for r in grammar}==set(range(1,9))
    assert all(set(r['compatible_sites'])=={'A','B'} and r['time_slots']==list(range(96)) for r in grammar)
    from v42_integration.experimental_qos import ExperimentalQoSProvider
    provider=ExperimentalQoSProvider(qos(),scenario='E2',participation='FLEX40',case_sha='FIXTURE_CASE',provider_sha='provider')
    assert provider.spec['scenario']=='E2'


def test_research_issue_QoS_reaches_new_Known_domain_without_Optimize(tmp_path):
    from v42_integration.fixture_validation import build_fixture
    from v42_integration.experimental_planning import bind_experimental_planning
    from v42_integration.a_engine import authorized_data
    from v42_integration.qos import QoSWindowProvider,ObservedJob
    case=build_fixture(tmp_path/'input')
    records={}
    strict=QoSWindowProvider(case.qos_provider.stats,case_sha=case.case_sha,provider_sha=case.qos_provider.provider_sha)
    requests=[]
    for r in case.actual_arguments['requests']:
        if r.metadata['origin_unknown']:
            requests.append(r);continue
        r=replace(r,submit=-21600)
        j=ObservedJob(r.uid,-21600,-21600,0,r.q50,gpu=r.gpu,origin_unknown=False,
            representation_starts_seconds=tuple(range(0,14401,900)),batch_eligible=True,
            provider_sha=strict.provider_sha,reference_sha='fixture-shadow')
        strict.issue(j);records[r.uid]=j;requests.append(r)
    case.actual_arguments['requests']=requests;case.qos_provider=strict
    parent=case.case_sha
    public_actual_arguments=case.actual_arguments
    class FutureBankTrap:
        def __iter__(self):raise AssertionError('Future request bank enumerated at Planning')
        def __getitem__(self,key):raise AssertionError('Future request bank read at Planning')
        def get(self,*args):raise AssertionError('Future request bank read at Planning')
    case.actual_arguments=FutureBankTrap()
    bind_experimental_planning(case,records,scenario='E1',participation='FLEX40')
    assert case.actual_arguments.__class__ is FutureBankTrap
    assert set(case.qos_provider.receipts)==set(records)
    case.actual_arguments=public_actual_arguments
    assert case.case_sha!=parent and case.science_sha!='FIXTURE_SCIENCE'
    a=case.make_a_case('B1','A1',case.initial_mess,tmp_path/'A1')
    data,domains=authorized_data(a)
    for uid,job in data[1].items():
        rec=case.qos_provider.receipts[uid]
        assert job.qos_budget_seconds==rec.budget_seconds and job.qos_receipt_sha
        assert job.qos_allowed_starts==a.window_slots[uid]
        assert not job.unknown_arrival and uid in domains
    assert set(data[1])==set(records)
    assert case.research_contract_binding['Native_Optimize_calls']==0
    issued_before={u:r.to_dict() for u,r in case.qos_provider.receipts.items()}
    projected,receipt=case.prepare_research_actual_arguments()
    assert projected['environment'] is public_actual_arguments['environment']
    assert [r.uid for r in projected['requests']]==[r.uid for r in requests]
    assert {u:r.to_dict() for u,r in case.qos_provider.receipts.items()}==issued_before
    assert receipt['Known_issue_record_count']==len(records)


@pytest.mark.parametrize('arm',['B1','B3'])
def test_final_A_stage_known_handoff_transport_only(tmp_path,monkeypatch,arm):
    from v42_integration.coordinator import run_arm
    from v42_integration.fixture_validation import build_fixture
    from test_v42_integration_policy_wiring import install_transport,NoSolver
    case=build_fixture(tmp_path/'input');install_transport(monkeypatch,case)
    observed={}
    def factory(**kwargs):
        observed.update(kwargs)
        from v42_integration.policy import compile_policy
        return compile_policy(kwargs['envelope'],kwargs['bindings'],case.signed_grid_coefficients)
    case.control_policy_factory=factory
    def future_actual_not_due():raise AssertionError('Actual projection before policy freeze or during Planning-only')
    case.prepare_research_actual_arguments=future_actual_not_due
    result=run_arm(arm,case,NoSolver(),tmp_path/'out',planning_only=True)
    assert observed['aidc']['stage']==('A1' if arm=='B1' else 'A2')
    assert result['freeze']['Known_schedule']==observed['aidc']['selected_jobs']
    assert observed['bindings']['aidc_anchor']==observed['aidc']['aidc_anchor']
    assert observed['bindings']['mess_anchor']==observed['mess']['plan_sha']
    if arm=='B1':assert all(v==0 for k in ('P_by_site','Q_by_site') for row in observed['mess'][k].values() for v in row)


def test_unknown_frozen_checkpoint_all_links_and_pinned_destination_guard():
    authority=dict(packet_source_sha='NAMED_TOY_PHYSICAL_MIGRATION',
        scalar=dict(bytes_per_GPU=90000,current_conservative_restart_seconds=900),
        protocol=dict(source_hold_until='transfer_start',destination_hold_from='transfer_end'),
        routes={'AB':dict(source='A',destination='B',bandwidth_bytes_per_second=100,links=['L'])},
        wan_capacities={'AB':100,'LINK::L':100})
    condition=dict(state='RUNNING',qos='normal',gpu=1,reference_site='A',compatible_sites=['A','B'],
        runtime_lower_seconds=900.,runtime_upper_seconds=3600.,time_slots=[2])
    provider,p=frozen(profile='migration_witness',migration_authority=authority,conditions=[condition])
    job=replace(observed('SYNTHETIC_UID_2',q50=5400),origin_unknown=True,state='RUNNING')
    receipt=provider.issue(job);assert receipt.participant
    m=metadata(provider,job,receipt);m.update(state='RUNNING',current_site='A',accumulated_compute_seconds=1800,
        Can_Checkpoint_Migrate=True)
    ledger=ReservationLedger({'A':8,'B':8},authority['wan_capacities']);ledger.retain_running(job.uid,'A',0,9000,1)
    p.set_current_resources(1800,{'A':1,'B':0})
    before=p.packet.evaluation_calls
    result=p.select_migration(m,receipt,1800,ledger,checkpoint_at=1800,reserve=False)
    assert result['action']=='CHECKPOINT_MIGRATE'
    assert any(r['resource']=='wan:LINK::L' for r in result['migration']['segments'])
    assert p.packet.evaluation_calls==before
    m['compatible_sites']=['A']
    assert p.select_migration(m,receipt,1800,ledger,checkpoint_at=1800,reserve=False)['action']=='STAY'


def test_known_off_grid_physical_checkpoint_preserves_control_roundup():
    controller=JobEventController({'A':8,'B':8},arm='B3',qos_window_provider=qos(),frozen_policy=NeverUnknown(),
        wan_capacities={'AB':100},known_schedule={'K':dict(start_seconds=0,site='A',migration_destination='B',
            checkpoint_control_seconds=2700,physical_checkpoint_seconds=2100,
            planned_migration_times=dict(transfer_start=2700,transfer_end=3600,restart_end=4500))})
    controller.submit(request('K',origin_unknown=False,q50=5400,qos='normal',protected=False,
        migration_capability=capability()),0);controller.admit(0)
    controller.metadata['K']['accumulated_compute_seconds']=1800
    result=controller.migration('K',2100,2100)
    assert result and result['control_checkpoint_seconds']==2700
    assert result['interruption_seconds']==2400 and not controller.rule_ledger


def test_E2_all_15min_options_and_verified_standby_maximum():
    conditions=[dict(state='PENDING',qos=tier,gpu=1,reference_site='A',compatible_sites=['A','B'],
        runtime_lower_seconds=0.,runtime_upper_seconds=900.,time_slots=[0]) for tier in ('normal','standby')]
    _,p=frozen(conditions=conditions,scenario='E2')
    for t in p.expanded_document()['templates']:
        assert {(r['site'],r['delay_seconds']) for r in t['scenario_comparisons']}=={
            (s,d) for s in ('A','B') for d in range(0,(3600 if t['qos']=='normal' else 7200)+1,900)}


def test_missed_pre_day_Known_start_is_failure_queue_without_reference_rewrite():
    controller=JobEventController({'A':8,'B':8},arm='B1',qos_window_provider=qos(),frozen_policy=NeverUnknown(),
        known_schedule={'K':dict(start_seconds=-900,site='B')})
    controller.submit(request('K',origin_unknown=False,dday_initialization_seconds=0,can_prestart_place=True),0)
    assert controller.admit(0)==[] and controller.decisions['K']['action']=='QUEUE'
    assert controller.events[-1]['event']=='KNOWN_COMMAND_EXECUTION_FAILED'
    assert controller.known_schedule['K']['site']=='B' and not controller.rule_ledger


def test_unknown_invalid_or_future_checkpoint_does_not_consume_first_valid_attempt():
    provider,p=frozen();job,receipt=participant(provider)
    m=metadata(provider,job,receipt)
    m.update(state='RUNNING',current_site='A',Can_Checkpoint_Migrate=True,
        t50_seconds=2700,accumulated_compute_seconds=1801)
    ledger=ReservationLedger({'A':8,'B':8})
    assert p.select_migration(m,receipt,1800,ledger)['reason']=='NOT_EXECUTION_ANCHORED_CHECKPOINT'
    assert 'frozen_first_checkpoint_attempt_seconds' not in m
    m['accumulated_compute_seconds']=1800
    assert p.select_migration(m,receipt,1800,ledger,checkpoint_at=2700)['reason']=='CHECKPOINT_NOT_OBSERVED'
    assert 'frozen_first_checkpoint_attempt_seconds' not in m
    m['is_observed']=False
    assert p.select_migration(m,receipt,1800,ledger)['reason']=='NO_OBSERVED_RUNNING_AUTHORITY'
    assert 'frozen_first_checkpoint_attempt_seconds' not in m
    m['is_observed']=True
    p.select_migration(m,receipt,1800,ledger,checkpoint_at=1800)
    assert m['frozen_first_checkpoint_attempt_seconds']==1800


def test_migration_destination_acquisition_rechecks_observed_overrun_before_execution():
    authority=dict(packet_source_sha='NAMED_TOY_PHYSICAL_MIGRATION',
        scalar=dict(bytes_per_GPU=90000,current_conservative_restart_seconds=900),
        protocol=dict(source_hold_until='transfer_start',destination_hold_from='transfer_end'),
        routes={'AB':dict(source='A',destination='B',bandwidth_bytes_per_second=100,links=['L'])},
        wan_capacities={'AB':100,'LINK::L':100})
    condition=dict(state='RUNNING',qos='normal',gpu=1,reference_site='A',compatible_sites=['A','B'],
        runtime_lower_seconds=900.,runtime_upper_seconds=3600.,time_slots=[2])
    provider,p=frozen(profile='migration_witness',migration_authority=authority,conditions=[condition])
    mover=request('SYNTHETIC_UID_2',submit=0,q50=5400,origin_unknown=True,
        qos='UNCONFIRMED',protected=None,batch_eligible=None,partition='',requested_walltime_seconds=None,
        elapsed_compute_seconds=0,representation_starts_seconds=tuple(range(0,86400,900)))
    background=request('BG',submit=-1000,gpu=8,q50=900,origin_unknown=False,
        source_site='B',compatible=('B',),qos='high',protected=True,batch_eligible=False,
        elapsed_compute_seconds=1000,representation_starts_seconds=tuple(range(0,86400,900)))
    before=p.packet.evaluation_calls
    with pytest.raises(ValueError,match='MIGRATION_PHASE_CURRENT_GUARD_FAILED:.*:transfer_end:GPU_CAPACITY'):
        run_experimental_actual({'A':8,'B':8},[],Environment({mover.uid:9000,'BG':9000},{mover.uid:9000,'BG':9000}),
            arm='B3',qos_window_provider=provider,frozen_policy=p,
            running=[(mover,'A',0),(background,'B',-1000)],begin=0,end=3600)
    assert p.packet.evaluation_calls==before
