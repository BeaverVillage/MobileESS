"""Independent named synthetic 96-slot signed-grid policy counterexamples."""
from copy import deepcopy
from types import SimpleNamespace

import numpy as np
import pytest

from v42_integration.policy import ReservationLedger, digest
from v42_integration.sensitivity_policy import (build_grid_packet,compile_sensitivity_policy,
    FrozenSensitivityPolicy,POLICY_ID,bounded_prototypes,export_policy_evidence)


def fixture(*, destination_slope=-.2, transformer_slope=0., voltage_slope=0., q90_extra=0.,
            kva_rating=None, profile='rebound', runtime_lower=900., running=False,mess_p=0.):
    sites=('A','B');controls=('aidc_load_kw[A]','aidc_load_kw[B]','mess_p_kw[M]','mess_q_kvar[M]')
    branches=('line.fixture::a','transformer.fixture::a');sha='a'*64
    baseline=np.zeros((96,2))
    if running:baseline[:8,0]=1
    else:baseline[:,0]=1;baseline[:,1]=1
    coefs=[]
    for t in range(96):
        # Baseline rho=.9 now, .85 at rebound, .2 elsewhere. The signed
        # current correction is independently checkable because flow rows=0.
        rho=.9 if t==0 else .85 if t==1 else .2
        if profile=='placement':rho=.9 if t==0 else .2
        cm=np.array([[.3,0.],[destination_slope,transformer_slope],[-.1,0.],[.05,0.]])
        x=np.r_[baseline[t],0.,0.]
        current=np.array([rho,.5])-cm.T@x
        voltage=np.array([1.])-np.array([[0.],[voltage_slope],[0.],[0.]]).T@x
        flow_p_matrix=np.zeros((2,4));flow_p_constant=np.zeros(2)
        if kva_rating is not None:
            flow_p_matrix[1,1]=1.;flow_p_constant[1]=.05-baseline[t,1]
        coefs.append(SimpleNamespace(slot=t,control_names=controls,branch_names=branches,
            coefficient_sha256=sha,anchor=x,voltage_constant=voltage,
            voltage_matrix=np.array([[0.],[voltage_slope],[0.],[0.]]),
            current_constant=current,current_matrix=cm,
            flow_p_constant=flow_p_constant,flow_q_constant=np.zeros(2),
            flow_p_matrix=flow_p_matrix,flow_q_matrix=np.zeros((2,4)),
            branch_limits=np.ones(2),transformer_ratings=(None,kva_rating)))
    final_mess=dict(P_by_site={'M':[mess_p]+[0.]*95},Q_by_site={'M':[0.]*96},
        routes={'m':[0]*96},SOC={'m':[1.]*97},Mode={'m':[0]*96},
        fixture_authority='NAMED_SYNTHETIC_96_SLOT_SIGNED_GRID_GEOMETRY_ONLY')
    final_mess['plan_sha']=digest(final_mess)
    pf=.95
    aidc=dict(aidc_anchor='A_FIXED_ANCHOR',AIDC_P_by_site={s:baseline[:,j].tolist() for j,s in enumerate(sites)},
        AIDC_Q_by_site={s:(baseline[:,j]*np.tan(np.arccos(pf))).tolist() for j,s in enumerate(sites)})
    bindings=dict(science_sha='FIXTURE_SCIENCE',qos_sha='FIXTURE_QOS',case_sha='FIXTURE_CASE',
        aidc_anchor=aidc['aidc_anchor'],mess_anchor=final_mess['plan_sha'],cc4_sha='FIXTURE_CC4_PREDICTION',
        runtime_sha='FIXTURE_RUNTIME_Q50',response_sha=sha,initial_state_sha='FIXTURE_COMMON_DD00')
    envelope=[dict(site=s,slot_start=float(t*900),slot_end=float((t+1)*900),gpu_capacity=1.,
        source_variable=f'anonymous_GPU[{s},{t}]',carryout_end=86400.) for t in range(96) for s in sites]
    known=np.zeros((96,2))
    if running:
        envelope=[dict(r,gpu_capacity=1. if r['site']=='B' or r['slot_start']<8*900 else 0.) for r in envelope]
        aidc['AIDC_P_by_site']['B']=[1.]*96
        aidc['AIDC_Q_by_site']['B']=[float(np.tan(np.arccos(pf)))]*96
        # Base coefficients anchor is independent of the final control point.
    packet=build_grid_packet(coefs,{(s,t):SimpleNamespace(slope=1.,intercept_kw=0.)
        for s in sites for t in range(96)},1.,{'A':8,'B':8},aidc,final_mess,
        SimpleNamespace(voltage_lower_squared=.94**2,voltage_upper_squared=1.06**2),bindings,
        known_gpu=known,mess_validation=dict(plan_sha=final_mess['plan_sha'],frozen_execution_validated=True))
    q50=np.full(24,26./24 if running else 2.);q90=q50.copy();q90[0]+=q90_extra
    stress=np.zeros((96,2));stress[0,1]=4*q90_extra
    authority=dict(model_id='LGBM_weighted_c1_s20260924',prediction_sha=bindings['cc4_sha'],
        runtime_sha=bindings['runtime_sha'],kernel_sha='FIXTURE_TRAIN_KERNEL_SHA',stress_site_GPU=stress.tolist())
    prototype=dict(state='RUNNING' if running else 'PENDING',gpu=1,service_seconds=900.,
        runtime_lower_seconds=runtime_lower,runtime_upper_seconds=900.,reference_site='A',
        compatible_sites=['A','B'],qos='normal',budget_seconds=3600,can_prestart_place=True,time_slots=[0])
    return packet,envelope,q50,q90,[1.],prototype,bindings,authority


