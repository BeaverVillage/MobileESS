"""One inclusive wall clock and measured Native ledger for each date/arm."""
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter, process_time
import math
from .common import atomic, now, d_path
from .execution import native_scope, guard


class BudgetStop(TimeoutError):
    pass


class DateBudget:
    def __init__(self, path, *, started=None, clock=perf_counter, wall_limit=5400., native_limit=5400.,
                 final_reserve=300., progress=None):
        self.path = d_path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            raise PermissionError('NEW_DATE_LEDGER_ONLY')
        self.clock = clock
        self.started = clock() if started is None else started
        self.wall_limit, self.native_limit, self.final_reserve = wall_limit, native_limit, final_reserve
        self.calls, self.costs, self.inflight = [], [], None
        self.progress, self.latest = progress or (lambda value: None), {}
        self.native_used = 0.
        self.persist()

    def wall(self):
        return max(0., self.clock() - self.started)

    def used(self):
        return self.native_used

    def remaining(self, reserve=None):
        reserve = self.final_reserve if reserve is None else reserve
        return max(0., min(self.native_limit - self.native_used, self.wall_limit - self.wall() - reserve))

    def check(self, reserve=0):
        if self.wall() + reserve >= self.wall_limit or self.native_used >= self.native_limit:
            raise BudgetStop('DATE_WALL_OR_NATIVE_BUDGET_EXHAUSTED')

    def charge(self, runtime):
        if not math.isfinite(float(runtime)) or runtime < 0:
            raise ValueError('NONFINITE_NATIVE_RUNTIME')
        self.native_used += float(runtime)
        self.persist()
        if self.native_used > self.native_limit + 1e-6:
            raise BudgetStop('NATIVE_RUNTIME_CEILING_EXCEEDED')

    def snapshot(self):
        return dict(Native_Runtime=self.native_used + self.latest.get('Runtime', 0),
                    Native_Runtime_completed=self.native_used, Wall_Time=self.wall(),
                    remaining_seconds=max(0., self.wall_limit - self.wall()),
                    inflight=self.inflight is not None, Work=sum(r.get('Native_Work') or 0 for r in self.calls))

    def persist(self):
        atomic(self.path, dict(wall_ceiling_seconds=self.wall_limit, Native_ceiling_seconds=self.native_limit,
            inclusive_T0=self.started, UTC=now(), wall_seconds=self.wall(), measured_Native_Runtime=self.native_used,
            calls=self.calls, costs=self.costs, inflight=self.inflight, P2_calls=0, historical_costs_reused=False))

    @contextmanager
    def cost(self, kind, label, *, track=None):
        start, cpu = self.clock(), process_time()
        try:
            yield
        finally:
            self.costs.append(dict(kind=kind, label=label, track=track,
                wall_seconds=self.clock() - start, CPU_seconds=process_time() - cpu))
            self.persist()

    def optimize(self, model, *, track, label, requested_seconds, callback=None):
        return self.native_optimize(model, callback, component='P1', track=track,
                                    label=label, requested_seconds=requested_seconds)

    def native_optimize(self, model, callback=None, *, component='P1', track='A', label='', requested_seconds=None):
        self.check(self.final_reserve)
        if any(r.get('runtime_unavailable') for r in self.calls):
            raise BudgetStop('UNMEASURED_RUNTIME_QUARANTINE')
        limit = min(self.remaining(), float(requested_seconds) if requested_seconds is not None else self.remaining())
        if limit < 1:
            raise BudgetStop('FINAL_VERIFICATION_RESERVE_REQUIRED')
        model.Params.Threads = 1
        model.Params.TimeLimit = limit
        model.Params.LogFile = str(self.path.parent / f'{len(self.calls):04d}_{track}_{component}_NATIVE.log')
        start = self.clock()
        row = dict(component=component, track=track, label=label, requested_seconds=requested_seconds,
                   effective_TimeLimit=limit, started_wall_seconds=self.wall(), UTC=now(), status='IN_FLIGHT')
        self.inflight = row; self.latest = {}; self.persist()
        error = None
        last_progress = [-float('inf')]
        import gurobipy as gp
        def observe(m, where):
            if where != gp.GRB.Callback.POLLING:
                try:
                    self.latest = dict(Runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME)))
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
            runtime = attr('Runtime')
            unknown = runtime is None or not math.isfinite(float(runtime)) or runtime < 0
            consumed = limit if unknown else float(runtime)
            row.update(status='FAILED' if error else 'FINISHED', error=error, Native_Runtime=consumed,
                runtime_unavailable=unknown, Native_Work=attr('Work'), Native_status=attr('Status'),
                SolCount=attr('SolCount', 0), Native_BestBd=attr('ObjBound'),
                optimize_wall_seconds=self.clock() - start, finished_wall_seconds=self.wall())
            self.calls.append(row); self.inflight = None; self.latest = {}
            self.charge(consumed)
            self.progress(dict(phase=component, Native_BestBd=row['Native_BestBd'], **self.snapshot()))
