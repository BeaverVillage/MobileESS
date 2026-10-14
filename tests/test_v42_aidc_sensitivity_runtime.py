"""Named numerical counterexamples; independent of historical May evidence."""
from copy import deepcopy
from dataclasses import replace, dataclass
from types import SimpleNamespace
import numpy as np
import pytest

from v42_integration.aidc_sensitivity_runtime import (Research60QoSProvider,
    SignedSensitivityPolicy, SensitivityRuntimeController, conditional_remaining_runtime,
    safe_backfill, known_initial_reconciliation, known_planning_bridge, coordinator_actual_runner)
from v42_integration.aidc_sensitivity_runtime import bind_unified_planning
from v42_integration.aidc_sensitivity_runtime import run_b1_prefix_canary
from v42_integration.aidc_sensitivity_runtime import profile_observed_decision
from v42_integration.aidc_sensitivity_runtime import require_final_a_authority, grid_numeric_fingerprint
from v42_integration.aidc_sensitivity_runtime import select_cc4_headroom_seed_choices
from v42_integration.aidc_sensitivity_runtime import build_boundary_completion_proof,require_boundary_completion_proof
from v42_integration.aidc_sensitivity_runtime import audit_seed_grid_outer_box
from v42_integration.aidc_sensitivity_runtime import anonymous_cohort_residual
from v42_integration.aidc_sensitivity_runtime import (SiteOnlySensitivityPolicy,SiteOnlyJobEventController,
    build_dday_known_fcfs_baseline,run_frozen_known_site_only_canary,run_site_only_prefix_canary)
from v42_integration.aidc_sensitivity_runtime import run_dday_known_site_only_canary
from v42_integration.trajectory_tracking import TrackingReference
from v42_integration.qos import CausalReferenceScheduler
from v42_integration.unified_contract import BINDING_FIELDS, load_contracts
from v42_integration.policy import ReservationLedger, digest
from v42_integration.actual import run_actual, FrozenPowerModel
from v42_capacity.actual import Environment
from test_v42_integration_actual import qos, request, capability
from test_v42_integration_sensitivity_policy import fixture
from test_v42_experimental_control import observed, metadata


def provider():
    strict = qos()
    spec = dict(schema='V42_NAMED_FIXTURE_RESEARCH60', source_training_sha=strict.stats.sha,
        participation='FLEX30', max_start_delay_seconds=3600, customer_SLA_claim=False,
        reissue_on_retry=False)
    return Research60QoSProvider(strict, case_sha=digest('FIXTURE_RESEARCH60_CASE'), frozen_spec=spec)


def participant(p):
    for i in range(100):
        j = replace(observed('FIXTURE60_UID_'+str(i)), origin_unknown=True)
        r = p.issue(j)
        if r.participant:
            return j, r
    raise AssertionError('FIXTURE_MEMBER_ABSENT')


def example(*, runtime_repair=True, basic=False, two_lines=False):
    p = provider()
    job, receipt = participant(p)
    packet = fixture(profile='placement')[0]
    bindings = {key:digest('NAMED_SIGNED_RUNTIME_FIXTURE:'+key) for key in BINDING_FIELDS}
    bindings['qos_sha'] = p.stats.sha
    bindings['case_sha'] = p.case_sha
    packet.bindings = bindings
    if two_lines:
        packet.branch_names = ('line.first::A', 'line.newcritical::B')
        packet.line_indices = np.array([0, 1])
        packet.transformer_indices = np.array([], dtype=int)
        for t, c in enumerate(packet.coefficients):
            c.branch_names = packet.branch_names
            c.current_matrix = np.array([[-.5, .5], [-.2, .05], [0, 0], [0, 0]])
            base = np.array([.8, .4]) if t == 0 else np.array([.1, .1])
            c.current_constant = base-c.current_matrix.T@packet.controls[t]
            packet.correction[t] = c.current_matrix.T
            packet.bias[t] = c.current_constant+c.current_matrix.T@c.anchor
    z = np.zeros((96, 2))
    ref = TrackingReference(z, z, z, z, z, sites=packet.sites, begin=0,
        commands={}, identity={'evidence_scope':'NAMED_SYNTHETIC_RUNTIME_FIXTURE'})
    policy = SignedSensitivityPolicy(ref, packet, bindings=bindings, expected_bindings=bindings,
        runtime_repair=runtime_repair, basic=basic, evidence_scope='NAMED_SYNTHETIC_RUNTIME_FIXTURE')
    m = metadata(p, job, receipt)
    policy.observe(0, {'A':0, 'B':0}, {job.uid:m})
    return p, job, receipt, policy, m


def site_only_example(*,basic=False,commands=None,study_authority=False):
    p,j,r,template,m=example(two_lines=True)
    z=np.zeros((96,2))
    ref=TrackingReference(z,z,z,z,z,sites=template.packet.sites,begin=0,commands=commands or {},
        identity={'evidence_scope':'NAMED_SITE_ONLY'})
    identity=dict(study_case_sha=digest('NAMED_SITE_STUDY'),Known_booking_horizon_seconds=86400)
    authority=dict(schema='PUBLIC_UNKNOWN_PRESTART_COMPATIBLE_SITE_STUDY_V1',study_case_sha=identity['study_case_sha'],
        interface_sha=template.bindings['interface_sha'],candidate_axis='SOURCE_COMPATIBLE_SITES_ONLY',
        intentional_delay_seconds=0,max_sites=12,Known_commands_modified=False,source_customer_SLA_claim=False)
    policy=SiteOnlySensitivityPolicy(ref,template.packet,bindings=template.bindings,expected_bindings=template.bindings,
        evidence_scope='NAMED_SITE_ONLY',basic=basic,source_identity=identity,
        site_authority=authority if study_authority else None)
    policy.observe(0,{'A':0,'B':0},{j.uid:m})
    return p,j,r,policy,m


def test_site_only_reads_current_all_lines_and_never_future_grid_or_cc4():
    _,_,r,p,m=site_only_example()
    p.packet.coefficients[4].voltage_constant[:]=100
    p.anonymous_residual_audit={'status':'CONSERVATION_NOT_CERTIFIED'}
    decision=p.select(m,r,0,ReservationLedger({'A':8,'B':8}),reserve=False)
    assert decision['site']=='B' and decision['start_seconds']==0
    assert decision['tracking']['checked_grid_slots']==1
    assert decision['tracking']['grid_peak']==pytest.approx(.6)
    assert decision['intentional_delay_seconds']==0 and not decision['migration']
    with pytest.raises(ValueError,match='SITE_ONLY_FUTURE'):
        p._public_future(None,None)


def test_site_only_waits_until_source_actual_executable_event_without_future_booking():
    _,_,r,p,m=site_only_example()
    r=replace(r,reference_start_seconds=5400,allowed_starts_seconds=(5400,6300),latest_start_seconds=6300)
    reservations=ReservationLedger({'A':8,'B':8})
    early=p.select(m,r,0,reservations)
    assert early['action']=='QUEUE' and early['candidate_count']==0
    assert reservations.reservations=={}
    p.observe(5400,{'A':0,'B':0},{m['uid']:m})
    d=p.select(m,r,5400,reservations)
    assert d['start_seconds']==5400 and d['additional_start_delay_seconds']==0


def test_site_only_zero_budget_may_use_explicit_study_site_authority_without_rewriting_source():
    _,_,r,p,m=site_only_example(study_authority=True)
    r=replace(r,budget_seconds=0,allowed_starts_seconds=(0,),latest_start_seconds=0)
    m['can_prestart_place']=False
    before=digest(m);receipt_before=digest(r.to_dict())
    d=p.select(m,r,0,ReservationLedger({'A':8,'B':8}),reserve=False)
    assert d['site']=='B' and d['additional_start_delay_seconds']==0
    assert digest(m)==before and digest(r.to_dict())==receipt_before


def test_site_only_preserves_source_site_authority_without_explicit_study():
    _,_,r,p,m=site_only_example()
    m['can_prestart_place']=False
    d=p.select(m,r,0,ReservationLedger({'A':8,'B':8}),reserve=False)
    assert d['site']=='A'
    assert any(row['reason']=='PREPLACE_SOURCE_AUTHORITY' for row in d['rejected_candidates'])


def test_site_only_unbounded_runtime_blocks_future_firm_known_even_after_q50():
    commands={'K':dict(site='A',start_seconds=1800,protected_segments=[dict(resource='gpu:A',begin=1800,end=2700,quantity=8)])}
    provider_,_,r,p,m=site_only_example(commands=commands,basic=True)
    m.update(compatible_sites=['A'],t50_seconds=900)
    c=SiteOnlyJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider_,frozen_policy=p,known_schedule=commands)
    d=p.select(m,r,0,c.reservations)
    assert d['action']=='QUEUE'
    assert d['reason']=='UNKNOWN_UNBOUNDED_RUNTIME_KNOWN_FIRM_BOOKING'


