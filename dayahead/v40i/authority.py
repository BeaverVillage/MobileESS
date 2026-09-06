"""Independent timing, site and interval authorities; no planning fallback."""
from copy import deepcopy
import math
from dayahead.v40h.identity import require, verify_file
from dayahead.v40d_actual.job_replay import timestamp
from dayahead.paper_analysis.storage import read

VERSION = 'V40I_ACTUAL_AUTHORITY_V1'
MISSING = 'COUNTERFACTUAL_ACTUAL_EXECUTION_SITE_AUTHORITY_MISSING'
PRE_COMPLETE = 'LEGITIMATE_PRE_DAY_COMPLETE'
AUTHORIZED = 'ACTUAL_EXECUTION_AUTHORIZED'
SEGMENT_FIELDS = ('uid', 'day', 'segment_start', 'segment_end', 'actual_site', 'compute_active',
    'source_authority_path', 'source_record_identifier', 'source_hash', 'derivation_version')


def timing_from_observation(job, observation, issue_time, *, observation_record, replay_contract_record):
    """RUNNING continues at issue under the frozen contract; pending has a lower bound only.

    Observed duration is a runtime authority. For PENDING jobs its historical
    wall-clock end is not the end of counterfactual capacity-delayed execution.
    Neither observation nor this timing proof asserts a site.
    """
    verify_file(observation_record); verify_file(replay_contract_record)
    issue = timestamp(issue_time); start = timestamp(observation['start_time']); end = timestamp(observation['end_time'])
    require(end > start, 'ACTUAL_DURATION_INVALID')
    require(int(observation['gpus_requested']) == int(job['requested_GPU']), 'ACTUAL_GPU_IDENTITY_MISMATCH')
    running = job['state_at_issue'] == 'RUNNING'
    require(job['state_at_issue'] in ('RUNNING', 'PENDING'), 'UNKNOWN_ISSUE_STATE')
    if running: require(start <= issue < end, 'RUNNING_NOT_ACTIVE_AT_ISSUE')
    seconds = (end - (issue if running else start)).total_seconds()
    ready = 0. if running else max(float(job['start_slot']), float(job.get('frozen_execution_ready_slot', 0)))
    exact = running and not job.get('migration_selected', False)
    finish = ready + seconds / 900.
    return {'uid': str(job['job_uid']), 'authority_kind': 'ACTUAL_TIMING', 'timing_authority_present': True,
        'counterfactual_timing_complete': exact, 'actual_start': ready if exact else None,
        'actual_finish': finish if exact else None, 'earliest_start': ready, 'earliest_finish': finish,
        'service_seconds': seconds, 'remaining_service_at_d_day_sec': max(0., finish - max(ready, 24.)) * 900.,
        'remaining_service_semantics': 'EXACT' if exact else 'FROZEN_READY_NO_DELAY_LOWER_BOUND',
        'active_intervals': [[ready, finish]] if exact else None,
        'proof_rule': 'RUNNING_CONTINUES_AT_ISSUE_WITHOUT_READMISSION_OR_MIGRATION' if exact else 'OBSERVED_DURATION_ONLY_ADMISSION_UNKNOWN',
        'authority_path': observation_record['path'], 'authority_record_id': 'id=' + str(job['job_uid']),
        'authority_files': [observation_record, replay_contract_record],
        'site_authority_present': False, 'segment_authority_present': False, 'planning_fallback_used': False}


def canonical_segments(rows, *, uid, day, evidence):
    require(evidence.get('authority_kind') == 'ACTUAL_EXECUTION_SEGMENTS', 'PLANNING_NOT_ACTUAL_SEGMENT_AUTHORITY')
    require(evidence.get('uid') == str(uid) and evidence.get('day') == day, 'SEGMENT_AUTHORITY_SCOPE_MISMATCH')
    verify_file(evidence['file'])
    source = read(evidence['file']['path'])
    require(isinstance(source, dict) and source.get('authority_kind') == 'ACTUAL_EXECUTION_SEGMENTS' and
        source.get('uid') == str(uid) and source.get('day') == day and source.get('segments') == rows,
        'SEGMENT_SOURCE_RECORD_BINDING_MISMATCH')
    segments = []
    for i, row in enumerate(rows):
        begin, end = float(row['segment_start']), float(row['segment_end'])
        active = row['compute_active']; site = row.get('actual_site')
        require(math.isfinite(begin) and math.isfinite(end) and begin < end, 'INVALID_SEGMENT_INTERVAL')
        require(active in (0, 1, False, True), 'COMPUTE_ACTIVE_STATE_REQUIRED')
        require((active and isinstance(site, str) and site.startswith('AIDC') and site != 'UNASSIGNED') or
            (not active and site is None), 'ACTIVE_SITE_OR_EXPLICIT_ZERO_COMPUTE_GAP_REQUIRED')
        segments.append(dict(uid=str(uid), day=day, segment_start=begin, segment_end=end, actual_site=site,
            compute_active=int(active), source_authority_path=evidence['file']['path'],
            source_record_identifier=row.get('source_record_identifier', evidence['record_id'] + '/' + str(i)),
            source_hash=evidence['file']['sha256'], derivation_version=VERSION))
    require(bool(segments), 'EMPTY_SEGMENT_AUTHORITY')
    require(all(a['segment_end'] <= b['segment_start'] for a, b in zip(segments, segments[1:])), 'SEGMENT_OVERLAP_OR_UNSORTED')
    return segments


