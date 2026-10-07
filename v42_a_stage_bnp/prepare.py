import gzip,pickle
import numpy as np
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_practical.integer_model import restore_types
from .policy import ROOT,OUT,STATIC
def prepare():
    p1=read(OUT/'P1_RESULT.json')
    if not p1['P1_LP_closure'] or p1['valid_LB'] is None:raise PermissionError('CLOSED_FULL_DOMAIN_ROOT_REQUIRED')
    for r in (p1['state'],p1['closed_point'],p1['closure_receipt']):
        if record(r['path'])!=r:raise ValueError('P1_ROOT_CERTIFICATE_BYTES_DRIFT')
    with gzip.open(p1['state']['path'],'rb') as f:state=pickle.load(f)
    authority=read(ROOT/'docs/v42_a_stage_phase1_residual_migration_20261008/ROW_ATTRIBUTION_AUTHORITY.json')
    with np.load(authority['coded_original_attributes']['path']) as z:types=z['vtype'][:state['n']].copy()
    typed,proof=restore_types(state,types)
    with gzip.open(STATIC/'INTEGER_STATE.pkl.gz','wb') as f:pickle.dump(dict(state=state,typed=typed),f,protocol=5)
    atomic(OUT/'INTEGER_BUILD_VERIFICATION.json',dict(PASS=True,state=record(STATIC/'INTEGER_STATE.pkl.gz'),original_integrality_proof=proof,
        rows=typed.matrix.shape[0],cols=typed.matrix.shape[1],nnz=typed.matrix.nnz,snapshot=typed.fingerprint(),
        root_full_domain_LB=p1['exact_valid_LB'],no_native_integer_optimization_yet=True))
    atomic(OUT/'P1_INTEGER_ENTRY_GATE.json',dict(PASS=True,row_closed=True,column_closed=True,root=record(OUT/'P1_RESULT.json'),
        full_pricing=p1['closure_receipt'],zero=read(OUT/'FROZEN64_RESULT.json')['closure_certificate'],
        root_LB=p1['exact_valid_LB'],integer_UB=None,integer_domain_closure_not_inferred_from_LP=True))
    print('INTEGER_PREPARED',typed.matrix.shape,proof['integer_columns'],flush=True)
if __name__=='__main__':prepare()
