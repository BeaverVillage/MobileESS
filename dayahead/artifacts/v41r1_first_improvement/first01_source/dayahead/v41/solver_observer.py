"""Read-only Gurobi pass receipts, also installed in the existing M1 worker."""
from contextlib import contextmanager
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
import math
import os
import time
import uuid

from dayahead.paper_analysis.storage import write_json

_root = None
_stage = None
_original = None


def finite(value):
    value = float(value)
    return value if math.isfinite(value) else None


def install(root, stage):
    import gurobipy as gp
    global _root, _stage, _original
    _root = Path(root); _stage = stage
    if gp.Model.optimize is not observed:
        _original = gp.Model.optimize
        gp.Model.optimize = observed


def observed(model, *args, **kwargs):
    import gurobipy as gp
    # User-authorized campaign-wide operational settings, including M1 children.
    model.Params.MemLimit=gp.GRB.INFINITY;model.Params.SoftMemLimit=gp.GRB.INFINITY
    model.Params.Threads=4;model.Params.NodefileStart=.5
    node_dir=_root/'gurobi_nodefiles';node_dir.mkdir(parents=True,exist_ok=True)
    model.Params.NodefileDir=str(node_dir.resolve())
    started = time.perf_counter()
    token = uuid.uuid4().hex
    try:
        return _original(model, *args, **kwargs)
    finally:
        import gurobipy as gp
        row = dict(schema='V41_SOLVER_PASS_V1', pid=os.getpid(), stage=_stage,
                   wallclock_seconds=time.perf_counter()-started, observation_only=True)
        try:
            incumbent = bool(model.SolCount)
            row.update(model_name=model.ModelName, status=int(model.Status), solution_count=int(model.SolCount),
                bound_scope=getattr(model,'_v41_bound_scope','MODEL_AS_BUILT; CHECK_STAGE_APPLICABILITY'),
                objective_expression=str(model.getObjective()), objective_value=finite(model.ObjVal) if incumbent else None,
                best_value=finite(model.ObjVal) if incumbent else None, best_bound=finite(model.ObjBound),
                solver_runtime_seconds=finite(model.Runtime), work=finite(model.Work), node_count=finite(model.NodeCount),
                iteration_count=finite(model.IterCount), barrier_iteration_count=int(model.BarIterCount),
                mip_gap=finite(model.MIPGap) if model.IsMIP and incumbent else None,
                configuration={k: getattr(model.Params, k) for k in ('Threads', 'Seed', 'FeasibilityTol',
                    'IntFeasTol', 'OptimalityTol', 'MIPGap', 'MIPGapAbs', 'WorkLimit', 'TimeLimit', 'MemLimit', 'SoftMemLimit', 'NodefileStart', 'NodefileDir')},
                active_freeze_constraints=[dict(name=c.ConstrName, sense=c.Sense, rhs=finite(c.RHS),
                    lhs=str(model.getRow(c))) for c in model.getConstrs()
                    if 'LOCK' in c.ConstrName or 'EXACT_CAP' in c.ConstrName or 'EXACT_PRIMARY_NUMERIC_ROW' in c.ConstrName])
        except gp.GurobiError as error:
            row['observation_error'] = str(error)
        from .scientific_archive import native
        write_json(_root / f'{os.getpid()}_{time.time_ns()}_{token}.json', native(row))


def initialize_worker(root, initializer, initargs):
    install(root, 'M1')
    from dayahead.v39e.runtime import initialize_runtime_worker
    initialize_runtime_worker(initializer, initargs)


class ObservedPool(ProcessPoolExecutor):
    def __init__(self, max_workers=None, *, initializer=None, initargs=(), **kwargs):
        # Identical to the inherited ObservedProductionPool: one process and
        # the same four-thread model/runtime initializer.
        super().__init__(max_workers=1, initializer=initialize_worker,
                         initargs=(str(_root), initializer, initargs), **kwargs)


@contextmanager
def observe(root, stage):
    import gurobipy as gp
    from dayahead.v40a import observability
    global _root, _stage, _original
    before = (gp.Model.optimize, observability.ObservedProductionPool, _root, _stage, _original)
    install(root, stage); observability.ObservedProductionPool = ObservedPool
    try:
        yield
    finally:
        gp.Model.optimize, observability.ObservedProductionPool, _root, _stage, _original = before
