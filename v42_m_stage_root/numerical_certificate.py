"""Exact boundary canonicalization; no native model, solve or tolerance cone.

Inequality signs are repaired to the exact zero boundary only after the caller
has established the existing numerical residual authority. Equality duals
are unrestricted. Original triangular equalities annihilate free residuals;
convexity multipliers are lowered by the exact minimum retained-column RC.
Every resulting column and interval support is independently checked.
"""
from fractions import Fraction as F
import numpy as np

def finite(x):return bool(np.isfinite(x) and abs(x)<1e90)
def down(q):
    x=float(q)
    return float(np.nextafter(x,-np.inf)) if F(x)>q else x
def residual(A,c,pi):
    q={int(j):F(float(c[j])) for j in np.flatnonzero(c)}
    for i,p in pi.items():
        if not p:continue
        a,b=A.indptr[i:i+2]
        for j,v in zip(A.indices[a:b],A.data[a:b]):
            j=int(j);q[j]=q.get(j,F(0))-p*F(float(v))
    return q
def signs(sense,pi):
    return all(sense[i]=='=' or sense[i]=='<' and p<=0 or sense[i]=='>' and p>=0 for i,p in pi.items())
def support(q,lo,hi):
    terms={}
    for j,r in q.items():
        if not r:continue
        bound=lo[j] if r>0 else hi[j]
        if not finite(bound):raise ValueError('NONZERO_RC_AT_INFINITE_BOUND:'+str(j))
        terms[j]=r*F(float(bound))
    return terms,sum(terms.values(),F(0))
def canonicalize(A,v,pivots,convexity_rows,within_authority,eps=1e-8):
    if not within_authority:raise ValueError('NUMERICAL_RESIDUAL_AUTHORITY_REQUIRED')
    pi={i:F(float(p)) for i,p in enumerate(v['pi']) if p}
    projected=[]
    for i,p in list(pi.items()):
        if v['sense'][i]=='<' and p>0 or v['sense'][i]=='>' and p<0:
            if abs(p)>F(eps):raise ValueError('SIGN_RESIDUAL_OUTSIDE_AUTHORITY')
            projected.append((i,p));pi[i]=F(0)
    q=residual(A,v['objective'],pi)
    free={j for j in range(A.shape[1]) if not finite(v['lower'][j]) and not finite(v['upper'][j])}
    prior=set();checked=[]
    for i,j in pivots:
        i,j=int(i),int(j)
        if j not in free or j in prior or v['sense'][i]!='=':raise ValueError('INVALID_FREE_EQUALITY_PIVOT')
        a,b=A.indptr[i:i+2];ix=A.indices[a:b];vals=A.data[a:b]
        if j not in ix or any(int(k)!=j and int(k) in free and int(k) not in prior for k in ix):raise ValueError('NONTRIANGULAR_EQUALITY_PIVOT')
        coefficient=F(float(vals[np.flatnonzero(ix==j)[0]]))
        if not coefficient:raise ValueError('ZERO_PIVOT')
        checked.append((i,j,coefficient));prior.add(j)
    if prior!=free:raise ValueError('INCOMPLETE_FREE_EQUALITY_COVERAGE')
    repairs=[]
    for i,j,c in reversed(checked):
        change=q.get(j,F(0))/c
        if change:
            pi[i]=pi.get(i,F(0))+change
            a,b=A.indptr[i:i+2]
            for k,z in zip(A.indices[a:b],A.data[a:b]):q[int(k)]=q.get(int(k),F(0))-change*F(float(z))
            repairs.append((i,j,change))
        assert q.get(j,F(0))==0
    offsets=[];seen=set()
    for i in convexity_rows:
        i=int(i);a,b=A.indptr[i:i+2];cols=A.indices[a:b]
        if v['sense'][i]!='=' or v['rhs'][i]!=1 or not np.all(A.data[a:b]==1):raise ValueError('INVALID_CONVEXITY_ROW')
        if any(int(j) in seen or v['lower'][j]!=0 for j in cols):raise ValueError('INVALID_CONVEXITY_COLUMN_PARTITION')
        seen.update(map(int,cols))
        delta=min([F(0),*(q.get(int(j),F(0)) for j in cols)])
        pi[i]=pi.get(i,F(0))+delta
        for j in cols:q[int(j)]=q.get(int(j),F(0))-delta
        offsets.append((i,delta))
    if not signs(v['sense'],pi):raise ValueError('CANONICAL_SIGN_NOT_EXACT')
    terms,penalty=support(q,v['lower'],v['upper'])
    rhs=F(float(v['constant']))+sum((p*F(float(v['rhs'][i])) for i,p in pi.items()),F(0))
    exact=rhs+penalty
    maximum_change=max((abs(p-F(float(v['pi'][i]))) for i,p in pi.items()),default=F(0))
    if maximum_change>F(eps):raise ValueError('CANONICAL_CHANGE_EXCEEDS_EXISTING_AUTHORITY')
    return pi,q,terms,dict(projected=projected,equality_repairs=repairs,convexity_offsets=offsets,
        exact_value=exact,rhs=rhs,support=penalty,maximum_change=maximum_change,
        free_coordinates=len(free),retained_columns=len(seen))
def independent_csc(A,v,pi):
    if not signs(v['sense'],pi):raise ValueError('INDEPENDENT_SIGN_FAILURE')
    C=A.tocsc();q={};terms={};free=0
    for j in range(A.shape[1]):
        a,b=C.indptr[j:j+2]
        r=F(float(v['objective'][j]))-sum((pi[int(i)]*F(float(w)) for i,w in zip(C.indices[a:b],C.data[a:b]) if int(i) in pi),F(0))
        q[j]=r
        if not finite(v['lower'][j]) and not finite(v['upper'][j]):
            if r:raise ValueError('INDEPENDENT_FREE_STATIONARITY_NONZERO:'+str(j))
            free+=1
        if r:
            bound=v['lower'][j] if r>0 else v['upper'][j]
            if not finite(bound):raise ValueError('INDEPENDENT_INFINITE_BOUND:'+str(j))
            terms[j]=r*F(float(bound))
    rhs=F(float(v['constant']))+sum((p*F(float(v['rhs'][i])) for i,p in pi.items()),F(0))
    return q,terms,rhs+sum(terms.values(),F(0)),free
