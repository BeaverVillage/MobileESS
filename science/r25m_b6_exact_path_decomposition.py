#!/usr/bin/env python3
"""R25M/B6 exact mobility path decomposition for the BUILD7C joint master.

Production idea
---------------
The R25G/R25K mobility block is an exact unit-flow DAG extended formulation.
For each MESS, a complete source-to-H path is a column.  This module projects
all STAY/MOVE/node-occupancy variables and the pure flow rows out of the already
constructed Gurobi model, and replaces them with path variables.

Certificate strategy
--------------------
1. Relax every remaining integer variable and solve the convex QCP restricted
   path master.
2. Use exact DAG pricing and linear-row duals to add every negative-reduced-cost
   path until pricing closes.  Since path variables enter no quadratic row, this
   certifies the full all-column continuous relaxation bound L.
3. Restore non-mobility integrality, make generated path variables binary, and
   solve the compact restricted integer master for any feasible incumbent U.
4. If (U-L)/|U| <= the frozen target (3%), U has a global 3% certificate for the
   original integer model.  Branch-and-price is unnecessary in that case.

If pricing does not close or the global certificate is not reached, the module
fails closed; a heuristic restricted-column bound is never treated as authority.
"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple
import hashlib, itertools, math, os, time, heapq
from r25c_exact_path_decomposition import Arc, shortest_path_pricing, validate_dag

Node=Tuple[int,str]

@dataclass
class RuntimePath:
    mid:str
    arc_ids:Tuple[str,...]
    sink:Node


def _exact_float_token(value:float)->str:
    """Stable, bit-exact token for an in-process model-copy audit."""
    return float(value).hex()


def _digest_token(digest, value)->None:
    data=str(value).encode('utf-8')
    digest.update(len(data).to_bytes(8,'big'))
    digest.update(data)


def exact_gurobi_model_structure_digest(model)->Tuple[str,Dict[str,Any]]:
    """Digest the mathematical model copied for the R25T projection phase.

    Gurobi's ``Fingerprint`` is useful provenance, but it is not a documented
    postcondition of ``Model.copy()`` for a large model carrying solver-guidance
    attributes.  This audit instead covers the complete mathematical structure
    used by R25T: variable domains and linear objective, every linear matrix
    coefficient, all quadratic rows, and any quadratic objective.  Search-only
    attributes such as starts, hints, and branch priorities are deliberately not
    part of the scientific-equivalence contract.
    """
    model.update()
    counts={
        'variables':int(model.NumVars),
        'linear_constraints':int(model.NumConstrs),
        'linear_nonzeros':int(model.DNumNZs),
        'quadratic_constraints':int(model.NumQConstrs),
        'quadratic_objective_nonzeros':int(model.NumQNZs),
        'sos_constraints':int(model.NumSOS),
        'general_constraints':int(model.NumGenConstrs),
        'integer_variables':int(model.NumIntVars),
        'binary_variables':int(model.NumBinVars),
    }
    # The current exact AC-QCP authority contains neither SOS nor general
    # constraints.  Refuse an un-audited future model class instead of silently
    # declaring two partially inspected models equivalent.
    if counts['sos_constraints'] or counts['general_constraints']:
        raise RuntimeError('R25T copy audit does not support SOS/general constraints: '+repr(counts))

    digest=hashlib.sha256()
    _digest_token(digest,'R25T_EXACT_GUROBI_STRUCTURE_V1')
    for key in sorted(counts):
        _digest_token(digest,key);_digest_token(digest,counts[key])
    _digest_token(digest,'ModelSense');_digest_token(digest,int(model.ModelSense))
    _digest_token(digest,'ObjCon');_digest_token(digest,_exact_float_token(model.ObjCon))

    variables=model.getVars()
    for index,var in enumerate(variables):
        _digest_token(digest,index)
        _digest_token(digest,var.VarName)
        _digest_token(digest,var.VType)
        _digest_token(digest,_exact_float_token(var.LB))
        _digest_token(digest,_exact_float_token(var.UB))
        _digest_token(digest,_exact_float_token(var.Obj))

    constraints=model.getConstrs()
    for index,constr in enumerate(constraints):
        _digest_token(digest,index)
        _digest_token(digest,constr.ConstrName)
        _digest_token(digest,constr.Sense)
        _digest_token(digest,_exact_float_token(constr.RHS))
        _digest_token(digest,int(constr.Lazy))

    # getA() provides the complete linear matrix in model row/column order.  The
    # order itself is audited above, so hashing the CSR buffers is both exact and
    # far cheaper than 6.6 million Python-level coefficient lookups on issue 149.
    matrix=model.getA().tocsr(copy=True)
    matrix.sort_indices()
    _digest_token(digest,matrix.shape)
    for array in (matrix.indptr,matrix.indices,matrix.data):
        _digest_token(digest,array.dtype.str)
        digest.update(array.tobytes(order='C'))
    del matrix

    for index,qconstr in enumerate(model.getQConstrs()):
        _digest_token(digest,index)
        _digest_token(digest,qconstr.QCName)
        _digest_token(digest,qconstr.QCSense)
        _digest_token(digest,_exact_float_token(qconstr.QCRHS))
        expression=model.getQCRow(qconstr)
        linear=expression.getLinExpr()
        linear_terms=sorted(
            (linear.getVar(i).VarName,_exact_float_token(linear.getCoeff(i)))
            for i in range(linear.size())
        )
        quadratic_terms=sorted(
            (min(expression.getVar1(i).VarName,expression.getVar2(i).VarName),
             max(expression.getVar1(i).VarName,expression.getVar2(i).VarName),
             _exact_float_token(expression.getCoeff(i)))
            for i in range(expression.size())
        )
        for term in linear_terms:_digest_token(digest,term)
        for term in quadratic_terms:_digest_token(digest,term)

    if counts['quadratic_objective_nonzeros']:
        objective=model.getObjective()
        linear=objective.getLinExpr()
        quadratic_terms=sorted(
            (min(objective.getVar1(i).VarName,objective.getVar2(i).VarName),
             max(objective.getVar1(i).VarName,objective.getVar2(i).VarName),
             _exact_float_token(objective.getCoeff(i)))
            for i in range(objective.size())
        )
        for i in range(linear.size()):
            _digest_token(digest,(linear.getVar(i).VarName,_exact_float_token(linear.getCoeff(i))))
        for term in quadratic_terms:_digest_token(digest,term)

    return digest.hexdigest(),counts




def rc_audit_pass(max_err:float,tol:float)->bool:
    return math.isfinite(float(max_err)) and 0.0 <= float(max_err) <= float(tol)

def r25t_recoverable_restricted_error(error_code:int)->bool:
    """Only OOM is a phase transition, and only for R25T's heuristic RMP."""
    return int(error_code)==10001

def guarded_full_lb(rmp_obj:float,mess_count:int,rc_audit_tol:float)->Tuple[float,float]:
    """Conservative numerical guard used only after priced closure.

    One RC-audit tolerance unit per MESS is subtracted from the solved RMP
    objective, plus a tiny objective-scale guard.  This can only weaken a
    minimization lower bound and therefore cannot create a false 3% pass.
    """
    o=float(rmp_obj); t=float(rc_audit_tol); n=int(mess_count)
    if not (math.isfinite(o) and n>0 and t>0): raise ValueError('invalid guarded_full_lb input')
    safety=float(n)*t + max(1e-6,1e-9*abs(o))
    return float(o-safety),float(safety)

def global_relative_gap(incumbent:float, lower_bound:float)->float:
    u=float(incumbent); l=float(lower_bound)
    if not (math.isfinite(u) and math.isfinite(l)): return float('inf')
    # minimization lower-bound contract
    if l>u+1e-7*max(1.0,abs(u),abs(l)):
        raise ValueError(f'lower bound exceeds incumbent: L={l} U={u}')
    den=abs(u)
    if den<=1e-12:return 0.0 if abs(u-l)<=1e-12 else float('inf')
    return max(0.0,(u-l)/den)

def incumbent_required_for_gap(lower_bound:float,target:float)->float:
    """Best incumbent threshold that certifies ``target`` at a fixed bound."""
    l=float(lower_bound);g=float(target)
    if not (math.isfinite(l) and math.isfinite(g) and 0.0<=g<1.0):
        raise ValueError('invalid incumbent target inputs')
    if l<0.0:return float(l/(1.0+g))
    if l>0.0:return float(l/(1.0-g))
    return 0.0

def gap_target_lower_bound(incumbent:float,target:float)->float:
    """Minimum node lower bound needed to certify the incumbent at target gap.

    For the frozen Gurobi-style gap g=(U-L)/|U| in a minimization problem,
    certification is exactly equivalent to L >= U-g|U|.  Keeping this threshold
    explicit avoids repeated sign-sensitive reasoning for negative objectives.
    """
    u=float(incumbent);g=float(target)
    if not (math.isfinite(u) and math.isfinite(g) and 0.0<=g<1.0):
        raise ValueError('invalid gap target inputs')
    return float(u-g*abs(u))

def gap_certificate_diagnostics(incumbent:float,lower_bound:float,target:float)->Dict[str,Any]:
    u=float(incumbent);l=float(lower_bound);g=float(target)
    rel=global_relative_gap(u,l);thr=gap_target_lower_bound(u,g)
    return {
        'incumbent':u,'lower_bound':l,'relative_gap':float(rel),'target':g,
        'target_lower_bound_for_current_incumbent':float(thr),
        'additional_bound_improvement_required':float(max(0.0,thr-l)),
        'certificate_pass':bool(rel<=g+1e-12),
        'absolute_gap':float(max(0.0,u-l)),
    }


def classify_integer_block(name:str)->str:
    """Diagnostic-only integrality block classifier for C5R2 gap-source attribution."""
    n=str(name)
    if n.startswith('mode_'): return 'mode'
    if n.startswith('x_'): return 'job_choice'
    if n.startswith('defer_'): return 'defer'
    return 'other_integer'

def qcp_dual_retry_schedule(primary:float)->Tuple[float,...]:
    """Strictly tighter BarQCPConvTol retry schedule; never loosens numerical accuracy."""
    p=float(primary)
    if not (math.isfinite(p) and p>0): raise ValueError('invalid BarQCPConvTol')
    # R25Q extends recovery below 1e-10.  R25P issue116 demonstrated that a
    # fresh scaled KKT solve can remain just outside the fixed 1e-4 accounting
    # audit even though primal/dual barrier residuals are tiny.  These are
    # stricter solves, never a tolerance relaxation.
    vals=[p,min(p,3e-10),min(p,1e-10),min(p,3e-11),min(p,1e-11),min(p,3e-12),min(p,1e-12)]
    out=[]
    for v in vals:
        if v not in out: out.append(v)
    return tuple(out)


def blend_dual_maps(current:Dict[Any,float], center:Dict[Any,float]|None, alpha:float)->Dict[Any,float]:
    """Convex dual smoothing used only for candidate-column generation.

    alpha=1 returns the true current dual.  The returned map is never used to
    declare pricing closure or to construct a scientific lower bound.
    """
    a=float(alpha)
    if not (0.0 < a <= 1.0): raise ValueError('dual stabilization alpha must lie in (0,1]')
    if center is None:
        return {k:float(v) for k,v in current.items()}
    keys=set(current)|set(center)
    return {k:a*float(current.get(k,0.0))+(1.0-a)*float(center.get(k,0.0)) for k in keys}

def update_dual_center(center:Dict[Any,float]|None, current:Dict[Any,float], beta:float)->Dict[Any,float]:
    """Lagged exponential dual center.  This is an acceleration state only."""
    b=float(beta)
    if not (0.0 <= b < 1.0): raise ValueError('dual center beta must lie in [0,1)')
    if center is None:
        return {k:float(v) for k,v in current.items()}
    keys=set(current)|set(center)
    return {k:b*float(center.get(k,0.0))+(1.0-b)*float(current.get(k,0.0)) for k in keys}

def true_reduced_cost_for_path(mid:str,path:Tuple[str,...],comp:Dict[str,float],pc:float,path_varnames_fn)->float:
    """Evaluate a candidate path under the *true current* RMP dual."""
    return float(sum(float(comp.get(n,0.0)) for n in path_varnames_fn(mid,path))-float(pc))


def certificate_from_relaxation(incumbent:float, full_relaxation_lb:float, target:float)->Dict[str,Any]:
    g=global_relative_gap(incumbent,full_relaxation_lb)
    return {'incumbent':float(incumbent),'full_relaxation_lower_bound':float(full_relaxation_lb),
            'global_relative_gap':float(g),'target':float(target),'accepted':bool(g<=float(target)+1e-12),
            'logic':'L <= integer optimum <= U; therefore (U-L)/|U| upper-bounds the unknown integer optimality gap.'}


def k_shortest_paths_dag(arcs:Iterable[Arc],source:Node,horizon:int,arc_cost:Dict[str,float],k:int=16)->List[Tuple[float,Tuple[str,...],Node]]:
    """Exact k-best paths in a DAG for small k; used only to enrich the integer RMP."""
    arcs=list(arcs);validate_dag(arcs,source,horizon);k=max(1,int(k))
    out=defaultdict(list)
    for a in arcs:out[a.tail].append(a)
    for u in out:out[u].sort(key=lambda a:(a.head[0],a.head[1],a.arc_id))
    nodes=sorted({source}|{a.tail for a in arcs}|{a.head for a in arcs},key=lambda x:(x[0],x[1]))
    best:Dict[Node,List[Tuple[float,Tuple[str,...]]]]={source:[(0.0,tuple())]}
    for u in nodes:
        cur=best.get(u,())
        if not cur:continue
        for a in out.get(u,()):
            arr=best.setdefault(a.head,[])
            ac=float(arc_cost.get(a.arc_id,0.0))
            for val,p in cur:
                arr.append((val+ac,p+(a.arc_id,)))
            # Deterministic truncation; duplicate paths cannot occur in a simple DAG.
            arr.sort(key=lambda z:(z[0],z[1]));del arr[k:]
    ans=[]
    for n,vals in best.items():
        if n[0]==horizon:
            for v,p in vals:ans.append((float(v),p,n))
    ans.sort(key=lambda z:(z[0],z[1],z[2][1]))
    return ans[:k]


def _flow_constraint_name(name:str,mids:Iterable[str])->bool:
    if name.startswith('occ_in_') or name.startswith('occ_out_') or name.startswith('occ_sink_in_'):return True
    return any(name==f'sink_{m}' for m in mids)


def _path_nodes(source:Node,path:Tuple[str,...],byid:Dict[str,Arc])->Tuple[Node,...]:
    ns=[source];cur=source
    for aid in path:
        a=byid[aid]
        if a.tail!=cur:raise RuntimeError(f'noncontiguous runtime path {aid}: {a.tail} != {cur}')
        cur=a.head;ns.append(cur)
    return tuple(ns)




def path_satisfies_node_restrictions(source:Node,path:Tuple[str,...],byid:Dict[str,Arc],required:Iterable[Node]=(),forbidden:Iterable[Node]=())->bool:
    """Return whether a complete path obeys exact node-occupancy branches."""
    ns=set(_path_nodes(source,tuple(path),byid)); req=set(required); forb=set(forbidden)
    return req.issubset(ns) and not bool(ns & forb)


def shortest_path_with_node_restrictions(arcs:Iterable[Arc],source:Node,horizon:int,arc_cost:Dict[str,float],required:Iterable[Node]=(),forbidden:Iterable[Node]=()):
    """Exact shortest source-to-H path containing all required and no forbidden nodes.

    Required nodes are topologically ordered by time.  Because every arc advances
    time strictly, a feasible path containing all of them decomposes exactly into
    independent shortest DAG segments between consecutive required nodes.
    """
    arcs=list(arcs);validate_dag(arcs,source,horizon)
    req=sorted(set(required),key=lambda x:(x[0],x[1]));forb=set(forbidden)
    if source in forb or any(n in forb for n in req):return (float('inf'),tuple(),None)
    if any(n[0]<source[0] or n[0]>horizon for n in req):return (float('inf'),tuple(),None)
    # Two distinct required states at the same time cannot both lie on one path.
    for a,b in zip(req,req[1:]):
        if a[0]==b[0] and a!=b:return (float('inf'),tuple(),None)
    # Keep only arcs that never occupy a forbidden node.
    aa=[a for a in arcs if a.tail not in forb and a.head not in forb]
    out=defaultdict(list)
    for a in aa:out[a.tail].append(a)
    for u in out:out[u].sort(key=lambda a:(a.head[0],a.head[1],a.arc_id))

    def seg(start:Node,target:Node|None):
        # target=None means any sink at horizon.
        dist={start:0.0};pth={start:tuple()}
        nodes=sorted({start}|{a.tail for a in aa}|{a.head for a in aa},key=lambda x:(x[0],x[1]))
        for u in nodes:
            if u not in dist:continue
            if u[0]<start[0]:continue
            if target is not None and u[0]>target[0]:continue
            for a in out.get(u,()):
                if target is not None and a.head[0]>target[0]:continue
                nv=dist[u]+float(arc_cost.get(a.arc_id,0.0));np=pth[u]+(a.arc_id,)
                old=dist.get(a.head,float('inf'))
                if nv<old-1e-12 or (abs(nv-old)<=1e-12 and np<pth.get(a.head,tuple(['~']))):
                    dist[a.head]=nv;pth[a.head]=np
        if target is not None:
            if target not in dist:return (float('inf'),tuple(),None)
            return float(dist[target]),pth[target],target
        sinks=[n for n in dist if n[0]==horizon]
        if not sinks:return (float('inf'),tuple(),None)
        sink=min(sinks,key=lambda n:(dist[n],pth[n],n[1]))
        return float(dist[sink]),pth[sink],sink

    cur=source;tot=0.0;path=[]
    for r in req:
        if r==cur:continue
        if r[0]<cur[0]:return (float('inf'),tuple(),None)
        v,p,s=seg(cur,r)
        if not math.isfinite(v):return (float('inf'),tuple(),None)
        tot+=v;path.extend(p);cur=r
    v,p,sink=seg(cur,None)
    if not math.isfinite(v):return (float('inf'),tuple(),None)
    tot+=v;path.extend(p)
    pp=tuple(path)
    if not path_satisfies_node_restrictions(source,pp,{a.arc_id:a for a in arcs},req,forb):
        raise RuntimeError('restricted shortest-path internal branch-contract failure')
    return float(tot),pp,sink


def k_shortest_paths_with_node_restrictions(arcs:Iterable[Arc],source:Node,horizon:int,arc_cost:Dict[str,float],required:Iterable[Node]=(),forbidden:Iterable[Node]=(),k:int=8)->List[Tuple[float,Tuple[str,...],Node]]:
    """Exact k-best source-to-H paths obeying node-occupancy branch restrictions.

    The DP state augments each physical DAG node with how many required nodes have
    already been visited.  Because every arc advances time strictly, retaining the
    k best partial paths per augmented state is exact for the k-best complete paths.
    This is used only for batch column insertion; closure is still certified by the
    exact single minimum-reduced-cost oracle.
    """
    arcs=list(arcs);validate_dag(arcs,source,horizon);k=max(1,int(k))
    req=sorted(set(required),key=lambda x:(x[0],x[1]));forb=set(forbidden)
    if source in forb or any(n in forb for n in req):return []
    if any(n[0]<source[0] or n[0]>horizon for n in req):return []
    for a,b in zip(req,req[1:]):
        if a[0]==b[0] and a!=b:return []
    # A required node at the source is already satisfied.
    j0=0
    while j0<len(req) and req[j0]==source:j0+=1
    aa=[a for a in arcs if a.tail not in forb and a.head not in forb]
    out=defaultdict(list)
    for a in aa:out[a.tail].append(a)
    for u in out:out[u].sort(key=lambda a:(a.head[0],a.head[1],a.arc_id))
    nodes=sorted({source}|{a.tail for a in aa}|{a.head for a in aa},key=lambda x:(x[0],x[1]))
    best:Dict[Tuple[Node,int],List[Tuple[float,Tuple[str,...]]]]={(source,j0):[(0.0,tuple())]}
    for u in nodes:
        for j in range(len(req)+1):
            cur=best.get((u,j),())
            if not cur:continue
            # If the next required state occurs at or before the current time and
            # has not been visited, no extension can repair the path.
            if j<len(req) and req[j][0]<=u[0] and req[j]!=u:continue
            for a in out.get(u,()):
                jj=j
                # Do not skip over an unmet required time.
                if jj<len(req) and a.head[0]>req[jj][0] and a.head!=req[jj]:continue
                if jj<len(req) and a.head==req[jj]:
                    jj+=1
                    while jj<len(req) and req[jj]==a.head:jj+=1
                arr=best.setdefault((a.head,jj),[])
                ac=float(arc_cost.get(a.arc_id,0.0))
                for val,path in cur:arr.append((val+ac,path+(a.arc_id,)))
                arr.sort(key=lambda z:(z[0],z[1]));del arr[k:]
    ans=[]
    for (n,j),vals in best.items():
        if n[0]==horizon and j==len(req):
            for val,path in vals:ans.append((float(val),path,n))
    ans.sort(key=lambda z:(z[0],z[1],z[2][1]))
    return ans[:k]



