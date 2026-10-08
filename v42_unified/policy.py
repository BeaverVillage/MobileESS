"""New run policy; historical modules and execution ledgers stay immutable."""
from dataclasses import dataclass, asdict
from math import isfinite

STAGES = ('A1', 'M1', 'A2', 'M2', 'PLANNING_FREEZE', 'ACTUAL', 'FRESH_AC', 'VALIDATION')


@dataclass(frozen=True)
class Policy:
    native_seconds: float = 5400.
    practical_wall_seconds: float = 5400.
    global_gap: float = .005
    threads: int = 1
    # Authority-specific tolerances; changing these is a scientific change.
    aidc_feasibility: float = 1e-6
    aidc_integrality: float = 1e-5
    mess_feasibility: float = 1e-8
    mess_integrality: float = 1e-8
    p1_lock: float = 1e-7
    component_lock: float = 1e-8

    def __post_init__(self):
        expected = (5400., 5400., .005, 1, 1e-6, 1e-5, 1e-8, 1e-8, 1e-7, 1e-8)
        if tuple(asdict(self).values()) != expected:
            raise ValueError('V42_PINNED_SCIENTIFIC_POLICY_REQUIRED')

    def parameters(self, stage):
        if stage not in STAGES[:4]:
            raise ValueError('NATIVE_STAGE_REQUIRED')
        a = stage.startswith('A')
        return dict(Threads=self.threads, MIPGap=self.global_gap,
                    FeasibilityTol=self.aidc_feasibility if a else self.mess_feasibility,
                    OptimalityTol=self.aidc_feasibility if a else self.mess_feasibility,
                    IntFeasTol=self.aidc_integrality if a else self.mess_integrality)


class NativeBudget:
    """One cumulative budget across LP, pricing, MIP and lex levels per stage.

    Wall is reported separately; it is a practicality criterion, not a memory or
    solver termination rule. Failed native calls count too. No budget reset.
    """
    def __init__(self, stage, policy=None, *, clock=None, native_allowed=True):
        from time import perf_counter
        if stage not in STAGES[:4]:
            raise ValueError('NATIVE_STAGE_REQUIRED')
        self.stage = stage
        self.policy = policy or Policy()
        self.clock = clock or perf_counter
        self.started = self.clock()
        self.calls = []
        self.native_allowed = native_allowed
        self.build_seconds = 0.
        self.validation_seconds = 0.

    @property
    def remaining(self):
        return max(0., self.policy.native_seconds-sum(c['Runtime'] for c in self.calls))

    def check(self):
        if self.remaining <= 0:
            raise TimeoutError(self.stage+'_NATIVE_BUDGET_EXHAUSTED')

    def optimize(self, model, callback=None):
        if not self.native_allowed:
            raise PermissionError('INTEGRATION_NATIVE_OPTIMIZE_FORBIDDEN')
        self.check()
        for key, value in self.policy.parameters(self.stage).items():
            setattr(model.Params, key, value)
        model.Params.TimeLimit = self.remaining
        if any(getattr(model.Params, k) != float('inf') for k in ('MemLimit', 'SoftMemLimit')):
            raise ValueError('FINITE_MEMORY_LIMIT_FORBIDDEN')
        start = self.clock()
        try:
            return model.optimize() if callback is None else model.optimize(callback)
        finally:
            runtime = float(model.Runtime)
            if not isfinite(runtime) or runtime < 0:
                raise ValueError('NATIVE_RUNTIME_REQUIRED')
            self.calls.append(dict(Runtime=runtime, optimize_wall_seconds=self.clock()-start,
                                   Work=float(getattr(model, 'Work', 0.)),
                                   status=getattr(model, 'Status', None)))

    def receipt(self):
        wall = self.clock()-self.started
        return dict(stage=self.stage, native_limit_seconds=self.policy.native_seconds,
                    native_Runtime=sum(c['Runtime'] for c in self.calls), native_calls=len(self.calls),
                    Work=sum(c['Work'] for c in self.calls), wall_seconds=wall,
                    practical_wall_PASS=wall <= self.policy.practical_wall_seconds,
                    build_seconds=self.build_seconds, validation_seconds=self.validation_seconds,
                    calls=self.calls, memory_automatic_stop=False, memory_limits=False,
                    historical_budgets_modified=False)
