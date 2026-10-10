"""5,400 seconds of measured Native Runtime; other work is timed separately."""
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter, process_time
import math
from .common import atomic, now, d_path
from .execution import native_scope, guard


class BudgetStop(TimeoutError):
    pass


class DateBudget:
    def __init__(self, path, *, started=None, clock=perf_counter, wall_limit=None, native_limit=5400.,
                 final_reserve=0., progress=None):
        self.path = d_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise PermissionError('NEW_DATE_LEDGER_ONLY')
        self.clock = clock
        self.started = clock() if started is None else started
        self.wall_limit, self.native_limit, self.final_reserve = wall_limit, native_limit, final_reserve
        self.calls, self.costs, self.admission_failures, self.inflight = [], [], [], None
        self.progress, self.latest = progress or (lambda value: None), {}
        self.native_used = 0.
        self.persist()

    def wall(self):
        return max(0., self.clock() - self.started)

    def used(self):
        return self.native_used

    def remaining(self, reserve=None):
        return max(0., self.native_limit - self.native_used)

    def check(self, reserve=0):
        if self.native_used > self.native_limit:
            raise BudgetStop('NATIVE_RUNTIME_CEILING_EXCEEDED')

    def charge(self, runtime):
        if not math.isfinite(float(runtime)) or runtime < 0:
            raise ValueError('NONFINITE_NATIVE_RUNTIME')
        self.native_used += float(runtime)
        self.persist()
        if self.native_used > self.native_limit:
            raise BudgetStop('NATIVE_RUNTIME_CEILING_EXCEEDED')

    def snapshot(self):
        return dict(Native_Runtime=self.native_used + self.latest.get('Runtime', 0),
                    Native_Runtime_completed=self.native_used, Wall_Time=self.wall(),
                    remaining_seconds=max(0., self.native_limit - self.native_used - self.latest.get('Runtime', 0)),
                    native_remaining_seconds=max(0., self.native_limit - self.native_used - self.latest.get('Runtime', 0)),
                    wall_limit_seconds=None, budget_basis='MEASURED_NATIVE_RUNTIME_ONLY',
                    inflight=self.inflight is not None, Work=sum(r.get('Native_Work') or 0 for r in self.calls))

    def persist(self):
        atomic(self.path, dict(wall_ceiling_seconds=None, Native_ceiling_seconds=self.native_limit,
            policy_version='NATIVE90_V2', budget_basis='MEASURED_NATIVE_RUNTIME_ONLY',
            inclusive_T0=self.started, UTC=now(), wall_seconds=self.wall(), measured_Native_Runtime=self.native_used,
            calls=self.calls, costs=self.costs, admission_failures=self.admission_failures,
            inflight=self.inflight, P2_calls=0, historical_costs_reused=False))

    @contextmanager
    def cost(self, kind, label, *, track=None):
        start, cpu, first = self.clock(), process_time(), len(self.calls)
        try:
            yield
        finally:
            elapsed = self.clock() - start
            nested = sum(r.get('optimize_wall_seconds', 0) for r in self.calls[first:])
            self.costs.append(dict(kind=kind, label=label, track=track,
                wall_seconds=elapsed, CPU_seconds=process_time() - cpu,
                exclusive_non_native_wall_seconds=max(0., elapsed - nested), nested_costs_may_overlap=True))
            self.persist()

    def optimize(self, model, *, track, label, requested_seconds, callback=None):
        return self.native_optimize(model, callback, component='P1', track=track,
                                    label=label, requested_seconds=requested_seconds)

    def native_optimize(self, model, callback=None, *, component='P1', track='A', label='', requested_seconds=5400.):
        self.check(self.final_reserve)
        if any(r.get('runtime_unavailable') for r in self.calls):
            raise RuntimeError('UNMEASURED_RUNTIME_QUARANTINE')
        if type(requested_seconds) not in (int, float):
            raise ValueError('FINITE_POSITIVE_REQUESTED_NATIVE_CAP_REQUIRED')
        try:
            requested_cap = float(requested_seconds)
        except OverflowError:
            raise ValueError('FINITE_POSITIVE_REQUESTED_NATIVE_CAP_REQUIRED') from None
        if not math.isfinite(requested_cap) or requested_cap <= 0:
            raise ValueError('FINITE_POSITIVE_REQUESTED_NATIVE_CAP_REQUIRED')
        limit = min(requested_cap, self.remaining())
        if limit <= 0:
            raise BudgetStop('DATE_NATIVE_RUNTIME_BUDGET_EXHAUSTED')
        model.Params.Threads = 1
        model.Params.TimeLimit = limit
        native_temp = d_path(self.path.parent / 'tmp' / 'gurobi')
        native_temp.mkdir(parents=True, exist_ok=True)
        model.Params.NodefileDir = str(native_temp)
        model.Params.LogFile = str(self.path.parent / f'{len(self.calls):04d}_{track}_{component}_NATIVE.log')
        start = self.clock()
        row = dict(component=component, track=track, label=label, requested_seconds=requested_seconds,
                   requested_cap_policy='MIN_VALID_REQUESTED_SECONDS_AND_REMAINING_NATIVE_V1',
                   effective_TimeLimit=limit, started_wall_seconds=self.wall(), UTC=now(), status='IN_FLIGHT')
        self.inflight = row; self.latest = {}; self.persist()
        error = None; entered_native = False
        last_progress = [-float('inf')]
        import gurobipy as gp
        def observe(m, where):
            if where != gp.GRB.Callback.POLLING:
                try:
                    self.latest = dict(Runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME)))
                    if self.latest['Runtime'] >= limit:
                        m.terminate()
                    if self.clock() - last_progress[0] >= 1.:
                        self.progress(dict(phase=component, **self.snapshot()))
                        last_progress[0] = self.clock()
                except gp.GurobiError:
                    pass
            if callback is not None:
                callback(m, where)
        try:
            with native_scope(model, component, track):
                guard(model)
                entered_native = True
                model.optimize(observe)
        except BaseException as exc:
            error = str(exc)
            raise
        finally:
            def attr(key, default=None):
                try:
                    return getattr(model, key)
                except (gp.GurobiError, AttributeError):
                    return default
            self.inflight = None; self.latest = {}
            if not entered_native:
                # Reused pricing models can still expose the previous solve's
                # Runtime/bound. A denied admission performed no Native call.
                row.update(status='ADMISSION_DENIED', error=error, entered_native=False,
                    Native_Runtime=0., admission_wall_seconds=self.clock() - start,
                    finished_wall_seconds=self.wall())
                self.admission_failures.append(row); self.persist()
                self.progress(dict(phase=component, admission_denied=True, **self.snapshot()))
            else:
                runtime = attr('Runtime')
                unknown = runtime is None or not math.isfinite(float(runtime)) or runtime < 0
                consumed = None if unknown else float(runtime)
                row.update(status='FAILED' if error else 'FINISHED', error=error, entered_native=True,
                    Native_Runtime=consumed, runtime_unavailable=unknown, Native_Work=attr('Work'),
                    Native_status=attr('Status'), SolCount=attr('SolCount', 0), Native_BestBd=attr('ObjBound'),
                    optimize_wall_seconds=self.clock() - start, finished_wall_seconds=self.wall())
                self.calls.append(row)
                if consumed is not None:
                    self.charge(consumed)
                else:
                    self.persist()
                self.progress(dict(phase=component, Native_BestBd=row['Native_BestBd'], **self.snapshot()))
                if unknown:
                    raise RuntimeError('NATIVE_RUNTIME_UNAVAILABLE_QUARANTINE')
