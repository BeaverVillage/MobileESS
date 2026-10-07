"""Recover a current complete-domain bound without classifying interruption infeasible."""
import math
from v42_pr134_b1.common import read,record,atomic
from .policy import OUT

def prepare():
    if (OUT/'LEX_CASE_ENTRY_GATE.json').exists():raise PermissionError('CASE_GATE_ALREADY_PREPARED')
    folder=OUT/'M19/P2/REFINEMENT/SHIFT_MAGNITUDE/N1'
    result=read(folder/'NATIVE_RESULT.json');actual=read(folder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json')
    partition=read(OUT/'M19/P2/REFINEMENT/SHIFT_MAGNITUDE/N0/EXHAUSTIVE_INTEGER_OBJECTIVE_PARTITION.json')
    if result['status']!=11 or result['native_error'] is not None or not actual['PASS'] or actual['differing_matrix_coefficients']!=0:raise ValueError('CURRENT_VERIFIED_INTERRUPTED_MODEL_REQUIRED')
    if not partition['both_children_preserved'] or not partition['exhaustive_over_original_integer_domain']:raise ValueError('EXHAUSTIVE_PARTITION_REQUIRED')
    left=float(result['ObjBound']);right=float(partition['right']['valid_LB'])
    if not math.isfinite(left):raise ValueError('FINITE_CURRENT_BOUND_REQUIRED')
    atomic(OUT/'INTERRUPTED_BOUND_RECOVERY.json',dict(PASS=True,component='shift_magnitude',valid_full_domain_LB=min(left,right),
        native_current_result=record(folder/'NATIVE_RESULT.json'),actual_matrix=record(folder/'INDEPENDENT_COMPILED_MODEL_VERIFICATION.json'),
        complete_relevant_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),original_integer_equivalence=record(OUT/'LEX_REFINE_BUILD_VERIFICATION.json'),
        exhaustive_partition=record(OUT/'M19/P2/REFINEMENT/SHIFT_MAGNITUDE/N0/EXHAUSTIVE_INTEGER_OBJECTIVE_PARTITION.json'),
        native_left_LB=left,analytic_right_LB=right,termination_infeasibility_claim=False,
        authority='CURRENT_NATIVE_FULL_RELEVANT_INTEGER_MODEL_BOUND_AFTER_SOLVE',
        official_attribute_contract='https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/model.html#objbound',
        independent_rational_MIP_dual_certificate=False))
    atomic(OUT/'LEX_CASE_ENTRY_GATE.json',dict(PASS=True,bound=record(OUT/'INTERRUPTED_BOUND_RECOVERY.json'),
        full_domain=record(OUT/'LEX_FULL_BUILD_VERIFICATION.json'),integer_equivalence=record(OUT/'LEX_REFINE_BUILD_VERIFICATION.json'),
        migration_zero=read(OUT/'P2_MIGRATION_PROBE_RESULT.json')['certificate'],rho_lock_epsilon=1e-7,
        integer_objective_lift_exact=True,both_children_preserved=True,parameter_sweep=False))
    print('CASE_ENTRY_GATE',min(left,right),flush=True)
if __name__=='__main__':prepare()
