"""Independent certificate checker; never invokes the cut generator.

Sparse COO grouping and exact affine domination independently check the sign
derivations. This checker can replay archived payloads after solver shutdown.
"""
from fractions import Fraction
import math
import numpy as np
from .certificates import Uncertifiable
from .canonical import digest_arrays

def rational(value):
    if not math.isfinite(float(value)):raise Uncertifiable('INDEPENDENT_NONFINITE')
    return Fraction(float(value))

def product(matrix,weights):
    active=np.flatnonzero(weights)
    coo=matrix[active].tocoo()
    terms={}
    for i,j,value in zip(coo.row,coo.col,coo.data):
        terms.setdefault(int(j),[]).append(rational(weights[active[i]])*rational(value))
    return {j:total for j,values in terms.items() if (total:=sum(values,Fraction()))}

def verify(can,cut,known=()):
    r=cut['record'];kind=r['type'];w=np.asarray(cut['multipliers']);x=np.asarray(cut['source_x']);a=np.asarray(cut['coefficients'])
    if kind not in ['feasibility','optimality']:raise Uncertifiable('INDEPENDENT_TYPE')
    if r['recourse_status']!=(3 if kind=='feasibility' else 2):raise Uncertifiable('INDEPENDENT_STATUS')
    if len(w)!=len(can.b) or len(x)!=len(can.xi) or len(a)!=len(can.xi):raise Uncertifiable('INDEPENDENT_AXES')
    if np.any(w<0) if kind=='feasibility' else np.any(w>0):raise Uncertifiable('INDEPENDENT_SIGN')
    ay=product(can.A,w);wx=product(can.B,w)
    residual=ay if kind=='feasibility' else {j:rational(can.c[j])-ay.get(j,Fraction()) for j in set(ay)|set(np.flatnonzero(can.c))}
    residual={j:v for j,v in residual.items() if v}
    maximum=max([abs(float(v)) for v in residual.values()]+[0.])
    if maximum>1e-7:raise Uncertifiable('INDEPENDENT_STATIONARITY')
    correction=Fraction();bound_terms={}
    for j,value in residual.items():
        bound=can.lower[j] if value>0 else can.upper[j]
        if not np.isfinite(bound):raise Uncertifiable('INDEPENDENT_INFINITE_SUPPORT')
        term=value*rational(bound);correction+=term;bound_terms[str(j)]=str(term)
    raw=sum((rational(value)*rational(can.b[i]) for i,value in enumerate(w) if value),Fraction())
    exact_intercept=raw-correction if kind=='feasibility' else raw+correction+rational(can.objective_constant)
    exact_coeff={j:-v for j,v in wx.items()}
    expected_coeff=np.zeros(len(x))
    for j,value in exact_coeff.items():expected_coeff[j]=float(value)
    if not np.array_equal(expected_coeff,a):raise Uncertifiable('INDEPENDENT_B_COEFFICIENT')
    errors=[rational(a[j])-exact_coeff.get(j,Fraction()) for j in range(len(a))]
    # Check global affine domination over the whole original x bound box.
    diff=rational(r['intercept'])-exact_intercept
    min_diff=diff;max_diff=diff;round_correction=Fraction()
    for j,delta in enumerate(errors):
        endpoints=[delta*rational(can.xlower[j]),delta*rational(can.xupper[j])]
        min_diff+=min(endpoints);max_diff+=max(endpoints)
        round_correction+=min(endpoints) if kind=='feasibility' else max(endpoints)
    if kind=='feasibility' and min_diff<0:raise Uncertifiable('INDEPENDENT_FEASIBILITY_ORIENTATION')
    if kind=='optimality' and max_diff>0:raise Uncertifiable('INDEPENDENT_OPTIMALITY_ORIENTATION')
    rounded=math.nextafter(float(exact_intercept-round_correction),math.inf if kind=='feasibility' else -math.inf)
    if r['intercept']!=rounded:raise Uncertifiable('INDEPENDENT_RHS')
    n=len(can.source_rows)
    bound_part=sum((rational(w[i])*rational(can.b[i]) for i in range(n,len(w)) if w[i]),Fraction())
    exact_source=exact_intercept+sum((v*rational(x[j]) for j,v in exact_coeff.items()),Fraction())
    source=r['intercept']+float(a@x)
    checks=dict(exact_bound_correction=str(correction),bound_correction_terms=bound_terms,
        bound_row_contribution=str(bound_part),exact_intercept=str(exact_intercept),
        source_exact_value=str(exact_source),source_value=source,stationarity_residual=maximum,
        source_x_hash=digest_arrays(x),dual_ray_hash=digest_arrays(w),canonical_original_hash=can.original_hash,
        cut_hash=digest_arrays(np.array([r['intercept']]),a),sparsity=int(np.count_nonzero(a)))
    for key,value in checks.items():
        if r.get(key)!=value:raise Uncertifiable('INDEPENDENT_PAYLOAD_'+key)
    if r['id']!=kind.upper()+'-'+checks['cut_hash'][:20]:raise Uncertifiable('INDEPENDENT_ID')
    if kind=='feasibility' and (source>=-1e-8 or exact_source>=0):raise Uncertifiable('INDEPENDENT_STRICT_MARGIN')
    if kind=='optimality' and (r['recourse_optimum'] is None or abs(r['recourse_optimum']-source)>1e-7):
        raise Uncertifiable('INDEPENDENT_SOURCE_TIGHTNESS')
    largest=0.
    for point,value in known:
        affine=r['intercept']+float(a@point)
        violation=-affine if kind=='feasibility' else affine-value
        largest=max(largest,violation)
        if violation>1e-7:raise Uncertifiable('INDEPENDENT_FEASIBLE_POINT')
    return dict(PASS=True,known_feasible_assignments=len(known),maximum_violation=largest,
        independent_implementation=True,exact_bound_compensation=True,global_affine_domination=True,
        primal_dual_sign_derivation_verified=True)
