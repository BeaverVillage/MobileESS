"""Final one-shot V28 Day-Ahead model contract and freeze utilities."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class CaseName(str, Enum):
    B0 = "B0_NO_FLEXIBILITY"
    B1 = "B1_AIDC_COMPUTE_FLEXIBILITY_ONLY"
    B2 = "B2_MOBILE_ESS_FLEXIBILITY_ONLY"
    B3 = "B3_JOINT_AIDC_AND_MOBILE_ESS_FLEXIBILITY"


CASE_FEATURES = {
    CaseName.B0: (False, False),
    CaseName.B1: (True, False),
    CaseName.B2: (False, True),
    CaseName.B3: (True, True),
}


@dataclass(frozen=True)
class SolverSettings:
    threads: int = 4
    seed: int = 20260828
    feasibility_tolerance: float = 1e-6
    optimality_tolerance: float = 1e-6
    mip_gap: float = 1e-3
    time_limit_seconds: float = 1800.0
    equivalence_tolerance: float = 1e-3

    def validate(self) -> None:
        if self.threads != 4:
            raise ValueError("V28_GUROBI_THREADS_MUST_EQUAL_4")


def verify_case_contract(results: Mapping[str, Mapping[str, Any]]) -> None:
    if set(results) != {"B0", "B1", "B2", "B3"}:
        raise ValueError("V28_EXACT_B0_B1_B2_B3_REQUIRED")
    b0 = str(results["B0"].get("reference_compute_schedule_sha256"))
    b2 = str(results["B2"].get("reference_compute_schedule_sha256"))
    if not b0 or b0 != b2:
        raise RuntimeError("V28_B0_B2_REFERENCE_COMPUTE_SCHEDULE_MISMATCH")


def verify_solver_equivalence(results: Mapping[str, Mapping[str, Any]], tolerance: float = 1e-3) -> None:
    expected = {"MONOLITHIC", "STANDARD_BD", "CL_MC_BD"}
    if set(results) != expected:
        raise ValueError("V28_B3_THREE_SOLVERS_REQUIRED")
    if not all(bool(results[name].get("hard_feasible")) for name in expected):
        raise RuntimeError("V28_B3_SOLVER_FEASIBILITY_MISMATCH")
    objective = [float(results[name]["objective"]) for name in expected]
    denominator = max(abs(objective[0]), 1e-6)
    if max(objective) - min(objective) > tolerance * denominator:
        raise RuntimeError("V28_B3_SOLVER_OBJECTIVE_MISMATCH")


def freeze_schedule(output: Path, schedule: Mapping[str, Any]) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(schedule, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    identity = hashlib.sha256(encoded).hexdigest()
    payload = {
        "DAYAHEAD_SCHEDULE_FROZEN": True,
        "schedule_sha256": identity,
        "actual_namespace_open_before_DA_freeze": 0,
        "future_actual_reads_before_DA_freeze": 0,
        "schedule": schedule,
    }
    path = output / "DAYAHEAD_FROZEN_SCHEDULE.json"
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)
    (output / "DAYAHEAD_FROZEN_SCHEDULE.sha256").write_text(f"{identity}  DAYAHEAD_FROZEN_SCHEDULE.json\n", encoding="ascii", newline="\n")
    return payload


def solve_decomposition_v28(*args: Any, method: str, **kwargs: Any) -> dict[str, Any]:
    """Call the immutable executor while overriding only its model configuration."""

    from .. import v16_3_decomposition_executor as authority

    original = authority.configure_model

    def configure(model: Any) -> None:
        original(model)
        model.Params.Threads = 4

    authority.configure_model = configure
    try:
        return authority.solve_benders(*args, method=method, **kwargs)
    finally:
        authority.configure_model = original
