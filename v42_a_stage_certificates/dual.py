"""Separate certificate dual projection for nonnegative unbounded variables.

Raw native Pi is retained. Setting selected legal Pi components to zero is
only a certificate proposal; its complete bound is independently recomputed.
Support shrinks monotonically and no residual is accepted by a tolerance.
"""
from fractions import Fraction
import numpy as np

def repair(matrix,c,raw_pi,senses,lower,upper,check=lambda:None):
    if np.any(lower<0):raise ValueError('NONNEGATIVE_DOMAIN_REQUIRED')
    A=matrix.tocsc();pi=np.asarray(raw_pi).copy();pi[(senses=='<')&(pi>0)]=0;pi[(senses=='>')&(pi<0)]=0
    inf=np.flatnonzero((~np.isfinite(upper))|(upper>=1e100));steps=[]
    if np.any(np.asarray(c)[inf]<0):raise ValueError('NONNEGATIVE_UNBOUNDED_OBJECTIVE_REQUIRED')
    for iteration in range(np.count_nonzero(pi)+1):
        check();bad=[];remove=set()
        for count,j in enumerate(inf):
            if count%128==0:check()
            lo,hi=A.indptr[j:j+2]
            rc=Fraction(float(c[j]))-sum((Fraction(float(a))*Fraction(float(pi[i])) for i,a in zip(A.indices[lo:hi],A.data[lo:hi])),Fraction(0))
            if rc<0:
                bad.append(int(j));remove.update(int(i) for i in A.indices[lo:hi] if pi[i])
        if not bad:
            return pi,dict(PASS=True,unbounded_columns=len(inf),all_unbounded_RC_exact_nonnegative=True,
                removed_rows=sorted(set(r for s in steps for r in s['removed_rows'])),steps=steps,
                original_raw_pi_preserved=True,separate_certificate_proposal=True,tolerance_used_for_RC_acceptance=False)
        if not remove:raise ValueError('CANNOT_REPAIR_WITH_SUPPORT_PROJECTION')
        steps.append(dict(iteration=iteration,bad_infinite_columns=bad,removed_rows=sorted(remove)))
        pi[list(remove)]=0.
    raise RuntimeError('MONOTONE_DUAL_SUPPORT_TERMINATION_FAILED')
