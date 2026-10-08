"""Independent CSR-row accumulation of a scalar exact finite-box LB.

PR185 constructs the certificate by CSC columns. This checker independently
accumulates CSR rows with exact integer dyadics, then checks EVERY bound term.
It neither optimizes nor constructs any additional scientific Cut.
"""
from v42_physics_redesign.common import *
from fractions import Fraction as F
import gzip

def ratio(v):
    n,q=float(v).as_integer_ratio();return n,q.bit_length()-1

def verify_payload(A,d,pi,p):
    assert p['Y']==[] and p['beta_integer']==[]
    assert np.isfinite(pi).all() and np.isfinite(d['lower']).all() and np.isfinite(d['upper']).all()
    assert not np.any(((d['sense']=='<')&(pi>0))|((d['sense']=='>')&(pi<0)))
    be=p['beta_exponent'];ae=p['alpha_exponent'];ue=ae-be;assert ue>=0
    residual=[]
    for value in d['objective']:
        n,e=ratio(value);assert be>=e;residual.append(n<<(be-e))
    n,e=ratio(d['constant']);assert be>=e;row_value=n<<(be-e)
    for i,value in enumerate(pi):
        if value==0:continue
        pn,pe=ratio(value);bn,be_rhs=ratio(d['rhs'][i]);assert be>=pe+be_rhs
        row_value+=(pn*bn)<<(be-pe-be_rhs)
        for k in range(A.indptr[i],A.indptr[i+1]):
            an,ce=ratio(A.data[k]);assert be>=pe+ce
            residual[int(A.indices[k])]-=(pn*an)<<(be-pe-ce)
    alpha=row_value<<ue;support=p['original_nonmaster_bound_support'];assert len(support)==A.shape[1]
    for j,r in enumerate(residual):
        bound=d['lower'][j] if r>=0 else d['upper'][j]
        bn,ex=ratio(bound);assert ue>=ex
        term=(r*bn)<<(ue-ex);alpha+=term
        assert support[j]==[j,r>=0,str(term)],('BOUND_SUPPORT_MISMATCH',j)
    assert alpha==int(p['alpha_integer']),'EXACT_ALPHA_MISMATCH'
    exact=F(alpha,1<<ae)
    assert F.from_float(float(p['delivered_intercept']))<=exact,'UNSAFE_OUTWARD_LB'
    return exact

def verify_certificate(A,d,accepted):
    start=time.perf_counter()
    with gzip.open(accepted['exact_path'],'rt',encoding='utf-8') as f:p=json.load(f)
    with np.load(accepted['npz_path']) as f:pi=f['pi'].copy()
    exact=verify_payload(A,d,pi,p)
    assert exact==F(accepted['exact_alpha'])
    outward=float(exact)
    if F.from_float(outward)>exact:outward=float(np.nextafter(outward,-np.inf))
    return dict(PASS=True,method='Independent CSR rows versus producer CSC columns; exact integer dyadic accumulation',
        exact_alpha=str(exact),certified_LB=outward,all_rows=A.shape[0],all_columns=A.shape[1],
        all_original_finite_bound_terms_checked=A.shape[1],valid_for_original_integer_domain=True,
        original_objective_used=True,sign_cone_PASS=True,global_transport_checked=True,
        exact_payload_SHA256=sha(accepted['exact_path']),multiplier_payload_SHA256=sha(accepted['npz_path']),
        new_native_calls=0,controller_wall_seconds=time.perf_counter()-start)

def tests():
    # Analytic: min w, .75*y+w=1, 0<=y,w<=1 => optimum .25.
    A=sparse.csr_matrix([[.75,1.]])
    d=dict(objective=np.array([0.,1.]),constant=np.array(0.),rhs=np.array([1.]),
        sense=np.array(['=']),lower=np.zeros(2),upper=np.ones(2))
    p=dict(Y=[],beta_integer=[],beta_exponent=3,alpha_exponent=4,alpha_integer='4',
        original_nonmaster_bound_support=[[0,False,'-12'],[1,True,'0']],delivered_intercept=.25)
    assert verify_payload(A,d,np.array([1.]),p)==F(1,4)
    rejected=0
    for altered in [dict(p,alpha_integer='5'),dict(p,delivered_intercept=.25000000000000006),
                    dict(p,original_nonmaster_bound_support=[[0,False,'0'],[1,True,'0']])]:
        try:verify_payload(A,d,np.array([1.]),altered)
        except AssertionError:rejected+=1
    try:verify_payload(A,dict(d,sense=np.array(['<'])),np.array([1.]),p)
    except AssertionError:rejected+=1
    assert rejected==4
    return dict(PASS=True,analytic_LB=.25,unsafe_alpha_intercept_bound_and_sign_mutations_rejected=4,native_calls=0)

if __name__=='__main__':
    prior.forbid_optimize();write(REPORTS/'INDEPENDENT_CERTIFICATE_CHECKER_TESTS.json',tests())
    print('INDEPENDENT_CHECKER_TESTS_PASS optimize=0',flush=True)
