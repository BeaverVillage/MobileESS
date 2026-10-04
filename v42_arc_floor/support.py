"""Actual Fraction weak duality on original bounds; infinite support is rejected.

Only equality multipliers are repaired. Reverse original triangular bindings
annihilate every free-coordinate residual exactly; no artificial bounds are
installed or used in the support-function certificate.
"""
from fractions import Fraction as F
import numpy as np
from v42_disjunctive.certificate import down

def finite_bound(x):return bool(np.isfinite(x) and abs(x)<1e90)

def support(q,lower,upper):
    value=F(0)
    for j,c in q.items():
        if not c:continue
        endpoint=lower[j] if c>0 else upper[j]
        if not finite_bound(endpoint):raise ValueError('INFINITE_SUPPORT_AT_COORDINATE_'+str(j))
        value+=c*F(float(endpoint))
    return value

def residual(A,d,pi):
    q={int(j):F(float(d['objective'][j])) for j in np.flatnonzero(d['objective'])}
    rhs=F(float(d['constant']))
    for i,p in pi.items():
        rhs+=p*F(float(d['rhs'][i]));a,b=A.indptr[i:i+2]
        for j,c in zip(A.indices[a:b],A.data[a:b]):q[int(j)]=q.get(int(j),F(0))-p*F(float(c))
    return q,rhs

def certify(A,d,native_pi,pivots=(),save=None):
    pi={int(i):F(float(v)) for i,v in enumerate(native_pi) if v}
    projected=0
    for i,p in list(pi.items()):
        if d['sense'][i]=='<' and p>0 or d['sense'][i]=='>' and p<0:pi[i]=F(0);projected+=1
    q,rhs=residual(A,d,pi);raw_free=max((abs(v) for j,v in q.items() if not finite_bound(d['lower'][j]) or not finite_bound(d['upper'][j])),default=F(0))
    free={j for j in range(A.shape[1]) if not finite_bound(d['lower'][j]) or not finite_bound(d['upper'][j])}
    prior=set();pivotrows=[]
    for i,j in pivots:
        i=int(i);j=int(j);assert j in free and j not in prior and d['sense'][i]=='='
        a,b=A.indptr[i:i+2];indices=A.indices[a:b];values=A.data[a:b]
        assert j in indices and all(int(k)==j or int(k) not in free or int(k) in prior for k in indices)
        coefficient=F(float(values[np.flatnonzero(indices==j)[0]]));assert coefficient
        prior.add(j);pivotrows.append((i,j,coefficient))
    repairs=[]
    for i,j,coefficient in reversed(pivotrows):
        change=q.get(j,F(0))/coefficient
        if change:
            pi[i]=pi.get(i,F(0))+change;rhs+=change*F(float(d['rhs'][i]));a,b=A.indptr[i:i+2]
            for k,c in zip(A.indices[a:b],A.data[a:b]):q[int(k)]=q.get(int(k),F(0))-change*F(float(c))
            repairs.append((i,j,change))
        assert q.get(j,F(0))==0
    # A genuinely free nonzero coefficient must never be multiplied by a
    # pseudo-finite Gurobi infinity. One-sided infinities are sign-checked too.
    penalty=support(q,d['lower'],d['upper']);value=rhs+penalty
    assert all(d['sense'][i]=='=' or d['sense'][i]=='<' and v<=0 or d['sense'][i]=='>' and v>=0 for i,v in pi.items())
    artifact=None
    if save:
        rows=sorted(i for i,p in pi.items() if p);np.savez_compressed(save,rows=rows,numerators=np.array([str(pi[i].numerator) for i in rows]),denominators=np.array([str(pi[i].denominator) for i in rows]));artifact=str(save)
    return dict(PASS=True,L_dual_support=down(value),exact_numerator=str(value.numerator),exact_denominator=str(value.denominator),exact_rational=True,raw_free_stationarity_max=float(raw_free),raw_pi_sign_projections=projected,equality_multiplier_repairs=len(repairs),pivot_rows=len(pivotrows),repaired_free_stationarity_max=float(max((abs(q.get(j,F(0))) for j in free),default=F(0))),nonzero_stationarity_coordinates=sum(v!=0 for v in q.values()),support_term=float(penalty),rhs_term=float(rhs),original_bounds_only=True,derived_pseudo_bounds_used=False,infinite_support_rejected=True,equality_repair_original_matrix_unchanged=True,weak_duality_proof='For min c*x+c0 and sign-valid pi, c*x+c0 >= c0+pi*b+(c-A.T*pi)*x. Equality multipliers are unrestricted. Each original interval support is minimized exactly; nonzero coefficients requiring an infinite endpoint invalidate the certificate. Reverse triangular original equalities set all free residuals to exact zero. Downward rounding preserves the rational bound.',dual_artifact=artifact)
