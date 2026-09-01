"""Measured solver, PUE, OpenDSS, memory, and process ledger for one day."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping

from .backend_contract import canonical_sha256
from .day_state import atomic_json


PUE_TRAJECTORIES = (
    "DA/B0", "DA/B1", "DA/B2", "DA/B3",
    "ACT/R0", "ACT/B0", "ACT/B1", "ACT/B2", "ACT/B3", "PI/B3",
)
OPENDSS_TRAJECTORIES = PUE_TRAJECTORIES


def _rss_bytes() -> int:
    try:
        import psutil

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        return 0


@dataclass
class RuntimeLedger:
    day: str
    started_epoch: float = field(default_factory=time.time)
    pid: int = field(default_factory=os.getpid)
    solver_calls: list[dict[str, object]] = field(default_factory=list)
    pue_calls: dict[str, int] = field(default_factory=dict)
    pue_evaluations: dict[str, int] = field(default_factory=dict)
    opendss_solved_slots: dict[str, int] = field(default_factory=dict)
    opendss_engine_count: dict[str, int] = field(default_factory=dict)
    opendss_versions: dict[str, str] = field(default_factory=dict)
    opendss_failures: list[dict[str, object]] = field(default_factory=list)
    optimizer_calls_by_namespace: dict[str, int] = field(default_factory=lambda: {"DAYAHEAD": 0, "ACTUAL": 0, "PI": 0})
    peak_rss_bytes: int = 0
    peak_active_heavy_solves: int = 0
    active_solver: dict[str, object] | None = None
    active_opendss_trajectory: str | None = None
    counters: dict[str, float | int | str | None] = field(default_factory=dict)

    def set_progress_callback(self, callback: Callable[[dict[str, object]], None] | None) -> None:
        self._progress_callback = callback

    def _notify(self, values: Mapping[str, object]) -> None:
        self.measure_peak_rss()
        self.counters.update(values)
        self.counters["peak_rss_bytes"] = self.peak_rss_bytes
        callback = getattr(self, "_progress_callback", None)
        if callback is not None:
            callback({**dict(values), "peak_rss_bytes": self.peak_rss_bytes})

    def measure_peak_rss(self) -> int:
        self.peak_rss_bytes = max(self.peak_rss_bytes, _rss_bytes())
        return self.peak_rss_bytes

    def begin_solver(self, namespace: str, case: str, solver: str) -> None:
        if namespace not in self.optimizer_calls_by_namespace:
            raise ValueError("V28R2_LEDGER_OPTIMIZER_NAMESPACE")
        if namespace == "ACTUAL":
            raise RuntimeError("V28R2_ACTUAL_OPTIMIZER_CALL_DETECTED")
        if self.active_solver is not None or self.active_opendss_trajectory is not None:
            raise RuntimeError("V28R2_OVERLAPPING_HEAVY_OPERATION")
        self.optimizer_calls_by_namespace[namespace] += 1
        self.active_solver = {
            "namespace": namespace, "case": case, "solver": solver,
            "started_epoch": time.time(),
        }
        self.peak_active_heavy_solves = max(self.peak_active_heavy_solves, 1)
        self._notify({
            "active_solver": solver, "active_solver_case": case,
            "objective": None, "incumbent": None, "lb": None, "ub": None,
            "gap": None, "iterations": 0, "optimality_cuts": 0, "feasibility_cuts": 0,
        })

    def record_solver(self, payload: Mapping[str, object]) -> None:
        required = {
            "case", "solver", "status", "runtime_seconds", "objective", "incumbent",
            "lower_bound", "upper_bound", "gap", "iterations", "optimality_cuts", "feasibility_cuts",
        }
        if not required.issubset(payload) or self.active_solver is None:
            raise ValueError("V28R2_LEDGER_SOLVER_PAYLOAD")
        if payload["case"] != self.active_solver["case"] or payload["solver"] != self.active_solver["solver"]:
            raise RuntimeError("V28R2_LEDGER_ACTIVE_SOLVER_MISMATCH")
        self.solver_calls.append(dict(payload))
        self.active_solver = None
        self._notify({
            "active_solver": None,
            "objective": payload["objective"], "incumbent": payload["incumbent"],
            "lb": payload["lower_bound"], "ub": payload["upper_bound"], "gap": payload["gap"],
            "iterations": payload["iterations"], "optimality_cuts": payload["optimality_cuts"],
            "feasibility_cuts": payload["feasibility_cuts"],
        })

    def record_pue(self, trajectory: str, exact_evaluation_count: int) -> None:
        if trajectory not in PUE_TRAJECTORIES or exact_evaluation_count <= 0:
            raise ValueError("V28R2_LEDGER_PUE_TRAJECTORY")
        self.pue_calls[trajectory] = self.pue_calls.get(trajectory, 0) + 1
        self.pue_evaluations[trajectory] = self.pue_evaluations.get(trajectory, 0) + int(exact_evaluation_count)
        if self.pue_calls[trajectory] > 1:
            raise RuntimeError(f"V28R2_PUE_APPLIED_MORE_THAN_ONCE:{trajectory}")
        self._notify({"latest_pue_trajectory": trajectory, "latest_pue_exact_evaluations": exact_evaluation_count})

    def begin_opendss(self, trajectory: str) -> None:
        if trajectory not in OPENDSS_TRAJECTORIES:
            raise ValueError("V28R2_LEDGER_OPENDSS_TRAJECTORY")
        if self.active_solver is not None or self.active_opendss_trajectory is not None:
            raise RuntimeError("V28R2_OVERLAPPING_HEAVY_OPERATION")
        if self.opendss_solved_slots.get(trajectory, 0) != 0:
            raise RuntimeError("V28R2_OPENDSS_TRAJECTORY_ALREADY_STARTED")
        self.opendss_engine_count[trajectory] = self.opendss_engine_count.get(trajectory, 0) + 1
        if self.opendss_engine_count[trajectory] != 1:
            raise RuntimeError("V28R2_OPENDSS_ENGINE_REUSE")
        self.active_opendss_trajectory = trajectory
        self._notify({"active_opendss_trajectory": trajectory, "opendss_slot": 0})

    def record_opendss_slot(self, trajectory: str, slot: int, converged: bool) -> None:
        if trajectory != self.active_opendss_trajectory or slot != self.opendss_solved_slots.get(trajectory, 0):
            raise RuntimeError("V28R2_OPENDSS_LEDGER_SEQUENCE")
        if not converged:
            self.opendss_failures.append({"trajectory": trajectory, "slot": slot})
            raise RuntimeError(f"V28R2_OPENDSS_NONCONVERGENCE:{trajectory}:{slot}")
        self.opendss_solved_slots[trajectory] = slot + 1
        self._notify({"active_opendss_trajectory": trajectory, "opendss_slot": slot + 1})

    def complete_opendss(self, trajectory: str, version: str) -> None:
        if trajectory != self.active_opendss_trajectory or self.opendss_solved_slots.get(trajectory) != 96:
            raise RuntimeError("V28R2_OPENDSS_LEDGER_INCOMPLETE_TRAJECTORY")
        self.opendss_versions[trajectory] = version
        self.active_opendss_trajectory = None
        self._notify({"active_opendss_trajectory": None, "opendss_slot": 96})

    def validate_complete(self) -> None:
        if self.active_solver is not None or self.active_opendss_trajectory is not None:
            raise RuntimeError("V28R2_RUNTIME_LEDGER_ACTIVE_OPERATION")
        if any(self.pue_calls.get(name) != 1 for name in PUE_TRAJECTORIES):
            raise RuntimeError("V28R2_PUE_LEDGER_INCOMPLETE")
        if any(self.opendss_solved_slots.get(name) != 96 for name in OPENDSS_TRAJECTORIES):
            raise RuntimeError("V28R2_OPENDSS_LEDGER_INCOMPLETE")
        if any(self.opendss_engine_count.get(name) != 1 for name in OPENDSS_TRAJECTORIES):
            raise RuntimeError("V28R2_OPENDSS_ENGINE_LEDGER_INCOMPLETE")
        if self.optimizer_calls_by_namespace != {"DAYAHEAD": 6, "ACTUAL": 0, "PI": 1}:
            raise RuntimeError("V28R2_OPTIMIZER_CALL_LEDGER_MISMATCH")
        if len(self.solver_calls) != 7 or self.peak_active_heavy_solves != 1:
            raise RuntimeError("V28R2_SOLVER_LEDGER_INCOMPLETE")
        if self.opendss_failures:
            raise RuntimeError("V28R2_OPENDSS_FAILURE_LEDGER_NONEMPTY")

    def payload(self) -> dict[str, object]:
        self.measure_peak_rss()
        return {
            "artifact_id": "V28R2_MEASURED_RUNTIME_LEDGER_V1",
            "day": self.day,
            "started_epoch": self.started_epoch,
            "pid": self.pid,
            "solver_calls": self.solver_calls,
            "pue_calls": self.pue_calls,
            "pue_evaluations": self.pue_evaluations,
            "opendss_solved_slots": self.opendss_solved_slots,
            "opendss_engine_count": self.opendss_engine_count,
            "opendss_versions": self.opendss_versions,
            "opendss_failures": self.opendss_failures,
            "optimizer_calls_by_namespace": self.optimizer_calls_by_namespace,
            "peak_rss_bytes": self.peak_rss_bytes,
            "peak_active_heavy_solves": self.peak_active_heavy_solves,
            "active_solver": self.active_solver,
            "active_opendss_trajectory": self.active_opendss_trajectory,
            "counters": self.counters,
            "elapsed_seconds": time.time() - self.started_epoch,
        }

    @classmethod
    def from_snapshot(cls, payload: Mapping[str, object]) -> "RuntimeLedger":
        ledger = cls(str(payload["day"]), float(payload["started_epoch"]), int(payload["pid"]))
        for name in (
            "solver_calls", "pue_calls", "pue_evaluations", "opendss_solved_slots",
            "opendss_engine_count", "opendss_versions", "opendss_failures",
            "optimizer_calls_by_namespace", "counters",
        ):
            current = getattr(ledger, name)
            setattr(ledger, name, type(current)(payload.get(name, current)))
        ledger.peak_rss_bytes = int(payload.get("peak_rss_bytes", 0))
        ledger.peak_active_heavy_solves = int(payload.get("peak_active_heavy_solves", 0))
        ledger.active_solver = payload.get("active_solver")
        ledger.active_opendss_trajectory = payload.get("active_opendss_trajectory")
        return ledger

    def save(self, path: Path) -> None:
        payload = self.payload()
        payload["runtime_ledger_sha256"] = canonical_sha256(payload)
        atomic_json(path, payload)

    @classmethod
    def load(cls, path: Path) -> "RuntimeLedger":
        payload = json.loads(path.read_text(encoding="utf-8"))
        stored = payload.pop("runtime_ledger_sha256", None)
        if stored != canonical_sha256(payload):
            raise RuntimeError("V28R2_RUNTIME_LEDGER_SHA_MISMATCH")
        return cls.from_snapshot(payload)