def compile_fixture(values, **kwargs):
    packet,envelope,q50,q90,kernel,proto,bindings,authority=values
    return compile_sensitivity_policy(packet,envelope,q50,q90,kernel,[proto],bindings,authority,**kwargs)


def metadata(service=900.):
    return dict(uid='OBSERVED_FIXTURE_JOB',submit_seconds=0.,event_seconds=0.,state='PENDING',qos='normal',
        protected=False,batch_eligible=True,is_observed=True,gpu=1,t50_seconds=service,
        nominal_service_seconds=service,source_site='A',reference_site='A',compatible_sites=['A','B'],
        can_prestart_place=True,cumulative_migration_interruption_seconds=0.)


def receipt(budget=3600):
    return dict(uid='OBSERVED_FIXTURE_JOB',case_sha='FIXTURE_CASE',reference_start_seconds=0.,
        budget_seconds=budget,allowed_starts_seconds=list(range(0,budget+1,900)))


def test_original_signed_grid_equations_and_final_mess_are_used_exactly():
    values=fixture();packet=values[0]
    delta=np.zeros((96,2));delta[0]=[-1,1]
    score=packet.evaluate(delta)
    c=packet.coefficients[0];control=packet.controls[0].copy();control[:2]+=delta[0]
    direct=c.current_constant+c.current_matrix.T@control
    assert score['per_slot_peak'][0]==pytest.approx(direct[0])
    assert score['per_slot_peak'][0]==pytest.approx(.4)
    assert score['peak_score']==pytest.approx(.85)
    assert np.all(packet.p_slope==1.)
    assert packet.authority['AIDC_Q']=='ORIGINAL_PF_COUPLED_RESPONSE_NOT_DOUBLE_COUNTED'
    # Frozen MESS positive injection uses the original negative signed column.
    moved=fixture(mess_p=1.)[0]
    assert moved.evaluate(np.zeros((96,2)))['per_slot_peak'][0]==pytest.approx(.8)


def test_rebound_counterexample_compares_all_remaining_slots_not_current_only():
    policy=compile_fixture(fixture(destination_slope=0.))
    template=policy.document['templates'][0]
    scores=template['scenario_comparisons']
    start=next(r for r in scores if r['action']=='START_NOW')
    delay=next(r for r in scores if r['action']=='DELAY_15')
    assert start['scenario_scores']['NOMINAL_Q50']==pytest.approx(.9)
    assert delay['scenario_scores']['NOMINAL_Q50']==pytest.approx(1.15)
    assert not delay['hard_feasible']
    assert all(r['action']!='DELAY_15' for r in template['ordered_actions'])
    # Resource-only current-slot reduction chooses the delay; full96 rejects it.
    assert fixture()[0].evaluate(np.zeros((96,2)))['remaining_slots']==96


