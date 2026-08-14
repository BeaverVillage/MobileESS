"""Nonblocking five-minute R26 controller orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import time
from typing import Any, Mapping, Optional, Protocol

from .audit import AuditLogger
from .dispatch import DispatchBackend, DispatchResult, OpenDssResult, OpenDssVerifier
from .event_engine import EventDecision, EventEngine
from .planner_manager import (
    AsyncPlannerManager,
    AtomicRoutePlanStore,
    PlannerRequest,
)
from .route_plan import RoutePlan, RouteStep


@dataclass(frozen=True)
class CausalFrame:
    issue: int
    cutoff_timestamp_utc: str
    pre_state_hash: str
    hard_flags: Mapping[str, bool]
    soft_metrics: Mapping[str, float]
    planner_target_issue: int
    planner_target_state_hash: str
    payload: Mapping[str, Any]


class CausalInputProvider(Protocol):
    def load(self, issue: int) -> CausalFrame:
        """Load only observations available at the frame cutoff."""


class StateStore(Protocol):
    def restore_pre(self, frame: CausalFrame) -> Any:
        ...

    def commit_post(
        self,
        *,
        frame: CausalFrame,
        pre_state: Any,
        dispatch: DispatchResult,
        opendss: OpenDssResult,
    ) -> str:
        """Atomically commit h0 and return the committed POST-state hash."""


class SafeFallbackProvider(Protocol):
    def get_safe_plan(self, *, frame: CausalFrame, pre_state: Any) -> Optional[RoutePlan]:
        """Return a precomputed/constant-time validated-safe plan, or None."""


@dataclass(frozen=True)
class IssueResult:
    issue: int
    status: str
    committed: bool
    runtime_seconds: float
    plan_checksum: Optional[str]
    event: EventDecision
    dispatch_status: Optional[str]
    opendss_status: Optional[str]
    post_state_hash: Optional[str]
    num_integer_vars: Optional[int]
    formulation: Optional[str]
    planner_disposition: Optional[str]
    dispatch_objective: Optional[float]
    operational_metrics: Mapping[str, Any]


class R26FastController:
    def __init__(
        self,
        *,
        inputs: CausalInputProvider,
        states: StateStore,
        dispatch: DispatchBackend,
        opendss: OpenDssVerifier,
        events: EventEngine,
        planner: AsyncPlannerManager,
        plans: AtomicRoutePlanStore,
        planner_runtime_budget_seconds: float,
        audit: Optional[AuditLogger] = None,
        fallback: Optional[SafeFallbackProvider] = None,
        plan_invalidating_hard_flags: tuple[str, ...] = (
            "ACTIVE_PLAN_INFEASIBLE",
            "MESS_TRANSIT_CONFLICT",
        ),
    ) -> None:
        self.inputs = inputs
        self.states = states
        self.dispatch = dispatch
        self.opendss = opendss
        self.events = events
        self.planner = planner
        self.plans = plans
        self.planner_runtime_budget_seconds = planner_runtime_budget_seconds
        self.audit = audit or AuditLogger()
        self.fallback = fallback
        self.plan_invalidating_hard_flags = plan_invalidating_hard_flags
        self._last_new_plan_issue: Optional[int] = None

    def _steps_since_plan(self, issue: int, plan: Optional[RoutePlan]) -> int:
        if self._last_new_plan_issue is not None:
            return max(0, issue - self._last_new_plan_issue)
        if plan is not None:
            return plan.shift_count
        return 10**9

    def run_issue(self, issue: int) -> IssueResult:
        started = time.monotonic()
        frame = self.inputs.load(issue)
        if frame.issue != issue:
            raise ValueError("causal input provider returned the wrong issue")
        pre_state = self.states.restore_pre(frame)
        active = self.plans.load()

        # Candidate polling is strictly nonblocking and swap is boundary-only.
        poll = self.planner.poll(issue=issue, source_state_hash=frame.pre_state_hash)
        if poll.status == "ACCEPTABLE" and poll.candidate is not None:
            self.plans.swap(
                poll.candidate, issue=issue, source_state_hash=frame.pre_state_hash
            )
            active = poll.candidate
            self._last_new_plan_issue = issue
            self.audit.emit(
                "ROUTE_PLAN_SWAPPED",
                {"issue": issue, "checksum": active.checksum, "plan_id": active.plan_id},
            )
        elif poll.status == "REJECTED":
            self.audit.emit("ROUTE_PLAN_REJECTED", {"issue": issue, "reason": poll.reason})

        if active is not None:
            active.validate()
            if (
                active.valid_from_issue != issue
                or active.source_state_hash != frame.pre_state_hash
            ):
                self.audit.emit(
                    "ACTIVE_ROUTE_PLAN_INVALID",
                    {
                        "issue": issue,
                        "valid_from_issue": active.valid_from_issue,
                        "state_hash_matches": active.source_state_hash == frame.pre_state_hash,
                        "checksum": active.checksum,
                    },
                )
                active = None

        decision = self.events.evaluate(
            issue=issue,
            hard_flags=frame.hard_flags,
            soft_metrics=frame.soft_metrics,
            steps_since_plan=self._steps_since_plan(issue, active),
        )
        self.audit.emit("EVENT_DECISION", decision.as_record())
        planner_disposition: Optional[str] = None
        if decision.request_replan:
            request_result = self.planner.request(
                PlannerRequest(
                    issue=frame.planner_target_issue,
                    cutoff_timestamp_utc=frame.cutoff_timestamp_utc,
                    source_state_hash=frame.planner_target_state_hash,
                    reasons=decision.reasons,
                    runtime_budget_seconds=self.planner_runtime_budget_seconds,
                )
            )
            planner_disposition = request_result.disposition
            self.events.mark_request_accepted(issue)
            self.audit.emit(
                "PLANNER_REQUEST",
                {"issue": issue, **asdict(request_result), "reasons": decision.reasons},
            )

        invalidating_reasons = {
            f"HARD:{name}" for name in self.plan_invalidating_hard_flags
        }.intersection(decision.hard_reasons)
        if invalidating_reasons:
            active = None
            self.audit.emit(
                "ACTIVE_ROUTE_PLAN_INVALIDATED_BY_HARD_EVENT",
                {"issue": issue, "reasons": sorted(invalidating_reasons)},
            )
        if active is None and self.fallback is not None:
            fallback = self.fallback.get_safe_plan(frame=frame, pre_state=pre_state)
            if fallback is not None:
                fallback.validate()
                if fallback.valid_from_issue != issue or fallback.source_state_hash != frame.pre_state_hash:
                    raise RuntimeError("safe fallback does not match the current PRE boundary")
                self.plans.swap(
                    fallback, issue=issue, source_state_hash=frame.pre_state_hash
                )
                active = fallback
                self.audit.emit(
                    "SAFE_FALLBACK_ACTIVATED",
                    {"issue": issue, "checksum": fallback.checksum},
                )

        if active is None:
            status = "FAIL_CLOSED_NO_VALID_ROUTE_PLAN"
            self.audit.emit("ISSUE_ABORTED", {"issue": issue, "status": status})
            return IssueResult(
                issue=issue,
                status=status,
                committed=False,
                runtime_seconds=time.monotonic() - started,
                plan_checksum=None,
                event=decision,
                dispatch_status=None,
                opendss_status=None,
                post_state_hash=None,
                num_integer_vars=None,
                formulation=None,
                planner_disposition=planner_disposition,
                dispatch_objective=None,
                operational_metrics={},
            )

        route_steps: Mapping[str, RouteStep] = active.first_steps()
        dispatch_result = self.dispatch.solve(
            frame=frame,
            pre_state=pre_state,
            route_steps=route_steps,
            work_assignments=active.work_assignments,
        )
        self.audit.emit(
            "FAST_DISPATCH",
            {
                "issue": issue,
                "feasible": dispatch_result.feasible,
                "status": dispatch_result.status,
                "objective": dispatch_result.objective,
                "runtime_seconds": dispatch_result.runtime_seconds,
                "numerical_gates_passed": dispatch_result.numerical_gates_passed,
                "model_structure": dispatch_result.structure.as_record(),
            },
        )
        if not dispatch_result.feasible or not dispatch_result.numerical_gates_passed:
            status = "FAIL_CLOSED_DISPATCH_GATE"
            return IssueResult(
                issue=issue,
                status=status,
                committed=False,
                runtime_seconds=time.monotonic() - started,
                plan_checksum=active.checksum,
                event=decision,
                dispatch_status=dispatch_result.status,
                opendss_status=None,
                post_state_hash=None,
                num_integer_vars=dispatch_result.structure.num_integer_vars,
                formulation=dispatch_result.structure.formulation,
                planner_disposition=planner_disposition,
                dispatch_objective=dispatch_result.objective,
                operational_metrics=dict(dispatch_result.h0_solution),
            )

        expected_work_starts = {
            assignment.job_uid
            for assignment in active.work_assignments
            if assignment.start_issue == issue
        }
        if expected_work_starts:
            actual_work_starts = set(
                map(str, dispatch_result.h0_solution.get("started_job_uids", ()))
            )
            if actual_work_starts != expected_work_starts:
                status = "FAIL_CLOSED_WORK_PLAN_COMMIT_MISMATCH"
                self.audit.emit(
                    "WORK_PLAN_COMMIT_MISMATCH",
                    {
                        "issue": issue,
                        "expected": sorted(expected_work_starts),
                        "actual": sorted(actual_work_starts),
                    },
                )
                return IssueResult(
                    issue=issue,
                    status=status,
                    committed=False,
                    runtime_seconds=time.monotonic() - started,
                    plan_checksum=active.checksum,
                    event=decision,
                    dispatch_status=dispatch_result.status,
                    opendss_status=None,
                    post_state_hash=None,
                    num_integer_vars=dispatch_result.structure.num_integer_vars,
                    formulation=dispatch_result.structure.formulation,
                    planner_disposition=planner_disposition,
                    dispatch_objective=dispatch_result.objective,
                    operational_metrics=dict(dispatch_result.h0_solution),
                )

        ac_result = self.opendss.verify_fresh(
            frame=frame, pre_state=pre_state, dispatch=dispatch_result
        )
        self.audit.emit(
            "FRESH_OPENDSS_GATE",
            {"issue": issue, "passed": ac_result.passed, "status": ac_result.status, "metrics": ac_result.metrics},
        )
        if not ac_result.passed:
            status = "FAIL_CLOSED_FRESH_OPENDSS_GATE"
            return IssueResult(
                issue=issue,
                status=status,
                committed=False,
                runtime_seconds=time.monotonic() - started,
                plan_checksum=active.checksum,
                event=decision,
                dispatch_status=dispatch_result.status,
                opendss_status=ac_result.status,
                post_state_hash=None,
                num_integer_vars=dispatch_result.structure.num_integer_vars,
                formulation=dispatch_result.structure.formulation,
                planner_disposition=planner_disposition,
                dispatch_objective=dispatch_result.objective,
                operational_metrics={
                    **dict(dispatch_result.h0_solution),
                    **dict(ac_result.metrics),
                },
            )

        post_hash = self.states.commit_post(
            frame=frame,
            pre_state=pre_state,
            dispatch=dispatch_result,
            opendss=ac_result,
        )
        shifted = active.shift_one(route_steps, next_source_state_hash=post_hash)
        # The shifted plan is persisted only after every h0 commit gate passes.
        self.plans.swap(
            shifted,
            issue=issue + 1,
            source_state_hash=post_hash,
        )
        elapsed = time.monotonic() - started
        result = IssueResult(
            issue=issue,
            status="COMMITTED",
            committed=True,
            runtime_seconds=elapsed,
            plan_checksum=shifted.checksum,
            event=decision,
            dispatch_status=dispatch_result.status,
            opendss_status=ac_result.status,
            post_state_hash=post_hash,
            num_integer_vars=dispatch_result.structure.num_integer_vars,
            formulation=dispatch_result.structure.formulation,
            planner_disposition=planner_disposition,
            dispatch_objective=dispatch_result.objective,
            operational_metrics={
                **dict(dispatch_result.h0_solution),
                **dict(ac_result.metrics),
            },
        )
        self.audit.emit("ISSUE_COMMITTED", asdict(result))
        return result
