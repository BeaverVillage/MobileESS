#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path


R = Path(__file__).resolve().parent
main = (R / "main.py").read_text(encoding="utf-8")
decomp = (R / "r25m_b6_exact_path_decomposition.py").read_text(encoding="utf-8")
contract = json.loads((R / "R25V_CAUSAL_MULTISTART_CONTRACT.json").read_text(encoding="utf-8"))

checks = {
    "causal_flag": "MOBILEESS_R25V_CAUSAL_ROLLING_MIPSTART" in main,
    "terminal_is_partial": "terminal_completion_policy" in main,
    "future_actual_excluded": '"future_realized_used":False' in main,
    "two_start_sources": all(
        value in decomp
        for value in ("CAUSAL_SHIFTED_PREVIOUS_PLAN", "SAME_ISSUE_RESTRICTED_MASTER")
    ),
    "native_multistart": "cm.NumStart=len(starts)" in decomp,
    "current_feasibility_required": "current_compact_feasibility_check_required" in decomp,
    "restricted_bound_not_promoted": "restricted_objbound_promoted" in decomp,
    "ac_unchanged": contract["invariants"]["AC_QCP_changed"] is False,
    "feasible_set_unchanged": contract["invariants"]["feasible_set_changed"] is False,
    "objective_unchanged": contract["invariants"]["objective_changed"] is False,
    "target_3pct": contract["invariants"]["global_gap_target"] == 0.03,
}
result = {"status": "PASS" if all(checks.values()) else "FAIL", "checks": checks}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result["status"] == "PASS" else 2)
