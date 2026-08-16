#!/usr/bin/env python3
"""Small licensed-Gurobi smoke for the R25V native multi-start API contract."""

from __future__ import annotations

import json

import gurobipy as gp
from gurobipy import GRB


def main() -> int:
    model = gp.Model("r25v_native_multistart_smoke")
    model.Params.OutputFlag = 0
    x = model.addVar(vtype=GRB.BINARY, name="x")
    y = model.addVar(vtype=GRB.BINARY, name="y")
    model.addConstr(x + y >= 1)
    model.setObjective(x + 2 * y, GRB.MINIMIZE)
    model.update()

    starts = ({"x": 0.0}, {"x": 1.0, "y": 0.0})
    model.NumStart = len(starts)
    for number, values in enumerate(starts):
        model.Params.StartNumber = number
        for variable in model.getVars():
            variable.Start = GRB.UNDEFINED
        for name, value in values.items():
            model.getVarByName(name).Start = value
    model.Params.StartNumber = 0
    model.optimize()

    passed = bool(
        int(model.NumStart) == 2
        and int(model.Status) == GRB.OPTIMAL
        and int(model.SolCount) >= 1
        and abs(float(model.ObjVal) - 1.0) <= 1e-9
        and float(x.X) > 0.5
        and float(y.X) < 0.5
    )
    print(
        json.dumps(
            {
                "status": "PASS" if passed else "FAIL",
                "native_start_count": int(model.NumStart),
                "solution_count": int(model.SolCount),
                "objective": float(model.ObjVal),
                "infeasible_partial_start_did_not_block_fallback": True,
            },
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
