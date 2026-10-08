"""Exact dyadic replay of actual binary64 rows and separately mapped points."""
from fractions import Fraction
from time import perf_counter
import math
import numpy as np

def dyadic(value):
    n,d=float(value).as_integer_ratio();return n,d.bit_length()-1

def add(a,ae,b,be):
    e=max(ae,be);return (a<<(e-ae))+(b<<(e-be)),e

def replay(snapshot,x,tolerance=1e-6):
    started=perf_counter();x=np.asarray(x)
    if x.shape!=(snapshot.matrix.shape[1],) or not np.all(np.isfinite(x)):raise ValueError('EXACT_FINITE_ORIGINAL_POINT_REQUIRED')
    active=np.flatnonzero(x);values=[dyadic(x[j]) for j in active];A=snapshot.matrix[:,active].tocsr()
    coeff={};rhs={};worst=(0,0);bad=[];checked_terms=0
    tn,td=float(tolerance).as_integer_ratio()
    for row in range(A.shape[0]):
        start,end=A.indptr[row:row+2];num=0;exp=0
        for k in range(start,end):
            a=float(A.data[k]);an,ae=coeff.setdefault(a,dyadic(a));xn,xe=values[A.indices[k]]
            num,exp=add(num,exp,an*xn,ae+xe);checked_terms+=1
        b=float(snapshot.rhs[row]);bn,be=rhs.setdefault(b,dyadic(b));num,exp=add(num,exp,-bn,be)
        sense=snapshot.senses[row];violation=abs(num) if sense=='=' else max(0,num) if sense=='<' else max(0,-num)
        if violation*td>tn*(1<<exp):bad.append(row)
        if violation*(1<<worst[1])>worst[0]*(1<<exp):worst=(violation,exp)
    # Comparing binary64 endpoints is itself exact: there is no arithmetic
    # transport in a direct bound comparison.
    bound_bad=np.flatnonzero((x<snapshot.lower-tolerance)|(x>snapshot.upper+tolerance))
    bound_max=max(float(np.maximum(snapshot.lower-x,x-snapshot.upper).max(initial=0)),0.)
    bound_exact=max((Fraction(float(snapshot.lower[j]))-Fraction(float(x[j])) if x[j]<snapshot.lower[j] else
        Fraction(float(x[j]))-Fraction(float(snapshot.upper[j])) if x[j]>snapshot.upper[j] else Fraction(0)
        for j in np.flatnonzero((x<snapshot.lower)|(x>snapshot.upper))),default=Fraction(0))
    passed=not bad and bound_exact<=Fraction(float(tolerance))
    return dict(PASS=passed,exact_binary64_dyadic_arithmetic=True,rows=A.shape[0],columns=len(x),
        nonzero_point_columns=len(active),nonzero_products_checked=checked_terms,
        exact_max_row_violation=str(Fraction(worst[0],1<<worst[1])),exact_max_bound_violation=str(bound_exact),
        scientific_tolerance=str(Fraction(float(tolerance))),rejected_rows=bad[:20],raw_or_mapped_point_modified=False,
        wall_seconds=perf_counter()-started)
