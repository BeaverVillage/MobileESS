"""Existing-point/log numerical and degeneracy census. No model or solve."""
from practical_support import *
import re

def magnitude(values):
    values=np.asarray(values);nz=np.abs(values[np.isfinite(values)&(values!=0)])
    return dict(nonzero=int(len(nz)),absolute_min=float(nz.min()) if len(nz) else None,absolute_max=float(nz.max()) if len(nz) else None)

def point_census(d,x):
    distance=np.minimum(abs(x-d['lower']),abs(x-d['upper']));B=d['types']=='B'
    return dict(total=len(x),exactly_at_bound=int(np.count_nonzero(distance==0)),within_1e_8_of_bound=int(np.count_nonzero(distance<=1e-8)),within_1e_8_fraction=float(np.mean(distance<=1e-8)),fractional_binaries_1e_8=int(np.count_nonzero(np.minimum(abs(x[B]),abs(1-x[B]))>1e-8)),rho=float(x[239826]))

def run():
    A,d,_=hc.load();assert verifier.verify(ROOT,d)['PASS'];CSC=A.tocsc()
    exact_duplicates={};duplicate_rows=[]
    for i in range(A.shape[0]):
        lo,hi=A.indptr[i:i+2];signature=hashlib.sha256(A.indices[lo:hi].tobytes()+A.data[lo:hi].tobytes()+np.asarray(d['rhs'][i]).tobytes()+str(d['sense'][i]).encode()).hexdigest()
        if signature in exact_duplicates:duplicate_rows.append(i)
        else:exact_duplicates[signature]=i
    families={}
    for i in duplicate_rows:
        family=str(d['row_names'][i]).split('[',1)[0];families[family]=families.get(family,0)+1
    counts=np.diff(CSC.indptr);columns=np.argsort(-counts,kind='stable')[:30]
    points=[]
    for name,p in [('native_control_root',OUT/'runs/cuts0_control/ROOT_POINT.npz'),('native_production_root',OUT/'runs/native_production_initial/ROOT_POINT.npz'),('archived_no_crossover_OPTIMAL_LP',hc.HISTORY/'PURE_LP_POINT.npz')]:
        if not p.exists():continue
        with np.load(p) as z:
            x=z['x'];result=dict(name=name,point_SHA256=sha(p),**point_census(d,x))
            if 'reduced_cost' in z:
                rc=z['reduced_cost'];result.update(exact_zero_RC=int(np.count_nonzero(rc==0)),RC_within_1e_8=int(np.count_nonzero(abs(rc)<=1e-8)),RC_within_1e_8_fraction=float(np.mean(abs(rc)<=1e-8)))
        points.append(result)
    logs=[]
    for name,p in [('registered_M0_external',OLD/'external_nodes/0000/LP.log'),('native_control',OUT/'runs/cuts0_control/NATIVE_SOLVER.log'),('native_production',OUT/'runs/native_production_initial/NATIVE_SOLVER.log')]:
        text=p.read_text(encoding='utf-8',errors='replace')
        logs.append(dict(name=name,log_SHA256_at_snapshot=sha(p),mutable_at_snapshot=name!='native_control',warnings_and_restarts=[line for line in text.splitlines() if re.search(r'warning|restart crossover|unscaled|numerical trouble',line,re.I)],presolve_and_root_summary=[line for line in text.splitlines() if re.search(r'^Presolve time|^Presolved:|^Root relaxation presolved|^Root relaxation:|^Barrier solved|^Crossover time|^Factor NZ|^ Factor NZ|^ Factor Ops',line)],Kappa=None,KappaExact=None,reason='No new solve or attribute request; neither value appears in saved receipts/logs.'))
    atomic(OUT/'ROOT_CONDITIONING_AUDIT.json',dict(UTC=stamp(),optimize_calls=0,model_builds=0,objective_identity_PASS=True,A_SHA256=sha(hc.PARENT/'C3A_A.npz'),DATA_SHA256=sha(hc.PARENT/'C3A_DATA.npz'),raw=dict(rows=A.shape[0],cols=A.shape[1],nnz=A.nnz,binaries=int(np.count_nonzero(d['types']=='B')),continuous=int(np.count_nonzero(d['types']=='C')),coefficient_range=magnitude(A.data),RHS_range=magnitude(d['rhs']),lower_bound_range=magnitude(d['lower']),upper_bound_range=magnitude(d['upper']),all_bounds_finite=bool(np.isfinite(d['lower']).all() and np.isfinite(d['upper']).all()),free_columns=0,zero_objective_columns=int(np.count_nonzero(d['objective']==0)),nonzero_matrix_coefficients_at_most_1e_10=int(np.count_nonzero(abs(A.data)<=1e-10))),exact_duplicated_rows=dict(count=len(duplicate_rows),fraction=len(duplicate_rows)/A.shape[0],by_family=families,definition='Identical raw CSR indices/coefficients, RHS binary64 and sense; no approximate or scaled row equivalence claimed'),highly_connected_original_columns=[dict(column=int(j),name=str(d['names'][j]),type=str(d['types'][j]),nnz=int(counts[j]),objective=float(d['objective'][j])) for j in columns],existing_points=points,existing_logs=logs,inference='Poorly scaled coefficients and substantial bound/zero-reduced-cost degeneracy are plausible contributors. The registered M0 log directly records crossover restart, a dropped basis variable and quad precision. Exact cause of native post-branch internal work remains unobserved.',new_Kappa_solve=False,scientific_formulation_unchanged=True))
    print('ROOT_CONDITIONING_AUDIT_OPTIMIZE_0',len(duplicate_rows),[(p['name'],p['within_1e_8_fraction']) for p in points])

if __name__=='__main__':run()
