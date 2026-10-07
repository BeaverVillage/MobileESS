"""Passive later-run instrumentation; no optimize, relax, or method probes."""
from math import isfinite
from time import perf_counter


NATIVE_SETTINGS = ('Method', 'Crossover', 'NumericFocus', 'ScaleFlag',
    'BarHomogeneous', 'Presolve', 'Threads', 'Seed', 'FeasibilityTol',
    'OptimalityTol', 'IntFeasTol')
RANGE_ATTRIBUTES = ('NumVars', 'NumConstrs', 'NumNZs', 'NumBinVars', 'NumIntVars',
    'MaxCoeff', 'MinCoeff', 'MaxBound', 'MinBound', 'MaxRHS', 'MinRHS',
    'MaxObjCoeff', 'MinObjCoeff')
POST_ATTRIBUTES = ('Runtime', 'Work', 'IterCount', 'BarIterCount', 'NodeCount',
    'Kappa', 'ConstrVio', 'BoundVio', 'IntVio', 'DualVio', 'ComplVio')


def native_scalar(obj, name):
    try:
        value = float(getattr(obj, name))
        return value if isfinite(value) and abs(value) < 1e99 else None
    except Exception:
        # Unsupported/unavailable solver attributes remain unavailable.
        return None


class FutureRunTelemetry:
    def __init__(self, model, *, day=None, sample_interval=1., max_samples=1024):
        self.day = day
        self.started = perf_counter()
        self.samples = []
        self.passes = []
        self.max_samples = max_samples
        self.sample_interval = sample_interval
        self.last_sample = -1.
        self.dropped_samples = 0
        self.active = None
        self.before = dict(matrix_geometry={k: native_scalar(model, k) for k in RANGE_ATTRIBUTES},
            solver_settings={k: native_scalar(model.Params, k) for k in NATIVE_SETTINGS})

    def begin_objective(self, name, *, group=None, remaining_seconds=None):
        self.active = dict(objective=name, group=group,
            begin_wall_seconds=perf_counter()-self.started,
            cumulative_native_seconds=sum(p.get('native_seconds') or 0. for p in self.passes),
            available_seconds=remaining_seconds)
        self.objective_started = perf_counter()
        self.last_sample = -1.

    def callback(self, model, where, GRB):
        if self.active is None:
            return
        names = {
            GRB.Callback.SIMPLEX: ('SIMPLEX', ('SPX_ITRCNT', 'SPX_OBJVAL', 'SPX_PRIMINF', 'SPX_DUALINF')),
            GRB.Callback.BARRIER: ('BARRIER', ('BARRIER_ITRCNT', 'BARRIER_PRIMINF', 'BARRIER_DUALINF', 'BARRIER_COMPL')),
            GRB.Callback.MIPNODE: ('MIPNODE', ('MIPNODE_NODCNT', 'MIPNODE_STATUS', 'MIPNODE_OBJBND')),
        }
        if where not in names:
            return
        elapsed = perf_counter()-self.objective_started
        if elapsed-self.last_sample < self.sample_interval:
            return
        label, attributes = names[where]
        row = dict(objective=self.active['objective'], group=self.active['group'],
            callback_kind=label, objective_wall_seconds=elapsed,
            total_wall_seconds=perf_counter()-self.started)
        for name in attributes:
            try:
                value = float(model.cbGet(getattr(GRB.Callback, name)))
                row[name] = value if isfinite(value) and abs(value) < 1e99 else None
            except Exception:
                row[name] = None
        row['root_node_confirmed'] = label == 'MIPNODE' and row.get('MIPNODE_NODCNT') == 0
        self.last_sample = elapsed
        if len(self.samples) < self.max_samples:
            self.samples.append(row)
        else:
            self.dropped_samples += 1

    def finish_objective(self, model):
        row = dict(self.active, wall_seconds=perf_counter()-self.objective_started,
            native_seconds=native_scalar(model, 'Runtime'),
            numerical_quality={k: native_scalar(model, k) for k in POST_ATTRIBUTES})
        self.passes.append(row)
        self.active = None
        return row

    def receipt(self):
        return dict(day=self.day, prepared_for_future_runs=True,
            matrix_geometry=self.before['matrix_geometry'], solver_settings=self.before['solver_settings'],
            objective_stage_timings=self.passes, root_and_solver_observations=self.samples,
            dropped_samples=self.dropped_samples, synthetic_root_duration_claimed=False,
            exact_condition_number_computed=False, solver_methods_changed=False,
            extra_relaxations_or_optimization_calls=0,
            note='Simplex/barrier callback observations do not isolate root LP time; Kappa is null without an available basis. KappaExact is not computed.')

