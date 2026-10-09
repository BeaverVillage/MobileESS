"""Mandatory Runtime accounting is persisted ahead of optional diagnostics."""
import math
from time import perf_counter
from v42_b2_seed_recovery_v18.budget import DateBudget as OriginalBudget,BudgetStop
from .common import now,d_path,atomic
from .execution import native_scope,guard

class DateBudget(OriginalBudget):
    def __init__(self,path,*,started=None,clock=perf_counter,wall_limit=None,native_limit=5400.,final_reserve=0.,progress=None):
        self.path=d_path(path);self.path.parent.mkdir(parents=True,exist_ok=True)
        if self.path.exists():raise PermissionError('NEW_DATE_LEDGER_ONLY')
        self.clock=clock;self.started=clock() if started is None else started
        self.wall_limit,self.native_limit,self.final_reserve=wall_limit,native_limit,final_reserve
        self.calls,self.costs,self.admission_failures,self.inflight=[],[],[],None
        self.progress,self.latest=progress or (lambda value:None),{}
        self.native_used=0.;self.prior_attempt=None
        from .execution import current
        context=current() or {};request=context.get('request',{})
        receipt=context.get('manifest',{}).get('prior_attempts',{}).get(request.get('day'))
        if receipt:
            from .policy import prior_runtime
            self.native_used=prior_runtime(receipt,root=request['root'],day=request['day'])
            self.prior_attempt=dict(receipt,point_or_bound_transferred=False,date_runtime_reset=False)
        self.persist()

    def conservative(self):
        return (self.prior_attempt or {}).get('budget_basis')=='CONSERVATIVE_LOST_CALL_WINDOW'

    def persist(self):
        super().persist()
        if self.conservative():
            from .common import read
            value=read(self.path)
            value.update(measured_Native_Runtime=None,actual_cumulative_Native_Runtime='UNKNOWN',
                budget_basis='CONSERVATIVE_LOST_CALL_WINDOW',Native_budget_accounted_upper_bound=self.native_used,
                current_attempt_measured_Native_Runtime=sum(c.get('Native_Runtime') or 0 for c in self.calls),
                known_prior_measured_Native_Runtime=self.prior_attempt['known_measured_prior']['Native_Runtime'])
            atomic(self.path,value)

    def snapshot(self):
        value=super().snapshot()
        if self.conservative():
            value.update(Native_Runtime=None,Native_Runtime_completed=None,
                Native_budget_accounted_upper_bound=self.native_used+self.latest.get('Runtime',0),
                budget_basis='CONSERVATIVE_LOST_CALL_WINDOW',actual_cumulative_Native_Runtime='UNKNOWN',
                current_attempt_measured_Native_Runtime=sum(c.get('Native_Runtime') or 0 for c in self.calls),
                lost_call_reserved_seconds=self.prior_attempt['lost_call_reserved_seconds'])
        if any(r.get('runtime_unavailable') for r in self.calls):
            value.update(Native_Runtime=None,Native_Runtime_completed=self.native_used,
                remaining_seconds=None,native_remaining_seconds=None,Native_budget_status='QUARANTINE')
        return value

    def native_optimize(self, model, callback=None, *, component='P1', track='A', label='', requested_seconds=None):
        self.check(self.final_reserve)
        if any(r.get('runtime_unavailable') for r in self.calls):
            raise RuntimeError('UNMEASURED_RUNTIME_QUARANTINE')
        from .execution import current
        from .numerical import set_precision
        from .native_diagnostics import empty, observe as observe_native, finished
        context = current()
        if context is None:
            raise PermissionError('V13_PRECISION_REQUIRES_WORKER_SCOPE')
        request = context['request']
        limit = self.remaining()
        if request['arm'] == 'B2' and requested_seconds is not None:
            if isinstance(requested_seconds, bool) or not math.isfinite(float(requested_seconds)) or requested_seconds <= 0:
                raise ValueError('B2_POSITIVE_FINITE_REQUESTED_SECONDS_REQUIRED')
            limit = min(limit, float(requested_seconds))
        if limit <= 0:
            raise BudgetStop('DATE_NATIVE_RUNTIME_BUDGET_EXHAUSTED')
        precision = set_precision(model, day=request['day'], component=component, arm=request['arm'])
        model.Params.Threads = 1
        model.Params.TimeLimit = limit
        native_temp = d_path(self.path.parent / 'tmp' / 'gurobi')
        native_temp.mkdir(parents=True, exist_ok=True)
        model.Params.NodefileDir = str(native_temp)
        model.Params.LogFile = str(self.path.parent / f'{len(self.calls):04d}_{track}_{component}_NATIVE.log')
        start = self.clock()
        row = dict(component=component, track=track, label=label, requested_seconds=requested_seconds,
                   precision_policy='B2_SEED_RECOVERY_V18R3', precision_parameters=precision,
                   effective_TimeLimit=limit, started_wall_seconds=self.wall(), UTC=now(), status='IN_FLIGHT')
        if request['arm'] == 'B2':
            row.update(time_limit_policy='B2_REQUEST_CAPPED_BY_REMAINING_NATIVE',
                       effective_MIPGap=float(model.Params.MIPGap))
        self.inflight = row; self.latest = {}; self.persist()
        diagnostics = empty()
        self.progress(dict(phase=component, **diagnostics, **self.snapshot()))
        error = None; entered_native = False
        last_progress = [-float('inf')]
        import gurobipy as gp
        def observe(m, where):
            if where != gp.GRB.Callback.POLLING:
                try:
                    self.latest = dict(Runtime=float(m.cbGet(gp.GRB.Callback.RUNTIME)))
                    if self.latest['Runtime'] >= limit:
                        m.terminate()
                    if where == gp.GRB.Callback.MIPSOL or self.clock() - last_progress[0] >= 1.:
                        diagnostics.update(observe_native(m, where, gp))
                        if diagnostics.get('Native_first_incumbent_Runtime', 'UNKNOWN') == 'UNKNOWN' and diagnostics.get('Native_incumbent', 'UNKNOWN') != 'UNKNOWN':
                            diagnostics.update(Native_first_incumbent_Runtime=self.latest['Runtime'],
                                Native_first_incumbent_UTC=now(), Native_first_incumbent_source='FIRST_CALLBACK_OBSERVATION_NOT_FULL_CERTIFICATE')
                        self.progress(dict(phase=component, **diagnostics, **self.snapshot()))
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
                # Persist Runtime BEFORE optional diagnostic extraction/merging.
                row.update(status='FAILED' if error else 'FINISHED',error=error,entered_native=True,
                    Native_Runtime=consumed,runtime_unavailable=unknown,
                    optimize_wall_seconds=self.clock()-start,finished_wall_seconds=self.wall())
                self.calls.append(row)
                if consumed is not None:self.native_used+=consumed
                self.persist()
                final_diagnostics=dict(diagnostics)
                try:
                    final_diagnostics.update(finished(model,gp))
                    row.update(final_diagnostics)
                    row.update(Native_Work=attr('Work'),Native_status=attr('Status'))
                except Exception as diagnostic_error:
                    row['diagnostic_error']=repr(diagnostic_error)
                self.persist()
                self.progress(dict(phase=component,**final_diagnostics,**self.snapshot()))
                if unknown:raise RuntimeError('NATIVE_RUNTIME_UNAVAILABLE_QUARANTINE')
                self.check()