def test_current_gpu_reject_witness_does_not_inherit_another_sites_prior_booking_conflict():
    _,_,r,p,m=site_only_example(basic=True)
    p.observe(0,{'A':8,'B':0},{m['uid']:m})
    reservations=ReservationLedger({'A':8,'B':8})
    reservations.last_conflict={'resource':'gpu:B','begin':0,'end':900}
    decision=p.select(m,r,0,reservations,reserve=False)
    assert decision['action']=='QUEUE'
    assert decision['reason']=='GPU_CAPACITY_RUNNING_RETAINED'
    witness=next(row for row in p.current_candidates if row['site']=='A')
    assert witness['hard_guard_reason']=='GPU_CAPACITY_RUNNING_RETAINED'
    assert witness['reservation_conflict'] is None


def test_site_only_multiple_unknown_horizon_bookings_cannot_hide_nominal_expiry():
    commands={'K':dict(site='A',start_seconds=1800,protected_segments=[dict(resource='gpu:A',begin=1800,end=2700,quantity=6)])}
    provider_,_,r,p,m=site_only_example(commands=commands,basic=True)
    # Capacity concerns are independent of the named electrical witness.
    for t,c in enumerate(p.packet.coefficients):
        c.current_matrix[:]=0;p.packet.correction[t][:]=0;p.packet.bias[t][:]=.1
    m.update(compatible_sites=['A'],gpu=2,t50_seconds=900)
    c=SiteOnlyJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider_,frozen_policy=p,known_schedule=commands)
    first=p.select(m,r,0,c.reservations)
    assert first['action']=='START' and first['segments'][0]['end']==86400
    second=dict(m,uid='SECOND')
    d=p.select(second,r,0,c.reservations)
    assert d['action']=='QUEUE' and d['reason']=='UNKNOWN_UNBOUNDED_RUNTIME_KNOWN_FIRM_BOOKING'


def test_site_only_original_zero_budget_fallback_cannot_bypass_grid_rejection():
    provider_,_,_,p,_=site_only_example(basic=True)
    for c in p.packet.coefficients:c.voltage_constant[:]=100
    c=SiteOnlyJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider_,frozen_policy=p,known_schedule={})
    job=request('ZERO',can_prestart_place=True,protected=True)
    c.submit(job,0)
    assert c.admit(0)==[]
    assert c.metadata['ZERO']['state']=='PENDING'
    assert c.decisions['ZERO']['action']=='QUEUE'


def test_dday_known_actual_keeps_original_b1_priority_order_and_declared_backfill():
    provider_,_,_,p,_=site_only_example()
    jobs=[request('K0',submit=-1800,q50=900,gpu=8,source_site='A',origin_unknown=False),
        request('K1',submit=-900,q50=900,gpu=1,source_site='B',origin_unknown=False)]
    commands={r.uid:dict(site=r.source_site,start_seconds=0,execution_rule='DETERMINISTIC_KNOWN_PRIORITY_SOURCE_FCFS_ORDER_WITH_B1_BACKFILL',
        source_hard_window_valid=True,protected_segments=[]) for r in jobs}
    z=np.zeros((96,2));p.reference=TrackingReference(z,z,z,z,z,sites=('A','B'),begin=0,commands=commands,identity={})
    p.spec['reference_target_sha']=p.reference.sha;p.sha=digest(p.spec)
    c=SiteOnlyJobEventController({'A':8,'B':8},arm='B1',qos_window_provider=provider_,frozen_policy=p,known_schedule=commands)
    for r in jobs:c.submit(r,0)
    # Named initial occupancy is observed; no private duration is needed.
    c.ledger.submit('RUN',-2700,0,1,{'q50':900},SimpleNamespace(predict_total=lambda m,**kw:900))
    c.ledger.start('RUN','A',0,'NAMED_RUNNING')
    assert c.admit(0)==['K1']
    assert c.metadata['K0']['state']=='PENDING'
    assert c.metadata['K1']['state']=='RUNNING'
    assert any(e['event']=='QUEUED' and e['uid']=='K0' for e in c.events)


def test_site_only_policy_freeze_reload_and_unknown_migration_disabled(tmp_path):
    _,_,r,p,m=site_only_example(study_authority=True)
    p.save(tmp_path/'siteonly.json')
    reloaded=SiteOnlySensitivityPolicy.load(tmp_path/'siteonly.json',bindings=p.bindings).bind_runtime_packet(p.packet)
    reloaded.observe(0,{'A':0,'B':0},{m['uid']:m})
    assert reloaded.select(m,r,0,ReservationLedger({'A':8,'B':8}),reserve=False)['site']=='B'
    assert reloaded.select_migration(m,r,0,None)['action']=='STAY'
    with pytest.raises(ValueError,match='HISTORICAL_KNOWN_ACTUAL_COMMANDS_HOLD'):
        run_frozen_known_site_only_canary(tmp_path)


def test_dday_known_reference_uses_current_public_state_same_source_site_and_full_service():
    _,_,_,p,_=site_only_example()
    old=CausalReferenceScheduler({'A':8,'B':8},reference_sha='OLD_SOURCE')
    known=request('K',submit=-900,q50=1800,gpu=2,source_site='A',origin_unknown=False)
    running=request('RUNNING',submit=-1800,q50=900,gpu=8,source_site='A',origin_unknown=False,
        elapsed_compute_seconds=1800)
    args=dict(begin=0,capacities={'A':8,'B':8},requests=[known],running=[(running,'A',-1800)],reference=old)
    a=build_dday_known_fcfs_baseline(args,p.packet)
    assert a['commands']['K']['start_seconds']==900
    assert a['commands']['K']['site']=='A'
    assert a['commands']['K']['nominal_service_seconds']==1800
    assert a['commands']['K']['protected_segments'][0]['end']==2700
    assert a['old_Planning_commands_executed'] is False and a['Native_calls']==0
    assert running.q50==900 and args['running'][0][2]==-1800
    poisoned=dict(args,requests=[replace(known,metadata=dict(known.metadata,future_completion_seconds=900))])
    with pytest.raises(ValueError,match='PRIVATE_REALIZATION'):
        build_dday_known_fcfs_baseline(poisoned,p.packet)


def test_site_only_actual_prefix_executes_known_and_unknown_at_legal_90minute_event(tmp_path):
    provider_,_,_,template,_=site_only_example(study_authority=True)
    reference=CausalReferenceScheduler({'A':8,'B':8},reference_sha='NAMED_DDAY_SOURCE')
    known=request('KNOWN',submit=-900,q50=900,gpu=1,origin_unknown=False)
    unknown=request('UNKNOWN',submit=0,q50=900,gpu=1,can_prestart_place=False,
        reference_start_seconds=5400)
    args=dict(capacities={'A':8,'B':8},begin=0,end=86400,requests=[known,unknown],running=[],
        environment=Environment({'KNOWN':900,'UNKNOWN':1800},{}),qos_window_provider=provider_,reference=reference)
    baseline=build_dday_known_fcfs_baseline(args,template.packet)
    z=np.zeros((96,2));ref=TrackingReference(z,z,z,z,z,sites=('A','B'),begin=0,
        commands=baseline['commands'],identity={'evidence_scope':'NAMED_SITE_ONLY'})
    result=run_site_only_prefix_canary(args,reference=ref,packet=template.packet,
        bindings=template.bindings,source_identity=template.spec['source_identity'],
        site_authority=template.spec['site_authority'],output=tmp_path,slots=8,
        evidence_scope='NAMED_SOURCE_ACTUAL_FIXTURE')
    receipt=result['receipt']
    assert receipt['same_actual_Known_execution']
    assert receipt['C0_Known_execution'][0]['admitted_time']==0
    assert receipt['C0_Known_execution'][0]['completion_observed_time']==900
    for variant in ('C0','C1'):
        actual=result['results'][variant]
        row=next(row for row in actual['queue_ledger'] if row['job_uid']=='UNKNOWN')
        assert row['admitted_time']==5400
        assert row['intentional_delay_seconds']==0
        assert row['accumulated_compute_seconds']==1800
        assert actual['receipt']['optimizer_calls']==0
        assert (tmp_path/(variant+'_FROZEN_SITE_ONLY_POLICY.json')).exists()
    assert receipt['changed_executed_site_UIDs']==['UNKNOWN']
    assert receipt['changed_actual_prefix_compute_GPUh']==pytest.approx(.5)


