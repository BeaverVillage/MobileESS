"""Independent exact-rational weak-duality checker, without optimization.

For min c'x, sign-valid pi gives c'x >= b'pi+(c-A'pi)'x.
Finite coordinate enclosures are proved from ORIGINAL binding equalities,
never installed as model bounds. Thus a nonzero dual residual is paid for.
"""
from .common import *
from fractions import Fraction as F
import math
import numpy as np

def down(q):
    f=float(q)
    return np.nextafter(f,-np.inf).item() if F(f)>q else f

def up(q):
    f=float(q)
    return np.nextafter(f,np.inf).item() if F(f)<q else f

def enclosures(A,d):
    lo=d['lower'].copy(); hi=d['upper'].copy()
    targets={i for i in range(len(lo)) if not (np.isfinite(lo[i]) and np.isfinite(hi[i]))}
    rows=[]
    for i,n in enumerate(d['row_names']):
        if str(n).endswith('_binding') and d['sense'][i]=='=':
            a,b=A.indptr[i:i+2]; jj=A.indices[a:b]; vv=A.data[a:b]
            unknown=[int(j) for j in jj if j in targets]
            if len(unknown)!=1: continue
            j=unknown[0]; coeff=F(float(vv[np.flatnonzero(jj==j)[0]]))
            rest=[(int(k),F(float(v))) for k,v in zip(jj,vv) if k!=j]
            if not all(np.isfinite(lo[k]) and np.isfinite(hi[k]) for k,_ in rest):continue
            low=high=F(float(d['rhs'][i]))
            for k,v in rest:
                p,q=v*F(float(lo[k])),v*F(float(hi[k]))
                low-=max(p,q); high-=min(p,q)
            ends=(low/coeff,high/coeff)
            lo[j]=down(min(ends)); hi[j]=up(max(ends))
            rows.append((i,j));targets.remove(j)
    assert not targets,('UNPROVEN_COORDINATE_ENCLOSURES',len(targets))
    np.savez_compressed(OUT/'PROVEN_COORDINATE_ENCLOSURES.npz',lower=lo,upper=hi,binding_row_column=np.asarray(rows,dtype=np.int64))
    write('COORDINATE_ENCLOSURE_PROOF.json',dict(PASS=True,
          derived_columns=len(rows),new_solver_bounds=0,new_constraints=0,
          method='Exact Fraction arithmetic on the original triangular affine binding equalities; rational endpoints rounded outwards to dyadic floats.',
          proof='Induct in binding-row order: all predecessors have valid finite enclosures. Solve the sole unknown coordinate equality over the predecessor box. Outward-rounded endpoints contain every original feasible point.',
          native_finite_bounds_unchanged=True,artifact_SHA=sha(OUT/'PROVEN_COORDINATE_ENCLOSURES.npz')))
    return lo,hi

def rational_bound(A,d,pi,lo,hi,selected=None,save=None):
    pi=np.asarray(pi,dtype=float).copy()
    # Project inequality signs exactly. Equality multipliers are unrestricted.
    pi[d['sense']=='<']=np.minimum(pi[d['sense']=='<'],0.)
    pi[d['sense']=='>']=np.maximum(pi[d['sense']=='>'],0.)
    residual={int(j):F(float(d['objective'][j])) for j in np.flatnonzero(d['objective'])}
    value=F(float(d['constant']))
    support=np.flatnonzero(pi)
    for i in support:
        p=F(float(pi[i])); value+=p*F(float(d['rhs'][i]))
        a,b=A.indptr[i:i+2]
        for j,c in zip(A.indices[a:b],A.data[a:b]):
            j=int(j); residual[j]=residual.get(j,F(0))-p*F(float(c))
    penalty=F(0)
    for j,r in residual.items():
        endpoint=1. if selected==j else float(lo[j] if r>=0 else hi[j])
        penalty+=r*F(endpoint)
    value+=penalty
    result=dict(rational_lower_bound=down(value),exact_bound_numerator=str(value.numerator),
                exact_bound_denominator=str(value.denominator),nonzero_dual_rows=len(support),
                nonzero_residual_columns=sum(v!=0 for v in residual.values()),
                residual_box_term=float(penalty),sign_projection=True,
                exact_weak_duality_PASS=True,raw_objective_used_as_coefficient=False)
    if save:
        np.savez_compressed(OUT/save,rows=support,Pi=pi[support])
        result.update(dual_certificate_file=save,dual_certificate_SHA=sha(OUT/save))
    return result

def safe_bound(certified,epsilon=1e-8):
    # The existing global L0 certificate also applies to every conditional LP.
    combined=max(BASE_LB,certified)
    safe=max(BASE_LB,down(F(combined)-F(epsilon)))
    return safe,combined

def audit_solution(A,d,B,e,x,pi,rc,vb,cb,lo,hi,j,objective,kappa,save):
    from v42_integrated.matrix import audit
    fixed=dict(d,lower=d['lower'].copy(),upper=d['upper'].copy())
    fixed['lower'][j]=fixed['upper'][j]=1.
    primal=audit(A,fixed,x,tolerance=1e-8)
    stationarity=e['objective']-B.T@pi-rc
    dual_sign=max(float(np.maximum(pi[e['sense']=='<'],0.).max(initial=0.)),
                  float(np.maximum(-pi[e['sense']=='>'],0.).max(initial=0.)))
    basic=np.asarray(vb)==0
    basis_residual=max(float(abs(stationarity).max(initial=0.)),float(abs(rc[basic]).max(initial=0.)))
    basis_exists=len(vb)==B.shape[1] and len(cb)==B.shape[0] and bool(np.isin(vb,[-3,-2,-1,0]).all()) and bool(np.isin(cb,[-1,0]).all())
    proof=rational_bound(B,e,pi,lo,hi,j,save)
    safe,combined=safe_bound(proof['rational_lower_bound'])
    gap=objective-proof['rational_lower_bound']
    passed=bool(primal['PASS'] and dual_sign<=1e-8 and basis_residual<=1e-8 and basis_exists and np.isfinite(kappa) and kappa<=1e12 and -1e-8<=gap<=1e-6 and safe<=objective+1e-8)
    return dict(PASS=passed,primal_full_rows_audit=primal,dual_sign_residual=dual_sign,
                basis_stationarity_residual=basis_residual,basis_exists=basis_exists,Kappa=kappa,
                objective=objective,primal_minus_rational_lower_bound=gap,
                certified_conditional_lower_bound=combined,L_safe=safe if passed else None,
                fixed_safety_epsilon=1e-8,selected_bound_column=j,
                selected_original_binary_name=str(d['names'][j]),only_selected_bounds_changed=True,
                numerical_policy_SHA=sha(OUT/'NUMERICAL_POLICY.json'),**proof)

def farkas(A,d,m,lo,hi,j,save):
    # Gurobi lambda has <= orientation. Negating it provides sign-valid pi.
    lam=np.asarray(m.getAttr('FarkasDual'))
    zero=dict(d,objective=np.zeros(A.shape[1]),constant=np.array(0.))
    cert=rational_bound(A,zero,-lam,lo,hi,j,save)
    proven=cert['rational_lower_bound']>0
    return dict(PASS=proven,exact_infeasible_state_fix=proven,
                explanation='Sign-valid multipliers prove 0 >= positive rational lower bound for every point satisfying original rows and selected y=1 bounds, a contradiction.',
                independently_reconstructed_without_solver=True,FarkasProof=float(m.FarkasProof),**cert)
