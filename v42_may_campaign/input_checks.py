"""Independent admission checks for the existing, nonoptimized B2 reference.

This module never invokes a reference, queue or power producer.  It verifies the
actual job assignments against the causal source rows and interval capacity,
then verifies the physical arrays against those assignments and source C1.
"""
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from pathlib import Path
import math
import numpy as np
import pandas as pd
from .common import ROOT, DAYS, read, record, sha, digest, atomic, d_path
from v42_final.common import MODEL

RULE = 'V42_COMMON_FCFS_Q50_NOMINAL_RELEASE_V2'
FORBIDDEN = frozenset(('end_time', 'actual_runtime', 'actual_remaining', 'voltage',
    'line_loading', 'electricity_price', 'actual_result', 'start_observed_by_day_end',
    'end_observed_by_day_end', 'future_completion_receipt'))
GENERATED = frozenset(('compatible_sites', 'reference_site', 'reference_start'))


def _require(ok, label):
    if not ok:
        raise ValueError('INDEPENDENT_B2_' + label)


def _time(value):
    t = datetime.fromisoformat(value)
    _require(t.tzinfo is not None and t.utcoffset() is not None, 'AWARE_TIME_REQUIRED')
    return t


def _fits(intervals, start, length, gpu, cap):
    """Prove whole-gang capacity at each occupancy discontinuity."""
    end = start + length
    probes = {start}
    probes.update(a for a, b, g in intervals if start < a < end)
    probes.update(b for a, b, g in intervals if start < b < end)
    return all(gpu + sum(g for a, b, g in intervals if a <= t < b) <= cap
               for t in probes)