def test_offline_ablation_has_distinct_scores_without_forcing_actions():
    values=fixture(profile='placement');policy=compile_fixture(values)
    scores=policy.document['templates'][0]['scenario_comparisons']
    fixed=next(r for r in scores if r['action']=='START_NOW')
    greedy=next(r for r in scores if r['action']=='DELAY_15')
    grid=policy.document['templates'][0]['ordered_actions'][0]
    assert fixed['scenario_scores']['NOMINAL_Q50']==pytest.approx(.9)
    assert greedy['scenario_scores']['NOMINAL_Q50']==pytest.approx(.6)
    assert grid['worst_peak_score']==pytest.approx(.4)
    assert grid['action']=='PREPLACE'
    assert policy.document['status']=='OFFLINE_POLICY_OPTIMIZATION_VALIDATED'
    assert policy.document['metrics']['Native_Optimize_calls']==0
    assert policy.document['Fresh_AC_status']=='NOT_RUN'


@pytest.mark.parametrize('constraint',['voltage','current','kva'])
def test_original_hard_constraints_reject_better_peak_actions(constraint):
    values=fixture(profile='placement',transformer_slope=.6 if constraint=='current' else 0.,
        voltage_slope=.3 if constraint=='voltage' else 0.,kva_rating=.1 if constraint=='kva' else None)
    packet=values[0]
    policy=compile_fixture(values)
    template=policy.document['templates'][0]
    assert all(row['action']!='PREPLACE' for row in template['ordered_actions'])
    rejects=[r for r in template['rejected_candidates'] if r.get('action')=='PREPLACE']
    assert rejects and any(not s['hard_feasible'] for s in rejects[0]['scenarios'].values())


def test_q90_is_separate_stress_not_added_twice_and_unsupported_burst_is_explicit():
    values=fixture(destination_slope=.2,profile='placement',q90_extra=.25)
    policy=compile_fixture(values);audit=policy.document['scenario_audit']
    assert audit['Q90_minus_Q50_GPUh']==.25 and audit['Q90_stress_day_GPUh']==.25
    assert not audit['Q90_actual_load_addition'] and audit['Q50_already_in_AIDC_baseline']
    assert audit['TRAIN_BURST_STRESS']=='INSUFFICIENT_SUPPORT'
    assert set(audit['scenario_names'])=={'NOMINAL_Q50','HIGH_DEMAND_Q90'}
    scores=policy.document['templates'][0]['scenario_comparisons']
    start=next(r for r in scores if r['action']=='START_NOW')
    assert start['scenario_scores']['HIGH_DEMAND_Q90']==pytest.approx(1.1)
    assert all(not r['hard_feasible'] for r in scores if r['action']=='START_NOW')
    unsupported=list(deepcopy(values));unsupported[-1].pop('stress_site_GPU')
    blocked=compile_fixture(unsupported)
    assert blocked.document['scenario_audit']['status']=='INSUFFICIENT_SOURCE_SITE_DISTRIBUTION'
    assert blocked.document['status']=='POLICY_COMPILER_ONLY'
    assert blocked.select(metadata(),receipt(),0,ReservationLedger({'A':8,'B':8}))['action']=='QUEUE'


def test_optimized_reserve_timing_preserves_source_mass_and_anchor():
    values=list(fixture(q90_extra=.25));authority=values[-1]
    reserve=np.zeros((96,2));reserve[3,1]=1.
    authority.update(stress_site_GPU=reserve.tolist(),stress_profile_GPU=reserve.sum(axis=1).tolist(),
        stress_carryout_GPUh=0.,stress_allocation_source='A_STAGE_OPTIMIZED_RESERVE',
        allocation_aidc_anchor=values[-2]['aidc_anchor'])
    policy=compile_fixture(values)
    assert policy.document['scenario_audit']['Q90_stress_day_GPUh']==.25
    authority['allocation_aidc_anchor']='STALE_A1'
    with pytest.raises(ValueError,match='ALLOCATION_ANCHOR_DRIFT'):compile_fixture(values)


