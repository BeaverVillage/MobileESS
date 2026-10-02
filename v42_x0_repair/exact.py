"""Derive exact equality multipliers; never alter a coefficient or delete a residual."""
from collections import deque
from fractions import Fraction as F
import math
import numpy as np
from v42_benders.certificates import Uncertifiable,round_affine
from v42_benders.canonical import digest_arrays

def q(v):return v if isinstance(v,F) else F.from_float(float(v))

def products(A,w):
    result={}
    for i,v in w.items():
        if not v:continue
        for k in range(A.indptr[i],A.indptr[i+1]):
            j=int(A.indices[k]);result[j]=result.get(j,F(0))+v*q(A.data[k])
    return {j:v for j,v in result.items() if v}

def pivots(n):
    free=np.flatnonzero(np.isneginf(n.lower)&np.isposinf(n.upper))
    erows=np.flatnonzero(n.sense=='=');E=n.A[erows][:,free].tocsr();C=E.tocsc()
    count=np.diff(E.indptr).copy();active=np.ones(len(free),bool);done=np.zeros(len(erows),bool)
    queue=deque(np.flatnonzero(count==1));order=[]
    while queue:
        i=int(queue.popleft())
        if done[i] or count[i]!=1:continue
        js=E.indices[E.indptr[i]:E.indptr[i+1]];j=next(int(j) for j in js if active[j])
        order.append((int(erows[i]),int(free[j])));done[i]=True;active[j]=False
        for k in C.indices[C.indptr[j]:C.indptr[j+1]]:
            if not done[k]:
                count[k]-=1
                if count[k]==1:queue.append(int(k))
    return order,free[active]

def complete(n,multipliers):
    w={i:q(v) for i,v in enumerate(multipliers) if v};a=products(n.A,w)
    order,unresolved=pivots(n);changes=[]
    for i,j in reversed(order):
        residual=a.get(j,F(0))
        if not residual:continue
        pivot=q(n.A[i,j]);delta=-residual/pivot;before=w.get(i,F(0));w[i]=before+delta
        changes.append(dict(row=i,column=j,before=str(before),delta=str(delta),after=str(w[i]),pivot=str(pivot)))
        for k in range(n.A.indptr[i],n.A.indptr[i+1]):
            col=int(n.A.indices[k]);a[col]=a.get(col,F(0))+delta*q(n.A.data[k])
        assert a[j]==0
    a={j:v for j,v in a.items() if v}
    if any(j in a for j in np.flatnonzero(np.isneginf(n.lower)&np.isposinf(n.upper))):
        raise Uncertifiable('FREE_EQUALITY_COMPLETION_UNRESOLVED')
    return {i:v for i,v in w.items() if v},changes,dict(pivots=len(order),unresolved=len(unresolved),free_columns=int(np.sum(np.isneginf(n.lower)&np.isposinf(n.upper))))

def support(a,lower,upper):
    bound=F(0);terms={}
    for j,v in a.items():
        extremum=lower[j] if v>0 else upper[j]
        if not math.isfinite(extremum):raise Uncertifiable('UNBOUNDED_SUPPORT_COLUMN_'+str(j))
        terms[j]=v*q(extremum);bound+=terms[j]
    return bound,terms

def create(n,raw,known=()):
    phase=bool(raw.get('phase1'))
    if raw['status']!=(2 if phase else 3) or raw.get('multipliers') is None:raise Uncertifiable('NONTERMINAL_SOURCE')
    if len(raw['multipliers'])!=len(n.b) or not np.isfinite(raw['multipliers']).all():raise Uncertifiable('MULTIPLIER_AXIS')
    # Phase-I dual is always positively normalized by 1/2, not selected after a result.
    # Its exact lower bound need not be tight to prove positive minimum slack.
    factor=F(1,2) if phase else F(1)
    w,changes,structure=complete(n,[q(v)*factor for v in raw['multipliers']])
    for i,v in w.items():
        sign=-1 if phase else 1
        if (n.sense[i]=='<' and v*sign<0) or (n.sense[i]=='>' and v*sign>0):raise Uncertifiable('MULTIPLIER_SIGN')
    if phase:
        for i,s in enumerate(n.sense):
            v=w.get(i,F(0));weight=q(raw['weights'][i])
            if (s in ['<','='] and weight+v<0) or (s in ['>','='] and weight-v<0):raise Uncertifiable('PHASE1_ARTIFICIAL_DUAL_INFEASIBLE')
    a=products(n.A,w);bx=products(n.B,w)
    bound,terms=support({j:-v for j,v in a.items()} if phase else a,n.lower,n.upper)
    row=sum((v*q(n.b[i]) for i,v in w.items()),F(0))
    intercept=-row-bound if phase else row-bound;coeff=bx if phase else {j:-v for j,v in bx.items()}
    ri,rc=round_affine(intercept,coeff,n.xlower,n.xupper,1)
    x=np.asarray(raw['source_x']);exact_source=intercept+sum((v*q(x[j]) for j,v in coeff.items()),F(0))
    violation=-(ri+float(rc@x))
    if exact_source>=-q(1e-8) or violation<=1e-8:raise Uncertifiable('NO_STRICT_SEPARATION')
    solver_row=sum((v*q(raw['solver_rhs'][i]) for i,v in w.items()),F(0))
    proof=solver_row+bound if phase else bound-solver_row
    if phase and float(proof)>raw['objective']+1e-7:raise Uncertifiable('PHASE1_WEAK_DUALITY')
    record=dict(kind='EXACT_EQUALITY_COMPLETED_PHASE1' if phase else 'EXACT_EQUALITY_COMPLETED_FARKAS',type='feasibility',intercept=ri,exact_intercept=str(intercept),
        exact_coefficients={str(j):str(v) for j,v in coeff.items()},bound_contribution=str(bound),
        bound_terms={str(j):str(v) for j,v in terms.items()},row_contribution=str(row),source_exact=str(exact_source),
        strict_margin=violation,source_x_hash=digest_arrays(x),source_hash=n.source_hash,
        native_FarkasProof=raw['farkas_proof'],completed_proof_on_solver_RHS=str(proof),
        difference_from_native_proof=None if phase else float(proof)-raw['farkas_proof'],raw_vector_sha256=raw['vector_sha256'],
        positive_dual_normalization=str(factor),
        rational_multipliers={str(i):str(v) for i,v in w.items()},equality_changes=changes,structure=structure,
        cut_hash=digest_arrays(np.array([ri]),rc),raw_persistence=raw['persistence'],
        clamp=False,flip=False,tiny_coefficient_deletion=False,scientific_matrix_changed=False)
    cut=dict(record=record,coefficients=rc,raw=raw)
    return cut
