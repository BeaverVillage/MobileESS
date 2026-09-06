"""Apply common scalar T_DA to the preserved RW/reference policy geometry."""
from copy import deepcopy
import json
import pandas as pd

from dayahead.paper_analysis.storage import read, digest
from dayahead.v40d_actual.inputs import frozen_jobs
from dayahead.v40a.invariants import tail
from dayahead.v37.aidc_materializer import Job, schedule
from .data import SOURCE_REPO, RUNTIME, issue_time, atomic_json
from .preflight import record
from .reserve import require
from .scalars import policy_inputs


def build(day, snapshot_path, capacity):
    snapshot = read(snapshot_path)
    values = policy_inputs(snapshot, 'B0', 'REFERENCE').payload()
    folder = RUNTIME / 'inputs' / day / 'common'
    if (folder / 'COMMON_INPUT_RECEIPT.json').exists():
        seal = read(folder / 'COMMON_INPUT_RECEIPT.json')
        require(seal['status'] == 'PASS' and seal['generator'] == record(__file__), 'COMMON_GENERATOR_OR_STATUS_DRIFT')
        require(seal['snapshot'] == record(snapshot_path), 'COMMON_SNAPSHOT_DRIFT')
        for entry in seal['files'].values():
            require(entry == record(entry['path']), 'COMMON_INPUT_DRIFT')
        return read(folder / 'COMMON_B0_REFERENCE_JOBS.json'), seal
    base = SOURCE_REPO / 'dayahead/artifacts'
    binding_path = base / 'v40d_actual_realized_replay/V40D_ACTUAL_DECISION_BINDING_AUDIT.json'
    binding = next(b for b in read(binding_path)['cases'] if b['day'] == day and b['case'] == 'B0')
    jobs, issue = frozen_jobs(SOURCE_REPO, binding)
    require(pd.Timestamp(issue) == issue_time(day), 'FIXED_AEST_ISSUE_DRIFT')
    source = base / 'v37_r4a_per_day_aidc/days' / day
    lp = source / 'V37_R4A_JOB_LEDGER.parquet'; sp = source / 'V37_R4A_D1_SNAPSHOT.parquet'
    snapshot_sha = record(sp)['sha256']
    ledger = pd.read_parquet(lp); ledger['uid'] = ledger.job_id.astype(str); ledger = ledger.set_index('uid')
    require(set(ledger.index) == {r['job_uid'] for r in jobs}, 'COMMON_JOB_UNIVERSE')
    before = deepcopy(jobs); scheduling = []
    for job in jobs:
        row = ledger.loc[job['job_uid']]
        if job['state_at_issue'] == 'PENDING':
            slots = values['PENDING_JOB_DURATION_SLOTS'][job['job_uid']]
            seconds = values['PENDING_JOB_Q90_SECONDS'][job['job_uid']]
            authority = 'ROLLING_Q90_TRACK_P_L2'
        else:
            slots = int(row.RSP_duration_slots); seconds = float(row.RSP_duration_seconds)
            authority = str(row.duration_authority)
            require(slots == job['end_slot'] - job['start_slot'], 'RUNNING_SERVICE_AUTHORITY_DRIFT')
        job.update(safe_duration_slots=slots, safe_duration_seconds=seconds, duration_authority=authority,
                   end_slot=job['start_slot'] + slots, source_snapshot_sha256=snapshot_sha, operating_day=day)
        if job['state_at_issue'] == 'RUNNING':
            job['initial_Rack_label'] = job['Rack_label']
        scheduling.append(Job(job_id=job['job_uid'], state_at_issue=job['state_at_issue'],
            workload_class=str(row.workload_class), protected=bool(row.protected), qos=job['qos'],
            partition=job['partition'], submit_time=job['submit_time'], requested_nodes=int(row.requested_nodes),
            requested_gpus=job['requested_GPU'], duration_slots=slots))
    # Recompute the existing causal earliest-start domain with current scalar
    # durations. No old runtime prediction/RSP start is forwarded to A0 or A1.
    earliest, _ = schedule(scheduling, 'V41_Q90_COMMON_SERVICE')
    earliest = earliest.set_index('job_id')
    failures = []
    for old, job in zip(before, jobs):
        uid = job['job_uid']; row = ledger.loc[uid]
        job.update(RSP_start_slot=int(earliest.loc[uid].scheduled_start_slot),
                   RW_completion_slot=int(row.RW_scheduled_completion))
        job['eligible_standby'] = (job['state_at_issue'] == 'PENDING' and job['qos'] == 'standby'
            and job['RSP_start_slot'] <= job['RW_completion_slot'] - job['safe_duration_slots'])
        job['post_H_site'] = job['AIDC_site'] if job['end_slot'] > 120 else None
        job['terminal_class'] = 'IN_DAY_COMPLETE' if job['end_slot'] <= 120 else 'CROSS_BOUNDARY' if job['start_slot'] < 120 else 'POST_H_ONLY'
        job['common_terminal_obligation'] = {'must_complete_by_H': job['end_slot'] <= 120, 'postH_profile': tail(job)}
        for field in ('job_uid', 'start_slot', 'AIDC_site', 'Rack_label', 'migration_selected', 'state_at_issue', 'qos', 'requested_GPU'):
            require(job.get(field) == old.get(field), 'B0_REFERENCE_GEOMETRY_CHANGED:' + field)
        from dayahead.v40a.feedback import authorized_options
        if (job['AIDC_site'], job['start_slot']) not in authorized_options(job, capacity):
            failures.append({'job_uid': uid, 'reason': 'B0_OUTSIDE_COMMON_AUTHORIZED_DOMAIN'})
        if max(24, job['start_slot']) < min(120, job['end_slot']) and job['AIDC_site'] not in capacity.aidc_ids:
            failures.append({'job_uid': uid, 'reason': 'UNASSIGNED_OPERATING_DAY_SERVICE'})
    from dayahead.v41r1.terminal import attach
    jobs = attach(jobs)
    # Revalidate every common reference against the new per-job domain.
    for job in jobs:
        from dayahead.v40a.feedback import authorized_options
        require((job['AIDC_site'], job['start_slot']) in authorized_options(job, capacity), 'R1_REFERENCE_OUTSIDE_DOMAIN')
    atomic_json(folder / 'COMMON_B0_REFERENCE_JOBS.json', jobs)
    rows = [{k: job[k] for k in ('job_uid', 'requested_GPU', 'state_at_issue', 'qos', 'safe_duration_seconds',
             'safe_duration_slots', 'duration_authority', 'common_terminal_obligation', 'terminal_contract',
             'terminal_reference_start_issue_slot', 'terminal_reference_site', 'terminal_reference_remaining_slots')} for job in jobs]
    rows.sort(key=lambda r: r['job_uid'])
    atomic_json(folder / 'COMMON_DA_SERVICE_AUTHORITY.json', dict(rows=rows, COMMON_DA_DURATION_SHA=digest(rows),
        source_ledger=record(lp), source_snapshot=record(sp), ML_snapshot=record(snapshot_path),
        legacy_predicted_runtime_or_probability_forwarded=False, Actual_reads=0))
    from dayahead.v40g_segments.canonical import import_frozen, occupancy
    gpu, _ = occupancy(import_frozen(jobs), capacity.aidc_ids)
    for i, site in enumerate(capacity.aidc_ids):
        if (gpu[:, i] > capacity.site_capacity[site]).any():
            failures.append({'site': site, 'reason': 'REFERENCE_SITE_CAPACITY_EXCEEDED'})
    seal = dict(day=day, status='FAIL' if failures else 'PASS', failures=failures, snapshot=record(snapshot_path),
        COMMON_DA_DURATION_SHA=digest(rows), job_count=len(jobs), policy_dependent_duration=False,
        generator=record(__file__),
        files={name: record(folder / name) for name in ('COMMON_B0_REFERENCE_JOBS.json', 'COMMON_DA_SERVICE_AUTHORITY.json')})
    atomic_json(folder / 'COMMON_INPUT_RECEIPT.json', seal)
    require(not failures, 'V41_COMMON_REFERENCE_PREFLIGHT_FAILED')
    return jobs, seal
