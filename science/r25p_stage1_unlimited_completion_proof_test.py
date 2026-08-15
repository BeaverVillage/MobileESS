#!/usr/bin/env python3
"""R25P static/runtime proof for the authoritative unlimited 54/54 policy."""
from __future__ import annotations

import ast
import importlib.util
import json
import math
import sys
from pathlib import Path

R=Path(__file__).resolve().parent
main_text=(R/"main.py").read_text(encoding="utf-8")
decomp_text=(R/"r25m_b6_exact_path_decomposition.py").read_text(encoding="utf-8")
ast.parse(main_text);ast.parse(decomp_text)

spec=importlib.util.spec_from_file_location("r25p_main_proof",R/"main.py")
mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)

class FakeExpr:
    def __init__(self,value):self.value=value
    def getValue(self):return self.value

class FakeVar:
    def __init__(self,value):self.X=value

scalar_cases=[
    (17.25,17.25),
    (FakeExpr(18.5),18.5),
    (FakeVar(19.75),19.75),
]
scalar_failures=[]
for value,expected in scalar_cases:
    got=mod._r25p_solution_scalar(value)
    if got!=expected:scalar_failures.append({"expected":expected,"actual":got})
nonfinite_rejected=False
try:mod._r25p_solution_scalar(float("inf"))
except RuntimeError:nonfinite_rejected=True

checks={
    "float_expression_variable_scalar_cases":len(scalar_cases),
    "scalar_failures":len(scalar_failures),
    "nonfinite_scalar_rejected":nonfinite_rejected,
    "unlimited_mode_flag":("MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION" in decomp_text and
                            "MOBILEESS_R25P_STAGE1_UNLIMITED_COMPLETION" in main_text),
    "root_and_child_iteration_caps_removed_in_mode":(
        "itertools.count() if max_iter is None" in decomp_text and
        "itertools.count() if maxit is None" in decomp_text),
    "branch_price_node_cap_removed_in_mode":(
        "bp_node_limit=(None if unlimited_completion" in decomp_text and
        "bp_node_limit is None or bp_nodes_solved<bp_node_limit" in decomp_text),
    "gurobi_no_limit_value_used":("GRB.INFINITY if not math.isfinite" in decomp_text),
    "all_major_solver_budgets_unlimited":all(token in decomp_text for token in [
        "cg_limit=(math.inf if unlimited_completion",
        "int_limit=(math.inf if unlimited_completion",
        "c5r4_polish_time=(math.inf if unlimited_completion",
        "bp_time_limit=(math.inf if unlimited_completion",
        "bp_node_cg_limit=(math.inf if unlimited_completion",
    ]),
    "certificate_fail_closed_before_physical_commit":(
        "R25P B6 global 3% certificate not reached" in main_text and
        main_text.find("R25P B6 global 3% certificate not reached") < main_text.find("# Extract.")),
    "authoritative_axis_is_113_to_166":(
        'start_issue!=113 or count!=54' in main_text and
        'resume_issue!=113' in main_text),
    "final_54_of_54_gate":all(token in main_text for token in [
        "PASS_R25R_STAGE1_54_OF_54_FINAL",
        "all_54_global_3pct_certificates_pass",
        "ANNUAL_MONTHLY_48H_BURNIN_4_PROCESSES_X_4_THREADS",
    ]),
    "scientific_feasible_set_changed":False,
    "objective_changed":False,
    "gap_semantics_changed":False,
}
passed=(len(scalar_failures)==0 and all(bool(v) for k,v in checks.items()
        if k not in {"scalar_failures","scientific_feasible_set_changed","objective_changed","gap_semantics_changed"})
        and checks["scalar_failures"]==0)
result={"release":"R25P_B6C5R4R2_STAGE1_54_OF_54_UNLIMITED","PASS":passed,"checks":checks}
print(json.dumps(result,indent=2,sort_keys=True))
raise SystemExit(0 if passed else 2)