def test_frozen_reload_budget_and_whole_gang_atomic_reservation(tmp_path):
    policy=compile_fixture(fixture(profile='placement'))
    path=tmp_path/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json';policy.save(path)
    reload=FrozenSensitivityPolicy.load(path,bindings=policy.bindings)
    ledger=ReservationLedger({'A':1,'B':1})
    first=reload.select(metadata(),receipt(900),0,ledger)
    assert first['action']=='PREPLACE' and first['policy_action']=='PREPLACE'
    assert first['estimated_worst_peak']==pytest.approx(.4)
    assert first['online_grid_horizon_evaluations']==0
    again=reload.select(metadata(),receipt(900),0,ledger)
    assert again['action']=='QUEUE'
    assert len(ledger.reservations)==1
    assert all(c['additional_start_delay_seconds']<=900 for c in reload.candidates(metadata(),receipt(900),0)[0])
    with pytest.raises(ValueError,match='ANCHOR_MISMATCH'):
        FrozenSensitivityPolicy.load(path,bindings=dict(policy.bindings,mess_anchor='STALE_M1'))


def test_upper_bucket_checks_piecewise_endpoints_but_does_not_change_actual_q50():
    policy=compile_fixture(fixture(profile='placement',runtime_lower=0.))
    template=policy.document['templates'][0]
    assert template['runtime_match']=='PIECEWISE_CERTIFIED_UPPER_BUCKET'
    observed=metadata(450)
    result=policy.select(observed,receipt(),0,ReservationLedger({'A':8,'B':8}))
    assert result['nominal_end_seconds']-result['start_seconds']==450
    assert observed['t50_seconds']==observed['nominal_service_seconds']==450
    outside=metadata(901)
    blocked=policy.select(outside,receipt(),0,ReservationLedger({'A':8,'B':8}))
    assert blocked['action']=='QUEUE' and blocked['reason']=='NO_MATCHED_FROZEN_TEMPLATE'


def test_same_frozen_inputs_have_deterministic_policy_identity_and_no_future_uids():
    first=compile_fixture(fixture());second=compile_fixture(fixture())
    assert first.sha==second.sha
    assert first.document['templates']==second.document['templates']
    values=fixture();values[5]['job_uid']='A_FUTURE_MAY_JOB'
    with pytest.raises(ValueError,match='FUTURE_JOB_IDENTITIES'):compile_fixture(values)
    with pytest.raises(ValueError,match='TRAIN_BURST_SOURCE'):
        compile_fixture(fixture(),burst=dict(source_partition='May',source_sha='unsupported'))
    meta=metadata();meta['future_queue']='PRIVATE'
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):
        first.select(meta,receipt(),0,ReservationLedger({'A':8,'B':8}))


def test_frozen_running_migration_reuses_checkpoint_shared_budget_and_service():
    values=fixture(profile='placement',running=True)
    proto=values[5];proto.update(time_slots=[0],accumulated_compute_seconds=1800,
        wan_capacities={'AB':100.},migration_capability=dict(source_sha='FIXTURE_PHYSICAL_CONTRACT',
            checkpoint_authorized=True,allowed_destinations=['B'],gpu_type_confirmed=True,
            rack_gang_confirmed=True,data_residency_confirmed=True,wan_path='AB',
            bandwidth_bytes_per_second=100.,payload_bytes=90000.,restart_seconds=900.,
            source_wait_seconds=0.,source_hold_until='transfer_start',destination_hold_from='transfer_end'))
    policy=compile_fixture(values)
    meta=metadata();meta.update(state='RUNNING',current_site='A',t50_seconds=2700.,
        accumulated_compute_seconds=1800.,migration_count=0,migration_capability=proto['migration_capability'])
    ledger=ReservationLedger({'A':8,'B':8},{'AB':100.})
    result=policy.select_migration(meta,receipt(),0,ledger)
    assert result['action']=='CHECKPOINT_MIGRATE'
    assert result['migration']['interruption_seconds']==1800
    assert result['migration']['times']['restart_end']==1800
    assert result['migration']['segments'][-1]['end']==2700
    assert meta['accumulated_compute_seconds']==1800 and meta['t50_seconds']==2700
    ledger2=ReservationLedger({'A':8,'B':8},{'AB':100.})
    no_budget=policy.select_migration(meta,receipt(900),0,ledger2)
    assert no_budget['action']=='STAY' and not ledger2.reservations
    meta['accumulated_compute_seconds']=1799
    no_checkpoint=policy.select_migration(meta,receipt(),0,ledger2)
    assert no_checkpoint['action']=='STAY' and not ledger2.reservations
    meta['accumulated_compute_seconds']=1800
    meta['migration_capability']=dict(meta['migration_capability'],source_wait_seconds=900)
    changed=policy.select_migration(meta,receipt(),0,ledger2)
    assert changed['action']=='STAY' and not ledger2.reservations
    assert changed['reason']=='MIGRATION_PHYSICAL_PROFILE_OUTSIDE_FROZEN_TEMPLATE'
    offgrid=policy.select_migration(meta,receipt(),100,ledger2,checkpoint_at=100)
    assert offgrid['action']=='STAY' and offgrid['reason']=='OFF_GRID_CHECKPOINT_OUTSIDE_FROZEN_SCORE_TEMPLATE'


