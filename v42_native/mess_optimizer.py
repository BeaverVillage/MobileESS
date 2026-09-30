"""MESS-only optimize budget; leaves AIDC/contracts/supervision unchanged."""
from time import perf_counter
import re
import gurobipy as gp
from gurobipy import GRB

from .contracts import require
from .solver import assert_milp, size

NATIVE_SECONDS = 1800.
NATIVE_GAP = .005


class OptimizeBudget:
    """One cumulative budget across lex levels, armed at first optimize()."""
    def __init__(self, stage, seconds=NATIVE_SECONDS, clock=perf_counter):
        require(stage in ('M1', 'M2') and 0 < seconds <= NATIVE_SECONDS, 'MESS_OPTIMIZE_BUDGET')
        self.stage, self.seconds, self.clock = stage, seconds, clock
        self.started = None

    def begin(self):
        require(self.started is None, 'MESS_BUDGET_ALREADY_USED')
        self.started = self.clock()

    @property
    def remaining(self):
        return self.seconds if self.started is None else max(0., self.seconds - (self.clock() - self.started))

    def check(self):
        if self.remaining <= 0:
            raise TimeoutError(self.stage + '_OPTIMIZE_DEADLINE')

    def receipt(self):
        elapsed = 0. if self.started is None else self.clock() - self.started
        return dict(stage=self.stage, budget_seconds=self.seconds, wall_seconds=elapsed,
                    deadline_exceeded=elapsed > self.seconds, budget_origin='FIRST_OPTIMIZE',
                    presolve_included=True, build_included=False)


