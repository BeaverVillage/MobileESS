"""Durable shared solve budget. Native runtime and other-solver wall stay separate."""
from contextlib import contextmanager
from pathlib import Path
from time import perf_counter,sleep
import json
import math
import os
import threading


class IntegrationBudget:
    def __init__(self, path, limit=3600.):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        if self.path.exists():
            self.document = json.loads(self.path.read_text(encoding='utf8'))
            if self.document['limit_seconds'] != limit:
                raise ValueError('BUDGET_MUST_NOT_RESET')
            if self.document.get('inflight') is not None:
                raise RuntimeError('UNRECONCILED_SOLVER_CALL')
        else:
            self.document = dict(schema='V42_INTEGRATION_SOLVE_BUDGET_V1',
                limit_seconds=float(limit), calls=[], inflight=None,
                Gurobi_Native_seconds=0., other_solver_wall_seconds=0.,
                conservative_solve_seconds=0., AC_wall_seconds=0., historical_ledgers_merged=False)
            self._save()

    def _save(self):
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.document, indent=2, allow_nan=False), encoding='utf8')
        os.replace(temp, self.path)

    def _refresh(self):
        self.document=json.loads(self.path.read_text(encoding='utf8'))

    @contextmanager
    def _transaction(self):
        # AC accounting and the one native worker may hold separate Python
        # objects. Serialize their ledger writes and merge the latest totals.
        path=self.path.parent/'BUDGET_LEDGER_MUTATION.lock'
        began=perf_counter()
        while True:
            try:
                fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
                os.close(fd)
                break
            except FileExistsError:
                if perf_counter()-began>30:raise RuntimeError('BUDGET_LEDGER_WRITE_LOCK_BUSY')
                sleep(.01)
        try:
            self._refresh()
            yield
            self._save()
        finally:
            path.unlink()

    def remaining(self, reserve=0.):
        self._refresh()
        return max(0., self.document['limit_seconds']-self.document['conservative_solve_seconds']-reserve)

    def used(self):
        self._refresh()
        return self.document['conservative_solve_seconds']

    def record_external(self, label, seconds, *, solver='OTHER', status='COMPLETED'):
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError('MEASURED_SOLVE_COST_REQUIRED')
        with self.lock,self._transaction():
            row = dict(label=label, solver=solver, status=status, measured_seconds=seconds)
            self.document['calls'].append(row)
            if solver == 'AC':
                self.document['AC_wall_seconds'] += seconds
            else:
                self.document['other_solver_wall_seconds'] += seconds
                self.document['conservative_solve_seconds'] += seconds
        return row

    def solve(self, model, *, label, cap, callback=None):
        """One solver at a time. Charge runtime even on failure/overshoot."""
        import psutil
        with self.lock:
            seconds = min(float(cap), self.remaining())
            if seconds <= 0:
                raise RuntimeError('INTEGRATION_SOLVE_BUDGET_EXHAUSTED')
            memory = psutil.virtual_memory()
            if memory.available < 4*1024**3:
                raise RuntimeError('INTEGRATION_RESOURCE_WAIT')
            owned_lock = self.path.parent/'HEAVY_SOLVER.lock'
            fd = os.open(owned_lock, os.O_CREAT|os.O_EXCL|os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode()); os.close(fd)
            start = perf_counter()
            model.Params.Threads = 1
            model.Params.TimeLimit = seconds
            with self._transaction():
                if self.document['inflight'] is not None:
                    owned_lock.unlink()
                    raise RuntimeError('UNRECONCILED_SOLVER_CALL')
                self.document['inflight'] = dict(label=label, cap=seconds, pid=os.getpid())
            error = None
            try:
                if callback is None: model.optimize()
                else: model.optimize(callback)
            except BaseException as exc:
                error = repr(exc)
                raise
            finally:
                wall = perf_counter()-start
                try: runtime = float(model.Runtime)
                except Exception: runtime = None
                # Unavailable Native cost is conservatively charged as wall;
                # retain NULL rather than fabricate a Gurobi Runtime value.
                cost = wall if runtime is None or not math.isfinite(runtime) else runtime
                row = dict(label=label, solver='GUROBI', Native_Runtime=runtime,
                    wall_seconds=wall, charged_seconds=cost, cap_seconds=seconds,
                    overshoot_seconds=max(0.,cost-seconds), error=error,
                    status=int(model.Status) if runtime is not None else None)
                with self._transaction():
                    self.document['calls'].append(row)
                    self.document['Gurobi_Native_seconds'] += runtime or 0.
                    self.document['conservative_solve_seconds'] += cost
                    self.document['inflight'] = None
                owned_lock.unlink()
            return row
