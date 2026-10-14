"""Declared synthetic source-equation/Actual tests, never May AC evidence."""
from copy import deepcopy
import numpy as np
import pytest

from v42_capacity.actual import Environment
from v42_integration.actual import FrozenPowerModel,run_actual,JobRequest
from v42_integration.experimental_actual import (run_experimental_actual,prepare_conditional_arguments,
    ExperimentalJobEventController)
from v42_integration.experimental_policy import ExperimentalControlPolicy
from v42_integration.experimental_qos import ExperimentalQoSProvider
from v42_integration.policy import ReservationLedger
from v42_integration.qos import ObservedJob
from test_v42_integration_actual import qos,request
from test_v42_integration_sensitivity_policy import fixture


def research_provider(scenario='E1'):
    return ExperimentalQoSProvider(qos(),scenario=scenario,participation='FLEX40',
        case_sha='FIXTURE_CASE',provider_sha='provider')


def observed(uid,*,q50=900,reference=0,event=0):
    return ObservedJob(uid,0,event,reference,q50,qos='UNCONFIRMED',protected=None,
        batch_eligible=None,partition='',requested_walltime_seconds=None,
        representation_starts_seconds=tuple(range(0,86400,900)),provider_sha='provider',reference_sha='CAUSAL_REFERENCE_START')


def participant(provider):
    # Synthetic UID grammar frozen independently of grid outcome; not May.
    for i in range(100):
        job=observed('SYNTHETIC_UID_'+str(i));receipt=provider.issue(job)
        if receipt.participant:return job,receipt
    raise AssertionError('DETERMINISTIC_FIXTURE_MEMBER_NOT_FOUND')


def policy(provider,*,algorithm='GRID_SENSITIVITY_AWARE',q90=0,profile='placement',migration_authority=None,packet_values=None):
    from v42_integration.q90_recourse import load_nominal_service
    values=packet_values or fixture(profile='placement' if profile=='migration_witness' else profile)
    packet=values[0]
    if profile=='migration_witness':
        # Named independent toy source: a future CP-slot peak makes a genuine
        # ranked migration distinguishable from a less-disruption STAY tie.
        for t in range(1,96):
            change=(.8 if t==2 else .1)-.2
            packet.coefficients[t].current_constant[0]+=change
            packet.bias[t][0]+=change
    lower=np.zeros(100);upper=np.ones(100)
    authority=dict(model_id='LGBM_weighted_c1_s20260924',prediction_sha=values[6]['cc4_sha'],
        kernel_sha='NAMED_SYNTHETIC_TRAIN_KERNEL',timing_envelope_sha='NAMED_SYNTHETIC_TRAIN_CDF')
    q50=np.full(24,2.)
    a2=dict(resource_sites=['A','B'],aidc_anchor=values[6]['aidc_anchor'],
        known_site_GPU={'A':[0.]*96,'B':[0.]*96},nominal_site_GPU={'A':[1.]*96,'B':[1.]*96},
        CC4_service={str((h,t)):.5 for h in range(24) for t in range(h*4,h*4+4)},
        CC4_carryout={str(h):0. for h in range(24)})
    nominal=load_nominal_service(a2,q50,lower,upper,source_authority=authority)
    return ExperimentalControlPolicy(packet,values[6],qos_provider=provider,
        q50_hourly=q50,q90_hourly=q50+q90,kernel=[1.],queue_authority=authority,
        frozen_anonymous_gpu=np.ones((96,2)),algorithm=algorithm,migration_authority=migration_authority,
        nominal_service=nominal,train_cdf_lower=lower,train_cdf_upper=upper,recourse_source_authority=authority)


def context(p,job,*,background=True):
    p.set_observed_context(now=0,observed_gpu={'A':0,'B':1 if background else 0},
        pending_nominal_work={job.uid:job.t50_seconds/3600},remaining_q50=[0.]*24,
        remaining_q90=p.q90.tolist(),forecast_depletion=dict(source='SYNTHETIC_OBSERVED_NONE'))


def metadata(provider,job,receipt,*,sites=('A','B')):
    from dataclasses import asdict
    return dict(asdict(job),**provider.metadata_overlay(job,receipt),state='PENDING',
        compatible_sites=list(sites),source_site='A',reference_site='A',nominal_service_seconds=job.t50_seconds,
        additional_start_delay_seconds=0,cumulative_migration_interruption_seconds=0)