def _assignments(p, selected):
    jobs = p['known_population']
    _require(jobs and len({r['job_uid'] for r in jobs}) == len(jobs), 'UNIQUE_RAW_POPULATION')
    _require(set(selected) == {r['job_uid'] for r in jobs}, 'NO_WORKLOAD_DROP')
    caps, racks = p['capacities'], p['rack_compatibility']
    _require(caps and set(caps) == set(racks), 'CAPACITY_RACK_AXIS')
    _require(all(type(c) is int and c > 0 for c in caps.values()), 'CAPACITY_INTEGER')
    issue = _time(p['issue_time'])
    _require(all(j.get('state_at_D1_cutoff') in ('RUNNING','PENDING')
                 and type(j.get('GPU_gang')) is int and j['GPU_gang'] > 0 for j in jobs),
             'OBSERVED_STATE_AND_WHOLE_GANG')
    order = sorted(jobs, key=lambda j: (0, -j['GPU_gang'], j['job_uid'])
                   if j['state_at_D1_cutoff'] == 'RUNNING'
                   else (1, _time(j['submit_time']), j['job_uid']))
    bound_running = [j for j in order if j['state_at_D1_cutoff'] == 'RUNNING' and j.get('source_site')]
    bound_uids = {j['job_uid'] for j in bound_running}
    order = bound_running + [j for j in order if j['job_uid'] not in bound_uids]
    reservations = {s: [] for s in sorted(caps)}
    issue_use = dict.fromkeys(caps, 0)
    previous_pending_start = 0
    expired = fallback = running = pending = deadline_fields = 0
    for raw in order:
        uid = raw['job_uid']; row = selected[uid]
        _require(not FORBIDDEN.intersection(raw), 'FUTURE_OR_GRID_ROW:' + uid)
        _require(_time(raw['submit_time']) <= issue, 'D1_CAUSAL_SUBMISSION:' + uid)
        _require(row.get('job_uid') == uid and row.get('job_id') == uid, 'JOB_ID:' + uid)
        _require(all(row.get(k) == v for k, v in raw.items() if k not in GENERATED), 'IMMUTABLE_RAW_ROW:' + uid)
        state, gpu, n = raw['state_at_D1_cutoff'], raw['GPU_gang'], raw['service_slots']
        _require(state in ('RUNNING', 'PENDING') and type(gpu) is int and gpu > 0,
                 'OBSERVED_STATE_AND_WHOLE_GANG:' + uid)
        _require(raw['runtime_authority'] == MODEL and type(n) is int and n >= 0,
                 'CURRENT_RUNTIME_AUTHORITY:' + uid)
        q50, elapsed = float(raw['Q50_total_seconds']), float(raw['elapsed_seconds'])
        _require(math.isfinite(q50) and q50 >= 0 and math.isfinite(elapsed) and elapsed >= 0,
                 'NOMINAL_SECONDS:' + uid)
        _require(state != 'PENDING' or elapsed == 0, 'PENDING_ELAPSED:' + uid)
        seconds = q50 if state == 'PENDING' else max(q50 - elapsed, 0.)
        _require(float(raw['nominal_remaining_seconds']) == seconds and n == math.ceil(seconds / 900),
                 'Q50_REMAINING_SERVICE:' + uid)
        if 'runtime_inference_event_time' in raw:
            _require(_time(raw['runtime_inference_event_time']) == issue, 'RUNTIME_INFERENCE_ISSUE:' + uid)
        eligible = [s for s in sorted(caps) if gpu <= caps[s] and any(gpu <= r for r in racks[s])]
        source = raw.get('source_site')
        if source:
            eligible = [s for s in eligible if s == source]
        site, start = row.get('reference_site'), row.get('reference_start')
        _require(row.get('status') == 'REFERENCE_ASSIGNED' and eligible and site in eligible,
                 'ASSIGNED_COMPATIBLE_SITE:' + uid)
        _require(type(start) is int and start >= 0 and row.get('planning_site') == site,
                 'ISSUE_RELATIVE_START:' + uid)
        _require(row.get('compatible_sites') == eligible and row.get('queue_rule') == RULE,
                 'ORIGINAL_RULE_AND_SITE_ORDER:' + uid)
        is_fallback = not bool(source)
        _require(row.get('fallback_used') is is_fallback, 'SOURCE_SITE_AUTHORITY:' + uid)
        expected_site_authority = ('USER_DEFINED_GRID_BLIND_REFERENCE_PLACEMENT'
                                   if is_fallback else raw['source_site_authority'])
        _require(row.get('site_authority_source') == expected_site_authority,
                 'PLACEMENT_AUTHORITY_LABEL:' + uid)
        _require(row.get('physical_running_retained') is (state == 'RUNNING')
                 and row.get('q50_expired') is (state == 'RUNNING' and n == 0)
                 and row.get('q50_expired_hard_occupancy') is False
                 and row.get('synthetic_completion') is False, 'RUNNING_NOT_SYNTHETICALLY_COMPLETED:' + uid)
        if state == 'RUNNING':
            _require(start == 0 and row.get('start_authority_source') == 'OBSERVED_RUNNING_AT_ISSUE',
                     'RUNNING_ISSUE_START:' + uid)
            feasible = [s for s in eligible if issue_use[s] + gpu <= caps[s]
                        and _fits(reservations[s], 0, n, gpu, caps[s])]
            _require(feasible and site == feasible[0], 'RUNNING_ISSUE_CAPACITY_AND_PRIORITY:' + uid)
            issue_use[site] += gpu
            running += 1; expired += n == 0
        else:
            _require(row.get('start_authority_source') == RULE and start >= previous_pending_start,
                     'STRICT_FCFS_NO_BACKFILL:' + uid)
            # Actual start must be a source reservation release or the preceding
            # FCFS start, and no earlier release may admit this gang anywhere.
            release_candidates = {previous_pending_start}
            release_candidates.update(b for s in eligible for a, b, g in reservations[s]
                                      if b >= previous_pending_start)
            _require(start in release_candidates, 'CAUSAL_RELEASE_START:' + uid)
            _require(not any(_fits(reservations[s], t, n, gpu, caps[s])
                             for t in release_candidates if t < start for s in eligible),
                     'EARLIEST_FCFS_START:' + uid)
            feasible = [s for s in eligible if _fits(reservations[s], start, n, gpu, caps[s])]
            _require(feasible and site == feasible[0], 'FCFS_CAPACITY_AND_ASCENDING_SITE:' + uid)
            previous_pending_start = start; pending += 1
        if n:
            reservations[site].append((start, start+n, gpu))
        fallback += is_fallback
        deadline_fields += sum('deadline' in key.lower() for key in raw)
    return dict(jobs=len(jobs), RUNNING=running, PENDING=pending, q50_expired_RUNNING=expired,
                fallback_jobs=fallback, issue_physical_GPU=issue_use,
                deadline_metadata_fields_preserved=deadline_fields,
                deadline_rule='EXISTING_V2_HAS_NO_DEADLINE_FEASIBILITY_GATE',
                all_original_rows_and_service_preserved=True, strict_FCFS_no_backfill=True,
                every_start_earliest_and_grid_blind_site_priority=True)


