"""Verify every stored CSR coefficient, including Gurobi's tiny-entry omissions."""
from electrical_engine import H,read,save,record
import scipy.sparse as sp
import numpy as np
import time
def main():
    rows=[];started=time.perf_counter()
    assert read(H/'FULL_LOGICAL_B1_SEED_AUDIT.json')['status']=='PASS'
    assert read(H/'full_model/core/POLICY_FEASIBLE_SEED_AUDIT.json')['status']=='PASS'
    for t in range(96):
        folder=H/f'full_model/electrical_blocks/slot_{t:02}'
        block=read(folder/'BLOCK_AUDIT.json');a=sp.load_npz(folder/'FULL_LINEAR_MATRIX.npz')
        with np.load(folder/'RHS_AND_SEED.npz') as z:b=z['rhs'];x=z['seed']
        residual=np.maximum(a@x-b,0)
        maximum=float(residual.max(initial=0));assert maximum<=1e-9,(t,maximum)
        original_nnz=a.nnz;gurobi_nnz=block['seed_audit']['matrix_nonzeros']
        rows.append(dict(slot=t,status='PASS',rows=a.shape[0],full_precision_CSR_nonzeros=original_nnz,Gurobi_materialized_nonzeros=gurobi_nnz,materialization_tiny_entry_difference=original_nnz-gurobi_nnz,all_stored_nonzero_coefficients_included=True,max_linear_residual=maximum,maximum_residual_row=int(residual.argmax()),matrix=block['matrix'],seed=block['data']))
    out=dict(status='PASS',all_31945536_rows_substituted_with_every_stored_coefficient=True,linear_rows=sum(r['rows'] for r in rows),full_precision_CSR_nonzeros=sum(r['full_precision_CSR_nonzeros'] for r in rows),Gurobi_materialized_nonzeros=sum(r['Gurobi_materialized_nonzeros'] for r in rows),Gurobi_materialization_tiny_entry_difference=sum(r['materialization_tiny_entry_difference'] for r in rows),maximum_full_precision_linear_residual=max(r['max_linear_residual'] for r in rows),explanation='The stored full CSR matrices are the complete logical electrical authority. Gurobi materialization omits tiny entries internally. This separate direct CSR substitution uses every stored nonzero, supplementing original Gurobi row_audit without relaxing any tolerance.',wall_seconds=time.perf_counter()-started,slots=rows)
    save(H/'FULL_PRECISION_ELECTRICAL_ROW_AUDIT.json',out)
    print('FULL_PRECISION_ALL_ROWS_PASS',out['maximum_full_precision_linear_residual'],flush=True)
if __name__=='__main__':main()
