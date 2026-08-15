#!/usr/bin/env python3
"""Small Gurobi API smoke for the R25T compact-authority lifecycle."""

from __future__ import annotations

import json
import math

import gurobipy as gp
from gurobipy import GRB

from r25m_b6_exact_path_decomposition import (
    exact_gurobi_model_structure_digest,
    global_relative_gap,
)


# The untouched model represents the complete exact problem.
compact = gp.Model("r25t_compact_authority_smoke")
compact.Params.OutputFlag = 0
compact.Params.Threads = 1
x = compact.addVar(vtype=GRB.BINARY, name="x")
y = compact.addVar(lb=0.0, ub=2.0, name="y")
compact.addConstr(y >= 1.0 - x, name="coupling")
compact.addQConstr(y * y <= 4.0, name="convex_qcp")
compact.setObjective(-4.0 * x + y, GRB.MINIMIZE)
compact.update()

work = compact.copy()
fingerprint_equal = int(work.Fingerprint) == int(compact.Fingerprint)
compact_structure, compact_counts = exact_gurobi_model_structure_digest(compact)
work_structure, work_counts = exact_gurobi_model_structure_digest(work)
structure_equal = compact_structure == work_structure and compact_counts == work_counts

# Search guidance is intentionally outside the mathematical-structure digest.
guided = compact.copy()
guided.getVarByName("x").Start = 1.0
guided.getVarByName("x").BranchPriority = 17
guided.update()
guided_structure, guided_counts = exact_gurobi_model_structure_digest(guided)
guidance_preserves_structure = guided_structure == compact_structure and guided_counts == compact_counts

# Conversely, changing one matrix coefficient must be detected fail-closed.
changed = compact.copy()
changed.chgCoeff(changed.getConstrByName("coupling"), changed.getVarByName("y"), 2.0)
changed.update()
changed_structure, _ = exact_gurobi_model_structure_digest(changed)
coefficient_change_detected = changed_structure != compact_structure
guided.dispose()
changed.dispose()

# A restricted surrogate is allowed to provide only an incumbent/start.
wx = work.getVarByName("x")
wy = work.getVarByName("y")
wx.LB = 1.0
wx.UB = 1.0
work.optimize()
assert work.SolCount > 0
for vv in compact.getVars():
    vv.Start = float(work.getVarByName(vv.VarName).X)

external_exact_lb = -4.0
live = {"terminated": False, "combined_lb": external_exact_lb}


def callback(model, where):
    if where not in (GRB.Callback.MIP, GRB.Callback.MIPSOL):
        return
    if where == GRB.Callback.MIP:
        incumbent = float(model.cbGet(GRB.Callback.MIP_OBJBST))
        native_lb = float(model.cbGet(GRB.Callback.MIP_OBJBND))
    else:
        incumbent = float(model.cbGet(GRB.Callback.MIPSOL_OBJ))
        native_lb = float(model.cbGet(GRB.Callback.MIPSOL_OBJBND))
    if not math.isfinite(incumbent):
        return
    combined = external_exact_lb
    if math.isfinite(native_lb) and native_lb <= incumbent + 1e-9:
        combined = max(combined, native_lb)
    live["combined_lb"] = combined
    if global_relative_gap(incumbent, combined) <= 0.03:
        live["terminated"] = True
        model.terminate()


compact.Params.MIPGap = 0.0
compact.optimize(callback)
assert compact.SolCount > 0
pre_obj = float(compact.ObjVal)
native_lb = float(compact.ObjBound)
combined_lb = max(external_exact_lb, native_lb)
certificate_pass = global_relative_gap(pre_obj, combined_lb) <= 0.03 + 1e-12

# The final authority is a fixed-integer continuous QCP, matching production.
fixed = {}
for vv in compact.getVars():
    if vv.VType in (GRB.BINARY, GRB.INTEGER):
        fixed[vv.VarName] = float(round(vv.X))
for name, value in fixed.items():
    vv = compact.getVarByName(name)
    vv.LB = value
    vv.UB = value
    vv.VType = GRB.CONTINUOUS
compact.update()
compact.Params.BarQCPConvTol = 1e-9
compact.optimize()

result = {
    "status": "PASS" if all((structure_equal, guidance_preserves_structure, coefficient_change_detected,
                               certificate_pass, compact.Status == GRB.OPTIMAL)) else "FAIL",
    "working_copy_scientific_structure_equal": structure_equal,
    "working_copy_fingerprint_equal_diagnostic_only": fingerprint_equal,
    "search_guidance_preserves_scientific_structure": guidance_preserves_structure,
    "matrix_coefficient_change_detected": coefficient_change_detected,
    "restricted_solution_used_as_start_only": True,
    "restricted_objbound_global_authority": False,
    "compact_objbound_global_authority": True,
    "combined_lower_bound": combined_lb,
    "certificate_pass": certificate_pass,
    "fixed_continuous_qcp_optimal": compact.Status == GRB.OPTIMAL and compact.IsMIP == 0,
}
print(json.dumps(result, indent=2, sort_keys=True))
raise SystemExit(0 if result["status"] == "PASS" else 1)
