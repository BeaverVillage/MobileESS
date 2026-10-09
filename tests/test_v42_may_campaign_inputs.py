from copy import deepcopy
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest
from v42_final.common import MODEL
from v42_capacity.reference import build_reference
from v42_capacity.queue import allocate
from v42_modelable.power import known_occupancy
from v42_may_campaign.common import digest
from v42_may_campaign.input_checks import validate_independent_aidc, RULE


@pytest.fixture
def source_case():
    issue = datetime(2025, 4, 30, 18, tzinfo=timezone(timedelta(hours=10)))
    sites = [f'S{i:02}' for i in range(12)]
    def job(uid, state, gpu, seconds, *, site=None, elapsed=0., age=1):
        remaining = seconds if state == 'PENDING' else max(seconds-elapsed, 0.)
        return dict(job_uid=uid, submit_time=(issue-timedelta(hours=age)).isoformat(),
            state_at_D1_cutoff=state, GPU_gang=gpu, service_slots=int(np.ceil(remaining/900)),
            Q50_total_seconds=float(seconds), elapsed_seconds=float(elapsed), nominal_remaining_seconds=float(remaining),
            runtime_authority=MODEL, source_site=site, source_site_authority='OBSERVED' if site else None,
            runtime_inference_event_time=issue.isoformat(), source_member='immutable.zip', source_row=uid,
            compatible_sites=sites, reference_site=None, reference_start=None,
            deadline_metadata='PRESERVE_EXISTING_METADATA')
    jobs = [job('r1', 'RUNNING', 8, 36000, site='S00'),
            job('r2', 'RUNNING', 8, 1, site='S01', elapsed=10),
            job('p1', 'PENDING', 8, 900, site='S00', age=4),
            job('p2', 'PENDING', 4, 900, site='S00', age=3),
            job('p3', 'PENDING', 4, 900, site='S01', age=2),
            job('p4', 'PENDING', 2, 450, age=1)]
    caps = {s:8 for s in sites}; racks = {s:[8] for s in sites}
    cc = dict(target_day='2025-05-01', issue_time=issue.isoformat(), future_job_ids=[],
              nominal_unknown_GPU_96=[100.]*96, Q50_GPUh=[100.]*24, Q90_GPUh=[120.]*24,
              full_tail_nominal_GPUh=0.)
    p = dict(day='2025-05-01', issue_time=issue.isoformat(), slots=96, slot_seconds=900,
             known_population=jobs, capacities=caps, rack_compatibility=racks,
             future_actual_arrival_IDs_present=False, forecast_inputs={'current_CC4':cc})
    rows, audit = build_reference(jobs, caps, racks, issue_time=p['issue_time'])
    assert audit['full_reference_ready']
    selected = {r['job_uid']:r for r in rows}
    known = known_occupancy(rows, sites)
    anon, incoming, outgoing = allocate(known, cc['nominal_unknown_GPU_96'], [8]*12)
    total = known+anon
    coeff = pd.DataFrame([dict(slot=t, aidc_id=s, slope=1.1+t/1000, intercept_kw=2.+i)
                          for t in range(96) for i,s in enumerate(sites)])
    power = dict(current_IT_idle_kW_per_installed_GPU=.5, current_IT_swing_kW_per_active_GPU=1.4)
    it = .5*np.array([8]*12)+1.4*total
    slopes = coeff.pivot(index='slot', columns='aidc_id', values='slope')[sites].to_numpy()
    intercepts = coeff.pivot(index='slot', columns='aidc_id', values='intercept_kw')[sites].to_numpy()
    pcc = slopes*it+intercepts
    planning = dict(sites=np.array(sites), capacities=np.array([8]*12), known_gpu=known,
                    cc4_served_gpu=anon, GPU=total, IT_kw=it, PCC_P_kw=pcc,
                    PCC_Q_kvar=pcc*np.tan(np.arccos(.95)))
    identity = dict(day=p['day'], arm='B2', rule=RULE, jobs=len(rows), reference_SHA=digest(rows),
                    job_ids_SHA=digest(sorted(selected)), time_axis=list(range(96)), sites=sites,
                    AIDC_optimization_calls=0, MESS_optimizer_calls=0, B0_B1_schedule_result_reads=0)
    bundle = dict(day=p['day'], issue_time=p['issue_time'], known_population=jobs,
                  C0_Q50=cc['Q50_GPUh'], C0_Q90=cc['Q90_GPUh'])
    return p, planning, selected, coeff, power, identity, bundle


def verify(case):
    return validate_independent_aidc(*case)