def test_strict_source_wrapper_explicitly_disables_legacy_experimental_migration_attribute(monkeypatch,tmp_path):
    from v42_integration import production_case,partial_canary,tracking_canary
    task_provider=qos()
    case=SimpleNamespace(qos_provider=task_provider,initial_mess={},
        make_a_case=lambda *a:SimpleNamespace())
    monkeypatch.setattr(production_case,'build_integration_case',lambda **kw:case)
    def source_read(path):
        if str(path).endswith('UNIFIED_INTERFACE_CONTRACT.json'):
            return dict(policy='DDAY_DETERMINISTIC_KNOWN_UNKNOWN_SITE_ONLY',max_start_delay_seconds=0,
                new_Known_A_Heavy_authorized=False)
        return {}
    monkeypatch.setattr(production_case,'read',source_read)
    monkeypatch.setattr(partial_canary,'source_known_records',lambda *a:{})
    def numeric_anchor(source,*a):
        assert source.experimental_migration_authority is None
        assert source.qos_provider is task_provider
        raise RuntimeError('NAMED_STOP_BEFORE_SOURCE_ARRAY_MATERIALIZATION')
    monkeypatch.setattr(tracking_canary,'reference_from_anchor',numeric_anchor)
    with pytest.raises(RuntimeError,match='NAMED_STOP_BEFORE_SOURCE_ARRAY'):
        run_dday_known_site_only_canary(tmp_path,slots=8)


def test_source_training_preserved_and_research60_not_reissued():
    p = provider()
    j, r = participant(p)
    before = digest(p.strict.to_dict())
    assert r.budget_seconds == 3600
    assert r.allowed_starts_seconds == (0, 900, 1800, 2700, 3600)
    assert r.contract_is_observed_SLA is False
    assert p.issue(replace(j, event_seconds=900)) is r
    assert p.source_training_sha == p.strict.stats.sha
    assert digest(p.strict.to_dict()) == before


def test_execution_rule_cannot_be_enabled_after_policy_freeze():
    p = provider()
    participant(p)
    p.spec['known_execution_rule'] = 'ATTEMPT_AT_FROZEN_START_THEN_UNAVOIDABLE_RESOURCE_WAIT_SAME_SITE'
    with pytest.raises(ValueError, match='RESEARCH60_FROZEN_POLICY_SHA_DRIFT'):
        p.require_frozen_policy()


def test_observed_profiler_separates_cold_baseline_and_warm_changed_rows(tmp_path):
    _, _, r, p, m = example(two_lines=True)
    result = profile_observed_decision(p,m,r,0,ReservationLedger({'A':8,'B':8}),output=tmp_path/'profile.json')
    cold,warm = result['rows']
    assert cold['action'] == warm['action']
    assert cold['baseline96_affine_calls'] == 96
    assert warm['baseline96_affine_calls'] == 0
    assert warm['baseline_cache_hits'] > 0
    assert result['Native_calls'] == result['AC_calls'] == 0


@pytest.mark.parametrize('field', ['voltage_constant','voltage_matrix','flow_p_constant','flow_p_matrix',
    'flow_q_constant','flow_q_matrix','current_constant','current_matrix','anchor','branch_limits',
    'controls','p_slope','cos','sin','ap','correction','bias'])
def test_baseline_cache_detects_numeric_arrays_even_if_declared_sha_unchanged(field):
    _, _, _, p, m = example(two_lines=True)
    baseline = np.zeros((96,2))
    segments = [dict(resource='gpu:B',begin=0,end=900,quantity=1)]
    p._score(m,segments,0,baseline)
    before = grid_numeric_fingerprint(p.packet)
    if field in {'ap','correction','bias'}:
        array = getattr(p.packet,field)[4]
    elif field in {'controls','p_slope','cos','sin'}:
        array = getattr(p.packet,field)
    else:
        array = getattr(p.packet.coefficients[4],field)
    array.flat[0] += 1e-8
    assert grid_numeric_fingerprint(p.packet) != before
    p._score(m,segments,0,baseline)
    assert p.baseline_cache_misses == 2


def test_final_native_a_authority_does_not_accept_an_old_or_unreplayed_point():
    _, _, _, p, _ = example()
    a = SimpleNamespace(case_sha='CURRENT_NATIVE',stage='A1',arm='B1',data=({}, {'K':object()}))
    required = dict(selected_jobs={'K':{}},AIDC_P_by_site={},AIDC_Q_by_site={},CC4_service={},
        CC4_carryout={},anonymous_resource_envelope=[])
    distribution = dict(nominal_site_GPU={},reserve_site_GPU={},known_site_GPU={},resource_sites=[],
        CC4_reserve_service={},CC4_reserve_carryout={})
    result = dict(required,**distribution,FULL_feasible=True,aidc_anchor=digest(required),
        resource_distribution_sha=digest(distribution),case_sha=a.case_sha,stage=a.stage,arm=a.arm,
        FULL_point_replay={'PASS':True},Native_call=dict(label='A1_ORIGINAL_P1',solver='GUROBI',error=None,
            stage_context=dict(native_case_sha=a.case_sha,stage=a.stage,arm=a.arm,bindings=p.bindings)))
    assert require_final_a_authority(a,result,p.bindings) is result
    with pytest.raises(ValueError,match='FINAL_A_CURRENT_NATIVE_CASE_AUTHORITY_REQUIRED'):
        require_final_a_authority(a,dict(result,case_sha='OLD_NATIVE'),p.bindings)
    with pytest.raises(ValueError,match='FINAL_A_CURRENT_NATIVE_CASE_AUTHORITY_REQUIRED'):
        require_final_a_authority(a,dict(result,FULL_point_replay={'PASS':False}),p.bindings)
    tampered = deepcopy(result); tampered['Native_call']['stage_context']['bindings']['qos_sha'] = 'OLD_QOS'
    with pytest.raises(ValueError,match='FINAL_A_NATIVE_CALL_SHARED_BINDING_DRIFT:qos_sha'):
        require_final_a_authority(a,tampered,p.bindings)


@pytest.mark.parametrize('qos_class', ['urgent', 'high', 'protected', 'interactive'])
def test_protected_classes_do_not_receive_extra_delay(qos_class):
    p = provider()
    j, _ = participant(p)
    j = replace(j, uid='PROTECTED_'+qos_class, qos=qos_class)
    assert p.issue(j).budget_seconds == 0


def test_all_line_maximum_beats_largest_absolute_sensitivity():
    _, _, r, p, m = example(two_lines=True)
    d = p.select(m, r, 0, ReservationLedger({'A':8, 'B':8}), reserve=False)
    # A reduces the old critical line most, but makes line2=.9. B gives=.6.
    assert d['site'] == 'B' and d['start_seconds'] == 0
    assert d['tracking']['grid_peak'] == pytest.approx(.6)
    assert d['tracking']['checked_grid_slots'] == 96
    assert d['online_global_optimizer_calls'] == 0


def test_future_rebound_is_scored_across_all_remaining_slots():
    _, _, r, p, m = example(two_lines=True)
    c = p.packet.coefficients[4]
    c.current_constant += np.array([.89, 0])
    p.packet.bias[4] += np.array([.89, 0])
    d = p.select(m, r, 0, ReservationLedger({'A':8, 'B':8}), reserve=False)
    # The job covers the later congested slot, reducing that signed response.
    # A current-slot-only score would have chosen immediate B (.6).
    assert d['start_seconds'] == 3600
    assert d['tracking']['grid_peak'] == pytest.approx(.8)


def test_cached_all96_score_matches_original_scalar_rows_and_invalidates():
    _, _, _, p, m = example(two_lines=True)
    baseline = np.zeros((96, 2))
    segments = [dict(resource='gpu:B', begin=0, end=2700, quantity=1)]
    from v42_integration.trajectory_tracking import service_integral
    profile = service_integral(p.packet.sites, segments, p.reference.begin)
    scalar = [p.packet._at_slot(t, baseline[t]+profile[t]-p.reference.arrays['G_Total_Plan'][t])
        for t in range(96)]
    score, reason = p._score(m, segments, 0, baseline)
    assert reason is None
    assert score['grid_peak'] == max(r[0] for r in scalar)
    assert score['loading_hours'] == sum(r[0] for r in scalar)*.25
    p._score(m, segments, 0, baseline)
    assert (p.baseline_cache_misses, p.baseline_cache_hits) == (1, 1)
    baseline[95, 1] = 1
    p._score(m, segments, 0, baseline)
    assert p.baseline_cache_misses == 2
    p.packet.coefficients[0].coefficient_sha256 = 'f'*64
    p._score(m, segments, 0, baseline)
    assert p.baseline_cache_misses == 3
    p.observe(900, {'A':0, 'B':0}, {m['uid']:m})
    assert not p._baseline_grid_cache
    late, reason = p._score(m, segments, 900, baseline)
    expected = [p.packet._at_slot(t, baseline[t]+profile[t]-p.reference.arrays['G_Total_Plan'][t])
        for t in range(1,96)]
    assert reason is None and late['grid_peak'] == max(r[0] for r in expected)


