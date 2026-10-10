"""Prove finite helper envelopes from unchanged equalities for the old checker.

These bounds are certificate inputs only. No model/data/domain is mutated.
The existing rational checker still evaluates every signed multiplier exactly.
"""
from collections import deque
from fractions import Fraction as F
from hashlib import sha256
import numpy as np
from v42_m1_research.check_lb import check_rational_dual_certificate as original_checker
from .common import atomic,record,digest

_cache={}


def outward(value,lower):
    x=float(value)
    if not np.isfinite(x):raise ValueError('DERIVED_HELPER_ENVELOPE_NOT_FINITE')
    if (lower and F(x)>value) or (not lower and F(x)<value):
        x=float(np.nextafter(x,-np.inf if lower else np.inf))
    return x


def derive(A,d,lower=None,upper=None):
    A=A.tocsr();lo=np.array(d['lower'] if lower is None else lower,dtype=float,copy=True)
    hi=np.array(d['upper'] if upper is None else upper,dtype=float,copy=True)
    if (lo.shape!=(A.shape[1],) or hi.shape!=lo.shape or np.isnan(lo).any() or np.isnan(hi).any()
            or np.isposinf(lo).any() or np.isneginf(hi).any() or np.any(lo>hi)):
        raise ValueError('HELPER_ENVELOPE_INVALID_ORIGINAL_BOX')
    if not all(np.isfinite(z).all() for z in (A.data,d['rhs'],d['objective'],np.asarray(d['constant']))):
        raise ValueError('HELPER_ENVELOPE_NONFINITE_SCIENTIFIC_COEFFICIENT')
    known=np.isfinite(lo)&np.isfinite(hi);initial=int((~known).sum())
    eq=np.flatnonzero(np.asarray(d['sense'])=='=');counts=np.zeros(A.shape[0],dtype=int)
    depend={};queue=deque();steps=[]
    for i in eq:
        a,b=A.indptr[i:i+2];unknown=[int(j) for j,w in zip(A.indices[a:b],A.data[a:b]) if w and not known[j]]
        counts[i]=len(unknown)
        for j in unknown:depend.setdefault(j,[]).append(int(i))
        if len(unknown)==1:queue.append(int(i))
    while queue:
        i=queue.popleft();a,b=A.indptr[i:i+2]
        terms=[(int(j),F(float(w))) for j,w in zip(A.indices[a:b],A.data[a:b]) if w]
        unknown=[j for j,w in terms if not known[j]]
        if len(unknown)!=1:continue
        j=unknown[0];pivot=next(w for k,w in terms if k==j)
        minimum=maximum=F(float(d['rhs'][i]))
        for k,w in terms:
            if k==j:continue
            # All dependencies are finite original bounds or prior proved bounds.
            minimum-=w*F(float(hi[k] if w>0 else lo[k]))
            maximum-=w*F(float(lo[k] if w>0 else hi[k]))
        if pivot>0:L,U=minimum/pivot,maximum/pivot
        else:L,U=maximum/pivot,minimum/pivot
        L=max(L,F(float(lo[j]))) if np.isfinite(lo[j]) else L
        U=min(U,F(float(hi[j]))) if np.isfinite(hi[j]) else U
        if L>U:raise ValueError('DERIVED_HELPER_ENVELOPE_EMPTY')
        lo[j],hi[j]=outward(L,True),outward(U,False);known[j]=True
        steps.append(dict(column=j,row=i,pivot=str(pivot),exact_lower=str(L),exact_upper=str(U),
            lower=float(lo[j]),upper=float(hi[j])))
        for row in depend.get(j,[]):
            counts[row]-=1
            if counts[row]==1:queue.append(row)
    if not known.all():
        raise ValueError('ORIGINAL_EQUALITIES_DO_NOT_PROVE_FINITE_HELPER_BOX:'+str(int((~known).sum())))
    return lo,hi,dict(PASS=True,initial_unbounded_columns=initial,derived_columns=len(steps),steps=steps,
        theorem='EXACT_INTERVAL_IMPLICATION_OF_UNCHANGED_ORIGINAL_EQUALITIES_AND_NATIVE_BOUNDS',
        original_model_bounds_mutated=False,original_checker_modified=False)


