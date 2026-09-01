"""Measured solver, PUE, OpenDSS, and process counters for one day."""

from __future__ import annotations

import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .day_state import atomic_json


PUE_TRAJECTORIES = (
    "DA/B0", "DA/B1", "DA/B2", "DA/B3",
    "ACT/R0", "ACT/B0", "ACT/B1", "ACT/B2", "ACT/B3", "PI/B3",
)
OPENDSS_TRAJECTORIES = PUE_TRAJECTORIES


@dataclass
class RuntimeLedger:
    day: str
    started_epoch: float = field(default_factory=time.time)
    pid: int = field(default_factory=os.getpid)
    solver_calls: list[dict[str, object]] = field(default_factory=list)
    pue_calls: dict[str, int] = field(default_factory=dict)
    opendss_solved_slots: dict[str, int] = field(default_factory=dict)
    opendss_failures: list[dict[str, object]] = field(default_factory=list)
    optimizer_calls_by_namespace: dict[str, int] = field(default_factory=lambda: {"DAYAHEAD": 0, "ACTUAL": 0, "PI": 0})
    peak_rss_bytes: int = 0
    counters: dict[str, float | int] = field(default_factory=dict)

    def record_optimizer_call(self, namespace: str) -> None:
        if namespace not in self.optimizer_calls_by_namespace:
            raise ValueError("V28R2_LEDGER_OPTIMIZER_NAMESPACE")
        self.optimizer_calls_by_namespace[namespace] += 1

    def record_solver(self, payload: dict[str, object]) -> None:
        required = {"case", "solver", "status", "runtime_seconds"}
        if not required.issubset(payload):
            raise ValueError("V28R2_LEDGER_SOLVER_PAYLOAD")
        self.solver_calls.append(dict(payload))

    def record_pue(self, trajectory: str) -> None:
        if trajectory not in PUE_TRAJECTORIES:
            raise ValueError("V28R2_LEDGER_PUE_TRAJECTORY")
        self.pue_calls[trajectory] = self.pue_calls.get(trajectory, 0) + 1
        if self.pue_calls[trajectory] > 1:
            raise RuntimeError(f"V28R2_PUE_APPLIED_MORE_THAN_ONCE:{trajectory}")

    def record_opendss_slot(self, trajectory: str, slot: int, converged: bool) -> None:
        if trajectory not in OPENDSS_TRAJECTORIES or slot != self.opendss_solved_slots.get(trajectory, 0):
            raise RuntimeError("V28R2_OPENDSS_LEDGER_SEQUENCE")
        if not converged:
            self.opendss_failures.append({"trajectory": trajectory, "slot": slot})
            raise RuntimeError(f"V28R2_OPENDSS_NONCONVERGENCE:{trajectory}:{slot}")
        self.opendss_solved_slots[trajectory] = slot + 1

    def validate_complete(self) -> None:
        if any(self.pue_calls.get(name) != 1 for name in PUE_TRAJECTORIES):
            raise RuntimeError("V28R2_PUE_LEDGER_INCOMPLETE")
        if any(self.opendss_solved_slots.get(name) != 96 for name in OPENDSS_TRAJECTORIES):
            raise RuntimeError("V28R2_OPENDSS_LEDGER_INCOMPLETE")
        if self.optimizer_calls_by_namespace["ACTUAL"] != 0:
            raise RuntimeError("V28R2_ACTUAL_OPTIMIZER_CALL_DETECTED")

    def save(self, path: Path) -> None:
        payload = asdict(self)
        payload["elapsed_seconds"] = time.time() - self.started_epoch
        atomic_json(path, payload)