def test_current_grid_uses_exact_original_c1_and_no_future_weather():
    _, _, _, p, m = example(two_lines=True)
    # C1: P=IT squared, so 1GPU produces1kW, 2GPU produces4kW;
    # a one-GPU planning secant cannot represent this exact current change.
    model = FrozenPowerModel(0., 1., {'A':8, 'B':8}, .95,
        lambda it, weather:np.asarray(it)**2, 'NAMED_NONLINEAR_C1_AUTHORITY')
    calls = []
    def current_weather(now):
        calls.append(now)
        assert now == p.current[0]
        return {'observed_clock':now}
    p.bind_observed_c1(model, current_weather_provider=current_weather)
    p.observe(0, {'A':0, 'B':1}, {m['uid']:m})
    delta = p._grid_delta(0, np.array([0, 2]), 0)
    cols = [p.packet.control_names.index('aidc_load_kw['+s+']') for s in p.packet.sites]
    expected_p = np.array([0., 4.])
    np.testing.assert_allclose(p.packet.controls[0,cols]+delta*p.packet.p_slope[0], expected_p)
    assert calls == [0]
    with pytest.raises(ValueError, match='ONLY_CURRENT_OBSERVED_WEATHER'):
        p._current_weather(900)


def test_real_c1_context_requires_source_authority_and_no_affine_fallback():
    _, _, _, p, m = example()
    p.evidence_scope = 'REAL_SOURCE_DIAGNOSTIC'
    p.spec['C1_source_sha'] = 'REAL_ORIGINAL_SOURCE_PIN'
    with pytest.raises(ValueError, match='REAL_EXACT_CURRENT_C1_CONTEXT_REQUIRED'):
        p.current_guard(m, [dict(resource='gpu:A', begin=0, end=900, quantity=1)], 0, {'A':0, 'B':0})
    wrong = FrozenPowerModel(0., 1., {'A':8, 'B':8}, .95,
        lambda it, weather:np.asarray(it), 'WRONG_SOURCE_PIN')
    with pytest.raises(ValueError, match='REAL_ORIGINAL_C1_SOURCE_SHA_DRIFT'):
        p.bind_observed_c1(wrong, current_weather_provider=lambda now:{})


def test_anonymous_residual_preserves_hour_site_cdf_carry_without_double_count():
    q50 = [2.]+[0.]*23
    unknown = np.zeros((96,2)); unknown[:4] = [1.,1.]
    known = np.zeros_like(unknown)
    identity = dict(CC4_Q50=q50, CC4_Q90=q50, CC4_service={str((0,t)):.5 for t in range(4)},
        CC4_carryout={str(h):0. for h in range(24)}, Timing_CDF_Q10=[0.]*100,
        Timing_CDF_Q90=[1.]*100, CC4_source_authority=dict(model_id='LGBM_weighted_c1_s20260924',
            prediction_sha='NAMED_FORECAST', kernel_sha='NAMED_KERNEL', timing_envelope_sha='NAMED_CDF',
            aidc_anchor='NAMED_AIDC_ANCHOR'))
    ref = TrackingReference(known, unknown, unknown, unknown, unknown,
        sites=('A','B'), begin=0, commands={}, identity=identity)
    observed_jobs = {'U':dict(origin_unknown=True, submit_seconds=0, gpu=1, t50_seconds=3600),
        'PREFIX':dict(origin_unknown=True, submit_seconds=-900, gpu=1, t50_seconds=3600)}
    residual, audit = anonymous_cohort_residual(ref, observed_jobs, 0)
    assert audit['status'] == 'SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS'
    assert audit['residual_nominal_GPUh'] == 1
    assert residual.sum()/4 == 1
    np.testing.assert_allclose(residual[:4], .5)
    assert audit['unique_Dday_observed_UIDs'] == ['U']
    assert audit['prefix_Unknown_UIDs_separate'] == ['PREFIX']
    assert ref.identity['CC4_service'] == identity['CC4_service']
    # The source cohort closes unsubmitted remainder into an explicit expiry
    # ledger; no unknown UID or fabricated service is added to physical GPU.
    late, closed = anonymous_cohort_residual(ref, observed_jobs, 3600)
    assert late.sum() == 0
    assert closed['cohort_rows'][0]['expired_unsubmitted_Q50_GPUh'] == 1
    assert closed['hard_occupancy'] is False


def test_unknown_cohort_authority_missing_never_promotes_forecast_safety():
    _, _, _, p, m = example()
    p.reference.arrays['G_Unknown_Q50_Plan'].setflags(write=True)
    p.reference.arrays['G_Unknown_Q50_Plan'][0,0] = 1
    _, audit = anonymous_cohort_residual(p.reference, {}, 0)
    assert audit['status'] == 'CONSERVATION_NOT_CERTIFIED'
    assert audit['safe_promotion_allowed'] is False


def test_carry_only_cohort_still_replays_and_preserves_residual_mass():
    z = np.zeros((96,2))
    q50 = [0.]*23+[2.]
    identity = dict(CC4_Q50=q50,CC4_Q90=q50,CC4_service={},CC4_carryout={'23':2.},
        Timing_CDF_Q10=[0.]*4,Timing_CDF_Q90=[1.]*4,
        CC4_source_authority=dict(model_id='LGBM_weighted_c1_s20260924',prediction_sha='P',kernel_sha='K',
            timing_envelope_sha='T',aidc_anchor='A',future_Actual_or_UID_inputs_used=False,forecast_modifications=0))
    ref = TrackingReference(z,z,z,z,z,sites=('A','B'),begin=0,commands={},identity=identity)
    residual,audit = anonymous_cohort_residual(ref,{},0)
    assert audit['status'] == 'SOURCE_COHORT_CDF_CARRY_CONSERVATION_PASS'
    assert residual.sum() == 0
    assert audit['residual_nominal_GPUh'] == audit['residual_carryout_GPUh'] == 2


def test_source_only_cc4_seed_pairs_preserve_reference_receipts_and_full_service(tmp_path):
    from v42_job_capability import Job,ServiceBoundary,Resources
    jobs = {u:Job(u,'PENDING',0,0,start,'A',3,1,initial_sites=('A',),duration_authority='NAMED_SERVICE')
        for u,start in (('FIRST',24),('SECOND',27))}
    bounds = {u:ServiceBoundary('NAMED',True,True,(j.reference_start,),123) for u,j in jobs.items()}
    resources = Resources({'A':2},{'A':(2,)},{},{},120,1,{('A',t):1 for t in range(24,30)},{},{})
    windows = {'FIRST':(24,25,26,27,28),'SECOND':(27,28,29,30,31)}
    docs = {u:dict(policy_id='NAMED60',budget_seconds=3600,participant=True,eligible_for_contract=True,
        reference_start_seconds=j.reference_start*900,hard_contract={},t50_seconds=2700,
        model_metadata=dict(batch_eligible=True,qos='normal',protected=False)) for u,j in jobs.items()}
    case = SimpleNamespace(arm='B1',stage='A1',case_sha='NAMED_CURRENT_CASE',
        data=({'C0_Q50':[.1]+[0.]*23},jobs,bounds,resources),qos_receipts=docs,window_slots=windows,
        grid=SimpleNamespace(timing_lower=np.array([0.,0.]+[1.]*94)))
    before = digest(docs)
    result = select_cc4_headroom_seed_choices(case,issue_seconds=0,pairs=1,output=tmp_path/'witness.json')
    assert result['selected_pairs'] == 1
    assert result['override_plans']['FIRST']['start'] == 28
    assert result['override_plans']['SECOND']['start'] == 30
    assert result['all_necessary_CDF_capacity_PASS']
    assert digest(docs) == before
    assert jobs['FIRST'].reference_start == 24 and jobs['SECOND'].reference_start == 27
    assert result['Full_grid_and_CDF'] == 'NOT_CHECKED'
    assert result['Native_calls'] == result['models_built'] == 0


