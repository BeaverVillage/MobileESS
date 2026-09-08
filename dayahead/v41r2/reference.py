"""Causal issue-state reference rematerialization, with no optimization inputs.

V37 ready PENDING membership has release 0 at D-1 18:00. V39D numeric
site/rack preference and V41R1 event first-fit are retained. Old resource
waiting is an output, never a new exogenous release constraint.
"""
from copy import deepcopy
from collections import defaultdict
import numpy as np
CONTRACT='V41R2_Q90_CAUSAL_ISSUE_STATE_780_REFERENCE_V1'

def materialize(jobs,scheduling,capacity):
    priority={j.job_id:j.priority_key for j in scheduling}
    assert set(priority)=={r['job_uid'] for r in jobs}
    result=deepcopy(jobs);old={r['job_uid']:r for r in jobs}
    horizon=20001+max(r['safe_duration_slots'] for r in jobs)
    load={s:np.zeros(horizon,dtype=np.int64) for s in capacity.aidc_ids}
    events={0};waiting=[]
    def reserve(r,s,t,rack):
        end=t+r['safe_duration_slots'];g=r['requested_GPU']
        assert np.all(load[s][t:end]+g<=capacity.site_capacity[s])
        load[s][t:end]+=g;events.add(end)
        r.update(AIDC_site=s,start_slot=t,end_slot=end,Rack_label=rack,initial_Rack_label=rack)
        r.pop('accepted_A0_assignment_and_WAN',None)
    for r in sorted((r for r in result if r['state_at_issue']=='RUNNING'),key=lambda r:r['job_uid']):
        if r['AIDC_site']=='UNASSIGNED':
            # Old spatial authority legitimately omitted pre-D00 complete work.
            # No fabricated physical source for these historical residuals.
            assert r['end_slot']<=24,'UNASSIGNED_RUNNING_WITHIN_DAY_REQUIRES_SOURCE_AUTHORITY'
            continue
        reserve(r,r['AIDC_site'],r['start_slot'],r['Rack_label'])
    for r in sorted((r for r in result if r['state_at_issue']=='PENDING'),key=lambda r:priority[r['job_uid']]):
        eligible=[(s,p.rack_pool_id) for s in capacity.aidc_ids if capacity.site_capacity[s]>=r['requested_GPU']
            for p in sorted(capacity.eligible_racks(s,r['requested_GPU']),key=lambda p:p.rack_pool_id)]
        chosen=None
        for t in sorted(events):
            if t>20000:break
            for s,rack in eligible:
                if np.all(load[s][t:t+r['safe_duration_slots']]+r['requested_GPU']<=capacity.site_capacity[s]):
                    chosen=(s,t,rack);break
            if chosen:break
        if chosen:reserve(r,*chosen)
        else:
            r.update(AIDC_site='UNASSIGNED',Rack_label='UNASSIGNED',initial_Rack_label='UNASSIGNED',start_slot=20001,end_slot=20001+r['safe_duration_slots'])
        waiting.append(dict(job_id=r['job_uid'],ready_issue_slot=0,start_issue_slot=r['start_slot'],
            capacity_wait_slots=r['start_slot'] if chosen else None,natural_delay_slots=0,
            UNASSIGNED_reason=None if chosen else 'NO_COMPATIBLE_GANG_OR_HORIZON_EXHAUSTED'))
    endpoint=defaultdict(lambda:defaultdict(int))
    for r in result:
        if r['AIDC_site']=='UNASSIGNED':continue
        assert capacity.eligible_racks(r['AIDC_site'],r['requested_GPU'])
        endpoint[r['AIDC_site']][r['start_slot']]+=r['requested_GPU']
        endpoint[r['AIDC_site']][r['end_slot']]-=r['requested_GPU']
    evidence=[]
    for s,points in endpoint.items():
        n=0
        for t,delta in sorted(points.items()):
            n+=delta;assert 0<=n<=capacity.site_capacity[s]
            evidence.append(dict(site=s,event=t,GPU=n,capacity=capacity.site_capacity[s]))
        assert n==0
    return result,dict(status='PASS',contract=CONTRACT,rows=waiting,occupancy_events=evidence,
        changed_start_jobs=sum(r['start_slot']!=old[r['job_uid']]['start_slot'] for r in result),
        site_changes=sum(r['AIDC_site']!=old[r['job_uid']]['AIDC_site'] for r in result),
        grid_reads=0,Actual_reads=0,optimizer_calls=0,immutable_issue_RUNNING=True,
        queue_rule='V37 service-tier/FIFO; earliest resource-feasible event from issue slot 0; numeric site/rack preference',
        logical_racks_nonadditive=True,reference_fixed_for_B1=True,explicit_temporal_optimization=False)
