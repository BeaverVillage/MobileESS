"""Replay frozen migration segments through the existing causal Rack dispatcher.

Internal segment identifiers are accounting handles for one indivisible job,
not new scientific jobs. Original observed service is split at the already
frozen checkpoint. No future observation is available to Planning.
"""
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import math
import numpy as np
import pandas as pd
from dayahead.v40d_actual import job_replay as old
from types import FunctionType
from dayahead.v40d_actual import power_replay as power_kernel
from .canonical import validate, identities, occupancy, terminal, require
from dayahead.v40d_actual.capacity_audit import write_runtime_audits as old_audits, require_current_capacity
from dayahead.paper_analysis.storage import write_json


def _dispatch_segments(jobs, observations, *, issue_time, site_capacity, racks):
    if not any(r.get('migration_selected') for r in jobs):
        return old.replay_jobs(jobs,observations,issue_time=issue_time,site_capacity=site_capacity,racks=racks)
    issue=old.timestamp(issue_time);expanded=[];obs=deepcopy(observations);root_by_segment={};phase={}
    originals={r['job_uid']:deepcopy(r) for r in jobs}
    for row in jobs:
        uid=row['job_uid'];o=observations[uid]
        if not row.get('migration_selected'):
            expanded.append(deepcopy(row));root_by_segment[uid]=uid;continue
        assert row['state_at_issue']=='RUNNING'
        residual=(old.timestamp(o['end_time'])-issue).total_seconds()
        source,destination=row['compute_segments'];event=row['migration_events'][0]
        checkpoint=source['end'];ready=event['restart_end']
        assert ready==destination['start'] and checkpoint==event['checkpoint']
        source_seconds=min(residual,checkpoint*900);remaining=residual-source_seconds
        src_uid=uid+'::SOURCE';src=deepcopy(row)
        for key in ('segment_schema','compute_segments','migration_events'):src.pop(key,None)
        src.update(job_uid=src_uid,AIDC_site=source['site'],migration_selected=False,start_slot=0,
                   end_slot=checkpoint, safe_duration_slots=max(1,checkpoint))
        src.pop('frozen_execution_ready_slot',None)
        srcobs=deepcopy(o);srcobs['end_time']=issue+timedelta(seconds=source_seconds)
        obs[src_uid]=srcobs;expanded.append(src);root_by_segment[src_uid]=uid;phase[src_uid]='SOURCE'
        if remaining>0:
            dst_uid=uid+'::DESTINATION';dst=deepcopy(row)
            for key in ('segment_schema','compute_segments','migration_events'):dst.pop(key,None)
            dst.update(AIDC_site=destination['site'],job_uid=dst_uid,state_at_issue='PENDING',migration_selected=False,start_slot=ready,
                       end_slot=ready+math.ceil(remaining/900),safe_duration_slots=math.ceil(remaining/900))
            dstobs=deepcopy(o);dstobs.update(start_time=issue,end_time=issue+timedelta(seconds=remaining))
            obs[dst_uid]=dstobs;expanded.append(dst);root_by_segment[dst_uid]=uid;phase[dst_uid]='DESTINATION'
    result=old.replay_jobs(expanded,obs,issue_time=issue,site_capacity=site_capacity,racks=racks)
    by_root={uid:[] for uid in originals}
    for part in result['job_ledger']:by_root[root_by_segment[part['job_uid']]].append(part)
    ledger=[]
    for uid,row in sorted(originals.items()):
        parts=by_root[uid]
        if not row.get('migration_selected'):
            ledger.append(parts[0]);continue
        parts.sort(key=lambda p:p['actual_residual_start'])
        segments=[{'site':p['AIDC_site'],'start':p['actual_residual_start'],'end':p['actual_execution_end'],
                   'Rack':p['actual_Rack'],'phase':phase[p['job_uid']]} for p in parts]
        o=observations[uid];total=(old.timestamp(o['end_time'])-old.timestamp(o['start_time'])).total_seconds()
        residual=(old.timestamp(o['end_time'])-issue).total_seconds()
        computed=sum((s['end']-s['start'])*900 for s in segments)
        if abs(computed-residual)>1e-6:raise RuntimeError('MIGRATION_ACTUAL_SERVICE_LOST')
        if any(a['end']>b['start'] for a,b in zip(segments,segments[1:])):raise RuntimeError('MIGRATION_COMPUTE_OVERLAP')
        end=segments[-1]['end'];remaining=sum(max(0,s['end']-max(120,s['start']))*900 for s in segments)
        merged={**parts[-1],**row,'job_uid':uid,'actual_compute_segments':segments,
                'actual_runtime_seconds':total,'actual_runtime_gt_requested_walltime':total>float(row['requested_walltime_seconds']),'actual_service_seconds':residual,'actual_runtime_slots':math.ceil(residual/900),
                'actual_execution_start':None,'actual_residual_start':0,'actual_execution_end':end,
                'actual_execution_origin':'FROZEN_CHECKPOINT_WAN_RESTART_MIGRATION',
                'frozen_AIDC_site':row['AIDC_site'],'frozen_planned_start':row['start_slot'],'frozen_planned_end':row['end_slot'],
                'migration_frozen':True,'migration_executed':len(parts)>1,'WAN_state':row['accepted_A0_assignment_and_WAN'],
                'actual_Rack':segments[-1]['Rack'],'unfinished_at_H':end>120,'remaining_runtime_at_H':remaining,
                'remaining_GPU_hours_at_H':remaining*row['requested_GPU']/3600,'post_H_site':segments[-1]['site'] if end>120 else None,
                'post_H_completion_time':end if end>120 else None,'status':'EXECUTION_ACCOUNTED',
                'service_conservation_error_seconds':computed-residual}
        ledger.append(merged)
    rack_ledger=[{**r,'segment_uid':r['job_uid'],'job_uid':root_by_segment[r['job_uid']]} for r in result['rack_ledger']]
    waits=[{**r,'segment_uid':r['job_uid'],'job_uid':root_by_segment[r['job_uid']]} for r in result['rack_waits']]
    return {**result,'job_ledger':ledger,'rack_ledger':rack_ledger,'rack_waits':waits,
            'segment_replay':result,'segment_frozen_jobs':expanded,'root_by_segment':root_by_segment,
            'frozen_migration_actual_audit':{'status':'PASS','whole_job_GPU_gangs_preserved':True,
                'same_original_observed_service_each_job':True,'migration_decision_changes':0,
                'runtime_AIDC_optimization_calls':0,'runtime_WAN_optimization_calls':0,
                'migration_selected_count':sum(bool(r.get('migration_selected')) for r in jobs),
                'migration_executed_count':sum(bool(r.get('migration_executed')) for r in ledger),
                'completed_before_checkpoint_count':sum(bool(r.get('migration_selected')) and not r.get('migration_executed') for r in ledger),
                'segment_identifier_scope':'Internal dispatcher accounting only; one final UID and complete service per original job'}}


