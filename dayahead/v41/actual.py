"""Counterfactual Actual: frozen policy geometry plus realized exogenous values.

No scheduling, queue repair, probability, route search or optimizer is called.
Exact completion times use 900-second slot units; occupancy is sampled at the
existing slot starts. Unselected jobs remain explicit service backlog.
"""
from copy import deepcopy
import math
from types import FunctionType
import zipfile
import re
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from dayahead.v40d_actual.job_replay import timestamp
from dayahead.v40g_segments.canonical import validate, identities, occupancy, terminal
from .reserve import require


def replay_jobs(jobs, observations, *, issue_time, site_capacity, racks):
    frozen = identities(jobs); issue = timestamp(issue_time)
    rack_map = {(r.site, r.rack_id): r for r in racks}
    ledger = []; rack_ledger = []; max_error = 0.
    for original in sorted(jobs, key=lambda r: r['job_uid']):
        row = deepcopy(original); validate(row); uid = row['job_uid']; g = row['requested_GPU']
        require(uid in observations, 'REALIZED_RUNTIME_MISSING:' + uid)
        o = observations[uid]; start = timestamp(o['start_time']); end = timestamp(o['end_time'])
        total = (end - start).total_seconds()
        require(math.isfinite(total) and total > 0 and int(o['gpus_requested']) == g,
                'REALIZED_RUNTIME_OR_GPU_INVALID:' + uid)
        if row['state_at_issue'] == 'RUNNING':
            require(start <= issue < end, 'RUNNING_OBSERVATION_AUTHORITY_DRIFT:' + uid)
            seconds = (end - issue).total_seconds()
        else:
            require(row['state_at_issue'] == 'PENDING', 'UNKNOWN_JOB_STATE')
            seconds = total
        admitted = row['AIDC_site'] != 'UNASSIGNED'
        parts = []
        if admitted:
            if row.get('migration_selected'):
                require(row['state_at_issue'] == 'RUNNING', 'NEW_ACTUAL_PENDING_MIGRATION')
                source, destination = row['compute_segments']; event = row['migration_events'][0]
                source_seconds = min(seconds, event['checkpoint'] * 900)
                if source_seconds:
                    parts.append(dict(site=source['site'], start=0., end=source_seconds / 900,
                        Rack=row['initial_Rack_label'], phase='SOURCE'))
                remaining = seconds - source_seconds
                if remaining:
                    parts.append(dict(site=destination['site'], start=float(event['restart_end']),
                        end=event['restart_end'] + remaining / 900, Rack=row['Rack_label'], phase='DESTINATION'))
            else:
                begin = 0 if row['state_at_issue'] == 'RUNNING' else row['start_slot']
                parts = [dict(site=row['AIDC_site'], start=float(begin), end=begin + seconds / 900,
                              Rack=row['Rack_label'], phase='SINGLE')]
            for part in parts:
                require(part['site'] in site_capacity and (part['site'], part['Rack']) in rack_map,
                        'FROZEN_SITE_OR_RACK_INVALID:' + uid)
                require(g <= site_capacity[part['site']] and g <= rack_map[part['site'], part['Rack']].capacity,
                        'FROZEN_GANG_RACK_INCOMPATIBLE:' + uid)
                rack_ledger.append(dict(job_uid=uid, site=part['site'], rack_id=part['Rack'],
                    start=part['start'], end=part['end'], requested_GPU=g, phase=part['phase']))
            computed = sum((p['end'] - p['start']) * 900 for p in parts)
            max_error = max(max_error, abs(computed - seconds))
            require(abs(computed - seconds) < 1e-6, 'ACTUAL_SERVICE_LOSS:' + uid)
            require(all(a['end'] <= b['start'] for a, b in zip(parts, parts[1:])), 'ACTUAL_COMPUTE_OVERLAP')
            remaining = sum(max(0., p['end'] - max(120, p['start'])) * 900 for p in parts)
            actual_end = parts[-1]['end']
            status = 'EXECUTION_ACCOUNTED'
        else:
            # The sealed policy chose no modeled site. Do not invent an
            # observed B-policy site or silently remove this service demand.
            remaining = seconds; actual_end = None; status = 'FROZEN_UNADMITTED_BACKLOG'
        row.update(status=status, frozen_policy_admitted=admitted, actual_compute_segments=parts,
            actual_runtime_seconds=total, actual_service_seconds=seconds, actual_runtime_slots=math.ceil(seconds / 900),
            actual_runtime_source='KESTREL_OBSERVED_END_MINUS_START',
            actual_runtime_gt_requested_walltime=total > row['requested_walltime_seconds'],
            actual_execution_start=(row['start_slot'] if admitted and row['state_at_issue'] == 'PENDING' else None),
            actual_residual_start=(parts[0]['start'] if parts else None), actual_execution_end=actual_end,
            actual_execution_origin='V41_FROZEN_DA_START_SITE_AND_MIGRATION',
            actual_Rack=parts[-1]['Rack'] if parts else None,
            frozen_AIDC_site=row['AIDC_site'], frozen_planned_start=row['start_slot'], frozen_planned_end=row['end_slot'],
            frozen_Rack_if_any=row['Rack_label'], start_delay_slots=0, start_delay_seconds=0,
            delayed_by_GPU_capacity=False, delayed_by_Rack_capacity=False,
            unfinished_at_H=remaining > 0, remaining_runtime_at_H=remaining,
            remaining_GPU_hours_at_H=remaining * g / 3600,
            backlog_GPU_hours=(seconds * g / 3600 if not admitted else 0.),
            migration_frozen=bool(row.get('migration_selected')),
            migration_executed=bool(row.get('migration_selected')) and len(parts) == 2,
            post_H_site=(parts[-1]['site'] if remaining > 0 else None) if parts else 'UNASSIGNED',
            post_H_completion_time=actual_end if admitted and actual_end > 120 else None,
            WAN_state=deepcopy(row.get('accepted_A0_assignment_and_WAN', {})))
        if admitted:
            row['terminal_segment_state'] = terminal(row, actual=True)
            from dayahead.v40h.pre_day_complete import classify
            row['counterfactual_day_classification'] = classify(original, o, issue, execution_segments=parts)
        else:
            row['counterfactual_day_classification'] = dict(status='FROZEN_UNADMITTED_BACKLOG',
                source_observed_end_used_for_completion=False, service_excluded=False,
                service_backlog_GPUh=seconds*g/3600, authority='V41_FROZEN_ADMISSION_COUNTERFACTUAL_REPLAY')
        ledger.append(row)
    gpu, contributions = occupancy(ledger, sorted(site_capacity), actual=True)
    violations = [dict(slot=int(t), site=s, actual_GPU=int(gpu[t, i]), capacity=int(site_capacity[s]))
                  for i, s in enumerate(sorted(site_capacity)) for t in np.flatnonzero(gpu[:, i] > site_capacity[s])]
    site_rows = [dict(slot=t, site_id=s, occupied_GPU_slots=int(gpu[t, i]), GPU_capacity=site_capacity[s])
                 for t in range(96) for i, s in enumerate(sorted(site_capacity))]
    require(identities(jobs) == frozen, 'ACTUAL_MUTATED_DAYAHEAD_DECISION')
    return dict(job_ledger=ledger, rack_ledger=rack_ledger, rack_waits=[], site_occupancy=site_rows,
        pre_day_complete=[], counterfactual_pre_day_complete_proofs=[r['counterfactual_day_classification'] for r in ledger
            if r['counterfactual_day_classification']['status']=='PRE_DAY_COMPLETE'], counters=dict(job_count=len(ledger),
            frozen_unadmitted_jobs=sum(not r['frozen_policy_admitted'] for r in ledger),
            frozen_unadmitted_GPUh=sum(r['backlog_GPU_hours'] for r in ledger),
            start_changes=0, site_changes=0, migration_decision_changes=0, Actual_optimizer_calls=0),
        canonical_actual_audit=dict(status='PASS', service_max_error_seconds=max_error, **frozen),
        capacity_audit=dict(status='FAIL' if violations else 'PASS', violations=violations,
                            policy_start_reoptimized=False, capacity_delay_inserted=False),
        GPU=gpu, contributions=contributions)


