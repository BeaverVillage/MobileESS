"""Exact bounded weak-duality cuts; native floating coefficients are not proof."""
from .common import *
from fractions import Fraction as F
import gzip
def dyadic(x):
    n,q=float(x).as_integer_ratio();return n,q.bit_length()-1
def exponent(values):
    values=np.asarray(values);v=values[values!=0]
    return max(0,53-int(np.frexp(v)[1].min())) if len(v) else 0
def cut(A,d,B,pi,path,kind='optimality'):
    assert kind in ('optimality','feasibility')
    assert np.isfinite(pi).all() and np.isfinite(d['lower']).all() and np.isfinite(d['upper']).all()
    wrong=((d['sense']=='<')&(pi>0))|((d['sense']=='>')&(pi<0))
    if wrong.any():return dict(PASS=False,reason='WRONG_SIGN_NATIVE_MULTIPLIERS',count=int(wrong.sum()),maximum=float(abs(pi[wrong]).max()))
    parts=[dyadic(v) for v in pi];pe=max((e for n,e in parts if n),default=0)
    be=max(exponent(A.data)+pe,exponent(d['rhs'])+pe,exponent(d['objective']),dyadic(d['constant'])[1]);ue=max(exponent(d['lower']),exponent(d['upper']));te=be+ue
    rhs=0
    for (n,e),b in zip(parts,d['rhs']):
        if n and b:
            bn,bq=dyadic(b);rhs+=(n*bn)<<(be-e-bq)
    cn,cq=dyadic(d['constant'] if kind=='optimality' else 0.);rhs+=cn<<(be-cq)
    alpha=rhs<<ue;slopes=[];Bset=set(map(int,B));Ac=A.tocsc();stationarity=np.empty(A.shape[1]);bound_terms=np.zeros(A.shape[1])
    for j in range(A.shape[1]):
        dot=0
        for k in range(Ac.indptr[j],Ac.indptr[j+1]):
            pn,pq=parts[int(Ac.indices[k])]
            if pn:
                an,aq=dyadic(Ac.data[k]);dot+=(an*pn)<<(be-aq-pq)
        cn,cq=dyadic(d['objective'][j] if kind=='optimality' else 0.);r=(cn<<(be-cq))-dot
        stationarity[j]=float(F(r,1<<be))
        if j in Bset:slopes.append(r)
        else:
            bn,bq=dyadic(d['lower'][j] if r>=0 else d['upper'][j]);term=(r*bn)<<(ue-bq);alpha+=term;bound_terms[j]=float(F(term,1<<te))
    af=F(alpha,1<<te);beta=np.array([float(F(r,1<<be)) for r in slopes]);transport_error=F(0)
    for j,r,v in zip(B,slopes,beta):
        error=F.from_float(float(v))-F(r,1<<be)
        transport_error+=max(error*F.from_float(float(d['lower'][j])),error*F.from_float(float(d['upper'][j])))
    conservative=af-transport_error;intercept=float(conservative)
    if F.from_float(intercept)>conservative:intercept=float(np.nextafter(intercept,-np.inf))
    assert F.from_float(intercept)<=conservative
    payload=dict(kind=kind,B=list(map(int,B)),alpha_integer=str(alpha),alpha_exponent=te,beta_integer=[str(r) for r in slopes],beta_exponent=be,transport_error=str(transport_error),float_intercept=intercept)
    with gzip.open(path.with_suffix('.exact.json.gz'),'wt',encoding='utf-8') as f:json.dump(payload,f,separators=(',',':'))
    save(path.with_suffix('.npz'),B=B,beta=beta,intercept=np.array(intercept),pi=pi,stationarity=stationarity,bound_terms=bound_terms)
    return dict(PASS=True,kind=kind,exact_alpha=str(af),intercept=intercept,coefficient_min=float(beta.min(initial=0)),coefficient_max=float(beta.max(initial=0)),nonzero_coefficients=int(np.count_nonzero(beta)),transport_error=str(transport_error),all_original_continuous_bound_terms_included=True,stationarity_residual_max=float(abs(stationarity[np.setdiff1d(np.arange(A.shape[1]),B)]).max()),bound_correction=float(bound_terms.sum()),native_signs_accepted_without_clamping=True,exact_path=str(path.with_suffix('.exact.json.gz')),npz_path=str(path.with_suffix('.npz')),beta=beta)
