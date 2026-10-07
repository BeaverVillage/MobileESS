"""Compare same-day authority fields without assuming B0/B1 nesting."""
import numpy as np,pickle,gzip
from .common import *
def analyze(day):
    d='DAY_'+day.replace('-','');base=ROOT/'docs/v42_may_b0_zero_margin_holdout'
    b0=read(base/'INPUT/BUNDLE'/d/'PLANNING_INPUT_BUNDLE.json');ref=read(base/'BUNDLE'/d/'REFERENCE.json')
    b1=read(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json');f=failed(day)
    b0rows={r['job_uid']:r for r in ref['rows']};b1rows={r['job_uid']:r for r in b1['known_population']}
    fields=[('state','state'),('GPU_gang','GPU_gang'),('runtime_authority','runtime_authority'),
            ('Q50_total_seconds','V10_Q50_total_seconds'),('service_slots','service_slots'),
            ('nominal_remaining_seconds','nominal_remaining_seconds'),('elapsed_seconds','elapsed_seconds'),
            ('planning_site','planning_site'),('reference_start','reference_start_if_authorized'),
            ('compatible_sites','compatible_sites')]
    differences=[];counts={}
    for k0,k1 in fields:
        delta=[]
        for uid in sorted(b0rows.keys()&b1rows.keys()):
            v0,v1=b0rows[uid].get(k0),b1rows[uid].get(k1)
            if v0!=v1:delta.append(dict(job_uid=uid,field_B0=k0,field_B1=k1,B0=v0,B1=v1))
        counts[k0]=len(delta);differences.extend(delta)
    with (f/'DATA.pkl').open('rb') as h:data=pickle.load(h)
    _,jobs,bounds,r,raw,graphs,old,prep=data
    print(day,'B0 jobs',len(b0rows),'B1 known',len(b1rows),'positive jobs',len(jobs),'diffs',counts,flush=True)
    available=[];missing=[]
    for uid,j in jobs.items():
        row=b0rows.get(uid)
        if row is None:missing.append(dict(job_uid=uid,reason='NO_SAME_DAY_B0_JOB'));continue
        site=row.get('planning_site');start=row.get('reference_start')
        allowed=(site,start) in graphs[uid].events['y'] if not graphs[uid].fixed else None
        available.append(dict(job_uid=uid,B0_site=site,B1_reference_site=j.reference_site,B0_start=start,
            B1_reference_start=j.reference_start,B0_service=row['service_slots'],B1_service=j.service_slots,
            zero_action_start_in_domain=allowed,fixed=graphs[uid].fixed is not None))
    with np.load(base/'BUNDLE'/d/'PLANNING_PHYSICAL.npz') as physical:
        physical_shapes={k:list(physical[k].shape) for k in physical.files}
    facts=dict(day=day,B0_input=record(base/'INPUT/BUNDLE'/d/'PLANNING_INPUT_BUNDLE.json'),
        B0_reference=record(base/'BUNDLE'/d/'REFERENCE.json'),B0_freeze=record(base/'BUNDLE'/d/'PLANNING_FREEZE.json'),
        B1_input=record(PRODUCTION/'inputs'/day/'NATIVE_INPUT.json'),population_ids_equal=set(b0rows)==set(b1rows),
        B0_only=sorted(b0rows.keys()-b1rows.keys()),B1_only=sorted(b1rows.keys()-b0rows.keys()),
        capacities_equal=b0['capacities']==b1['capacities'],field_difference_counts=counts,
        all_job_differences=differences,B0_no_action_domains=available,missing_B0_jobs=missing,
        B0_physical_shapes=physical_shapes,B1_jobs=len(jobs),B0_reference_audit=ref['audit'],
        C0_Q50_equal=b0['forecast_inputs']['current_CC4']['Q50_GPUh']==b1['C0_Q50'],
        C0_Q90_equal=b0['forecast_inputs']['current_CC4']['Q90_GPUh']==b1['C0_Q90'],
        nesting_assumed=False,direct_witness_constructed=False,optimization_calls=0)
    write(label(day)+'_INPUT_IDENTITY.json',facts)
    print(day,'domain examples',available[:3],flush=True)
    print(day,'B0 physical',physical_shapes,flush=True)
    print(day,'B1 reference',b1['reference'],flush=True)
    print(day,'fixed_gpu peak',max(r.fixed_gpu.values(),default=0),'fixed risk jobs',len(raw)-len(jobs),flush=True)
if __name__=='__main__':
    for day in DAYS:analyze(day)
