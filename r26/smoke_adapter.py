"""Dependency-free non-authoritative adapter for orchestration smoke tests only."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from .audit import AuditLogger
from .controller import CausalFrame, R26FastController
from .dispatch import DispatchResult, ModelStructureAudit, OpenDssResult
from .event_engine import EventConfig, EventEngine
from .planner_manager import AsyncPlannerManager, AtomicRoutePlanStore, PlannerRequest
from .route_plan import MessRoute, RoutePlan, RouteState, RouteStep


def _plan(issue: int, state_hash: str, horizon: int = 54) -> RoutePlan:
    state = RouteState(location="IDC01")
    steps = tuple(RouteStep(h, issue + h, state, "STAY", state) for h in range(horizon))
    return RoutePlan(
        schema_version="r26.route_plan.v1",
        plan_id=f"NONAUTHORITATIVE-SMOKE-{issue}",
        created_at_utc="2026-08-14T00:00:00Z",
        cutoff_timestamp_utc="2026-08-14T00:00:00Z",
        source_state_hash=state_hash,
        valid_from_issue=issue,
        step_seconds=300,
        horizon_steps=horizon,
        terminal_policy="CAUSAL_STAY_OR_CONTINUE_TRANSIT",
        planner_status="FEASIBLE",
        planner_objective=0.0,
        planner_runtime_seconds=0.0,
        mess_routes=(MessRoute("MESS01", steps),),
    )


class _Inputs:
    def load(self, issue: int) -> CausalFrame:
        return CausalFrame(
            issue=issue,
            cutoff_timestamp_utc="2026-08-14T00:00:00Z",
            pre_state_hash=f"smoke-state-{issue}",
            hard_flags={"ACTIVE_PLAN_INFEASIBLE": False},
            soft_metrics={"load_forecast_error_pct": 0.0},
            planner_target_issue=issue + 1,
            planner_target_state_hash=f"smoke-state-{issue + 1}",
            payload={"NONAUTHORITATIVE_SMOKE": True, "actual_through_issue": issue},
        )


class _States:
    def restore_pre(self, frame: CausalFrame) -> Mapping[str, Any]:
        return {"state_hash": frame.pre_state_hash}

    def commit_post(self, *, frame: CausalFrame, **_: Any) -> str:
        return f"smoke-state-{frame.issue + 1}"


class _Dispatch:
    def solve(self, *, frame: CausalFrame, **_: Any) -> DispatchResult:
        structure = ModelStructureAudit(
            num_vars=1,
            num_constraints=1,
            num_quadratic_constraints=1,
            num_integer_vars=0,
            integer_var_names=(),
            formulation="CONTINUOUS_AC_AWARE_QCP",
        )
        return DispatchResult(
            feasible=True,
            status="NONAUTHORITATIVE_SMOKE_FEASIBLE",
            objective=0.0,
            runtime_seconds=0.0,
            next_state={},
            h0_solution={},
            structure=structure,
            numerical_gates_passed=True,
        )


class _OpenDss:
    def verify_fresh(self, **_: Any) -> OpenDssResult:
        return OpenDssResult(
            passed=True,
            status="NONAUTHORITATIVE_SMOKE_ONLY_NOT_AN_OPENDSS_SOLVE",
            metrics={"real_opendss_executed": False},
        )


def create_controller(*, config: Mapping[str, Any], output: Path) -> R26FastController:
    event_config = EventConfig.from_mapping(config["event_config"])
    start_issue = int(config.get("start_issue", 113))
    plans = AtomicRoutePlanStore(output / "active_route_plan.json")
    if plans.load() is None:
        plans.swap(
            _plan(start_issue, f"smoke-state-{start_issue}"),
            issue=start_issue,
            source_state_hash=f"smoke-state-{start_issue}",
        )
    audit = AuditLogger(output / "R26_AUDIT.jsonl")

    def planner(request: PlannerRequest) -> RoutePlan:
        return _plan(request.issue, request.source_state_hash)

    return R26FastController(
        inputs=_Inputs(),
        states=_States(),
        dispatch=_Dispatch(),
        opendss=_OpenDss(),
        events=EventEngine(event_config),
        planner=AsyncPlannerManager(planner, audit=audit),
        plans=plans,
        planner_runtime_budget_seconds=float(config.get("planner_runtime_budget_seconds", 60)),
        audit=audit,
    )
