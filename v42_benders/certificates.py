"""Certificates evaluated exactly on stored IEEE coefficients.

Rational residual compensation uses only existing finite bounds. An unbounded
required support, weak margin, bad sign, or altered payload never becomes a cut.
"""
from fractions import Fraction as F
import math
import numpy as np
from .canonical import digest_arrays

class Uncertifiable(ValueError): pass

def q(v):
    if not math.isfinite(float(v)): raise Uncertifiable('NONFINITE_CERTIFICATE')
    return F.from_float(float(v))

def weighted(matrix, weights):
    # Independent exact arithmetic, not the BLAS product used by the solver.
    out={}
    for i in np.flatnonzero(weights):
        w=q(weights[i])
        for k in range(matrix.indptr[i],matrix.indptr[i+1]):
            j=int(matrix.indices[k]);out[j]=out.get(j,F(0))+w*q(matrix.data[k])
    return {j:v for j,v in out.items() if v}

def support(residual,lower,upper):
    terms={};total=F(0)
    for j,r in residual.items():
        bound=lower[j] if r>0 else upper[j]
        if not math.isfinite(float(bound)): raise Uncertifiable('UNBOUNDED_STATIONARITY_SUPPORT')
        terms[j]=r*q(bound);total+=terms[j]
    return total,terms

def round_affine(intercept,coeff,xlo,xhi,direction):
    rounded=np.zeros(len(xlo));error=F(0)
    for j,a in coeff.items():
        rounded[j]=float(a);delta=q(rounded[j])-a
        # direction=+1 -> affine is rounded above; -1 -> below.
        error+=min(delta*q(xlo[j]),delta*q(xhi[j])) if direction>0 else max(delta*q(xlo[j]),delta*q(xhi[j]))
    target=intercept-error
    ri=math.nextafter(float(target),math.inf if direction>0 else -math.inf)
    if (q(ri)-target)*direction<0:raise Uncertifiable('OUTWARD_ROUNDING')
    return ri,rounded

def create(can,multipliers,x,kind,status,iteration=0,recourse_value=None):
    if status not in [2,3] or (kind=='feasibility' and status!=3) or (kind=='optimality' and status!=2):
        raise Uncertifiable('NO_CUT_FOR_NONTERMINAL_STATUS')
    w=np.asarray(multipliers,dtype=float);x=np.asarray(x,dtype=float)
    if len(w)!=len(can.b) or not np.isfinite(w).all():raise Uncertifiable('MULTIPLIER_AXIS')
    if kind not in ['feasibility','optimality']:raise Uncertifiable('CUT_TYPE')
    if (kind=='feasibility' and np.any(w<0)) or (kind=='optimality' and np.any(w>0)):
        raise Uncertifiable('MULTIPLIER_SIGN')
    ay=weighted(can.A,w);bx=weighted(can.B,w)
    if kind=='feasibility':r=ay
    else:
        r={j:q(v)-ay.get(j,F(0)) for j,v in enumerate(can.c) if v or j in ay}
        r={j:v for j,v in r.items() if v}
    residual=max([abs(float(v)) for v in r.values()]+[0.])
    if residual>1e-7:raise Uncertifiable('STATIONARITY_RESIDUAL')
    correction,terms=support(r,can.lower,can.upper)
    raw=sum((q(w[i])*q(can.b[i]) for i in np.flatnonzero(w)),F(0))
    intercept=raw-correction if kind=='feasibility' else raw+correction+q(can.objective_constant)
    coef={j:-a for j,a in bx.items()}
    ri,rc=round_affine(intercept,coef,can.xlower,can.xupper,1 if kind=='feasibility' else -1)
    source=ri+float(rc@x)
    exact_source=intercept+sum((a*q(x[j]) for j,a in coef.items()),F(0))
    margin=-source if kind=='feasibility' else None
    tight=None if recourse_value is None else float(recourse_value-source)
    if kind=='feasibility' and (margin<=1e-8 or exact_source>=0):raise Uncertifiable('NO_STRICT_FARKAS_MARGIN')
    if kind=='optimality' and (tight is None or abs(tight)>1e-7):raise Uncertifiable('DUAL_SOURCE_NOT_TIGHT')
    n=len(can.source_rows)
    bh=sum((q(w[i])*q(can.b[i]) for i in np.flatnonzero(w[n:])+n),F(0))
    equality_rows=np.flatnonzero(can.signs==-1) # includes reversed >; source provenance disambiguates externally
    row=dict(iteration=iteration,type=kind,source_x_hash=digest_arrays(x),recourse_status=status,
        dual_ray_hash=digest_arrays(w),stationarity_residual=residual,exact_bound_correction=str(correction),
        bound_row_contribution=str(bh),bound_correction_terms={str(j):str(v) for j,v in terms.items()},
        equality_reverse_row_mass=float(np.sum(abs(w[equality_rows]))),
        exact_intercept=str(intercept),intercept=ri,source_value=source,source_exact_value=str(exact_source),
        violation_at_source=margin,source_tightness=tight,recourse_optimum=recourse_value,
        sparsity=int(np.count_nonzero(rc)),active_inactive_history=[],
        canonical_original_hash=can.original_hash,proof='EXACT_RATIONAL_BOUND_COMPENSATED_OUTWARD_ROUNDED')
    row['cut_hash']=digest_arrays(np.array([ri]),rc)
    row['id']=kind.upper()+'-'+row['cut_hash'][:20]
    return dict(record=row,coefficients=rc,multipliers=w.copy(),source_x=x.copy())

def verify(can,cut,known=()):
    r=cut['record']
    recomputed=create(can,cut['multipliers'],cut['source_x'],r['type'],r['recourse_status'],
        r['iteration'],r['recourse_optimum'])
    expected=recomputed['record']
    for k in expected:
        if k=='active_inactive_history':continue
        if r.get(k)!=expected[k]:raise Uncertifiable('ALTERED_CERTIFICATE_'+k)
    if not np.array_equal(cut['coefficients'],recomputed['coefficients']):raise Uncertifiable('ALTERED_B_COEFFICIENT')
    maximum=0.
    for x,optimum in known:
        value=r['intercept']+float(cut['coefficients']@x)
        violation=-value if r['type']=='feasibility' else value-optimum
        maximum=max(maximum,violation)
        if violation>1e-7:raise Uncertifiable('KNOWN_FEASIBLE_ASSIGNMENT_EXCLUDED')
    return dict(PASS=True,known_feasible_assignments=len(known),maximum_violation=maximum,
        independent_exact_matrix_products=True,exact_bound_compensation=True,outward_rounding=True)