def _known_integral(rows, sites):
    """Exact rational interval overlap on the D-day axis, not producer replay."""
    shape = (96, len(sites)); exact = [[Fraction(0) for _ in sites] for _ in range(96)]
    rounding = np.zeros(shape); counts = np.zeros(shape, dtype=int)
    index = {s: i for i, s in enumerate(sites)}; eps = np.finfo(float).eps
    for row in rows:
        i, g = index[row['reference_site']], row['GPU_gang']
        start = row['reference_start']; seconds = float(row['nominal_remaining_seconds'])
        left = Fraction(900 * start); right = left + Fraction.from_float(seconds)
        lo = max(0, start - 24); hi = min(96, start - 24 + row['service_slots'])
        for t in range(lo, hi):
            slot_left = Fraction(900 * (t+24)); slot_right = slot_left + 900
            overlap = max(Fraction(0), min(right, slot_right) - max(left, slot_left))
            exact[t][i] += g * overlap / 900
            counts[t, i] += 1
            rounding[t, i] += 16 * eps * g * (abs(seconds) + 900*abs(t+24-start) + 900) / 900
    expected = np.array([[float(x) for x in r] for r in exact])
    rounding += 8 * eps * counts * np.maximum(1, np.abs(expected))
    return expected, rounding


def validate_independent_aidc(p, planning, selected_jobs, coefficients, power, identity=None, bundle=None):
    day = p['day']; issue = _time(p['issue_time'])
    midnight = datetime.fromisoformat(day).replace(tzinfo=timezone(timedelta(hours=10)))
    _require(issue == midnight - timedelta(hours=6) and issue.utcoffset() == timedelta(hours=10),
             'FIXED_AEST_ISSUE_TO_DAY_24_SLOTS')
    _require(p.get('slots', 96) == 96 and p.get('slot_seconds', 900) == 900,
             'ORIGINAL_96_QUARTER_HOUR_AXIS')
    _require(p.get('future_actual_arrival_IDs_present', False) is False, 'NO_FUTURE_ACTUAL_IDS')
    assignment = _assignments(p, selected_jobs)
    sites = sorted(p['capacities']); caps = np.array([p['capacities'][s] for s in sites])
    _require(np.array_equal(planning['sites'], sites) and np.array_equal(planning['capacities'], caps),
             'ORIGINAL_SITE_CAPACITY_AXIS')
    arrays = {k: np.asarray(planning[k], float) for k in ('known_gpu', 'cc4_served_gpu', 'GPU', 'IT_kw', 'PCC_P_kw', 'PCC_Q_kvar')}
    _require(all(x.shape == (96, len(sites)) and np.isfinite(x).all() for x in arrays.values()),
             'FINITE_PHYSICAL_ARRAY_AXIS')
    known, rounding = _known_integral(selected_jobs.values(), sites)
    known_error = np.abs(arrays['known_gpu'] - known)
    _require(np.all(known_error <= rounding), 'DAY_OCCUPANCY_EXACT_INTERVAL_INTEGRAL')
    cc = p['forecast_inputs']['current_CC4']
    _require(cc['target_day'] == day and not cc['future_job_ids'], 'CAUSAL_CC4_AXIS')
    if 'issue_time' in cc:
        _require(_time(cc['issue_time']) == issue, 'CC4_SAME_ISSUE')
    reference = np.asarray(cc['nominal_unknown_GPU_96'], float)
    _require(reference.shape == (96,) and np.isfinite(reference).all() and np.all(reference >= 0),
             'ORIGINAL_CC4_NOMINAL_PROFILE')
    served = arrays['cc4_served_gpu']; backlog = 0.; maximum_backlog = 0.
    for t in range(96):
        demand = float(reference[t]) + backlog
        available = np.maximum(0., caps - arrays['known_gpu'][t])
        _require(np.all(served[t] >= 0) and np.all(served[t] <= available + 1e-9), 'CC4_CAPACITY')
        consumed = 0.
        for i in range(len(sites)):
            expected = min(max(0., demand-consumed), available[i])
            _require(abs(float(served[t, i])-expected) <= 1e-9 + 1e-12*abs(demand),
                     'CC4_ASCENDING_SITE_PRIORITY')
            consumed += float(served[t, i])
        backlog = demand-consumed
        _require(backlog >= -1e-9 and abs(consumed-min(demand, float(available.sum()))) <= 1e-9 + 1e-12*abs(demand),
                 'CC4_NO_DROP_OR_UNSERVED_FREE_CAPACITY')
        maximum_backlog = max(maximum_backlog, backlog)
    _require(np.array_equal(arrays['GPU'], arrays['known_gpu']+served), 'GPU_COMPONENT_SUM')
    _require(np.all(arrays['GPU'] >= 0) and np.all(arrays['GPU'] <= caps+1e-9), 'ALL_GPU_SITE_CAPACITY')
    forecast_mass = float(sum(cc['Q50_GPUh']))
    got = float(served.sum()/4 + backlog/4 + cc['full_tail_nominal_GPUh'])
    mass_error = got-forecast_mass
    _require(abs(mass_error) <= 1e-9 + 1e-12*abs(forecast_mass), 'ORIGINAL_Q50_GPUH_CONSERVATION')
    c = coefficients if isinstance(coefficients, pd.DataFrame) else pd.read_csv(coefficients)
    _require(set(c.aidc_id) == set(sites) and set(c.slot) == set(range(96))
             and len(c) == 96*len(sites) and not c.duplicated(['slot','aidc_id']).any(), 'SOURCE_C1_EXACT_AXIS')
    slope = c.pivot(index='slot', columns='aidc_id', values='slope').reindex(index=range(96), columns=sites).to_numpy()
    intercept = c.pivot(index='slot', columns='aidc_id', values='intercept_kw').reindex(index=range(96), columns=sites).to_numpy()
    it = power['current_IT_idle_kW_per_installed_GPU']*caps + power['current_IT_swing_kW_per_active_GPU']*arrays['GPU']
    pcc = slope*it+intercept; q = pcc*np.tan(np.arccos(.95))
    _require(np.isfinite(slope).all() and np.isfinite(intercept).all()
             and np.array_equal(arrays['IT_kw'], it) and np.array_equal(arrays['PCC_P_kw'], pcc)
             and np.array_equal(arrays['PCC_Q_kvar'], q), 'ORIGINAL_C1_POWER_MAPPING_EXACT')
    refs = [selected_jobs[uid] for uid in sorted(selected_jobs)]
    if identity is not None:
        _require(identity['day'] == day and identity['arm'] == 'B2' and identity['rule'] == RULE
                 and identity['jobs'] == len(refs) and identity['reference_SHA'] == digest(refs)
                 and identity['job_ids_SHA'] == digest(sorted(selected_jobs))
                 and identity['time_axis'] == list(range(96)) and identity['sites'] == sites,
                 'GENERATED_IDENTITY_BOUND_TO_ACTUAL_REFERENCE')
        _require(identity['AIDC_optimization_calls'] == 0 and identity['MESS_optimizer_calls'] == 0
                 and identity['B0_B1_schedule_result_reads'] == 0, 'NONOPTIMIZED_INDEPENDENT_B2')
        if 'full_reference' in identity:
            audit=identity['full_reference']
            _require(audit['queue_rule']==RULE and audit['input_jobs']==audit['output_jobs']==audit['assigned_jobs']==len(refs)
                and audit['blocked_jobs']==0 and audit['full_reference_ready'] is True and audit['workload_drop'] is False
                and audit['optimizer_calls']==audit['voltage_reads']==audit['actual_reads']==0
                and audit['population_sha256']==digest(p['known_population']) and audit['reference_sha256']==digest(refs)
                and audit['fallback_jobs']==assignment['fallback_jobs'], 'SOURCE_REFERENCE_AUDIT_BOUND_TO_RAW_AND_SELECTED')
        if 'conservation' in identity:
            cons=identity['conservation']; tol=1e-9+1e-12*abs(forecast_mass)
            _require(cons['PASS'] is True and cons['forecast_Q50_GPUh']==forecast_mass
                and cons['served_DDAY_GPUh']==float(served.sum()/4)
                and cons['original_post96_tail_GPUh']==cc['full_tail_nominal_GPUh']
                and abs(cons['capacity_backlog_carryout_GPUh']-backlog/4)<=tol
                and abs(cons['conservation_error']-mass_error)<=tol, 'SOURCE_CONSERVATION_AUDIT_BOUND_TO_PHYSICAL_ARRAYS')
    if bundle is not None:
        _require(bundle['day'] == day and _time(bundle['issue_time']) == issue
                 and bundle['known_population'] == p['known_population'], 'NATIVE_RAW_POPULATION_AND_ISSUE')
        _require(np.array_equal(bundle['C0_Q50'], cc['Q50_GPUh'])
                 and np.array_equal(bundle['C0_Q90'], cc['Q90_GPUh']), 'NATIVE_SAME_CC4_FORECAST')
    return dict(PASS=True, day=day, arm='B2', rule=RULE, Native_calls=0,
        AIDC_optimization_calls=0, producer_calls=0, independent_interval_and_assignment_checker=True,
        original_reference=assignment, issue_relative_day_offset_slots=24,
        known_occupancy_max_absolute_error=float(known_error.max(initial=0)),
        known_occupancy_numerical_error_bound=float(rounding.max(initial=0)),
        CC4_capacity_backlog_carryout_GPU=float(backlog), CC4_maximum_backlog_GPU=float(maximum_backlog),
        original_Q50_GPUh=forecast_mass, conservation_error_GPUh=mass_error,
        original_C1_IT_PCC_mapping_exact=True, all_GPU_capacity=True,
        reference_SHA=digest(refs), jobs=len(refs))