def boundary_completed_fixture(tmp_path, *, completion=-100, origin_unknown=False):
    import json
    _, _, _, p, _ = example()
    payload = dict(begin_epoch_seconds=0,day_begin_epoch_seconds=0,MODEL_ASSUMPTION=True,
        historical_completed=[dict(job_uid='DONE',origin_unknown=origin_unknown,
            observed_completion_seconds=completion,observed_control_release_seconds=0)])
    initial_sha = digest(payload)
    source = dict(payload,common_initial_state_sha=initial_sha,initial_state_payload_keys=list(payload))
    path = tmp_path/'NAMED_CURRENT_BOUNDARY.json'; path.write_text(json.dumps(source),encoding='utf-8')
    from v42_integration.unified_contract import file_sha
    record = dict(path=str(path),sha256=file_sha(path),bytes=path.stat().st_size)
    p.bindings = dict(p.bindings,initial_state_sha=initial_sha)
    p.packet.bindings = p.bindings
    proof = build_boundary_completion_proof(record,bindings=p.bindings,begin_seconds=0,
        evidence_scope='NAMED_BOUNDARY_COMPLETION_FIXTURE')
    return p,proof


def test_boundary_completed_proof_cancels_ghost_runtime_bookings_without_command_change(tmp_path):
    p,proof = boundary_completed_fixture(tmp_path)
    _, _, _, template, _ = example()
    template.packet.bindings = p.bindings
    z=np.zeros((96,2)); commands={'DONE':dict(site='A',start_seconds=900,protected_segments=[
        dict(resource='gpu:A',begin=900,end=1800,quantity=8)])}
    ref=TrackingReference(z,z,z,z,z,sites=('A','B'),begin=0,commands=commands,identity={'evidence_scope':'NAMED_COMPLETION'})
    policy=SignedSensitivityPolicy(ref,template.packet,bindings=p.bindings,expected_bindings=p.bindings,
        evidence_scope='NAMED_BOUNDARY_COMPLETION_FIXTURE')
    task_provider=provider()
    assert policy.bindings['qos_sha']==task_provider.stats.sha
    assert policy.bindings['case_sha']==task_provider.case_sha
    proof=build_boundary_completion_proof(proof['source_file_record'],bindings=policy.bindings,begin_seconds=0,
        evidence_scope='NAMED_BOUNDARY_COMPLETION_FIXTURE')
    c=SensitivityRuntimeController({'A':8,'B':8},arm='B1',qos_window_provider=task_provider,
        frozen_policy=policy,known_schedule=commands,boundary_completion_proof=proof)
    assert 'DONE' not in c.reservations.known_plans
    assert c.known_schedule == commands
    assert len(c.boundary_completion_cancellations) == 1
    policy.observe(0,{'A':0,'B':0},{})
    future,_=policy._public_future(c.reservations,'UNKNOWN')
    assert future.sum() == 0
    with pytest.raises(ValueError,match='BOUNDARY_COMPLETED_KNOWN_UID_RESUBMITTED'):
        c.submit(request('DONE',origin_unknown=False),0)


def test_boundary_proof_rejects_wrong_file_sha_future_time_and_mixed_uid(tmp_path):
    p,proof=boundary_completed_fixture(tmp_path)
    bad=deepcopy(proof); bad['source_file_record']['sha256']='0'*64
    bad['proof_sha']=digest({k:v for k,v in bad.items() if k!='proof_sha'})
    with pytest.raises(ValueError,match='BOUNDARY_COMPLETION_SOURCE_FILE_SHA_DRIFT'):
        require_boundary_completion_proof(bad,bindings=p.bindings,begin_seconds=0)
    bad=deepcopy(proof); bad['rows'][0]['uid']='ANOTHER_UID'
    bad['proof_sha']=digest({k:v for k,v in bad.items() if k!='proof_sha'})
    with pytest.raises(ValueError,match='BOUNDARY_COMPLETION_EXACT_UID_OBSERVATION_DRIFT'):
        require_boundary_completion_proof(bad,bindings=p.bindings,begin_seconds=0)
    with pytest.raises(ValueError,match='BOUNDARY_COMPLETION_FUTURE_OR_NONCOMPLETED_OBSERVATION'):
        boundary_completed_fixture(tmp_path,completion=1)


@pytest.mark.parametrize('boundary_mode', ['IMPOSSIBLE','ULP_UNCERTAIN','TINY_NONZERO_RESCUE'])
def test_original_grid_outer_box_is_outward_and_never_deletes_tiny_coefficients(tmp_path,boundary_mode):
    _, _, _, p, _ = example()
    coefficients=deepcopy(p.packet.coefficients)
    lower=.94**2
    for c in coefficients:
        c.voltage_matrix[:]=0
        if boundary_mode=='IMPOSSIBLE':c.voltage_constant[:]=.8
        elif boundary_mode=='ULP_UNCERTAIN':c.voltage_constant[:]=np.nextafter(lower,-np.inf)
        else:
            c.voltage_constant[:]=lower-4e-10
            c.voltage_matrix[0,0]=1e-10
    hardware=SimpleNamespace(capacities={'A':8,'B':8},fixed_gpu={})
    grid=SimpleNamespace(coefficients=coefficients,idle_kw=0.,swing_kw=1.,
        power={(s,t):SimpleNamespace(slope=1.,intercept_kw=0.) for s in ('A','B') for t in range(96)},
        fixed_mess=dict(P_by_site={'M':[0.]*96},Q_by_site={'M':[0.]*96}),
        authority=SimpleNamespace(voltage_lower_squared=lower,voltage_upper_squared=1.06**2))
    case=SimpleNamespace(arm='B1',stage='A1',case_sha='NAMED_BOX',data=({}, {}, {},hardware),grid=grid)
    result=audit_seed_grid_outer_box(case,output=tmp_path/'box.json')
    if boundary_mode=='IMPOSSIBLE':
        assert result['status']=='PROVEN_INDIVIDUAL_ROW_CONFLICT'
        assert any(c['row_kind']=='voltage_lower' for c in result['conflicts'])
    else:assert result['status']=='NO_INDIVIDUAL_BOX_CONFLICT_JOINT_FEASIBILITY_NOT_CERTIFIED'
    assert result['models_built']==result['Native_calls']==0


def test_soft_running_predictions_do_not_become_hard_capacity():
    _, _, _, p, m = example()
    m2 = dict(m, uid='PEER', state='RUNNING', current_site='B', gpu=8, t50_seconds=7200,
        accumulated_compute_seconds=0)
    p.observe(0, {'A':0, 'B':8}, {m['uid']:m, 'PEER':m2})
    l = ReservationLedger({'A':8, 'B':8})
    l.retain_running('PEER', 'B', 0, 900, 8)
    baseline, _ = p._public_future(l, m['uid'])
    segments = [dict(resource='gpu:B', begin=900, end=1800, quantity=1)]
    assert l.feasible(segments) is None
    assert p.last_hard_profile[1, 1] == 0
    assert baseline[1, 1] == 8
    # A soft risk is reported; no PREDICTED_COMMITTED_GPU_CAPACITY veto exists.
    score, reason = p._score(m, segments, 0, baseline)
    assert reason is None
    assert score['soft_prediction_capacity_risk_GPUh'] > 0


def test_actual_committed_reservations_remain_hard_and_uid_union():
    _, _, r, p, m = example(two_lines=True)
    from v42_integration.reservation_state import ContractReservationLedger
    owner = SimpleNamespace(known_schedule={'K':dict(site='B', protected_segments=[
        dict(resource='gpu:B', begin=0, end=900, quantity=8)])}, metadata={})
    l = ContractReservationLedger(owner, capacities={'A':8, 'B':8})
    l.reserve('K', [dict(resource='gpu:B', begin=0, end=900, quantity=8)])
    future, known = p._public_future(l, m['uid'])
    assert future[0, 1] == known[0, 1] == 8
    d = p.select(m, r, 0, l, reserve=False)
    assert any(x['reason'] == 'NO_CAPACITY' for x in d['rejected_candidates'])
    assert d['action'] == 'QUEUE' or d['site'] != 'B' or d['start_seconds'] >= 900


def test_q50_overrun_has_no_zero_hold_completion_claim():
    d = conditional_remaining_runtime(dict(state='RUNNING', t50_seconds=900,
        accumulated_compute_seconds=1500, experimental_prediction_Q90_seconds=1200))
    assert d['public_remaining_Q50_seconds'] == 0
    assert d['running_hold_required']
    assert d['conditional_remaining_Q90_seconds'] is None
    assert d['conditional_provider_status'] == 'NOT_CERTIFIED'


