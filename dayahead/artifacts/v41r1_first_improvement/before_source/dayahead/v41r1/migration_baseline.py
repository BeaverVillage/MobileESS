"""Uniform Q90-consistent baseline; fixed sites, inherited queue and first fit.

Old authorized starts are release bounds. This prospective materialization
can delay starts to restore capacity, but cannot advance, relocate, drop, or
migrate jobs. RUNNING reservations remain immutable. No electrical or realized
execution argument is accepted by this module.
"""
from copy import deepcopy
from collections import defaultdict
import heapq
import numpy as np

CONTRACT='V41R1_Q90_FIXED_SITE_BASELINE_FIRST_FIT_V1'


def materialize(jobs, scheduling, capacity):
    original={r['job_uid']:deepcopy(r) for r in jobs}
    assert len(original)==len(jobs)
    priority={j.job_id:j.priority_key for j in scheduling}
    assert set(priority)==set(original)
    output=deepcopy(jobs)
    limit=20000+max(r['safe_duration_slots'] for r in jobs)
    site_load={s:np.zeros(limit,dtype=np.int64) for s in capacity.aidc_ids}
    rack_load={r.rack_pool_id:np.zeros(limit,dtype=np.int64) for r in capacity.rack_pools}
    rack_cap={r.rack_pool_id:int(r.historical_gpu_capacity) for r in capacity.rack_pools}
    entries=[];reservations=[];waits=[]

    def fits(row,start,rack):
        end=start+row['safe_duration_slots'];g=row['requested_GPU'];site=row['AIDC_site']
        return (np.all(site_load[site][start:end]+g<=capacity.site_capacity[site]) and
                np.all(rack_load[rack][start:end]+g<=rack_cap[rack]))

    def reserve(row,start,rack):
        end=start+row['safe_duration_slots'];g=row['requested_GPU'];site=row['AIDC_site']
        site_load[site][start:end]+=g;rack_load[rack][start:end]+=g
        row.update(start_slot=start,end_slot=end,Rack_label=rack,initial_Rack_label=rack)
        reservations.append((row['job_uid'],site,rack,start,end,g))

    # These jobs have no Day-D site admission. Their full duration stays in the
    # ledger, but materialization never invents a site or a new admitted job.
    for row in output:
        if row.get('migration_selected'):raise ValueError('B0_MIGRATION_MUST_BE_DISABLED')
        if row['AIDC_site']!='UNASSIGNED' and row['AIDC_site'] not in capacity.aidc_ids:
            raise ValueError('Q90_UNKNOWN_SITE_AUTHORITY:'+row['job_uid'])

    running=sorted((r for r in output if r['state_at_issue']=='RUNNING' and r['AIDC_site']!='UNASSIGNED'),key=lambda r:r['job_uid'])
    for row in running:
        rack=row['Rack_label'];start=row['start_slot']
        if rack not in rack_cap or not fits(row,start,rack):raise ValueError('IMMUTABLE_RUNNING_BASELINE_CAPACITY')
        reserve(row,start,rack)
    pending=sorted((r for r in output if r['state_at_issue']=='PENDING' and r['AIDC_site']!='UNASSIGNED'),key=lambda r:priority[r['job_uid']])
    racks_by_uid={r['job_uid']:sorted(p.rack_pool_id for p in capacity.eligible_racks(r['AIDC_site'],r['requested_GPU'])) for r in pending}
    if any(not racks for racks in racks_by_uid.values()):raise ValueError('BASELINE_NO_COMPATIBLE_RACK')
    seen={r['start_slot'] for r in pending}|{r['end_slot'] for r in running}
    clock=list(seen);heapq.heapify(clock)
    while clock and pending:
        t=heapq.heappop(clock)
        if t>20000:raise ValueError('V37_R4A_SCHEDULER_HORIZON_EXHAUSTED')
        remaining=[]
        for row in pending:
            if row['start_slot']>t:remaining.append(row);continue
            rack=next((rack for rack in racks_by_uid[row['job_uid']] if fits(row,t,rack)),None)
            if rack is None:
                blocking=sorted(uid for uid,site,r,a,b,g in reservations if site==row['AIDC_site'] and a<=t<b)
                waits.append(dict(job_id=row['job_uid'],event_issue_slot=t,blocking_job_ids=blocking,
                    site=row['AIDC_site'],reason='REFERENCE_Q90_RESOURCE_CONTENTION'))
                remaining.append(row);continue
            reserve(row,t,rack)
            if row['end_slot'] not in seen:heapq.heappush(clock,row['end_slot']);seen.add(row['end_slot'])
        pending=remaining
    if pending:raise ValueError('BASELINE_QUEUE_DID_NOT_DRAIN')
    for row in output:
        old=original[row['job_uid']]
        for field in ('job_uid','state_at_issue','qos','requested_GPU','safe_duration_slots','safe_duration_seconds','AIDC_site','migration_selected'):
            assert row.get(field)==old.get(field)
        assert row['start_slot']>=old['start_slot']
        if row['state_at_issue']=='RUNNING':assert row['start_slot']==old['start_slot'] and row['end_slot']==old['end_slot']
        entries.append(dict(job_id=row['job_uid'],state_at_issue=row['state_at_issue'],site=row['AIDC_site'],
            old_start_issue_slot=old['start_slot'],new_start_issue_slot=row['start_slot'],
            start_delay_slots=row['start_slot']-old['start_slot'],duration_slots=row['safe_duration_slots'],
            end_issue_slot=row['end_slot'],old_rack=old['Rack_label'],rack=row['Rack_label'],
            priority_key=list(priority[row['job_uid']]),admission_unchanged=True,
            frozen_admitted=row['AIDC_site']!='UNASSIGNED',
            unadmitted_backlog_GPUh=(row['safe_duration_slots']*row['requested_GPU']/4
                if row['AIDC_site']=='UNASSIGNED' else 0),
            unadmitted_Q90_interval_overlaps_Day_D=(row['AIDC_site']=='UNASSIGNED'
                and max(24,row['start_slot'])<min(120,row['end_slot']))))
    # Independent endpoint sweep verifies the resulting table, not the builder arrays.
    events=defaultdict(lambda:defaultdict(int))
    for row in output:
        if row['AIDC_site']=='UNASSIGNED':continue
        for kind,key in (('site',row['AIDC_site']),('rack',row['Rack_label'])):
            events[kind,key][row['start_slot']]+=row['requested_GPU']
            events[kind,key][row['end_slot']]-=row['requested_GPU']
    evidence=[]
    for (kind,key),points in sorted(events.items()):
        used=0;cap=int(capacity.site_capacity[key]) if kind=='site' else rack_cap[key]
        times=sorted(points)
        for index,t in enumerate(times):
            used+=points[t];assert 0<=used<=cap
            if index+1<len(times):evidence.append(dict(kind=kind,resource=key,start_issue_slot=t,end_issue_slot=times[index+1],GPU=used,capacity=cap))
        assert used==0
    return output,dict(status='PASS',contract=CONTRACT,rows=entries,occupancy_events=evidence,queue_waits=waits,
        changed_start_jobs=sum(r['start_delay_slots']>0 for r in entries),site_changes=0,
        admission_changes=0,migration_count=0,advanced_starts=0,
        GPU_feasibility='PASS',rack_feasibility='PASS',
        queue_rule='V37 Job.priority_key: high/urgent, normal, standby, other; submit_time; job_id',
        start_rule='Release at old authorized start; earliest event with full site/rack capacity; non-preemptive whole-job execution',
        rack_rule='V39D stable ascending rack-ID first fit within the frozen site',
        immutable_running=True,grid_reads=0,Actual_reads=0,optimizer_calls=0,
        independent_days=True,post_D24_scheduling='Baseline queue ledger only; Day-D power uses overlap [24,120)')