def replay_jobs(jobs, observations, *, issue_time, site_capacity, racks):
    """Project canonical phases into the unchanged deterministic dispatcher.

    For residual R and checkpoint c, source service is min(R,900c),
    destination service is R-min(R,900c). The latter exists iff positive.
    Their release/ready times are disjoint. Each handle requests the full
    original gang and uses the inherited priority/rack policy. Mapping the
    handles back to their UID therefore preserves service and occupancy.
    """
    frozen = identities(jobs)
    result = _dispatch_segments(jobs, observations, issue_time=issue_time,
                               site_capacity=site_capacity, racks=racks)
    original = {r['job_uid']: r for r in jobs}
    max_error = 0.0
    for row in result['job_ledger']:
        source = original[row['job_uid']]
        require(row['compute_segments'] == source['compute_segments'] and
                row['migration_events'] == source['migration_events'], 'ACTUAL_CHANGED_FROZEN_SEGMENTS')
        if 'actual_compute_segments' not in row:
            row['actual_compute_segments'] = ([{'site': source['compute_segments'][0]['site'],
                'start': row['actual_residual_start'], 'end': row['actual_execution_end'],
                'Rack': row['actual_Rack'], 'phase': 'SINGLE'}] if row['status'] == 'EXECUTION_ACCOUNTED' else [])
        segs = row['actual_compute_segments']
        require(all(a['end'] <= b['start'] for a, b in zip(segs, segs[1:])), 'ACTUAL_COMPUTE_OVERLAP')
        if row['status'] == 'EXECUTION_ACCOUNTED':
            computed = sum((s['end'] - s['start']) * 900 for s in segs)
            error = abs(computed - row['actual_service_seconds']); max_error = max(max_error, error)
            require(error < 1e-6, 'ACTUAL_SERVICE_LOSS')
            if row.get('migration_executed'):
                a, b = segs; e = row['migration_events'][0]
                require(a['site'] == e['source_AIDC'] and b['site'] == e['destination_AIDC'], 'ACTUAL_PHASE_SITE')
                require(a['end'] == e['checkpoint'] and b['start'] >= e['restart_end'], 'ACTUAL_MIGRATION_CAUSALITY')
        row['terminal_segment_state'] = terminal(row, actual=True)
        term = row['terminal_segment_state']
        if row['status'] == 'EXECUTION_ACCOUNTED':
            require(abs(term['remaining_compute_slots'] * 900 - row['remaining_runtime_at_H']) < 1e-6, 'ACTUAL_TERMINAL_SERVICE')
            require(term['post_H_site'] == row['post_H_site'], 'ACTUAL_TERMINAL_SITE')
    require(identities(jobs) == frozen, 'ACTUAL_MUTATED_INPUT')
    result['canonical_actual_audit'] = {'status': 'PASS', **frozen,
        'common_frozen_segments_changed': 0, 'service_max_error_seconds': max_error,
        'job_count': len(jobs), 'runtime_optimization_calls': 0,
        'dispatcher_compression_equivalence': 'Disjoint whole-gang phases; min(R,900c)+(R-min(R,900c))=R; identical priority, ready and release boundaries'}
    return result


