"""Counterfactual exclusion needs execution evidence, never observed end time."""
from pathlib import Path
from collections import Counter
import pandas as pd
from dayahead.paper_analysis.storage import read, write_json, write_parquet, reference
from dayahead.v40d_actual.job_replay import timestamp
from .identity import REL, require

SITE_BLOCKER = 'COUNTERFACTUAL_ACTUAL_EXECUTION_SITE_AUTHORITY_MISSING'


def classify(job, observation, issue_time, *, execution_segments=None):
    issue = timestamp(issue_time)
    start, end = timestamp(observation['start_time']), timestamp(observation['end_time'])
    require(end > start, 'INVALID_REALIZED_SERVICE')
    seconds = (end - issue).total_seconds() if job['state_at_issue'] == 'RUNNING' else (end - start).total_seconds()
    require(seconds > 0, 'NONPOSITIVE_COUNTERFACTUAL_SERVICE')
    ready = 0 if job['state_at_issue'] == 'RUNNING' else max(float(job['start_slot']), float(job.get('frozen_execution_ready_slot', 0)))
    from dayahead.v41r1.migration import active
    if active(job) and job.get('migration_selected') and job['state_at_issue']=='PENDING':
        # Source compute begins at the frozen initial start; destination READY
        # is not first-placement readiness. Migration pause remains in trace.
        ready=float(job['start_slot'])
    earliest_end = ready + seconds / 900
    # This is a lower-bound timing witness only. It cannot prove that unknown
    # site capacity caused no delay. A completed exclusion requires the actual
    # deterministic execution trace, with its authoritative site and service.
    lower_overlap = max(0., min(earliest_end, 120) - max(ready, 24)) * 900
    result = {'job_uid': str(job['job_uid']), 'status': 'FAIL_CLOSED',
        'source_observed_end_used_for_completion': False,
        'frozen_ready_slot': ready, 'realized_compute_seconds': seconds,
        'earliest_counterfactual_end_slot': earliest_end,
        'earliest_counterfactual_D_day_compute_seconds': lower_overlap,
        'D_DAY_GPU_SERVICE': None, 'reason': SITE_BLOCKER if job['AIDC_site'] == 'UNASSIGNED' else 'DETERMINISTIC_EXECUTION_TRACE_REQUIRED'}
    if execution_segments is None: return result
    segments = list(execution_segments)
    require(bool(segments), 'EMPTY_EXECUTION_TRACE')
    require(segments[0]['start'] >= ready and all(a['end'] <= b['start'] for a, b in zip(segments, segments[1:])), 'INVALID_EXECUTION_TRACE_ORDER')
    require(all(s['site'] != 'UNASSIGNED' and s['start'] < s['end'] for s in segments), SITE_BLOCKER)
    require(abs(sum((s['end'] - s['start']) * 900 for s in segments) - seconds) < 1e-6, 'EXECUTION_TRACE_SERVICE_LOSS')
    if not job.get('migration_selected'):
        require(all(s['site'] == job['AIDC_site'] for s in segments), 'EXECUTION_SITE_NOT_FROZEN')
    overlap = sum(max(0., min(s['end'], 120) - max(s['start'], 24)) * 900 for s in segments)
    complete = segments[-1]['end'] <= 24
    result.update(status='PRE_DAY_COMPLETE' if complete and overlap == 0 else 'EXECUTION_INCLUDED',
        reason=None, actual_execution_segments=segments, actual_execution_end_slot=segments[-1]['end'],
        D_DAY_GPU_SERVICE=overlap * job['requested_GPU'] / 3600, reconstructed_D_day_compute_seconds=overlap)
    return result


def require_safe_exclusion(classification):
    require(classification['status'] == 'PRE_DAY_COMPLETE' and classification['D_DAY_GPU_SERVICE'] == 0 and
            classification.get('actual_execution_end_slot', float('inf')) <= 24, 'COUNTERFACTUAL_EXCLUSION_NOT_PROVEN')