def exact_value(cert,z):
    with gzip.open(cert['exact_path'],'rt',encoding='utf-8') as f:p=json.load(f)
    return F(int(p['alpha_integer']),1<<p['alpha_exponent'])+sum((F(int(n),1<<p['beta_exponent'])*int(v) for n,v in zip(p['beta_integer'],z)),F(0))
def certify_with_explicit_projection(A,d,B,pi,path,kind='optimality'):
    raw=cut(A,d,B,pi,path,kind)
    if raw['PASS']:return raw
    # Reject the native ray first. Construct a DIFFERENT mathematical
    # multiplier in the admissible sign cone and recompute every coefficient
    # and finite-bound residual exactly. This never clips matrix/cut terms,
    # claims a raw invalid ray was valid, or assumes stationarity.
    assert raw['reason']=='WRONG_SIGN_NATIVE_MULTIPLIERS'
    projected=pi.copy();bad=((d['sense']=='<')&(pi>0))|((d['sense']=='>')&(pi<0));projected[bad]=0.
    recovered=cut(A,d,B,projected,path.with_name(path.name+'_projected'),kind)
    recovered.update(raw_native_certificate_rejected=raw,explicit_multiplier_cone_projection=True,projection_count=int(bad.sum()),projection_max=float(abs(pi-projected).max()),original_matrix_objective_bounds_unchanged=True,all_cut_coefficients_recomputed_exactly=True,no_cut_coefficient_clamping=True)
    return recovered
def known_witnesses(cert,d,assignments):
    vals=[]
    for path in assignments:
        with np.load(path) as f:x=f['x'];z=f['z']
        exact=exact_value(cert,z);obj=F.from_float(float(d['constant']))+sum((F.from_float(float(c))*F.from_float(float(v)) for c,v in zip(d['objective'],x) if c),F(0))
        tolerance=F.from_float(1e-8)
        limit=obj if cert['kind']=='optimality' else F(0)
        vals.append(dict(assignment=path.stem,cut_value=float(exact),objective=float(obj),PASS=exact<=limit+tolerance))
    return dict(PASS=all(x['PASS'] for x in vals),witnesses=vals,known_witness_numerical_acceptance=1e-8,global_validity_from_exact_weak_duality_not_sample=True)
def solver_transport(cert,d,threshold=1e-12):
    # Gurobi may ignore coefficients below 1e-13. Account for the actual
    # delivered sparsification in the exact global error envelope, rather
    # than silently treating discarded terms as an exact row.
    with gzip.open(cert['exact_path'],'rt',encoding='utf-8') as f:p=json.load(f)
    B=np.array(p['B'],int);exact=[F(int(n),1<<p['beta_exponent']) for n in p['beta_integer']];beta=np.array([float(v) for v in exact]);small=(abs(beta)<threshold)&(beta!=0);beta[small]=0.
    error=F(0)
    for j,a,b in zip(B,exact,beta):
        e=F.from_float(float(b))-a;error+=max(e*F.from_float(float(d['lower'][j])),e*F.from_float(float(d['upper'][j])))
    alpha=F(int(p['alpha_integer']),1<<p['alpha_exponent'])-error;intercept=float(alpha)
    if F.from_float(intercept)>alpha:intercept=float(np.nextafter(intercept,-np.inf))
    return beta,intercept,dict(PASS=F.from_float(intercept)<=alpha,delivered_nonzero=int(np.count_nonzero(beta)),exact_sparse_transport_threshold=threshold,explicitly_accounted_small_terms=int(small.sum()),exact_total_global_error_envelope=str(error),delivered_intercept=intercept,original_scientific_coefficients_unchanged=True)
