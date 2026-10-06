from copy import deepcopy
from v42_m_stage_root.policy import convergence_certificate

def evidence():
    return dict(certified=True,dual_SHA='true'),[dict(unit=m,type='FINAL_CERTIFICATION',native_status=2,
        valid_bound=True,valid_point=True,full_original_domain=True,stabilized_discovery=False,
        dual_SHA='true',true_dual_SHA='true',ObjBound=0.,rc_inc=0.) for m in range(4)]

def test_only_four_exact_same_true_dual_nonnegative_certificates_converge():
    c,p=evidence();assert convergence_certificate(c,p,'true')
    for field,value in [('type','DISCOVERY'),('native_status',9),('valid_bound',False),
        ('full_original_domain',False),('stabilized_discovery',True),('dual_SHA','other'),
        ('true_dual_SHA','other'),('ObjBound',-1e-7),('rc_inc',-1e-7)]:
        q=deepcopy(p);q[0][field]=value
        assert not convergence_certificate(c,q,'true'),field
    assert not convergence_certificate(c,p[:3],'true')
    q=deepcopy(p);q[3]['unit']=2;assert not convergence_certificate(c,q,'true')
    assert not convergence_certificate(dict(c,certified=False),p,'true')

def test_engineering_negative_rc_tolerances_cannot_converge():
    c,p=evidence()
    for value in (-.01,-.001,-1e-6):
        q=deepcopy(p)
        for r in q:r.update(ObjBound=value,rc_inc=value)
        assert not convergence_certificate(c,q,'true')
