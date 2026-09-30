"""Standalone exhaustive legacy transfer oracle, without compute screening."""
from collections import defaultdict
import gurobipy as gp
from .common import *
from .factor import add_job,contributions,authority
from v42_compact.graph import Graph
from v42_compact.formulation import add_resources
from v42_boundary.generator import Generator
from .gates import adversarial
from dataclasses import replace

def contract(j,b,r):
    H=r.control_end;k=j.reference_site;dests=sorted({d for a,d in r.paths if a==k and d!=k and r.paths[a,d] and len(set(r.paths[a,d]))==len(r.paths[a,d])})
    if not dests:return []
    # Compute is a transparent one-slot suffix and checkpoint is boundary 0.
    # Every possible pair/start is indexed, including legacy-infeasible starts.
    # WAN dynamics/resource rows alone decide feasibility.
    j=replace(j,state='RUNNING',event=0,reference_start=0,service_slots=1,elapsed_seconds=1800.,initial_sites=tuple(sorted({k,*dests})))
    generator=Generator(r,H+2);events=dict(y=((k,0),),q=((k,0),),w=tuple((k,d,t) for d in dests for t in range(H)),f0=((k,1),),f1=tuple((d,t) for d in dests for t in range(1,H+2)))
    states=dict(r0=((k,0),),h=tuple((k,t) for t in range(H)),r1=tuple((d,t) for d in dests for t in range(H+1)))
    g=Graph(events,states,{(k,0):(0,)},{(k,0,0):0},{key:generator.transfer(*key[:2],j.gpu,key[2]) for key in events['w']})
    m=gp.Model();m.Params.OutputFlag=0;m.Params.Threads=1;m.Params.Seed=20260929
    v=add_job(m,j,g,r);use=contributions(j,g,v);add_resources(m,use,r)
    pairs,quantum,B,rates=authority(j,g,r);rows=[]
    for d in dests:
        for t in range(H):
            pin=[m.addConstr(x==int(p==(k,d))) for p,x in v['pair'].items()]+[m.addConstr(x==int(s==t)) for s,x in v['wan_start'].items()]
            m.optimize();tr=generator.transfer(k,d,j.gpu,t);feasible=m.Status==gp.GRB.OPTIMAL
            if m.Status not in (gp.GRB.OPTIMAL,gp.GRB.INFEASIBLE):raise ValueError('WAN_CONTRACT_SOLVE_INCOMPLETE')
            if feasible!=tr.feasible:raise ValueError('WAN_FEASIBILITY_CONTRACT:'+str((k,d,t,tr.reason,m.Status)))
            if feasible:
                want={(l,slot):n for l,slot,n in tr.wan}
                for key,x in v['link_bytes'].items():
                    if abs(x.X-want.get(key,0))>max(1e-5,abs(want.get(key,0))*1e-9):raise ValueError('WAN_BYTES_CONTRACT')
                for slot,x in v['wan_active'].items():
                    if abs(x.X-int(t<=slot<tr.end))>1e-6:raise ValueError('WAN_ACTIVE_CONTRACT')
                finals=[s for s,x in v['wan_final'].items() if x.X>.5]
                arrivals=[R for (site,R),x in v['arrive'].items() if x.X>.5]
                if finals!=[tr.end-1] or arrivals!=[tr.restart]:raise ValueError('WAN_BOUNDARY_CONTRACT')
                if abs(sum(x.X for x in v['sent'].values())*quantum-r.bytes_per_gpu*j.gpu)>1e-5:raise ValueError('WAN_PAYLOAD_CONTRACT')
            rows.append(dict(source=k,destination=d,start=t,legacy_feasible=tr.feasible,new_feasible=feasible,legacy_reason=tr.reason,PASS=True))
            m.remove(pin);m.update()
    m.dispose();return rows

def main():
    cases=[];total=[]
    for name,jobs,bounds,r in adversarial():
        j=next(iter(jobs.values()));b=bounds[j.uid];rows=contract(j,b,r);total+=rows
        cases.append(dict(case=name,combinations=len(rows),feasible=sum(x['legacy_feasible'] for x in rows),PASS=True))
    previous=read(OUT/'WAN_TEMPLATE_EQUIVALENCE.json')
    previous.update(standalone_all_pairs_starts_PASS=True,standalone_combinations=len(total),standalone_cases=cases,standalone_rows=total,
        standalone_scope='All authorized source-reference destination/start combinations in sixteen bounded authorities; infeasible starts included; compute suffix transparent')
    dump('WAN_TEMPLATE_EQUIVALENCE.json',previous);print('WAN standalone',len(total),'PASS',flush=True)

if __name__=='__main__':main()