def compare_occupancy(replay, capacity):
    gpu, raw = occupancy(replay['job_ledger'], sorted(capacity), actual=True)
    require(np.array_equal(gpu, replay['GPU']), 'ACTUAL_OCCUPANCY_RECALCULATION_MISMATCH')
    require(not replay['capacity_audit']['violations'], 'FROZEN_ACTUAL_SITE_CAPACITY_EXCEEDED')
    contributions = [dict(job_uid=r['job_uid'], slot=r['slot'], site=r['site_id'], occupied_GPU=r['GPU']) for r in raw]
    return gpu, contributions, dict(status='PASS', independent_canonical_occupancy=True,
        duplicate_UID_count=0, SITE_CAPACITY_VIOLATIONS_TOTAL=0, GPU_slot_sum=int(gpu.sum()))


def power_from_execution(repo, replay, capacity, weather):
    from dayahead.v40d_actual import power_replay as original
    namespace = dict(vars(original)); namespace['compare_occupancy'] = compare_occupancy
    fn = original.power_from_execution
    return FunctionType(fn.__code__, namespace, fn.__name__, fn.__defaults__, fn.__closure__)(repo, replay, capacity, weather)


def realized_workload(day, output=None):
    """Only called after the policy freeze: historical arriving GPU service."""
    from .data import KESTREL_ARCHIVE, issue_time, SLOT_NS
    begin = issue_time(day) + pd.Timedelta(hours=6); end = begin + pd.Timedelta(days=1)
    frames = []
    with zipfile.ZipFile(KESTREL_ARCHIVE) as archive:
        for name in sorted(archive.namelist()):
            if not re.search(r'year=\d{4}/month=\d{1,2}/.*\.parquet$', name):
                continue
            with archive.open(name) as stream:
                f = pq.read_table(stream, columns=['id', 'submit_time', 'start_time', 'end_time', 'gpus_requested'],
                    filters=[('submit_time', '>=', begin.to_pydatetime()), ('submit_time', '<', end.to_pydatetime())]).to_pandas()
            if not len(f):
                continue
            authorized = f.gpus_requested.gt(0) & np.isfinite(f.gpus_requested)
            require(not (authorized & (f.start_time.isna() | f.end_time.isna())).any(), 'REALIZED_WORKLOAD_LABEL_MISSING')
            valid = authorized & f.end_time.gt(f.start_time) & f.start_time.ge(f.submit_time)
            if valid.any():
                frames.append(f[valid].copy())
    require(bool(frames), 'REALIZED_WORKLOAD_DAY_HAS_NO_VERIFIABLE_CONTRIBUTORS')
    work = pd.concat(frames, ignore_index=True)
    require(work.id.is_unique, 'DUPLICATE_REALIZED_WORKLOAD_UID')
    for col in ('submit_time', 'start_time', 'end_time'):
        work[col] = pd.to_datetime(work[col], utc=True)
    weight = work.gpus_requested * (work.end_time - work.start_time).dt.total_seconds() / 3600
    ix = ((work.submit_time.dt.as_unit('ns').astype('int64').to_numpy() - begin.value) // SLOT_NS).astype(int)
    atomic = np.bincount(ix, weights=weight.to_numpy(), minlength=96)
    cumulative = np.lib.stride_tricks.sliding_window_view(atomic, 16).sum(axis=1)
    sources = None
    if output is not None:
        from .persistence import table
        from .preflight import record
        from .data import KESTREL_ARCHIVE_SHA256
        work['GPU_service_GPUh'] = weight.to_numpy(); work['arrival_slot'] = ix
        source = record(KESTREL_ARCHIVE)
        require(source['sha256'] == KESTREL_ARCHIVE_SHA256, 'ACTUAL_KESTREL_ARCHIVE_DRIFT')
        sources = dict(authority=source, daily_slice=table(output / 'REALIZED_WORKLOAD_CONTRIBUTORS.parquet', work),
                       units='GPUh', start=begin.isoformat(), end=end.isoformat())
    return dict(day=day, arriving_GPU_service_work_15min_GPUh=atomic.tolist(), H4_actual_GPUh=cumulative.tolist(),
        target_contributors=len(work), total_arriving_GPUh=float(atomic.sum()),
        source_membership=sources,
        synthetic_future_jobs=0, AIDC_scheduling_calls=0, target_definition='sum(gpus_requested*(end-start)/3600) by original submit time')
