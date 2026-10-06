"""Full-LP equality projection. No integer-only deletion, no fill-in."""
import time
from fractions import Fraction as Q
from collections import Counter
import numpy as np
import scipy.sparse as sp
from .common import *

def union_aliases(a, sense, rhs, n):
    parent=np.arange(n,dtype=np.int64); proofs=[]
    def root(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]];x=int(parent[x])
        return x
    lens=np.diff(a.indptr)
    for r in np.flatnonzero((lens==2)&(sense=='=')&(rhs==0)):
        p=int(a.indptr[r]); x,y=map(int,a.indices[p:p+2]); c,d=a.data[p:p+2]
        # Both coefficients are exactly +/-1; equality proves x=y over LP.
        if abs(c)!=1 or d!=-c: continue
        u,v=root(x),root(y)
        if u!=v:
            parent[max(u,v)]=min(u,v); proofs.append((int(r),x,y))
    for i in range(n): parent[i]=root(i)
    return parent,np.asarray(proofs,dtype=np.int64).reshape(-1,3)

def interval_safe(a, lb, ub, sense, rhs, rational=False):
    """Screen only exact integer arithmetic with sums safely below 2**52.

    General floating-point/grid bounds require separate rational certificates
    and remain UNKNOWN here. No tolerance makes an unsafe row deletable.
    """
    c=a.data; j=a.indices
    low=np.where(c>=0,lb[j],ub[j]); high=np.where(c>=0,ub[j],lb[j])
    exactlow=(np.isfinite(low)&(abs(low)<1e10)&(low==np.floor(low))&(c==np.floor(c))&(abs(c)<1e10))
    exacthigh=(np.isfinite(high)&(abs(high)<1e10)&(high==np.floor(high))&(c==np.floor(c))&(abs(c)<1e10))
    lo=np.zeros(a.shape[0]);hi=np.zeros(a.shape[0]);ok=np.zeros(a.shape[0],dtype=bool)
    lens=np.diff(a.indptr); nz=np.flatnonzero(lens)
    with np.errstate(invalid='ignore',over='ignore'):
        lo[nz]=np.add.reduceat(c*low,a.indptr[nz])
        hi[nz]=np.add.reduceat(c*high,a.indptr[nz])
        ml=np.add.reduceat(abs(c*low),a.indptr[nz]);mh=np.add.reduceat(abs(c*high),a.indptr[nz])
    el=np.minimum.reduceat(exactlow,a.indptr[nz])&(ml<2**52)
    eh=np.minimum.reduceat(exacthigh,a.indptr[nz])&(mh<2**52)
    ok[nz]=((sense[nz]=='<')&eh|(sense[nz]=='>')&el|(sense[nz]=='=')&el&eh)
    ok[lens==0]=True
    safe=ok&np.isfinite(rhs)&((sense=='<')&(hi<=rhs)|(sense=='>')&(lo>=rhs)|(sense=='=')&(lo==rhs)&(hi==rhs))
    if rational:
        # Conservative screening only. Deletion below requires exact Fraction
        # comparison of original binary64 coefficient/bound/RHS values.
        candidates=np.zeros(a.shape[0],dtype=bool)
        candidates[nz]=((sense[nz]=='<')&np.isfinite(hi[nz])&(hi[nz]+(4*lens[nz]+8)*2**-52*mh<=rhs[nz]))|((sense[nz]=='>')&np.isfinite(lo[nz])&(lo[nz]-(4*lens[nz]+8)*2**-52*ml>=rhs[nz]))
        for r in np.flatnonzero(candidates&~safe):
            p,q=map(int,a.indptr[r:r+2]);s=sense[r];total=Q(0)
            for j,c0 in zip(a.indices[p:q],a.data[p:q]):
                b0=(ub[j] if c0>=0 else lb[j]) if s=='<' else (lb[j] if c0>=0 else ub[j])
                total+=Q(float(c0))*Q(float(b0))
            safe[r]=total<=Q(float(rhs[r])) if s=='<' else total>=Q(float(rhs[r]))
    return safe

