#!/usr/bin/env python3
"""Actual Gurobi smoke for the R25P no-wall-clock-limit parameter contract."""
from __future__ import annotations

import json
import math
import gurobipy as gp
from gurobipy import GRB

m=gp.Model("r25p_unlimited_policy_smoke")
m.Params.OutputFlag=0
m.Params.Threads=1
m.Params.TimeLimit=GRB.INFINITY
m.Params.Method=2
x=m.addVar(lb=0.0,ub=2.0,name="x")
m.addQConstr(x*x<=1.0,name="unit_qcp")
m.setObjective(-x,GRB.MINIMIZE)
m.optimize()

result={
    "release":"R25P_B6C5R4R2_STAGE1_54_OF_54_UNLIMITED",
    "status":int(m.Status),
    "solution_count":int(m.SolCount),
    "configured_TimeLimit":float(m.Params.TimeLimit),
    "gurobi_INFINITY":float(GRB.INFINITY),
    "objective":float(m.ObjVal) if int(m.SolCount)>0 else None,
    "x":float(x.X) if int(m.SolCount)>0 else None,
    "ConstrVio":float(m.ConstrVio) if int(m.SolCount)>0 else None,
}
result["PASS"]=bool(
    result["status"]==GRB.OPTIMAL and result["solution_count"]>0 and
    result["configured_TimeLimit"]>=0.99*float(GRB.INFINITY) and
    abs(result["x"]-1.0)<=1e-6 and result["ConstrVio"]<=1e-8)
print(json.dumps(result,indent=2,sort_keys=True))
m.dispose()
raise SystemExit(0 if result["PASS"] else 2)