def covers(required, available, tolerance=1e-9):
    for start, end in required:
        cursor = start
        for a, b in available:
            if b <= cursor: continue
            if a > cursor + tolerance: break
            cursor = max(cursor, b)
            if cursor >= end - tolerance: break
        if cursor < end - tolerance: return False
    return True


def classify(*, uid, day, timing=None, site_segments=None, segment_evidence=None, boundary=24.):
    result = {'uid': str(uid), 'day': day, 'd_day_boundary': boundary, 'pre_day_complete_recomputed': False,
        'timing_authority_present': False, 'site_authority_present': False, 'segment_authority_present': False,
        'site_coverage_complete': False, 'compute_interval_coverage_complete': False, 'blocker_released': False,
        'final_classification': MISSING, 'planning_fallback_detected': False, 'planning_fallback_used': False,
        'actual_start': None, 'actual_finish': None, 'remaining_service_at_d_day_sec': None,
        'reason': 'Timing and full active-interval actual site evidence required; no fallback.'}
    if timing is None or timing.get('authority_kind') != 'ACTUAL_TIMING': return result
    require(timing['uid'] == str(uid), 'TIMING_UID_MISMATCH')
    for r in timing.get('authority_files', []): verify_file(r)
    result.update({k: deepcopy(timing[k]) for k in ('actual_start', 'actual_finish', 'remaining_service_at_d_day_sec',
        'authority_path', 'authority_record_id', 'timing_authority_present') if k in timing})
    complete = timing.get('counterfactual_timing_complete') is True
    intervals = timing.get('active_intervals')
    if complete:
        require(intervals and all(math.isfinite(a) and math.isfinite(b) and a < b for a, b in intervals), 'COMPLETE_TIMING_INTERVALS_REQUIRED')
        require(all(a[1] <= b[0] for a, b in zip(intervals, intervals[1:])), 'TIMING_INTERVAL_OVERLAP')
        require(abs(intervals[-1][1] - timing['actual_finish']) < 1e-9, 'TIMING_FINISH_CONTRADICTION')
        require(abs(sum((b-a)*900 for a,b in intervals)-timing['service_seconds']) < 1e-6, 'TIMING_SERVICE_LOSS')
        result['compute_interval_coverage_complete'] = True
        if timing['actual_finish'] <= boundary:
            result.update(final_classification=PRE_COMPLETE, blocker_released=True, pre_day_complete_recomputed=True,
                remaining_service_at_d_day_sec=0., reason='Complete actual timing proof finishes no later than D-day boundary; no site inferred.')
            return result
    if site_segments is None or segment_evidence is None: return result
    if segment_evidence.get('authority_kind') != 'ACTUAL_EXECUTION_SEGMENTS':
        result.update(planning_fallback_detected=True, reason='Planning or isolated site label rejected as Actual interval authority.')
        return result
    segments = canonical_segments(site_segments, uid=uid, day=day, evidence=segment_evidence)
    active = [(s['segment_start'], s['segment_end']) for s in segments if s['compute_active']]
    result.update(site_authority_present=bool(active), segment_authority_present=True, canonical_segments=segments)
    if not complete: return result
    # Exact interval union is required in both directions; gaps cannot be filled.
    covered = covers(intervals, active) and covers(active, intervals)
    gaps = [(a[1], b[0]) for a,b in zip(intervals,intervals[1:]) if a[1] < b[0]]
    explicit_gaps = [(s['segment_start'],s['segment_end']) for s in segments if not s['compute_active']]
    covered = covered and covers(gaps, explicit_gaps) and covers(explicit_gaps, gaps)
    result.update(site_coverage_complete=covered, compute_interval_coverage_complete=covered)
    if covered:
        result.update(final_classification=AUTHORIZED, blocker_released=True,
            reason='Independent actual timing and actual site/segment evidence cover all required active intervals.')
    return result
