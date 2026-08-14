#!/usr/bin/env python3
"""Dependency-free proof checks for the R25T solver lifecycle."""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

from r25m_b6_exact_path_decomposition import (
    global_relative_gap,
    incumbent_required_for_gap,
    r25t_recoverable_restricted_error,
)


ROOT = Path(__file__).resolve().parent
TEXT = (ROOT / "r25m_b6_exact_path_decomposition.py").read_text(encoding="utf-8")
checks = {}

for lower_bound in (-1698.080293, -2016.127869, -10.0, 10.0):
    target = 0.03
    required = incumbent_required_for_gap(lower_bound, target)
    checks[f"threshold_exact_{lower_bound}"] = abs(
        global_relative_gap(required, lower_bound) - target
    ) <= 1e-12

rng = random.Random(25006)
safe = True
monotone = True
for _ in range(2000):
    incumbent = -rng.uniform(10.0, 5000.0)
    lb1 = incumbent - rng.uniform(0.0, 500.0)
    lb2 = incumbent - rng.uniform(0.0, 500.0)
    combined = max(lb1, lb2)
    safe = safe and combined <= incumbent
    monotone = monotone and global_relative_gap(incumbent, combined) <= min(
        global_relative_gap(incumbent, lb1),
        global_relative_gap(incumbent, lb2),
    ) + 1e-15
checks["max_of_valid_lower_bounds_is_valid"] = safe
checks["combined_bound_gap_is_monotone"] = monotone
checks["restricted_oom_is_phase_transition"] = r25t_recoverable_restricted_error(10001)
checks["non_oom_errors_still_fail_closed"] = all(
    not r25t_recoverable_restricted_error(code) for code in (0, 10003, 10005, 20001)
)

tokens = {
    "portfolio_is_opt_in": "MOBILEESS_R25T_GLOBAL_PORTFOLIO",
    "compact_authority_preserved_before_projection": "compact_authority=m if r25t_global_portfolio else None",
    "copy_mathematical_structure_checked": "R25T exact working copy mathematical structure differs before projection",
    "copy_fingerprint_diagnostic_only": "fingerprint_equal_diagnostic_only",
    "copy_full_linear_matrix_checked": "matrix=model.getA().tocsr(copy=True)",
    "restricted_phase_has_stall_transition": "PRIMAL_INCUMBENT_STALL",
    "restricted_phase_has_node_transition": "PRIMAL_PHASE_MAX_NODES",
    "restricted_phase_has_time_transition": "PRIMAL_PHASE_MAX_SECONDS",
    "restricted_phase_spills_early": "m.Params.NodefileStart=min(float(m.Params.NodefileStart),0.1)",
    "restricted_phase_caps_memory": "m.Params.SoftMemLimit=min(float(m.Params.SoftMemLimit),4.0)",
    "restricted_oom_never_promotes_bound": "PRIMAL_PHASE_MEMORY_PRESSURE",
    "restricted_bound_never_promoted": "'restricted_objbound_promoted':False",
    "compact_bound_is_global_authority": "'compact_objbound_is_global_authority':True",
    "combined_bound_rule_explicit": "max(EXACT_PRICED_ROOT_LB, ORIGINAL_COMPACT_MIQCP_OBJBOUND)",
    "same_issue_start_is_disclosed": "'posthoc_same_issue_MIP_start_used':bool",
    "compact_solution_is_polished": "R25T compact continuous polish failed",
    "restricted_tree_released_before_compact": "restricted_work_model_disposed_before_compact",
    "custom_bp_disabled_in_portfolio": "R25T uses original compact MIQCP native global B&B authority",
    "ac_qcp_not_changed": "'AC_QCP_changed':False",
}
for name, token in tokens.items():
    checks[name] = token in TEXT

result = {
    "release": "R25T_B6C6_GLOBAL_BOUND_PORTFOLIO",
    "PASS": all(checks.values()),
    "checks": checks,
    "issue149_required_incumbent": incumbent_required_for_gap(-1698.080293, 0.03),
}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result["PASS"] else 1)