def optimize(model, objectives, budget, incumbent=None, *, diagnostic_quadratic=False,
             progress=None, exact_diagnostic=False):
    model.update()
    applied = 0
    if incumbent is not None:
        # mess.validate_start has validated the COMPLETE physical trajectory.
        for v in model.getVars():
            require(v.VarName in incumbent['values'] or not v.VarName.startswith(
                ('arc[', 'charge_mode[', 'Pch[', 'Pdis[', 'Q[', 'SOC[')), 'INCOMPLETE_MESS_START')
            # Grid/AIDC anchors may change in M2. Only the validated MESS
            # physical variables transfer; Gurobi completes dynamic grid data.
            if v.VarName.startswith(('arc[', 'charge_mode[', 'Pch[', 'Pdis[', 'Q[', 'SOC[')):
                v.Start = incumbent['values'][v.VarName]
                applied += 1
    events = dict(first_incumbent_seconds=None, root_relaxation_first_observed_seconds=None,
                  root_relaxation_bound=None, presolve_last_observed_seconds=None,
                  presolve_removed_rows=0, presolve_removed_columns=0,
                  warm_start_accepted=False, warm_start_initial_objective=None)
    messages, passes, saved = [], [], None
    phases = dict(presolve_reported_seconds=None, root_relaxation_reported_seconds=None)
    last_progress = [-1.]

    def callback(m, where):
        now = budget.seconds - budget.remaining
        if where == GRB.Callback.MESSAGE:
            message = m.cbGet(GRB.Callback.MSG_STRING).strip()
            presolve = re.search(r'Presolve time: ([0-9.]+)s', message)
            root = re.search(r'Root relaxation:.* ([0-9.]+) seconds', message)
            if presolve:phases['presolve_reported_seconds'] = float(presolve.group(1))
            if root:phases['root_relaxation_reported_seconds'] = float(root.group(1))
            if 'MIP start' in message:
                messages.append(message)
                if ('Loaded user MIP start with objective' in message or
                        'User MIP start produced solution with objective' in message):
                    events['warm_start_accepted'] = True
                    if events['warm_start_initial_objective'] is None:
                        try:
                            events['warm_start_initial_objective'] = float(message.split('objective')[1].split()[0])
                        except (ValueError, IndexError):
                            pass
        elif where == GRB.Callback.PRESOLVE:
            events.update(presolve_last_observed_seconds=now,
                          presolve_removed_rows=int(m.cbGet(GRB.Callback.PRE_ROWDEL)),
                          presolve_removed_columns=int(m.cbGet(GRB.Callback.PRE_COLDEL)))
        elif where == GRB.Callback.MIPSOL and events['first_incumbent_seconds'] is None:
            events['first_incumbent_seconds'] = now
        elif where == GRB.Callback.MIPNODE and m.cbGet(GRB.Callback.MIPNODE_NODCNT) == 0:
            if events['root_relaxation_first_observed_seconds'] is None:
                events['root_relaxation_first_observed_seconds'] = now
            events['root_relaxation_bound'] = float(m.cbGet(GRB.Callback.MIPNODE_OBJBND))
        if progress is not None and where in (GRB.Callback.MIPSOL, GRB.Callback.MIPNODE) and (now - last_progress[0] >= .5 or last_progress[0] < 0):
            prefix = 'MIPSOL' if where == GRB.Callback.MIPSOL else 'MIPNODE'
            raw = dict(events, elapsed_seconds=now, scientific_acceptance=False,
                       objective=float(m.cbGet(getattr(GRB.Callback, prefix + ('_OBJ' if prefix == 'MIPSOL' else '_OBJBST')))),
                       bound=float(m.cbGet(getattr(GRB.Callback, prefix + '_OBJBND'))),
                       nodes=float(m.cbGet(getattr(GRB.Callback, prefix + '_NODCNT'))),
                       objective_level=objectives[len(passes)][0])
            if where == GRB.Callback.MIPSOL:
                raw['raw_incumbent_values'] = dict(zip((v.VarName for v in m.getVars()), m.cbGetSolution(m.getVars())))
            raw['gap'] = abs(raw['objective'] - raw['bound']) / max(abs(raw['objective']), 1e-10)
            progress(raw)
            last_progress[0] = now
        if budget.remaining <= 0:
            m.terminate()

    model.Params.Threads = 1
    model.Params.Seed = 20260929
    model.Params.MIPGap = 0 if exact_diagnostic else NATIVE_GAP
    if exact_diagnostic:
        model.Params.FeasibilityTol = 1e-9
        model.Params.OptimalityTol = 1e-9
        model.Params.IntFeasTol = 1e-9
    model.Params.LogToConsole = 0
    model.Params.OutputFlag = 1
    try:
        for name, obj in objectives:
            budget.check()
            phases.update(presolve_reported_seconds=None, root_relaxation_reported_seconds=None)
            model.setObjective(obj, GRB.MINIMIZE)
            model.update()
            if not diagnostic_quadratic:
                assert_milp(model)
            model.Params.TimeLimit = budget.remaining
            if budget.started is None:
                budget.begin()
            model.optimize(callback)
            passes.append(dict(level=name, status=model.Status, solve_seconds=model.Runtime,
                               nodes=model.NodeCount, objective=float(model.ObjVal) if model.SolCount else None,
                               bound=float(model.ObjBound) if model.IsMIP else (float(model.ObjVal) if model.SolCount else None),
                               gap=float(model.MIPGap) if model.IsMIP and model.SolCount else (0. if model.SolCount else None),
                               **phases))
            if model.SolCount:
                saved = dict(values={v.VarName: float(v.X) for v in model.getVars()},
                             objectives={n: float(gp.LinExpr(o).getValue()) for n, o in objectives}, lex_complete=False)
            if model.Status != GRB.OPTIMAL:
                break
            if len(passes) == len(objectives):
                saved['lex_complete'] = True
                break
            model.addConstr(obj <= model.ObjVal + (1e-7 if name == 'rho' else 1e-8), name='objective_lock[' + name + ']')
    except TimeoutError:
        pass
    receipt = dict(events, warm_start_values_applied=applied, warm_start_messages=messages,
                   passes=passes, solve_wall_seconds=budget.seconds - budget.remaining,
                   model_size=size(model), target_MIPGap=0 if exact_diagnostic else NATIVE_GAP,
                   root_timing_note='First root callback observation, not isolated LP time; null when unavailable',
                   branch_and_bound_seconds=None,
                   timing_limit='Gurobi Runtime per pass includes presolve/root/B&B; callbacks are observations, not additive phase durations',
                   **budget.receipt())
    return saved, receipt