def test_backfill_needs_source_bound_not_q90_before_confirmed_booking():
    l = ReservationLedger({'A':8})
    l.reserve('K', [dict(resource='gpu:A', begin=1800, end=3600, quantity=8)])
    m = dict(gpu=1, t50_seconds=900, experimental_prediction_Q90_seconds=1000)
    assert safe_backfill(m, now=0, site='A', reservations=l, uid='U')[0] is False
    m.update(source_runtime_upper_bound_seconds=1800,
        runtime_upper_bound_authority={'source_sha':'SOURCE_BOUND', 'observed_at_seconds':0})
    assert safe_backfill(m, now=0, site='A', reservations=l, uid='U',
        evidence_scope='NAMED_SYNTHETIC_UPPER_BOUND_FIXTURE')[0] is True
    m['source_runtime_upper_bound_seconds'] = 1801
    assert safe_backfill(m, now=0, site='A', reservations=l, uid='U')[0] is False


def test_fake_public_bound_authority_cannot_enable_real_backfill():
    l = ReservationLedger({'A':8})
    l.reserve('K', [dict(resource='gpu:A', begin=1800, end=3600, quantity=8)])
    fake = dict(gpu=1, source_runtime_upper_bound_seconds=900,
        runtime_upper_bound_authority={'source_sha':'ATTACKER_CHOSEN_SHA', 'observed_at_seconds':0})
    ok, reason = safe_backfill(fake, now=0, site='A', reservations=l, uid='U')
    assert not ok and reason == 'VALIDATED_NONPREEMPTIVE_RUNTIME_BOUND_PROVIDER_NOT_AVAILABLE'
    no_booking = ReservationLedger({'A':8})
    assert safe_backfill(fake, now=0, site='A', reservations=no_booking, uid='U') == (True, 'NO_FUTURE_COMMITTED_BOOKING')


def test_past_known_command_is_not_moved_and_running_truth_kept():
    p, _, _, policy, _ = example()
    policy.reference._commands = {'K':dict(site='A', start_seconds=-900)}
    policy.reference.sha = policy.reference._digest()
    policy.spec['reference_target_sha'] = policy.reference.sha
    policy.sha = digest(policy.spec)
    c = SensitivityRuntimeController({'A':8, 'B':8}, arm='B1', qos_window_provider=p,
        frozen_policy=policy, known_schedule=policy.reference.commands)
    c.submit(request('K', origin_unknown=False, qos='normal', protected=False), 0)
    assert c._known_decision('K', 0)['action'] == 'QUEUE'
    assert c.known_schedule['K']['start_seconds'] == -900
    f = dict(pending=[dict(uid='K', origin_unknown=False, observed_start_seconds=None)],
        running=[dict(uid='R', origin_unknown=False, observed_start_seconds=-1200, site='A')])
    result = known_initial_reconciliation({'K':dict(site='A', start_seconds=-900),
        'R':dict(site='B', start_seconds=-1800)}, f, issue_seconds=-21600, begin_seconds=0)
    assert result['status'] == 'NOT_CERTIFIED'
    assert result['counts']['PAST_START_NOT_OBSERVED_EXECUTED_BLOCKED'] == 1
    assert result['counts']['OBSERVED_RUNNING_PLAN_MISMATCH_PRESERVE_OCCUPANCY'] == 1


def test_issue_only_bridge_does_not_consume_future_boundary():
    result = known_planning_bridge({'P':dict(state='PENDING'), 'R':dict(state='RUNNING')},
        issue_seconds=-21600, begin_seconds=0)
    assert result['rows']['P']['earliest_new_pending_command_seconds'] == 0
    assert result['future_Dday_snapshot_consumed'] is False
    assert result['new_A1_certified'] is False


def test_policy_roundtrip_and_binding_drift_fail_closed(tmp_path):
    _, _, r, p, m = example(two_lines=True)
    path = tmp_path/'policy.json'
    p.save(path)
    restored = SignedSensitivityPolicy.load(path, bindings=p.bindings)
    restored.bind_runtime_packet(p.packet)
    restored.observe(0, {'A':0, 'B':0}, {m['uid']:m})
    one = p.select(m, r, 0, ReservationLedger({'A':8, 'B':8}), reserve=False)
    two = restored.select(m, r, 0, ReservationLedger({'A':8, 'B':8}), reserve=False)
    assert (one['site'], one['start_seconds'], p.sha) == (two['site'], two['start_seconds'], restored.sha)
    with pytest.raises(ValueError, match='ANCHOR_DRIFT'):
        SignedSensitivityPolicy.load(path, bindings=dict(p.bindings, cc4_sha='a'*64))


@pytest.mark.parametrize('field', ['future_unknown_uids', 'actual_duration_seconds', 'completion_time'])
def test_future_runtime_private_fields_rejected(field):
    _, _, r, p, m = example()
    with pytest.raises(ValueError):
        p.select(dict(m, **{field:123}), r, 0, ReservationLedger({'A':8, 'B':8}))


def test_migration_funnel_running_checkpoint_authority_and_limit():
    _, _, r, p, m = example()
    l = ReservationLedger({'A':8, 'B':8}, wan_capacities={'AB':100})
    m.update(state='RUNNING', current_site='A', accumulated_compute_seconds=1800,
        t50_seconds=5400, Can_Checkpoint_Migrate=True, migration_count=1, migration_capability=capability())
    p.observe(1800, {'A':1, 'B':0}, {m['uid']:m})
    d = p.select_migration(m, r, 1800, l, checkpoint_at=1800)
    assert d['action'] == 'STAY' and d['reason'] == 'MAXIMUM_ONE_MIGRATION'
    assert p.funnel[-1]['RUNNING'] and p.funnel[-1]['CHECKPOINT']


def test_feasible_migration_is_considered_when_stay_is_infeasible():
    _, _, r, p, m = example()
    c = p.packet.coefficients[3]
    c.current_constant += np.array([.7, 0])
    p.packet.bias[3] += np.array([.7, 0])
    m.update(state='RUNNING', current_site='A', accumulated_compute_seconds=1800,
        t50_seconds=5400, Can_Checkpoint_Migrate=True, migration_count=0, migration_capability=capability())
    p.observe(1800, {'A':1, 'B':0}, {m['uid']:m})
    l = ReservationLedger({'A':8, 'B':8}, wan_capacities={'AB':100})
    l.retain_running(m['uid'], 'A', 1800, 2700, 1)
    d = p.select_migration(m, r, 1800, l, checkpoint_at=1800, reserve=False)
    assert d['action'] == 'CHECKPOINT_MIGRATE'
    assert p.funnel[-1]['reason'] == 'FEASIBLE_MIGRATION_REPLACES_INFEASIBLE_STAY'
    assert d['tracking']['Fresh_AC_PASS_claimed'] is False


def test_native0_actual_preserves_overrun_and_recalculates_exact_c1():
    p, j, _, policy, _ = example(two_lines=True)
    u = request(j.uid, q50=900, qos='UNCONFIRMED', protected=None, batch_eligible=None,
        partition='', requested_walltime_seconds=None, representation_starts_seconds=tuple(range(0,86400,900)))
    power = FrozenPowerModel(.1, 1., {'A':8, 'B':8}, .95, lambda it, weather:np.asarray(it), 'NAMED_TOY_C1')
    out = run_actual({'A':8, 'B':8}, [u], Environment({u.uid:2000}), arm='B1',
        qos_window_provider=p, frozen_policy=policy, controller_class=SensitivityRuntimeController,
        begin=0, end=3600, expected_bindings=policy.bindings, power_model=power, weather=[{}]*4)
    np.testing.assert_allclose(out['physical']['IT_kw'], .8+out['occupancy_GPU'])
    audit = out['carryout']['controller']['runtime_repair_state']['runtime']
    assert any(r['event'] == 'OVERRUN_RUNNING_HOLD' and r['running_gpu_protected'] for r in audit)
    assert out['receipt']['actual_power_recomputed']


def test_real_coordinator_rejects_past_known_before_execution():
    _, _, _, p, _ = example()
    p.evidence_scope = 'REAL_DIAGNOSTIC'
    p.reference._commands = {'K':dict(site='A', start_seconds=-900)}
    p.reference.sha = p.reference._digest()
    p.spec['reference_target_sha'] = p.reference.sha
    p.sha = digest(p.spec)
    with pytest.raises(ValueError, match='KNOWN_BOUNDARY_RECONCILIATION_REQUIRED:1'):
        coordinator_actual_runner(frozen_policy=p, expected_bindings=p.bindings,
            requests=[request('K', origin_unknown=False)], running=[], begin=0,
            known_schedule={'K':dict(site='A', start_seconds=-900)})


def test_latest_common_contract_files_are_byte_frozen():
    assert load_contracts()['new_science_differs_from_30min']