def positive_resource_bounds(a,lb,ub,sense,rhs,groups):
    """For sum(x_i)<=b, x_i>=0, derive x_i<=b, without rounding."""
    co=a.tocoo();b=sp.coo_matrix((co.data,(co.row,groups[co.col])),shape=(a.shape[0],len(lb))).tocsr();b.eliminate_zeros()
    rows=[];values=[];cols=[];newub=ub.copy()
    for r in np.flatnonzero(((sense=='<')|(sense=='='))&(rhs>=0)&np.isfinite(rhs)):
        p,q=map(int,b.indptr[r:r+2]);ids=b.indices[p:q]
        if q==p or not np.all(b.data[p:q]==1) or not np.all(lb[ids]>=0):continue
        for j in ids:
            if rhs[r]<newub[j]:
                newub[j]=rhs[r];rows.append(int(r));cols.append(int(j));values.append(float(rhs[r]))
    return newub,np.array(rows,dtype=np.int64),np.array(cols,dtype=np.int64),np.array(values,dtype=float)

def duplicate_rows(a,sense,rhs,eligible):
    import hashlib
    seen={}; pairs=[]
    for r in np.flatnonzero(eligible):
        p,q=map(int,a.indptr[r:r+2])
        blob=a.indices[p:q].tobytes()+a.data[p:q].tobytes()+str(sense[r]).encode()+np.float64(rhs[r]).tobytes()
        h=hashlib.blake2b(blob,digest_size=20).digest()
        if h in seen:
            s=seen[h]; u,v=map(int,a.indptr[s:s+2])
            if sense[s]==sense[r] and rhs[s]==rhs[r] and np.array_equal(a.indices[p:q],a.indices[u:v]) and np.array_equal(a.data[p:q],a.data[u:v]):
                pairs.append((int(r),int(s)))
        else:seen[h]=int(r)
    return np.array(pairs,dtype=np.int64).reshape(-1,2)

def proportional_domination(a,sense,rhs,eligible):
    """Exact power-of-two proportional rows. Comparisons use rational RHS.

    Normalization is exponent shifting, with an exact round-trip check. No
    arbitrary division, tolerance or integer-domain dominance is used.
    """
    import hashlib, math
    states={}; factors={}; edges=[]
    def ratio(r):return Q(float(rhs[r]))/Q(factors[r])
    def direction(r):
        s=sense[r]
        return s if factors[r]>0 or s=='=' else ('>' if s=='<' else '<')
    for r0 in np.flatnonzero(eligible):
        r=int(r0);p,q=map(int,a.indptr[r:r+2])
        if p==q:continue
        original=a.data[p:q]; first=float(original[0]);_,exp=math.frexp(abs(first))
        try: factor=math.copysign(math.ldexp(1.,exp-1),first)
        except OverflowError:continue
        normalized=original/factor
        if not np.all(np.isfinite(normalized)) or not np.array_equal(normalized*factor,original):continue
        h=hashlib.blake2b(a.indices[p:q].tobytes()+normalized.tobytes(),digest_size=24).digest()
        factors[r]=factor;s=direction(r)
        if h not in states:states[h]=[r,{s:r}];continue
        representative, best=states[h];u,v=map(int,a.indptr[representative:representative+2])
        if not np.array_equal(a.indices[p:q],a.indices[u:v]) or not np.array_equal(normalized,a.data[u:v]/factors[representative]):
            # A hash collision is never a proof and cannot authorize removal.
            continue
        if s not in best:best[s]=r;continue
        previous=best[s];value=ratio(r);old=ratio(previous)
        if s=='=':
            if value==old:edges.append((r,previous))
        elif s=='<':
            if value<old:edges.append((previous,r));best[s]=r
            else:edges.append((r,previous))
        else:
            if value>old:edges.append((previous,r));best[s]=r
            else:edges.append((r,previous))
    for _,best in states.values():
        if '=' not in best:continue
        eq=best['='];v=ratio(eq)
        if '<' in best and ratio(best['<'])>=v:edges.append((best['<'],eq))
        if '>' in best and ratio(best['>'])<=v:edges.append((best['>'],eq))
    return np.asarray(edges,dtype=np.int64).reshape(-1,2)