def scan(repo):
    """Historical decisions are diagnostic inputs only, never campaign reuse."""
    from dayahead.v40d_actual.inputs import frozen_jobs, observations
    from dayahead.v40d_actual.pre_day_complete import classify as legacy
    repo = Path(repo); old = repo / 'dayahead/artifacts/v40d_actual_realized_replay'; root = repo / REL
    bindings = read(old / 'V40D_ACTUAL_DECISION_BINDING_AUDIT.json')['cases']; require(len(bindings) == 124, '124_PREFLIGHT_BINDINGS_REQUIRED')
    obs = observations(old); rows = []; jobs_scanned = 0
    previous = read(old / 'pre_day_complete_preflight/JOB_PREFLIGHT.json')
    old_cases = {(r['day'], r['case']) for r in previous['cases'] if r['status'] != 'PASS'}
    for binding in bindings:
        jobs, issue = frozen_jobs(repo, binding); jobs_scanned += len(jobs)
        for job in jobs:
            if job['AIDC_site'] != 'UNASSIGNED' or job['start_slot'] >= 120: continue
            before = legacy(job, obs[job['job_uid']], issue)
            after = classify(job, obs[job['job_uid']], issue)
            rows.append({'day': binding['day'], 'case': binding['case'], 'job_uid': job['job_uid'],
                'requested_GPU': job['requested_GPU'], 'state': job['state_at_issue'],
                'frozen_start': job['start_slot'], 'frozen_end': job['end_slot'],
                'old_status': before['status'], **{k: v for k, v in after.items() if k != 'job_uid'},
                'definite_false_old_exclusion': before['status'] == 'PRE_DAY_COMPLETE' and after['earliest_counterfactual_D_day_compute_seconds'] > 0,
                'unproven_old_exclusion_due_to_missing_site': before['status'] == 'PRE_DAY_COMPLETE' and after['earliest_counterfactual_D_day_compute_seconds'] == 0})
    blocked = [r for r in rows if r['status'] == 'FAIL_CLOSED']
    blocked_cases = {(r['day'], r['case']) for r in blocked}; newly = blocked_cases - old_cases
    result = {'status': 'STATIC_SCAN_COMPLETE_FAIL_CLOSED', 'scanned_case_count': 124, 'scanned_job_rows': jobs_scanned,
        'old_PRE_DAY_COMPLETE_count': sum(r['old_status'] == 'PRE_DAY_COMPLETE' for r in rows),
        'new_PRE_DAY_COMPLETE_count': sum(r['status'] == 'PRE_DAY_COMPLETE' for r in rows),
        'removed_false_PRE_DAY_COMPLETE_count': sum(r['definite_false_old_exclusion'] for r in rows),
        'removed_unproven_PRE_DAY_COMPLETE_count': sum(r['unproven_old_exclusion_due_to_missing_site'] for r in rows),
        'newly_blocked_case_count': len(newly),
        'newly_blocked_job_count': sum(r['old_status'] == 'PRE_DAY_COMPLETE' for r in blocked),
        'newly_blocked_unique_UID_count': len({r['job_uid'] for r in blocked if r['old_status'] == 'PRE_DAY_COMPLETE'}),
        'newly_blocked_unique_day_UID_count': len({(r['day'], r['job_uid']) for r in blocked if r['old_status'] == 'PRE_DAY_COMPLETE'}),
        'EXISTING_UNASSIGNED_44_CASE_BLOCKER': {'status': 'OPEN', 'case_count': len(old_cases), 'cases': sorted(old_cases)},
        'new_blocked_cases': sorted(newly), 'deduplicated_total_blocked_case_count': len(old_cases | blocked_cases),
        'all_current_missing_site_cases': sorted(blocked_cases), 'count_unit': 'job counts are case/job rows unless explicitly unique',
        'conservative_boundary': 'Earliest frozen-start plus realized-service ending before D00 is not proof that unknown site capacity causes no delay. Missing execution-site authority remains fail-closed; no site is inferred.',
        'UID_8749975': [r for r in rows if r['day'] == '2025-05-03' and r['case'] in ('B1', 'B3') and r['job_uid'] == '8749975'],
        'optimization_calls': 0, 'OpenDSS_calls': 0, 'historical_results_adopted': 0}
    write_parquet(root / 'PRE_DAY_COMPLETE_RECLASSIFICATION.parquet', pd.DataFrame(rows))
    write_json(root / 'PRE_DAY_COMPLETE_RECLASSIFICATION.json', result)
    print({k: result[k] for k in ('old_PRE_DAY_COMPLETE_count', 'new_PRE_DAY_COMPLETE_count', 'removed_false_PRE_DAY_COMPLETE_count', 'newly_blocked_case_count', 'newly_blocked_job_count', 'deduplicated_total_blocked_case_count')}, flush=True)
    return result