def test_q90_backlog_is_risk_and_does_not_blanket_veto_nominal_feasible_preplacement():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider,q90=100)
    context(p,job);ledger=ReservationLedger({'A':8,'B':8})
    ledger.retain_running('sourcebackground','B',0,86400,1)
    result=p.select(metadata(provider,job,receipt),receipt,0,ledger)
    assert result['action']=='PREPLACE' and result['site']=='B'
    assert result['q50_hard_feasible'] and result['q90_risk']['carryout_GPUh']>0
    assert result['q90_mass_conservation']['conservation_PASS']
    assert not result['grid_safety_guaranteed']


def test_whole_gang_physical_reservations_override_favorable_grid_score():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    context(p,job);ledger=ReservationLedger({'A':8,'B':8})
    ledger.retain_running('fullA','A',0,86400,8);ledger.retain_running('fullB','B',0,86400,8)
    result=p.select(metadata(provider,job,receipt),receipt,0,ledger)
    assert result['action']=='QUEUE' and result['reason']=='NO_CAPACITY'
    assert len(ledger.reservations)==2
    assert p.last_selection[job.uid]['physical_or_Q50_veto']
    assert p.audit[-1]['terminal_status']=='NO_PHYSICAL_CAUSAL_REFERENCE'


def test_zero_current_delay_preplacement_and_past_issue_reference_do_not_renew_budget():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    context(p,job);ledger=ReservationLedger({'A':8,'B':8});ledger.retain_running('bg','B',0,86400,1)
    m=metadata(provider,job,receipt);m['Can_TimeShift']=False
    result=p.select(m,receipt,0,ledger,reserve=False)
    assert result['action']=='PREPLACE' and result['additional_start_delay_seconds']==0
    assert provider.receipts[job.uid] is receipt


def test_original_signed_grid_hard_rows_reject_unsafe_voltage_even_when_peak_improves():
    provider=research_provider();job,receipt=participant(provider)
    values=fixture(profile='placement',voltage_slope=.3)
    p=policy(provider,packet_values=values)
    context(p,job);ledger=ReservationLedger({'A':8,'B':8});ledger.retain_running('bg','B',0,86400,1)
    result=p.select(metadata(provider,job,receipt),receipt,0,ledger,reserve=False)
    assert result['action']!='PREPLACE'
    assert any(not r['hard'] for r in p.audit[-1]['q50_scores'])


@pytest.mark.parametrize('algorithm',['FIXED','GREEDY','GRID_SENSITIVITY_AWARE'])
def test_ablations_share_same_physical_and_q50_hard_guards(algorithm):
    provider=research_provider();job,receipt=participant(provider);p=policy(provider,algorithm=algorithm)
    context(p,job);ledger=ReservationLedger({'A':8,'B':8});ledger.retain_running('bg','B',0,86400,1)
    result=p.select(metadata(provider,job,receipt),receipt,0,ledger,reserve=False)
    assert result['q50_hard_feasible'] and result['online_global_optimizer_calls']==0


def test_source_protected_flag_preserved_without_forcing_flexible_action():
    provider=research_provider();job=observed('PROTECTED')
    from dataclasses import replace
    job=replace(job,protected=True);receipt=provider.issue(job);overlay=provider.metadata_overlay(job,receipt)
    assert overlay['protected'] is True and not overlay['Can_Preplace']
    assert receipt.budget_seconds==0