def singleton_zero_fixed_point(a,lb,ub,sense,rhs,groups):
    """Zero endpoints and implied zero chains, with original-row receipts."""
    lb=lb.copy();ub=ub.copy();receipts=[]; rounds=[]
    for iteration in range(100):
        knownzero=(lb==0)&(ub==0); co=a.tocoo(); valid=~knownzero[groups[co.col]]
        b=sp.coo_matrix((co.data[valid],(co.row[valid],groups[co.col[valid]])),shape=(a.shape[0],len(lb))).tocsr()
        b.eliminate_zeros(); lens=np.diff(b.indptr);changed=0
        for r in np.flatnonzero((lens==1)&(rhs==0)):
            p=int(b.indptr[r]);j=int(b.indices[p]);c=b.data[p];s=sense[r]
            forces=s=='=' or (s=='<' and c>0 and lb[j]==0) or (s=='<' and c<0 and ub[j]==0) or (s=='>' and c>0 and ub[j]==0) or (s=='>' and c<0 and lb[j]==0)
            if forces and not (lb[j]==0 and ub[j]==0):
                if lb[j]>0 or ub[j]<0:raise ValueError('ZERO_BOUND_CONTRADICTION')
                lb[j]=ub[j]=0;receipts.append((iteration,int(r),j));changed+=1
        rounds.append(dict(round=iteration,new_zero_groups=changed))
        if not changed:break
    else:raise ValueError('ZERO_PROPAGATION_NOT_FIXED_POINT')
    return lb,ub,np.asarray(receipts,dtype=np.int64).reshape(-1,3),rounds

def matrix_census(a,lb,ub,typ):
    nz=abs(a.data[a.data!=0]); d=np.diff(a.indptr); cd=np.bincount(a.indices,minlength=a.shape[1])
    return dict(rows=a.shape[0],columns=a.shape[1],binaries=int(np.sum(typ=='B')),
        integers=int(np.sum(typ=='I')),continuous=int(np.sum(typ=='C')),nnz=a.nnz,
        coefficient_min_abs=float(nz.min()) if len(nz) else 0,coefficient_max_abs=float(nz.max()) if len(nz) else 0,
        max_row_density=int(d.max(initial=0)),max_column_density=int(cd.max(initial=0)))

