"""Bounded weak-duality proof on original binary AND continuous coordinates.

No native optimization occurs here. All source doubles are exact dyadics.
For row multipliers pi with pi<=0 on <= and pi>=0 on >=,
 L(y)=c0+pi*b+(cY-AY.T*pi)*y+min_[lW,uW](cW-AW.T*pi)*w
 is a lower bound on the ORIGINAL objective. For a feasibility certificate,
 set c=c0=0 in this mathematical proof only; every feasible point has L<=0.
"""
from .common import *
from fractions import Fraction as F
import gzip

def dyadic(value):
    n,q=float(value).as_integer_ratio();return n,q.bit_length()-1

def exponent(values):
    values=np.asarray(values);v=values[values!=0]
    return max(0,53-int(np.frexp(v)[1].min())) if len(v) else 0

def payload(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:return json.load(f)

def evaluate(p,values,delivered=False):
    # F.from_float is deliberate. int(value) would invalidate continuous f.
    values=np.asarray(values);assert len(values)==len(p['Y']) and np.isfinite(values).all()
    if delivered:
        a=F.from_float(p['delivered_intercept']);coeff=map(F.from_float,p['delivered_beta'])
    else:
        a=F(int(p['alpha_integer']),1<<p['alpha_exponent'])
        coeff=(F(int(n),1<<p['beta_exponent']) for n in p['beta_integer'])
    return a+sum((b*F.from_float(float(v)) for b,v in zip(coeff,values)),F(0))

def construct(A,d,Y,pi,path,kind='optimality'):
    assert kind in ('optimality','feasibility')
    assert len(set(map(int,Y)))==len(Y) and np.array_equal(Y,np.sort(Y))
    assert len(pi)==A.shape[0] and np.isfinite(pi).all()
    assert np.isfinite(d['lower']).all() and np.isfinite(d['upper']).all()
    wrong=((d['sense']=='<')&(pi>0))|((d['sense']=='>')&(pi<0))
    if wrong.any():return dict(PASS=False,reason='WRONG_SIGN_NATIVE_MULTIPLIERS',count=int(wrong.sum()),maximum=float(abs(pi[wrong]).max()),silent_correction=False)
    c=d['objective'] if kind=='optimality' else np.zeros(A.shape[1]);c0=float(d['constant']) if kind=='optimality' else 0.
    parts=[dyadic(v) for v in pi];pe=max((e for n,e in parts if n),default=0)
    be=max(exponent(A.data)+pe,exponent(d['rhs'])+pe,exponent(c),dyadic(c0)[1])
    ue=max(exponent(d['lower']),exponent(d['upper']));te=be+ue
    rhs=0
    for (n,e),b in zip(parts,d['rhs']):
        if n and b:
            bn,bq=dyadic(b);rhs+=(n*bn)<<(be-e-bq)
    cn,cq=dyadic(c0);rhs+=cn<<(be-cq)
    alpha=rhs<<ue;slopes=[];Yset=set(map(int,Y));Ac=A.tocsc();stationarity=np.empty(A.shape[1]);bound_terms=np.zeros(A.shape[1]);support=[]
    for j in range(A.shape[1]):
        dot=0
        for k in range(Ac.indptr[j],Ac.indptr[j+1]):
            pn,pq=parts[int(Ac.indices[k])]
            if pn:
                an,aq=dyadic(Ac.data[k]);dot+=(an*pn)<<(be-aq-pq)
        cn,cq=dyadic(c[j]);r=(cn<<(be-cq))-dot
        stationarity[j]=float(F(r,1<<be))
        if j in Yset:slopes.append(r)
        else:
            bn,bq=dyadic(d['lower'][j] if r>=0 else d['upper'][j]);term=(r*bn)<<(ue-bq);alpha+=term;bound_terms[j]=float(F(term,1<<te));support.append((j,r>=0,str(term)))
    exact=[F(r,1<<be) for r in slopes];beta=np.array([float(v) for v in exact])
    small=(abs(beta)<1e-12)&(beta!=0);beta[small]=0.
    error=F(0)
    for j,a,b in zip(Y,exact,beta):
        e=F.from_float(float(b))-a
        error+=max(e*F.from_float(float(d['lower'][j])),e*F.from_float(float(d['upper'][j])))
    af=F(alpha,1<<te);safe=af-error;intercept=float(safe)
    if F.from_float(intercept)>safe:intercept=float(np.nextafter(intercept,-np.inf))
    assert F.from_float(intercept)<=safe
    p=dict(kind=kind,Y=list(map(int,Y)),alpha_integer=str(alpha),alpha_exponent=te,beta_integer=[str(r) for r in slopes],beta_exponent=be,original_nonmaster_bound_support=support,delivered_intercept=intercept,delivered_beta=beta.tolist(),global_transport_error_envelope=str(error),outward_intercept_loss=str(safe-F.from_float(intercept)),transport_valid_for_entire_original_box=True,f_original_type='C',continuous_values_never_integer_cast=True)
    with gzip.open(path.with_suffix('.exact.json.gz'),'wt',encoding='utf-8') as f:json.dump(p,f,separators=(',',':'))
    save(path.with_suffix('.npz'),Y=Y,beta=beta,intercept=np.array(intercept),pi=pi,stationarity=stationarity,bound_terms=bound_terms)
    return dict(PASS=True,kind=kind,exact_path=str(path.with_suffix('.exact.json.gz')),npz_path=str(path.with_suffix('.npz')),exact_alpha=str(af),exact_beta_exponent=be,exact_support_count=len(support),all_original_nonmaster_finite_bounds_included=True,original_binary_bounds_and_continuous_f_bounds_used=True,sign_cone_PASS=True,transport_PASS=True,exact_total_global_error_envelope=str(error),outward_intercept_loss=p['outward_intercept_loss'],delivered_nonzero=int(np.count_nonzero(beta)),explicitly_accounted_small_terms=int(small.sum()),continuous_values_never_integer_cast=True,global_validity='Exact bounded weak duality over full original C3A; no restricted-domain bound claim',objective_used_for_certificate='original min-rho' if kind=='optimality' else 'zero mathematical separating functional; native objective remains original min-rho')

def certify(A,d,Y,pi,path,kind):
    raw=construct(A,d,Y,pi,path,kind)
    if raw['PASS']:return dict(raw_native_multiplier_certificate=raw,accepted=raw)
    # Explicit, separately stored mathematical multiplier. Raw result remains
    # rejected, not relabelled as an accepted native certificate.
    assert raw['reason']=='WRONG_SIGN_NATIVE_MULTIPLIERS'
    projected=pi.copy();bad=((d['sense']=='<')&(pi>0))|((d['sense']=='>')&(pi<0));projected[bad]=0.
    save(path.with_name(path.name+'_NEW_SIGN_CONE_MULTIPLIER').with_suffix('.npz'),pi=projected,raw_pi=pi,changed_rows=np.flatnonzero(bad))
    new=construct(A,d,Y,projected,path.with_name(path.name+'_NEW_SIGN_CONE'),kind)
    new.update(raw_rejected=True,new_mathematical_multiplier=True,projection_count=int(bad.sum()),projection_max=float(abs(pi-projected).max()),all_coefficients_and_bounds_recomputed=True,silent_native_multiplier_correction=False)
    return dict(raw_native_multiplier_certificate=raw,new_mathematical_multiplier_certificate=new,accepted=new if new['PASS'] else None)

def verify_witnesses(cert,d,points):
    p=payload(cert['exact_path']);Y=np.array(p['Y']);results=[]
    for label,x in points:
        exact=evaluate(p,x[Y]);delivered=evaluate(p,x[Y],True)
        objective=F.from_float(float(d['constant']))+sum((F.from_float(float(c))*F.from_float(float(v)) for c,v in zip(d['objective'],x) if c),F(0))
        limit=objective if cert['kind']=='optimality' else F(0)
        results.append(dict(label=label,exact_value=float(exact),delivered_value=float(delivered),objective=float(objective),transport_pointwise_PASS=delivered<=exact,PASS=delivered<=exact and exact<=limit+F.from_float(1e-8)))
    return dict(PASS=all(r['PASS'] for r in results),witnesses=results,known_feasible_point_residual_contract=1e-8,global_validity_proven_algebraically_not_inferred_from_samples=True)

def tests():
    # Independently known analytic LP: min w, y+w=1, 0<=y,w<=1.
    A=sparse.csr_matrix([[1.,1.]])
    d=dict(objective=np.array([0.,1.]),constant=np.array(0.),rhs=np.array([1.]),sense=np.array(['=']),lower=np.zeros(2),upper=np.ones(2),types=np.array(['C','C']))
    base=WORK/'artifacts/fixture';cert=construct(A,d,np.array([0]),np.array([1.]),base)
    p=payload(cert['exact_path']);checks=[]
    for val in (.25,.5,.75):
        checks.append(dict(f=val,expected=1.-val,exact=float(evaluate(p,[val])),PASS=evaluate(p,[val])==F.from_float(1.-val) and evaluate(p,[val],True)<=evaluate(p,[val])))
    bad=dict(d,sense=np.array(['<']));rejection=construct(A,bad,np.array([0]),np.array([1.]),WORK/'artifacts/fixture_bad')
    assert not rejection['PASS'] and rejection['reason']=='WRONG_SIGN_NATIVE_MULTIPLIERS'
    fd=dict(d,upper=np.array([1.,.25]));fc=construct(A,fd,np.array([0]),np.array([1.]),WORK/'artifacts/fixture_feasibility','feasibility');fp=payload(fc['exact_path'])
    assert evaluate(fp,[.5])==F(1,4) and evaluate(fp,[.75])==0
    # Tiny transported coefficient is explicitly removed, and its maximal
    # error over a CONTINUOUS [-2,3] box is fully charged to the intercept.
    tiny=sparse.csr_matrix([[2.**-45,1.]])
    td=dict(d,lower=np.array([-2.,0.]),upper=np.array([3.,1.]))
    tc=construct(tiny,td,np.array([0]),np.array([1.]),WORK/'artifacts/fixture_transport');tp=payload(tc['exact_path'])
    for value in (-2.,-.25,.5,3.):assert evaluate(tp,[value],True)<=evaluate(tp,[value])
    result=dict(PASS=all(v['PASS'] for v in checks),fractional_continuous_f_tests=checks,integer_cast_would_fail=True,invalid_sign_rejection=rejection,finite_bound_feasibility_fixture_PASS=True,sparse_continuous_box_transport_PASS=True,native_optimize_calls=0)
    write(REPORTS/'EXACT_KERNEL_TESTS.json',result);return result
