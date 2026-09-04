"""V29 development backend constants and effect-resolution gate."""

from __future__ import annotations

from typing import Mapping


SOLVER_EQUIVALENCE_TOLERANCE = 1e-4
OPERATIONAL_SOLVER = {"B0": "MONOLITHIC", "B1": "MONOLITHIC", "B2": "MONOLITHIC", "B3": "CL_MC_BD"}


def increment_resolution(b2_objective: float, b3_objectives: Mapping[str, float]) -> dict[str, object]:
    increments = {solver: float(b2_objective - objective) for solver, objective in b3_objectives.items()}
    values = list(map(float, b3_objectives.values()))
    spread = max(values) - min(values)
    signs = {0 if abs(value) <= 1e-12 else 1 if value > 0 else -1 for value in increments.values()}
    operational = increments["CL_MC_BD"]
    resolved = len(signs) == 1 and 1 in signs and abs(operational) > spread
    strong = resolved and abs(operational) >= 10.0 * spread
    return {
        "increments": increments, "B3_solver_absolute_spread": spread,
        "all_improvement_signs_identical": len(signs) == 1,
        "operational_increment_magnitude_exceeds_spread": abs(operational) > spread,
        "status": "STRONGLY_RESOLVED" if strong else "INCREMENT_RESOLVED" if resolved else "UNRESOLVED",
        "scientific_improvement_claim_allowed": resolved,
    }
