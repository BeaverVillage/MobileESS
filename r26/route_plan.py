"""Immutable, hash-addressed route plans and deterministic one-step shifts."""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Mapping, Optional, Sequence, Tuple


def _utc(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class RouteState:
    """A stationary location or a transit state, never both."""

    location: Optional[str] = None
    transit_origin: Optional[str] = None
    transit_destination: Optional[str] = None
    remaining_steps: int = 0

    def validate(self) -> None:
        stationary = self.location is not None
        transit = self.transit_origin is not None or self.transit_destination is not None
        if stationary:
            if transit or self.remaining_steps != 0:
                raise ValueError("stationary state cannot contain transit fields")
        else:
            if not (self.transit_origin and self.transit_destination):
                raise ValueError("transit state requires origin and destination")
            if self.remaining_steps <= 0:
                raise ValueError("transit state requires positive remaining_steps")

    @property
    def in_transit(self) -> bool:
        return self.location is None


@dataclass(frozen=True)
class RouteStep:
    step_index: int
    issue: int
    before: RouteState
    action: str
    after: RouteState
    travel_steps: Optional[int] = None

    def validate(self) -> None:
        self.before.validate()
        self.after.validate()
        if self.step_index < 0:
            raise ValueError("step_index must be non-negative")
        if self.before.in_transit:
            if self.action != "CONTINUE_TRANSIT":
                raise ValueError("an in-transit MESS must continue transit")
            if self.travel_steps is not None:
                raise ValueError("continuation cannot set travel_steps")
            remaining = self.before.remaining_steps
            if remaining == 1:
                expected = RouteState(location=self.before.transit_destination)
            else:
                expected = replace(self.before, remaining_steps=remaining - 1)
            if self.after != expected:
                raise ValueError("transit continuation does not decrement exactly once")
            return
        if self.action == "STAY":
            if self.travel_steps is not None or self.after != self.before:
                raise ValueError("STAY must preserve the stationary state")
            return
        if self.action != "MOVE":
            raise ValueError(f"unsupported route action: {self.action}")
        if self.travel_steps is None or self.travel_steps <= 0:
            raise ValueError("MOVE requires positive travel_steps")
        destination = self.after.location or self.after.transit_destination
        if not destination or destination == self.before.location:
            raise ValueError("MOVE requires a distinct destination")
        expected = (
            RouteState(location=destination)
            if self.travel_steps == 1
            else RouteState(
                transit_origin=self.before.location,
                transit_destination=destination,
                remaining_steps=self.travel_steps - 1,
            )
        )
        if self.after != expected:
            raise ValueError("MOVE after-state is inconsistent with travel_steps")


@dataclass(frozen=True)
class MessRoute:
    mess_id: str
    steps: Tuple[RouteStep, ...]

    def validate(self, *, valid_from_issue: int, horizon_steps: int) -> None:
        if not self.mess_id:
            raise ValueError("mess_id is required")
        if len(self.steps) != horizon_steps:
            raise ValueError("MESS trajectory length differs from plan horizon")
        for index, step in enumerate(self.steps):
            step.validate()
            if step.step_index != index:
                raise ValueError("step_index must be dense and zero-based")
            if step.issue != valid_from_issue + index:
                raise ValueError("step issue does not match valid_from_issue")
            if index and self.steps[index - 1].after != step.before:
                raise ValueError("route state chain is discontinuous")


@dataclass(frozen=True)
class WorkAssignment:
    """Slow-layer workload decision conditioned into the fast dispatch model."""

    job_uid: str
    destination_idc_id: str
    rack_pool_id: str
    start_issue: int
    duration_steps: int
    status: str = "PLANNED"

    def validate(self, *, valid_from_issue: int, horizon_steps: int) -> None:
        if not self.job_uid or not self.destination_idc_id or not self.rack_pool_id:
            raise ValueError("work assignment identifiers are required")
        if self.duration_steps <= 0:
            raise ValueError("work duration must be positive")
        if not (valid_from_issue <= self.start_issue < valid_from_issue + horizon_steps):
            raise ValueError("work start lies outside the route-plan horizon")
        if self.status not in {"PLANNED", "COMMITTED", "RUNNING"}:
            raise ValueError("unsupported work assignment status")


@dataclass(frozen=True)
class RoutePlan:
    schema_version: str
    plan_id: str
    created_at_utc: str
    cutoff_timestamp_utc: str
    source_state_hash: str
    valid_from_issue: int
    step_seconds: int
    horizon_steps: int
    terminal_policy: str
    planner_status: str
    planner_objective: Optional[float]
    planner_runtime_seconds: float
    mess_routes: Tuple[MessRoute, ...]
    work_assignments: Tuple[WorkAssignment, ...] = ()
    committed_prefix: Tuple[Mapping[str, Any], ...] = ()
    shift_count: int = 0
    parent_checksum: Optional[str] = None

    def validate(self) -> None:
        if self.schema_version != "r26.route_plan.v1":
            raise ValueError("unsupported RoutePlan schema")
        if not self.plan_id or not self.source_state_hash:
            raise ValueError("plan_id and source_state_hash are required")
        _utc(self.created_at_utc)
        _utc(self.cutoff_timestamp_utc)
        if self.valid_from_issue < 0 or self.step_seconds <= 0 or self.horizon_steps <= 0:
            raise ValueError("invalid issue, cadence, or horizon")
        if self.terminal_policy != "CAUSAL_STAY_OR_CONTINUE_TRANSIT":
            raise ValueError("unsupported terminal extension policy")
        if not math.isfinite(self.planner_runtime_seconds) or self.planner_runtime_seconds < 0:
            raise ValueError("invalid planner runtime")
        if self.planner_objective is not None and not math.isfinite(self.planner_objective):
            raise ValueError("invalid planner objective")
        ids = [route.mess_id for route in self.mess_routes]
        if not ids or len(ids) != len(set(ids)):
            raise ValueError("MESS ids must be nonempty and unique")
        for route in self.mess_routes:
            route.validate(valid_from_issue=self.valid_from_issue, horizon_steps=self.horizon_steps)
        jobs = [assignment.job_uid for assignment in self.work_assignments]
        if len(jobs) != len(set(jobs)):
            raise ValueError("work assignments must contain unique job_uids")
        for assignment in self.work_assignments:
            assignment.validate(
                valid_from_issue=self.valid_from_issue, horizon_steps=self.horizon_steps
            )

    def payload(self) -> Mapping[str, Any]:
        return asdict(self)

    @property
    def checksum(self) -> str:
        return hashlib.sha256(canonical_json(self.payload()).encode("utf-8")).hexdigest()

    def first_steps(self) -> Mapping[str, RouteStep]:
        return {route.mess_id: route.steps[0] for route in self.mess_routes}

    def shift_one(
        self,
        committed: Mapping[str, RouteStep],
        *,
        next_source_state_hash: Optional[str] = None,
    ) -> "RoutePlan":
        """Consume exactly the committed first step and extend the causal tail."""

        self.validate()
        expected = self.first_steps()
        if set(committed) != set(expected):
            raise ValueError("committed MESS set differs from the route plan")
        for mess_id, first in expected.items():
            if committed[mess_id] != first:
                raise ValueError(f"committed step differs from plan for {mess_id}")

        shifted_routes = []
        starting_work = tuple(
            assignment
            for assignment in self.work_assignments
            if assignment.start_issue == self.valid_from_issue
        )
        prefix_entry = {
            "route_steps": {
                mess_id: asdict(expected[mess_id]) for mess_id in sorted(expected)
            },
            "work_starts": [asdict(item) for item in starting_work],
        }
        for route in self.mess_routes:
            remaining = list(route.steps[1:])
            tail_before = route.steps[-1].after
            if tail_before.in_transit:
                tail_action = "CONTINUE_TRANSIT"
                if tail_before.remaining_steps == 1:
                    tail_after = RouteState(location=tail_before.transit_destination)
                else:
                    tail_after = replace(tail_before, remaining_steps=tail_before.remaining_steps - 1)
            else:
                tail_action = "STAY"
                tail_after = tail_before
            remaining.append(
                RouteStep(
                    step_index=self.horizon_steps - 1,
                    issue=self.valid_from_issue + self.horizon_steps,
                    before=tail_before,
                    action=tail_action,
                    after=tail_after,
                )
            )
            reindexed = tuple(
                replace(step, step_index=index, issue=self.valid_from_issue + 1 + index)
                for index, step in enumerate(remaining)
            )
            shifted_routes.append(MessRoute(route.mess_id, reindexed))
        shifted = replace(
            self,
            source_state_hash=next_source_state_hash or self.source_state_hash,
            valid_from_issue=self.valid_from_issue + 1,
            mess_routes=tuple(shifted_routes),
            work_assignments=tuple(
                assignment
                for assignment in self.work_assignments
                if assignment.start_issue > self.valid_from_issue
            ),
            committed_prefix=self.committed_prefix + (prefix_entry,),
            shift_count=self.shift_count + 1,
            parent_checksum=self.checksum,
        )
        shifted.validate()
        return shifted

    def to_json(self) -> str:
        self.validate()
        envelope = {"checksum": self.checksum, "route_plan": self.payload()}
        return canonical_json(envelope)

    @classmethod
    def from_json(cls, raw: str) -> "RoutePlan":
        envelope = json.loads(raw)
        data = envelope["route_plan"]
        routes = []
        for route in data["mess_routes"]:
            steps = []
            for step in route["steps"]:
                steps.append(
                    RouteStep(
                        step_index=step["step_index"],
                        issue=step["issue"],
                        before=RouteState(**step["before"]),
                        action=step["action"],
                        after=RouteState(**step["after"]),
                        travel_steps=step.get("travel_steps"),
                    )
                )
            routes.append(MessRoute(route["mess_id"], tuple(steps)))
        data = dict(data)
        data["mess_routes"] = tuple(routes)
        data["work_assignments"] = tuple(
            WorkAssignment(**item) for item in data.get("work_assignments", ())
        )
        data["committed_prefix"] = tuple(data.get("committed_prefix", ()))
        plan = cls(**data)
        plan.validate()
        if envelope.get("checksum") != plan.checksum:
            raise ValueError("RoutePlan checksum mismatch")
        return plan