def verify_b2(payload, input_folder):
    folder = Path(input_folder)
    p = read(folder/'PLANNING_INPUT_BUNDLE.json')
    _require(payload['identity']['input_SHA'] == sha(folder/'PLANNING_INPUT_BUNDLE.json'), 'RAW_BUNDLE_SHA')
    _require({'full_reference','conservation','source'}.issubset(payload['identity'])
        and payload['identity']['source']['sha256']==sha(ROOT/'v42_capacity/reference.py'), 'ORIGINAL_REFERENCE_SOURCE_SHA')
    _require(payload['anchor']['day']==p['day']
        and np.array_equal(payload['anchor']['PCC_P_kw'],payload['planning']['PCC_P_kw']), 'FIXED_AIDC_ANCHOR_BOUND_TO_POWER')
    result = validate_independent_aidc(p, payload['planning'], payload['selected_jobs'],
        folder/'C1_PLANNING_COEFFICIENTS.csv', read(folder/'POWER_AUTHORITY.json'),
        payload['identity'], payload['bundle'])
    result['original_sources'] = {name: record(folder/name) for name in
        ('PLANNING_INPUT_BUNDLE.json', 'C1_PLANNING_COEFFICIENTS.csv', 'POWER_AUTHORITY.json', 'NATIVE_INPUT.json')}
    result['checker_source'] = record(Path(__file__))
    result['reference_source'] = record(ROOT/'v42_capacity/reference.py')
    return result