def test_original_reference_independently_verified_without_producer_calls(source_case, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError('Producer must not be called by independent checker')
    monkeypatch.setattr('v42_capacity.reference.build_reference', forbidden)
    monkeypatch.setattr('v42_capacity.queue.allocate', forbidden)
    monkeypatch.setattr('v42_modelable.power.known_occupancy', forbidden)
    receipt = verify(source_case)
    assert receipt['PASS'] and receipt['Native_calls'] == receipt['producer_calls'] == 0
    assert receipt['jobs'] == 6 and receipt['original_reference']['q50_expired_RUNNING'] == 1
    assert receipt['original_reference']['issue_physical_GPU']['S01'] == 8
    assert receipt['original_reference']['deadline_metadata_fields_preserved'] == 6
    assert receipt['issue_relative_day_offset_slots'] == 24
    assert receipt['CC4_capacity_backlog_carryout_GPU'] > 0


def test_actual_waiting_order_no_backfill(source_case):
    p, planning, rows, *rest = source_case
    assert rows['p1']['reference_start'] == 40
    assert rows['p2']['reference_start'] == rows['p3']['reference_start'] == 41
    rows['p3']['reference_start'] = 0
    with pytest.raises(ValueError, match='STRICT_FCFS_NO_BACKFILL'):
        verify(source_case)


def test_delaying_gang_is_not_original_fcfs(source_case):
    source_case[2]['p1']['reference_start'] = 41
    with pytest.raises(ValueError, match='CAUSAL_RELEASE_START|EARLIEST_FCFS_START'):
        verify(source_case)


def test_q50_expired_running_keeps_issue_placement_capacity(source_case):
    p, planning, rows, *rest = source_case
    extra = deepcopy(p['known_population'][1]); extra['job_uid'] = 'r3'; extra['source_row'] = 'r3'
    p['known_population'].append(extra)
    row = dict(rows['r2'], job_uid='r3', job_id='r3', source_row='r3')
    rows['r3'] = row
    with pytest.raises(ValueError, match='RUNNING_ISSUE_CAPACITY_AND_PRIORITY'):
        verify(source_case)


@pytest.mark.parametrize('mutation,label', [
    ('future_submission','D1_CAUSAL_SUBMISSION'), ('future_outcome','FUTURE_OR_GRID_ROW'),
    ('gpu_changed','IMMUTABLE_RAW_ROW'), ('deadline_changed','IMMUTABLE_RAW_ROW'),
    ('service_changed','Q50_REMAINING_SERVICE'), ('drop','NO_WORKLOAD_DROP'),
    ('site_priority','FCFS_CAPACITY_AND_ASCENDING_SITE'), ('expired_hard','RUNNING_NOT_SYNTHETICALLY_COMPLETED'),
    ('issue_zone','FIXED_AEST_ISSUE_TO_DAY_24_SLOTS'), ('native_forecast','NATIVE_SAME_CC4_FORECAST'),
    ('identity','GENERATED_IDENTITY_BOUND_TO_ACTUAL_REFERENCE'), ('cc4_future','CAUSAL_CC4_AXIS')])
def test_original_input_and_actual_assignment_mutations_rejected(source_case, mutation, label):
    p, planning, rows, coeff, power, identity, bundle = source_case
    if mutation == 'future_submission':
        p['known_population'][0]['submit_time'] = '2025-04-30T19:00:00+10:00'
    elif mutation == 'future_outcome': p['known_population'][0]['actual_runtime'] = 1
    elif mutation == 'gpu_changed': rows['p1']['GPU_gang'] = 7
    elif mutation == 'deadline_changed': rows['p1']['deadline_metadata'] = 'NEW_POLICY'
    elif mutation == 'service_changed':
        p['known_population'][2]['service_slots'] = 2; rows['p1']['service_slots'] = 2
    elif mutation == 'drop': del rows['p1']
    elif mutation == 'site_priority':
        rows['p4']['reference_site'] = rows['p4']['planning_site'] = 'S02'
    elif mutation == 'expired_hard': rows['r2']['q50_expired_hard_occupancy'] = True
    elif mutation == 'issue_zone': p['issue_time'] = '2025-04-30T08:00:00+00:00'
    elif mutation == 'native_forecast': bundle['C0_Q50'] = [99.]*24
    elif mutation == 'identity': identity['jobs'] = 7
    elif mutation == 'cc4_future': p['forecast_inputs']['current_CC4']['future_job_ids'] = ['future']
    with pytest.raises(ValueError, match=label): verify(source_case)


@pytest.mark.parametrize('field,label', [('known_gpu','DAY_OCCUPANCY_EXACT_INTERVAL_INTEGRAL'),
    ('cc4_served_gpu','CC4_CAPACITY|CC4_ASCENDING_SITE_PRIORITY'), ('GPU','GPU_COMPONENT_SUM'),
    ('IT_kw','ORIGINAL_C1_POWER_MAPPING_EXACT'), ('PCC_P_kw','ORIGINAL_C1_POWER_MAPPING_EXACT'),
    ('PCC_Q_kvar','ORIGINAL_C1_POWER_MAPPING_EXACT')])
def test_physical_array_mutation_rejected(source_case, field, label):
    source_case[1][field][25, 0] += .01
    with pytest.raises(ValueError, match=label): verify(source_case)


def test_cc4_site_priority_even_when_capacity_and_mass_are_preserved(source_case):
    plan = source_case[1]
    # Reduce the input demand to expose a partly filled first site. Regenerate
    # this test's baseline once using the unchanged producer, before checking.
    p = source_case[0]; p['forecast_inputs']['current_CC4']['nominal_unknown_GPU_96'] = [1.]*96
    p['forecast_inputs']['current_CC4']['Q50_GPUh'] = [1.]*24
    plan['cc4_served_gpu'], _, _ = allocate(plan['known_gpu'], [1.]*96, [8]*12)
    plan['cc4_served_gpu'][20, 0] -= .5; plan['cc4_served_gpu'][20, 1] += .5
    with pytest.raises(ValueError, match='CC4_ASCENDING_SITE_PRIORITY'): verify(source_case)


def test_c1_slot_identity_and_q50_mass_are_checked(source_case):
    source_case[3].loc[0, 'slot'] = 1
    with pytest.raises(ValueError, match='SOURCE_C1_EXACT_AXIS'): verify(source_case)


def test_original_post96_mass_is_not_discarded(source_case):
    source_case[0]['forecast_inputs']['current_CC4']['full_tail_nominal_GPUh'] = 1.
    with pytest.raises(ValueError, match='ORIGINAL_Q50_GPUH_CONSERVATION'): verify(source_case)
