"""Exact weak duality; raw RMP ObjVal is never used as a lower bound."""
from .common import *
from fractions import Fraction as F
import numpy as np
from v42_disjunctive.certificate import down

def global_dual(A,d,pi,lo,hi):
    assert np.all(pi[d['sense']=='<']<=0) and np.all(pi[d['sense']=='>']>=0),'RAW_PI_SIGN_INVALID'
    residual={int(j):F(float(d['objective'][j])) for j in np.flatnonzero(d['objective'])}
    rhs=F(float(d['constant']))
    for i in np.flatnonzero(pi):
        p=F(float(pi[i]));rhs+=p*F(float(d['rhs'][i]))
        a,b=A.indptr[i:i+2]
        for j,c in zip(A.indices[a:b],A.data[a:b]):residual[int(j)]=residual.get(int(j),F(0))-p*F(float(c))
    penalty=sum((q*F(float(lo[j] if q>=0 else hi[j])) for j,q in residual.items()),F(0));value=rhs+penalty
    return value,dict(exact_numerator=str(value.numerator),exact_denominator=str(value.denominator),rhs_objective=float(rhs),global_residual_box_term=float(penalty),nonzero_residual_columns=sum(q!=0 for q in residual.values()),sign_projection=False,all_free_coordinates_have_proven_enclosures=True)
def corrected(global_value,alpha,bounds):
    assert len(alpha)==len(bounds)==4 and all(v is not None for v in bounds)
    beta=[F(down(F(float(v))-F(EPS))) for v in bounds];delta=[min(F(0),v) for v in beta]
    value=global_value+sum((F(float(a))+d for a,d in zip(alpha,delta)),F(0))
    return down(value),value,beta,delta
def decide(L,U):
    if L is not None and L>=T_MATERIAL:return 'PROVEN_MATERIAL'
    if U is not None and U<=T_MATERIAL:return 'PROVEN_NONMATERIAL'
    return 'INCONCLUSIVE'
def receipt(iteration,round_number,pi,alpha,key,global_value,global_proof,prices,U,master,blocks):
    bounds=[p['ObjBound'] if p['valid_bound'] else None for p in prices]
    if any(v is None for v in bounds):return dict(iteration=iteration,round=round_number,dual_SHA=key,certified=False,L_corr=None,U_RMP=U,materiality=decide(None,U),reason='FOUR_FINITE_VALID_SAME_DUAL_BOUNDS_REQUIRED')
    assert all(p['dual_SHA']==key for p in prices)
    L,value,beta,delta=corrected(global_value,alpha,bounds)
    corrected_rc=[]
    from v42_dw_root.run import exact_rc
    for c in master.column_data:
        m=c['unit'];corrected_rc.append(exact_rc(blocks[m],c['x'],pi,alpha[m])-delta[m])
    smallest=min(corrected_rc);assert smallest>=-F(EPS),'CORRECTED_RETAINED_COLUMN_SIGN_FAIL'
    assert L<=U,'CERTIFIED_INTERVAL_CONTRADICTION'
    return dict(iteration=iteration,round=round_number,dual_SHA=key,certified=True,L_corr=L,U_RMP=U,
       beta_raw=bounds,beta_safe=list(map(float,beta)),delta=list(map(float,delta)),alpha_corrected=[float(F(float(a))+d) for a,d in zip(alpha,delta)],
       exact_numerator=str(value.numerator),exact_denominator=str(value.denominator),exact_global_proof=global_proof,
       textbook_zRMP_plus_delta_diagnostic=float(F(U)+sum(delta)),exact_RMP_dual_minus_native_ObjVal=float(global_value+sum(map(lambda a:F(float(a)),alpha))-F(U)),
       retained_corrected_rc_min=float(smallest),all_retained_corrected_RC_audit_PASS=True,
       materiality=decide(L,U),pricing_receipts=[p['receipt'] for p in prices],
       lower_scope='Exact global dual arithmetic plus native full-domain MIP ObjBound authority with fixed1e-8 safety.',upper_scope='Native OPTIMAL restricted LP with registered all-original-row affine1e-6 / physical-bound-route1e-8 audit; not an integer UB.')
