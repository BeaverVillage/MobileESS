"""Single-worker, nonblocking online route planner manager."""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass
import os
from pathlib import Path
import threading
from typing import Callable, Mapping, Optional, Tuple

from .audit import AuditLogger
from .route_plan import RoutePlan


@dataclass(frozen=True)
class PlannerRequest:
    issue: int
    cutoff_timestamp_utc: str
    source_state_hash: str
    reasons: Tuple[str, ...]
    runtime_budget_seconds: float


@dataclass(frozen=True)
class PlannerRequestResult:
    disposition: str
    running_issue: Optional[int]
    pending_issue: Optional[int]


@dataclass(frozen=True)
class CandidatePoll:
    status: str
    candidate: Optional[RoutePlan] = None
    reason: Optional[str] = None


class AsyncPlannerManager:
    """At most one route-planning job runs; newer requests are coalesced."""

    def __init__(
        self,
        planner: Callable[[PlannerRequest], RoutePlan],
        *,
        audit: Optional[AuditLogger] = None,
    ) -> None:
        self._planner = planner
        self._audit = audit or AuditLogger()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="r26-route")
        self._future: Optional[Future[RoutePlan]] = None
        self._running_request: Optional[PlannerRequest] = None
        self._pending_request: Optional[PlannerRequest] = None
        self._lock = threading.Lock()

    def _submit_locked(self, request: PlannerRequest) -> None:
        self._running_request = request
        self._future = self._executor.submit(self._planner, request)
        self._audit.emit("PLANNER_STARTED", asdict(request))

    def request(self, request: PlannerRequest) -> PlannerRequestResult:
        if request.runtime_budget_seconds <= 0:
            raise ValueError("planner runtime budget must be positive")
        with self._lock:
            if self._future is None:
                self._submit_locked(request)
                disposition = "STARTED"
            else:
                merged = set(request.reasons)
                if self._pending_request is not None:
                    merged.update(self._pending_request.reasons)
                self._pending_request = PlannerRequest(
                    issue=request.issue,
                    cutoff_timestamp_utc=request.cutoff_timestamp_utc,
                    source_state_hash=request.source_state_hash,
                    reasons=tuple(sorted(merged)),
                    runtime_budget_seconds=request.runtime_budget_seconds,
                )
                disposition = "COALESCED"
                self._audit.emit("PLANNER_REQUEST_COALESCED", asdict(self._pending_request))
            return PlannerRequestResult(
                disposition=disposition,
                running_issue=self._running_request.issue if self._running_request else None,
                pending_issue=self._pending_request.issue if self._pending_request else None,
            )

    def poll(self, *, issue: int, source_state_hash: str) -> CandidatePoll:
        """Return immediately; never wait for an unfinished planner future."""

        with self._lock:
            if self._future is None or not self._future.done():
                return CandidatePoll("NOT_READY")
            future = self._future
            completed_request = self._running_request
            self._future = None
            self._running_request = None
            try:
                candidate = future.result(timeout=0)
                candidate.validate()
                if candidate.valid_from_issue != issue:
                    result = CandidatePoll("REJECTED", reason="STALE_VALID_FROM_ISSUE")
                elif candidate.source_state_hash != source_state_hash:
                    result = CandidatePoll("REJECTED", reason="SOURCE_STATE_HASH_MISMATCH")
                elif candidate.planner_status not in {"OPTIMAL", "FEASIBLE", "TIME_LIMIT_FEASIBLE"}:
                    result = CandidatePoll("REJECTED", reason="NO_FEASIBLE_PLANNER_STATUS")
                else:
                    result = CandidatePoll("ACCEPTABLE", candidate=candidate)
            except Exception as exc:
                result = CandidatePoll("REJECTED", reason=f"PLANNER_EXCEPTION:{type(exc).__name__}:{exc}")
            self._audit.emit(
                "PLANNER_COMPLETED",
                {
                    "request": asdict(completed_request) if completed_request else None,
                    "candidate_status": result.status,
                    "reason": result.reason,
                    "candidate_checksum": result.candidate.checksum if result.candidate else None,
                },
            )
            if self._pending_request is not None:
                pending = self._pending_request
                self._pending_request = None
                self._submit_locked(pending)
            return result

    @property
    def running(self) -> bool:
        with self._lock:
            return self._future is not None

    def close(self, *, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait, cancel_futures=not wait)


class AtomicRoutePlanStore:
    """Boundary-only active-plan persistence using same-directory os.replace."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> Optional[RoutePlan]:
        if not self.path.exists():
            return None
        return RoutePlan.from_json(self.path.read_text(encoding="utf-8"))

    def swap(self, candidate: RoutePlan, *, issue: int, source_state_hash: str) -> None:
        candidate.validate()
        if candidate.valid_from_issue != issue:
            raise ValueError("candidate may only be swapped at its issue boundary")
        if candidate.source_state_hash != source_state_hash:
            raise ValueError("candidate state hash does not match boundary PRE state")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_name(
            f".{self.path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temporary.write_text(candidate.to_json() + "\n", encoding="utf-8", newline="\n")
        os.replace(temporary, self.path)