def test_common_actual_adapter_executes_new_policy_with_power_compute_and_cc4_causality():
    provider=research_provider();job,receipt=participant(provider)
    # Use the same public metadata as the issued fixture receipt and register
    # reference identity; an actual request issues an independent fresh copy.
    provider=research_provider();p=policy(provider)
    pending=request(job.uid,q50=900,qos='UNCONFIRMED',protected=None,batch_eligible=None,
        partition='',requested_walltime_seconds=None,representation_starts_seconds=tuple(range(0,86400,900)))
    bg=request('BG',submit=-1000,q50=900,source_site='B',compatible=('B',),origin_unknown=False,
        qos='high',protected=True,batch_eligible=False,elapsed_compute_seconds=1000,
        representation_starts_seconds=tuple(range(0,86400,900)))
    power=FrozenPowerModel(0.,1.,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'SYNTHETIC_LINEAR_C1_ONLY')
    from v42_final.workload import ForecastBook
    result=run_experimental_actual({'A':8,'B':8},[pending],Environment({job.uid:900,'BG':10000},{'BG':9000}),
        arm='B3',qos_window_provider=provider,frozen_policy=p,running=[(bg,'B',-1000)],
        begin=0,end=4500,power_model=power,weather=[{}]*5,
        forecast=ForecastBook(tuple([0.]*24),tuple([0.]*24),0))
    row=next(r for r in result['queue_ledger'] if r['job_uid']==job.uid)
    assert row['admitted_time']==0 and row['policy_action']=='PREPLACE' and row['site']=='B'
    assert len(result['cc4_depletion_ledger'])==1 and result['cc4_depletion_ledger'][0]['depletion_count']==1
    assert result['receipt']['future_duration_controller_reads']==0 and result['receipt']['capacity_violations']==0
    assert result['physical']['IT_recomputed_from_actual_occupation']
    np.testing.assert_array_equal(result['physical']['PCC_P_kw'],result['occupancy_GPU'])
    assert result['experimental_scope']['Actual_Maximum_Line_Loading'] is None


def test_program_reload_requires_same_literal_source_and_defends_public_copy(tmp_path):
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    path=tmp_path/'program.json';p.save(path)
    loaded=ExperimentalControlPolicy.load(path,packet=p.packet,qos_provider=provider,bindings=p.bindings)
    copied=loaded.document;copied['frozen_Q90'][0]=999
    assert loaded.sha==p.sha and loaded.document['frozen_Q90'][0]==2
    for selector in (p,loaded):context(selector,job)
    def ledger():
        result=ReservationLedger({'A':8,'B':8});result.retain_running('bg','B',0,86400,1);return result
    first=p.select(metadata(provider,job,receipt),receipt,0,ledger(),reserve=False)
    second=loaded.select(metadata(provider,job,receipt),receipt,0,ledger(),reserve=False)
    # The packet's exact-response memoization changes work counts, never choice.
    first.pop('online_grid_horizon_evaluations');second.pop('online_grid_horizon_evaluations')
    assert first==second
    with pytest.raises(ValueError,match='BINDING_MISMATCH'):
        ExperimentalControlPolicy.load(path,packet=p.packet,qos_provider=provider,
            bindings=dict(p.bindings,mess_anchor='CHANGED'))


def test_serial_base_profile_cache_equals_full_reservation_reconstruction():
    from v42_integration.experimental_policy import segments_gpu
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    context(p,job);ledger=ReservationLedger({'A':8,'B':8});ledger.retain_running('bg','B',0,86400,1)
    segments=[dict(resource='gpu:A',begin=100,end=1900,quantity=1)]
    base=segments_gpu(ledger.reservations['bg']['segments'],p.packet.sites,0)
    uncached=p._score(metadata(provider,job,receipt),segments,0,ledger)
    cached=p._score(metadata(provider,job,receipt),segments,0,ledger,base_gpu=base)
    assert cached==uncached
    np.testing.assert_allclose(segments_gpu(segments,('A','B'),0)[:,0][:3],[800/900,1.,100/900])


def test_public_known_issue_projection_reuses_new_receipt_preserves_old_proof_and_environment():
    from dataclasses import asdict,replace
    from v42_integration.qos import CausalReferenceScheduler
    strict=qos();original=replace(observed('KNOWN',reference=0),origin_unknown=False,
        reference_sha='ORIGINAL_ISSUE_REFERENCE',nominal_service_seconds=1800)
    old_receipt=strict.issue(original)
    old_proof=dict(uid='KNOWN',case_sha=strict.case_sha,provider_sha=strict.provider_sha,
        stats_sha=strict.stats.sha,reference_sha=old_receipt.reference_sha,
        authority_sha=old_receipt.authority_sha,gpu=1)
    raw=dict(asdict(original),common_initial_state_sha='PUBLIC_MODEL_INITIAL_STATE',
        reused_planning_qos_authority=old_proof)
    r=JobRequest('KNOWN',0,1,('A','B'),900,'A',raw)
    environment=Environment({'KNOWN':900})
    args=dict(capacities={'A':8,'B':8},requests=[r],environment=environment,
        qos_window_provider=strict,begin=0,end=1800,
        reference=CausalReferenceScheduler({'A':8,'B':8},reference_sha='DDAY_REFERENCE'))
    projected=prepare_conditional_arguments(args,{'KNOWN':original},scenario='E1',
        participation='FLEX40',case_sha='FIXTURE_CASE')
    clone=projected['arguments']['requests'][0]
    assert projected['arguments']['environment'] is environment
    assert clone.metadata['original_source_planning_authority']==old_proof
    assert r.metadata==raw or r.metadata['reused_planning_qos_authority']==old_proof
    assert clone.metadata['nominal_service_seconds']==1800
    assert clone.metadata['experimental_prediction_Q50_seconds']==900
    new=projected['new_qos_provider'];p=policy(new)
    result=run_experimental_actual(**projected['arguments'],arm='B3',frozen_policy=p)
    assert result['receipt']['future_duration_controller_reads']==0
    assert new.receipts['KNOWN'].issued_at_seconds==original.event_seconds
    assert new.receipts['KNOWN'].authority_sha==old_receipt.authority_sha
    assert strict.receipts['KNOWN'] is old_receipt


