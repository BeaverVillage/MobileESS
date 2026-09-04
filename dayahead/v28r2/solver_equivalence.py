"""Hard-feasibility and objective equivalence audit for three B3 solvers."""

from __future__ import annotations

from typing import Mapping

from .solver_payload import SolverPayload


def verify_b3_equivalence(
    payloads: Mapping[str, SolverPayload], tolerance: float = 1e-3,
) -> dict[str, object]:
    expected = {"MONOLITHIC", "STANDARD_BD", "CL_MC_BD"}
    if set(payloads) != expected:
        raise ValueError("V28R2_B3_THREE_SOLVERS_REQUIRED")
    for payload in payloads.values():
        payload.validate()
        if payload.case != "B3" or not payload.hard_feasible:
            raise RuntimeError("V28R2_B3_HARD_FEASIBILITY_MISMATCH")
    fingerprints = {payload.formulation_fingerprint for payload in payloads.values()}
    inputs = {payload.input_sha256 for payload in payloads.values()}
    if len(fingerprints) != 1 or len(inputs) != 1:
        raise RuntimeError("V28R2_B3_FORMULATION_OR_INPUT_MISMATCH")
    objectives = {name: float(payload.objective) for name, payload in payloads.items()}
    denominator = max(abs(objectives["MONOLITHIC"]), 1e-6)
    relative_range = (max(objectives.values()) - min(objectives.values())) / denominator
    if relative_range > tolerance:
        raise RuntimeError(f"V28R2_B3_OBJECTIVE_MISMATCH:{relative_range}")
    maximum_residual = max(
        max(payload.feasibility_residuals.values(), default=0.0)
        for payload in payloads.values()
    )
    if maximum_residual > 1e-5:
        raise RuntimeError("V28R2_B3_FEASIBILITY_RESIDUAL")
    return {
        "status": "PASS",
        "formulation_fingerprint": next(iter(fingerprints)),
        "input_sha256": next(iter(inputs)),
        "objectives": objectives,
        "relative_objective_range": relative_range,
        "tolerance": tolerance,
        "maximum_hard_feasibility_residual": maximum_residual,
        "identical_schedule_sha_required": False,
        "B3_SOLVER_EQUIVALENCE_READY": True,
    }
