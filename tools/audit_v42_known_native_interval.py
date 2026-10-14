from pathlib import Path
import json,pickle,collections,numpy as np
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from v42_integration.production_case import STATIC
from v42_integration.unified_contract import REPORT,load_contracts
with STATIC.open('rb') as f:data=pickle.load(f)
bundle,jobs,bounds,r=data[:4]
path=REPORT/'B1_NEW_A1_ATTEMPT02/PREPARATION/ISSUE_ONLY_DDAY_KNOWN_REFERENCE.json'
audit=json.loads(path.read_text(encoding='utf-8'))
ref=audit['new_issue_only_Dday_reference']; assignments=ref['assignments']; issue=audit['issue_seconds']
sites=sorted(r.capacities); H=max(max(b.latest_completion for b in bounds.values()),max(t+1 for s,t in r.fixed_gpu) if r.fixed_gpu else 0)
known=np.zeros((H,len(sites))); fixed=np.zeros_like(known); pending=np.zeros_like(known); running=np.zeros_like(known)
rows=[]
for uid,j in jobs.items():
    if j.state=='PENDING':
        rec=assignments[uid]; start=int(round((rec['reference_start_seconds']-issue)/900));site=rec['reference_site']; target=pending
        q50_release=int(round((rec['nominal_release_seconds']-issue)/900))
        rows.append(dict(uid=uid,state=j.state,start=start,site=site,native_end=start+j.service_slots,
            public_ceil_release=q50_release,release_alignment=q50_release==start+j.service_slots))
    else:start=j.reference_start;site=j.reference_site;target=running
    target[max(0,start):min(H,start+j.service_slots),sites.index(site)]+=j.gpu
for (s,t),n in r.fixed_gpu.items():
    if 0<=t<H:fixed[t,sites.index(s)]+=n
known=pending+running;allgpu=known+fixed
caps=np.array([r.capacities[s] for s in sites])
violations=[dict(native_slot=int(t),site=sites[s],pending=float(pending[t,s]),running=float(running[t,s]),
    fixed=float(fixed[t,s]),total=float(allgpu[t,s]),capacity=int(caps[s])) for t,s in np.argwhere(allgpu>caps+1e-9)]
start_hist=dict(collections.Counter(x['start'] for x in rows));site_hist=dict(collections.Counter(x['site'] for x in rows))
q50=bundle['C0_Q50']; min_required=[]
from v42_integration.production_case import TIMING
import pandas as pd
lo=pd.read_csv(TIMING).Q10.to_numpy()
for t in range(96):
    lower=sum(float(q50[h])*float(lo[min(t-4*h,len(lo)-1)]) for h in range(24) if t>=4*h)
    free_gpu_hours=sum(float(np.maximum(caps-allgpu[u+24],0).sum())/4 for u in range(t+1))
    min_required.append(dict(dday_slot=t,minimum_cumulative_CC4_GPUh=lower,total_capacity_free_GPUh=free_gpu_hours,
        necessary_capacity_PASS=free_gpu_hours+1e-7>=lower))
out=dict(bindings=load_contracts()['bindings'],Native_calls=0,model_built=False,Actual_bank_read=False,
    PendingUIDs=len(rows),public_native_release_mismatches=sum(not x['release_alignment'] for x in rows),
    start_histogram=start_hist,site_histogram=site_hist,capacity_violations=violations,
    known_GPUh_Dday=float(known[24:120].sum()/4),fixed_GPUh_Dday=float(fixed[24:120].sum()/4),
    per_site_peak=dict(zip(sites,allgpu.max(axis=0).tolist())),CC4_necessary_capacity=min_required,
    source_reference_SHA=ref['reference_sha'],source_reference_path=str(path))
(REPORT/'KNOWN_FCFS_NATIVE_INTERVAL_REPLAY.json').write_text(json.dumps(out,indent=2,allow_nan=False),encoding='utf-8')
np.savez_compressed(REPORT/'KNOWN_FCFS_NATIVE_INTERVAL_PROFILE.npz',sites=np.array(sites),known=known,fixed=fixed,pending=pending,running=running)
print(json.dumps({k:out[k] for k in ('PendingUIDs','public_native_release_mismatches','start_histogram','capacity_violations','known_GPUh_Dday','fixed_GPUh_Dday','per_site_peak')}))
print(json.dumps(dict(CC4_necessary_failed_slots=[x['dday_slot'] for x in min_required if not x['necessary_capacity_PASS']])))
