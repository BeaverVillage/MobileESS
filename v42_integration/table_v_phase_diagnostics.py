"""Original-coordinate LP diagnostics; numerical admission is not a bound."""
from collections import defaultdict,deque
import csv
from fractions import Fraction
import numpy as np
from .table_v_phase_policy import compare_raw


def residual_report(snapshot,raw,folder,*,master=None):
    report=compare_raw(snapshot,raw)
    if 'X' not in raw:return report
    x=np.asarray(raw['X']);A=snapshot.matrix
    activity=A@x;error=activity-snapshot.rhs
    violation=np.maximum(0.,np.where(snapshot.senses=='<',error,
        np.where(snapshot.senses=='>',-error,abs(error))))
    magnitude=abs(A)@abs(x)
    scale=np.maximum(1.,np.maximum(abs(snapshot.rhs),magnitude))
    relative=violation/scale
    # The snapshot carries coefficient axes, not engineering unit annotations.
    # Never label a mixed-coordinate row as pu, MW, seconds or GPU without its
    # authority metadata. This denominator diagnoses cancellation, not admission.
    with (folder/'ROW_RESIDUALS.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['snapshot_row','sense','rhs','activity',
            'signed_residual','absolute_violation','relative_violation','abs_term_sum',
            'diagnostic_scale','physical_unit','pass_1e6','pass_1e5'])
        for i in range(A.shape[0]):
            writer.writerow([i,snapshot.senses[i],snapshot.rhs[i],activity[i],error[i],
                violation[i],relative[i],magnitude[i],scale[i],'UNANNOTATED_SOURCE_COORDINATE',
                violation[i]<=1e-6,violation[i]<=1e-5])
    exact=[]
    for i in np.argsort(-violation,kind='stable')[:20]:
        a,b=A.indptr[i:i+2]
        value=sum((Fraction(float(v))*Fraction(float(x[j])) for j,v in
            zip(A.indices[a:b],A.data[a:b])),Fraction(0))-Fraction(float(snapshot.rhs[i]))
        exact.append(dict(snapshot_row=int(i),signed_exact_residual=str(value)))
    report.update(max_absolute_row_violation=float(violation.max(initial=0)),
        max_relative_row_violation=float(relative.max(initial=0)),
        relative_denominator='max(1,abs(rhs),sum(abs(A_ij*x_j))) diagnostic only',
        row_units='UNANNOTATED in LinearSnapshot; no physical unit conversion or row scaling applied',
        worst_20_exact_dyadic_residuals=exact,all_original_coefficients_retained=True)
    if all(k in raw for k in ('Pi','RC')):
        pi=np.asarray(raw['Pi']);rc=np.asarray(raw['RC'])
        from v42_a_stage_phase1.core import reconstructed_reduced_cost
        rebuilt=reconstructed_reduced_cost(snapshot,pi)
        report['relative_dual_KKT']=dict(
            max_stationarity=float((abs(rebuilt-rc)/np.maximum(1.,np.maximum(abs(rebuilt),abs(rc)))).max(initial=0)),
            max_complementarity=float((abs(pi*error)/np.maximum(1.,abs(pi)*scale)).max(initial=0)),
            diagnostic_only=True,acceptance_uses_absolute_residuals=True)
    phi=snapshot.objectives[0]
    if phi.name=='Phi':
        terms=phi.coefficients();ids=np.asarray(list(terms),dtype=int)
        value=sum((v*Fraction(float(x[j])) for j,v in terms.items()),Fraction(phi.constant))
        report['Phi']=dict(exact=str(value),float_value=float(value),exact_zero=value==0,
            artificial_max_abs=float(abs(x[ids]).max(initial=0)),
            artificial_nonnegative_violation=float(np.maximum(0.,-x[ids]).max(initial=0)),
            artificial_count=len(ids),certified_Global_LB=None)
    if master is not None:
        from v42_a_stage_phase1.core import primal_replay
        n=master.original.matrix.shape[1]
        report['artificial_free_original_replay']={str(t):primal_replay(master.original,x[:n],t) for t in (1e-6,1e-5)}
    return report


