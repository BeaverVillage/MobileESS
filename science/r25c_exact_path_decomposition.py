#!/usr/bin/env python3
"""R25C/A3 exact mobility-path decomposition kernel.

This module does NOT solve the production MIQCP. It defines the exact full-column
Dantzig-Wolfe representation of one MESS time-expanded mobility DAG and an exact
DAG pricing oracle for additive reduced costs. A5 must provide certified branch-and-price
(or an equivalent all-column certificate) before this can replace the monolithic model.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple, Any, Optional
import math

Node=Tuple[int,str]

@dataclass(frozen=True)
class Arc:
    arc_id:str
    tail:Node
    head:Node
    kind:str                 # STAY or MOVE
    slot:Optional[int]=None
    safe_energy_kwh:float=0.0
    route_penalty:float=0.0

@dataclass
class PathColumn:
    mess_id:str
    arc_ids:Tuple[str,...]
    move_arc_ids:Tuple[str,...]
    stay_nodes:Tuple[Node,...]
    move_departures:Tuple[Tuple[int,int,str,str,float],...]
    additive_base_cost:float


def validate_dag(arcs:Iterable[Arc], source:Node, horizon:int)->None:
    a=list(arcs)
    if source[0]<0 or source[0]>horizon: raise ValueError('source time outside horizon')
    ids=set()
    for x in a:
        if x.arc_id in ids: raise ValueError('duplicate arc id')
        ids.add(x.arc_id)
        if x.kind not in {'STAY','MOVE'}: raise ValueError('unknown arc kind')
        if not (0<=x.tail[0]<x.head[0]<=horizon): raise ValueError('non-forward arc in mobility DAG')
        if x.kind=='STAY' and not (x.head[0]==x.tail[0]+1 and x.head[1]==x.tail[1]):
            raise ValueError('invalid STAY arc')
        if x.kind=='MOVE' and x.slot is None: raise ValueError('MOVE requires slot')
        if x.safe_energy_kwh < -1e-12: raise ValueError('planning Safe route energy must be nonnegative')


def shortest_path_pricing(arcs:Iterable[Arc], source:Node, horizon:int,
                          arc_reduced_cost:Dict[str,float]) -> Tuple[float,Tuple[str,...],Node]:
    """Exact shortest path on the acyclic mobility graph for additive reduced cost.

    All legal sink services at time H are accepted, matching BUILD7C terminal-location semantics.
    """
    arcs=list(arcs);validate_dag(arcs,source,horizon)
    out=defaultdict(list)
    for a in arcs: out[a.tail].append(a)
    dist={source:0.0};pred={}
    nodes=sorted({source}|{a.tail for a in arcs}|{a.head for a in arcs},key=lambda x:(x[0],x[1]))
    for u in nodes:
        if u not in dist: continue
        du=dist[u]
        for a in out.get(u,[]):
            nd=du+float(arc_reduced_cost.get(a.arc_id,0.0))
            if a.head not in dist or nd<dist[a.head]-1e-12:
                dist[a.head]=nd;pred[a.head]=(u,a.arc_id)
    sinks=[n for n,d in dist.items() if n[0]==horizon]
    if not sinks: raise ValueError('no legal H sink reachable')
    sink=min(sinks,key=lambda n:(dist[n],n[1]));ids=[];cur=sink
    while cur!=source:
        pu,aid=pred[cur];ids.append(aid);cur=pu
    ids.reverse()
    return float(dist[sink]),tuple(ids),sink


def column_from_path(mess_id:str, arcs_by_id:Dict[str,Arc], path:Iterable[str], base_arc_cost:Optional[Dict[str,float]]=None)->PathColumn:
    ids=tuple(path); moves=[];stays=[];deps=[];cost=0.0
    for aid in ids:
        a=arcs_by_id[aid]
        cost+=float((base_arc_cost or {}).get(aid,a.route_penalty))
        if a.kind=='STAY': stays.append(a.tail)
        else:
            moves.append(aid);deps.append((a.tail[0],int(a.slot),a.tail[1],a.head[1],float(a.safe_energy_kwh)))
    return PathColumn(str(mess_id),ids,tuple(moves),tuple(stays),tuple(deps),float(cost))


def signature_additive_cost(col:PathColumn, stay_price:Dict[Node,float],
                            move_price:Dict[Tuple[int,int,str,str],float],
                            energy_price_by_h:Dict[int,float]) -> float:
    """Linear master-coupling signature -> additive column price.

    Covers the mobility couplings used by BUILD7C: STAY occupancy/location gating,
    MOVE selection, route Safe-energy departure terms and route tie-break. Other master
    coefficients can be added as further additive arc signatures without changing the kernel.
    """
    v=col.additive_base_cost
    for n in col.stay_nodes: v+=float(stay_price.get(n,0.0))
    for h,slot,src,dst,e in col.move_departures:
        v+=float(move_price.get((h,slot,src,dst),0.0))+float(energy_price_by_h.get(h,0.0))*e
    return float(v)


def enumerate_paths(arcs:Iterable[Arc], source:Node, horizon:int, limit:int=100000)->List[Tuple[str,...]]:
    """Small-graph proof helper only; never use for production H54."""
    arcs=list(arcs);validate_dag(arcs,source,horizon);out=defaultdict(list)
    for a in arcs:out[a.tail].append(a)
    ans=[]
    def dfs(u,cur):
        if len(ans)>limit:raise RuntimeError('enumeration proof limit exceeded')
        if u[0]==horizon:ans.append(tuple(cur));return
        for a in out.get(u,[]):dfs(a.head,cur+[a.arc_id])
    dfs(source,[]);return ans