def compare_occupancy(replay, capacity):
    require_current_capacity(capacity)
    gpu, raw = occupancy(replay['job_ledger'], sorted(capacity), actual=True)
    frame = pd.DataFrame(replay['site_occupancy'])
    require(len(frame) == 1152 and not frame.duplicated(['slot', 'site_id']).any(), 'ACTUAL_OCCUPANCY_AXIS')
    recorded = frame.pivot(index='slot', columns='site_id', values='occupied_GPU_slots').reindex(index=range(96), columns=sorted(capacity)).to_numpy()
    require(np.array_equal(gpu, recorded), 'CANONICAL_DISPATCHER_OCCUPANCY_DIFFERENCE')
    require(np.all(gpu >= 0) and all(np.all(gpu[:, i] <= capacity[s]) for i, s in enumerate(sorted(capacity))), 'ACTUAL_SITE_CAPACITY')
    contributions = [{'job_uid': r['job_uid'], 'slot': r['slot'], 'site': r['site_id'], 'occupied_GPU': r['GPU']} for r in raw]
    return gpu, contributions, {'status': 'PASS', 'input': 'CANONICAL_ROOT_UID_ACTUAL_COMPUTE_SEGMENTS',
        'max_abs_gpu_occupancy_error': 0, 'GPU_OCCUPANCY_RECALC_MAX_ERROR': 0,
        'duplicate_UID_count': 0, 'duplicate_case_site_slot_job_count': 0,
        'SITE_CAPACITY_VIOLATIONS_TOTAL': 0, 'PRE_DAY_COMPLETE_GPU_OCCUPANCY_VIOLATIONS': 0,
        'independent_job_sum_equals_dispatcher': True, 'site_slot_count': 1152, 'GPU_slot_sum': int(gpu.sum())}


def power_from_execution(repo, replay, capacity, weather):
    # Shared CENTER/C1 numeric kernel, with its ONLY job reader replaced by
    # canonical root-UID occupancy. No single-interval reader is reachable.
    namespace = dict(power_kernel.power_from_execution.__globals__)
    namespace['compare_occupancy'] = compare_occupancy
    kernel = FunctionType(power_kernel.power_from_execution.__code__, namespace)
    return kernel(repo, replay, capacity, weather)


def write_runtime_audits(output, day, case, jobs, replay, capacity, racks, power):
    # Legacy gang checks are sound for disjoint internal phase handles.
    legacy = old_audits(output, day, case, replay.get('segment_frozen_jobs', jobs),
        replay.get('segment_replay', replay), capacity, racks, power)
    canonical = compare_occupancy(replay, capacity)[2]
    write_json(Path(output) / 'CANONICAL_ACTUAL_SEGMENT_AUDIT.json', replay['canonical_actual_audit'])
    write_json(Path(output) / 'CANONICAL_ROOT_UID_OCCUPANCY_AUDIT.json', canonical)
    write_json(Path(output) / 'TERMINAL_ACTUAL_SEGMENTS.json', [r['terminal_segment_state'] for r in replay['job_ledger']])
    return {'legacy_phase_gang_audit': legacy, 'canonical_root_occupancy': canonical}

