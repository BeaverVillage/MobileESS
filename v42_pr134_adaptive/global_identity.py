"""Independent full global coefficient/RHS/sense/bound identity check."""
import sys
import numpy as np,scipy.sparse as sp
from .common import *
def verify(day,folder):
    source=SOURCE/day;old=sp.load_npz(source/'A0_MATRIX.npz');z=dict(np.load(source/'A0_ATTRIBUTES_CODED.npz'))
    new=sp.load_npz(folder/'EXPANDED_MATRIX.npz');q=dict(np.load(folder/'EXPANDED_ATTRIBUTES.npz'))
    stats=read(folder/'F2-CRA_MODEL_STATS.json');globals=stats['global_variables']
    labels=z['rf_names'];families=labels[z['rf']]
    first_local=next(i for i,f in enumerate(families) if str(f).startswith(('row_v42_root_','row_v42_compact_','row_factor_','row_formulation_')) or str(f) in ('class_exact_cardinality','fixed_duration_count_finish','fixed_duration_count_occupancy'))
    print('GLOBAL_BOUNDARY',day,'rows',first_local,'columns',globals,'local-family',families[first_local],flush=True)
    delta=old[:first_local,:globals]-new[:first_local,:globals];delta.eliminate_zeros()
    mismatches={k:np.flatnonzero(z[k][:first_local]!=q[k][:first_local]).tolist()[:12] for k in ('rhs','sense')}
    bounds={}
    for k in ('lb','ub'):
        left=np.where(z[k][:globals]<=-1e100,-np.inf,np.where(z[k][:globals]>=1e100,np.inf,z[k][:globals]));right=np.where(q[k][:globals]<=-1e100,-np.inf,np.where(q[k][:globals]>=1e100,np.inf,q[k][:globals]));bounds[k]=np.flatnonzero(left!=right).tolist()[:12]
    result=dict(PASS=delta.nnz==0 and not any(mismatches.values()) and not any(bounds.values()),global_rows=first_local,global_columns=globals,
        global_coefficient_differences=delta.nnz,global_RHS_sense_mismatches=mismatches,global_bound_mismatches=bounds,
        old_matrix=record(source/'A0_MATRIX.npz'),new_matrix=record(folder/'EXPANDED_MATRIX.npz'),global_boundary_source='original captured row family module + native global_variables census')
    atomic(folder/'GLOBAL_NUMERIC_IDENTITY.json',result)
    print('GLOBAL_IDENTITY',result['PASS'],mismatches,bounds,'nnz',delta.nnz,flush=True)
    return result
if __name__=='__main__':verify(sys.argv[1],Path(sys.argv[2]))
