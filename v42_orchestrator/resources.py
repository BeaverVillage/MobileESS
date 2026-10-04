"""One campaign-wide solver semaphore; mock telemetry only in this lane."""
import math
import threading
from contextlib import contextmanager
from dataclasses import dataclass

from .config import Config


class ResourceStop(RuntimeError):
    pass


@dataclass(frozen=True)
class Telemetry:
    available_gib: float = 8
    commit_percent: float = 50
    oom: bool = False
    sustained_catastrophic_paging: bool = False
    solver_failure: bool = False
    license_failure: bool = False


class Resources:
    def __init__(self, config=Config(), telemetry=lambda: Telemetry()):
        self.config, self.telemetry = config, telemetry
        self.condition = threading.Condition()
        self.active = self.peak = 0
        self.stopped = None
        self.events = []

    def admit(self):
        with self.condition:
            if self.stopped:
                raise ResourceStop(self.stopped)
            try:
                t = self.telemetry()
            except Exception:
                t = None
            if not isinstance(t, Telemetry):
                reason = 'INVALID_TELEMETRY'
            elif not (type(t.available_gib) in (int, float) and type(t.commit_percent) in (int, float)
                      and all(type(getattr(t, key)) is bool for key in ('oom', 'sustained_catastrophic_paging', 'solver_failure', 'license_failure'))
                      and math.isfinite(t.available_gib) and math.isfinite(t.commit_percent)
                      and t.available_gib >= 0 and 0 <= t.commit_percent <= 100):
                reason = 'INVALID_TELEMETRY'
            elif t.oom:
                reason = 'OOM'
            elif t.commit_percent >= self.config.COMMIT_STOP_PERCENT:
                reason = 'COMMIT_GUARD'
            elif t.sustained_catastrophic_paging:
                reason = 'PAGING_GUARD'
            elif t.solver_failure or t.license_failure:
                reason = 'SOLVER_OR_LICENSE_FAILURE'
            elif t.available_gib < self.config.RAM_FLOOR_GIB:
                reason = 'RAM_FLOOR'
            else:
                return
            self.stopped = reason
            self.condition.notify_all()
            raise ResourceStop(reason)

    @contextmanager
    def solve_slot(self, owner):
        with self.condition:
            self.admit()
            while self.active >= self.config.GLOBAL_SOLVER_SLOTS:
                self.condition.wait(timeout=.01)
                self.admit()
            self.active += 1
            self.peak = max(self.peak, self.active)
            self.events.append(dict(owner=owner, action='acquire', active=self.active))
        try:
            yield
            self.admit()
        finally:
            with self.condition:
                self.active -= 1
                self.events.append(dict(owner=owner, action='release', active=self.active))
                self.condition.notify_all()