def verify(A,d,lo,hi,proof,lower=None,upper=None):
    """Replay supplied implication witnesses without running the queue generator."""
    A=A.tocsr();L=np.array(d['lower'] if lower is None else lower,dtype=float,copy=True)
    U=np.array(d['upper'] if upper is None else upper,dtype=float,copy=True)
    seen=set()
    for s in proof['steps']:
        j,i=int(s['column']),int(s['row'])
        if j in seen or not 0<=j<A.shape[1] or not 0<=i<A.shape[0] or str(d['sense'][i])!='=':
            raise ValueError('HELPER_BOX_PROOF_AXIS_OR_EQUALITY_DRIFT')
        a,b=A.indptr[i:i+2];weights={int(k):F(float(w)) for k,w in zip(A.indices[a:b],A.data[a:b]) if w}
        pivot=weights.pop(j,F(0))
        if not pivot or pivot!=F(s['pivot']):raise ValueError('HELPER_BOX_PROOF_PIVOT_DRIFT')
        left=right=F(float(d['rhs'][i]))
        for k,w in weights.items():
            if not np.isfinite(L[k]) or not np.isfinite(U[k]):raise ValueError('HELPER_BOX_UNPROVED_DEPENDENCY')
            endpoints=(w*F(float(L[k])),w*F(float(U[k])))
            left-=max(endpoints);right-=min(endpoints)
        bounds=sorted((left/pivot,right/pivot))
        if np.isfinite(L[j]):bounds[0]=max(bounds[0],F(float(L[j])))
        if np.isfinite(U[j]):bounds[1]=min(bounds[1],F(float(U[j])))
        if bounds!=[F(s['exact_lower']),F(s['exact_upper'])]:raise ValueError('HELPER_BOX_EXACT_ENDPOINT_DRIFT')
        if F(s['lower'])>bounds[0] or F(s['upper'])<bounds[1]:raise ValueError('HELPER_BOX_INWARD_ROUNDING')
        L[j],U[j]=s['lower'],s['upper'];seen.add(j)
    if not np.isfinite(L).all() or not np.isfinite(U).all() or not np.array_equal(L,lo) or not np.array_equal(U,hi):
        raise ValueError('HELPER_BOX_COMPLETE_AXIS_OR_BOUND_DRIFT')
    return dict(PASS=True,checked_original_equality_implications=len(seen),all_original_feasible_points_contained=True)


def check(A,d,multipliers,*,lower=None,upper=None,source_rows=None,case_sha=None):
    if np.isfinite(d['lower'] if lower is None else lower).all() and np.isfinite(d['upper'] if upper is None else upper).all():
        return original_checker(A,d,multipliers,lower=lower,upper=upper,source_rows=source_rows,case_sha=case_sha)
    key=sha256()
    for z in (A.indptr,A.indices,A.data,d['lower'] if lower is None else lower,
              d['upper'] if upper is None else upper,d['rhs'],d['sense']):key.update(np.asarray(z).tobytes())
    name=key.hexdigest()
    if name not in _cache:
        lo,hi,proof=derive(A,d,lower,upper);proof['independent_replay']=verify(A,d,lo,hi,proof,lower,upper)
        proof['source_matrix_domain_SHA']=name
        from .execution import current
        context=current()
        evidence=dict(proof_SHA=digest(proof),independent_replay=proof['independent_replay'],
            derived_columns=proof['derived_columns'],original_model_bounds_mutated=False)
        if context:
            from pathlib import Path
            path=Path(context['request']['output'])/'CERTIFICATE_DOMAIN_PROOFS'/(name+'.json')
            atomic(path,proof);evidence['proof_file']=record(path)
        _cache[name]=(lo,hi,evidence)
    lo,hi,evidence=_cache[name]
    result=original_checker(A,d,multipliers,lower=lo,upper=hi,source_rows=source_rows,case_sha=case_sha)
    return dict(result,finite_box_original_row_implication=evidence,
        original_checker_byte_preserved=True,arbitrary_finite_bounds_used=False)
