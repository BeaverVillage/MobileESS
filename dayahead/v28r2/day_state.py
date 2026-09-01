"""Serializable, tamper-evident V28R2 per-day execution state."""

from __future__ import annotations

import copy
import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Mapping

from .backend_contract import EXECUTION_STEPS, canonical_sha256, sha256_file


VALID_STATUS = {"PENDING", "RUNNING", "PASS", "FAIL", "INCOMPLETE"}


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )
    os.replace(temporary, path)


@dataclass
class DayState:
    day: str
    campaign: str
    run_spec_sha256: str
    status: str = "PENDING"
    current_step: str | None = None
    completed_steps: list[str] = field(default_factory=list)
    predecessor_sha256: str | None = None
    step_sha256: dict[str, str] = field(default_factory=dict)
    step_counters: dict[str, dict[str, object]] = field(default_factory=dict)
    artifacts: dict[str, dict[str, str]] = field(default_factory=dict)
    attempts: dict[str, int] = field(default_factory=dict)
    pid: int | None = None
    heartbeat_epoch: float | None = None
    counters: dict[str, object] = field(default_factory=dict)
    failure: dict[str, object] | None = None
    defect_ids: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if self.status not in VALID_STATUS:
            raise ValueError("V28R2_DAY_STATE_STATUS")
        indices = [EXECUTION_STEPS.index(step) for step in self.completed_steps]
        if indices != sorted(set(indices)) or indices != list(range(len(indices))):
            raise ValueError("V28R2_DAY_STATE_COMPLETED_PREFIX")
        if self.current_step is not None and self.current_step not in EXECUTION_STEPS:
            raise ValueError("V28R2_DAY_STATE_CURRENT_STEP")
        if set(self.step_sha256) != set(self.completed_steps):
            raise ValueError("V28R2_DAY_STATE_STEP_SHA_AXIS")
        if set(self.step_counters) != set(self.completed_steps):
            raise ValueError("V28R2_DAY_STATE_STEP_COUNTER_AXIS")
        expected_predecessor = self.step_sha256[self.completed_steps[-1]] if self.completed_steps else None
        if self.predecessor_sha256 != expected_predecessor:
            raise ValueError("V28R2_DAY_STATE_PREDECESSOR_SHA")

    def payload(self) -> dict[str, object]:
        self.validate()
        return asdict(self)

    @property
    def state_sha256(self) -> str:
        return canonical_sha256(self.payload())

    def save(self, path: Path) -> None:
        payload = self.payload()
        payload["state_sha256"] = canonical_sha256(payload)
        atomic_json(path, payload)

    @classmethod
    def load(cls, path: Path) -> "DayState":
        payload = json.loads(path.read_text(encoding="utf-8"))
        stored = payload.pop("state_sha256", None)
        if stored != canonical_sha256(payload):
            raise RuntimeError("V28R2_DAY_STATE_SHA_MISMATCH")
        state = cls(**payload)
        state.validate()
        return state

    def begin_step(self, step: str) -> None:
        expected_index = len(self.completed_steps)
        if step != EXECUTION_STEPS[expected_index]:
            raise RuntimeError(f"V28R2_STEP_PREDECESSOR_MISMATCH:{step}")
        self.status = "RUNNING"
        self.current_step = step
        self.pid = os.getpid()
        self.heartbeat_epoch = time.time()
        self.attempts[step] = self.attempts.get(step, 0) + 1
        self.failure = None

    def complete_step(self, step: str, artifacts: Mapping[str, Path], counters: Mapping[str, object]) -> None:
        if self.current_step != step:
            raise RuntimeError("V28R2_COMPLETE_NONCURRENT_STEP")
        evidence = {name: {"path": str(path.resolve()), "sha256": sha256_file(path)} for name, path in sorted(artifacts.items())}
        predecessor = self.predecessor_sha256
        frozen_counters = copy.deepcopy(dict(counters))
        digest = canonical_sha256({
            "step": step, "predecessor_sha256": predecessor,
            "artifacts": evidence, "counters": frozen_counters,
        })
        self.artifacts[step] = evidence
        self.step_counters[step] = frozen_counters
        self.step_sha256[step] = digest
        self.completed_steps.append(step)
        self.predecessor_sha256 = digest
        self.current_step = None
        self.heartbeat_epoch = time.time()
        self.counters.update(counters)
        self.status = "PASS" if len(self.completed_steps) == len(EXECUTION_STEPS) else "INCOMPLETE"

    def fail_step(self, step: str, error: BaseException, defect_id: str) -> None:
        self.status = "FAIL"
        self.current_step = step
        self.heartbeat_epoch = time.time()
        self.failure = {"type": type(error).__name__, "message": str(error), "step": step}
        if defect_id not in self.defect_ids:
            self.defect_ids.append(defect_id)

    def reusable_prefix_length(self) -> int:
        predecessor: str | None = None
        for index, step in enumerate(self.completed_steps):
            evidence = self.artifacts.get(step, {})
            try:
                files_valid = all(
                    Path(record["path"]).is_file()
                    and sha256_file(Path(record["path"])) == record["sha256"]
                    for record in evidence.values()
                )
            except (KeyError, TypeError):
                return index
            if not files_valid:
                return index
            expected = canonical_sha256({
                "step": step, "predecessor_sha256": predecessor,
                "artifacts": evidence,
                "counters": self.step_counters.get(step, {}),
            })
            if self.step_sha256.get(step) != expected:
                return index
            predecessor = self.step_sha256[step]
        return len(self.completed_steps)
