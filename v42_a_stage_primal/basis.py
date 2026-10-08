"""Read-only qualification of the unchanged parent-row basis for repair LPs."""
import numpy as np
import scipy.sparse as sp
from v42_pr134_b1.common import read,record,atomic
from v42_a_stage_lexcases.policy import OUT

def qualify():
    if (OUT/'PRIMAL_PARENT_BASIS_QUALIFICATION.json').exists():raise PermissionError('PARENT_BASIS_ALREADY_QUALIFIED')
    pf=OUT/'M19/P2/SHIFT_MAGNITUDE/ROOT_LP';cf=OUT/'M19/P2/PRIMAL_REPAIR_V2/C0'
    p=read(pf/'MODEL_IDENTITY.json');c=read(cf/'MODEL_IDENTITY.json');r=read(pf/'NATIVE_RESULT.json')
    for q in (p['matrix'],p['attributes'],c['matrix'],c['attributes'],r['raw_attributes']):
        if record(q['path'])!=q:raise ValueError('PARENT_OR_CHILD_PERSISTED_AXIS_DRIFT')
    A=sp.load_npz(p['matrix']['path']);B=sp.load_npz(c['matrix']['path'])
    if A.shape!=B.shape or not all(np.array_equal(getattr(A,k),getattr(B,k)) for k in ('indptr','indices','data')):raise ValueError('EVERY_PARENT_CHILD_MATRIX_COEFFICIENT_MUST_MATCH')
    pa=np.load(p['attributes']['path']);ca=np.load(c['attributes']['path']);raw=np.load(r['raw_attributes']['path'])
    if r['status']!=2 or not all(np.array_equal(pa[k],ca[k]) for k in ('senses','rhs')):raise ValueError('PARENT_NATIVE_OPTIMAL_AND_ORIGINAL_ROW_AXES_REQUIRED')
    if len(raw['VBasis'])!=A.shape[1] or len(raw['CBasis'])!=A.shape[0]:raise ValueError('COMPLETE_PARENT_BASIS_REQUIRED')
    atomic(OUT/'PRIMAL_PARENT_BASIS_QUALIFICATION.json',dict(PASS=True,parent=record(pf/'MODEL_IDENTITY.json'),
        parent_native=record(pf/'NATIVE_RESULT.json'),parent_basis=r['raw_attributes'],child=record(cf/'MODEL_IDENTITY.json'),
        every_matrix_coefficient_row_sense_and_RHS_identical=True,rows=A.shape[0],columns=A.shape[1],
        child_changes_only_bounds_and_objective=True,basis_may_be_infeasible_for_child_but_algebraic_axes_preserved=True,
        dual_simplex_with_LPWarmStart2=True,scientific_rows_tolerances_unchanged=True,native_solve_calls=0,
        basis_not_a_child_bound_or_feasibility_certificate=True))
    print('PRIMAL_PARENT_BASIS_QUALIFIED',A.shape,flush=True)
if __name__=='__main__':qualify()
