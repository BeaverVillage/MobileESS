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
        self.prior_attempt = None
        from .execution import current
        context = current()
        request = context['request'] if context else {}
        if request.get('arm') == 'B1' and request.get('day') == '2025-05-31' and request.get('manifest'):
            from .common import read, record
            manifest = read(request['manifest'])
            row = read(manifest['base_checkpoint']['path'])['dates']['B1/2025-05-31']
            previous = Path(row['result']).parent / 'NATIVE_RUNTIME_LEDGER.json'
            receipt = manifest['prior_native_ledger']
            if record(previous) != receipt:
                raise PermissionError('V12_PRIOR_DATE_NATIVE_LEDGER_SHA_DRIFT')
            ledger = read(previous)
            if ledger.get('inflight') is not None or any(c.get('runtime_unavailable') for c in ledger['calls']):
                raise PermissionError('V12_UNMEASURED_PRIOR_RUNTIME_REJECTED')
            self.native_used = float(ledger['measured_Native_Runtime'])
            if not math.isfinite(self.native_used) or not 0 <= self.native_used < native_limit:
                raise PermissionError('V12_NO_REMAINING_DATE_NATIVE_BUDGET')
            self.prior_attempt = dict(ledger=receipt, Native_Runtime=self.native_used,
                point_or_bound_transferred=False, date_runtime_reset=False)
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
            inflight=self.inflight, P2_calls=0, historical_costs_reused=False,
            prior_attempt=self.prior_attempt, date_runtime_reset=False))

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

    def native_optimize(self, model, callback=None, *, component='P1', track='A', label='', requested_seconds=None):
        self.check(self.final_reserve)
        if any(r.get('runtime_unavailable') for r in self.calls):
            raise RuntimeError('UNMEASURED_RUNTIME_QUARANTINE')
        limit = self.remaining()
        if limit <= 0:
            raise BudgetStop('DATE_NATIVE_RUNTIME_BUDGET_EXHAUSTED')
        from .execution import current
        from .numerical import set_precision
        context = current()
        if context is None:
            raise PermissionError('V12_PRECISION_REQUIRES_WORKER_SCOPE')
        request = context['request']
        precision = set_precision(model, day=request['day'], component=component, arm=request['arm'])
        model.Params.Threads = 1
        model.Params.TimeLimit = limit
        native_temp = d_path(self.path.parent / 'tmp' / 'gurobi')
        native_temp.mkdir(parents=True, exist_ok=True)
        model.Params.NodefileDir = str(native_temp)
        model.Params.LogFile = str(self.path.parent / f'{len(self.calls):04d}_{track}_{component}_NATIVE.log')
        start = self.clock()
        row = dict(component=component, track=track, label=label, requested_seconds=requested_seconds,
                   precision_policy='B2_FULL_VALIDATION_LIVE_WORKERS_RECOVERY_V12', precision_parameters=precision,
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
