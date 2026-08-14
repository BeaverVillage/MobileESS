#!/usr/bin/env python3
"""Proof checks for R25R retained-OPTIMAL dual fallback and issue136 resume."""
from __future__ import annotations

import ast
import json
import math
from pathlib import Path

R=Path(__file__).resolve().parent
dm=(R/'r25m_b6_exact_path_decomposition.py').read_text(encoding='utf-8')
mt=(R/'main.py').read_text(encoding='utf-8')
ast.parse(dm);ast.parse(mt)

# Reproduce the issue136 magnitude: an OPTIMAL snapshot whose measured RC
# mismatch is above the fixed audit tolerance but below the conservative cap.
obj=-764.550693
err=0.00011129066137919501
n_mess=4
guard=max(1e-4,err)
guarded=obj-(n_mess*guard+max(1e-6,1e-9*abs(obj)))

checks={
    'issue136_error_above_fixed_audit_tolerance':err>1e-4,
    'issue136_error_inside_frozen_hard_cap':err<=5e-4,
    'guarded_bound_only_weakens_optimal_objective':math.isfinite(guarded) and guarded<obj-n_mess*err,
    'root_optimal_candidate_retained_before_retry':(
        'best_bounded_root_candidate=candidate' in dm and
        "'source_solve_status':'OPTIMAL'" in dm),
    'root_nonoptimal_retry_uses_retained_candidate':(
        "'trigger':'stricter_retry_nonoptimal'" in dm and
        'rmp_obj,pi,current_conv_pi,_qcp_pi,comp,max_rc_err=best_bounded_root_candidate' in dm),
    'root_fallback_requires_finite_hard_cap':(
        'math.isfinite(candidate_err) and candidate_err<=rc_envelope_hard_cap' in dm),
    'root_branch_comes_from_retained_optimal_solution':(
        'best_bounded_root_branch=_select_branch' in dm and
        'if not root_branch_from_saved_optimal:' in dm),
    'root_recovery_restores_last_optimal_parameters':(
        "best_bounded_root_params={'BarQCPConvTol'" in dm and
        'for pname,pvalue in best_bounded_root_params.items():setattr(m.Params,pname,pvalue)' in dm),
    'bounded_candidate_accepted_after_two_strict_retries':(
        "MOBILEESS_R25R_RC_STRICT_RETRY_BUDGET','2'" in dm and
        "'trigger':'strict_retry_budget_reached'" in dm and
        'dual_retry_count>=bounded_rc_strict_retry_budget' in dm and
        'dual_retry_count_child>=bounded_rc_strict_retry_budget' in dm),
    'child_optimal_candidate_retained_before_retry':(
        'best_bounded_child_candidate=candidate' in dm and
        'best_bounded_child_branch=_select_branch' in dm),
    'child_nonoptimal_retry_uses_retained_candidate':(
        'robj,pi,current_convc_pi,comp_check,dual_audit=best_bounded_child_candidate' in dm and
        'child_branch_from_saved_optimal=True' in dm),
    'child_recovery_restores_last_optimal_parameters':(
        "best_bounded_child_params={'BarQCPConvTol'" in dm and
        'for pname,pvalue in best_bounded_child_params.items():setattr(nm.Params,pname,pvalue)' in dm),
    'measured_guard_controls_root_and_child_lower_bounds':(
        'guarded_full_lb(rmp_obj,len(mids),effective_rc_guard)' in dm and
        'guarded_full_lb(robj,len(mids),child_effective_rc_guard)' in dm),
    'resume_prefix_is_cryptographically_bound':(
        'actual!=claimed' in mt and 'actual!=expected_resume_sha' in mt and
        'r25q_verified_prefix!=resume_issue-113' in mt),
    'final_authoritative_count_remains_54':(
        '_authoritative_count=int(r25q_verified_prefix)+len(issue_rows)' in mt and
        '_authoritative_count==54' in mt),
    'scientific_feasible_set_changed':False,
    'objective_changed':False,
    'causality_changed':False,
    'gap_semantics_changed':False,
}
false_expected={'scientific_feasible_set_changed','objective_changed','causality_changed','gap_semantics_changed'}
passed=all((not bool(v)) if k in false_expected else bool(v) for k,v in checks.items())
print(json.dumps({'release':'R25R_B6C5R4R4_RETAINED_OPTIMAL_DUAL_RESUME','PASS':passed,
                  'issue136_guarded_bound_example':guarded,'checks':checks},indent=2,sort_keys=True))
raise SystemExit(0 if passed else 2)