def test_selected_delay_persists_across_control_retry_without_renewing_B():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    context(p,job,background=False)
    m=metadata(provider,job,receipt,sites=('A',));m['Can_Preplace']=False
    ledger=ReservationLedger({'A':8,'B':8})
    selected=p.select(m,receipt,0,ledger,reserve=False)
    assert selected['action']=='DELAY' and selected['additional_start_delay_seconds']<=receipt.budget_seconds
    m['additional_start_delay_seconds']=receipt.budget_seconds
    p.set_observed_context(now=900,observed_gpu={'A':0,'B':0},pending_nominal_work={job.uid:.25},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    retry=p.select(m,receipt,900,ledger,reserve=False)
    assert retry['additional_start_delay_seconds']==receipt.budget_seconds
    assert retry['execution_window_receipt']['remaining_budget_seconds']==0
    assert provider.receipts[job.uid] is receipt


def test_initial_running_migration_uses_same_physical_service_budget_and_no_double_compute():
    from dataclasses import asdict,replace
    from test_v42_integration_actual import capability
    from v42_final.workload import ForecastBook
    provider=research_provider();job,_=participant(provider)
    # Public identity/member chosen before phase outcomes; named source packet
    # uses 900s WAN transfer+900s restart, no zero physical assumptions.
    provider=research_provider();job=replace(job,t50_seconds=5400,state='RUNNING',origin_unknown=True)
    cap=capability()
    raw=dict(asdict(job),elapsed_compute_seconds=0,migration_capability=cap)
    r=JobRequest(job.uid,0,1,('A','B'),5400,'A',raw);p=policy(provider,profile='migration_witness')
    power=FrozenPowerModel(0.,1.,{'A':8,'B':8},.95,lambda it,w:np.asarray(it),'SYNTHETIC_LINEAR_C1_ONLY')
    result=run_experimental_actual({'A':8,'B':8},[],Environment({job.uid:5400},{job.uid:5400}),
        qos_window_provider=provider,frozen_policy=p,arm='B3',running=[(r,'A',0)],
        begin=0,end=8100,wan_capacities={'AB':100},power_model=power,weather=[{}]*9,
        forecast=ForecastBook(tuple([0.]*24),tuple([0.]*24),0))
    assert len(result['migration_receipts'])==1
    migration=result['migration_receipts'][0]
    assert migration['interruption_seconds']==1800
    budget=result['qos_ledger'][0]
    assert budget['total_intentional_burden_seconds']==1800<=budget['budget_seconds']
    assert sum(result['compute_occupancy_GPU'].sum(axis=1))*900==5400
    assert result['receipt']['capacity_violations']==0
    assert len(result['cc4_depletion_ledger'])==1
    np.testing.assert_array_equal(result['physical']['PCC_P_kw'],result['occupancy_GPU'])


def test_E0_uses_unchanged_default_actual_controller():
    r=request('STRICT')
    reference=run_actual({'A':8,'B':8},[r],Environment({'STRICT':900}),
        qos_window_provider=qos(),arm='B0',end=1800)
    provider=ExperimentalQoSProvider(qos(),scenario='E0',participation='FLEX20')
    result=run_experimental_actual({'A':8,'B':8},[r],Environment({'STRICT':900}),
        qos_window_provider=provider,frozen_policy=None,arm='B0',end=1800)
    assert reference['receipt']==result['receipt']
    assert reference['queue_ledger']==result['queue_ledger']
    np.testing.assert_array_equal(reference['occupancy_GPU'],result['occupancy_GPU'])


def test_due_delayed_command_rechecks_new_observed_hard_rows_and_keeps_spent_budget():
    from dataclasses import asdict,replace
    provider=research_provider();job,_=participant(provider)
    provider=research_provider();job=replace(job,origin_unknown=True)
    values=fixture(profile='placement',voltage_slope=.3)
    p=policy(provider,packet_values=values)
    controller=ExperimentalJobEventController({'A':8,'B':8},arm='B3',qos_window_provider=provider,frozen_policy=p)
    initial_bg=JobRequest('INITIAL_BACKGROUND',0,1,('B',),86400,'B',dict(
        origin_unknown=True,representation_starts_seconds=tuple(range(0,86400,900)),
        qos='high',protected=True,batch_eligible=False))
    controller.submit(initial_bg,0);controller.pending.remove((0,initial_bg.uid))
    controller.ledger.start(initial_bg.uid,'B',0,'PUBLIC_INITIAL_BACKGROUND_EPISODE')
    controller.metadata[initial_bg.uid].update(state='RUNNING',current_site='B')
    controller.reservations.retain_running(initial_bg.uid,'B',0,86400,1)
    r=JobRequest(job.uid,0,1,('A',),900,'A',asdict(job));controller.submit(r,0)
    assert controller.admit(0)==[]
    original=controller.budgets[job.uid]
    assert controller.decisions[job.uid]['action']=='DELAY'
    assert controller.decisions[job.uid]['start_seconds']==900
    # A new observed background phase lies outside the old Q50 voltage state.
    bg=JobRequest('OBSERVED_BACKGROUND',600,7,('B',),86400,'B',dict(
        origin_unknown=True,representation_starts_seconds=tuple(range(0,86400,900)),
        qos='high',protected=True,batch_eligible=False))
    controller.submit(bg,900);controller.pending.remove((600,bg.uid))
    controller.ledger.start(bg.uid,'B',900,'PUBLIC_BACKGROUND_EPISODE')
    controller.metadata[bg.uid].update(state='RUNNING',current_site='B')
    controller.reservations.retain_running(bg.uid,'B',900,86400,7)
    assert controller.admit(900)==[]
    assert controller.metadata[job.uid]['additional_start_delay_seconds']==900
    assert controller.budgets[job.uid] is original
    assert controller.metadata[job.uid]['cumulative_migration_interruption_seconds']==0
    failures=[e for e in controller.events if e['event']=='EXPERIMENTAL_COMMAND_REVALIDATED']
    assert failures[-1]['passed'] is False
    assert controller.ledger.jobs[job.uid]['latest_observed_state']=='PENDING'


def test_nominal_initial_booking_overrun_retains_running_and_cancels_conflicting_future_start():
    from v42_integration.actual import JobEventController
    provider=research_provider();p=policy(provider)
    controller=ExperimentalJobEventController({'A':8,'B':8},arm='B3',qos_window_provider=provider,frozen_policy=p)
    running=JobRequest('INITIAL_RUNNING',-1800,8,('A',),900,'A',dict(origin_unknown=False,
        representation_starts_seconds=tuple(range(0,86400,900)),elapsed_compute_seconds=1800,
        qos='high',protected=True,batch_eligible=False))
    controller.submit(running,0);controller.pending.remove((-1800,running.uid))
    controller.ledger.start(running.uid,'A',0,'SOURCE_PUBLIC_RUNNING_EPISODE')
    controller.metadata[running.uid].update(state='RUNNING',current_site='A',accumulated_compute_seconds=1800)
    controller.reservations.retain_running(running.uid,'A',0,86400,8)
    assert controller.reservations.reservations[running.uid]['segments'][0]['end']==900
    pending=request('PENDING_CONFLICT',q50=900,compatible=('A',));controller.submit(pending,0)
    controller.decisions[pending.uid]=dict(uid=pending.uid,action='START',site='A',start_seconds=900,
        additional_start_delay_seconds=0)
    assert controller.reservations.reserve(pending.uid,[dict(resource='gpu:A',begin=900,end=1800,quantity=1)])[0]
    frozen=controller.budgets[pending.uid]
    # Only a current RUNNING observation extends the hold; no true end is read.
    controller.reservations.retain_running(running.uid,'A',900,1800,8)
    assert controller.admit(900)==[]
    assert controller.ledger.physical(900)['A']==8
    assert controller.ledger.jobs[running.uid]['latest_observed_state']=='RUNNING'
    assert controller.metadata[pending.uid]['additional_start_delay_seconds']==0
    assert controller.budgets[pending.uid] is frozen
    recheck=[e for e in controller.events if e['event']=='EXPERIMENTAL_COMMAND_REVALIDATED'][-1]
    assert recheck['reason']=='NO_CAPACITY'
    strict=JobEventController({'A':8,'B':8},arm='B0',qos_window_provider=qos())
    strict.reservations.retain_running('STRICT','A',0,86400,8)
    assert strict.reservations.reservations['STRICT']['segments'][0]['end']==86400


def test_original_source_zero_delay_preplace_is_independent_of_research_nonparticipation():
    from dataclasses import asdict
    provider=research_provider()
    for i in range(100):
        job=observed('SOURCE_RIGHT_NONPARTICIPANT_'+str(i))
        if not provider.issue(job).participant:break
    provider=research_provider();p=policy(provider)
    controller=ExperimentalJobEventController({'A':8,'B':8},arm='B3',qos_window_provider=provider,frozen_policy=p)
    r=JobRequest(job.uid,0,1,('A','B'),900,'A',dict(asdict(job),can_prestart_place=True))
    controller.submit(r,0)
    metadata=controller.metadata[job.uid]
    assert metadata['Can_Preplace'] and not metadata['Can_TimeShift']
    assert metadata['preplace_authority_classes']==['ORIGINAL_MODEL_INITIALIZER_APPROVED']
    assert not controller.budgets[job.uid].participant and controller.budgets[job.uid].budget_seconds==0
    assert metadata['source_observed_qos_metadata']['qos']=='UNCONFIRMED'


def test_exact_score_cache_copy_and_public_context_invalidation():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    context(p,job);ledger=ReservationLedger({'A':8,'B':8});ledger.retain_running('bg','B',0,86400,1)
    segments=[dict(resource='gpu:A',begin=0,end=900,quantity=1)]
    m=metadata(provider,job,receipt)
    first,_=p._score(m,segments,0,ledger)
    copied,_=p._score(m,segments,0,ledger)
    assert copied==first and p.queue_cache_hits==1
    copied['q50_peak_score']=999
    again,_=p._score(m,segments,0,ledger)
    assert again==first and p.queue_cache_hits==2
    p.set_observed_context(now=0,observed_gpu={'A':0,'B':1},
        pending_nominal_work={job.uid:.25,'OTHER_OBSERVED':.2},remaining_q50=[0.]*24,
        remaining_q90=[0.]*24,forecast_depletion={})
    p._score(m,segments,0,ledger)
    assert p.queue_cache_misses==1  # Unrelated Pending cannot reschedule literal A2 Q50.
    assert p.document['exact_input_cache']['quantization'] is False


def test_off_grid_replacement_prediction_preserves_observed_source_part_of_current_slot(monkeypatch):
    import v42_integration.experimental_policy as module
    from dataclasses import replace
    provider=research_provider();job,_=participant(provider)
    provider=research_provider();job=replace(job,t50_seconds=5400,state='RUNNING')
    receipt=provider.issue(job);p=policy(provider,profile='migration_witness');ledger=ReservationLedger({'A':8,'B':8})
    ledger.retain_running(job.uid,'A',0,5400,1)
    ledger.retain_running('OBSERVED_BACKGROUND','B',0,86400,1)
    m=metadata(provider,job,receipt);m.update(state='RUNNING',current_site='A',accumulated_compute_seconds=1800)
    p.set_observed_context(now=450,observed_gpu={'A':1,'B':1},pending_nominal_work={},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    capture=[];original=module.evaluate_q90_recourse
    def spy(*args,**kwargs):
        capture.append(kwargs['candidate_gpu_delta'].copy());return original(*args,**kwargs)
    monkeypatch.setattr(module,'evaluate_q90_recourse',spy)
    p._score(m,[dict(resource='gpu:A',begin=450,end=900,quantity=1),
        dict(resource='gpu:B',begin=1800,end=6300,quantity=1)],450,ledger,replace=True,
        reference_segments=ledger.reservations[job.uid]['segments'])
    assert capture[0][0,0]==0  # Earlier 0..450 history cancels from after-minus-reference.
    assert capture[0][0,1]==0


def test_research_route_packet_reserves_each_link_and_keeps_payload_separate_from_rounding():
    from dataclasses import asdict,replace
    provider=research_provider();job,_=participant(provider);provider=research_provider()
    job=replace(job,t50_seconds=5400,state='RUNNING',origin_unknown=True)
    authority=dict(packet_source_sha='NAMED_SYNTHETIC_ORIGINAL_PHYSICAL_MODEL',
        scalar={'bytes_per_GPU':90000,'current_conservative_restart_seconds':900},
        routes={'AB_ROUTE':dict(source='A',destination='B',links=['AB'],bandwidth_bytes_per_second=100)},
        links={'AB':{'bandwidth_bytes_per_second':100}},
        protocol={'source_hold_until':'transfer_start','destination_hold_from':'transfer_end'},
        wan_capacities={'AB_ROUTE':100,'LINK::AB':100},request_capability_is_observed=False)
    p=policy(provider,migration_authority=authority,profile='migration_witness')
    r=JobRequest(job.uid,0,1,('A','B'),5400,'A',dict(asdict(job),elapsed_compute_seconds=0))
    result=run_experimental_actual({'A':8,'B':8},[],Environment({job.uid:5400},{job.uid:5400}),
        arm='B3',qos_window_provider=provider,frozen_policy=p,running=[(r,'A',0)],
        end=8100,wan_capacities=authority['wan_capacities'])
    assert len(result['migration_receipts'])==1
    migration=result['migration_receipts'][0]
    resources={s['resource'] for s in migration['segments']}
    assert {'wan:AB_ROUTE','wan:LINK::AB','active:WAN'}<=resources
    assert migration['WAN_payload_bytes_on_each_ordered_link']=={'AB':90000}
    assert migration['WAN_reservation_bytes_on_each_link']==90000
    assert migration['request_capability_is_observed_Kestrel'] is False
    assert result['receipt']['capacity_violations']==0
    assert result['compute_occupancy_GPU'].sum()*900==5400


def test_final_May_case_requires_literal_A2_and_original_TRAIN_CDF():
    from v42_integration.experimental_actual import run_conditional_case
    with pytest.raises(ValueError,match='LITERAL_A2_NOMINAL_AND_ORIGINAL_TRAIN_CDF_RECOURSE_REQUIRED'):
        run_conditional_case({},scenario='E1',participation='FLEX30',algorithm='GRID_SENSITIVITY_AWARE',
            case_sha='NEW_SCIENCE',source_freeze_sha='SOURCE')


def test_future_horizon_veto_does_not_rebase_after_expiry_on_new_capacity_block():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    # A future source row is unsupported, while DD00 actual geometry is safe.
    p.packet.bias[8][0]+=1.
    p.packet.coefficients[8].current_constant[0]+=1.
    context(p,job);m=metadata(provider,job,receipt,sites=('A',));m['Can_Preplace']=False
    ledger=ReservationLedger({'A':8,'B':8})
    first=p.select(m,receipt,0,ledger,reserve=False)
    assert first['action']=='QUEUE' and p.references[job.uid]['reference_start_seconds']==0
    assert not p.observed_blocks
    p.set_observed_context(now=3600,observed_gpu={'A':8,'B':0},pending_nominal_work={},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    ledger.retain_running('LATER_OBSERVED_RUNNING','A',3600,4500,8)
    retry=p.select(m,receipt,3600,ledger,reserve=False)
    assert retry['action']=='QUEUE' and retry['status']=='EMPTY_EXPERIMENTAL_EXECUTION_WINDOW'
    assert p.references[job.uid]['reference_start_seconds']==0 and not p.observed_blocks
    assert provider.receipts[job.uid] is receipt and receipt.budget_seconds==1800


def test_reference_advances_only_with_prior_due_observed_block_and_no_budget_refund():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider,algorithm='FIXED')
    m=metadata(provider,job,receipt,sites=('A',));m['Can_Preplace']=False
    ledger=ReservationLedger({'A':8,'B':8})
    # Nominal booking is not completion truth: physical observed gang still fills A.
    p.set_observed_context(now=0,observed_gpu={'A':8,'B':0},pending_nominal_work={},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    assert p.select(m,receipt,0,ledger,reserve=False)['action']=='QUEUE'
    assert p.observed_blocks[job.uid]['observed_at_seconds']==0
    p.set_observed_context(now=900,observed_gpu={'A':0,'B':0},pending_nominal_work={},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    result=p.select(m,receipt,900,ledger,reserve=False)
    assert result['action']=='START' and result['causal_reference_start_seconds']==900
    advance=[r for r in p.reference_audit if r['event']=='OBSERVED_PHYSICAL_REFERENCE_ADVANCE'][-1]
    assert advance['proof']['observed_at_seconds']==0 and not advance['immutable_budget_renewed']
    assert provider.receipts[job.uid] is receipt and result['additional_start_delay_seconds']==0


def test_committed_selected_delay_spends_once_retry_without_renewal():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    context(p,job,background=False);m=metadata(provider,job,receipt,sites=('A',));m['Can_Preplace']=False
    ledger=ReservationLedger({'A':8,'B':8})
    selected=p.select(m,receipt,0,ledger,reserve=True)
    assert selected['action']=='DELAY' and m['additional_start_delay_seconds']==900
    ledger.release(job.uid,900)
    p.set_observed_context(now=900,observed_gpu={'A':0,'B':0},pending_nominal_work={},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    retry=p.select(m,receipt,900,ledger,reserve=True)
    assert retry['additional_start_delay_seconds']==900
    assert retry['execution_window_receipt']['remaining_budget_seconds']==900
    assert retry['execution_window_receipt']['latest_start_seconds']==1800
    assert p.references[job.uid]['first_reference_start_seconds']==0


def test_experimental_resume_fails_closed_instead_of_reopening_frozen_reference():
    provider=research_provider();p=policy(provider)
    controller=ExperimentalJobEventController({'A':8,'B':8},arm='B3',qos_window_provider=provider,frozen_policy=p)
    job,_=participant(provider)
    from dataclasses import asdict
    controller.submit(JobRequest(job.uid,0,1,('A',),900,'A',asdict(job)),0)
    controller._policy_resource_guard(0)
    p.select(controller.metadata[job.uid],controller.budgets[job.uid],0,controller.reservations,reserve=False)
    snapshot=controller.snapshot(3600)
    assert snapshot['experimental_runtime_state']['references']==p.references
    with pytest.raises(ValueError,match='CONTINUATION_NOT_SUPPORTED_NO_REFERENCE_RENEWAL'):
        controller.restore(snapshot)
    assert p.references[job.uid]['first_reference_start_seconds']==0


def test_instantaneous_whole_gang_guard_never_uses_partial_slot_average():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider)
    p.set_observed_context(now=450,observed_gpu={'A':8,'B':0},pending_nominal_work={},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    m=metadata(provider,job,receipt)
    score,reason=p._score(m,[dict(resource='gpu:A',begin=450,end=451,quantity=1)],450,
        ReservationLedger({'A':8,'B':8}))
    assert score is None and reason=='CURRENT_INSTANTANEOUS_WHOLE_GANG_CAPACITY'


def test_continuous_observed_block_chain_then_release_preserves_frozen_budget():
    provider=research_provider();job,receipt=participant(provider);p=policy(provider,algorithm='FIXED')
    m=metadata(provider,job,receipt,sites=('A',));m['Can_Preplace']=False
    ledger=ReservationLedger({'A':8,'B':8})
    for clock in (0,900,1800):
        p.set_observed_context(now=clock,observed_gpu={'A':8,'B':0},pending_nominal_work={},
            remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
        assert p.select(m,receipt,clock,ledger,reserve=False)['action']=='QUEUE'
        assert p.observed_blocks[job.uid]['observed_at_seconds']==clock
    p.set_observed_context(now=2700,observed_gpu={'A':0,'B':0},pending_nominal_work={},
        remaining_q50=[0.]*24,remaining_q90=[0.]*24,forecast_depletion={})
    selected=p.select(m,receipt,2700,ledger,reserve=False)
    assert selected['action']=='START' and selected['causal_reference_start_seconds']==2700
    assert p.references[job.uid]['first_reference_start_seconds']==0 and not p.observed_blocks
    assert provider.receipts[job.uid] is receipt and selected['additional_start_delay_seconds']==0
    advances=[r for r in p.reference_audit if r['event']=='OBSERVED_PHYSICAL_REFERENCE_ADVANCE']
    assert [r['proof']['observed_at_seconds'] for r in advances]==[0,900,1800]