def test_unknown_running_reference_never_borrows_fixed_known_service():
    values=list(fixture(running=True))
    for row in values[1]:
        if row['site']=='A':row['gpu_capacity']=0.
    values[2]=np.ones(24);values[3]=np.ones(24)
    values[0].known_gpu[:8,0]=1.
    policy=compile_fixture(values)
    template=policy.document['templates'][0]
    assert not template['ordered_actions']
    assert template['rejected_candidates'][0]['reason']=='PROTOTYPE_REFERENCE_NOT_IN_ANONYMOUS_ENVELOPE'
    assert template['Known_schedule_modifications']==0
    values[5]['reference_resource_scope']='KNOWN'
    with pytest.raises(ValueError,match='MUST_NOT_BORROW_KNOWN_SERVICE'):compile_fixture(values)


def test_bounded_prototypes_include_running_and_source_racks_before_reference():
    values=fixture();packet=values[0]
    prototypes=bounded_prototypes(packet,values[1])
    assert 0<len(prototypes)<=144 and {r['state'] for r in prototypes}=={'PENDING','RUNNING'}
    assert all('uid' not in r and r['reference_resource_scope']=='ANONYMOUS' for r in prototypes)
    assert all(r['migration_capability'] is None for r in prototypes if r['state']=='RUNNING')
    packet.rack_compatibility={'A':(1,), 'B':(8,)}
    restricted=bounded_prototypes(packet,values[1],time_slots=[0],gpu_gangs=(4,),runtime_bounds=(900,),max_templates=2)
    assert all(r['reference_site']=='B' and r['compatible_sites']==['B'] for r in restricted)


def test_resource_support_is_literal_scenario_bound_not_actual_grid_certificate():
    policy=compile_fixture(fixture(q90_extra=.25))
    support=policy.resource_support_at(0)
    assert support['lower_by_site']=={'A':1.,'B':1.}
    assert support['upper_by_site']=={'A':1.,'B':2.}
    assert len(support['source_sha'])==64
    assert support['support_is_necessary_guard_not_Actual_grid_certificate']
    assert policy.resource_baseline_at(0)=={'A':1.,'B':1.}
    assert policy.resource_support_at(86400) is None
    assert not policy.document['Event30']['activation_claimed']


def test_policy_export_freeze_and_reload_evidence_has_no_actual_claim(tmp_path):
    policy=compile_fixture(fixture(profile='placement'))
    receipts=export_policy_evidence(policy,tmp_path)
    assert {'GRID_SENSITIVITY_SCORE_AUDIT.json','CONTROL_POLICY_RELOAD_TEST.json',
        'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json'}<=set(receipts)
    loaded=FrozenSensitivityPolicy.load(tmp_path/'OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json',bindings=policy.bindings)
    assert loaded.sha==policy.sha and loaded.document['templates']==policy.document['templates']
    assert len(receipts['OPTIMIZED_CONDITIONAL_CONTROL_POLICY.json']['sha256'])==64


def test_q50_envelope_mass_cannot_silently_change_source_prediction():
    values=list(fixture());values[2]=np.zeros(24);values[3]=np.zeros(24)
    with pytest.raises(ValueError,match='NOMINAL_SERVICE_CARRYOUT_MASS_DRIFT'):compile_fixture(values)
