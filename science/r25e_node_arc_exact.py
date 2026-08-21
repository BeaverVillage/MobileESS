#!/usr/bin/env python3
"""R25E/A5 exact node-binary / continuous-arc mobility reformulation.

For a simple acyclic state graph (no parallel arcs with the same tail and head),
a unit source-to-H path can be represented with binary node occupancy y and
continuous arc flow x in [0,1]:

    sum_in(v)  = y_v
    sum_out(v) = y_v       for nonterminal v
    sum_{v in H} y_v = 1

The source receives one unit of fixed inflow.  With binary y, any fractional
split would have to enter a child with fractional total inflow before it could
merge again.  That contradicts binary y.  The only zero-intermediate-node
exception is a pair of parallel arcs from the same tail directly to the same
head; R25E therefore rejects parallel tail/head arcs fail-closed.

This preserves the exact integer path set while moving O(|A|) MOVE/STAY arc
variables out of the integer domain and keeping only O(|V|) state binaries.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections import defaultdict
from typing import Iterable, Tuple, Dict, List, Any

Node=Tuple[int,str]

@dataclass(frozen=True)
class StateArc:
    arc_id:str
    tail:Node
    head:Node
    kind:str


def validate_simple_dag(arcs:Iterable[StateArc], source:Node, horizon:int)->dict[str,Any]:
    arcs=list(arcs)
    ids=set(); pairs={}; out=defaultdict(list); inc=defaultdict(list)
    for a in arcs:
        if a.arc_id in ids: raise ValueError(f"duplicate arc id {a.arc_id}")
        ids.add(a.arc_id)
        if not (0 <= a.tail[0] < a.head[0] <= horizon): raise ValueError(f"nonforward arc {a}")
        pair=(a.tail,a.head)
        if pair in pairs: raise ValueError(f"parallel tail/head arcs forbidden: {pairs[pair]} and {a.arc_id} on {pair}")
        pairs[pair]=a.arc_id; out[a.tail].append(a); inc[a.head].append(a)
    if source[0] > horizon: raise ValueError("source beyond horizon")
    return {"arc_count":len(arcs),"parallel_tail_head_count":0,
            "node_count":len({source}|{a.tail for a in arcs}|{a.head for a in arcs}),
            "source":source,"horizon":int(horizon)}


def enumerate_paths(arcs:Iterable[StateArc], source:Node, horizon:int, limit:int=100000)->List[Tuple[str,...]]:
    arcs=list(arcs); validate_simple_dag(arcs,source,horizon)
    out=defaultdict(list)
    for a in arcs: out[a.tail].append(a)
    ans=[]
    def dfs(u,cur):
        if len(ans)>limit: raise RuntimeError("path enumeration proof limit exceeded")
        if u[0]==horizon:
            ans.append(tuple(cur)); return
        for a in out.get(u,[]): dfs(a.head,cur+[a.arc_id])
    dfs(source,[])
    return ans


def node_signature(path:Iterable[str], byid:Dict[str,StateArc], source:Node)->Tuple[Node,...]:
    cur=source; nodes=[source]
    for aid in path:
        a=byid[aid]
        if a.tail!=cur: raise ValueError("noncontiguous path")
        cur=a.head; nodes.append(cur)
    return tuple(nodes)


def prove_path_signature_injective(arcs:Iterable[StateArc], source:Node, horizon:int)->dict[str,Any]:
    arcs=list(arcs); audit=validate_simple_dag(arcs,source,horizon); byid={a.arc_id:a for a in arcs}
    paths=enumerate_paths(arcs,source,horizon)
    sig={}
    for p in paths:
        ns=node_signature(p,byid,source)
        occ=tuple(sorted(ns))
        if occ in sig and sig[occ]!=p:
            raise AssertionError(f"two distinct paths share binary-node occupancy signature: {sig[occ]} vs {p}")
        sig[occ]=p
    audit.update({"path_count":len(paths),"unique_node_occupancy_signatures":len(sig),
                  "path_to_node_signature_injective":len(paths)==len(sig)})
    return audit


def structural_binary_bound(stay_state_count:int, mess_count:int=4, service_count:int=24,
                            mode_binary_count:int=216, other_integer_count:int=0)->dict[str,Any]:
    # stay_state_count counts reachable states for h=0..H-1.  At H there can be
    # at most mess_count*service_count additional occupancy binaries.
    occ_upper=int(stay_state_count)+int(mess_count)*int(service_count)
    return {"node_occupancy_binary_upper_bound":occ_upper,
            "mode_binary_count":int(mode_binary_count),
            "other_integer_count":int(other_integer_count),
            "total_integer_upper_bound":occ_upper+int(mode_binary_count)+int(other_integer_count)}