def candidate(name,aliases=False):
    t=time.perf_counter(); a=sp.load_npz(LOCAL/'A0_MATRIX.npz'); z=attributes()
    n=a.shape[1]; parent=np.arange(n,dtype=np.int64); alias=np.zeros((0,3),dtype=np.int64)
    if aliases: parent,alias=union_aliases(a,z['sense'],z['rhs'],n)
    roots,groups=np.unique(parent,return_inverse=True); k=len(roots)
    lb=np.full(k,-np.inf);ub=np.full(k,np.inf)
    np.maximum.at(lb,groups,z['lb']);np.minimum.at(ub,groups,z['ub'])
    if np.any(lb>ub): raise ValueError('EMPTY_ALIAS_DOMAIN')
    typ=z['vtype'][roots].copy()
    intgroups=np.unique(groups[z['vtype']!='C']);typ[intgroups]='I'
    bingroups=np.unique(groups[z['vtype']=='B']);typ[bingroups]='B'
    br=bc=np.array([],dtype=np.int64);bv=np.array([],dtype=float)
    if aliases:ub,br,bc,bv=positive_resource_bounds(a,lb,ub,z['sense'],z['rhs'],groups)
    lb,ub,bound_receipts,rounds=singleton_zero_fixed_point(a,lb,ub,z['sense'],z['rhs'],groups)
    # Zero constants can be substituted exactly without RHS rounding.
    zero=(lb==0)&(ub==0); keep=np.flatnonzero(~zero)
    new=np.full(k,-1,dtype=np.int64);new[keep]=np.arange(len(keep))
    mapping=new[groups]
    co=a.tocoo(); mask=mapping[co.col]>=0
    b=sp.coo_matrix((co.data[mask],(co.row[mask],mapping[co.col[mask]])),shape=(a.shape[0],len(keep))).tocsr()
    b.sum_duplicates();b.eliminate_zeros();b.sort_indices()
    lb,ub,typ=lb[keep],ub[keep],typ[keep]
    safe=interval_safe(b,lb,ub,z['sense'],z['rhs'],rational=aliases)
    duplicates=duplicate_rows(b,z['sense'],z['rhs'],~safe)
    deleted=safe.copy();deleted[duplicates[:,0]]=True
    domination=proportional_domination(b,z['sense'],z['rhs'],~deleted) if aliases else np.empty((0,2),dtype=np.int64)
    deleted[domination[:,0]]=True
    retained=np.flatnonzero(~deleted)
    b=b[retained]; vf=z['vf'][roots[keep]]
    np.savez_compressed(LOCAL/(name+'_PROOF.npz'),mapping_delta=np.diff(mapping,prepend=0),alias_edges=alias,zero_columns=np.flatnonzero(mapping<0),
        interval_rows=np.flatnonzero(safe),duplicate_pairs=duplicates,domination_pairs=domination,retained_rows_delta=np.diff(retained,prepend=0),roots_delta=np.diff(roots[keep],prepend=0),
        all_roots_delta=np.diff(roots,prepend=0),groups_delta=np.diff(groups,prepend=0),bound_receipts=bound_receipts,
        resource_bound_rows=br,resource_bound_groups=bc,resource_bound_values=bv)
    np.savez_compressed(LOCAL/(name+'_ATTRIBUTES.npz'),lb=lb,ub=ub,vtype=typ,
        rhs=z['rhs'][retained],sense=z['sense'][retained],vf=vf,rf=z['rf'][retained],
        obj=np.bincount(mapping[mapping>=0],weights=z['obj'][mapping>=0],minlength=len(keep)),
        vf_names=z['vf_names'],rf_names=z['rf_names'])
    sp.save_npz(LOCAL/(name+'_MATRIX.npz'),b)
    c=matrix_census(b,lb,ub,typ)
    c.update(alias_edges=len(alias),fixed_zero_columns=int(np.sum(mapping<0)),
             alias_columns=n-int(np.sum(mapping<0))-len(keep),bound_redundant_rows=int(safe.sum()),
             duplicate_rows=len(duplicates),proportional_dominated_rows=len(domination),wall_seconds=time.perf_counter()-t,
             zero_bound_tightenings=len(bound_receipts),fixed_point_rounds=rounds,
             resource_bound_tightenings=len(br),
             nnz_added=0,LP_equivalence_claim='Pending independent verification',
             A2_classification='A-STAGE-GENERIC; regenerate proof against each original A2 matrix, including anchor-specific grid rows')
    write(name+'_MODEL_CENSUS.json',c)
    original_v=Counter(z['vf']);original_r=Counter(z['rf'])
    removed_v=Counter(z['vf'][mapping<0]); alias_v=Counter()
    ids=np.flatnonzero(mapping>=0);representatives=roots[keep]
    aliased=ids[ids!=representatives[mapping[ids]]];alias_v=Counter(z['vf'][aliased])
    removed_r=Counter(z['rf'][deleted])
    ledger=[]
    for family,count in sorted(original_v.items()):
        rem=removed_v[family]+alias_v[family]
        ledger.append(dict(kind='column',family=str(z['vf_names'][family]),original_count=count,tested_count=count,removed_count=rem,
          retained_count=count-rem,proof_type='FIXED_ZERO / EXACT_ALIAS' if rem else 'ESSENTIAL_OR_UNKNOWN',
          reason_retained='All columns tested for explicit fixed-zero and +/-1 equality alias; unproved deterministic/affine/semantic reductions retained'))
    for family,count in sorted(original_r.items()):
        rem=removed_r[family]
        ledger.append(dict(kind='row',family=str(z['rf_names'][family]),original_count=count,tested_count=count,removed_count=rem,
          retained_count=count-rem,proof_type='FULL_LP_REDUNDANT: exact interval/duplicate/alias substitution' if rem else 'ESSENTIAL_OR_UNKNOWN',
          reason_retained='Integer-only and uncertain sign/rank/domain/flow/grid claims retained; no tolerance-based deletion'))
    table(name+'_EXHAUSTIVE_LEDGER.csv',ledger)
    print(name,c,flush=True)

def run():
    if not (OUT/'CURRENT_A0_PRESOLVE_FORENSIC.json').exists():raise PermissionError('PRESOLVE_FORENSIC_REQUIRED_FIRST')
    candidate('A1R');candidate('A2SC',True)

if __name__=='__main__':run()
