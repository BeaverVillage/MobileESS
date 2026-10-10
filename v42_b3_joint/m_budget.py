"""Measured M-stage calls with requested limits and crash-safe diagnostics."""
import math
import importlib


def finite_diagnostic(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def native_optimize(self, model, callback=None, *, component="P1", track="M",
                    label="", requested_seconds=None):
    self.check()
    if self.inflight is not None or any(row.get("runtime_unavailable") for row in self.calls):
        raise RuntimeError("UNMEASURED_OR_INTERRUPTED_RUNTIME_QUARANTINE")
    limit = self.remaining()
    if requested_seconds is not None:
        if isinstance(requested_seconds, bool) or not math.isfinite(float(requested_seconds)) or requested_seconds <= 0:
            raise ValueError("M_POSITIVE_FINITE_REQUESTED_SECONDS_REQUIRED")
        limit = min(limit, float(requested_seconds))
    if limit <= 0:
        raise TimeoutError("M_NATIVE_RUNTIME_BUDGET_EXHAUSTED")
    model.Params.Threads, model.Params.TimeLimit = 1, limit
    folder = self.path.parent / "tmp" / "gurobi"
    folder.mkdir(parents=True, exist_ok=True)
    model.Params.NodefileDir = str(folder)
    model.Params.LogFile = str(self.path.parent / f"{len(self.calls):04d}_{track}_{component}_NATIVE.log")
    start = self.clock()
    row = dict(component=component, track=track, label=label, requested_seconds=requested_seconds,
        effective_TimeLimit=limit, started_wall_seconds=self.wall(), UTC=self._b3_now(), status="IN_FLIGHT",
        time_limit_policy="M_REQUEST_CAPPED_BY_REMAINING_NATIVE")
    self.inflight, self.latest = row, {}
    self.persist()
    error, entered = None, False
    gp = importlib.import_module("gurobipy")
    last_progress = [-math.inf]
    def observe(m, where):
        if where != gp.GRB.Callback.POLLING:
            try:
                runtime = float(m.cbGet(gp.GRB.Callback.RUNTIME))
                if math.isfinite(runtime) and runtime >= 0:
                    self.latest = dict(Runtime=runtime)
                    if runtime >= limit:
                        m.terminate()
                    if self.clock() - last_progress[0] >= 1:
                        self.progress(dict(phase=component, **self.snapshot()))
                        last_progress[0] = self.clock()
            except gp.GurobiError:
                pass
        if callback is not None:
            callback(m, where)
    try:
        with self._b3_native_scope(model, component, track):
            self._b3_guard(model)
            entered = True
            model.optimize(observe)
    except BaseException as exception:
        error = str(exception)
        raise
    finally:
        def attr(key, default=None):
            try:
                return finite_diagnostic(getattr(model, key))
            except Exception:
                return default
        self.inflight, self.latest = None, {}
        if not entered:
            row.update(status="ADMISSION_DENIED", error=error, entered_native=False,
                Native_Runtime=0., admission_wall_seconds=self.clock() - start,
                finished_wall_seconds=self.wall())
            self.admission_failures.append(row)
            self.persist()
        else:
            runtime = attr("Runtime")
            unknown = type(runtime) not in (int, float) or runtime < 0
            consumed = None if unknown else float(runtime)
            row.update(status="FAILED" if error else "FINISHED", error=error,
                entered_native=True, Native_Runtime=consumed, runtime_unavailable=unknown,
                optimize_wall_seconds=self.clock() - start, finished_wall_seconds=self.wall())
            self.calls.append(row)
            if consumed is not None:
                self.native_used += consumed
            # Runtime is durable before optional solver attributes are inspected.
            self.persist()
            row.update(Native_Work=attr("Work"), Native_status=attr("Status"),
                SolCount=attr("SolCount", 0), Native_BestBd=attr("ObjBound"),
                native_request_excess_seconds=None if consumed is None else max(0., consumed - limit),
                cumulative_budget_excess_seconds=max(0., self.used() - self.native_limit))
            self.persist()
            self.progress(dict(phase=component, **self.snapshot()))
            if unknown:
                raise RuntimeError("NATIVE_RUNTIME_UNAVAILABLE_QUARANTINE")
    return row
