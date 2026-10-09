"""One-shot mock state machine, fail closed at every boundary."""
from dataclasses import dataclass
from .contracts import StageRequest, require
from .budget import MockNativeBudget
from .handoff import next_request
from .planning import freeze_mock_plan, mock_actual, mock_fresh_ac, mock_validation
from .policy import STAGES, require_production_authorization
from .validation import verify_stage


@dataclass(frozen=True)
class MockPipelineResult:
    states: tuple
    requests: tuple
    results: tuple
    frozen: object
    ledgers: tuple
    actual_json: str
    fresh_json: str
    validation_json: str


class MockPipeline:
    def __init__(self, backend=None):
        from .dry_run import FakeBackend
        self.backend = backend or FakeBackend()
        require(type(self.backend) is FakeBackend, "B3_BUILTIN_FAKE_BACKEND_REQUIRED")
        self.state = "PREPARED"
        self.completed_stages = []
        self.failure = None

    def execute_mock(self, authority):
        require(self.state == "PREPARED", "ONE_SHOT_MOCK_PIPELINE_REQUIRED")
        requests, results, ledgers = [], [], []
        request = StageRequest("A1", authority)
        try:
            for stage in STAGES[:4]:
                self.state = stage
                require(request.stage == stage, "STAGE_ORDER_REQUIRED")
                budget = MockNativeBudget(stage)
                result = self.backend.execute(request, budget)
                verify_stage(request, result, budget=budget)
                requests.append(request)
                results.append(result)
                ledgers.append(budget.receipt())
                self.completed_stages.append(stage)
                if stage != "M2":
                    request = next_request(request, result, m1=results[1] if len(results) >= 2 else None)
            self.state = "PLANNING_FREEZE"
            frozen = freeze_mock_plan(requests, results)
            self.completed_stages.append(self.state)
            self.state = "ACTUAL"
            actual = mock_actual(frozen)
            self.completed_stages.append(self.state)
            self.state = "FRESH_AC"
            fresh = mock_fresh_ac(frozen, actual)
            self.completed_stages.append(self.state)
            self.state = "VALIDATION"
            validation = mock_validation(frozen, actual, fresh)
            self.completed_stages.append(self.state)
            self.state = "MOCK_COMPLETE"
            return MockPipelineResult(tuple(self.completed_stages), tuple(requests), tuple(results), frozen,
                                      tuple(ledgers), actual, fresh, validation)
        except BaseException as exc:
            self.failure = {"stage": self.state, "reason": str(exc)}
            self.state = "FAILED"
            raise


def run_production(*args, **kwargs):
    require_production_authorization("CAMPAIGN")
