"""New shared V42 reference generator: no grid inputs and no optimizer.

Order: RUNNING by decreasing gang then UID; PENDING by submit time then UID.
Fixed source sites are kept. Missing-site RUNNING gangs use first compatible
site with capacity at issue. Missing-site PENDING gangs use earliest feasible
start, then ascending site ID. Existing placements are never moved to rescue
a later gang. All input rows remain, including blocked requests.

Q50-expired RUNNING jobs retain hard physical occupancy. Without a causal
release authority they reserve capacity indefinitely in this reference. No
inferred completion is created. This can block pending work and is reported.
"""
import math
from copy import deepcopy
from datetime import datetime
from .contracts import require, digest
from v42_final.common import MODEL

QUEUE_RULE = 'V42_COMMON_FCFS_FIXED_SITE_TIEBREAK_V1'


def build_reference(jobs, capacities, compatibility, *, issue_time):
    issue = datetime.fromisoformat(issue_time)
    require(issue.tzinfo is not None, 'ISSUE_TIMEZONE_REQUIRED')
    forbidden = {'end_time', 'actual_runtime', 'actual_remaining', 'voltage', 'line_loading', 'electricity_price', 'actual_result'}
    for j in jobs:
        require(not forbidden.intersection(j), 'FUTURE_OR_GRID_REFERENCE_INPUT')
        submitted = datetime.fromisoformat(j['submit_time'])
        require(submitted.tzinfo is not None and submitted <= issue, 'D1_CAUSAL_REFERENCE_REQUIRED')
    require(capacities and set(capacities) == set(compatibility), 'CAPACITY_COMPATIBILITY_REQUIRED')
    require(all(type(c) is int and c > 0 for c in capacities.values()), 'CAPACITY_INTEGER')
    ids = [j['job_uid'] for j in jobs]
    require(len(ids) == len(set(ids)), 'DUPLICATE_JOB_ID')
    sites = sorted(capacities)
    reservations = {s: [] for s in sites}
    output = {}
    def fits(site, start, end, gpu):
        intervals = reservations[site]
        points = {start} | {a for a, b, g in intervals if start < a < end}
        return all(gpu + sum(g for a, b, g in intervals if a <= t < b) <= capacities[site] for t in points)
    def assign(j, start, site, eligible, fallback):
        n = j['service_slots']
        # Expired RUNNING Q50 is not evidence of a physical completion.
        hard = j['state_at_D1_cutoff'] == 'RUNNING' and n == 0
        end = float('inf') if hard else start + n
        if end > start:
            reservations[site].append((start, end, j['GPU_gang']))
        return dict(j, job_id=j['job_uid'], reference_site=site, planning_site=site,
                    reference_start=start, compatible_sites=eligible, fallback_used=fallback,
                    site_authority_source='USER_DEFINED_GRID_BLIND_REFERENCE_PLACEMENT' if fallback else j['source_site_authority'],
                    start_authority_source='OBSERVED_RUNNING_AT_ISSUE' if j['state_at_D1_cutoff'] == 'RUNNING' else QUEUE_RULE,
                    queue_rule=QUEUE_RULE, status='REFERENCE_ASSIGNED',
                    physical_running_retained=j['state_at_D1_cutoff'] == 'RUNNING',
                    q50_expired_hard_occupancy=hard, synthetic_completion=False)
    order = sorted(jobs, key=lambda j: (0, -j.get('GPU_gang', 0) if isinstance(j.get('GPU_gang'), int) else 0, j['job_uid'])
                   if j['state_at_D1_cutoff'] == 'RUNNING' else (1, datetime.fromisoformat(j['submit_time']), j['job_uid']))
    # Bind every authoritative RUNNING site before any fallback placement.
    order = [j for j in order if j['state_at_D1_cutoff'] == 'RUNNING' and j.get('source_site')] + [
             j for j in order if not (j['state_at_D1_cutoff'] == 'RUNNING' and j.get('source_site'))]
    for original in order:
        j = deepcopy(original)
        blocked = dict(j, status='BLOCKED', reference_site=None, reference_start=None,
                       compatible_sites=[], fallback_used=False, queue_rule=QUEUE_RULE)
        gpu, n = j.get('GPU_gang'), j.get('service_slots')
        reason = None
        if type(gpu) is not int or gpu <= 0:
            reason = 'GPU_REQUEST_AUTHORITY_MISSING'
        elif j.get('runtime_authority') != MODEL or type(n) is not int or n < 0:
            reason = 'CURRENT_RUNTIME_SERVICE_AUTHORITY_MISSING'
        elif j['state_at_D1_cutoff'] not in ('RUNNING', 'PENDING'):
            reason = 'OBSERVED_STATE_AUTHORITY_MISSING'
        if reason:
            output[j['job_uid']] = dict(blocked, reason=reason)
            continue
        eligible = [s for s in sites if gpu <= capacities[s] and any(gpu <= rack for rack in compatibility[s])]
        source = j.get('source_site')
        if source:
            eligible = [s for s in eligible if s == source]
        if not eligible:
            output[j['job_uid']] = dict(blocked, reason='GANG_COMPATIBILITY_UNAVAILABLE')
            continue
        if j['state_at_D1_cutoff'] == 'RUNNING':
            end = float('inf') if n == 0 else n
            feasible = [s for s in eligible if fits(s, 0, end, gpu)]
            if feasible:
                output[j['job_uid']] = assign(j, 0, feasible[0], eligible, not bool(source))
            else:
                output[j['job_uid']] = dict(blocked, reason='RUNNING_INITIAL_CAPACITY_UNAVAILABLE', compatible_sites=eligible)
            continue
        # Strict FCFS start order; later gangs may not backfill ahead of a
        # preceding unresolved request. No arbitrary large sentinel starts.
        prior = [o for o in output.values() if o['state_at_D1_cutoff'] == 'PENDING']
        if any(o['status'] == 'BLOCKED' for o in prior):
            output[j['job_uid']] = dict(blocked, reason='FCFS_PREDECESSOR_UNRESOLVED', compatible_sites=eligible)
            continue
        earliest = max([0] + [o['reference_start'] for o in prior])
        candidates = sorted({earliest} | {int(b) for s in eligible for a, b, g in reservations[s]
                                         if math.isfinite(b) and b >= earliest})
        found = next(((t, s) for t in candidates for s in eligible if fits(s, t, t+n, gpu)), None)
        if found is None:
            output[j['job_uid']] = dict(blocked, reason='CAUSAL_RELEASE_AUTHORITY_UNAVAILABLE', compatible_sites=eligible)
        else:
            output[j['job_uid']] = assign(j, found[0], found[1], eligible, not bool(source))
    rows = [output[uid] for uid in sorted(ids)]
    require(len(rows) == len(jobs) and {r['job_uid'] for r in rows} == set(ids), 'WORKLOAD_DROP')
    blocked = [r for r in rows if r['status'] == 'BLOCKED']
    assigned = [r for r in rows if r['status'] == 'REFERENCE_ASSIGNED']
    known_mass = sum(r['GPU_gang'] * r['service_slots'] / 4 for r in jobs
                     if type(r.get('GPU_gang')) is int and type(r.get('service_slots')) is int)
    fallback_mass = sum(r['GPU_gang'] * r['service_slots'] / 4 for r in assigned if r['fallback_used'])
    return rows, dict(queue_rule=QUEUE_RULE, input_jobs=len(jobs), output_jobs=len(rows),
                      blocked_jobs=len(blocked), assigned_jobs=len(assigned),
                      fallback_jobs=sum(r['fallback_used'] for r in assigned),
                      fallback_share_of_all_rows=sum(r['fallback_used'] for r in assigned)/len(rows) if rows else None,
                      fallback_nominal_GPUh=fallback_mass, measurable_nominal_GPUh=known_mass,
                      fallback_GPUh_share=None if not known_mass else fallback_mass/known_mass,
                      total_workload_GPUh_known=all(type(r.get('GPU_gang')) is int for r in jobs),
                      full_reference_ready=not blocked and bool(rows), workload_drop=False,
                      voltage_reads=0, actual_reads=0, may_reads=0, optimizer_calls=0,
                      population_sha256=digest(jobs), reference_sha256=digest(rows))
