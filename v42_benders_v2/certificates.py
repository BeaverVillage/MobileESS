"""Exact bound-supported cuts; failed certificates never yield a cut."""
from fractions import Fraction as F
import numpy as np
from v42_benders.certificates import q, weighted, support, round_affine, Uncertifiable
from v42_benders.canonical import digest_arrays

def create(n, raw, kind):
    w=np.asarray(raw['multipliers'],dtype=float); x=np.asarray(raw['source_x'],dtype=float)
    if w.shape!=n.b.shape or not np.isfinite(w).all():raise Uncertifiable('MULTIPLIER_AXIS')
    if x.shape!=n.xlower.shape or not np.isfinite(x).all():raise Uncertifiable('SOURCE_AXIS')
    farkas=kind=='native_farkas';phase=kind=='phase1'
    if kind not in ['native_farkas','phase1','optimality']:raise Uncertifiable('CUT_KIND')
    if raw['status']!=(3 if farkas else 2):raise Uncertifiable('NONTERMINAL_SOURCE')
    sign=1 if farkas else -1
    if np.any(w[n.sense=='<']*sign<0) or np.any(w[n.sense=='>']*sign>0):raise Uncertifiable('MULTIPLIER_SIGN')
    ay=weighted(n.A,w); bx=weighted(n.B,w)
    r=ay if farkas else {j:q(0 if phase else n.c[j])-ay.get(j,F(0)) for j in range(len(n.yi)) if (not phase and n.c[j]) or j in ay}
    r={j:v for j,v in r.items() if v}; bound,terms=support(r,n.lower,n.upper)
    h=sum((q(w[i])*q(n.b[i]) for i in np.flatnonzero(w)),F(0))
    equality=sum((q(w[i])*q(n.b[i]) for i in np.flatnonzero((n.sense=='=')&(w!=0))),F(0))
    if farkas:
        intercept=h-bound;coef={j:-v for j,v in bx.items()};direction=1
        proof=bound-sum((q(w[i])*q(raw['solver_rhs'][i]) for i in np.flatnonzero(w)),F(0))
        if not np.isfinite(raw['farkas_proof']) or abs(float(proof)-raw['farkas_proof'])>1e-7*max(1.,abs(float(proof))):raise Uncertifiable('NATIVE_PROOF_MISMATCH')
    else:
        rc=np.asarray(raw['reduced_costs'])[:len(n.yi)]
        residual=np.array([float(r.get(j,F(0))) for j in range(len(n.yi))])
        if not np.isfinite(rc).all() or np.max(abs(rc-residual),initial=0)>1e-7*max(1.,np.max(abs(rc),initial=0)):raise Uncertifiable('REDUCED_COST_MISMATCH')
        if phase:
            weights=raw['weights'];aux=[]
            for i,s in enumerate(n.sense):
                if s in ['<','=']:aux.append(q(weights[i])+q(w[i]))
                if s in ['>','=']:aux.append(q(weights[i])-q(w[i]))
            if any(v<0 for v in aux):raise Uncertifiable('PHASE1_ARTIFICIAL_DUAL_INFEASIBLE')
            supplied=np.asarray(raw['reduced_costs'])[len(n.yi):]
            if len(supplied)!=len(aux) or np.max(abs(supplied-np.array(list(map(float,aux)))),initial=0)>1e-7:raise Uncertifiable('PHASE1_AUX_REDUCED_COST')
            intercept=-h-bound;coef=bx;direction=1
        else:intercept=h+bound+q(n.objective_constant);coef={j:-v for j,v in bx.items()};direction=-1
        proof=None
    ri,rcut=round_affine(intercept,coef,n.xlower,n.xupper,direction)
    exact_source=intercept+sum((v*q(x[j]) for j,v in coef.items()),F(0));source=ri+float(rcut@x)
    if farkas or phase:
        if -source<=1e-8 or exact_source>=-q(1e-8):raise Uncertifiable('NO_STRICT_SEPARATION')
    if not farkas:
        lower_at_source=-float(exact_source) if phase else float(exact_source)
        if abs(raw['objective']-lower_at_source)>1e-7*max(1.,abs(raw['objective'])):raise Uncertifiable('SOURCE_DUAL_NOT_TIGHT')
    record=dict(kind=kind,type='optimality' if kind=='optimality' else 'feasibility',
        intercept=ri,exact_intercept=str(intercept),exact_coefficients={str(j):str(v) for j,v in coef.items()},
        bound_contribution=str(bound),bound_terms={str(j):str(v) for j,v in terms.items()},
        row_contribution=str(h),equality_contribution=str(equality),source_value=source,source_exact=str(exact_source),
        strict_margin=-source if farkas or phase else None,native_proof_reconstructed=None if proof is None else float(proof),
        source_hash=n.source_hash,source_x_hash=digest_arrays(x),raw_vector_sha256=digest_arrays(w),
        raw_persistence=raw['persistence'],bound_completed_stationarity=0.,
        bound_support_finite=True,globally_outward_rounded=True)
    record['cut_hash']=digest_arrays(np.array([ri]),rcut)
    return dict(record=record,coefficients=rcut,raw=raw)
