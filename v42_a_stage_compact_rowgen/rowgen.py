"""Exact omitted-row separation; never calls optimize or deletes original rows."""
from dataclasses import replace
from fractions import Fraction
import numpy as np
from .projection import exact_replay

TOLERANCE=Fraction(1,1000000)

def separate(snapshot,point,included,tolerance=TOLERANCE):
    x=tuple(Fraction(float(v)) for v in point);included=set(map(int,included));violated=[];worst=Fraction(0);A=snapshot.matrix
    for i in range(A.shape[0]):
        if i in included:continue
        lo,hi=A.indptr[i:i+2]
        activity=sum((Fraction(float(a))*x[int(j)] for j,a in zip(A.indices[lo:hi],A.data[lo:hi]) if x[int(j)]),Fraction(0))
        residual=activity-Fraction(float(snapshot.rhs[i]));sense=snapshot.senses[i]
        violation=max(Fraction(0),abs(residual) if sense=='=' else residual if sense=='<' else -residual)
        worst=max(worst,violation)
        if violation>tolerance:violated.append(i)
    return dict(omitted_rows=A.shape[0]-len(included),violated_rows=violated,max_exact_omitted_violation=str(worst),
        registered_tolerance=str(tolerance),PASS=not violated,all_omitted_original_rows_evaluated=True)

def restricted(snapshot,included):
    rows=tuple(sorted(set(included)))
    return replace(snapshot,matrix=snapshot.matrix[list(rows)].tocsr(),senses=snapshot.senses[list(rows)],rhs=snapshot.rhs[list(rows)]).require()

def certified_separate(snapshot,point,included,tolerance=TOLERANCE):
    """Outward sparse-dot envelopes, exact rational fallback near threshold.

    Every omitted row is evaluated. A row is excluded only if its upper
    violation envelope is <= tolerance. Every ambiguity uses original binary64
    coefficients and point as exact rationals; no scientific rounding.
    """
    A=snapshot.matrix;x=np.asarray(point);activity=A@x
    residual=activity-snapshot.rhs
    violation=np.maximum(0,np.where(snapshot.senses=='=',abs(residual),np.where(snapshot.senses=='<',residual,-residual)))
    k=2*np.diff(A.indptr)+8;eps=np.finfo(float).eps
    mag=abs(A)@abs(x)+abs(snapshot.rhs)
    error=np.nextafter(k*eps/(1-k*eps)*np.nextafter(mag/(1-k*eps),np.inf)+k*np.nextafter(0.,1.),np.inf)
    mask=np.ones(A.shape[0],dtype=bool);mask[list(included)]=False
    certain=np.flatnonzero(mask & (np.nextafter(violation-error,-np.inf)>float(tolerance)))
    ambiguous=np.flatnonzero(mask & (np.nextafter(violation+error,np.inf)>float(tolerance)) & ~(np.nextafter(violation-error,-np.inf)>float(tolerance)))
    violated=list(map(int,certain));rational={};worst=0.
    for i in ambiguous:
        lo,hi=A.indptr[i:i+2]
        for j in A.indices[lo:hi]:
            if int(j) not in rational:rational[int(j)]=Fraction(float(x[j]))
        value=sum((Fraction(float(a))*rational[int(j)] for j,a in zip(A.indices[lo:hi],A.data[lo:hi])),Fraction(0))-Fraction(float(snapshot.rhs[i]))
        v=max(Fraction(0),abs(value) if snapshot.senses[i]=='=' else value if snapshot.senses[i]=='<' else -value)
        worst=max(worst,float(v))
        if v>tolerance:violated.append(int(i))
    return dict(PASS=not violated,omitted_rows=int(mask.sum()),violated_rows=sorted(violated),
        max_numeric_omitted_violation=float(violation[mask].max(initial=0)),exact_fallback_rows=len(ambiguous),
        registered_tolerance=str(tolerance),all_omitted_original_rows_evaluated=True,
        outward_envelope='gamma_(2*nnz+8), magnitude upward inflation, subnormal allowance; threshold ambiguity exact Fraction',
        coefficients_or_raw_point_modified=False)
