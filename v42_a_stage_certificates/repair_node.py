"""No native solve: independently re-evaluate the prior child with a repaired dual."""
from fractions import Fraction
from time import time
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_lexcases.policy import OUT,STATIC
from v42_a_stage_compact_rowgen.budget import Budget
from v42_a_stage_phase1.core import interval_box_bound
from .dual import repair

def run():
    target=OUT/'CERTIFICATE_RECOVERY';folder=OUT/'M19/P2/SHIFT_MAGNITUDE/TREE/N2'
    identity=read(folder/'MODEL_IDENTITY.json');rec=read(folder/'NATIVE_RESULT.json');recovery=read(target/'RESULT.json')
    for r in (identity['matrix'],identity['attributes'],rec['raw_attributes'],recovery['upper']):
        if record(r['path'])!=r:raise ValueError('QUALIFIED_CERTIFICATE_SOURCE_BYTE_DRIFT')
    if recovery['reconstructed_snapshot_sha256']!=identity['original_snapshot_sha256'] or not recovery['primal']['PASS'] or not recovery['sign']['PASS']:raise ValueError('PRIOR_NODE_EXACT_RECONSTRUCTION_AND_RAW_REPLAY_REQUIRED')
    A=sp.load_npz(identity['matrix']['path']);attrs=dict(np.load(identity['attributes']['path']));raw=dict(np.load(rec['raw_attributes']['path']));u=np.load(recovery['upper']['path'])['upper']
    budget=Budget();start=time()
    def check():
        budget.remaining()
        if time()-start>180:raise TimeoutError('READ_ONLY_DUAL_REPAIR_ALLOCATION')
    pi,proof=repair(A,attrs['objective'],raw['Pi'],attrs['senses'],attrs['lower'],u,check)
    constant=Fraction(read(OUT/'M19/P2/EXACT_CASES/SHIFT_MAGNITUDE/INTEGER_OBJECTIVE_DEFINITION.json')['original_objective_constant'])
    L=interval_box_bound(A,attrs['objective'],pi,attrs['lower'],u,attrs['rhs'],float(constant))
    path=STATIC/'READ_ONLY_N2_CERTIFICATE_DUAL.npz';np.savez_compressed(path,Pi=pi)
    result=dict(PASS=L is not None,valid_LB=L,proposal=proof,certificate_dual=record(path),original_raw_dual=rec['raw_attributes'],
        matrix_and_attributes=record(folder/'MODEL_IDENTITY.json'),original_reconstruction=record(target/'RESULT.json'),
        full_relevant_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),all_rows_and_relevant_columns_present=True,
        LP_closure_only=True,integer_optimality_claim=False,old_queue_not_modified=True,native_solve_calls=0,
        source_files=[record(__file__),record(__import__('pathlib').Path(__file__).parent/'dual.py')],wall_seconds=time()-start)
    atomic(target/'REPAIRED_NODE_BOUND.json',result);print('REPAIRED_NODE_BOUND',result['PASS'],L,proof['removed_rows'],flush=True)
if __name__=='__main__':run()