def choose_time_layer_multiway_partition(kbest_paths, source:Node, byid:Dict[str,Arc],
                                         required:Iterable[Node]=(), forbidden:Iterable[Node]=(),
                                         horizon:int=1, max_explicit:int=4):
    """Choose an exact multiway path partition using service occupancy at one time layer.

    Children are: require one selected service node (h,s) for each explicit node,
    plus one REST child that forbids all selected nodes.  Because DAG arc durations
    are strictly positive, a complete trajectory can contain at most one service
    node at a given time h.  Therefore these children are pairwise disjoint and
    their union is the complete parent path set, including paths in transit or at
    service nodes not present in the sampled k-best family.

    The k-best sample selects a useful partition only; exact child bounds still use
    the complete restricted-DAG pricing oracle.
    """
    req=set(required); forb=set(forbidden); H=max(1,int(horizon)); me=max(1,int(max_explicit))
    rows=list(kbest_paths)
    if len(rows)<2:return None
    # Any time already fixed by a required node is not a useful branching layer.
    req_times={int(n[0]) for n in req}
    by_time=defaultdict(lambda:defaultdict(int))
    npaths=len(rows)
    for _,pth,_ in rows:
        seen={}
        for nn in _path_nodes(source,tuple(pth),byid):
            h=int(nn[0])
            if h<=0 or h>=H:continue
            if h in seen and seen[h]!=tuple(nn):
                # Positive-duration DAGs should make this impossible; fail closed
                # rather than construct a non-partitioning branch.
                return None
            seen[h]=tuple(nn)
        for h,nn in seen.items():
            if nn not in forb:by_time[h][nn]+=1
    cand=[]
    for h,counts in by_time.items():
        if h in req_times:continue
        explicit=[(int(c),tuple(nn)) for nn,c in counts.items() if 0<int(c)<npaths]
        if not explicit:continue
        explicit.sort(key=lambda z:(-z[0],z[1]))
        explicit=explicit[:me]
        selected=[nn for _,nn in explicit]
        child_counts=[c for c,_ in explicit]
        rest=npaths-sum(child_counts)
        # If selected categories overlap this can be negative; do not branch.
        if rest<0:continue
        positive=[c for c in child_counts if c>0]
        if rest>0:positive.append(rest)
        if len(positive)<2:continue
        maxshare=max(positive)/float(npaths)
        # Entropy-like balance score, with earlier layers as deterministic tie break.
        probs=[c/float(npaths) for c in positive]
        entropy=-sum(q*math.log(max(q,1e-300)) for q in probs)
        balance=1.0-maxshare
        cand.append((balance,entropy,-h,h,selected,child_counts,rest))
    if not cand:return None
    cand.sort(reverse=True,key=lambda z:(z[0],z[1],z[2],repr(z[4])))
    balance,entropy,_,h,selected,child_counts,rest=cand[0]
    return {
        'kind':'mobility_time_multi','h':int(h),'nodes':tuple(selected),
        'sample_child_counts':tuple(int(x) for x in child_counts),
        'sample_rest_count':int(rest),'sample_size':int(npaths),
        'balance':float(balance),'entropy':float(entropy),
    }


def branch_price_gap_prunable(incumbent:float,node_lower_bound:float,target:float)->bool:
    # Equivalent to the Gurobi-style relative-gap test, but expressed as the
    # target lower-bound threshold.  This remains valid for negative objectives.
    return float(node_lower_bound) >= gap_target_lower_bound(float(incumbent),float(target))-1e-12


def branch_fractionality(x:float)->float:
    """Distance to the nearest integer for branch-candidate ranking only."""
    y=float(x)
    if not math.isfinite(y): return 0.0
    return max(0.0,min(y-math.floor(y),math.ceil(y)-y))


def strong_branch_score(parent_obj:float,child0_obj:float|None,child1_obj:float|None)->Tuple[float,float]:
    """Selection-only strong-branch score for a minimization relaxation.

    Probe objectives are NEVER lower-bound/certificate authority.  The score is
    lexicographic: maximize the weaker child improvement, then total improvement.
    An infeasible probe is treated as +infinity improvement for selection only.
    """
    p=float(parent_obj)
    def imp(v):
        if v is None:return None
        vv=float(v)
        if math.isinf(vv) and vv>0:return float('inf')
        if not math.isfinite(vv):return None
        return max(0.0,vv-p)
    a=imp(child0_obj);b=imp(child1_obj)
    if a is None or b is None:return (-1.0,-1.0)
    weak=min(a,b);tot=a+b
    return (float(weak),float(tot))


def branch_candidate_key(branch:Tuple[Any,...])->Tuple[Any,...]:
    if branch[0]=='mobility_node':
        return ('mobility_node',str(branch[1]),tuple(branch[2]))
    if branch[0]=='integer':
        return ('integer',str(branch[1]))
    raise ValueError('unknown branch kind '+repr(branch[0]))


def branch_side_distance(branch:Tuple[Any,...],side:int)->float:
    if branch[0]=='mobility_node':
        y=float(branch[3]);return max(1e-9,y if int(side)==0 else 1.0-y)
    if branch[0]=='integer':
        x=float(branch[2]);return max(1e-9,x-math.floor(x) if int(side)==0 else math.ceil(x)-x)
    raise ValueError('unknown branch kind '+repr(branch[0]))


def select_strong_branch_shortlist(mobility_candidates:Iterable[Tuple[Any,...]],integer_candidates:Iterable[Tuple[Any,...]],horizon:int,limit:int=4,early_weight:float=0.35)->List[Tuple[Any,...]]:
    """Build a small deterministic reliability-strong-branching shortlist.

    Mobility candidates receive a mild earlier/mid-horizon weight so an h=H-1
    state does not win merely because it is closest to 0.5.  If both mobility
    and non-mobility fractional integers exist and the budget permits, one slot
    is reserved for the best non-mobility candidate so the probe can compare the
    two disjunction classes.  Final selection is by probe/pseudocost score only.
    """
    H=max(2,int(horizon));lim=max(1,int(limit));ew=max(0.0,float(early_weight))
    mob=[];ints=[]
    for c in mobility_candidates:
        if c and c[0]=='mobility_node':
            b=tuple(c);frac=branch_fractionality(float(c[3]));h=int(c[2][0])
        else:
            frac=float(c[0]);mid=c[2];node=tuple(c[3]);y=float(c[4]);h=int(node[0]);b=('mobility_node',mid,node,y)
        hw=1.0+ew*max(0.0,1.0-float(h)/float(max(1,H-1)))
        mob.append((frac*hw,frac,h,b))
    for c in integer_candidates:
        if c and c[0]=='integer':
            b=tuple(c);frac=branch_fractionality(float(c[2]))
        else:
            frac=float(c[0]);name=c[1];x=float(c[2]);typ=c[3];lo=float(c[4]);hi=float(c[5]);b=('integer',name,x,typ,lo,hi)
        ints.append((frac,frac,0,b))
    mob.sort(key=lambda z:(-z[0],-z[1],z[2],repr(z[3])))
    ints.sort(key=lambda z:(-z[0],-z[1],repr(z[3])))
    if mob and ints and lim>=2:
        chosen=[z[3] for z in mob[:lim-1]]+[ints[0][3]]
        return chosen[:lim]
    ranked=[(z[0],z[1],z[2],0,z[3]) for z in mob]+[(z[0],z[1],z[2],1,z[3]) for z in ints]
    ranked.sort(key=lambda z:(-z[0],-z[1],z[2],z[3],repr(z[4])))
    return [z[4] for z in ranked[:lim]]


