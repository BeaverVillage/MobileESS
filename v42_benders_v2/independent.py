"""COO rational replay. Does not call the generator or its product/support helpers."""
from fractions import Fraction as F
import math
import numpy as np
from v42_benders.certificates import Uncertifiable
from v42_benders.canonical import digest_arrays

def verify(n, cut, known=()):
    rec=cut['record'];raw=cut['raw'];w=np.asarray(raw['multipliers']);x=np.asarray(raw['source_x']);kind=rec['kind']
    def q(v):
        if not math.isfinite(float(v)):raise Uncertifiable('NONFINITE_CERTIFICATE')
        return F.from_float(float(v))
    if w.shape!=n.b.shape or x.shape!=n.xlower.shape or not np.isfinite(w).all() or not np.isfinite(x).all():raise Uncertifiable('AXIS')
    if kind not in ['native_farkas','phase1','optimality']:raise Uncertifiable('KIND')
    farkas=kind=='native_farkas';phase=kind=='phase1'
    if raw['status']!=(3 if farkas else 2):raise Uncertifiable('STATUS')
    for i,s in enumerate(n.sense):
        if (s=='<' and w[i]*(1 if farkas else -1)<0) or (s=='>' and w[i]*(1 if farkas else -1)>0):raise Uncertifiable('SIGN')
    def product(matrix):
        result={};a=matrix.tocoo()
        for i,j,v in zip(a.row,a.col,a.data):
            if w[i]:result[int(j)]=result.get(int(j),F(0))+q(w[i])*q(v)
        return {j:v for j,v in result.items() if v}
    ay=product(n.A);bx=product(n.B)
    residual=ay if farkas else {j:q(0 if phase else n.c[j])-ay.get(j,F(0)) for j in range(len(n.yi))}
    residual={j:v for j,v in residual.items() if v};total=F(0);terms={}
    for j,r in residual.items():
        edge=n.lower[j] if r>0 else n.upper[j]
        if not math.isfinite(edge):raise Uncertifiable('INFINITE_SUPPORT')
        terms[str(j)]=str(r*q(edge));total+=r*q(edge)
    row=sum((q(w[i])*q(n.b[i]) for i in range(len(w)) if w[i]),F(0))
    eq=sum((q(w[i])*q(n.b[i]) for i in range(len(w)) if w[i] and n.sense[i]=='='),F(0))
    if farkas:
        exact=row-total;coef={j:-v for j,v in bx.items()};direction=1
        proof=total-sum((q(w[i])*q(raw['solver_rhs'][i]) for i in range(len(w)) if w[i]),F(0))
        if abs(float(proof)-raw['farkas_proof'])>1e-7*max(1.,abs(float(proof))) or float(proof)<=0:raise Uncertifiable('PROOF')
        if rec['native_proof_reconstructed']!=float(proof):raise Uncertifiable('ALTERED_PROOF')
    else:
        native_rc=np.asarray(raw['reduced_costs']);expected=np.array([float(residual.get(j,F(0))) for j in range(len(n.yi))])
        if not np.isfinite(native_rc).all() or np.max(abs(native_rc[:len(n.yi)]-expected),initial=0)>1e-7*max(1.,np.max(abs(expected),initial=0)):raise Uncertifiable('RC')
        if phase:
            aux=[]
            for i,s in enumerate(n.sense):
                if s in ['<','=']:aux.append(q(raw['weights'][i])+q(w[i]))
                if s in ['>','=']:aux.append(q(raw['weights'][i])-q(w[i]))
            if any(v<0 for v in aux):raise Uncertifiable('AUXILIARY_STATIONARITY')
            if len(native_rc)!=len(n.yi)+len(aux) or np.max(abs(native_rc[len(n.yi):]-np.array(list(map(float,aux)))),initial=0)>1e-7:raise Uncertifiable('AUXILIARY_RC')
            exact=-row-total;coef=bx;direction=1
        else:exact=row+total+q(n.objective_constant);coef={j:-v for j,v in bx.items()};direction=-1
    exact_source=exact+sum((v*q(x[j]) for j,v in coef.items()),F(0))
    if not farkas and abs(raw['objective']-(-float(exact_source) if phase else float(exact_source)))>1e-7*max(1.,abs(raw['objective'])):raise Uncertifiable('DUAL_TIGHTNESS')
    for key,val in [('exact_intercept',str(exact)),('bound_contribution',str(total)),('bound_terms',terms),('row_contribution',str(row)),('equality_contribution',str(eq)),('source_exact',str(exact_source)),('source_hash',n.source_hash),('source_x_hash',digest_arrays(x)),('raw_vector_sha256',digest_arrays(w))]:
        if rec.get(key)!=val:raise Uncertifiable('ALTERED_'+key)
    if rec['exact_coefficients']!={str(j):str(v) for j,v in coef.items()}:raise Uncertifiable('ALTERED_COEFFICIENT_PROVENANCE')
    # Global domination over original x box, independently check outward rounding.
    rounded=np.asarray(cut['coefficients']);delta=q(rec['intercept'])-exact
    if rounded.shape!=n.xlower.shape:raise Uncertifiable('CUT_AXIS')
    for j,a in enumerate(rounded):
        e=q(a)-coef.get(j,F(0));edges=[e*q(n.xlower[j]),e*q(n.xupper[j])]
        delta+=min(edges) if direction>0 else max(edges)
    if delta*direction<0:raise Uncertifiable('NOT_GLOBAL_OUTWARD_ROUNDING')
    source=rec['intercept']+float(rounded@x)
    if source!=rec['source_value']:raise Uncertifiable('ALTERED_SOURCE_VALUE')
    if rec['cut_hash']!=digest_arrays(np.array([rec['intercept']]),rounded):raise Uncertifiable('ALTERED_HASH')
    if farkas or phase:
        if -source<=1e-8 or exact_source>=-q(1e-8):raise Uncertifiable('WEAK_MARGIN')
    worst=0.
    for xv,opt in known:
        value=rec['intercept']+float(rounded@xv);violation=value-opt if kind=='optimality' else -value
        worst=max(worst,violation)
        if violation>1e-7:raise Uncertifiable('FEASIBLE_ASSIGNMENT_EXCLUDED')
    return dict(PASS=True,independent_COO_rational_replay=True,known_feasible_points=len(known),
        maximum_known_violation=worst,bound_completed_stationarity=0.,finite_support=True,
        source_separation=-source if farkas or phase else None)