def audit_all_b2(campaign_root, progress=None):
    """Check frozen inputs only; do not call any producer or baseline loop."""
    root=d_path(campaign_root); receipts=[]
    for day in DAYS:
        if progress: progress(dict(phase='B2_INDEPENDENT_INPUT_ADMISSION_NATIVE0',day=day))
        folder=root/'inputs/B2'/day; fixed=read(folder/'B2_FIXED_AIDC.json')
        _require(Path(fixed['physical']['path']).resolve()==(folder/'PLANNING_PHYSICAL.npz').resolve()
            and fixed['physical']['sha256']==sha(folder/'PLANNING_PHYSICAL.npz'), 'FROZEN_PHYSICAL_SHA')
        with np.load(folder/'PLANNING_PHYSICAL.npz',allow_pickle=False) as data:
            planning={k:data[k].copy() for k in data.files}
        payload=dict(identity=fixed['identity'],selected_jobs=fixed['selected_jobs'],planning=planning,
            bundle=read(folder/'NATIVE_INPUT.json'),anchor=dict(day=day,PCC_P_kw=planning['PCC_P_kw'].tolist()))
        receipt=verify_b2(payload,folder)
        atomic(folder/'INDEPENDENT_AIDC_ADMISSION_CHECK.json',receipt);receipts.append(receipt)
    result=dict(PASS=all(r['PASS'] for r in receipts),days_checked=len(receipts),days=receipts,
        Native_calls=0,AIDC_optimization_calls=0,producer_calls=0,B0_B1_result_reads=0,
        checker=record(Path(__file__)))
    atomic(root/'B2_INDEPENDENT_AIDC_ADMISSION_AUDIT.json',result)
    return result


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--root',required=True)
    args=parser.parse_args()
    result=audit_all_b2(args.root,lambda r:print(r['day'],'independent B2 admission Native0',flush=True))
    print('INDEPENDENT B2 ADMISSION',result['PASS'],result['days_checked'],flush=True)