def test_cached_known_command_never_executes_after_its_frozen_tick():
    p, _, _, policy, _ = example()
    commands = {'K':dict(site='A', start_seconds=900)}
    policy.reference._commands = commands
    policy.reference.sha = policy.reference._digest()
    policy.spec['reference_target_sha'] = policy.reference.sha
    policy.sha = digest(policy.spec)
    c = SensitivityRuntimeController({'A':8, 'B':8}, arm='B1', qos_window_provider=p,
        frozen_policy=policy, known_schedule=commands)
    c.submit(request('K', origin_unknown=False, q50=900, qos='normal', protected=False), 0)
    c.decisions['K'] = dict(uid='K', action='START', site='A', start_seconds=900,
        nominal_end_seconds=1800, additional_start_delay_seconds=0)
    c.admit(2700)
    assert c.ledger.jobs['K']['latest_observed_state'] == 'PENDING'
    assert c.decisions['K']['action'] == 'QUEUE'
    assert c.known_schedule == commands
    assert any(e.get('reason') == 'KNOWN_MISSED_FROZEN_COMMAND' for e in c.events)


@pytest.mark.parametrize('intervening_grid_veto', [False, True])
def test_opt_in_known_capacity_wait_executes_same_frozen_site_after_overrun(intervening_grid_veto):
    base, _, _, old, _ = example()
    spec = dict(base.spec, known_execution_rule='ATTEMPT_AT_FROZEN_START_THEN_UNAVOIDABLE_RESOURCE_WAIT_SAME_SITE')
    p = Research60QoSProvider(base.strict, case_sha=base.case_sha, frozen_spec=spec)
    job, _ = participant(base)
    uid = job.uid
    packet = old.packet
    packet.bindings = dict(packet.bindings, qos_sha=p.stats.sha)
    for t, coefficient in enumerate(packet.coefficients):
        coefficient.current_matrix[:] = 0
        coefficient.current_constant[:] = .1
        packet.correction[t][:] = 0
        packet.bias[t][:] = .1
    commands = {uid:dict(site='A', start_seconds=900)}
    z = np.zeros((96,2))
    ref = TrackingReference(z,z,z,z,z, sites=packet.sites, begin=0, commands=commands,
        identity={'evidence_scope':'NAMED_KNOWN_RESOURCE_WAIT_WITNESS'})
    policy = SignedSensitivityPolicy(ref, packet, bindings=packet.bindings,
        expected_bindings=packet.bindings, evidence_scope='NAMED_KNOWN_RESOURCE_WAIT_WITNESS')
    if intervening_grid_veto:
        original_guard = policy.current_guard
        policy.current_guard = lambda meta, segments, now, use: (
            'PREDICTED_ORIGINAL_PLANNING_VOLTAGE' if now == 2700 else original_guard(meta, segments, now, use))
    k = request(uid, origin_unknown=False, q50=900, qos='UNCONFIRMED', protected=None,
        batch_eligible=None, partition='', requested_walltime_seconds=None,
        reference_start_seconds=0,
        representation_starts_seconds=tuple(range(0,86400,900)))
    hold = request('OBSERVED_RUNNING', gpu=8, q50=900, compatible=('A',), source_site='A',
        protected=True, origin_unknown=True)
    result = run_actual({'A':8, 'B':8}, [k], Environment({uid:900}, {'OBSERVED_RUNNING':2000}),
        running=[(hold,'A',0)], begin=0, end=4500, arm='B1', qos_window_provider=p,
        frozen_policy=policy, controller_class=SensitivityRuntimeController,
        known_schedule=commands, expected_bindings=policy.bindings)
    known = next(r for r in result['queue_ledger'] if r['job_uid'] == uid)
    if intervening_grid_veto:
        assert known['admitted_time'] is None
        state = result['carryout']['controller']['known_frozen_execution_state']
        assert uid not in state['observed_resource_wait_UIDs']
        assert state['invalidated_resource_wait_permissions'][uid]['time_seconds'] == 2700
        assert result['carryout']['controller']['tracking_state']['Known_schedule_sha'] == digest(commands)
        return
    assert known['admitted_time'] == 2700
    assert known['plan_start_seconds'] == 900
    assert known['site'] == 'A'
    assert known['intentional_delay_seconds'] == 900
    assert known['unavoidable_queue_seconds'] == 1800
    assert known['unavoidable_resource_wait_seconds'] == 1800
    state = result['carryout']['controller']['known_frozen_execution_state']
    assert state['start_attempt_receipts'][uid]['planned_start_seconds'] == 900
    assert uid in state['observed_resource_wait_UIDs']
    assert result['carryout']['controller']['tracking_state']['Known_schedule_sha'] == digest(commands)
    assert any(e.get('event') == 'KNOWN_OBSERVED_RESOURCE_WAIT' for e in result['job_event_ledger'])


def test_serialized_reference_cannot_be_swapped_with_unchanged_policy_sha(tmp_path):
    import json
    _, _, _, p, _ = example()
    path = tmp_path/'policy.json'
    p.save(path)
    d = json.loads(path.read_text())
    d['reference']['commands'] = {'INJECTED':dict(site='A', start_seconds=0)}
    a = d['reference']['arrays']
    r = TrackingReference(a['G_Known_Plan'], a['G_Unknown_Q50_Plan'], a['IT_Plan'],
        a['PCC_P_Plan'], a['PCC_Q_Plan'], sites=d['reference']['sites'], begin=d['reference']['begin'],
        commands=d['reference']['commands'], identity=d['reference']['identity'])
    d['reference']['target_sha'] = r.sha
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match='REFERENCE_OR_MIGRATION_AUTHORITY_DRIFT'):
        SignedSensitivityPolicy.load(path, bindings=p.bindings)


@dataclass
class NativeIssueFixture:
    uid: str = 'K'
    state: str = 'PENDING'
    reference_start: int = 0
    reference_site: str = 'A'
    initial_sites: tuple = ('A', 'B')
    service_slots: int = 1


def binding_fixture(*, reference_start=0, future_record=False, hard_latest=None):
    strict = qos()
    spec = dict(schema='NAMED_BINDER_FIXTURE', source_training_sha=strict.stats.sha,
        participation='FLEX30', max_start_delay_seconds=3600,
        customer_SLA_claim=False, reissue_on_retry=False)
    bindings = {k:digest('BINDER_FIXTURE:'+k) for k in BINDING_FIELDS}
    bindings['qos_sha'] = digest(spec)
    bindings['aidc_anchor'] = digest('SOURCE_A')
    bindings['mess_anchor'] = digest('SOURCE_M')
    job = replace(observed('K'), submit_seconds=-21600, event_seconds=-21600,
        reference_start_seconds=reference_start, origin_unknown=future_record,
        hard_latest_start_seconds=hard_latest,
        representation_starts_seconds=tuple(range(-21600,86400,900)))
    calls = []
    class FutureBankMustNotBeRead:
        def __iter__(self):
            raise AssertionError('Future Actual request bank accessed during Planning bind')
    def original_a(arm, stage, mess, output):
        calls.append((stage, mess['plan_sha']))
        native = NativeIssueFixture()
        return SimpleNamespace(data=({}, {'K':native}, {'K':SimpleNamespace(latest_completion=121)}, SimpleNamespace(
            capacities={'A':8, 'B':8}, rack_limits={'A':(8,), 'B':(8,)}, control_end=120, fixed_gpu={})),
            grid=SimpleNamespace(), case_sha='ORIGINAL_A', qos_receipts={}, window_slots={})
    def original_m(arm, stage, aidc, output):
        calls.append((stage, aidc['aidc_anchor']))
        return SimpleNamespace(identity={'aidc_anchor':aidc['aidc_anchor']}, case_sha='ORIGINAL_M')
    case = SimpleNamespace(_consumed=False, planning_slot_zero_seconds=-21600,
        qos_provider=strict, make_a_case=original_a, make_m_case=original_m,
        actual_arguments=FutureBankMustNotBeRead(), reference_aidc={'aidc_anchor':bindings['aidc_anchor']},
        initial_mess={'plan_sha':bindings['mess_anchor']}, evidence_kind='NAMED_FIXTURE')
    return case, {'K':job}, dict(bindings=bindings, qos_contract=spec), calls