def extend_basis(old,new,raw):
    """Exact row/column inclusion plus new basic slacks preserves basis rank.

    Old basic columns embed as the upper-left block. Each added row receives
    its own slack basis column, giving a block triangular basis. No primal or
    dual start is invented, and Gurobi still validates the installed basis.
    """
    if not all(k in raw for k in ('VBasis','CBasis')):raise ValueError('NO_VALID_NATIVE_BASIS')
    oc=old.objectives[0].coefficients();nc=new.objectives[0].coefficients()
    if old.objectives[0].name!='Phi' or new.objectives[0].name!='Phi' or not oc or not nc:
        raise ValueError('ELASTIC_PHI_BASIS_ONLY')
    n=min(oc)
    if min(nc)!=n or any(not np.array_equal(getattr(old,k)[:n],getattr(new,k)[:n]) for k in ('lower','upper','vtypes')):
        raise ValueError('BASE_COLUMN_DOMAIN_CHANGED')
    def rows(s):
        a=s.matrix[:,:n].tocsr();out=[]
        for i in range(a.shape[0]):
            lo,hi=a.indptr[i:i+2]
            out.append((a.indices[lo:hi].tobytes(),a.data[lo:hi].tobytes(),
                        str(s.senses[i]),np.asarray(s.rhs[i]).tobytes()))
        return out
    byrow=defaultdict(deque)
    for i,key in enumerate(rows(new)):byrow[key].append(i)
    mapping=[]
    for key in rows(old):
        if not byrow[key]:raise ValueError('OLD_ROW_NOT_EXACTLY_INCLUDED')
        mapping.append(byrow[key].popleft())
    def arts(s,coeffs,rowmap=None):
        a=s.matrix.tocsc();out={}
        for j in range(n,a.shape[1]):
            lo,hi=a.indptr[j:j+2]
            if hi-lo!=1 or j not in coeffs:raise ValueError('NONLOCAL_ARTIFICIAL_COLUMN')
            i=int(a.indices[lo]);i=rowmap[i] if rowmap is not None else i
            key=(i,float(a.data[lo]),coeffs[j],float(s.lower[j]),float(s.upper[j]),str(s.vtypes[j]))
            if key in out:raise ValueError('AMBIGUOUS_ARTIFICIAL_COLUMN')
            out[key]=j
        return out
    target=arts(new,nc);source=arts(old,oc,mapping)
    columns=list(range(n))+[target[key] if key in target else -1 for key in source]
    if -1 in columns:raise ValueError('OLD_ARTIFICIAL_COLUMN_NOT_INCLUDED')
    vb=np.asarray(raw['VBasis']);cb=np.asarray(raw['CBasis'])
    if vb.shape!=(old.matrix.shape[1],) or cb.shape!=(old.matrix.shape[0],):raise ValueError('BASIS_AXES')
    if not np.isin(vb,[0,-1,-2,-3]).all() or not np.isin(cb,[0,-1]).all():raise ValueError('INVALID_BASIS_CODES')
    if np.count_nonzero(vb==0)+np.count_nonzero(cb==0)!=old.matrix.shape[0]:raise ValueError('INCOMPLETE_NATIVE_BASIS')
    vnew=np.full(new.matrix.shape[1],-1,dtype=np.int32);cnew=np.zeros(new.matrix.shape[0],dtype=np.int32)
    vnew[columns]=vb;cnew[mapping]=cb
    return vnew,cnew,dict(PASS=True,old_rows=len(mapping),new_rows=new.matrix.shape[0]-len(mapping),
        old_columns=len(columns),new_columns=new.matrix.shape[1]-len(columns),
        exact_inclusion=True,new_row_slacks_basic=True,PStart_DStart_installed=False,LPWarmStart=2)
