"""Deterministic complete legal paths, never a restriction on the exact solve."""
from collections import defaultdict
from .common import *

def closest_path(graph,origin,flow,horizon=96):
    """Minimize duration-weighted arc L1 distance to fractional root flow.

    A complete path occupies horizon slots. Its variable part in the weighted
    L1 distance is -2*sum(duration*root_flow) over selected arcs. The DAG dynamic
    program therefore maximizes this score, keeping original legal transitions.
    """
    outgoing=defaultdict(list)
    for k,a in enumerate(graph):outgoing[a[:2]].append(k)
    score={(origin,0):0.};parent={}
    for t in range(horizon):
        for site in sorted({a[0] for a in graph}):
            node=(site,t)
            if node not in score:continue
            for k in outgoing[node]:
                a=graph[k];dest=(a[2],a[3])
                candidate=score[node]+(a[3]-a[1])*float(flow.get(k,0.))
                if dest not in score or candidate>score[dest]+1e-12:
                    score[dest]=candidate;parent[dest]=(node,k)
    ends=sorted((n for n in score if n[1]==horizon),key=lambda n:(-score[n],n[0]))
    assert ends,'NO_LEGAL_COMPLETE_ROUTE'
    node=ends[0];chosen=[]
    while node!=(origin,0):node,k=parent[node];chosen.append(k)
    chosen.reverse();assert path_validation(graph,origin,chosen,horizon)['PASS']
    return chosen,score[ends[0]]

def path_validation(graph,origin,chosen,horizon=96):
    node=(origin,0);seen=set();travel=0.;errors=[]
    for k in chosen:
        if k in seen or not 0<=k<len(graph):errors.append('INVALID_OR_DUPLICATE_ARC');break
        seen.add(k);a=graph[k]
        if a[:2]!=node or not a[1]<a[3]<=horizon:errors.append('ILLEGAL_CONTINUITY');break
        if a[-1] is not None:
            r=a[-1]
            if (r.source,r.depart,r.destination,r.connect)!=a[:4]:errors.append('ROUTE_AUTHORITY_MISMATCH')
            if not r.depart<r.arrive<=r.connect<horizon:errors.append('TRAVEL_CONVENTION')
            travel+=r.energy_kwh
        elif a[0]!=a[2] or a[3]!=a[1]+1:errors.append('ILLEGAL_STAY')
        node=(a[2],a[3])
    if node[1]!=horizon:errors.append('INCOMPLETE_HORIZON')
    return dict(PASS=not errors,errors=errors,travel_energy_kwh=travel,terminal_site=node[0],arc_count=len(chosen))

def generate():
    _,_,_,sites,initial,_,_=inputs();graph=arcs();names=axis()['names'];pos={str(n):i for i,n in enumerate(names)}
    candidates=[];support=[];rows=[]
    for number,source in enumerate(SOURCES,1):
        values,path=root(source);routes={};scores={};valid={}
        for u,origin in sorted(initial.items()):
            flow={k:values.get(f'arc[{u},{k}]',0.) for k in range(len(graph))}
            chosen,score=closest_path(graph,origin,flow)
            routes[u]=chosen;scores[u]=score;valid[u]=path_validation(graph,origin,chosen)
            assert all(f'arc[{u},{k}]' in pos for k in chosen),'REACHABILITY_DOMAIN_CHANGED'
            for k,a in enumerate(graph):
                intersects=a[1]<=95 and a[3]>58 or 58<=a[1]<=95
                if intersects and flow[k]>1e-9:
                    support.append(dict(source=source,unit=u,arc=k,source_site=a[0],departure=a[1],destination=a[2],connection=a[3],
                        travel=a[-1] is not None,energy_kwh=a[-1].energy_kwh if a[-1] else 0.,root_mass=flow[k],selected=k in chosen))
            moves=[k for k in chosen if graph[k][-1] is not None]
            rows.append(dict(candidate=f'W{number}',source=source,unit=u,root_score=score,complete_route_valid=True,
                selected_arc_count=len(chosen),travel_count=len(moves),travel_energy_kwh=valid[u]['travel_energy_kwh'],
                selected_arc_indices=json.dumps(chosen),fixed_policy='B3-authorized route arcs only; outside route variables remain relaxed/free'))
        candidates.append(dict(id=f'W{number}',source=source,source_solution_path=path.relative_to(ROOT).as_posix(),
            source_sha256=sha(path),routes=routes,scores=scores,route_validation=valid))
    dump('ROUTE_WITNESS_CANDIDATES.json',dict(candidate_count=2,candidates=candidates,generated_without_optimization=True,
        scientific_graph_unpruned=True,ranking='duration-weighted L1 nearest complete flow path; deterministic original arc order ties'))
    table('ROUTE_WITNESS_CANDIDATES.csv',rows)
    table('ROOT_ROUTE_SUPPORT.csv',support)
    states=[]
    for source in SOURCES:
        v,_=root(source)
        for u in sorted(initial):
            for t in range(58,96):
                stay={s:v.get(f'arc[{u},{next(k for k,a in enumerate(graph) if a[:2]==(s,t) and a[-1] is None)}]',0.) for s in sites}
                trans=sum(v.get(f'arc[{u},{k}]',0.) for k,a in enumerate(graph) if a[-1] is not None and a[1]<=t<a[3])
                states.append(dict(source=source,unit=u,slot=t,SOC=v[f'SOC[{u},{t}]'],charge_mode=v[f'charge_mode[{u},{t}]'],
                    Pch=sum(v.get(f'Pch[{u},{s},{t}]',0.) for s in sites),Pdis=sum(v.get(f'Pdis[{u},{s},{t}]',0.) for s in sites),
                    Q=sum(v.get(f'Q[{u},{s},{t}]',0.) for s in sites),location_probabilities=json.dumps(stay),transit_probability=trans))
    table('ROOT_GUIDED_STATES.csv',states)
    print('ROOT CANDIDATES SEALED',len(candidates),flush=True)

if __name__=='__main__':generate()
