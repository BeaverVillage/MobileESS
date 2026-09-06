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
from dayahead.v40d_actual.power_replay import power_from_execution as old_power
from dayahead.v40d_actual.capacity_audit import write_runtime_audits as old_audits
from dayahead.paper_analysis.storage import write_json


def replay_jobs(jobs, observations, *, issue_time, site_capacity, racks):
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
        checkpoint=row['migration_checkpoint_slot'];ready=row['frozen_execution_ready_slot']
        source_seconds=min(residual,checkpoint*900);remaining=residual-source_seconds
        src_uid=uid+'::SOURCE';src=deepcopy(row)
        src.update(job_uid=src_uid,AIDC_site=row['initial_AIDC'],migration_selected=False,start_slot=0,
                   end_slot=checkpoint, safe_duration_slots=max(1,checkpoint))
        src.pop('frozen_execution_ready_slot',None)
        srcobs=deepcopy(o);srcobs['end_time']=issue+timedelta(seconds=source_seconds)
        obs[src_uid]=srcobs;expanded.append(src);root_by_segment[src_uid]=uid;phase[src_uid]='SOURCE'
        if remaining>0:
            dst_uid=uid+'::DESTINATION';dst=deepcopy(row)
            dst.update(job_uid=dst_uid,state_at_issue='PENDING',migration_selected=False,start_slot=ready,
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
                'actual_runtime_seconds':total,'actual_service_seconds':residual,'actual_runtime_slots':math.ceil(residual/900),
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


def power_from_execution(repo,replay,capacity,weather):
    result=old_power(repo,replay.get('segment_replay',replay),capacity,weather)
    if 'root_by_segment' not in replay:return result
    root=replay['root_by_segment']
    rows=[{**r,'job_uid':root[r['job_uid']]} for r in result['job_slot_contributions']]
    if len({(r['job_uid'],r['slot']) for r in rows})!=len(rows):raise RuntimeError('MIGRATION_GANG_DOUBLE_COMPUTE')
    # Independent reconstruction from the final scientific UID segments.
    occ=np.zeros_like(result['occupancy']);sites=sorted(capacity)
    for r in replay['job_ledger']:
        if r['status']!='EXECUTION_ACCOUNTED':continue
        parts=r.get('actual_compute_segments',[{'site':r['AIDC_site'],'start':r['actual_residual_start'],'end':r['actual_execution_end']}])
        for s in parts:
            for t in range(24,120):
                if s['start']<=t<s['end']:occ[t-24,sites.index(s['site'])]+=r['requested_GPU']
    if not np.array_equal(occ,result['occupancy']):raise RuntimeError('FINAL_UID_SEGMENT_OCCUPANCY_MISMATCH')
    result['job_slot_contributions']=rows
    result['occupancy_audit'].update(final_UID_segment_recalculation='PASS',duplicated_original_UID_slot_count=0)
    return result


def write_runtime_audits(output,day,case,jobs,replay,capacity,racks,power):
    result=old_audits(output,day,case,replay.get('segment_frozen_jobs',jobs),replay.get('segment_replay',replay),capacity,racks,power)
    if 'frozen_migration_actual_audit' in replay:
        write_json(Path(output)/'V40G_FROZEN_MIGRATION_ACTUAL_AUDIT.json',replay['frozen_migration_actual_audit'])
        result['scientific_UID_migration_audit']=replay['frozen_migration_actual_audit']
    return result
