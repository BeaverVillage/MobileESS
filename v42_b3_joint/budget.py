"""Independent native-only ledgers verified with a mock clock, never a solver."""
from math import isfinite
from .contracts import canonical, require
from .policy import STAGES, NATIVE_LIMIT_SECONDS, require_production_authorization


class MockClock:
    def __init__(self):
        self.seconds = 0.0

    def __call__(self):
        return self.seconds

    def advance(self, seconds):
        require(type(seconds) in (int, float) and isfinite(seconds) and seconds >= 0, "FINITE_MOCK_ELAPSED_REQUIRED")
        self.seconds += seconds


class MockNativeBudget:
    """Simulate measured optimize Runtime, including failed entered calls.

    Native presolve/simplex/barrier/B&B belongs inside one measured Runtime.
    No model object or executable callback is accepted. Costs outside optimize
    advance wall time only. Unknown runtime permanently quarantines this ledger.
    """
    def __init__(self, stage, *, clock=None):
        require(stage in STAGES[:4], "OPTIMIZATION_STAGE_REQUIRED")
        require(clock is None or type(clock) is MockClock, "MOCK_CLOCK_ONLY")
        self._stage = stage
        self.clock = clock or MockClock()
        self._started = self.clock()
        self._calls = []
        self._costs = []
        self._quarantined = False
        self._identity = None

    @property
    def stage(self):
        return self._stage

    @property
    def used(self):
        return sum(row["Runtime"] for row in self._calls if row["Runtime"] is not None)

    @property
    def remaining(self):
        return max(0.0, NATIVE_LIMIT_SECONDS - self.used)

    def bind(self, request):
        from .contracts import StageRequest
        require(isinstance(request, StageRequest) and request.stage == self.stage, "STAGE_REQUEST_BUDGET_BINDING_REQUIRED")
        identity = {"authority_sha": request.authority.sha, "fixed_input_sha": request.fixed_input_sha,
                    "request_sha": request.request_sha}
        if self._identity is not None:
            require(self._identity == identity, "NATIVE_LEDGER_INPUT_REBIND_FORBIDDEN")
        else:
            require(not self._calls and not self._costs, "NATIVE_LEDGER_LATE_BIND_FORBIDDEN")
            self._identity = identity

    def simulate(self, runtime_seconds, *, kind="MILP", failed=False):
        require(kind in ("LP", "MILP", "PRICING", "QCP"), "P1_NATIVE_CALL_KIND_REQUIRED")
        require(type(failed) is bool, "FAILED_BOOLEAN_REQUIRED")
        if self._quarantined:
            raise RuntimeError("UNMEASURED_RUNTIME_QUARANTINE")
        if self.remaining <= 0:
            raise TimeoutError("STAGE_NATIVE_BUDGET_EXHAUSTED")
        effective_limit = self.remaining
        if type(runtime_seconds) not in (int, float) or not isfinite(runtime_seconds) or runtime_seconds < 0:
            self._quarantined = True
            self._calls.append({"Runtime": None, "effective_TimeLimit": effective_limit,
                                "kind": kind, "failed": failed, "runtime_unavailable": True})
            raise RuntimeError("NATIVE_RUNTIME_UNAVAILABLE_QUARANTINE")
        self.clock.advance(runtime_seconds)
        self._calls.append({"Runtime": runtime_seconds, "effective_TimeLimit": effective_limit,
                            "kind": kind, "failed": failed, "runtime_unavailable": False})
        if self.used > NATIVE_LIMIT_SECONDS:
            raise TimeoutError("STAGE_NATIVE_RUNTIME_CEILING_EXCEEDED")

    def record_non_native(self, kind, seconds):
        require(kind in ("MODEL_BUILD", "PHYSICAL_DOMAIN", "MATRIX", "CERTIFICATION", "ACTUAL", "FRESH_AC"), "NON_NATIVE_COST_KIND_REQUIRED")
        self.clock.advance(seconds)
        self._costs.append({"kind": kind, "wall_seconds": seconds})

    def receipt(self):
        return {"stage": self.stage, **(self._identity or {"authority_sha": None, "fixed_input_sha": None, "request_sha": None}),
                "evidence_kind": "MOCK", "native_limit_seconds": 5400,
                "budget_basis": "MEASURED_NATIVE_RUNTIME_ONLY", "wall_limit_seconds": None,
                "simulated_native_runtime": self.used, "remaining_seconds": self.remaining,
                "simulated_calls": len(self._calls), "real_native_optimize_calls": 0,
                "P2_calls": 0, "Threads": 1, "quarantined": self._quarantined,
                "wall_seconds": self.clock() - self._started,
                "calls": [dict(row) for row in self._calls],
                "non_native_costs": [dict(row) for row in self._costs]}

    def sealed_receipt(self):
        return canonical(self.receipt())


class NativeStageBudget:
    """Prepared policy metadata; actual admission is permanently closed here."""
    def __init__(self, stage):
        require(stage in STAGES[:4], "OPTIMIZATION_STAGE_REQUIRED")
        self.stage = stage

    def native_optimize(self, *args, **kwargs):
        require_production_authorization("NATIVE_OPTIMIZE")
