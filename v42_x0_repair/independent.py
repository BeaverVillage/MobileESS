"""Independent COO rational replay of the completed certificate and cut."""
from fractions import Fraction
import gzip,hashlib,json,math
from pathlib import Path
import numpy as np
from v42_benders.certificates import Uncertifiable
from v42_benders.canonical import digest_arrays

def rational(v):return Fraction.from_float(float(v))
def reject(condition,label):
    if not condition:raise Uncertifiable(label)

def verify(n,cut,known=()):
    r=cut['record'];raw=cut['raw'];phase=bool(raw.get('phase1'));factor=Fraction(1,2) if phase else Fraction(1)
    reject(raw['status']==(2 if phase else 3),'NONTERMINAL_SOURCE')
    persistence=raw['persistence']
    with gzip.open(persistence['journal'],'rb') as f:payload=list(f)[persistence['record']-1].rstrip(b'\n')
    reject(hashlib.sha256(payload).hexdigest()==persistence['payload_sha256'],'RAW_PAYLOAD_HASH')
    saved=json.loads(payload)
    for key in ['status','multipliers','source_x','source_hash','farkas_proof','objective','phase1','solver_rhs','weights']:
        reject(raw[key]==saved[key],'ALTERED_RAW_'+key)
    reject(digest_arrays(np.asarray(raw['multipliers']))==r['raw_vector_sha256']==raw['vector_sha256'],'RAW_VECTOR_HASH')
    reject(r['source_hash']==n.source_hash and r['source_x_hash']==digest_arrays(np.asarray(raw['source_x'])),'SOURCE_AXIS_HASH')
    reject(np.array_equal(n.rhs(raw['source_x']),raw['solver_rhs']),'SOURCE_RHS')
    w={int(i):Fraction(v) for i,v in r['rational_multipliers'].items()}
    reject(all(0<=i<len(n.b) for i in w),'MULTIPLIER_AXIS')
    for i in range(len(n.b)):
        v=w.get(i,Fraction(0));sign=-1 if phase else 1
        reject(not ((n.sense[i]=='<' and v*sign<0) or (n.sense[i]=='>' and v*sign>0)),'MULTIPLIER_SIGN')
        if n.sense[i]!='=':reject(v==factor*rational(raw['multipliers'][i]),'INEQUALITY_MULTIPLIER_CHANGED')
        if phase:
            weight=rational(raw['weights'][i])
            reject(not ((n.sense[i] in ['<','='] and weight+v<0) or (n.sense[i] in ['>','='] and weight-v<0)),'ARTIFICIAL_DUAL_INFEASIBLE')
    # No generator helper, pivot order, or product routine is imported here.
    def coo_product(matrix):
        a={};coo=matrix.tocoo()
        for i,j,c in zip(coo.row,coo.col,coo.data):
            if int(i) in w:a[int(j)]=a.get(int(j),Fraction(0))+w[int(i)]*rational(c)
        return {j:v for j,v in a.items() if v}
    a=coo_product(n.A);b=coo_product(n.B);bound=Fraction(0);terms={}
    for j,value in a.items():
        v=-value if phase else value;extreme=n.lower[j] if v>0 else n.upper[j]
        reject(math.isfinite(extreme),'UNBOUNDED_SUPPORT')
        terms[str(j)]=str(v*rational(extreme));bound+=v*rational(extreme)
    reject(terms==r['bound_terms'] and str(bound)==r['bound_contribution'],'BOUND_SUPPORT')
    row=sum((v*rational(n.b[i]) for i,v in w.items()),Fraction(0))
    intercept=-row-bound if phase else row-bound;coef=b if phase else {j:-v for j,v in b.items()}
    reject(str(intercept)==r['exact_intercept'] and str(row)==r['row_contribution'],'EXACT_INTERCEPT')
    reject({str(j):str(v) for j,v in coef.items()}==r['exact_coefficients'],'EXACT_COEFFICIENTS')
    source=intercept+sum((v*rational(raw['source_x'][j]) for j,v in coef.items()),Fraction(0))
    reject(str(source)==r['source_exact'] and source<-rational(1e-8),'SOURCE_SEPARATION')
    proof=(bound if not phase else -bound)-sum((v*rational(raw['solver_rhs'][i]) for i,v in w.items()),Fraction(0))
    if phase:proof=-proof
    reject(str(proof)==r['completed_proof_on_solver_RHS'],'SOLVER_RHS_PROOF')
    if phase:reject(float(proof)<=raw['objective']+1e-7,'WEAK_DUALITY')
    rc=np.asarray(cut['coefficients']);reject(rc.shape==(len(n.xi),) and np.isfinite(rc).all() and math.isfinite(r['intercept']),'FINITE_CUT_AXIS')
    reject(digest_arrays(np.array([r['intercept']]),rc)==r['cut_hash'],'CUT_HASH')
    rounding_min=rational(r['intercept'])-intercept
    for j in range(len(rc)):
        error=rational(rc[j])-coef.get(j,Fraction(0))
        rounding_min+=error*rational(n.xlower[j] if error>=0 else n.xupper[j])
    reject(rounding_min>=0,'GLOBAL_OUTWARD_DOMINATION')
    reject(abs(r['strict_margin']+(r['intercept']+float(rc@raw['source_x'])))<=1e-10 and r['strict_margin']>1e-8,'ROUNDED_SOURCE_SEPARATION')
    maximum=0.
    for x,value in known:
        violation=-(r['intercept']+float(rc@x));maximum=max(maximum,violation)
        reject(violation<=1e-7,'KNOWN_FEASIBLE_ASSIGNMENT_EXCLUDED')
    return dict(PASS=True,independent_COO_rational_products=True,known_feasible_assignments=len(known),maximum_violation=maximum,
        free_stationarity_exact_zero=True,finite_native_bound_support=True,global_outward_domination=str(rounding_min),
        completed_ray_is_new_derived_certificate=True,raw_solver_ray_accepted_unchanged=False)
