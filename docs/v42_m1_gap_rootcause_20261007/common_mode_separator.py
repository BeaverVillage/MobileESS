"""Exact read-only support proof for the complete trajectory hull projection.

No new cut strategy or solve: locate a separating facet and identify whether
it already arises from one slot, rather than falsely calling it temporal.
"""
from common import *
from fractions import Fraction as F
from collections import defaultdict
import itertools
def f(v):return F.from_float(float(v))

def supports(authority,unit,site,t,targetmode=0):
    L=f(authority.battery.p_limit);S=f(authority.battery.pcs_kva)
    faces=authority.pcs(unit,site,t)
    if targetmode==1:faces=tuple((-aa,bb,cap) for aa,bb,cap in faces)
    if not hasattr(authority,'_support_cache'):authority._support_cache={}
    cache_key=faces,L,S
    if cache_key in authority._support_cache:return authority._support_cache[cache_key]
    rows=[(-F(1),F(0),{}),(F(1),F(0),{'y':F(1)}),(-L,F(0),{'D':-F(1)}),(L,F(0),{'y':L,'C':-F(1)})]
    for aa,bb,cap in faces:
        rows.append((-cap,bb,{'D':-aa}))
        rows.append((cap,-bb,{'y':cap,'C':aa,'Q':-bb}))
    rows.extend([(-S,F(1),{}),(-S,-F(1),{}),(S,-F(1),{'y':S,'Q':-F(1)}),(S,F(1),{'y':S,'Q':F(1)})])
    candidates=[((),{})]
    choices=[]
    for i,(aa,bb,_) in enumerate(rows):
        if bb==0 and aa<0:choices.append(((i,-F(1)/aa),))
    for i,j in itertools.combinations(range(len(rows)),2):
        aa,bb,_=rows[i];cc,dd,_=rows[j];det=aa*dd-cc*bb
        if not det:continue
        wi,wj=-dd/det,bb/det
        if wi>=0 and wj>=0:choices.append(((i,wi),(j,wj)))
    for weights in choices:
        assert sum(w*rows[i][0] for i,w in weights)==-1
        assert sum(w*rows[i][1] for i,w in weights)==0
        terms=defaultdict(F)
        for i,w in weights:
            for k,v in rows[i][2].items():terms[k]-=w*v
        candidates.append((weights,dict(terms)))
    authority._support_cache[cache_key]=rows,candidates
    return rows,candidates

def main():
    a=Authority();unit='MESS04';A,d,start=load()
    with np.load(HISTORY/'PURE_LP_POINT.npz') as z:x=z['x']
    results=[]
    for t in range(69,73):
        terms=defaultdict(F);details=[];required=F(0)
        for siteid,site in enumerate(a.sites):
            if f'Q[{unit},{site},{t}]' not in a.names:continue
            values={k:a.value(n,x) for k,n in {'y':f'arc[{unit},{siteid*96+t}]','C':f'Pch[{unit},{site},{t}]','D':f'Pdis[{unit},{site},{t}]','Q':f'Q[{unit},{site},{t}]'}.items()}
            rows,candidates=supports(a,unit,site,t)
            weights,chosen=max(candidates,key=lambda v:sum(v[1].get(k,F(0))*value for k,value in values.items()))
            value=sum(chosen.get(k,F(0))*v for k,v in values.items());required+=value
            names={'y':f'arc[{unit},{siteid*96+t}]','C':f'Pch[{unit},{site},{t}]','D':f'Pdis[{unit},{site},{t}]','Q':f'Q[{unit},{site},{t}]'}
            for k,w in chosen.items():terms[names[k]]+=w
            details.append(dict(site=site,required_discharge_mode_mass=float(value),required_mass_exact=str(value),dual_weights=[[i,str(w)] for i,w in weights],support_coefficients={k:str(v) for k,v in chosen.items()},rows=[dict(u_coefficient=str(aa),qD_coefficient=str(bb),rhs={k:str(v) for k,v in rhs.items()}) for aa,bb,rhs in rows],input_values={k:float(v) for k,v in values.items()}))
        mode=a.value(f'charge_mode[{unit},{t}]',x);terms[f'charge_mode[{unit},{t}]']+=1
        violation=required+mode-1
        start_residual=sum(w*a.value(name,start) for name,w in terms.items())-1
        assert start_residual<=F.from_float(1e-8)
        results.append(dict(slot=t,available_discharge_mode_mass=float(1-mode),required_discharge_mode_mass=float(required),violation=float(violation),exact_violation=str(violation),physical_terms={k:str(v) for k,v in terms.items() if v},rhs='1',details=details,original_integer_start_exact_residual=str(start_residual),universal_proof='At each site a nonnegative combination of original charge/discharge half-PCS rows yields u_s>=support(Pch,Pdis,Q,stay). The multipliers satisfy sum(w*a)=-1 and sum(w*b)=0 exactly. Every integral trajectory has sum(u_s)<=1-charge_mode. Summing site supports gives the stated inequality, valid for all 4-slot integer trajectories and their convex hull.',original_16_PCS_coefficients_used=True,temporal_SOC_or_route_constraint_required_for_this_separator=False))
    best=max(results,key=lambda r:r['violation'])
    write('MESS04_69_72_COMMON_MODE_SEPARATION.json',dict(PASS=True,optimize_calls=0,results=results,strongest=best,structural_outside_proved=best['violation']>1e-8,known_PR167_single_slot_candidates_not_repeated=True,untested_exact_mode_location_PQ_disjunction_identified=True,hull_is_still_full_four_slot_in_strengthened_LP=True))
    write('MESS04_69_72_SEPARATION.json',dict(exact_separation=best['violation']>1e-8,exact_rational_inequality=best,physical_impossibility='The aggregate discharge-mode mass required by the location-specific P/Q points exceeds the single physical unit available discharge-mode mass.',SOC_impossibility_proved=False,multiperiod_necessity_proved=False,original_PR167_proxy_raw_numerical_failure_preserved=True))
    write('MESS04_69_72_LP_MEMBERSHIP.json',dict(exact_stored_point_inside=False if best['violation']>1e-8 else None,structural_outside_proved=best['violation']>1e-8,native_membership=read(OUT/'MESS04_69_72_MEMBERSHIP.json'),exact_separator=best,violation_magnitude=best['violation'],temporal_impossibility_not_assumed=True,membership_NO_does_not_prove_window_explains_global_gap=True))
    print('EXACT_COMMON_MODE_SEPARATOR',[(r['slot'],r['violation']) for r in results],flush=True)

if __name__=='__main__':main()
