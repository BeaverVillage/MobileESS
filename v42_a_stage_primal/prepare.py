"""Deterministic local integer proposals from a preserved full-domain primal.

No optimization is invoked. Proposals are not scientific feasible points.
Only an independently replayed original-model LP repair may admit a new UB.
"""
import gzip,pickle
from fractions import Fraction
import numpy as np
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_lexcases.policy import OUT,ROOT
from v42_a_stage_lexfull.runner import objective_value

def proposals(state,s,x,target):
    known=state['scientific_descriptor']['known'];data=state['data'];answer=[]
    current=objective_value(s,x,'shift_magnitude');required=current-Fraction(target)
    if required<=0 or required.denominator!=1:return []
    obj=s.objective('shift_magnitude').coefficients()
    for u in state['reference_descriptor']['units']:
        if not u.get('stay_count') or u.get('optional') or u.get('retained_mixed_flow'):continue
        job=data[1][u['uid']];ys=u['v']['y']
        for (site,start),e in sorted(ys.items()):
            if e[0]!='v' or s.vtypes[e[1]] not in ('B','I') or x[e[1]]<1-1e-5:continue
            src=int(e[1])
            for (newsite,newstart),ne in sorted(ys.items()):
                if newsite!=site or ne[0]!='v':continue
                dst=int(ne[1])
                if s.vtypes[dst] not in ('B','I') or obj.get(src,Fraction(0))-obj.get(dst,Fraction(0))!=required:continue
                if x[src]-1<s.lower[src]-1e-6 or x[dst]+1>s.upper[dst]+1e-6:continue
                effects={}
                for slot in range(start,start+job.service_slots):effects[slot]=effects.get(slot,0)-job.gpu
                for slot in range(newstart,newstart+job.service_slots):effects[slot]=effects.get(slot,0)+job.gpu
                feasible=True;worst=0.
                for slot,change in effects.items():
                    if not change:continue
                    enc=known.get((site,slot))
                    if enc is None or enc[0]!='v':feasible=False;break
                    j=int(enc[1]);value=x[j]+change
                    if value<s.lower[j]-1e-6 or value>s.upper[j]+1e-6:feasible=False;break
                    worst=max(worst,value/s.upper[j] if s.upper[j]>0 else 0.)
                if feasible:answer.append(dict(class_id=u['class_key'],uid=u['uid'],source=src,destination=dst,
                    source_site=site,source_start=int(start),destination_start=int(newstart),count_transfer=1,
                    proposed_shift=int(target),exact_objective_reduction=str(required),worst_GPU_load_ratio=worst,
                    native_solve_required=True,scientific_feasibility_claimed=False))
    return sorted(answer,key=lambda p:(p['worst_GPU_load_ratio'],p['class_id'],p['source'],p['destination']))

def prepare():
    path=OUT/'PRIMAL_PROPOSALS.json'
    if path.exists():raise PermissionError('PRIMAL_PROPOSALS_ALREADY_PREPARED')
    build=read(OUT/'LEX_FULL_BUILD_VERIFICATION.json')
    if record(build['state']['path'])!=build['state']:raise ValueError('FULL_ORIGINAL_STATE_DRIFT')
    with gzip.open(build['state']['path'],'rb') as f:p=pickle.load(f)
    authority=read(ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008/ROW_ATTRIBUTION_AUTHORITY.json')['global_descriptor']
    if record(authority['path'])!=authority:raise ValueError('SCIENTIFIC_GLOBAL_DESCRIPTOR_DRIFT')
    with gzip.open(authority['path'],'rb') as f:p['state']['scientific_descriptor']=pickle.load(f)
    previous=read(OUT/'P2_CASE_CHECKPOINT.json');point=previous['incumbent']['point']
    if record(point['path'])!=point:raise ValueError('PRESERVED_INTEGER_POINT_DRIFT')
    x=np.load(point['path'])['X'];candidates=proposals(p['state'],p['snapshot'],x,948)
    atomic(path,dict(PASS=True,static_only=True,native_solve_calls=0,scientific_feasibility_claimed=False,
        candidate_deletion=False,global_bound_claimed=False,original_full_model=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),
        preserved_incumbent=point,global_descriptor=authority,prior_valid_global_LB=948.,proposals=candidates,count=len(candidates)))
    print('PRIMAL_STATIC_PROPOSALS',len(candidates),flush=True)
    return candidates
if __name__=='__main__':prepare()
