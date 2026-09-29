"""Canonical view of the source-preserving native bundle.

The bundle intentionally retains PR93 reference fields for forensic comparison.
Consumers use this view, not inherited requested-duration mass or FLEX fields.
This is an input adapter, not an accepted native scheduling result.
"""
from .common import require,MODEL
from v42_job_capability import Job,checkpoint_records


def canonical_jobs(bundle):
    result=[]
    for r in bundle['known_population']:
        if not r['planning_eligible']:continue
        n=r['service_slots'];g=r['GPU_gang'];start=r['reference_start_if_authorized']
        require(r['runtime_authority']==MODEL and n>=0,'FROZEN_Q50_NATIVE_INPUT')
        sites=tuple(s for s,c in bundle['capacities'].items() if g<=c and any(
            rack['aidc_id']==s and g<=rack['compatibility_GPU_limit'] for rack in bundle['racks']))
        mg=False
        if n>0 and r['can_checkpoint_migrate']:
            j=Job(r['job_uid'],r['state'],0,0,start,r['planning_site'],n,g,
                  initial_sites=sites,checkpoint_authorized=True,elapsed_seconds=r['elapsed_seconds'],duration_authority=MODEL)
            mg=any(24<=cp<118 for cp,_ in checkpoint_records(j,start,min(start+n,120)))
        ts=bool(r['can_timeshift']);ps=bool(r['can_prestart_place'])
        result.append(dict(job_id=r['job_uid'],state=r['state'],site=r['planning_site'],
            reference_start=start,nominal_end=start+n,nominal_slots=n,
            exact_compute_seconds=r['exact_service_seconds'],nominal_reserved_GPUh=n*g/4,
            exact_compute_GPUh=r['exact_service_seconds']*g/3600,
            post_H_reserved_GPUh=max(0,start+n-max(start,120))*g/4,
            current_physical_GPU=g if r['state']=='RUNNING' else 0,GPU_gang=g,
            nominal_total_seconds=r['V10_Q50_total_seconds'],elapsed_seconds=r['elapsed_seconds'],
            risk_nominal_completion_issue_slot=r['risk_nominal_completion_issue_slot'],
            runtime_authority=MODEL,can_timeshift=ts,delay_budget_slots=r['delay_budget_slots'],
            can_prestart_place=ps,can_checkpoint_migrate=mg,FLEX=ts or ps or mg,FIX=not(ts or ps or mg),
            compatible_sites=sites,mask_scope='CAUSAL_LOCAL_CANDIDATE_NOT_GLOBAL_FEASIBILITY_WITNESS'))
    return result