def certified_path_decomposition_solve(*,m,mids,H,avail_h,initial_sid,reachable_by_mid,allowed_by_mid,moves,
        stay,mv,node_occ,out,target_gap,base_callback=None,cg_time_limit_s=None,integer_time_limit_s=None,
        pricing_tol=1e-7,kbest=16):
    """Transform an already-built single-economic-objective MIQCP and solve it.

    This function intentionally imports gurobipy only at runtime so static/proof tests
    remain dependency-free in the packaging environment.
    """
    import gurobipy as gp
    from gurobipy import GRB
    t0=time.monotonic();out=Path(out)
    # R25P is the authoritative Stage-1 completion run. In this mode no
    # wall-clock or search-count budget may create an unresolved subtree.
    # Termination remains mathematical: pricing closure, certified 3% gap,
    # infeasibility, or a fail-closed numerical/physical error.
    unlimited_completion=(os.environ.get('MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION','0')=='1')
    cg_limit=(math.inf if unlimited_completion else float(cg_time_limit_s if cg_time_limit_s is not None else os.environ.get('MOBILEESS_R25M_B6_CG_TIMELIMIT','420')))
    int_limit=(math.inf if unlimited_completion else float(integer_time_limit_s if integer_time_limit_s is not None else os.environ.get('MOBILEESS_R25M_B6_INTEGER_TIMELIMIT','600')))
    kbest=int(os.environ.get('MOBILEESS_R25M_B6_KBEST',str(kbest)))
    pricing_tol=float(os.environ.get('MOBILEESS_R25M_B6_PRICING_TOL',str(pricing_tol)))
    pricing_batch=max(1,int(os.environ.get('MOBILEESS_R25M_B6_PRICING_BATCH','8')))
    child_pricing_batch=max(1,int(os.environ.get('MOBILEESS_R25M_B6C2_CHILD_PRICING_BATCH','8')))
    dual_stab_enabled=(os.environ.get('MOBILEESS_R25M_B6C3_DUAL_STABILIZATION','1')=='1')
    dual_stab_alpha=float(os.environ.get('MOBILEESS_R25M_B6C3_DUAL_ALPHA','0.65'))
    dual_center_beta=float(os.environ.get('MOBILEESS_R25M_B6C3_CENTER_BETA','0.75'))
    dual_stab_batch=max(1,int(os.environ.get('MOBILEESS_R25M_B6C3_STABILIZED_BATCH','8')))
    strong_branch_enabled=(os.environ.get('MOBILEESS_R25M_B6C4_STRONG_BRANCHING','1')=='1')
    strong_branch_candidates=max(1,int(os.environ.get('MOBILEESS_R25M_B6C4_STRONG_CANDIDATES','4')))
    strong_probe_time=float(os.environ.get('MOBILEESS_R25M_B6C4_PROBE_TIMELIMIT','1.5'))
    strong_early_weight=float(os.environ.get('MOBILEESS_R25M_B6C4_EARLY_WEIGHT','0.35'))
    pseudocost_reliability=max(1,int(os.environ.get('MOBILEESS_R25M_B6C4_PSEUDOCOST_RELIABILITY','2')))
    rc_audit_tol=float(os.environ.get('MOBILEESS_R25M_B6_RC_AUDIT_TOL','1e-4'))
    bounded_rc_envelope=(os.environ.get('MOBILEESS_R25Q_BOUNDED_RC_ENVELOPE','0')=='1')
    rc_envelope_hard_cap=float(os.environ.get('MOBILEESS_R25Q_RC_ENVELOPE_HARD_CAP','5e-4'))
    bounded_rc_strict_retry_budget=max(0,int(os.environ.get('MOBILEESS_R25R_RC_STRICT_RETRY_BUDGET','2')))
    # C5R2 numerical-policy repair: this is a QCP/SOCP master, so BarQCPConvTol
    # (not BarConvTol) controls barrier convergence relevant to QCP dual recovery.
    qcp_barrier_tol=float(os.environ.get('MOBILEESS_R25N_B6C5R2_BARQCP_TOL','1e-9'))
    qcp_dual_retry_tols=qcp_dual_retry_schedule(qcp_barrier_tol)
    thread_screen_mode=(os.environ.get('MOBILEESS_R25N_B6C5R2_THREAD_SCREEN','0')=='1')
    thread_screen_iters=max(1,int(os.environ.get('MOBILEESS_R25N_B6C5R2_THREAD_SCREEN_ITERS','6')))
    c5r3_mobility_first=(os.environ.get('MOBILEESS_R25N_B6C5R3_MOBILITY_FIRST','1')=='1')
    c5r3_fd_multiway=(os.environ.get('MOBILEESS_R25N_B6C5R3_FIXED_DUAL_MULTIWAY','1')=='1')
    c5r3_fd_multiway_max=max(1,int(os.environ.get('MOBILEESS_R25N_B6C5R3_FIXED_DUAL_MULTIWAY_MAX_EXPLICIT','4')))
    c5r4_disable_fixed_dual=(os.environ.get('MOBILEESS_R25N_B6C5R4_DISABLE_FIXED_DUAL_PREPASS','0')=='1')
    c5r4_polish_enabled=(os.environ.get('MOBILEESS_R25N_B6C5R4_FIXED_INTEGER_QCP_POLISH','0')=='1')
    c5r4_polish_time=(math.inf if unlimited_completion else float(os.environ.get('MOBILEESS_R25N_B6C5R4_POLISH_TIMELIMIT','180')))
    c5r4_polish_constr_gate=float(os.environ.get('MOBILEESS_R25N_B6C5R4_POLISH_CONSTR_GATE','1e-6'))
    c5r4_polish_bound_gate=float(os.environ.get('MOBILEESS_R25N_B6C5R4_POLISH_BOUND_GATE','1e-7'))
    # R25T changes solver orchestration only.  The original compact MIQCP is
    # retained as a separate exact authority while path decomposition runs on a
    # copy.  A bounded restricted-master phase supplies incumbents; the original
    # compact model then supplies both feasible incumbents and a native global
    # bound.  No restricted-master ObjBound is promoted to global authority.
    r25t_global_portfolio=(os.environ.get('MOBILEESS_R25T_GLOBAL_PORTFOLIO','0')=='1')
    r25t_primal_min_s=float(os.environ.get('MOBILEESS_R25T_PRIMAL_MIN_SECONDS','60'))
    r25t_primal_stall_s=float(os.environ.get('MOBILEESS_R25T_PRIMAL_STALL_SECONDS','120'))
    r25t_primal_max_s=float(os.environ.get('MOBILEESS_R25T_PRIMAL_MAX_SECONDS','600'))
    r25t_primal_max_nodes=max(1,int(os.environ.get('MOBILEESS_R25T_PRIMAL_MAX_NODES','200000')))
    r25t_meaningful_fraction=float(os.environ.get('MOBILEESS_R25T_MEANINGFUL_IMPROVEMENT_FRACTION','0.02'))
    r25t_compact_mip_focus=int(os.environ.get('MOBILEESS_R25T_COMPACT_MIPFOCUS','3'))
    # R25U exact-safe search guidance.  These controls add only mathematically
    # feasible path columns to the continuous working master and transfer a
    # feasible RMP solution as native MIP hints.  They do not remove a path,
    # alter a row, or promote a restricted bound to global authority.
    r25u_initial_hint_kbest=max(1,int(os.environ.get('MOBILEESS_R25U_INITIAL_HINT_KBEST','1')))
    r25u_initial_objective_kbest=max(1,int(os.environ.get('MOBILEESS_R25U_INITIAL_OBJECTIVE_KBEST','1')))
    r25u_rmp_hint_priority=max(0,int(os.environ.get('MOBILEESS_R25U_RMP_HINT_PRIORITY','50')))
    root_forensic_only=(os.environ.get('MOBILEESS_R25N_B6C5R2_ROOT_FORENSIC_ONLY','0')=='1')
    c5r4r1_root_pricing_only=(os.environ.get('MOBILEESS_R25O_B6C5R4R1_ROOT_PRICING_ONLY','0')=='1')
    block_diag_time=float(os.environ.get('MOBILEESS_R25N_B6C5R2_BLOCK_DIAG_TIMELIMIT','20'))
    b6r3_branch_price=(os.environ.get('MOBILEESS_R25M_B6R3_BRANCH_PRICE','0')=='1')
    primal_kbest=max(1,int(os.environ.get('MOBILEESS_R25M_B6R3_PRIMAL_KBEST','32')))
    bp_time_limit=(math.inf if unlimited_completion else float(os.environ.get('MOBILEESS_R25M_B6R3_BP_TIMELIMIT','600')))
    bp_node_limit=(None if unlimited_completion else max(1,int(os.environ.get('MOBILEESS_R25M_B6R3_BP_NODE_LIMIT','64'))))
    bp_node_cg_limit=(math.inf if unlimited_completion else float(os.environ.get('MOBILEESS_R25M_B6R3_BP_NODE_CG_TIMELIMIT','90')))
    if not (pricing_tol>0 and rc_audit_tol>pricing_tol and rc_envelope_hard_cap>=rc_audit_tol and qcp_barrier_tol>0 and block_diag_time>0 and bp_time_limit>0 and bp_node_cg_limit>0 and c5r4_polish_time>0 and c5r4_polish_constr_gate>0 and c5r4_polish_bound_gate>0):
        raise ValueError('invalid B6R3 numerical/pricing/branch-price tolerances')
    if not (0.0<=r25t_primal_min_s<=r25t_primal_max_s and r25t_primal_stall_s>0.0 and
            0.0<r25t_meaningful_fraction<=1.0 and r25t_compact_mip_focus in (0,1,2,3)):
        raise ValueError('invalid R25T global-portfolio controls')
    if not (0.0 < dual_stab_alpha <= 1.0 and 0.0 <= dual_center_beta < 1.0 and dual_stab_batch >= 1):
        raise ValueError('invalid B6-C3 dual-stabilization controls')
    if not (strong_branch_candidates>=1 and strong_probe_time>0 and strong_early_weight>=0 and pseudocost_reliability>=1):
        raise ValueError('invalid B6-C4 strong-branch controls')
    def _set_solve_time_limit(model,remaining):
        """Apply a finite budget, or Gurobi's actual no-limit parameter value."""
        model.Params.TimeLimit=(GRB.INFINITY if not math.isfinite(float(remaining)) else max(1.0,float(remaining)))
    def _audit_limit(value):
        return None if value is None or not math.isfinite(float(value)) else float(value)
    m.update()
    # Keep the exact compact authority alive for R25T and perform every path
    # projection/mutation on a separate model object.  The dictionaries supplied
    # by main.py contain model-bound Var handles, so remap them by immutable names.
    compact_authority=m if r25t_global_portfolio else None
    compact_stay=dict(stay) if r25t_global_portfolio else None
    compact_mv=dict(mv) if r25t_global_portfolio else None
    compact_node_occ=dict(node_occ) if r25t_global_portfolio else None
    if r25t_global_portfolio:
        work=m.copy();work.update()
        compact_digest,compact_counts=exact_gurobi_model_structure_digest(compact_authority)
        work_digest,work_counts=exact_gurobi_model_structure_digest(work)
        copy_audit={
            'status':'PASS' if compact_digest==work_digest and compact_counts==work_counts else 'FAIL_CLOSED',
            'revision':'R25T_B6C6_COPY_STRUCTURE_AUDIT_V1',
            'audit_scope':'complete mathematical model before path projection',
            'scientific_structure_equal':bool(compact_digest==work_digest and compact_counts==work_counts),
            'scientific_structure_sha256':compact_digest,
            'working_copy_structure_sha256':work_digest,
            'counts':compact_counts,
            'working_copy_counts':work_counts,
            'compact_fingerprint':int(compact_authority.Fingerprint),
            'working_copy_fingerprint':int(work.Fingerprint),
            'fingerprint_equal_diagnostic_only':bool(int(work.Fingerprint)==int(compact_authority.Fingerprint)),
            'search_guidance_attributes_excluded':['Start','VarHintVal','VarHintPri','BranchPriority'],
            'AC_QCP_changed':False,
        }
        out.mkdir(parents=True,exist_ok=True)
        import json as _copy_json
        (out/'ConversationA_R25T_EXACT_COPY_STRUCTURE_AUDIT.json').write_text(
            _copy_json.dumps(copy_audit,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        if not copy_audit['scientific_structure_equal']:
            raise RuntimeError('R25T exact working copy mathematical structure differs before projection')
        print('[R25T COPY_AUDIT] scientific_structure_equal=true '
              f'fingerprint_equal={str(copy_audit["fingerprint_equal_diagnostic_only"]).lower()} '
              f'sha256={compact_digest}',flush=True)
        def _remap_vars(mapping):
            ans={}
            for key,var in mapping.items():
                vv=work.getVarByName(var.VarName)
                if vv is None:raise RuntimeError('R25T working copy missing variable '+str(var.VarName))
                ans[key]=vv
            return ans
        stay=_remap_vars(stay);mv=_remap_vars(mv);node_occ=_remap_vars(node_occ)
        m=work

    # Runtime DAGs and exact correspondence to the original mobility variables.
    graphs={};byid={};arc_varname={};node_varname={};source={}
    for mid in mids:
        aa=[];source[mid]=(int(avail_h[mid]),str(initial_sid[mid]))
        for (mm,h,sid),v in stay.items():
            if mm!=mid:continue
            aid=f'S|{mid}|{int(h)}|{sid}';a=Arc(aid,(int(h),str(sid)),(int(h)+1,str(sid)),'STAY')
            aa.append(a);byid[aid]=a;arc_varname[aid]=v.VarName
        for (mm,h,slot),v in mv.items():
            if mm!=mid:continue
            q=moves[(int(h),int(slot))]
            aid=f'M|{mid}|{int(h)}|{int(slot)}';a=Arc(aid,(int(h),str(q['source'])),(int(h)+int(q['D']),str(q['dest'])),'MOVE',slot=int(slot),safe_energy_kwh=float(q['energy_kWh']),route_penalty=float(q['energy_kWh']))
            aa.append(a);byid[aid]=a;arc_varname[aid]=v.VarName
        validate_dag(aa,source[mid],H);graphs[mid]=aa
        for (mm,h,sid),v in node_occ.items():
            if mm==mid:node_varname[(mid,int(h),str(sid))]=v.VarName

    mob_vars=list(stay.values())+list(mv.values())+list(node_occ.values())
    mob_names={v.VarName for v in mob_vars};var_by_name={v.VarName:v for v in mob_vars}
    flow_rows=[c for c in m.getConstrs() if _flow_constraint_name(c.ConstrName,mids)]
    flow_set=set(flow_rows)

    # Fail closed if a mobility variable leaked into a quadratic constraint.  The
    # column projection below is exact only because every mobility coupling is linear.
    qmob=[]
    for qc in m.getQConstrs():
        qe=m.getQCRow(qc)
        try:
            le=qe.getLinExpr()
            for i in range(le.size()):
                if le.getVar(i).VarName in mob_names:qmob.append((qc.QCName,le.getVar(i).VarName,'linear'))
        except Exception:pass
        try:
            for i in range(qe.size()):
                v1=qe.getVar1(i);v2=qe.getVar2(i)
                if v1.VarName in mob_names or v2.VarName in mob_names:qmob.append((qc.QCName,v1.VarName,v2.VarName))
        except Exception:pass
    if qmob:raise RuntimeError('B6 mobility variable appears in quadratic row: '+repr(qmob[:8]))

    # Capture exact linear columns and objective coefficients before projection.
    contrib={};objcoef={};hint_score={}
    retained_constraints=set(m.getConstrs())-flow_set
    for v in mob_vars:
        name=v.VarName;objcoef[name]=float(v.Obj);lst=[]
        col=m.getCol(v)
        for i in range(col.size()):
            c=col.getConstr(i)
            if c in flow_set:continue
            lst.append((c,float(col.getCoeff(i))))
        contrib[name]=lst
        hs=0.0
        try:
            hv=float(v.VarHintVal);hp=int(v.VarHintPri)
            if math.isfinite(hv) and hv>0.5 and hp>0:hs=float(hp)
        except Exception:pass
        hint_score[name]=hs

    def path_varnames(mid,path):
        ns=_path_nodes(source[mid],path,byid);names=[]
        nv=node_varname.get((mid,ns[0][0],ns[0][1]))
        if nv is not None:names.append(nv)
        for aid,n in zip(path,ns[1:]):
            names.append(arc_varname[aid]);nv=node_varname.get((mid,n[0],n[1]))
            if nv is not None:names.append(nv)
        return names
    def path_obj(mid,path):return sum(objcoef.get(n,0.0) for n in path_varnames(mid,path))
    def path_coeffs(mid,path):
        d=defaultdict(float)
        for n in path_varnames(mid,path):
            for c,a in contrib.get(n,()):d[c]+=a
        return {c:a for c,a in d.items() if abs(a)>1e-14}

    # Seed deterministic causal columns: zero-cost feasible path, objective-min path,
    # and the feasible path with maximum overlap with previous-plan VarHints.
    pools={mid:{} for mid in mids};lvars={mid:{} for mid in mids};conv={}
    def add_path(mid,path,sink,label):
        path=tuple(path)
        if path in pools[mid]:return False
        coeff=path_coeffs(mid,path);cs=list(coeff);vals=[coeff[c] for c in cs]
        lam=m.addVar(lb=0.0,ub=GRB.INFINITY,vtype=GRB.CONTINUOUS,obj=path_obj(mid,path),column=gp.Column(vals,cs),name=f'b6lam_{mid}_{len(pools[mid]):04d}')
        pools[mid][path]=RuntimePath(mid,path,sink);lvars[mid][path]=lam
        if mid in conv:m.chgCoeff(conv[mid],lam,1.0)
        return True
    initial_seed_enrichment={mid:{'zero':0,'objective':0,'hint':0} for mid in mids}
    for mid in mids:
        zcost={a.arc_id:0.0 for a in graphs[mid]};_,p,s=shortest_path_pricing(graphs[mid],source[mid],H,zcost);add_path(mid,p,s,'zero')
        initial_seed_enrichment[mid]['zero']=1
        ocost={a.arc_id:objcoef.get(arc_varname[a.arc_id],0.0)+objcoef.get(node_varname.get((mid,a.head[0],a.head[1]),''),0.0) for a in graphs[mid]}
        for _,p,s in k_shortest_paths_dag(graphs[mid],source[mid],H,ocost,r25u_initial_objective_kbest):
            if add_path(mid,p,s,'objective'):
                initial_seed_enrichment[mid]['objective']+=1
        hcost={a.arc_id:-(hint_score.get(arc_varname[a.arc_id],0.0)+hint_score.get(node_varname.get((mid,a.head[0],a.head[1]),''),0.0)) for a in graphs[mid]}
        for _,p,s in k_shortest_paths_dag(graphs[mid],source[mid],H,hcost,r25u_initial_hint_kbest):
            if add_path(mid,p,s,'hint'):
                initial_seed_enrichment[mid]['hint']+=1
        m.update();conv[mid]=m.addLConstr(gp.quicksum(lvars[mid].values())==1.0,name=f'b6_path_convexity_{mid}')
    m.update()

    original_nonmob_types=[]
    for v in m.getVars():
        if v.VarName not in mob_names and not v.VarName.startswith('b6lam_'):
            original_nonmob_types.append((v,v.VType))
    # Remove the extended network representation after its coefficients have been
    # exactly aggregated into the path columns.
    m.remove(flow_rows);m.remove(mob_vars);m.update()
    projected_stats={'removed_STAY':len(stay),'removed_MOVE':len(mv),'removed_node_occupancy':len(node_occ),'removed_flow_rows':len(flow_rows),
                      'initial_columns':{mid:len(pools[mid]) for mid in mids},'post_projection_variables':int(m.NumVars),'post_projection_linear_rows':int(m.NumConstrs),'post_projection_qrows':int(m.NumQConstrs)}
    projected_stats['initial_exact_seed_enrichment']=initial_seed_enrichment

    # B6-C4 selection-only reliability strong branching.  Probe objectives and
    # pseudocosts are NEVER scientific lower-bound authority; they select only
    # which exact branch partition is explored next.  Every accepted child still
    # receives full exact pricing closure before its lower bound can be used.
    nonmob_static_meta=[(v.VarName,typ,float(v.LB),float(v.UB)) for v,typ in original_nonmob_types]
    branch_pseudocost=defaultdict(lambda:{0:[0.0,0],1:[0.0,0]})
    branch_selection_records=[]

    def _name_of(v_or_name):
        return v_or_name if isinstance(v_or_name,str) else v_or_name.VarName

    def _collect_branch_candidates(model,path_name_maps):
        mobcand=[]
        for mm in mids:
            agg=defaultdict(float)
            for path,vv0 in path_name_maps.get(mm,{}).items():
                vv=model.getVarByName(_name_of(vv0))
                if vv is None or float(vv.UB)<=0:continue
                try:xv=float(vv.X)
                except Exception:continue
                if xv<=1e-9:continue
                for nn in _path_nodes(source[mm],tuple(path),byid):agg[nn]+=xv
            for nn,y in agg.items():
                if nn==source[mm] or int(nn[0])>=H:continue
                frac=branch_fractionality(y)
                if frac>1e-6:mobcand.append((frac,-int(nn[0]),mm,tuple(nn),float(y)))
        intcand=[]
        for name,typ,lb0,ub0 in nonmob_static_meta:
            if typ not in (GRB.BINARY,GRB.INTEGER):continue
            vv=model.getVarByName(name)
            if vv is None:continue
            try:x=float(vv.X)
            except Exception:continue
            frac=branch_fractionality(x)
            if frac>1e-6:intcand.append((frac,name,float(x),typ,float(vv.LB),float(vv.UB)))
        return mobcand,intcand

    def _probe_branch(model,path_name_maps,branch,side):
        # Restricted-column probe used ONLY for branch selection.  Missing columns
        # can make this objective optimistic as a *score* but it is never promoted
        # to a B&P lower bound and never used for pruning/certification.
        pm=model.copy();pm.Params.OutputFlag=0;pm.Params.QCPDual=0;pm.Params.Method=2
        pm.Params.TimeLimit=max(0.1,float(strong_probe_time))
        if branch[0]=='mobility_node':
            _,mm,nn,y=branch;nn=tuple(nn)
            for path,vv0 in path_name_maps.get(mm,{}).items():
                pv=pm.getVarByName(_name_of(vv0))
                if pv is None:continue
                contains=nn in set(_path_nodes(source[mm],tuple(path),byid))
                violates=(contains if int(side)==0 else not contains)
                if violates:pv.UB=0.0
        else:
            _,name,x,typ,lo,hi=branch
            vv=pm.getVarByName(name)
            if vv is None:return None
            if int(side)==0:vv.UB=min(float(vv.UB),float(math.floor(x)))
            else:vv.LB=max(float(vv.LB),float(math.ceil(x)))
            if float(vv.LB)>float(vv.UB)+1e-12:return float('inf')
        pm.update();pm.optimize();st=int(pm.Status)
        if st==GRB.INFEASIBLE:return float('inf')
        if st==GRB.OPTIMAL:return float(pm.ObjVal)
        return None

    def _pseudocost_prediction(branch):
        key=branch_candidate_key(branch);hist=branch_pseudocost.get(key)
        if not hist:return None
        if hist[0][1]<pseudocost_reliability or hist[1][1]<pseudocost_reliability:return None
        vals=[]
        for side in (0,1):
            avg=float(hist[side][0])/float(hist[side][1])
            vals.append(avg*branch_side_distance(branch,side))
        return (min(vals),sum(vals))

    def _select_branch(model,path_name_maps,parent_obj,node_tag):
        mobcand,intcand=_collect_branch_candidates(model,path_name_maps)
        # C5R3 forensic result: path/mobility integrality dominates the root gap
        # (restricted-pool diagnostic lift ~13.33 versus ~0.57 for mode and 0 for
        # job/defer).  Prioritize mobility while fractional mobility remains.
        # This is branch ordering only; exact child pricing still certifies bounds.
        if c5r3_mobility_first and mobcand:
            intcand=[]
        shortlist=select_strong_branch_shortlist(mobcand,intcand,H,strong_branch_candidates,strong_early_weight)
        if not shortlist:return None
        if not strong_branch_enabled:return shortlist[0]
        trials=[]
        for rank,b in enumerate(shortlist):
            ps=_pseudocost_prediction(b);mode='pseudocost'
            c0=c1=None
            if ps is None:
                mode='strong_probe';c0=_probe_branch(model,path_name_maps,b,0);c1=_probe_branch(model,path_name_maps,b,1)
                ps=strong_branch_score(parent_obj,c0,c1)
            fallback=branch_fractionality(float(b[3] if b[0]=='mobility_node' else b[2]))
            # Earlier mobility states win only exact score ties.
            early=-(int(b[2][0]) if b[0]=='mobility_node' else H)
            trials.append((float(ps[0]),float(ps[1]),fallback,early,-rank,b,mode,c0,c1))
        best=max(trials,key=lambda z:(z[0],z[1],z[2],z[3],z[4]))
        branch_selection_records.append({
            'node':str(node_tag),'parent_objective':float(parent_obj),
            'shortlist':[repr(z[5]) for z in trials],
            'selected':repr(best[5]),'selected_mode':best[6],
            'selected_score':[float(best[0]),float(best[1])],
            'probe_time_limit_s':float(strong_probe_time),
            'candidate_limit':int(strong_branch_candidates),
            'certificate_authority':False,
            'note':'Strong-branch probes and pseudocosts select a partition only; exact child pricing closure remains mandatory.'
        })
        return best[5]

    def _record_exact_child_pseudocost(branch,side,parent_lb,child_lb):
        if branch is None or not (math.isfinite(float(parent_lb)) and math.isfinite(float(child_lb))):return
        imp=max(0.0,float(child_lb)-float(parent_lb));dist=branch_side_distance(branch,int(side))
        key=branch_candidate_key(branch);rec=branch_pseudocost[key][int(side)]
        rec[0]+=imp/dist;rec[1]+=1

    # Full all-column continuous relaxation via exact pricing.
    for v,typ in original_nonmob_types:
        if typ in (GRB.BINARY,GRB.INTEGER):v.VType=GRB.CONTINUOUS
    for dd in lvars.values():
        for v in dd.values():v.VType=GRB.CONTINUOUS;v.UB=GRB.INFINITY
    m.update()
    _old_numeric_focus=int(m.Params.NumericFocus);_old_scale_flag=int(m.Params.ScaleFlag);_old_barconv=float(m.Params.BarConvTol);_old_barqcp=float(m.Params.BarQCPConvTol);_old_barhom=int(m.Params.BarHomogeneous);_old_quad=int(m.Params.Quad)
    m.Params.QCPDual=1;m.Params.Method=2;m.Params.NumericFocus=max(1,_old_numeric_focus);m.Params.BarQCPConvTol=qcp_barrier_tol
    max_iter=(None if unlimited_completion else int(os.environ.get('MOBILEESS_R25M_B6_MAX_CG_ITER','200')))
    cg_records=[];pricing_closed=False;final_components=None;root_branch_candidate=None
    root_dual_center_pi=None;root_dual_center_conv=None
    root_stab_stats={'enabled':bool(dual_stab_enabled),'candidate_paths_examined':0,'candidate_paths_added':0,
                     'iterations_with_stabilized_candidates':0,'alpha':float(dual_stab_alpha),
                     'center_beta':float(dual_center_beta),'batch':int(dual_stab_batch)}
    cg_start=time.monotonic()
    for it in (itertools.count() if max_iter is None else range(max_iter)):
        rem=cg_limit-(time.monotonic()-cg_start)
        if rem<=0:break
        _set_solve_time_limit(m,rem)
        solve_t0=time.monotonic();m.optimize();rmp_solve_seconds=time.monotonic()-solve_t0
        if int(m.Status)!=GRB.OPTIMAL:
            raise RuntimeError(f'B6 continuous RMP not optimal; status={m.Status} iter={it}')
        # C5R2: QCP dual recovery is explicit.  C5R1 failed at root iteration 22
        # because Gurobi reported an inaccurate QCP-dual KKT solve while the code
        # had tightened BarConvTol, which does not control QCP barrier convergence.
        # Retry only with a strictly tighter BarQCPConvTol; no primal/dual bound is
        # accepted until Pi, convexity Pi, QCPi and path RC are all retrievable.
        dual_retry_count=0;dual_retry_history=[];bounded_rc_envelope_used=False
        # R25R: retain the best fully solved OPTIMAL snapshot before asking the
        # barrier for a stricter KKT solve.  A stricter numerical retry can return
        # SUBOPTIMAL even though the preceding solve was OPTIMAL and had a finite,
        # explicitly measured RC-accounting error inside the conservative cap.
        # Parameter retries must never destroy that already-valid fallback.
        best_bounded_root_candidate=None;best_bounded_root_branch=None;best_bounded_root_params=None
        root_branch_from_saved_optimal=False
        def _root_dual_snapshot(enforce_audit=True):
            rmp_obj_local=float(m.ObjVal)
            pi_local={c:float(c.Pi) for c in retained_constraints}
            conv_pi_local={mid:float(conv[mid].Pi) for mid in mids}
            qcs_local=m.getQConstrs()
            qcp_pi_local=m.getAttr('QCPi',qcs_local) if qcs_local else []
            if any(not math.isfinite(float(z)) for z in qcp_pi_local):raise RuntimeError('nonfinite QCPi')
            sample=[]
            for mm0 in mids:
                for vv0 in lvars[mm0].values():
                    sample.append(float(vv0.RC))
                    if len(sample)>=16:break
                if len(sample)>=16:break
            if not sample or any(not math.isfinite(z) for z in sample):raise RuntimeError('path RC unavailable/nonfinite')
            comp_local={}
            for n0 in mob_names:
                comp_local[n0]=float(objcoef.get(n0,0.0))-sum(float(pi_local[c])*float(a) for c,a in contrib.get(n0,()))
            max_err_local=0.0
            for mm0 in mids:
                pc0=float(conv_pi_local[mm0])
                for path0,lam0 in lvars[mm0].items():
                    manual0=sum(comp_local.get(n0,0.0) for n0 in path_varnames(mm0,path0))-pc0
                    max_err_local=max(max_err_local,abs(manual0-float(lam0.RC)))
            if enforce_audit and not rc_audit_pass(max_err_local,rc_audit_tol):
                raise RuntimeError(f'reduced_cost_accounting_mismatch max_err={max_err_local} tol={rc_audit_tol}')
            return rmp_obj_local,pi_local,conv_pi_local,qcp_pi_local,comp_local,max_err_local
        while True:
            try:
                rmp_obj,pi,current_conv_pi,_qcp_pi,comp,max_rc_err=_root_dual_snapshot()
                break
            except Exception as exc:
                if bounded_rc_envelope and 'reduced_cost_accounting_mismatch' in str(exc):
                    try:
                        candidate=_root_dual_snapshot(enforce_audit=False)
                        candidate_err=float(candidate[-1])
                        if (math.isfinite(candidate_err) and candidate_err<=rc_envelope_hard_cap and
                            (best_bounded_root_candidate is None or candidate_err<float(best_bounded_root_candidate[-1]))):
                            best_bounded_root_candidate=candidate
                            best_bounded_root_params={'BarQCPConvTol':float(m.Params.BarQCPConvTol),
                                'ScaleFlag':int(m.Params.ScaleFlag),'NumericFocus':int(m.Params.NumericFocus),
                                'BarHomogeneous':int(m.Params.BarHomogeneous),'Quad':int(m.Params.Quad)}
                            candidate_names={mm:{p:v.VarName for p,v in lvars[mm].items()} for mm in mids}
                            best_bounded_root_branch=_select_branch(m,candidate_names,float(candidate[0]),f'root_retry_{dual_retry_count}_optimal_candidate')
                    except Exception as candidate_exc:
                        dual_retry_history.append({'bounded_candidate_capture_failed':type(candidate_exc).__name__+':'+str(candidate_exc)})
                if best_bounded_root_candidate is not None and dual_retry_count>=bounded_rc_strict_retry_budget:
                    rmp_obj,pi,current_conv_pi,_qcp_pi,comp,max_rc_err=best_bounded_root_candidate
                    bounded_rc_envelope_used=True
                    root_branch_candidate=best_bounded_root_branch;root_branch_from_saved_optimal=True
                    for pname,pvalue in best_bounded_root_params.items():setattr(m.Params,pname,pvalue)
                    dual_retry_history.append({'bounded_envelope_accept':True,'trigger':'strict_retry_budget_reached',
                        'strict_retry_budget':int(bounded_rc_strict_retry_budget),'measured_max_error':float(max_rc_err),
                        'hard_cap':float(rc_envelope_hard_cap),'source_solve_status':'OPTIMAL',
                        'lower_bound_safety_will_use_measured_error':True})
                    break
                if dual_retry_count+1>=len(qcp_dual_retry_tols):
                    if best_bounded_root_candidate is not None:
                        rmp_obj,pi,current_conv_pi,_qcp_pi,comp,max_rc_err=best_bounded_root_candidate
                        bounded_rc_envelope_used=True
                        root_branch_candidate=best_bounded_root_branch;root_branch_from_saved_optimal=True
                        for pname,pvalue in best_bounded_root_params.items():setattr(m.Params,pname,pvalue)
                        dual_retry_history.append({'bounded_envelope_accept':True,'trigger':'strict_retry_schedule_exhausted',
                            'measured_max_error':float(max_rc_err),'hard_cap':float(rc_envelope_hard_cap),
                            'source_solve_status':'OPTIMAL','lower_bound_safety_will_use_measured_error':True})
                        break
                    raise RuntimeError(f'B6-C5R4R1 QCP dual/RC audit failed after BarQCPConvTol retries; iter={it} last={type(exc).__name__}:{exc} history={dual_retry_history!r}')
                dual_retry_count+=1
                newtol=float(qcp_dual_retry_tols[dual_retry_count])
                dual_retry_history.append({'retry':dual_retry_count,'reason':type(exc).__name__+':'+str(exc),'BarQCPConvTol':newtol})
                m.Params.BarQCPConvTol=newtol
                # A finite but inconsistent RC is a QCP dual-quality failure too.
                # Re-solve with explicit scaling/focus before considering any
                # tolerance envelope. Never accept or merely loosen the mismatch.
                if 'reduced_cost_accounting_mismatch' in str(exc):
                    m.Params.ScaleFlag=2;m.Params.NumericFocus=max(2,int(m.Params.NumericFocus))
                    if dual_retry_count>=3:m.Params.BarHomogeneous=1;m.Params.NumericFocus=3
                    if dual_retry_count>=5:m.Params.Quad=1
                rem2=cg_limit-(time.monotonic()-cg_start)
                if rem2<=0: raise RuntimeError('B6-C5R2 no CG time remaining for QCP-dual recovery')
                _set_solve_time_limit(m,rem2)
                # Parameter-only optimize() may legally reuse the prior barrier
                # point (0 iterations), leaving the same inaccurate KKT duals.
                # Reset solution state so the tighter/scaled retry is a real solve.
                m.reset()
                rt=time.monotonic();m.optimize();rmp_solve_seconds+=time.monotonic()-rt
                if int(m.Status)!=GRB.OPTIMAL:
                    if best_bounded_root_candidate is not None:
                        failed_retry_status=int(m.Status)
                        rmp_obj,pi,current_conv_pi,_qcp_pi,comp,max_rc_err=best_bounded_root_candidate
                        bounded_rc_envelope_used=True
                        root_branch_candidate=best_bounded_root_branch;root_branch_from_saved_optimal=True
                        for pname,pvalue in best_bounded_root_params.items():setattr(m.Params,pname,pvalue)
                        dual_retry_history.append({'bounded_envelope_accept':True,'trigger':'stricter_retry_nonoptimal',
                            'failed_stricter_retry_status':failed_retry_status,'measured_max_error':float(max_rc_err),
                            'hard_cap':float(rc_envelope_hard_cap),'source_solve_status':'OPTIMAL',
                            'lower_bound_safety_will_use_measured_error':True})
                        break
                    raise RuntimeError(f'B6-C5R2 dual-recovery RMP not optimal status={m.Status} iter={it}')
        # R25M/B6R1 lifecycle fix remains: all solution attributes, including the
        # analytical-vs-native RC audit, are cached before model mutation.
        stab_pi=blend_dual_maps(pi,root_dual_center_pi,dual_stab_alpha) if dual_stab_enabled else dict(pi)
        stab_conv=blend_dual_maps(current_conv_pi,root_dual_center_conv,dual_stab_alpha) if dual_stab_enabled else dict(current_conv_pi)
        # This check is a *sign-convention / dual-accounting* audit, not an
        # exact-arithmetic equality test.  Convex-QCP barrier duals are numerical,
        # and B6R1 observed only O(1e-5) drift after 90 RMP solves while true
        # negative reduced costs were O(1e-1..1).  Fail only on a materially large
        # discrepancy; at pricing closure we weaken the global lower bound by a
        # conservative tolerance guard before using it for the 3% certificate.
        new=0;mins={};priced={};new_by_mid={};stab_added_by_mid={};stab_examined_by_mid={}
        # Stabilized components are acceleration-only.  Exact closure and every
        # scientific lower bound still use the true current dual above.
        stab_comp={}
        if dual_stab_enabled:
            for n in mob_names:
                stab_comp[n]=float(objcoef.get(n,0.0))-sum(float(stab_pi[c])*float(a) for c,a in contrib.get(n,()))
        for mid in mids:
            srcn=node_varname.get((mid,source[mid][0],source[mid][1]));srcconst=comp.get(srcn,0.0)
            ac={a.arc_id:comp.get(arc_varname[a.arc_id],0.0)+comp.get(node_varname.get((mid,a.head[0],a.head[1])),0.0) for a in graphs[mid]}
            pc=current_conv_pi[mid]
            # Exact TRUE-dual shortest path remains the closure oracle.  The true
            # k-best batch remains available independently of stabilization.
            kb=k_shortest_paths_dag(graphs[mid],source[mid],H,ac,pricing_batch)
            if not kb:raise RuntimeError(f'B6 pricing found no source-to-H path for {mid}')
            val,path,sink=kb[0]
            red=float(srcconst+val-pc);mins[mid]=red;priced[mid]=(ac,srcconst)
            nmid=0
            for v2,p2,s2 in kb:
                r2=float(srcconst+float(v2)-pc)
                if r2 < -pricing_tol and p2 not in pools[mid]:
                    if add_path(mid,p2,s2,'pricing_batch_true_dual'):
                        new+=1;nmid+=1
            # B6-C3 dual stabilization: use a lagged convex combination only to
            # propose additional paths.  Every proposed path is re-evaluated under
            # the TRUE current dual and is inserted only if its true RC is negative.
            # Therefore stabilization cannot create a false pricing closure or a
            # false global lower bound.
            sadd=0;sexam=0
            if dual_stab_enabled:
                ssrc=float(stab_comp.get(srcn,0.0))
                sac={a.arc_id:float(stab_comp.get(arc_varname[a.arc_id],0.0))+float(stab_comp.get(node_varname.get((mid,a.head[0],a.head[1])),0.0)) for a in graphs[mid]}
                skb=k_shortest_paths_dag(graphs[mid],source[mid],H,sac,dual_stab_batch)
                for _,p2,s2 in skb:
                    sexam+=1;root_stab_stats['candidate_paths_examined']+=1
                    if p2 in pools[mid]:continue
                    true_rc=true_reduced_cost_for_path(mid,p2,comp,pc,path_varnames)
                    if true_rc < -pricing_tol:
                        if add_path(mid,p2,s2,'pricing_stabilized_true_rc_filtered'):
                            new+=1;nmid+=1;sadd+=1;root_stab_stats['candidate_paths_added']+=1
                if sadd>0:root_stab_stats['iterations_with_stabilized_candidates']+=1
            new_by_mid[mid]=nmid;stab_added_by_mid[mid]=sadd;stab_examined_by_mid[mid]=sexam
        # Record the objective of the solved RMP before mutating the model.
        # The column_count shown is the pool *after* this pricing pass, while
        # rmp_objective is the valid objective of the pre-addition solved RMP.
        effective_rc_guard=max(float(rc_audit_tol),float(max_rc_err))
        cg_records.append({'iteration':it,'rmp_objective':rmp_obj,'new_columns':new,'new_columns_by_mid':new_by_mid,'pricing_batch':pricing_batch,'min_reduced_cost':mins,'max_existing_lambda_rc_check_error':max_rc_err,'rc_audit_tolerance':rc_audit_tol,'effective_rc_guard':effective_rc_guard,'bounded_rc_envelope_used':bounded_rc_envelope_used,'column_count':{mid:len(pools[mid]) for mid in mids},
                           'rmp_solve_seconds':float(rmp_solve_seconds),'threads':int(m.Params.Threads),
                           'BarQCPConvTol':float(m.Params.BarQCPConvTol),'ScaleFlag':int(m.Params.ScaleFlag),'NumericFocus':int(m.Params.NumericFocus),'qcp_dual_retry_count':int(dual_retry_count),
                           'qcp_dual_retry_history':dual_retry_history,'qcp_pi_count':len(_qcp_pi),
                           'dual_stabilization':{'enabled':bool(dual_stab_enabled),'alpha':float(dual_stab_alpha),'center_beta':float(dual_center_beta),
                                                'stabilized_candidates_examined_by_mid':stab_examined_by_mid,'stabilized_candidates_added_by_mid':stab_added_by_mid}})
        try:
            import json
            (out/'ConversationA_R25M_B6_CG_LIVE.json').write_text(json.dumps({
                'revision':'R25M_B6R2_BATCH_PRICING_NUMERICAL_GUARD','iteration':it,
                'rmp_objective':rmp_obj,'new_columns':new,'new_columns_by_mid':new_by_mid,'pricing_batch':pricing_batch,'min_reduced_cost':mins,
                'max_existing_lambda_rc_check_error':max_rc_err,'rc_audit_tolerance':rc_audit_tol,
                'column_count':{mid:len(pools[mid]) for mid in mids},
                'dual_stabilization':{'enabled':bool(dual_stab_enabled),'alpha':float(dual_stab_alpha),'center_beta':float(dual_center_beta),
                                      'stabilized_candidates_examined_by_mid':stab_examined_by_mid,'stabilized_candidates_added_by_mid':stab_added_by_mid},
                'elapsed_s':time.monotonic()-cg_start,'rmp_solve_seconds':float(rmp_solve_seconds),
                'threads':int(m.Params.Threads),'BarQCPConvTol':float(m.Params.BarQCPConvTol),'ScaleFlag':int(m.Params.ScaleFlag),'NumericFocus':int(m.Params.NumericFocus),
                'qcp_dual_retry_count':int(dual_retry_count),'qcp_dual_retry_history':dual_retry_history},indent=2)+'\n',encoding='utf-8')
        except Exception:
            pass
        # Update the lagged center only after all candidate generation and true-RC
        # filtering for the current solved RMP.  The center is never authoritative.
        if dual_stab_enabled:
            root_dual_center_pi=update_dual_center(root_dual_center_pi,pi,dual_center_beta)
            root_dual_center_conv=update_dual_center(root_dual_center_conv,current_conv_pi,dual_center_beta)
        if new==0:
            # Numerical closure is accepted only inside the explicit RC audit
            # envelope.  The lower bound is then weakened by one full audit
            # tolerance per MESS plus a tiny objective-scale guard.  This makes the
            # final 3% certificate conservative rather than optimistic.
            if all(v>=-effective_rc_guard for v in mins.values()):
                full_lb,lb_safety=guarded_full_lb(rmp_obj,len(mids),effective_rc_guard)
                # B6R4: cache a valid branching candidate while the exact all-column
                # root relaxation solution is still alive.  This lets the external
                # B&P tree reuse the already-certified root lower bound instead of
                # redundantly re-solving/re-pricing the root after the integer phase.
                # B6-C4: choose the root partition with reliability strong
                # branching instead of the previous "closest to 0.5" rule.  The
                # probe models are selection-only and cannot certify/prune anything.
                if not root_branch_from_saved_optimal:
                    root_names={mm:{p:v.VarName for p,v in lvars[mm].items()} for mm in mids}
                    root_branch_candidate=_select_branch(m,root_names,rmp_obj,'root_priced_closed')
                pricing_closed=True;final_components=(comp,priced,dict(current_conv_pi),float(rmp_obj));raw_full_lb=float(rmp_obj);break
            raise RuntimeError('B6 negative reduced-cost path already present outside numerical closure guard')
        # Apply newly generated columns only after every solution attribute needed
        # from the current RMP has been cached.  The next loop iteration re-solves.
        m.update()
        if thread_screen_mode and (it+1)>=thread_screen_iters:
            import json as _json
            recs=list(cg_records)
            total_s=sum(float(r.get('rmp_solve_seconds',0.0)) for r in recs)
            audit={'status':'THREAD_SCREEN_COMPLETE','revision':'R25N_B6C5R2_THREAD_GAP_SOURCE_FORENSIC',
                   'threads':int(m.Params.Threads),'completed_cg_iterations':len(recs),
                   'mean_rmp_solve_seconds':(total_s/len(recs) if recs else None),'total_rmp_solve_seconds':total_s,
                   'cg_elapsed_s':float(time.monotonic()-cg_start),'last_objective':float(rmp_obj),
                   'last_min_reduced_cost':mins,'last_new_columns':int(new),
                   'BarQCPConvTol':float(m.Params.BarQCPConvTol),'qcp_dual_retry_total':sum(int(r.get('qcp_dual_retry_count',0)) for r in recs),
                   'pricing_closed':False,'scientific_authority':False,'physical_h0_committed':False}
            (out/'ConversationA_R25N_B6C5R2_THREAD_SCREEN_AUDIT.json').write_text(_json.dumps(audit,indent=2)+'\n',encoding='utf-8')
            raise RuntimeError('B6C5R2_THREAD_SCREEN_COMPLETE')
    if not pricing_closed:
        raise RuntimeError(f'B6 pricing did not close within limit; iterations={len(cg_records)}')
    cg_seconds=time.monotonic()-cg_start
    if thread_screen_mode:
        import json as _json
        recs=list(cg_records);total_s=sum(float(r.get('rmp_solve_seconds',0.0)) for r in recs)
        audit={'status':'THREAD_SCREEN_COMPLETE','revision':'R25N_B6C5R2_THREAD_GAP_SOURCE_FORENSIC',
               'threads':int(m.Params.Threads),'completed_cg_iterations':len(recs),
               'mean_rmp_solve_seconds':(total_s/len(recs) if recs else None),'total_rmp_solve_seconds':total_s,
               'cg_elapsed_s':float(cg_seconds),'last_objective':float(raw_full_lb),
               'BarQCPConvTol':float(m.Params.BarQCPConvTol),'qcp_dual_retry_total':sum(int(r.get('qcp_dual_retry_count',0)) for r in recs),
               'pricing_closed':True,'full_all_column_lower_bound':float(full_lb),
               'scientific_authority':False,'physical_h0_committed':False}
        (out/'ConversationA_R25N_B6C5R2_THREAD_SCREEN_AUDIT.json').write_text(_json.dumps(audit,indent=2)+'\n',encoding='utf-8')
        raise RuntimeError('B6C5R2_THREAD_SCREEN_COMPLETE')

    if c5r4r1_root_pricing_only:
        import json as _json
        _root_max_rc=max(float(r.get('max_existing_lambda_rc_check_error',0.0)) for r in cg_records)
        _root_effective_guard=max(float(r.get('effective_rc_guard',rc_audit_tol)) for r in cg_records)
        _root_bounded_used=any(bool(r.get('bounded_rc_envelope_used',False)) for r in cg_records)
        audit={'status':'PASS_ROOT_PRICING_CLOSED','revision':'R25R_B6C5R4R4_RETAINED_OPTIMAL_DUAL_RESUME',
               'threads':int(m.Params.Threads),'pricing_closed':True,'cg_iterations':len(cg_records),
               'cg_seconds':float(cg_seconds),'raw_root_objective':float(raw_full_lb),
               'guarded_full_all_column_lower_bound':float(full_lb),
               'max_rc_accounting_error':_root_max_rc,
               'rc_audit_tolerance':float(rc_audit_tol),
               'effective_rc_guard':_root_effective_guard,
               'bounded_rc_envelope_enabled':bool(bounded_rc_envelope),
               'bounded_rc_envelope_used':_root_bounded_used,
               'bounded_rc_envelope_hard_cap':float(rc_envelope_hard_cap),
               'lower_bound_safety_rule':'subtract effective RC guard once per MESS plus objective-scale guard',
               'qcp_dual_retry_total':sum(int(r.get('qcp_dual_retry_count',0)) for r in cg_records),
               'qcp_dual_retry_history':[x for r in cg_records for x in (r.get('qcp_dual_retry_history') or [])],
               'final_BarQCPConvTol':float(m.Params.BarQCPConvTol),'final_ScaleFlag':int(m.Params.ScaleFlag),
               'final_NumericFocus':int(m.Params.NumericFocus),'final_BarHomogeneous':int(m.Params.BarHomogeneous),
               'final_Quad':int(m.Params.Quad),'scientific_authority':False,
               'physical_h0_committed':False,'long_integer_or_branch_price_run':False}
        (out/'ConversationA_R25O_B6C5R4R1_ROOT_PRICING_AUDIT.json').write_text(_json.dumps(audit,indent=2)+'\n',encoding='utf-8')
        raise RuntimeError('B6C5R4R1_ROOT_PRICING_COMPLETE')

    if root_forensic_only:
        import json as _json
        def _frac(x):
            z=float(x);return abs(z-round(z))
        path_stats={};occ_stats={};all_path_frac=0.0;all_path_count=0
        for mm in mids:
            vals=[];agg=defaultdict(float)
            for path,vv in lvars[mm].items():
                x=float(vv.X);vals.append((x,tuple(path)))
                if 1e-7<x<1-1e-7:
                    all_path_count+=1;all_path_frac+=min(x,1.0-x)
                if x>1e-10:
                    for nn in _path_nodes(source[mm],tuple(path),byid):agg[tuple(nn)]+=x
            frac_occ=[(min(y,1.0-y),nn,y) for nn,y in agg.items() if nn!=source[mm] and int(nn[0])<H and 1e-7<y<1-1e-7]
            frac_occ.sort(reverse=True)
            path_stats[mm]={'positive_paths':sum(1 for x,_ in vals if x>1e-9),'fractional_paths':sum(1 for x,_ in vals if 1e-7<x<1-1e-7),
                            'fractionality_mass':sum(min(x,1.0-x) for x,_ in vals if 1e-7<x<1-1e-7)}
            occ_stats[mm]={'fractional_occupancies':len(frac_occ),'fractionality_mass':sum(z[0] for z in frac_occ),
                           'top_fractional_occupancies':[{'h':int(nn[0]),'service':str(nn[1]),'value':float(y),'fractionality':float(fr)} for fr,nn,y in frac_occ[:20]]}
        block={k:{'fractional_count':0,'fractionality_mass':0.0,'top':[]} for k in ['mode','job_choice','defer','other_integer']}
        for v,typ in original_nonmob_types:
            if typ not in (GRB.BINARY,GRB.INTEGER):continue
            x=float(v.X);f=_frac(x)
            if f<=1e-7:continue
            b=classify_integer_block(v.VarName);block[b]['fractional_count']+=1;block[b]['fractionality_mass']+=min(f,1.0-f)
            block[b]['top'].append({'name':v.VarName,'value':x,'fractionality':min(f,1.0-f)})
        for b in block:block[b]['top']=sorted(block[b]['top'],key=lambda z:-z['fractionality'])[:30]

        # Diagnostic-only restricted-pool block integrality solves.  Their ObjBound
        # must never be promoted to the all-column/global certificate because omitted
        # positive-RC paths can become relevant after integrality is imposed.
        diag_groups={'path_lambda':'path','mode':'mode','job_all':'job','nonmob_all':'nonmob'};block_diag={}
        for label,kind in diag_groups.items():
            dm=m.copy();dm.Params.OutputFlag=0;dm.Params.Threads=int(m.Params.Threads);dm.Params.QCPDual=0;dm.Params.MIPFocus=3;dm.Params.MIPGap=0.0;dm.Params.MIPGapAbs=0.0;dm.Params.TimeLimit=float(block_diag_time)
            if kind=='path':
                for vv in dm.getVars():
                    if vv.VarName.startswith('b6lam_'):vv.VType=GRB.BINARY;vv.UB=min(float(vv.UB),1.0)
            elif kind=='mode':
                for name,typ,_,_ in nonmob_static_meta:
                    if typ in (GRB.BINARY,GRB.INTEGER) and classify_integer_block(name)=='mode':
                        vv=dm.getVarByName(name)
                        if vv is not None:vv.VType=typ
            elif kind=='job':
                for name,typ,_,_ in nonmob_static_meta:
                    if typ in (GRB.BINARY,GRB.INTEGER) and classify_integer_block(name) in ('job_choice','defer'):
                        vv=dm.getVarByName(name)
                        if vv is not None:vv.VType=typ
            else:
                for name,typ,_,_ in nonmob_static_meta:
                    if typ in (GRB.BINARY,GRB.INTEGER):
                        vv=dm.getVarByName(name)
                        if vv is not None:vv.VType=typ
            dm.update();dt=time.monotonic();dm.optimize();elapsed=time.monotonic()-dt
            try:bd=float(dm.ObjBound) if int(dm.IsMIP) else float(dm.ObjVal)
            except Exception:bd=None
            try:iv=float(dm.ObjVal) if int(dm.SolCount)>0 else None
            except Exception:iv=None
            block_diag[label]={'status':int(dm.Status),'is_mip':int(dm.IsMIP),'obj_bound':bd,'incumbent':iv,'elapsed_s':elapsed,
                               'restricted_pool_bound_lift_vs_exact_continuous_root':(None if bd is None else float(bd)-float(raw_full_lb)),
                               'scientific_lower_bound_authority':False}
        audit={'status':'PASS_ROOT_GAP_SOURCE_FORENSIC','revision':'R25N_B6C5R2_THREAD_GAP_SOURCE_FORENSIC',
               'threads':int(m.Params.Threads),'pricing_closed':True,'cg_iterations':len(cg_records),'cg_seconds':float(cg_seconds),
               'raw_root_objective':float(raw_full_lb),'guarded_full_all_column_lower_bound':float(full_lb),
               'BarQCPConvTol':float(m.Params.BarQCPConvTol),'BarConvTol_not_qcp_authority':float(m.Params.BarConvTol),
               'qcp_dual_retry_total':sum(int(r.get('qcp_dual_retry_count',0)) for r in cg_records),
               'path_lambda_fractionality':{'fractional_count':all_path_count,'fractionality_mass':all_path_frac,'by_mess':path_stats},
               'mobility_occupancy_fractionality':occ_stats,'nonmobility_integer_fractionality':block,
               'restricted_pool_block_integrality_diagnostics':block_diag,
               'diagnostic_limitations':'Block-integrality ObjBound values use the generated root path pool only and are NOT all-column/global lower-bound authority.',
               'scientific_feasible_set_changed':False,'objective_changed':False,'physical_h0_committed':False}
        (out/'ConversationA_R25N_B6C5R2_GAP_SOURCE_FORENSIC.json').write_text(_json.dumps(audit,indent=2)+'\n',encoding='utf-8')
        raise RuntimeError('B6C5R2_ROOT_FORENSIC_COMPLETE')

    # Enrich the compact integer RMP with deterministic path families.  These are
    # used only to obtain a better feasible incumbent U; the certified lower bound
    # remains the exact all-column priced relaxation and is never taken from this
    # restricted pool.
    comp,priced,final_conv_pi,final_rmp_obj=final_components;added_kbest=0;primal_enrichment={mid:{} for mid in mids}
    for mid in mids:
        ac,_=priced[mid]
        fam={
          'final_dual':ac,
          'raw_objective':{a.arc_id:objcoef.get(arc_varname[a.arc_id],0.0)+objcoef.get(node_varname.get((mid,a.head[0],a.head[1]),''),0.0) for a in graphs[mid]},
          'previous_hint':{a.arc_id:-(hint_score.get(arc_varname[a.arc_id],0.0)+hint_score.get(node_varname.get((mid,a.head[0],a.head[1]),''),0.0)) for a in graphs[mid]},
          'safe_energy':{a.arc_id:(float(a.safe_energy_kwh) if a.kind=='MOVE' else 0.0) for a in graphs[mid]},
        }
        for label,costs in fam.items():
            addn=0
            kk=kbest if label=='final_dual' else primal_kbest
            for _,path,sink in k_shortest_paths_dag(graphs[mid],source[mid],H,costs,kk):
                if add_path(mid,path,sink,'primal_'+label):added_kbest+=1;addn+=1
            primal_enrichment[mid][label]=addn
    m.update()

    # R25M/B6-C1 dual-lifecycle correctness repair.  Preserve a pristine
    # *continuous* path-master authority before the separate primal MIP mutates
    # variable types.  Every branch-and-price child is cloned from this object,
    # never from a post-MIP model and never through Model.relax() after a MIP
    # solve.  This keeps Pi/RC/QCPi lifecycle requirements explicit and local.
    bp_continuous_authority=None
    bp_continuous_authority_meta=None
    if b6r3_branch_price and not r25t_global_portfolio:
        bp_continuous_authority=m.copy()
        bp_continuous_authority.Params.QCPDual=1
        bp_continuous_authority.Params.Method=2
        bp_continuous_authority.Params.NumericFocus=max(1,_old_numeric_focus)
        bp_continuous_authority.Params.BarQCPConvTol=qcp_barrier_tol
        bp_continuous_authority.update()
        bp_continuous_authority_meta={
            'num_vars':int(bp_continuous_authority.NumVars),
            'num_linear_rows':int(bp_continuous_authority.NumConstrs),
            'num_qrows':int(bp_continuous_authority.NumQConstrs),
            'num_int_vars':int(bp_continuous_authority.NumIntVars),
            'num_bin_vars':int(bp_continuous_authority.NumBinVars),
            'is_mip':int(bp_continuous_authority.IsMIP),
            'created_before_primal_integrality_restore':True,
            'source':'priced-closed continuous path master after deterministic primal column enrichment',
        }
        if bp_continuous_authority_meta['num_int_vars']!=0 or bp_continuous_authority_meta['num_bin_vars']!=0 or bp_continuous_authority_meta['is_mip']!=0:
            raise RuntimeError('B6-C1 pristine continuous authority is not continuous: '+repr(bp_continuous_authority_meta))

    # Restore all non-mobility integrality and select exactly one generated path/MESS.
    for v,typ in original_nonmob_types:v.VType=typ
    for mid in mids:
        for v in lvars[mid].values():
            v.VType=GRB.BINARY;v.UB=1.0
            try:v.BranchPriority=30
            except Exception:pass
    m.update();m.Params.QCPDual=0;m.Params.NumericFocus=_old_numeric_focus;m.Params.ScaleFlag=_old_scale_flag;m.Params.BarConvTol=_old_barconv;m.Params.BarQCPConvTol=_old_barqcp;m.Params.BarHomogeneous=_old_barhom;m.Params.Quad=_old_quad;m.Params.MIPGap=0.0;m.Params.MIPGapAbs=0.0;m.Params.MIPFocus=1;m.Params.ImproveStartGap=0.0
    # C5R3: this restricted integer master contributes a feasible incumbent only;
    # its native bound is never scientific authority.  A higher heuristic effort
    # can therefore improve U without weakening the exact global certificate.
    c5r3_primal_heur=float(os.environ.get('MOBILEESS_R25N_B6C5R3_PRIMAL_HEURISTICS','0.20'))
    if not (0.0<=c5r3_primal_heur<=1.0):raise ValueError('invalid C5R3 primal heuristic effort')
    m.Params.Heuristics=c5r3_primal_heur
    if r25t_global_portfolio:
        # The original compact authority is intentionally resident at the same
        # time.  Spill the heuristic RMP tree early and cap its own memory so it
        # cannot starve the subsequent exact compact phase.
        m.Params.NodefileStart=min(float(m.Params.NodefileStart),0.1)
        m.Params.SoftMemLimit=min(float(m.Params.SoftMemLimit),4.0)
    _set_solve_time_limit(m,int_limit)
    cert={'reached':False,'gap':None,'incumbent':None}
    # Single lower-bound authority variable.  It begins at the exact priced root
    # bound and may only be raised by a separately certified gap-closing procedure.
    certificate_lb=float(full_lb)
    primal_phase={
        'bounded':bool(r25t_global_portfolio),'termination_reason':None,
        'last_meaningful_runtime_s':0.0,'last_meaningful_node':0.0,
        'last_meaningful_incumbent':None,'best_incumbent':None,
        'last_improvement_runtime_s':0.0,'last_improvement_node':0.0,
        'incumbent_improvement_count':0,
        'target_incumbent_at_exact_root':incumbent_required_for_gap(full_lb,target_gap),
        'min_seconds':float(r25t_primal_min_s),'stall_seconds':float(r25t_primal_stall_s),
        'max_seconds':float(r25t_primal_max_s),'max_nodes':int(r25t_primal_max_nodes),
        'meaningful_improvement_fraction_of_initial_deficit':float(r25t_meaningful_fraction),
        'nodefile_start_gb':float(m.Params.NodefileStart),
        'soft_memory_limit_gb':float(m.Params.SoftMemLimit),
        'recoverable_memory_transition':False,
    }
    _initial_deficit=[None]
    def cb(model,where):
        if base_callback is not None:
            try:base_callback(model,where)
            except Exception:pass
        if where in (GRB.Callback.MIP,GRB.Callback.MIPSOL):
            try:
                u=float(model.cbGet(GRB.Callback.MIP_OBJBST if where==GRB.Callback.MIP else GRB.Callback.MIPSOL_OBJ))
                runtime=float(model.cbGet(GRB.Callback.RUNTIME))
                nodes=float(model.cbGet(GRB.Callback.MIP_NODCNT if where==GRB.Callback.MIP else GRB.Callback.MIPSOL_NODCNT))
                if math.isfinite(u):
                    previous_best=primal_phase['best_incumbent']
                    if previous_best is None or u<float(previous_best)-1e-9*max(1.0,abs(u)):
                        primal_phase['last_improvement_runtime_s']=runtime
                        primal_phase['last_improvement_node']=nodes
                        primal_phase['incumbent_improvement_count']+=1
                    g=global_relative_gap(u,full_lb)
                    cert.update({'gap':g,'incumbent':u})
                    primal_phase['best_incumbent']=u
                    target_u=float(primal_phase['target_incumbent_at_exact_root'])
                    deficit=max(0.0,u-target_u)
                    if _initial_deficit[0] is None:_initial_deficit[0]=max(deficit,1e-9)
                    meaningful=max(1e-7*max(1.0,abs(u)),r25t_meaningful_fraction*float(_initial_deficit[0]))
                    last=primal_phase['last_meaningful_incumbent']
                    if last is None or u<float(last)-meaningful:
                        primal_phase['last_meaningful_incumbent']=u
                        primal_phase['last_meaningful_runtime_s']=runtime
                        primal_phase['last_meaningful_node']=nodes
                    if g<=float(target_gap)+1e-12:
                        cert['reached']=True;primal_phase['termination_reason']='GLOBAL_3PCT_AT_EXACT_ROOT';model.terminate();return
                if r25t_global_portfolio and runtime>=r25t_primal_min_s:
                    reason=None
                    if runtime>=r25t_primal_max_s:reason='PRIMAL_PHASE_MAX_SECONDS'
                    elif nodes>=r25t_primal_max_nodes:reason='PRIMAL_PHASE_MAX_NODES'
                    elif runtime-float(primal_phase['last_meaningful_runtime_s'])>=r25t_primal_stall_s:
                        reason='PRIMAL_INCUMBENT_STALL'
                    if reason is not None:
                        primal_phase['termination_reason']=reason;model.terminate()
            except Exception:pass
    int_start=time.monotonic()
    try:
        m.optimize(cb)
    except gp.GurobiError as exc:
        error_code=int(getattr(exc,'errno',-1))
        if not (r25t_global_portfolio and r25t_recoverable_restricted_error(error_code)):
            raise
        # This tree has no lower-bound authority in R25T.  Preserve any feasible
        # incumbent it produced, then release the working model before starting
        # the untouched compact exact authority.  With no incumbent the compact
        # model simply starts without a MIP start.
        primal_phase['termination_reason']='PRIMAL_PHASE_MEMORY_PRESSURE'
        primal_phase['recoverable_memory_transition']=True
        primal_phase['gurobi_error_code']=error_code
        primal_phase['gurobi_error_message']=str(exc)
    int_seconds=time.monotonic()-int_start
    if primal_phase['termination_reason'] is None:
        primal_phase['termination_reason']='SOLVER_NATIVE_TERMINATION'
    primal_phase['elapsed_s']=float(int_seconds)
    try:primal_phase['nodes']=float(m.NodeCount)
    except Exception:primal_phase['nodes']=None
    if int(m.SolCount)>0:
        u=float(m.ObjVal);g=global_relative_gap(u,full_lb);cert.update({'gap':g,'incumbent':u,'reached':bool(g<=float(target_gap)+1e-12)})
    else:
        u=float('inf');g=float('inf')

    # Preserve the restricted-master incumbent path before any B6R3 bound-tree work.
    restricted_master_snapshot={
        'status':int(m.Status),'solution_count':int(m.SolCount),
        'incumbent':(float(m.ObjVal) if int(m.SolCount)>0 else None),
        'bound':(float(m.ObjBound) if int(m.SolCount)>0 else None),
        'native_gap':(float(m.MIPGap) if int(m.SolCount)>0 else None),
    }
    selected={};selected_stay=set();selected_move=set()
    if int(m.SolCount)>0:
        for mid in mids:
            hits=[(path,v) for path,v in lvars[mid].items() if float(v.X)>0.5]
            if len(hits)!=1:raise RuntimeError(f'B6 integer RMP selected path cardinality {mid}={len(hits)}')
            path,_=hits[0];selected[mid]=path
            for aid in path:
                a=byid[aid]
                if a.kind=='STAY':selected_stay.add((mid,a.tail[0],a.tail[1]))
                else:selected_move.add((mid,a.tail[0],int(a.slot)))

    # C5R4 numerical polish: freeze the complete incumbent integer decision and
    # re-optimize only the retained continuous convex QCP. This is not a same-issue
    # MIP start and cannot change mobility, workload, mode or defer decisions. It
    # gives the physical extraction and numerical gate the polished P/Q/SOC point.
    fixed_integer_polish={
        'enabled':bool(c5r4_polish_enabled),'attempted':False,'pass':False,
        'same_issue_MIP_start_used':False,'integer_decisions_changed':False,
    }
    if c5r4_polish_enabled and not r25t_global_portfolio:
        if int(m.SolCount)<=0:raise RuntimeError('B6-C5R4 polish requires a feasible restricted-master incumbent')
        fixed_integer_polish['attempted']=True
        pre_obj=float(m.ObjVal);fixed_values={};bad_integrality=[]
        for v,typ in original_nonmob_types:
            if typ not in (GRB.BINARY,GRB.INTEGER):continue
            x=float(v.X);z=float(round(x))
            if abs(x-z)>1e-5:bad_integrality.append((v.VarName,x))
            fixed_values[v.VarName]=z
        for mid in mids:
            chosen=tuple(selected[mid])
            for path,v in lvars[mid].items():fixed_values[v.VarName]=(1.0 if tuple(path)==chosen else 0.0)
        if bad_integrality:raise RuntimeError('B6-C5R4 incumbent integrality drift '+repr(bad_integrality[:8]))
        for name,z in fixed_values.items():
            v=m.getVarByName(name)
            if v is None:raise RuntimeError('B6-C5R4 polish missing integer variable '+name)
            if z<float(v.LB)-1e-9 or z>float(v.UB)+1e-9:raise RuntimeError('B6-C5R4 polish fixed value outside bounds '+name)
            v.LB=z;v.UB=z;v.VType=GRB.CONTINUOUS
        m.update()
        if int(m.NumIntVars)!=0 or int(m.NumBinVars)!=0 or int(m.IsMIP)!=0:
            raise RuntimeError(f'B6-C5R4 fixed-integer polish model not continuous int={m.NumIntVars} bin={m.NumBinVars} isMIP={m.IsMIP}')
        m.Params.QCPDual=0;m.Params.Method=2;m.Params.NumericFocus=3;m.Params.ScaleFlag=2
        m.Params.FeasibilityTol=min(float(m.Params.FeasibilityTol),1e-9)
        m.Params.OptimalityTol=min(float(m.Params.OptimalityTol),1e-9)
        _set_solve_time_limit(m,c5r4_polish_time)
        polish_t0=time.monotonic();attempts=[]
        for ptol in (1e-9,3e-10,1e-10):
            remaining=float(c5r4_polish_time)-(time.monotonic()-polish_t0)
            if remaining<=0:break
            m.Params.BarQCPConvTol=float(ptol);_set_solve_time_limit(m,remaining)
            st0=time.monotonic();m.optimize();elapsed=time.monotonic()-st0
            rec={'BarQCPConvTol':float(ptol),'status':int(m.Status),'elapsed_s':float(elapsed)}
            if int(m.Status)==GRB.OPTIMAL and int(m.SolCount)>0:
                for attr in ('ConstrVio','BoundVio','IntVio','MaxVio'):
                    try:rec[attr]=float(getattr(m,attr))
                    except Exception:pass
                rec['objective']=float(m.ObjVal)
                rec['quality_pass']=bool(
                    math.isfinite(float(rec.get('ConstrVio',float('inf')))) and rec['ConstrVio']<=c5r4_polish_constr_gate and
                    math.isfinite(float(rec.get('BoundVio',float('inf')))) and rec['BoundVio']<=c5r4_polish_bound_gate)
            else:rec['quality_pass']=False
            attempts.append(rec)
            if rec['quality_pass']:break
        if not attempts or not attempts[-1].get('quality_pass'):
            raise RuntimeError('B6-C5R4 fixed-integer continuous QCP polish failed '+repr(attempts[-3:]))
        post_obj=float(m.ObjVal)
        if post_obj>pre_obj+1e-7*max(1.0,abs(pre_obj)):
            raise RuntimeError(f'B6-C5R4 polish worsened fixed-decision objective pre={pre_obj} post={post_obj}')
        max_fix_error=0.0
        for name,z in fixed_values.items():max_fix_error=max(max_fix_error,abs(float(m.getVarByName(name).X)-float(z)))
        if max_fix_error>1e-8:raise RuntimeError(f'B6-C5R4 polished integer-fix drift {max_fix_error}')
        fixed_integer_polish.update({
            'pass':True,'pre_objective':pre_obj,'post_objective':post_obj,
            'objective_improvement':pre_obj-post_obj,'fixed_integer_count':len(fixed_values),
            'max_fixed_value_error':max_fix_error,'elapsed_s':time.monotonic()-polish_t0,
            'attempts':attempts,'continuous_model_num_int_vars':int(m.NumIntVars),
            'continuous_model_num_bin_vars':int(m.NumBinVars),'continuous_model_is_mip':int(m.IsMIP),
            'acceptance_gate':{'ConstrVio':c5r4_polish_constr_gate,'BoundVio':c5r4_polish_bound_gate},
            'authority':'same frozen scalar objective with incumbent integer decisions fixed; continuous convex QCP reoptimized',
        })
        u=post_obj;g=global_relative_gap(u,full_lb)
        cert.update({'gap':g,'incumbent':u,'reached':bool(g<=float(target_gap)+1e-12)})

    # R25T exact global portfolio.  The bounded path-master solve above is used
    # only to create a good incumbent.  Continue on the untouched original
    # compact MIQCP, whose native ObjBound is valid for the complete model.  The
    # exact priced-root bound and the compact-tree bound are independent valid
    # lower bounds, so their maximum remains globally valid.
    compact_exact={
        'enabled':bool(r25t_global_portfolio),'attempted':False,
        'certificate_pass':False,'restricted_objbound_promoted':False,
    }
    if r25t_global_portfolio:
        compact_exact['attempted']=True
        cm=compact_authority
        if cm is None:raise RuntimeError('R25T compact authority missing')
        cm.update()
        compact_exact['pre_solve_structure']={
            'fingerprint':int(cm.Fingerprint),'num_vars':int(cm.NumVars),
            'num_linear_rows':int(cm.NumConstrs),'num_qrows':int(cm.NumQConstrs),
            'num_int_vars':int(cm.NumIntVars),'num_bin_vars':int(cm.NumBinVars),
            'is_mip':int(cm.IsMIP),
        }
        if int(cm.IsMIP)!=1 or int(cm.NumIntVars)<=0:
            raise RuntimeError('R25T compact authority is not the original mixed-integer model')

        # R25V rolling multi-start portfolio. Preserve the causal shifted start
        # attached by main.py, then build the same-issue restricted-master start
        # independently. Gurobi completes/checks both against the unchanged
        # compact model; neither has feasibility or lower-bound authority.
        rolling_start={}
        for vv in cm.getVars():
            try:z=float(vv.Start)
            except Exception:continue
            if math.isfinite(z) and abs(z)<0.5*float(GRB.INFINITY):rolling_start[vv.VarName]=z
        mip_start={'attempted':False,'nonmob_values':0,'mobility_zero_values':0,
                   'mobility_one_values':0,'integer_hint_values':0,
                   'hint_priority':int(r25u_rmp_hint_priority),'source':'NONE',
                   'causal_rolling_start_values':len(rolling_start),
                   'causal_rolling_start_integer_values':sum(
                       1 for name in rolling_start
                       if cm.getVarByName(name) is not None and cm.getVarByName(name).VType in (GRB.BINARY,GRB.INTEGER)),
                   'causal_rolling_start_source':'PREVIOUS_OPTIMIZER_PLAN_SHIFTED_ONE_STEP' if rolling_start else 'NONE'}
        rmp_start={}
        if int(m.SolCount)>0:
            mip_start['attempted']=True;mip_start['source']='RESTRICTED_MASTER_FEASIBLE_INCUMBENT'
            for wv in m.getVars():
                if wv.VarName.startswith('b6lam_'):continue
                cv=cm.getVarByName(wv.VarName)
                if cv is None:continue
                rmp_start[cv.VarName]=float(wv.X);mip_start['nonmob_values']+=1
                if cv.VType in (GRB.BINARY,GRB.INTEGER) and r25u_rmp_hint_priority>0:
                    cv.VarHintVal=float(wv.X)
                    cv.VarHintPri=max(int(cv.VarHintPri),int(r25u_rmp_hint_priority))
                    mip_start['integer_hint_values']+=1
            for name in mob_names:
                cv=cm.getVarByName(name)
                if cv is not None:
                    rmp_start[cv.VarName]=0.0;mip_start['mobility_zero_values']+=1
                    if cv.VType in (GRB.BINARY,GRB.INTEGER) and r25u_rmp_hint_priority>0:
                        cv.VarHintVal=0.0
                        cv.VarHintPri=max(int(cv.VarHintPri),int(r25u_rmp_hint_priority))
                        mip_start['integer_hint_values']+=1
            for mid,path in selected.items():
                for name in path_varnames(mid,path):
                    cv=cm.getVarByName(name)
                    if cv is None:raise RuntimeError('R25T compact MIP-start variable missing '+str(name))
                    rmp_start[cv.VarName]=1.0;mip_start['mobility_one_values']+=1
                    if cv.VType in (GRB.BINARY,GRB.INTEGER) and r25u_rmp_hint_priority>0:
                        cv.VarHintVal=1.0
        starts=[]
        if rolling_start:starts.append(('CAUSAL_SHIFTED_PREVIOUS_PLAN',rolling_start))
        if rmp_start:starts.append(('SAME_ISSUE_RESTRICTED_MASTER',rmp_start))
        if starts:
            cm.NumStart=len(starts)
            for sn,(_,values) in enumerate(starts):
                cm.Params.StartNumber=sn
                for vv in cm.getVars():vv.Start=GRB.UNDEFINED
                for name,z in values.items():
                    cv=cm.getVarByName(name)
                    if cv is None:raise RuntimeError('R25V compact MIP-start variable missing '+str(name))
                    cv.Start=float(z)
            cm.Params.StartNumber=0
        else:
            cm.NumStart=0
            for vv in cm.getVars():vv.Start=GRB.UNDEFINED
        mip_start['native_start_count']=len(starts)
        mip_start['native_start_sources']=[label for label,_ in starts]
        mip_start['rmp_start_values']=len(rmp_start)
        mip_start['all_starts_nonbinding_solver_guidance']=True
        mip_start['current_compact_feasibility_check_required']=True
        cm.update()
        compact_exact['mip_start']=mip_start
        compact_exact['hard_tail_classifier']={
            'compact_integer_variables':int(cm.NumIntVars),
            'compact_binary_variables':int(cm.NumBinVars),
            'compact_variables':int(cm.NumVars),
            'classified_hard_tail':bool(int(cm.NumIntVars)>=8000 or int(cm.NumVars)>=100000),
            'classification_is_diagnostic_only':True,
        }
        # The projected master has finished its only R25T role.  Release its
        # native search tree before the compact exact tree starts so the two
        # potentially large node stores never overlap in memory.
        m.dispose()
        compact_exact['restricted_work_model_disposed_before_compact']=True
        cm.Params.QCPDual=0;cm.Params.MIPGap=0.0;cm.Params.MIPGapAbs=0.0
        cm.Params.MIPFocus=int(r25t_compact_mip_focus)
        cm.Params.Heuristics=max(float(cm.Params.Heuristics),float(c5r3_primal_heur))
        _set_solve_time_limit(cm,math.inf if unlimited_completion else bp_time_limit)
        compact_live={
            'best_global_lower_bound':float(full_lb),'best_incumbent':None,
            'global_gap':None,'termination_reason':None,'callback_updates':0,
            'last_write_monotonic':0.0,
        }
        def _compact_cb(model,where):
            if base_callback is not None:
                try:base_callback(model,where)
                except Exception:pass
            if where not in (GRB.Callback.MIP,GRB.Callback.MIPSOL):return
            try:
                if where==GRB.Callback.MIP:
                    cu=float(model.cbGet(GRB.Callback.MIP_OBJBST));cbnd=float(model.cbGet(GRB.Callback.MIP_OBJBND))
                    cnodes=float(model.cbGet(GRB.Callback.MIP_NODCNT))
                else:
                    cu=float(model.cbGet(GRB.Callback.MIPSOL_OBJ));cbnd=float(model.cbGet(GRB.Callback.MIPSOL_OBJBND))
                    cnodes=float(model.cbGet(GRB.Callback.MIPSOL_NODCNT))
                if not math.isfinite(cu):return
                glb=float(full_lb)
                if math.isfinite(cbnd) and cbnd<=cu+1e-7*max(1.0,abs(cu),abs(cbnd)):
                    glb=max(glb,cbnd)
                cg=global_relative_gap(cu,glb)
                compact_live.update({'best_global_lower_bound':glb,'best_incumbent':cu,
                                     'global_gap':cg,'callback_updates':compact_live['callback_updates']+1})
                now=time.monotonic()
                if now-float(compact_live['last_write_monotonic'])>=10.0:
                    import json as _json
                    compact_live['last_write_monotonic']=now
                    (out/'ConversationA_R25T_COMPACT_EXACT_LIVE.json').write_text(_json.dumps({
                        'schema_version':'r25t.compact_exact_live.v1',
                        'phase':'ORIGINAL_COMPACT_MIQCP_EXACT_BB',
                        'incumbent':cu,'compact_native_lower_bound':cbnd,
                        'exact_priced_root_lower_bound':float(full_lb),
                        'combined_global_lower_bound':glb,'global_certified_gap':cg,
                        'runtime_s':float(model.cbGet(GRB.Callback.RUNTIME)),
                        'nodes':cnodes,
                        'restricted_objbound_global_authority':False,
                        'compact_objbound_global_authority':True,
                    },indent=2)+'\n',encoding='utf-8')
                if cg<=float(target_gap)+1e-12:
                    compact_live['termination_reason']='GLOBAL_3PCT_COMBINED_BOUND';model.terminate()
            except Exception:pass
        compact_t0=time.monotonic();cm.optimize(_compact_cb);compact_seconds=time.monotonic()-compact_t0
        if int(cm.SolCount)<=0:
            raise RuntimeError(f'R25T compact exact solve produced no feasible incumbent status={int(cm.Status)}')
        compact_u=float(cm.ObjVal);compact_native_lb=float(cm.ObjBound)
        if compact_native_lb>compact_u+1e-7*max(1.0,abs(compact_u),abs(compact_native_lb)):
            raise RuntimeError(f'R25T compact lower bound exceeds incumbent L={compact_native_lb} U={compact_u}')
        combined_lb=max(float(full_lb),compact_native_lb)
        combined_gap=global_relative_gap(compact_u,combined_lb)
        compact_pass=bool(combined_gap<=float(target_gap)+1e-12)
        compact_exact.update({
            'status':int(cm.Status),'solution_count':int(cm.SolCount),
            'elapsed_s':float(compact_seconds),'nodes':float(cm.NodeCount),
            'incumbent_before_polish':compact_u,'compact_native_lower_bound':compact_native_lb,
            'exact_priced_root_lower_bound':float(full_lb),'combined_global_lower_bound':combined_lb,
            'global_gap_before_polish':combined_gap,'certificate_pass':compact_pass,
            'termination_reason':compact_live['termination_reason'] or 'SOLVER_NATIVE_TERMINATION',
            'callback_updates':int(compact_live['callback_updates']),
            'global_bound_rule':'max(EXACT_PRICED_ROOT_LB, ORIGINAL_COMPACT_MIQCP_OBJBOUND)',
            'compact_objbound_is_global_authority':True,
            'restricted_objbound_promoted':False,
            'overall_time_limit_s':None if unlimited_completion else _audit_limit(bp_time_limit),
        })
        if not compact_pass:
            raise RuntimeError('R25T compact exact solve ended without global 3% certificate '+repr(compact_exact))
        certificate_lb=float(combined_lb)
        cert.update({'gap':combined_gap,'incumbent':compact_u,'reached':True})

        # Final numerical authority: fix every original discrete variable at the
        # compact feasible incumbent and reoptimize the unchanged continuous QCP.
        fixed_integer_polish={
            'enabled':bool(c5r4_polish_enabled),'attempted':False,'pass':False,
            'same_issue_MIP_start_used':bool(mip_start['attempted']),
            'integer_decisions_changed':False,'source':'R25T_ORIGINAL_COMPACT_MIQCP_INCUMBENT',
        }
        if c5r4_polish_enabled:
            fixed_integer_polish['attempted']=True
            pre_obj=float(cm.ObjVal);fixed_values={};bad_integrality=[]
            for vv in cm.getVars():
                if vv.VType not in (GRB.BINARY,GRB.INTEGER):continue
                x=float(vv.X);z=float(round(x))
                if abs(x-z)>1e-5:bad_integrality.append((vv.VarName,x))
                fixed_values[vv.VarName]=z
            if bad_integrality:raise RuntimeError('R25T compact incumbent integrality drift '+repr(bad_integrality[:8]))
            for name,z in fixed_values.items():
                vv=cm.getVarByName(name)
                if z<float(vv.LB)-1e-9 or z>float(vv.UB)+1e-9:
                    raise RuntimeError('R25T compact polish value outside bounds '+name)
                vv.LB=z;vv.UB=z;vv.VType=GRB.CONTINUOUS
            cm.update()
            if int(cm.NumIntVars)!=0 or int(cm.NumBinVars)!=0 or int(cm.IsMIP)!=0:
                raise RuntimeError('R25T compact fixed model is not continuous')
            cm.Params.QCPDual=0;cm.Params.Method=2;cm.Params.NumericFocus=3;cm.Params.ScaleFlag=2
            cm.Params.FeasibilityTol=min(float(cm.Params.FeasibilityTol),1e-9)
            cm.Params.OptimalityTol=min(float(cm.Params.OptimalityTol),1e-9)
            polish_t0=time.monotonic();attempts=[]
            for ptol in (1e-9,3e-10,1e-10):
                remaining=float(c5r4_polish_time)-(time.monotonic()-polish_t0)
                if remaining<=0:break
                cm.Params.BarQCPConvTol=float(ptol);_set_solve_time_limit(cm,remaining)
                st0=time.monotonic();cm.optimize();elapsed=time.monotonic()-st0
                rec={'BarQCPConvTol':float(ptol),'status':int(cm.Status),'elapsed_s':float(elapsed)}
                if int(cm.Status)==GRB.OPTIMAL and int(cm.SolCount)>0:
                    for attr in ('ConstrVio','BoundVio','IntVio','MaxVio'):
                        try:rec[attr]=float(getattr(cm,attr))
                        except Exception:pass
                    rec['objective']=float(cm.ObjVal)
                    rec['quality_pass']=bool(
                        math.isfinite(float(rec.get('ConstrVio',float('inf')))) and rec['ConstrVio']<=c5r4_polish_constr_gate and
                        math.isfinite(float(rec.get('BoundVio',float('inf')))) and rec['BoundVio']<=c5r4_polish_bound_gate)
                else:rec['quality_pass']=False
                attempts.append(rec)
                if rec['quality_pass']:break
            if not attempts or not attempts[-1].get('quality_pass'):
                raise RuntimeError('R25T compact continuous polish failed '+repr(attempts[-3:]))
            post_obj=float(cm.ObjVal)
            if post_obj>pre_obj+1e-7*max(1.0,abs(pre_obj)):
                raise RuntimeError(f'R25T compact polish worsened objective pre={pre_obj} post={post_obj}')
            max_fix_error=max((abs(float(cm.getVarByName(name).X)-z) for name,z in fixed_values.items()),default=0.0)
            if max_fix_error>1e-8:raise RuntimeError(f'R25T compact polish fixed-value drift {max_fix_error}')
            polished_gap=global_relative_gap(post_obj,certificate_lb)
            if polished_gap>float(target_gap)+1e-12:
                raise RuntimeError('R25T compact polish lost global certificate')
            fixed_integer_polish.update({
                'pass':True,'pre_objective':pre_obj,'post_objective':post_obj,
                'objective_improvement':pre_obj-post_obj,'fixed_integer_count':len(fixed_values),
                'max_fixed_value_error':max_fix_error,'elapsed_s':time.monotonic()-polish_t0,
                'attempts':attempts,'continuous_model_num_int_vars':int(cm.NumIntVars),
                'continuous_model_num_bin_vars':int(cm.NumBinVars),'continuous_model_is_mip':int(cm.IsMIP),
                'acceptance_gate':{'ConstrVio':c5r4_polish_constr_gate,'BoundVio':c5r4_polish_bound_gate},
                'authority':'original compact MIQCP integer incumbent fixed; unchanged continuous convex QCP reoptimized',
            })
            compact_exact['incumbent_after_polish']=post_obj
            compact_exact['global_gap_after_polish']=polished_gap
            cert.update({'gap':polished_gap,'incumbent':post_obj,'reached':True})

        # Reconstruct the mobility path selected by the final compact authority.
        selected={};selected_stay=set();selected_move=set()
        for mid in mids:
            chosen=[]
            for a in graphs[mid]:
                vv=cm.getVarByName(arc_varname[a.arc_id])
                if vv is not None and float(vv.X)>0.5:chosen.append(a)
            chosen.sort(key=lambda a:(int(a.tail[0]),int(a.head[0]),a.arc_id))
            cur=source[mid];ordered=[]
            while int(cur[0])<H:
                hits=[a for a in chosen if a.tail==cur]
                if len(hits)!=1:raise RuntimeError(f'R25T compact path reconstruction {mid} at {cur}: {len(hits)}')
                a=hits[0];ordered.append(a.arc_id);cur=a.head
            selected[mid]=tuple(ordered)
        for key,vv in compact_stay.items():
            if float(vv.X)>0.5:selected_stay.add(key)
        for key,vv in compact_mv.items():
            if float(vv.X)>0.5:selected_move.add(key)
        m=cm


    # B6-C5R1 gap-targeted fixed-dual mobility certificate prepass.
    #
    # After exact root pricing closure, the root continuous master dual is valid
    # for every child obtained only by *removing mobility path columns*.  For a
    # child path set P'_m, the convexity dual of block m can be shifted by the
    # exact minimum reduced cost over P'_m.  Therefore
    #
    #   L_child = D_root + sum_m minRC_m(P'_m) - numerical_guard
    #
    # is a globally valid lower bound for that child without solving another QCP.
    # This is particularly valuable for the frozen 3% contract: we only need to
    # prove L_child >= U-g|U|, not re-optimize every child to its exact LP optimum.
    fixed_dual_prepass={
        'enabled':bool((os.environ.get('MOBILEESS_R25N_B6C5R1_FIXED_DUAL_PREPASS','1')=='1') and not c5r4_disable_fixed_dual),
        'attempted':False,'certificate_pass':False,
        'disabled_by_C5R4':bool(c5r4_disable_fixed_dual),
        'disabled_reason':('C5R3 measured 120 s and 214 nodes with zero material global-bound lift; budget reassigned to exact child QCP repricing' if c5r4_disable_fixed_dual else None),
    }
    if fixed_dual_prepass['enabled'] and int(m.SolCount)>0 and not cert['reached']:
        fd_t0=time.monotonic()
        fd_node_limit=int(os.environ.get('MOBILEESS_R25N_B6C5R1_FIXED_DUAL_NODE_LIMIT','256'))
        fd_time_limit=float(os.environ.get('MOBILEESS_R25N_B6C5R1_FIXED_DUAL_TIMELIMIT','30'))
        fd_kbest=int(os.environ.get('MOBILEESS_R25N_B6C5R1_FIXED_DUAL_KBEST','16'))
        if fd_node_limit<1 or fd_time_limit<=0 or fd_kbest<2:
            raise RuntimeError('invalid B6-C5R1 fixed-dual prepass configuration')
        fixed_dual_prepass['attempted']=True
        fd_target=gap_target_lower_bound(float(m.ObjVal),float(target_gap))
        def _fd_node_bound(req,forb):
            reds={};paths={}
            for mm in mids:
                ac,srcconst=priced[mm]
                val,pth,snk=shortest_path_with_node_restrictions(
                    graphs[mm],source[mm],H,ac,req.get(mm,set()),forb.get(mm,set()))
                if not math.isfinite(val):
                    return {'infeasible':True,'reason':'no_mobility_path','reds':reds}
                red=float(srcconst+float(val)-float(final_conv_pi[mm]))
                reds[mm]=red;paths[mm]=(tuple(pth),snk)
            # The same numerical envelope used for the exact root bound is
            # subtracted again; this weakens, never strengthens, the child bound.
            lb=float(final_rmp_obj+sum(reds.values())-float(lb_safety))
            return {'infeasible':False,'lb':lb,'reds':reds,'paths':paths}
        def _fd_choose_branch(req,forb):
            candidates=[]
            for mm in mids:
                ac,srcconst=priced[mm]
                kb=k_shortest_paths_with_node_restrictions(
                    graphs[mm],source[mm],H,ac,req.get(mm,set()),forb.get(mm,set()),fd_kbest)
                if len(kb)<2:continue
                if c5r3_fd_multiway:
                    part=choose_time_layer_multiway_partition(
                        kb,source[mm],byid,req.get(mm,set()),forb.get(mm,set()),H,c5r3_fd_multiway_max)
                    if part is not None:
                        candidates.append((float(part['balance']),float(part['entropy']),
                                           -int(part['h']),str(mm),part))
                        continue
                # Exact binary occupancy fallback used when no useful multiway
                # time-layer partition exists.
                counts=defaultdict(int)
                for _,pth,_ in kb:
                    for nn in _path_nodes(source[mm],tuple(pth),byid):
                        if nn==source[mm] or int(nn[0])>=H:continue
                        if nn in req.get(mm,set()) or nn in forb.get(mm,set()):continue
                        counts[tuple(nn)]+=1
                n=len(kb)
                bc=[]
                for nn,cnt in counts.items():
                    if cnt<=0 or cnt>=n:continue
                    balance=min(cnt,n-cnt)/float(n)
                    bc.append((balance,-int(nn[0]),tuple(nn),cnt/float(n)))
                if bc:
                    bc.sort(key=lambda z:(-z[0],-z[1],z[2]))
                    balance,_,nn,y=bc[0]
                    candidates.append((float(balance),0.0,-int(nn[0]),str(mm),
                                       {'kind':'mobility_node','node':tuple(nn),'y':float(y)}))
            if not candidates:return None
            candidates.sort(reverse=True,key=lambda z:(z[0],z[1],z[2],z[3],repr(z[4])))
            _,_,_,mm,part=candidates[0]
            if part['kind']=='mobility_time_multi':
                return ('mobility_time_multi',mm,int(part['h']),tuple(part['nodes']),part)
            return ('mobility_node',mm,tuple(part['node']),float(part['y']))
        empty_req_fd={mm:set() for mm in mids};empty_forb_fd={mm:set() for mm in mids}
        root_fd=_fd_node_bound(empty_req_fd,empty_forb_fd)
        fd_heap=[];fd_leaves=[];fd_unresolved=[];fd_records=[];fd_seq=0;fd_nodes=0
        if root_fd.get('infeasible'):
            # Impossible because a globally feasible restricted-master incumbent
            # already exists; fail closed rather than infer anything.
            fd_unresolved.append(float(full_lb))
            fd_records.append({'depth':0,'status':'UNRESOLVED','reason':'root_fixed_dual_no_path_inconsistent'})
        else:
            root_fd_lb=min(float(root_fd['lb']),float(full_lb)+max(0.0,float(root_fd['lb'])-float(full_lb)))
            # full_lb is already a valid root bound.  The fixed-dual expression
            # should agree within the numerical envelope; keep the weaker value.
            root_fd_lb=min(float(root_fd_lb),float(full_lb))
            heapq.heappush(fd_heap,(root_fd_lb,fd_seq,0,empty_req_fd,empty_forb_fd));fd_seq+=1
        while fd_heap and fd_nodes<fd_node_limit and (time.monotonic()-fd_t0)<fd_time_limit:
            nlb,_,depth,req,forb=heapq.heappop(fd_heap);fd_nodes+=1
            if float(nlb)>=float(fd_target)-1e-12:
                fd_leaves.append(float(nlb));continue
            br=_fd_choose_branch(req,forb)
            if br is None:
                fd_unresolved.append(float(nlb))
                fd_records.append({'depth':depth,'lb':float(nlb),'status':'UNRESOLVED','reason':'no_low_rc_mobility_partition'})
                continue
            kids=[]
            if br[0]=='mobility_time_multi':
                _,mm,h,nodes,meta=br
                for j,nn in enumerate(nodes):
                    rrq={m0:set(v) for m0,v in req.items()};ffb={m0:set(v) for m0,v in forb.items()}
                    rrq[mm].add(tuple(nn));kids.append((rrq,ffb,f'svc{j}'))
                # REST is exact: every parent path either visits one selected
                # service node at time h or visits none of them (including transit
                # and unobserved service states).
                rrq={m0:set(v) for m0,v in req.items()};ffb={m0:set(v) for m0,v in forb.items()}
                for nn in nodes:ffb[mm].add(tuple(nn))
                kids.append((rrq,ffb,'rest'))
                fd_records.append({'depth':depth,'lb':float(nlb),'branch_type':'mobility_time_multi',
                                   'mess':mm,'h':int(h),'nodes':[list(x) for x in nodes],
                                   'sample_balance':meta.get('balance'),'sample_entropy':meta.get('entropy'),
                                   'status':'BRANCH'})
            else:
                _,mm,nn,y=br
                r0={m0:set(v) for m0,v in req.items()};f0={m0:set(v) for m0,v in forb.items()};f0[mm].add(tuple(nn))
                r1={m0:set(v) for m0,v in req.items()};f1={m0:set(v) for m0,v in forb.items()};r1[mm].add(tuple(nn))
                kids=[(r0,f0,0),(r1,f1,1)]
                fd_records.append({'depth':depth,'lb':float(nlb),'branch_type':'mobility_node',
                                   'branch':[mm,list(nn),float(y)],'status':'BRANCH'})
            for kr,kf,side in kids:
                rr=_fd_node_bound(kr,kf)
                if rr.get('infeasible'):
                    fd_records.append({'depth':depth+1,'side':side,'status':'INFEASIBLE_MOBILITY_PATH_SET'})
                    continue
                klb=float(rr['lb'])
                if klb<float(full_lb)-1e-6:
                    # A child path restriction cannot produce a weaker true bound
                    # than the root. Numerical dual drift must never lower authority.
                    klb=float(full_lb)
                if klb>=float(fd_target)-1e-12:
                    fd_leaves.append(klb)
                else:
                    heapq.heappush(fd_heap,(klb,fd_seq,depth+1,kr,kf));fd_seq+=1
        # Unprocessed heap nodes remain validly represented by their fixed-dual LBs.
        fd_candidates=list(fd_leaves)+[float(x[0]) for x in fd_heap]+list(fd_unresolved)
        fd_global_lb=min(fd_candidates) if fd_candidates else float('inf')
        # An empty partition while a feasible incumbent exists is an internal
        # inconsistency, never a zero-gap certificate.  Non-finite bounds fail
        # closed in both reporting and acceptance.
        fd_gap=global_relative_gap(float(m.ObjVal),fd_global_lb) if math.isfinite(fd_global_lb) else float('inf')
        fd_pass=bool(math.isfinite(fd_global_lb) and fd_gap<=float(target_gap)+1e-12)
        fixed_dual_prepass.update({
            'certificate_pass':fd_pass,'nodes_processed':int(fd_nodes),
            'open_nodes':len(fd_heap),'closed_leaves':len(fd_leaves),'unresolved_nodes':len(fd_unresolved),
            'global_lower_bound':float(fd_global_lb),'global_gap':float(fd_gap),
            'target_lower_bound':float(fd_target),'elapsed_s':float(time.monotonic()-fd_t0),
            'node_limit':int(fd_node_limit),'time_limit_s':float(fd_time_limit),'kbest':int(fd_kbest),
            'multiway_time_layer_enabled':bool(c5r3_fd_multiway),'multiway_max_explicit':int(c5r3_fd_multiway_max),
            'records_tail':fd_records[-150:],
            'authority':'ROOT_TRUE_DUAL_PLUS_EXACT_RESTRICTED_DAG_MIN_RC_WITH_CONVEXITY_DUAL_SHIFT',
            'qcp_child_resolve_required_for_this_bound':False,
        })
        if math.isfinite(fd_global_lb):
            # The minimum over the complete current partition (closed leaves,
            # open nodes, unresolved nodes represented by their valid ancestor
            # bounds) is a valid global lower bound even before it reaches 3%.
            certificate_lb=max(float(certificate_lb),float(fd_global_lb))
            g=global_relative_gap(float(m.ObjVal),float(certificate_lb))
            cert.update({'gap':g,'incumbent':float(m.ObjVal),'reached':bool(g<=float(target_gap)+1e-12)})

    # R25M/B6R4 certified fallback: the root all-column relaxation can be too weak to
    # certify 3% even when the compact restricted integer master has already
    # moved its own bound much higher.  Tighten the *global* lower bound with an
    # external, exact branch-and-price tree.  Branching is on original binary
    # node-occupancy decisions (path-compatible) and original non-mobility
    # integers.  Every tree node re-prices to all-column closure, so no
    # restricted-master ObjBound is ever promoted to scientific authority.
    bp_summary={'enabled':bool(b6r3_branch_price and not r25t_global_portfolio),'attempted':False,
                'certificate_pass':False,
                'disabled_reason':('R25T uses original compact MIQCP native global B&B authority' if r25t_global_portfolio else None)}
    if b6r3_branch_price and not r25t_global_portfolio and not cert['reached'] and int(m.SolCount)>0:
        bp_summary['attempted']=True
        bp_t0=time.monotonic()
        incumbent=float(m.ObjVal)
        # Exact linear column coefficients keyed by constraint name for model copies.
        contrib_name={n:[(c.ConstrName,float(a)) for c,a in contrib.get(n,())] for n in mob_names}
        def path_coeffs_named(mid,path):
            d=defaultdict(float)
            for n in path_varnames(mid,path):
                for cn,a in contrib_name.get(n,()):d[cn]+=a
            return {cn:a for cn,a in d.items() if abs(a)>1e-14}
        root_path_names={mid:{path:v.VarName for path,v in lvars[mid].items()} for mid in mids}
        # B6-C2 global path cache.  Every trajectory discovered at any branch node
        # is a valid path of the original DAG, so its sparse projected master column
        # can be computed once and inherited by every later node whose occupancy
        # restrictions allow it.  This changes only the starting restricted master,
        # never the exact pricing closure oracle.
        global_path_cache={mid:{} for mid in mids}
        global_cache_stats={'initial_root_paths':0,'new_paths_registered':0,'node_inherited_columns':0,'child_batch_columns':0}
        def _global_meta(mid,path,origin='runtime'):
            path=tuple(path)
            meta=global_path_cache[mid].get(path)
            if meta is None:
                meta={'nodes':frozenset(_path_nodes(source[mid],path,byid)),
                      'coeffs':path_coeffs_named(mid,path),
                      'objective':float(path_obj(mid,path)),
                      'origins':{str(origin)}}
                global_path_cache[mid][path]=meta
                global_cache_stats['new_paths_registered']+=1
            else:
                meta['origins'].add(str(origin))
            return meta
        for mid in mids:
            for path in root_path_names[mid]:
                _global_meta(mid,path,'root')
                global_cache_stats['initial_root_paths']+=1
        # Do not count the frozen root pool as newly discovered C2 paths.
        global_cache_stats['new_paths_registered']=0
        nonmob_meta=[(v.VarName,typ,float(v.LB),float(v.UB)) for v,typ in original_nonmob_types]

        # B6-C1: branch-price children MUST originate from the pristine
        # continuous authority captured before the primal MIP restored integrality.
        # Do not call Model.relax() on the post-MIP model: the B6R4 user-runtime
        # failure showed that this lifecycle could reach an OPTIMAL child while Pi
        # was unavailable.  The authoritative continuous master and primal MIP are
        # now separate model objects.
        if bp_continuous_authority is None:
            raise RuntimeError('B6-C1 missing pristine continuous authority')
        bp_base=bp_continuous_authority
        for mid in mids:
            for path,vname in root_path_names[mid].items():
                vv=bp_base.getVarByName(vname)
                if vv is not None:vv.UB=GRB.INFINITY
        bp_base.update()
        if int(bp_base.NumIntVars)!=0 or int(bp_base.NumBinVars)!=0 or int(bp_base.IsMIP)!=0:
            raise RuntimeError(f'B6-C1 continuous authority retained discrete state int={bp_base.NumIntVars} bin={bp_base.NumBinVars} isMIP={bp_base.IsMIP}')
        bp_base.Params.QCPDual=1;bp_base.Params.Method=2
        bp_base.Params.NumericFocus=max(2,_old_numeric_focus);bp_base.Params.ScaleFlag=2;bp_base.Params.BarQCPConvTol=qcp_barrier_tol

        def _eligible(mid,path,req,forb):
            ns=_global_meta(mid,path,'eligibility')['nodes']
            return set(req.get(mid,set())).issubset(ns) and not bool(ns & set(forb.get(mid,set())))

        def _solve_bp_node(req,forb,fixes,node_id):
            nm=bp_base.copy();nm.Params.OutputFlag=0;nm.Params.QCPDual=1;nm.Params.Method=2
            nm.Params.NumericFocus=max(2,_old_numeric_focus);nm.Params.ScaleFlag=2;nm.Params.BarQCPConvTol=qcp_barrier_tol
            local={mid:dict(root_path_names[mid]) for mid in mids}
            # Apply original non-mobility integer branch bounds.
            for name,(lo,hi) in fixes.items():
                vv=nm.getVarByName(name)
                if vv is None:raise RuntimeError('B6R3 missing branch variable '+name)
                vv.LB=max(float(vv.LB),float(lo));vv.UB=min(float(vv.UB),float(hi))
                if vv.LB>vv.UB+1e-12:return {'infeasible':True,'reason':'integer_bound_conflict'}
            # Existing path columns violating mobility node branches are disabled.
            for mid in mids:
                for path,vname in list(local[mid].items()):
                    vv=nm.getVarByName(vname)
                    if vv is None:continue
                    if not _eligible(mid,path,req,forb):vv.UB=0.0
            nm.update()
            # Constraint map used for exact column projection in this copy.
            cmap={c.ConstrName:c for c in nm.getConstrs()}
            convc={mid:nm.getConstrByName(f'b6_path_convexity_{mid}') for mid in mids}
            if any(c is None for c in convc.values()):raise RuntimeError('B6R3 missing convexity constraint')
            add_counter=0
            def add_local(mid,path,sink,label):
                nonlocal add_counter
                path=tuple(path)
                if path in local[mid]:
                    vv=nm.getVarByName(local[mid][path])
                    if vv is not None and vv.UB>0:return False
                if not path_satisfies_node_restrictions(source[mid],path,byid,req.get(mid,set()),forb.get(mid,set())):return False
                meta=_global_meta(mid,path,label);cc=meta['coeffs'];cs=[];vals=[]
                for cn,a in cc.items():
                    c=cmap.get(cn)
                    if c is None:raise RuntimeError('B6R3 projected row missing '+cn)
                    cs.append(c);vals.append(float(a))
                cs.append(convc[mid]);vals.append(1.0)
                vname=f'b6bp_{node_id}_{mid}_{add_counter:04d}';add_counter+=1
                vv=nm.addVar(lb=0.0,ub=GRB.INFINITY,vtype=GRB.CONTINUOUS,obj=float(meta['objective']),column=gp.Column(vals,cs),name=vname)
                local[mid][path]=vname
                return True
            # B6-C2 parent/sibling inheritance: import every globally discovered
            # path compatible with this child before solving its first RMP.  Root
            # paths already exist in the copied model; only non-root cache entries
            # need a new local column.
            inherited_here=0
            for mid in mids:
                for path in list(global_path_cache[mid].keys()):
                    if path in local[mid] or not _eligible(mid,path,req,forb):continue
                    if add_local(mid,path,None,'global_inherit'):
                        inherited_here+=1
            global_cache_stats['node_inherited_columns']+=inherited_here
            # Guarantee an eligible seed column for every MESS before the first RMP.
            zc={mid:{a.arc_id:0.0 for a in graphs[mid]} for mid in mids}
            for mid in mids:
                active=False
                for path,vname in local[mid].items():
                    vv=nm.getVarByName(vname)
                    if vv is not None and vv.UB>0 and _eligible(mid,path,req,forb):active=True;break
                if not active:
                    val,pth,snk=shortest_path_with_node_restrictions(graphs[mid],source[mid],H,zc[mid],req.get(mid,set()),forb.get(mid,set()))
                    if not math.isfinite(val):return {'infeasible':True,'reason':'no_mobility_path'}
                    add_local(mid,pth,snk,'seed')
            nm.update()
            tnode=time.monotonic();records=[];maxit=(None if unlimited_completion else 100)
            child_dual_center_pi=None;child_dual_center_conv=None
            child_stab_stats={'candidate_paths_examined':0,'candidate_paths_added':0,'iterations_with_stabilized_candidates':0}
            for itn in (itertools.count() if maxit is None else range(maxit)):
                rem=min(bp_node_cg_limit,bp_time_limit-(time.monotonic()-bp_t0))-(time.monotonic()-tnode)
                if rem<=0:return {'incomplete':True,'reason':'node_cg_time','records':records}
                if int(nm.NumIntVars)!=0 or int(nm.NumBinVars)!=0:
                    return {'incomplete':True,'reason':f'node_relaxation_not_continuous_int{nm.NumIntVars}_bin{nm.NumBinVars}','records':records}
                _set_solve_time_limit(nm,rem);_child_s0=time.monotonic();nm.optimize();child_solve_seconds=time.monotonic()-_child_s0
                st=int(nm.Status)
                # A restricted-column RMP can be infeasible even when omitted
                # columns would restore feasibility.  Without a Phase-I/Farkas
                # pricing proof it is NOT a valid full-node infeasibility proof.
                if st==GRB.INFEASIBLE:
                    return {'incomplete':True,'reason':'restricted_rmp_infeasible_requires_phase1_pricing','records':records}
                if st!=GRB.OPTIMAL:return {'incomplete':True,'reason':f'rmp_status_{st}','records':records}
                robj=float(nm.ObjVal)
                # C5R2 applies the same QCP-dual recovery contract at child nodes.
                # A child lower bound is never used until Pi, QCPi, RC and convexity
                # Pi are all retrievable under an explicit BarQCPConvTol.
                dual_retry_count_child=0;dual_retry_history_child=[];child_bounded_envelope_used=False
                best_bounded_child_candidate=None;best_bounded_child_branch=None;best_bounded_child_params=None
                child_branch_from_saved_optimal=False
                while True:
                    def _child_attr(attr):
                        try:return float(getattr(nm,attr))
                        except Exception:return None
                    dual_audit={'num_int_vars':int(nm.NumIntVars),'num_bin_vars':int(nm.NumBinVars),'is_mip':int(nm.IsMIP),
                                'linear_dual_available':False,'quadratic_dual_available':False,'reduced_cost_available':False,
                                'BarQCPConvTol':float(nm.Params.BarQCPConvTol),'ScaleFlag':int(nm.Params.ScaleFlag),
                                'NumericFocus':int(nm.Params.NumericFocus),'qcp_dual_retry_count':int(dual_retry_count_child),
                                'coefficient_ranges':{a:_child_attr(a) for a in ('MinCoeff','MaxCoeff','MinQCCoeff','MaxQCCoeff','MinRHS','MaxRHS','MinBound','MaxBound','MinObjCoeff','MaxObjCoeff')}}
                    try:
                        lrows=nm.getConstrs();pi={c.ConstrName:float(c.Pi) for c in lrows}
                        dual_audit['linear_dual_available']=True;dual_audit['linear_dual_count']=len(pi)
                        qrows=nm.getQConstrs();qpi=[float(q.QCPi) for q in qrows]
                        if any(not math.isfinite(z) for z in qpi):raise RuntimeError('nonfinite QCPi')
                        dual_audit['quadratic_dual_available']=True;dual_audit['quadratic_dual_count']=len(qpi)
                        rc_checked=0;rc_max_abs=0.0
                        for mid0 in mids:
                            for path0,vname0 in local[mid0].items():
                                vv0=nm.getVarByName(vname0)
                                if vv0 is None or vv0.UB<=0:continue
                                rv=float(vv0.RC);rc_checked+=1;rc_max_abs=max(rc_max_abs,abs(rv))
                                if rc_checked>=16:break
                            if rc_checked>=16:break
                        if rc_checked<=0:raise RuntimeError('no active path variable for RC audit')
                        dual_audit['reduced_cost_available']=True;dual_audit['reduced_cost_sample_count']=rc_checked;dual_audit['reduced_cost_sample_max_abs']=rc_max_abs
                        current_convc_pi={mid0:float(convc[mid0].Pi) for mid0 in mids}
                        comp_check={}
                        for n0 in mob_names:
                            comp_check[n0]=float(objcoef.get(n0,0.0))-sum(float(pi.get(cn,0.0))*float(a) for cn,a in contrib_name.get(n0,()))
                        rc_accounting_max_err=0.0;rc_accounting_checked=0
                        for mid0 in mids:
                            pc0=float(current_convc_pi[mid0])
                            for path0,vname0 in local[mid0].items():
                                vv0=nm.getVarByName(vname0)
                                if vv0 is None or vv0.UB<=0:continue
                                manual0=sum(comp_check.get(n0,0.0) for n0 in path_varnames(mid0,path0))-pc0
                                rc_accounting_max_err=max(rc_accounting_max_err,abs(manual0-float(vv0.RC)));rc_accounting_checked+=1
                        dual_audit['rc_accounting_checked']=rc_accounting_checked
                        dual_audit['rc_accounting_max_error']=rc_accounting_max_err
                        dual_audit['rc_accounting_tolerance']=rc_audit_tol
                        if not rc_audit_pass(rc_accounting_max_err,rc_audit_tol):
                            raise RuntimeError(f'reduced_cost_accounting_mismatch max_err={rc_accounting_max_err} tol={rc_audit_tol}')
                        break
                    except Exception as exc:
                        if (bounded_rc_envelope and 'reduced_cost_accounting_mismatch' in str(exc) and
                            math.isfinite(float(dual_audit.get('rc_accounting_max_error',float('inf')))) and
                            float(dual_audit['rc_accounting_max_error'])<=rc_envelope_hard_cap):
                            candidate_err=float(dual_audit['rc_accounting_max_error'])
                            candidate=(float(robj),dict(pi),dict(current_convc_pi),dict(comp_check),dict(dual_audit))
                            if best_bounded_child_candidate is None or candidate_err<float(best_bounded_child_candidate[4]['rc_accounting_max_error']):
                                best_bounded_child_candidate=candidate
                                best_bounded_child_params={'BarQCPConvTol':float(nm.Params.BarQCPConvTol),
                                    'ScaleFlag':int(nm.Params.ScaleFlag),'NumericFocus':int(nm.Params.NumericFocus),
                                    'BarHomogeneous':int(nm.Params.BarHomogeneous),'Quad':int(nm.Params.Quad)}
                                best_bounded_child_branch=_select_branch(nm,local,float(robj),f'child_{node_id}_retry_{dual_retry_count_child}_optimal_candidate')
                        if best_bounded_child_candidate is not None and dual_retry_count_child>=bounded_rc_strict_retry_budget:
                            robj,pi,current_convc_pi,comp_check,dual_audit=best_bounded_child_candidate
                            child_bounded_envelope_used=True;child_branch_from_saved_optimal=True
                            for pname,pvalue in best_bounded_child_params.items():setattr(nm.Params,pname,pvalue)
                            dual_retry_history_child.append({'bounded_envelope_accept':True,
                                'trigger':'strict_retry_budget_reached','strict_retry_budget':int(bounded_rc_strict_retry_budget),
                                'source_solve_status':'OPTIMAL','measured_max_error':float(dual_audit['rc_accounting_max_error']),
                                'hard_cap':float(rc_envelope_hard_cap),'lower_bound_safety_will_use_measured_error':True})
                            break
                        if dual_retry_count_child+1>=len(qcp_dual_retry_tols):
                            if best_bounded_child_candidate is not None:
                                robj,pi,current_convc_pi,comp_check,dual_audit=best_bounded_child_candidate
                                child_bounded_envelope_used=True
                                child_branch_from_saved_optimal=True
                                for pname,pvalue in best_bounded_child_params.items():setattr(nm.Params,pname,pvalue)
                                dual_retry_history_child.append({'bounded_envelope_accept':True,
                                    'trigger':'strict_retry_schedule_exhausted','source_solve_status':'OPTIMAL',
                                    'measured_max_error':float(dual_audit['rc_accounting_max_error']),
                                    'hard_cap':float(rc_envelope_hard_cap),
                                    'lower_bound_safety_will_use_measured_error':True})
                                break
                            dual_audit['last_error']=type(exc).__name__+':'+str(exc);dual_audit['retry_history']=dual_retry_history_child
                            return {'incomplete':True,'reason':'qcp_dual_unavailable_after_retries','records':records,'dual_audit':dual_audit}
                        dual_retry_count_child+=1;newtol=float(qcp_dual_retry_tols[dual_retry_count_child])
                        dual_retry_history_child.append({'retry':dual_retry_count_child,'reason':type(exc).__name__+':'+str(exc),'BarQCPConvTol':newtol})
                        nm.Params.BarQCPConvTol=newtol
                        if 'reduced_cost_accounting_mismatch' in str(exc):
                            nm.Params.ScaleFlag=2;nm.Params.NumericFocus=max(2,int(nm.Params.NumericFocus))
                            if dual_retry_count_child>=3:nm.Params.BarHomogeneous=1;nm.Params.NumericFocus=3
                            if dual_retry_count_child>=5:nm.Params.Quad=1
                        remr=min(bp_node_cg_limit,bp_time_limit-(time.monotonic()-bp_t0))-(time.monotonic()-tnode)
                        if remr<=0:return {'incomplete':True,'reason':'node_cg_time_during_dual_recovery','records':records,'dual_audit':dual_audit}
                        _set_solve_time_limit(nm,remr);nm.reset();_rt=time.monotonic();nm.optimize();child_solve_seconds+=time.monotonic()-_rt
                        if int(nm.Status)!=GRB.OPTIMAL:
                            if best_bounded_child_candidate is not None:
                                failed_retry_status=int(nm.Status)
                                robj,pi,current_convc_pi,comp_check,dual_audit=best_bounded_child_candidate
                                child_bounded_envelope_used=True
                                child_branch_from_saved_optimal=True
                                for pname,pvalue in best_bounded_child_params.items():setattr(nm.Params,pname,pvalue)
                                dual_retry_history_child.append({'bounded_envelope_accept':True,
                                    'trigger':'stricter_retry_nonoptimal','failed_stricter_retry_status':failed_retry_status,
                                    'source_solve_status':'OPTIMAL','measured_max_error':float(dual_audit['rc_accounting_max_error']),
                                    'hard_cap':float(rc_envelope_hard_cap),'lower_bound_safety_will_use_measured_error':True})
                                break
                            return {'incomplete':True,'reason':f'dual_recovery_rmp_status_{int(nm.Status)}','records':records,'dual_audit':dual_audit}
                        robj=float(nm.ObjVal)
                child_effective_rc_guard=max(float(rc_audit_tol),float(dual_audit.get('rc_accounting_max_error',0.0)))
                dual_audit['retry_history']=dual_retry_history_child;dual_audit['rmp_solve_seconds']=float(child_solve_seconds)
                dual_audit['bounded_rc_envelope_used']=bool(child_bounded_envelope_used);dual_audit['effective_rc_guard']=float(child_effective_rc_guard)
                stab_pi_child=blend_dual_maps(pi,child_dual_center_pi,dual_stab_alpha) if dual_stab_enabled else dict(pi)
                stab_conv_child=blend_dual_maps(current_convc_pi,child_dual_center_conv,dual_stab_alpha) if dual_stab_enabled else dict(current_convc_pi)
                compn={}
                for n in mob_names:
                    compn[n]=float(objcoef.get(n,0.0))-sum(float(pi.get(cn,0.0))*float(a) for cn,a in contrib_name.get(n,()))
                stab_compn={}
                if dual_stab_enabled:
                    for n in mob_names:
                        stab_compn[n]=float(objcoef.get(n,0.0))-sum(float(stab_pi_child.get(cn,0.0))*float(a) for cn,a in contrib_name.get(n,()))
                newn=0;mins={};batch_by_mid={};stab_added_by_mid={};stab_examined_by_mid={}
                for mid in mids:
                    srcn=node_varname.get((mid,source[mid][0],source[mid][1]));srcconst=compn.get(srcn,0.0)
                    ac={a.arc_id:compn.get(arc_varname[a.arc_id],0.0)+compn.get(node_varname.get((mid,a.head[0],a.head[1])),0.0) for a in graphs[mid]}
                    pc=current_convc_pi[mid]
                    # Exact TRUE-dual minimum path remains the scientific closure oracle.
                    val,pth,snk=shortest_path_with_node_restrictions(graphs[mid],source[mid],H,ac,req.get(mid,set()),forb.get(mid,set()))
                    if not math.isfinite(val):return {'infeasible':True,'reason':'pricing_no_path','records':records}
                    red=float(srcconst+val-pc);mins[mid]=red
                    added_mid=0
                    if red < -pricing_tol and pth not in local[mid]:
                        if add_local(mid,pth,snk,'pricing_exact_min'):
                            newn+=1;added_mid+=1
                    # B6-C2 true-dual batch.
                    kb=k_shortest_paths_with_node_restrictions(graphs[mid],source[mid],H,ac,req.get(mid,set()),forb.get(mid,set()),child_pricing_batch)
                    for v2,p2,s2 in kb:
                        r2=float(srcconst+float(v2)-pc)
                        if r2 < -pricing_tol and p2 not in local[mid]:
                            if add_local(mid,p2,s2,'pricing_batch_true_dual'):
                                newn+=1;added_mid+=1;global_cache_stats['child_batch_columns']+=1
                    # B6-C3 stabilized candidate batch, always filtered by true RC.
                    sadd=0;sexam=0
                    if dual_stab_enabled:
                        sac={a.arc_id:float(stab_compn.get(arc_varname[a.arc_id],0.0))+float(stab_compn.get(node_varname.get((mid,a.head[0],a.head[1])),0.0)) for a in graphs[mid]}
                        skb=k_shortest_paths_with_node_restrictions(graphs[mid],source[mid],H,sac,req.get(mid,set()),forb.get(mid,set()),dual_stab_batch)
                        for _,p2,s2 in skb:
                            sexam+=1;child_stab_stats['candidate_paths_examined']+=1
                            if p2 in local[mid]:continue
                            true_rc=true_reduced_cost_for_path(mid,p2,compn,pc,path_varnames)
                            if true_rc < -pricing_tol:
                                if add_local(mid,p2,s2,'pricing_stabilized_true_rc_filtered'):
                                    newn+=1;added_mid+=1;sadd+=1;child_stab_stats['candidate_paths_added']+=1
                        if sadd>0:child_stab_stats['iterations_with_stabilized_candidates']+=1
                    batch_by_mid[mid]=added_mid;stab_added_by_mid[mid]=sadd;stab_examined_by_mid[mid]=sexam
                records.append({'iteration':itn,'objective':robj,'min_reduced_cost':mins,'new_columns':newn,'new_columns_by_mid':batch_by_mid,'child_pricing_batch':int(child_pricing_batch),'inherited_columns_at_node_start':int(inherited_here),'global_cache_size':{mid:len(global_path_cache[mid]) for mid in mids},'dual_audit':dual_audit,
                                'dual_stabilization':{'enabled':bool(dual_stab_enabled),'alpha':float(dual_stab_alpha),'center_beta':float(dual_center_beta),
                                                     'stabilized_candidates_examined_by_mid':stab_examined_by_mid,'stabilized_candidates_added_by_mid':stab_added_by_mid}})
                if dual_stab_enabled:
                    child_dual_center_pi=update_dual_center(child_dual_center_pi,pi,dual_center_beta)
                    child_dual_center_conv=update_dual_center(child_dual_center_conv,current_convc_pi,dual_center_beta)
                if newn==0:
                    if all(v>=-child_effective_rc_guard for v in mins.values()):
                        lb,safe=guarded_full_lb(robj,len(mids),child_effective_rc_guard)
                        # Fractional branching state from the priced-closed RMP.
                        # B6-C4 reliability strong branching.  Probe the small
                        # deterministic shortlist on the current priced-closed RMP;
                        # final child bounds are still accepted only after exact
                        # all-column pricing closure.
                        branch=(best_bounded_child_branch if child_branch_from_saved_optimal else
                                _select_branch(nm,local,robj,f'child_{node_id}'))
                        return {'infeasible':False,'incomplete':False,'lb':float(lb),'raw_lb':robj,'guard':safe,'branch':branch,'records':records}
                    return {'incomplete':True,'reason':'negative_rc_existing_or_numeric','records':records}
                nm.update()
            return {'incomplete':True,'reason':'node_cg_iteration_limit','records':records}

        # Best-bound-first exact branch-and-price tree.  The incumbent is fixed to
        # the feasible restricted-master solution retained in m; B&P is used only
        # to lift the scientific lower bound, never to invent a heuristic bound.
        empty_req={mid:set() for mid in mids};empty_forb={mid:set() for mid in mids}
        # B6R4 root reuse: root exact pricing was already closed before the integer
        # primal phase, so full_lb is the certified all-column root lower bound.
        # Reusing it avoids a redundant root RMP/pricing cycle and removes the exact
        # lifecycle location that triggered the B6R3 Pi failure.
        heap=[];leaves=[];unresolved=[];seq=1;bp_nodes_solved=0;bp_records=[]
        # Start from the strongest already certified scalar global bound.  C5R1
        # may have lifted it with the fixed-dual mobility partition prepass.
        rootlb=float(certificate_lb);rootbr=root_branch_candidate
        bp_records.append({'node':0,'depth':0,'lb':rootlb,'branch':rootbr,'status':'REUSED_EXACT_ROOT_PRICING'})
        if branch_price_gap_prunable(incumbent,rootlb,target_gap):leaves.append(rootlb)
        else:heapq.heappush(heap,(rootlb,0,0,empty_req,empty_forb,{},rootbr))
        # C5R1: one slow/incomplete child must not abort the entire exact tree.
        # Preserve that child's *ancestor valid lower bound* as unresolved, explore
        # siblings/other nodes, and retain all newly generated columns globally.
        # The unresolved ancestor bound participates conservatively in the final
        # global bound; therefore no false certificate can be created.
        def _node_budget_available():
            return bp_node_limit is None or bp_nodes_solved<bp_node_limit
        while heap and _node_budget_available() and (time.monotonic()-bp_t0)<bp_time_limit:
            plb,_,depth,req,forb,fixes,branch=heapq.heappop(heap)
            if branch_price_gap_prunable(incumbent,plb,target_gap):leaves.append(plb);continue
            if branch is None:
                unresolved.append({'lb':float(plb),'depth':int(depth),'req':req,'forb':forb,'fixes':fixes,'reason':'integral_or_unbranchable_relaxation'})
                bp_records.append({'depth':depth,'lb':plb,'status':'UNRESOLVED','reason':'integral_or_unbranchable_relaxation'})
                continue
            children=[]
            if branch[0]=='mobility_node':
                _,midb,nnb,y=branch
                r0={mm:set(v) for mm,v in req.items()};f0={mm:set(v) for mm,v in forb.items()};f0[midb].add(tuple(nnb))
                r1={mm:set(v) for mm,v in req.items()};f1={mm:set(v) for mm,v in forb.items()};r1[midb].add(tuple(nnb))
                children=[(r0,f0,dict(fixes),'mob0'),(r1,f1,dict(fixes),'mob1')]
            else:
                _,name,x,typ,lo,hi=branch
                fl=math.floor(x);ce=math.ceil(x)
                fx0=dict(fixes);fx1=dict(fixes)
                fx0[name]=(lo,min(hi,float(fl)));fx1[name]=(max(lo,float(ce)),hi)
                children=[({mm:set(v) for mm,v in req.items()},{mm:set(v) for mm,v in forb.items()},fx0,'int0'),({mm:set(v) for mm,v in req.items()},{mm:set(v) for mm,v in forb.items()},fx1,'int1')]
            for cr,cf,cx,label in children:
                if (not _node_budget_available()) or (time.monotonic()-bp_t0)>=bp_time_limit:
                    # This child has not been solved; its parent lower bound is a
                    # valid conservative lower bound for the entire child subtree.
                    unresolved.append({'lb':float(plb),'depth':int(depth+1),'req':cr,'forb':cf,'fixes':cx,'reason':'bp_budget_before_child'})
                    bp_records.append({'depth':depth+1,'status':'UNRESOLVED','reason':'bp_budget_before_child','ancestor_lb':plb,'side':label})
                    continue
                nid=seq;seq+=1;rr=_solve_bp_node(cr,cf,cx,nid);bp_nodes_solved+=1
                if rr.get('incomplete'):
                    unresolved.append({'lb':float(plb),'depth':int(depth+1),'req':cr,'forb':cf,'fixes':cx,'reason':rr.get('reason')})
                    bp_records.append({'node':nid,'depth':depth+1,'status':'UNRESOLVED','reason':rr.get('reason'),'ancestor_lb':plb,'side':label})
                    continue
                if rr.get('infeasible'):
                    # Only exact structural infeasibility reasons reach this branch.
                    bp_records.append({'node':nid,'depth':depth+1,'status':'INFEASIBLE','reason':rr.get('reason'),'side':label});continue
                # A child inherits every valid lower bound of its parent.  In
                # particular, C5R1 may enter B&P with a stronger global scalar bound
                # obtained from the complete fixed-dual mobility partition.  Never
                # let a separately guarded child-QCP solve numerically *decrease*
                # that already-certified bound.  max(parent_lb, child_exact_lb) is
                # still a valid lower bound for the child and improves certificate
                # monotonicity without changing the feasible set.
                lb=max(float(plb),float(rr['lb']));br=rr.get('branch')
                _record_exact_child_pseudocost(branch,0 if label in ('mob0','int0') else 1,plb,lb)
                bp_records.append({'node':nid,'depth':depth+1,'lb':lb,'branch':br,'side':label})
                if branch_price_gap_prunable(incumbent,lb,target_gap):leaves.append(lb)
                else:heapq.heappush(heap,(lb,seq,depth+1,cr,cf,cx,br));seq+=1
            try:
                import json
                unresolved_lbs=[float(z['lb']) for z in unresolved]
                best_candidates=[float(x[0]) for x in heap]+unresolved_lbs
                (out/'ConversationA_R25M_B6R3_BP_LIVE.json').write_text(json.dumps({'nodes_solved':bp_nodes_solved,'open_nodes':len(heap),'unresolved_nodes':len(unresolved),'leaves':len(leaves),'incumbent':incumbent,'best_open_lb':(min(best_candidates) if best_candidates else None),'elapsed_s':time.monotonic()-bp_t0},indent=2)+'\n',encoding='utf-8')
            except Exception:pass
        hit_node_limit=bool(heap and bp_node_limit is not None and bp_nodes_solved>=bp_node_limit)
        hit_time_limit=bool(heap and (time.monotonic()-bp_t0)>=bp_time_limit)
        # Every unresolved subtree is represented by a valid priced-closed ancestor
        # lower bound.  This makes the reported global lower bound conservative
        # even when a child RMP times out or needs future Phase-I pricing.
        candidates=list(leaves)+[float(x[0]) for x in heap]+[float(z['lb']) for z in unresolved]
        bp_global_lb=min(candidates) if candidates else (min(leaves) if leaves else float('inf'))
        bp_gap=global_relative_gap(incumbent,bp_global_lb) if math.isfinite(bp_global_lb) else float('inf')
        bp_pass=bool(math.isfinite(bp_global_lb) and bp_gap<=float(target_gap)+1e-12)
        bp_incomplete=bool(unresolved or heap or hit_node_limit or hit_time_limit)
        bp_summary.update({'certificate_pass':bp_pass,'nodes_solved':bp_nodes_solved,'open_nodes':len(heap),'unresolved_nodes':len(unresolved),'unresolved_reasons':[str(z.get('reason')) for z in unresolved],
                           'closed_leaf_count':len(leaves),'global_lower_bound':float(bp_global_lb),'global_gap':float(bp_gap),'elapsed_s':time.monotonic()-bp_t0,
                           'incomplete':bool(bp_incomplete),'hit_node_limit':hit_node_limit,'hit_time_limit':hit_time_limit,
                           'node_limit':bp_node_limit,'time_limit_s':_audit_limit(bp_time_limit),
                           'node_cg_time_limit_s':_audit_limit(bp_node_cg_limit),
                           'unlimited_completion':bool(unlimited_completion),'records':bp_records,
                           'b6c4_strong_branch_records':len(branch_selection_records),'b6c4_pseudocost_keys':len(branch_pseudocost),
                           'global_bound_semantics':'minimum of exact closed leaves, exact open-node LBs, and conservative ancestor LBs for unresolved children'})
        if math.isfinite(bp_global_lb):
            certificate_lb=max(float(certificate_lb),float(bp_global_lb))
            g=global_relative_gap(incumbent,float(certificate_lb))
            cert.update({'gap':g,'incumbent':incumbent,'reached':bool(g<=float(target_gap)+1e-12)})

    result={'revision':('R25T_B6C6_GLOBAL_BOUND_PORTFOLIO' if r25t_global_portfolio else 'R25R_B6C5R4R4_RETAINED_OPTIMAL_DUAL_RESUME'),
            'status':'PASS_GLOBAL_3PCT_CERTIFICATE' if cert['reached'] else 'NO_GLOBAL_3PCT_CERTIFICATE',
            'pricing_closed':pricing_closed,'full_all_column_relaxation_lower_bound':full_lb,'certificate_lower_bound':float(certificate_lb),'raw_pricing_closed_rmp_objective':raw_full_lb,'numerical_lower_bound_safety':float(raw_full_lb-full_lb),'pricing_batch':int(pricing_batch),'rc_audit_tolerance':float(rc_audit_tol),'qcp_barrier_tolerance':float(qcp_barrier_tol),'BarConvTol_not_qcp_authority':float(m.Params.BarConvTol),
            'gap_certificate_diagnostics':(gap_certificate_diagnostics(float(cert['incumbent']),float(certificate_lb),float(target_gap)) if cert.get('incumbent') is not None and math.isfinite(float(cert['incumbent'])) else None),
            'fixed_dual_mobility_prepass':fixed_dual_prepass,
            'fixed_integer_continuous_qcp_polish':fixed_integer_polish,
            'restricted_primal_phase':primal_phase,
            'compact_exact_global_phase':compact_exact,
            'b6c2_child_pricing_batch':int(child_pricing_batch),'b6c2_global_path_cache_size':{mid:len(global_path_cache[mid]) for mid in mids} if 'global_path_cache' in locals() else {},'b6c2_global_cache_stats':dict(global_cache_stats) if 'global_cache_stats' in locals() else {},
            'b6c3_dual_stabilization':{'enabled':bool(dual_stab_enabled),'alpha':float(dual_stab_alpha),'center_beta':float(dual_center_beta),'candidate_batch':int(dual_stab_batch),
                                      'root_stats':dict(root_stab_stats),'authority':'TRUE_CURRENT_DUAL_EXACT_MINIMUM_PATH_ONLY','stabilized_dual_certificate_authority':False},
            'b6c4_branching':{'enabled':bool(strong_branch_enabled),'candidate_limit':int(strong_branch_candidates),'probe_time_limit_s':float(strong_probe_time),'early_weight':float(strong_early_weight),'pseudocost_reliability':int(pseudocost_reliability),'selection_records':list(branch_selection_records),'certificate_authority':False,'exact_child_pricing_still_required':True,'late_horizon_fractionality_only_rule_removed':True},
            'b6c5r3_policy':{'threads':int(m.Params.Threads),'mobility_integrality_first':bool(c5r3_mobility_first),
                              'fixed_dual_multiway_time_layer':bool(c5r3_fd_multiway),'fixed_dual_multiway_max_explicit':int(c5r3_fd_multiway_max),
                              'restricted_primal_heuristics':float(c5r3_primal_heur),
                              'basis':'C5R2 actual forensic: path_lambda diagnostic lift dominated mode/job; Threads=4 won 5pct RAM-aware screen',
                               'scientific_feasible_set_changed':False,'objective_changed':False,'branch_order_only':True},
            'b6c5r4_policy':{'threads':int(m.Params.Threads),'complete_MW_MWh_normalization':bool(os.environ.get('MOBILEESS_R25N_B6C5R4_COMPLETE_UNIT_NORMALIZATION','0')=='1'),
                              'fixed_integer_continuous_qcp_polish':bool(c5r4_polish_enabled),
                              'fixed_dual_prepass_removed':bool(c5r4_disable_fixed_dual),
                              'exact_child_QCP_reoptimization_retained':True,
                              'child_pricing_closure_retained':True,
                              'root_RC_mismatch_triggers_tighter_QCP_dual_retry':True,
                              'root_RC_retry_ScaleFlag':2,'root_RC_retry_NumericFocus':2,
                              'child_ScaleFlag':2,'child_NumericFocus':2,
                              'child_RC_accounting_audit':True,'scientific_feasible_set_changed':False,
                               'objective_changed':False,'gap_semantics_changed':False,
                               'unlimited_completion':bool(unlimited_completion),
                               'root_CG_time_limit_s':_audit_limit(cg_limit),
                               'restricted_integer_time_limit_s':_audit_limit(int_limit),
                               'polish_time_limit_s':_audit_limit(c5r4_polish_time),
                               'branch_price_time_limit_s':_audit_limit(bp_time_limit),
                               'branch_price_node_limit':bp_node_limit,
                               'branch_price_child_CG_time_limit_s':_audit_limit(bp_node_cg_limit),
                               'root_CG_iteration_limit':max_iter,
                               'bounded_RC_envelope_enabled':bool(bounded_rc_envelope),
                               'bounded_RC_envelope_hard_cap':float(rc_envelope_hard_cap),
                               'bounded_RC_strict_retry_budget':int(bounded_rc_strict_retry_budget),
                               'bounded_RC_envelope_rule':'measured error is subtracted per MESS from minimization lower bound; never added to feasibility or objective tolerances'},
            'r25t_global_portfolio_policy':{
                               'enabled':bool(r25t_global_portfolio),
                               'restricted_master_role':'BOUNDED_FEASIBLE_INCUMBENT_GENERATOR_ONLY',
                               'restricted_primal_min_seconds':float(r25t_primal_min_s),
                               'restricted_primal_stall_seconds':float(r25t_primal_stall_s),
                               'restricted_primal_max_seconds':float(r25t_primal_max_s),
                               'restricted_primal_max_nodes':int(r25t_primal_max_nodes),
                               'compact_model_role':'ORIGINAL_EXACT_MIQCP_INCUMBENT_AND_GLOBAL_BOUND_AUTHORITY',
                               'global_bound_rule':'max(EXACT_PRICED_ROOT_LB, ORIGINAL_COMPACT_MIQCP_OBJBOUND)',
                               'compact_mip_focus':int(r25t_compact_mip_focus),
                               'initial_hint_kbest':int(r25u_initial_hint_kbest),
                               'initial_objective_kbest':int(r25u_initial_objective_kbest),
                               'rmp_integer_hint_priority':int(r25u_rmp_hint_priority),
                               'overall_exact_completion_time_limit_s':None if unlimited_completion else _audit_limit(bp_time_limit),
                               'scientific_feasible_set_changed':False,'objective_changed':False,
                               'gap_semantics_changed':False,'AC_QCP_changed':False,
                               'restricted_master_objbound_global_authority':False},
            'global_certified_gap':(None if cert.get('gap') is None or not math.isfinite(float(cert['gap'])) else float(cert['gap'])),'target_gap':float(target_gap),
            'final_certified_incumbent':(None if cert.get('incumbent') is None or not math.isfinite(float(cert['incumbent'])) else float(cert['incumbent'])),
            'certificate_pass':bool(cert['reached']),'cg_iterations':len(cg_records),'cg_seconds':cg_seconds,'integer_seconds':int_seconds,
            'total_decomposition_seconds':time.monotonic()-t0,'columns_by_mess':{mid:len(pools[mid]) for mid in mids},
            'kbest_columns_added':added_kbest,'primal_enrichment':primal_enrichment,'projected_stats':projected_stats,'pricing_records':cg_records,
            'branch_price':bp_summary,'B6C1_pristine_continuous_authority':bp_continuous_authority_meta,
            'selected_paths':{mid:list(p) for mid,p in selected.items()},'selected_stay_keys':[list(x) for x in sorted(selected_stay)],
            'selected_move_keys':[list(x) for x in sorted(selected_move)],
            'restricted_master_status':restricted_master_snapshot['status'],'restricted_master_solution_count':restricted_master_snapshot['solution_count'],
            'restricted_master_incumbent_before_polish':restricted_master_snapshot['incumbent'],
            'restricted_master_incumbent':restricted_master_snapshot['incumbent'],
            'restricted_master_bound':restricted_master_snapshot['bound'],
            'restricted_master_native_gap':restricted_master_snapshot['native_gap'],
            'original_mobility_path_set_changed':False,'objective_changed':False,'future_actual_used':False,'future_D2_state_reinjected':False,
            'posthoc_same_issue_MIP_start_used':bool(r25t_global_portfolio and (compact_exact.get('mip_start') or {}).get('attempted')),
            'certificate_logic':('exact all-column priced-root lower bound; bounded restricted primal incumbent generation; original exact compact MIQCP native global bound; maximum of independent valid lower bounds; fixed-integer continuous-QCP polish' if r25t_global_portfolio else 'exact root pricing; fixed-integer continuous-QCP incumbent polish; conservative partial/exact branch-and-price bounds with exact child pricing closure; restricted integer master contributes only a globally feasible incumbent')}
    return result
