"""Final MESS objective adapter; inherited route/P/Q/SOC physics unchanged."""
from time import perf_counter
from contextlib import contextmanager
import gurobipy as gp
from .contract import mess_groups,passes,relative_gap,integer_certificate,P1_EPS,COMPONENT_EPS

def optimize(model,objectives,deadline,incumbent=None,*,diagnostic_quadratic=False,progress=None):
    if diagnostic_quadratic:raise ValueError('FINAL_CONTRACT_REQUIRES_MILP')
    groups=mess_groups(objectives);ordered=passes(groups);model.update()
    applied=0
    if incumbent:
        for var in model.getVars():
            if var.VarName in incumbent['values']:var.Start=incumbent['values'][var.VarName];applied+=1
    model.Params.Threads=1;model.Params.Seed=20260929;model.Params.MIPGap=.005
    model.Params.OutputFlag=0;rows=[];saved=None;begin=perf_counter()
    for group,name,expr in ordered:
        deadline.check();model.setObjective(expr);model.Params.TimeLimit=deadline.remaining;model.optimize()
        inc=model.ObjVal if model.SolCount else None;bound=model.ObjBound if model.IsMIP else inc
        rows.append(dict(scientific_group=group,component=name,status=model.Status,incumbent=inc,bound=bound,relative_gap=relative_gap(inc,bound),integer_exact_certificate=integer_certificate(inc,bound) if name=='movement_count' else None,solve_seconds=model.Runtime,nodes=model.NodeCount))
        if model.SolCount:
            saved=dict(values={v.VarName:float(v.X) for v in model.getVars()},objectives={n:float(gp.LinExpr(x).getValue()) for _,n,x in ordered},lex_complete=False,
                scientific_objective_count=2,scientific_groups=['MAX_LINE_LOADING','MIN_INTERVENTION'],
                report_only_metrics=dict(raw_reserve_shortfall=float(gp.LinExpr(objectives[1][1]).getValue())))
        if model.Status!=gp.GRB.OPTIMAL:break
        if len(rows)==len(ordered):saved['lex_complete']=True
        else:model.addConstr(expr<=inc+(P1_EPS if name=='rho' else COMPONENT_EPS),name='final_objective_lock_'+name)
    return saved,dict(passes=rows,scientific_objective_count=2,solve_wall_seconds=perf_counter()-begin,warm_start_values_applied=applied,**deadline.receipt())


def solve(*args,unit_test=False,**kwargs):
    """Process-local adapter. Each independent campaign case owns a process."""
    if not unit_test:
        from v42_root.common import OUT,read
        result=read(OUT/'TWO_OBJECTIVE_A1_OPTIMIZATION.json')
        if not result['complete'] or not result['physical_PASS']:raise ValueError('CORRECTED_A1_GATE_NOT_ACCEPTED')
    import v42_native.mess as native
    old=native.optimize;native.optimize=optimize
    try:return native.solve(*args,**kwargs)
    finally:native.optimize=old
