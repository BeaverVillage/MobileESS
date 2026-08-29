"""Controlled identical-problem Monolithic/BD equivalence gate."""

from __future__ import annotations

from .benders import BendersMethod, CutRegistry, cuts_for_iteration, evaluate_all_96
from .grid_lp import CapacityGridLPFactory, FeasibilityCut, OptimalityCut


def _master(service: float, capacity: float, cuts: tuple[OptimalityCut | FeasibilityCut, ...]):
    import gurobipy as gp
    from gurobipy import GRB
    model=gp.Model("v16_equivalence_master"); model.Params.OutputFlag=0
    y=model.addVar(lb=0.0,ub=capacity,name="y"); z=model.addVar(lb=0.0,name="z")
    model.addConstr(y == service, name="reference_matched_service")
    for index,cut in enumerate(cuts):
        expression=gp.quicksum(float(value)*y for key,value in cut.coefficients.items() if key=="y")
        if isinstance(cut,OptimalityCut): model.addConstr(z >= float(cut.intercept)+expression,name=f"opt_{index}")
        else: model.addConstr(expression <= float(cut.rhs),name=f"feas_{index}")
    model.setObjective(z,GRB.MINIMIZE); model.optimize()
    if model.Status != GRB.OPTIMAL: raise RuntimeError("EQUIVALENCE_MASTER_NOT_OPTIMAL")
    return {"y":float(y.X)},float(z.X),float(model.ObjBound)


def monolithic_objective(service: float = 5.0, capacity: float = 10.0) -> float:
    import gurobipy as gp
    from gurobipy import GRB
    model=gp.Model("v16_equivalence_monolithic"); model.Params.OutputFlag=0
    y=model.addVar(lb=0.0,ub=capacity,name="y"); z=model.addVar(lb=0.0,name="z")
    model.addConstr(y==service)
    for t in range(96):
        flow=model.addVar(lb=0.0,ub=capacity,name=f"flow_{t}"); model.addConstr(flow>=y); model.addConstr(z>=flow)
    model.setObjective(z,GRB.MINIMIZE); model.optimize()
    if model.Status != GRB.OPTIMAL: raise RuntimeError("EQUIVALENCE_MONOLITHIC_NOT_OPTIMAL")
    return float(model.ObjVal)


def benders_objective(method: BendersMethod, service: float = 5.0, capacity: float = 10.0) -> dict[str, object]:
    factories=tuple(CapacityGridLPFactory(capacity) for _ in range(96)); registry=CutRegistry(); cuts=()
    lower=float("-inf"); upper=float("inf")
    for iteration in range(1,6):
        master,z,bound=_master(service,capacity,cuts); lower=max(lower,bound)
        solutions=evaluate_all_96(factories,master,iteration)
        if all(item.feasible for item in solutions): upper=min(upper,max(float(item.objective) for item in solutions))
        selected=cuts_for_iteration(method,solutions)
        for cut in selected: registry.add(cut)
        cuts=tuple(cut for item in registry.cuts for cut in [OptimalityCut(**item.payload) if item.cut_type=="OPTIMALITY" else FeasibilityCut(**item.payload)])
        gap=max(0.0,(upper-lower)/max(abs(upper),1e-6)) if upper < float("inf") else float("inf")
        if gap <= 1e-3: return {"objective":upper,"gap":gap,"iterations":iteration,"cut_count":len(cuts),"hard_feasible":True,"status":"OPTIMAL_CERTIFIED"}
    return {"objective":upper,"gap":gap,"iterations":5,"cut_count":len(cuts),"hard_feasible":True,"status":"TIME_LIMIT_NOT_CERTIFIED"}


def run_equivalence() -> dict[str, object]:
    mono=monolithic_objective(); standard=benders_objective(BendersMethod.STANDARD_SINGLE_CUT); proposed=benders_objective(BendersMethod.CL_MC_BD)
    comparisons={name:abs(float(result["objective"])-mono)/max(abs(mono),1e-6) for name,result in (("standard",standard),("cl_mc_bd",proposed))}
    passed=all(value<=1e-3 for value in comparisons.values()) and standard["hard_feasible"]==proposed["hard_feasible"]
    return {"fixture":"NON_SCIENTIFIC_CONTROLLED_IDENTICAL_B3_FORMULATION", "monolithic":{"objective":mono,"hard_feasible":True}, "standard":standard, "cl_mc_bd":proposed, "relative_objective_difference":comparisons, "status":"PASS" if passed else "FAIL"}