def test_issue_binder_connects_original_a1_m1_a2_m2_domains_without_actual_read():
    case, jobs, shared, calls = binding_fixture()
    bound = bind_unified_planning(case, jobs, shared)
    a1 = bound.make_a_case('B3', 'A1', bound.initial_mess, None)
    m1_a = {'aidc_anchor':digest('A1_RESULT')}
    m1 = bound.make_m_case('B3', 'M1', m1_a, None)
    m1_plan = {'plan_sha':digest('M1_RESULT')}
    a2 = bound.make_a_case('B3', 'A2', m1_plan, None)
    m2_a = {'aidc_anchor':digest('A2_RESULT')}
    m2 = bound.make_m_case('B3', 'M2', m2_a, None)
    assert calls[1:] == [('A1', bound.initial_mess['plan_sha']), ('M1', m1_a['aidc_anchor']),
        ('A2', m1_plan['plan_sha']), ('M2', m2_a['aidc_anchor'])]
    assert a1.window_slots['K'] and all(slot >= 24 for slot in a1.window_slots['K'])
    assert a1.qos_receipts['K'] is bound.qos_provider.receipts['K']
    assert a1.case_sha != a2.case_sha
    assert m1.identity['qos_sha'] == m2.identity['qos_sha'] == shared['bindings']['qos_sha']
    assert bound.unified_actual_runner is coordinator_actual_runner
    assert bound.research_contract_binding['boundary_bridge']['future_Actual_bank_read_at_binding'] is False


def test_issue_binder_original_hard_deadline_is_preserved_and_fails_closed():
    case, jobs, shared, _ = binding_fixture(reference_start=-9000, hard_latest=-3600)
    bound = bind_unified_planning(case, jobs, shared)
    original_receipt = bound.qos_provider.receipts['K']
    with pytest.raises(ValueError, match='EMPTY_POST_DDAY_AUTHORIZED_KNOWN_DOMAIN:1'):
        bound.make_a_case('B3', 'A1', bound.initial_mess, None)
    domain = bound.research_contract_binding['boundary_bridge']['stage_domains']['A1']
    assert domain['empty_post_Dday_authorized_UIDs'] == ['K']
    assert original_receipt.reference_start_seconds == 0
    assert original_receipt.hard_contract['hard_latest_start_seconds'] == -3600
    assert domain['budgets_extended'] is False


def test_new_issue_reference_replaces_old_expired_baseline_without_moving_commands():
    case, jobs, shared, _ = binding_fixture(reference_start=-9000)
    old_authority = jobs['K'].authority_sha
    bound = bind_unified_planning(case, jobs, shared)
    a = bound.make_a_case('B3', 'A1', bound.initial_mess, None)
    assert a.window_slots['K'][0] == 24
    assert a.data[1]['K'].reference_start == 24
    audit = bound.research_contract_binding['boundary_bridge']['new_issue_only_Dday_reference']
    assert audit['original_references']['K']['reference_start_seconds'] == -9000
    assert audit['original_references']['K']['authority_sha'] == old_authority
    assert jobs['K'].reference_start_seconds == -9000


def test_new_issue_reference_known_command_actually_starts_in_actual():
    from dataclasses import asdict
    case, jobs, shared, _ = binding_fixture(reference_start=-9000)
    raw = asdict(jobs['K'])
    raw.update(common_initial_state_sha='NAMED_FIXTURE_INITIAL', dday_initialization_seconds=0)
    u = request('K', submit=-21600, q50=900, origin_unknown=False, qos='UNCONFIRMED',
        protected=None, batch_eligible=None, partition='', requested_walltime_seconds=None,
        representation_starts_seconds=jobs['K'].representation_starts_seconds)
    u = replace(u, metadata=raw)
    case.actual_arguments = dict(capacities={'A':8, 'B':8}, requests=[u], running=[],
        environment=Environment({'K':900}), begin=0, end=3600)
    bound = bind_unified_planning(case, jobs, shared)
    a = bound.make_a_case('B1', 'A1', bound.initial_mess, None)
    new_start = bound.qos_provider.receipts['K'].reference_start_seconds
    assert new_start == 0 and a.data[1]['K'].reference_start == 24
    args, _ = bound.prepare_research_actual_arguments()
    _, _, _, old_policy, _ = example(two_lines=True)
    commands = {'K':dict(site=a.data[1]['K'].reference_site, start_seconds=new_start)}
    z = np.zeros((96,2))
    ref = TrackingReference(z,z,z,z,z, sites=('A','B'), begin=0, commands=commands,
        identity={'evidence_scope':'NAMED_NEW_KNOWN_START_WITNESS'})
    packet = old_policy.packet
    packet.bindings = bound.unified_bindings
    p = SignedSensitivityPolicy(ref, packet, bindings=bound.unified_bindings,
        expected_bindings=bound.unified_bindings, evidence_scope='NAMED_NEW_KNOWN_START_WITNESS')
    out = coordinator_actual_runner(**args, arm='B1', qos_window_provider=bound.qos_provider,
        frozen_policy=p, known_schedule=commands, expected_bindings=p.bindings)
    known = next(row for row in out['queue_ledger'] if row['job_uid'] == 'K')
    assert known['admitted_time'] == 0
    assert known['policy_action'] == 'START'
    assert out['occupancy_GPU'][0,0] == 1
    assert not any(r.get('event') == 'KNOWN_COMMAND_EXECUTION_FAILED' for r in out['job_event_ledger'])
    assert jobs['K'].reference_start_seconds == -9000


def test_issue_binder_rejects_future_unknown_uid():
    case, jobs, shared, _ = binding_fixture(future_record=True)
    with pytest.raises(ValueError, match='ISSUE_ONLY_KNOWN_RECORDS_REQUIRED'):
        bind_unified_planning(case, jobs, shared)


def test_b1_prefix_requires_frozen_full_a1_before_reading_actual():
    case, jobs, shared, _ = binding_fixture()
    bound = bind_unified_planning(case, jobs, shared)
    with pytest.raises(ValueError, match='FINAL_B1_A1_FULL_FEASIBILITY_REQUIRED_BEFORE_ACTUAL'):
        run_b1_prefix_canary(bound, {'FULL_feasible':False})
    with pytest.raises(ValueError, match='EXPLICIT_PARTIAL_B1_PREFIX_REQUIRED'):
        run_b1_prefix_canary(bound, {'FULL_feasible':True}, slots=96)


def test_b1_prefix_executes_same_frozen_known_for_three_variants(tmp_path, monkeypatch):
    from dataclasses import asdict
    case, jobs, shared, _ = binding_fixture(reference_start=-9000)
    raw = asdict(jobs['K']); raw.update(common_initial_state_sha='NAMED_FIXTURE_INITIAL', dday_initialization_seconds=0)
    k = request('K', submit=-21600, q50=900, origin_unknown=False, qos='UNCONFIRMED', protected=None,
        batch_eligible=None, partition='', requested_walltime_seconds=None,
        representation_starts_seconds=jobs['K'].representation_starts_seconds)
    case.actual_arguments = dict(capacities={'A':8,'B':8}, requests=[replace(k,metadata=raw)], running=[],
        environment=Environment({'K':900}), begin=0, end=3600)
    bound = bind_unified_planning(case,jobs,shared)
    bound.make_a_case('B1','A1',bound.initial_mess,None)
    bound.initial_mess.update(P_by_site={'A':[0]*96,'B':[0]*96}, Q_by_site={'A':[0]*96,'B':[0]*96})
    monkeypatch.setattr('v42_integration.mess_actual.consume_frozen_mess', lambda *a, **kw:dict(frozen_execution_validated=True))
    _, _, _, template, _ = example(two_lines=True)
    commands = {'K':dict(site='A',start_seconds=0)}
    z = np.zeros((96,2))
    ref = TrackingReference(z,z,z,z,z,sites=('A','B'),begin=0,commands=commands,
        identity={'evidence_scope':'NAMED_PREFIX_KNOWN_WITNESS'})
    def frozen_factory(**kw):
        packet = deepcopy(template.packet); packet.bindings = kw['bindings']
        return SignedSensitivityPolicy(ref,packet,bindings=kw['bindings'],expected_bindings=kw['bindings'],
            evidence_scope='NAMED_PREFIX_KNOWN_WITNESS')
    bound.control_policy_factory = frozen_factory
    result = run_b1_prefix_canary(bound, {'FULL_feasible':True,'aidc_anchor':digest('FROZEN_A1')},slots=4,output=tmp_path)
    assert len(result['receipt']['variants']) == 3
    assert len({r['same_input_sha'] for r in result['receipt']['variants']}) == 1
    for row in result['receipt']['variants']:
        assert row['admitted_Known_UIDs'] == 1
        assert row['capacity_PASS'] and row['original_intentional_QoS_PASS']
        assert row['Known_schedule_sha'] == digest(commands)
        assert row['executed_frozen_policy_sha']
        assert row['frozen_policy_file_sha']
        assert (tmp_path/(row['variant']+'_FROZEN_POLICY.json')).exists()
    assert result['receipt']['Full96'] == 'NOT_RUN'
    assert result['receipt']['full96_release_eligible'] is False
