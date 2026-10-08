"""Bounds proved from unchanged original rows, for the dual certificate only."""
import math
from fractions import Fraction
import numpy as np
from v42_a_stage_phase1.core import interval_box_bound

def certify(original,global_rows,n,pi,c,excluded_rows):
    rows=list(global_rows);global_set=set(rows);A=original.matrix[rows,:n].tocsc();pg=np.asarray(pi)[rows]
    lower=original.lower[:n].copy();upper=original.upper[:n].copy();excluded=set(excluded_rows)
    bycolumn=original.matrix.tocsc();proofs=[]
    def infinite(x):return not math.isfinite(x) or abs(x)>=1e100
    def outward(value,up):
        x=float(value)
        if (up and Fraction(x)<value) or (not up and Fraction(x)>value):
            x=np.nextafter(x,np.inf if up else -np.inf)
        return x
    for j in np.flatnonzero([infinite(l) or infinite(u) for l,u in zip(lower,upper)]):
        lo,hi=A.indptr[j:j+2]
        rc=Fraction(float(c[j]))-sum((Fraction(float(A.data[k]))*Fraction(float(pg[A.indices[k]])) for k in range(lo,hi)),Fraction())
        direction='upper' if rc<0 and infinite(upper[j]) else 'lower' if rc>0 and infinite(lower[j]) else None
        if direction is None:continue
        choices=[]
        for row in bycolumn.indices[bycolumn.indptr[j]:bycolumn.indptr[j+1]]:
            if row not in global_set or row in excluded:continue
            a,b=original.matrix.indptr[row:row+2];items=list(zip(original.matrix.indices[a:b],original.matrix.data[a:b]))
            if any(k>=n for k,v in items):continue
            sense=original.senses[row]
            for sign in ((1,-1) if sense=='=' else (1,) if sense=='<' else (-1,)):
                coefficient=next((Fraction(float(v))*sign for k,v in items if k==j),Fraction())
                if not coefficient or (coefficient>0)!=(direction=='upper'):continue
                terms=[];inputs=[]
                for k,v in items:
                    if k==j:continue
                    v=Fraction(float(v))*sign
                    bound=original.lower[k] if v>=0 else original.upper[k]
                    if infinite(bound):break
                    terms.append(v*Fraction(float(bound)));inputs.append(dict(column=int(k),coefficient=str(v),original_bound=str(Fraction(float(bound)))))
                else:
                    rhs=Fraction(float(original.rhs[row]))*sign
                    value=(rhs-sum(terms,Fraction()))/coefficient
                    choices.append(dict(row=int(row),sign=sign,coefficient=str(coefficient),rhs=str(rhs),
                        other_original_box_inputs=inputs,exact_bound=str(value),value=value))
        if not choices:
            return None,dict(PASS=False,reason='ORIGINAL_GLOBAL_ROWS_DO_NOT_BOUND_REQUIRED_RESIDUAL',column=int(j),exact_RC=str(rc),proofs=proofs)
        chosen=(min if direction=='upper' else max)(choices,key=lambda x:x['value']);value=chosen.pop('value')
        (upper if direction=='upper' else lower)[j]=outward(value,direction=='upper')
        proofs.append(dict(column=int(j),direction=direction,exact_RC=str(rc),**chosen))
    if np.any(lower>upper):return None,dict(PASS=False,reason='DERIVED_BOX_CONTRADICTION_NOT_AN_INFEASIBILITY_CERTIFICATE',proofs=proofs)
    bound=interval_box_bound(A,c,pg,lower,upper,original.rhs[rows])
    return bound,dict(PASS=bound is not None,global_bound=bound,proofs=proofs,
        only_original_global_non_coupling_rows_used=True,exact_Fraction_row_implication=True,
        outward_rounded_certificate_box=True,raw_native_Pi_preserved=True,
        original_solver_matrix_bounds_objectives_tolerances_unchanged=True,
        original_snapshot_sha256=original.fingerprint(),derived_box_not_installed_in_solver=True)
