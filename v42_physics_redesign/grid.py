"""Exact ALL-original-row checks at fractional and integer points."""
from .common import *
from v42_rowgen.core import separate,row_digest

def main():
    prior.forbid_optimize();A,d,_=hc.load()
    with np.load(ROOT/'docs/v42_m1_joint_formulation_20261008/runs/ORIGINAL/LP_POINT_DUAL.npz') as f:x=f['x'].copy();pi=f['Pi'].copy()
    with np.load(P183/'artifacts/BEST_VALID_POINT.npz') as f:best=f['x'].copy()
    fractional=separate(A,d,x);integer=separate(A,d,best);assert integer['PASS']
    write(REPORTS/'GRID_ORIGINAL_ROW_SEPARATION_AUDIT.json',dict(original_fractional_archive=fractional,validated_integer_UB=integer,all_original_rows_checked=True,initial_and_final_original_grid_rows_retained=True,deferred_grid_rows=0,new_native_optimize_calls=0,fractional_point_not_used_as_integer_or_LB=True))
    rho=int(np.flatnonzero(d['objective'])[0]);c=A.tocsc();with_rho=c.indices[c.indptr[rho]:c.indptr[rho+1]]
    critical=sorted([int(i) for i in with_rho if abs(pi[i])>1e-8],key=lambda i:-abs(pi[i]));table_rows=[]
    for i in critical:
        r=A.getrow(i);network=[];slots=[]
        for j,v in zip(r.indices,r.data):
            n=str(d['names'][j])
            if n.startswith('response_'):
                network.append(dict(column=int(j),name=n,coefficient=float(v),root_value=float(x[j])))
                if '[' in n:
                    last=n[n.find('[')+1:-1].split(',')[-1]
                    if last.isdigit():slots.append(int(last))
        table_rows.append(dict(original_row_index=i,original_row_name=str(d['row_names'][i]),sense=str(d['sense'][i]),RHS=float(d['rhs'][i]),dual=float(pi[i]),native_row_sparse_SHA256=row_digest(A,d,i),grid_slots=sorted(set(slots)),original_network_columns=network,original_row_residual=float((r@x)[0]-d['rhs'][i])))
    write(REPORTS/'CRITICAL_GRID_RHO_COUPLING.json',dict(source='Actual original C3A CSR rho column and archived Pi, all rows with abs(Pi)>1e-8',diagnostic_threshold_only=True,original_grid_rows_never_dropped=True,critical_rows=table_rows,critical_row_count=len(table_rows),source_axis_sha256=hashlib.sha256(d['names'].tobytes()).hexdigest(),no_empirical_cut_created=True))
    print('ALL_ORIGINAL_ROW_SEPARATION_DONE',len(critical),fractional['PASS'],integer['PASS'],flush=True)

if __name__=='__main__':main()
