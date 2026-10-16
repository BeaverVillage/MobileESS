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
    """Extend an actual native basis with primal-feasible local pivots.

    Old basic columns embed as the upper-left block. Each added row receives
    a local artificial pivot when the old point violates it; otherwise its
    slack remains basic. New equality slacks fixed to zero cannot absorb a
    nonzero RHS. The old block is unchanged and the extension is triangular.
    The constructed elastic witness is diagnostic only, never an original
    feasible point or an installed primal/dual start.
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
    from v42_a_stage_phase1.core import primal_replay
    if 'X' not in raw:raise ValueError('ACTUAL_NATIVE_PRIMAL_REQUIRED_FOR_BASIS_EXTENSION')
    x=np.asarray(raw['X'],dtype=float)
    if not primal_replay(old,x,tolerance=1e-5)['PASS']:
        raise ValueError('OLD_NATIVE_BASIS_POINT_NOT_PRIMAL_FEASIBLE')
    point=np.zeros(new.matrix.shape[1]);point[columns]=x
    byart=defaultdict(list)
    for key,j in target.items():byart[key[0]].append((key[1],j))
    added=sorted(set(range(new.matrix.shape[0]))-set(mapping))
    initial=primal_replay(new,point,tolerance=1e-5)
    pivots=[]
    for i in added:
        a,b=new.matrix.indptr[i:i+2]
        residual=Fraction(float(new.rhs[i]))-sum((Fraction(float(v))*Fraction(float(point[j]))
            for j,v in zip(new.matrix.indices[a:b],new.matrix.data[a:b]) if point[j]),Fraction(0))
        sense=new.senses[i]
        violated=(residual!=0 if sense=='=' else residual<0 if sense=='<' else residual>0)
        if not violated:continue
        eligible=[(sign,j) for sign,j in byart[i] if residual/Fraction(sign)>=0]
        if not eligible:raise ValueError('NEW_HARD_ROW_HAS_NO_PRIMAL_FEASIBLE_BASIS_EXTENSION')
        sign,j=eligible[0];value=float(residual/Fraction(sign))
        if not np.isfinite(value) or not new.lower[j]<=value<=new.upper[j]:
            raise ValueError('NEW_ARTIFICIAL_BASIS_VALUE_OUTSIDE_DOMAIN')
        vnew[j]=0;cnew[i]=-1;point[j]=value;pivots.append(j)
    replay=primal_replay(new,point,tolerance=1e-5)
    if not replay['PASS']:raise ValueError('EXTENDED_ELASTIC_BASIS_WITNESS_REPLAY_FAILED')
    if np.count_nonzero(vnew==0)+np.count_nonzero(cnew==0)!=new.matrix.shape[0]:
        raise ValueError('EXTENDED_NATIVE_BASIS_RANK_COUNT')
    return vnew,cnew,dict(PASS=True,old_rows=len(mapping),new_rows=new.matrix.shape[0]-len(mapping),
        old_columns=len(columns),new_columns=new.matrix.shape[1]-len(columns),
        exact_inclusion=True,new_row_slacks_basic=len(added)-len(pivots),
        new_local_artificials_basic=len(pivots),block_triangular_nonzero_local_pivots=True,
        uncompensated_prior_point_replay=initial,extended_elastic_witness_replay=replay,
        old_primal_coordinates_unchanged=True,old_native_basis_unchanged=True,
        original_FULL_feasible_claimed=False,elastic_witness_installed_as_start=False,
        PStart_DStart_installed=False,LPWarmStart=2)


def basis_admission(proof):
    """Use a proven feasible original basis without crushing positive pivots.

    May01 crossover stalled with LPWarmStart=2; cold barrier then exhausted
    Phase I after discarding the feasible extension. Primal simplex with
    LPWarmStart=1 and Presolve=0 consumes that actual basis on the unchanged
    original elastic matrix. Performance and exact Phi zero still need a solve.
    """
    if not (proof.get('PASS') is True and proof.get('exact_inclusion') is True
            and proof.get('block_triangular_nonzero_local_pivots') is True
            and proof.get('extended_elastic_witness_replay',{}).get('PASS') is True
            and proof.get('old_native_basis_unchanged') is True):
        raise ValueError('VERIFIED_NATIVE_BASIS_EXTENSION_REQUIRED_FOR_ADMISSION')
    count=proof.get('new_local_artificials_basic')
    if type(count) is not int or count<0:raise ValueError('EXACT_NEW_ARTIFICIAL_PIVOT_COUNT_REQUIRED')
    primal=count>0
    return dict(reuse=True,barrier_required=False,primal_simplex_required=primal,
        reason='POSITIVE_ELASTIC_PIVOTS_USE_ORIGINAL_PRIMAL_BASIS' if primal else 'FEASIBLE_NATIVE_BASIS_REUSE_ADMITTED',
        parameters=dict(Method=0,LPWarmStart=1,Presolve=0) if primal else dict(LPWarmStart=2),
        native_basis_preserved_as_evidence=True,original_FULL_UB_claimed=False,
        solver_performance_improvement_claimed=False,
        policy='ACTUAL_MAY01_ORIGINAL_PRIMAL_BASIS_V2')


def restore_cold_phase_policy(model,parameters):
    """A failed basis install must not leave a basis-dependent solver policy."""
    model.reset()
    for key,value in parameters.items():model.setParam(key,value)
    model.setParam('LPWarmStart',0)
