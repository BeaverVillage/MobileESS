"""Shared bounded lex solve, structural MILP audit, and observable warm starts."""
from collections import Counter
from time import perf_counter
import gurobipy as gp
from gurobipy import GRB
from .contracts import require
from v42_a_stage_domain_v2.execution import guard_model_optimize,day_from_authority,tag_model_for_day
from v42_a_stage_domain_v2.status import initial_domain_status
from v42_a_stage_domain_v2.telemetry import FutureRunTelemetry


def size(model):
    model.update()
    return dict(binary=model.NumBinVars,integer=model.NumIntVars-model.NumBinVars,
        continuous=model.NumVars-model.NumIntVars,linear_constraints=model.NumConstrs,
        quadratic_constraints=model.NumQConstrs,SOS=model.NumSOS,general_constraints=model.NumGenConstrs,
        quadratic_objective_terms=model.getObjective().size() if isinstance(model.getObjective(),gp.QuadExpr) else 0,
        nonzeros=model.NumNZs,constraint_families=dict(Counter(c.ConstrName.split('[')[0] for c in model.getConstrs())))


def assert_milp(model):
    s=size(model)
    require(not any(s[k] for k in ('quadratic_constraints','quadratic_objective_terms','SOS','general_constraints')),'HIDDEN_NON_MILP_TERM')
    return s


def optimize(model, objectives, deadline, incumbent=None, *, diagnostic_quadratic=False, progress=None):
    """Each objective pair is (name, expression). One wall budget across levels.

    A non-optimal solve preserves its incumbent/bound and stops lex refinement;
    it never invents an optimum or silently resets the time budget.
    """
    guard_model_optimize(model)
    day=day_from_authority(deadline)
    if day is not None:tag_model_for_day(model,day)
    guard_model_optimize(model)
    deadline.check();model.update()
    diagnostics=FutureRunTelemetry(model,day=getattr(model,'_v42_a_stage_day',None))
    domain_status=dict(getattr(model,'_v42_domain_status',initial_domain_status()))
    applied=0
    if incumbent is not None:
        for v in model.getVars():
            if v.VarName in incumbent['values']:
                v.Start=incumbent['values'][v.VarName];applied+=1
    events=dict(first_incumbent_seconds=None,root_relaxation_first_observed_seconds=None,
        root_relaxation_bound=None,presolve_last_observed_seconds=None,presolve_removed_rows=0,presolve_removed_columns=0,
        warm_start_accepted=False,warm_start_initial_objective=None)
    messages=[];passes=[];saved=None;started=perf_counter();last_progress=[-1.]
    def callback(m,where):
        diagnostics.callback(m,where,GRB)
        now=perf_counter()-started
        if where==GRB.Callback.MESSAGE:
            message=m.cbGet(GRB.Callback.MSG_STRING).strip()
            if 'MIP start' in message:
                messages.append(message)
                if 'Loaded user MIP start with objective' in message or 'User MIP start produced solution with objective' in message:
                    events['warm_start_accepted']=True
                    try:
                        if events['warm_start_initial_objective'] is None:events['warm_start_initial_objective']=float(message.split('objective')[1].split()[0])
                    except (ValueError,IndexError):pass
        elif where==GRB.Callback.PRESOLVE:
            events['presolve_last_observed_seconds']=now
            events['presolve_removed_rows']=int(m.cbGet(GRB.Callback.PRE_ROWDEL))
            events['presolve_removed_columns']=int(m.cbGet(GRB.Callback.PRE_COLDEL))
        elif where==GRB.Callback.MIPSOL and events['first_incumbent_seconds'] is None:
            events['first_incumbent_seconds']=now
        elif where==GRB.Callback.MIPNODE and m.cbGet(GRB.Callback.MIPNODE_NODCNT)==0:
            if events['root_relaxation_first_observed_seconds'] is None:events['root_relaxation_first_observed_seconds']=now
            events['root_relaxation_bound']=float(m.cbGet(GRB.Callback.MIPNODE_OBJBND))
        if progress is not None and where in (GRB.Callback.MIPSOL,GRB.Callback.MIPNODE) and (now-last_progress[0]>=.5 or last_progress[0]<0):
            raw=dict(events,elapsed_seconds=now,scientific_acceptance=False)
            if where==GRB.Callback.MIPSOL:
                raw.update(raw_incumbent_values=dict(zip((v.VarName for v in m.getVars()),m.cbGetSolution(m.getVars()))),
                    objective=float(m.cbGet(GRB.Callback.MIPSOL_OBJ)),bound=float(m.cbGet(GRB.Callback.MIPSOL_OBJBND)),
                    nodes=float(m.cbGet(GRB.Callback.MIPSOL_NODCNT)))
            else:
                raw.update(objective=float(m.cbGet(GRB.Callback.MIPNODE_OBJBST)),
                    bound=float(m.cbGet(GRB.Callback.MIPNODE_OBJBND)),nodes=float(m.cbGet(GRB.Callback.MIPNODE_NODCNT)))
            raw['objective_level']=objectives[len(passes)][0]
            raw['gap']=abs(raw['objective']-raw['bound'])/max(abs(raw['objective']),1e-10)
            progress(raw);last_progress[0]=now
        if deadline.remaining<=0:m.terminate()
    model.Params.Threads=1;model.Params.Seed=20260929;model.Params.MIPGap=0
    # MESSAGE callback receives diagnostics while console remains silent.
    model.Params.OutputFlag=1;model.Params.LogToConsole=0
    try:
        for name,obj in objectives:
            deadline.check();model.setObjective(obj,GRB.MINIMIZE);model.update()
            if not diagnostic_quadratic:assert_milp(model)
            model.Params.TimeLimit=deadline.remaining
            diagnostics.begin_objective(name,remaining_seconds=deadline.remaining)
            model.optimize(callback)
            diagnostics.finish_objective(model)
            row=dict(level=name,status=model.Status,solve_seconds=model.Runtime,nodes=model.NodeCount,
                objective=float(model.ObjVal) if model.SolCount else None,
                bound=float(model.ObjBound) if model.IsMIP else (float(model.ObjVal) if model.SolCount else None),
                gap=float(model.MIPGap) if model.IsMIP and model.SolCount else (0. if model.SolCount else None))
            passes.append(row)
            if model.SolCount:
                saved=dict(values={v.VarName:float(v.X) for v in model.getVars()},
                           objectives={n:float(gp.LinExpr(o).getValue()) for n,o in objectives},
                           lex_complete=False)
                saved['domain_status']=dict(domain_status)
                saved['scientific_full_domain_optimal']=False
            if model.Status!=GRB.OPTIMAL:break
            if len(passes)==len(objectives):saved['lex_complete']=True
            tolerance=1e-7 if name=='rho' else 1e-8
            model.addConstr(obj<=model.ObjVal+tolerance,name='objective_lock['+name+']')
    except TimeoutError:
        pass
    receipt=dict(**events,warm_start_values_applied=applied,warm_start_messages=messages,
        domain_status=domain_status,scientific_full_domain_optimal=False,future_run_diagnostics=diagnostics.receipt(),
        passes=passes,solve_wall_seconds=perf_counter()-started,model_size=size(model),
        root_timing_note='Callback first root observation, not an invented isolated root-LP duration; null if presolve solves model',
        warm_start_node_reduction=None,warm_start_node_reduction_reason='No second native cold run authorized; no causal speedup claimed',
        **deadline.receipt())
    return saved,receipt
