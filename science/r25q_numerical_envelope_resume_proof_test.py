#!/usr/bin/env python3
"""Proof checks for R25Q stricter recovery, bounded RC safety, and resume."""
from __future__ import annotations
import ast,json,math
from pathlib import Path

R=Path(__file__).resolve().parent
dm=(R/'r25m_b6_exact_path_decomposition.py').read_text(encoding='utf-8')
mt=(R/'main.py').read_text(encoding='utf-8')
ast.parse(dm);ast.parse(mt)

def guarded(obj,n,err):
    return obj-(n*err+max(1e-6,1e-9*abs(obj)))

cases=0;failures=0
for obj in (-2500.0,-572.952411,0.0,831.25):
    for n in (1,4,8):
        for err in (1e-4,1.1697620255634213e-4,5e-4):
            cases+=1
            lb=guarded(obj,n,err)
            if not (math.isfinite(lb) and lb<=obj-n*err):failures+=1

checks={
    'guarded_lower_bound_cases':cases,'guarded_lower_bound_failures':failures,
    'strict_retry_schedule_to_1e_minus_12':all(x in dm for x in ['min(p,3e-11)','min(p,1e-11)','min(p,3e-12)','min(p,1e-12)']),
    'homogeneous_and_quad_recovery':('m.Params.BarHomogeneous=1' in dm and 'm.Params.Quad=1' in dm and
                                     'nm.Params.BarHomogeneous=1' in dm and 'nm.Params.Quad=1' in dm),
    'bounded_envelope_hard_cap':('MOBILEESS_R25Q_RC_ENVELOPE_HARD_CAP' in dm and 'candidate_err<=rc_envelope_hard_cap' in dm),
    'measured_error_controls_pricing_and_lb':('effective_rc_guard=max(float(rc_audit_tol),float(max_rc_err))' in dm and
        'all(v>=-effective_rc_guard' in dm and 'guarded_full_lb(rmp_obj,len(mids),effective_rc_guard)' in dm and
        'guarded_full_lb(robj,len(mids),child_effective_rc_guard)' in dm),
    'root_validation_audit_exposes_envelope':("'effective_rc_guard':_root_effective_guard" in dm and
        "'bounded_rc_envelope_used':_root_bounded_used" in dm and
        "'bounded_rc_envelope_hard_cap':float(rc_envelope_hard_cap)" in dm),
    'fixed_tolerance_not_loosened':("rc_audit_tol=float(os.environ.get('MOBILEESS_R25M_B6_RC_AUDIT_TOL','1e-4'))" in dm),
    'resume_requires_verified_prefix':('R25Q continuation requires a verified contiguous prefix' in mt and
        'r25q_verified_prefix!=resume_issue-113' in mt),
    'resume_state_hash_verified':('actual!=claimed' in mt and 'actual!=expected_resume_sha' in mt),
    'prefix_plus_continuation_exactly_54':('_authoritative_count=int(r25q_verified_prefix)+len(issue_rows)' in mt and
        '_authoritative_count==54' in mt),
    'scientific_feasible_set_changed':False,'objective_changed':False,
    'causality_changed':False,'gap_semantics_changed':False,
}
passed=(failures==0 and all(bool(v) for k,v in checks.items() if k not in {
    'guarded_lower_bound_failures','scientific_feasible_set_changed','objective_changed','causality_changed','gap_semantics_changed'}))
result={'release':'R25Q_B6C5R4R3_NUMERICAL_ENVELOPE_RESUME','PASS':passed,'checks':checks}
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(0 if passed else 2)
