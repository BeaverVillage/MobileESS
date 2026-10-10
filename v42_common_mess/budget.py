"""Cap every primal/initialization call by the same measured stage budget."""
import math
from time import perf_counter
from . import NATIVE_LIMIT_SECONDS


class NativeBudgetExhausted(TimeoutError):
    pass


class StageBudget:
    def __init__(self, parent, limit=NATIVE_LIMIT_SECONDS):
        self.parent, self.native_limit = parent, float(limit)
        self.started = perf_counter()
        self.final_reserve = 0.
        self.initial_calls = len(getattr(parent, 'calls', []))

    def used(self):
        value = float(self.parent.used())
        if not math.isfinite(value) or value < 0:
            raise ValueError('COMMON_M_UNMEASURED_NATIVE_RUNTIME')
        return value

    def remaining(self, reserve=None):
        return max(0., min(self.native_limit - self.used(), self.parent.remaining()))

    def wall(self):
        return max(0., perf_counter() - self.started)

    @property
    def calls(self):
        return self.parent.calls

    def cost(self, *args, **kwargs):
        return self.parent.cost(*args, **kwargs)

    def native_optimize(self, model, callback=None, *, component='UB', track='M_U4',
                        label='', requested_seconds=None):
        requested = self.remaining() if requested_seconds is None else float(requested_seconds)
        if not math.isfinite(requested) or requested <= 0:
            raise NativeBudgetExhausted('COMMON_M_NATIVE_BUDGET_EXHAUSTED')
        limit = min(requested, self.remaining())
        if limit <= 0:
            raise NativeBudgetExhausted('COMMON_M_NATIVE_BUDGET_EXHAUSTED')
        model.Params.TimeLimit = limit
        # The parent persists Runtime even when native.optimize raises. Its
        # own source/numerical guard remains authoritative at native entry.
        return self.parent.native_optimize(model, callback, component=component,
            track=track, label=label, requested_seconds=limit)

    def optimize(self, model, *, track, label, requested_seconds, callback=None):
        return self.native_optimize(model, callback, component='UB', track=track,
            label=label, requested_seconds=requested_seconds)
