"""One numerical validator for every V42 stage; no point or model mutation."""
import math
import numpy as np
from v42_integrated.matrix import audit

SOLVER_FEASIBILITY_TOL = SOLVER_OPTIMALITY_TOL = SOLVER_INTEGRALITY_TOL = 1e-8
V42_POSTSOLVE_NUMERICAL_TOL = POSTSOLVE_NUMERICAL_TOL = 1e-6
STAGES=('A1','M1','A2','M2','B0','B1','B2','B3','B3_loop1','B3_loop2','B3_loop3','B3_loop4','Planning_freeze','reconstructed_certificate')

def contract():
    return dict(schema='V42_GLOBAL_POSTSOLVE_NUMERICAL_V1',solver_FeasibilityTol=SOLVER_FEASIBILITY_TOL,solver_IntFeasTol=SOLVER_INTEGRALITY_TOL,solver_OptimalityTol=SOLVER_OPTIMALITY_TOL,postsolve_numerical_audit_tol=V42_POSTSOLVE_NUMERICAL_TOL,physical_limits_changed=False,result_specific_threshold=False,applies_to=list(STAGES),validator='v42_postsolve.contract.audit_point / numerical_residuals',physical_audit_policy='Inherited independent physical validator and its existing tolerance; numerical tolerance never added to a physical RHS or rating.',raw_solution_repair_allowed=False,legacy_frozen_experiment_sources_preserved=True,future_stage_authority='All listed stages must use this common validator for post-solve numerical/certificate validation; historical scientific executions are not retroactively rewritten.')

def numerical_residuals(stage,residuals,*,finite=True):
    if stage not in STAGES:raise ValueError('UNREGISTERED_V42_STAGE')
    if not residuals:raise ValueError('NUMERICAL_RESIDUALS_REQUIRED')
    checks={key:math.isfinite(float(value)) and 0<=float(value)<=V42_POSTSOLVE_NUMERICAL_TOL for key,value in residuals.items()}
    return dict(NUMERICAL_AUDIT_PASS=bool(finite and all(checks.values())),stage=stage,tolerance=V42_POSTSOLVE_NUMERICAL_TOL,residuals={k:float(v) for k,v in residuals.items()},residual_checks=checks,finite=bool(finite),validator='v42_postsolve.contract.numerical_residuals',rounding_clipping_repair_calls=0)

def audit_point(stage,A,d,point,*,transport_residuals=None):
    checked=audit(A,d,point,integral=True,tolerance=V42_POSTSOLVE_NUMERICAL_TOL)
    residuals=dict(original_full_row=checked['max_constraint_violation'],original_variable_bound=checked['max_bound_violation'],near_integer=checked['max_integrality_violation'])
    residuals.update(transport_residuals or {})
    result=numerical_residuals(stage,residuals,finite=checked['finite'])
    result.update(full_unreduced_matrix_audit=checked,objective=checked['objective'],original_full_rows=A.shape[0],original_variables=len(point))
    return result

def feasible(numerical,physical,*,solver_accepted):
    return bool(numerical['NUMERICAL_AUDIT_PASS'] and physical['PHYSICAL_AUDIT_PASS'] and solver_accepted)

def current_certificate(run,records):
    if run.get('bound_provenance')!='same_completed_solve' or run.get('old_bounds_used',True):raise ValueError('HISTORICAL_BOUND_TRANSFER_FORBIDDEN')
    required=('solve_log_sha256','solve_result_sha256','model_identity','A1_freeze_sha256','NormalAmps_authority_sha256')
    if any(not run.get(k) for k in required):raise ValueError('CURRENT_SOLVE_IDENTITY_REQUIRED')
    accepted=[]
    for record in records:
        if record['solve_log_sha256']!=run['solve_log_sha256']:raise ValueError('SOLUTION_FROM_DIFFERENT_SOLVE')
        if feasible(record['numerical'],record['physical'],solver_accepted=record['solver_accepted']):accepted.append(record)
    chosen=min(accepted,key=lambda r:r['objective']) if accepted else None
    ub=chosen['objective'] if chosen else None
    lb=run['LB'] if run['valid_global_LB'] else None
    gap=None if ub is None or lb is None or ub==0 else (ub-lb)/abs(ub)
    if gap is not None and gap<0:raise ValueError('GLOBAL_LB_ABOVE_FEASIBLE_UB')
    p1=bool(chosen and gap is not None and gap<=.005)
    return dict(schema='V42_RECLASSIFIED_SAME_SOLVE_CERTIFICATE_V1',run_identity=run,UB=ub,LB=lb,gap=gap,valid_incumbent=bool(chosen),valid_global_LB=run['valid_global_LB'],NUMERICAL_AUDIT_PASS=bool(chosen),PHYSICAL_AUDIT_PASS=bool(chosen),chosen_incumbent=chosen,accepted_incumbents=len(accepted),M1_P1_ACCEPTED=p1,M1_ACCEPTED=False,old_bounds_used=False,CURRENT_SOLVE_START_USED=False,postsolve_numerical_tolerance=V42_POSTSOLVE_NUMERICAL_TOL,new_optimize_calls=0)
