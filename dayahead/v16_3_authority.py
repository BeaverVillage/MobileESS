"""Frozen V16.3 planning authority and LP-safe phase-current semantics.

The module is deliberately independent of OpenDSS and of final campaign
runners.  It binds the reviewed D-1 AC anchors to an affine, time-local LP.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


AUTHORITY_ID = "V16_3_DA_AIDC_ICPS_AC_ANCHORED_FROZEN_D1_CONTROL"
CONTROL_SEMANTICS_ID = "D1_FROZEN_COMMON_NATIVE_CONTROL_STATE"
BETA_AIDC = 0.25
RHO_VALID = 0.10
TIME_LOCAL_GRID_LP_COUNT = 96
CONTROL_DIMENSION = 60
PHASE_CURRENT_DIMENSION = 383
CURRENT_COEFFICIENT_HASH_OF_DAILY_HASHES = (
    "9c2402f16f7252fb3219a231842523ac85fedbbafb8f28bc6083ebca8ff7883e"
)
ACTIVE_FOR_PRODUCTION_PLANNING = True


@dataclass(frozen=True)
class PhaseCurrentEpigraph:
    """The explicit LP epigraph used for one branch-phase and time slice."""

    i_hat: Any
    hard_constraint: Any
    affine_constraint: Any
    objective_constraint: Any | None


def add_phase_current_epigraph(
    model: Any,
    *,
    affine_current_pu: Any,
    slot: int,
    branch_name: str,
    line_objective: Any | None = None,
) -> PhaseCurrentEpigraph:
    """Add ``I_hat=max(I_aff, 0)`` in LP epigraph form.

    Minimization of the nonnegative line objective makes the epigraph tight
    for line phases.  Transformer phases use the same nonnegative hard-limit
    envelope while their authoritative total-kVA polygons remain separate.
    """

    safe_name = branch_name.replace("[", "(").replace("]", ")")
    i_hat = model.addVar(
        lb=0.0,
        ub=1.0,
        name=f"grid_phase_current_hat_pu[{slot},{safe_name}]",
    )
    affine_constraint = model.addConstr(
        i_hat >= affine_current_pu,
        name=f"grid_phase_current_epigraph[{slot},{safe_name}]",
    )
    # The variable upper bound is the hard I_hat <= 1 constraint.  Keeping the
    # returned handle explicit makes this binding auditable without adding a
    # duplicate row.
    hard_constraint = i_hat
    objective_constraint = None
    if line_objective is not None:
        objective_constraint = model.addConstr(
            line_objective >= i_hat,
            name=f"line_current_objective[{slot},{safe_name}]",
        )
    return PhaseCurrentEpigraph(
        i_hat=i_hat,
        hard_constraint=hard_constraint,
        affine_constraint=affine_constraint,
        objective_constraint=objective_constraint,
    )


def physical_phase_current_pu(affine_current_pu: float) -> float:
    """Materialize the physical nonnegative value represented by the epigraph."""

    return max(0.0, float(affine_current_pu))


def authority_constants() -> dict[str, object]:
    return {
        "authority_id": AUTHORITY_ID,
        "control_semantics_id": CONTROL_SEMANTICS_ID,
        "beta_AIDC": BETA_AIDC,
        "rho_valid": RHO_VALID,
        "time_local_grid_LP_count": TIME_LOCAL_GRID_LP_COUNT,
        "control_dimension": CONTROL_DIMENSION,
        "phase_current_dimension": PHASE_CURRENT_DIMENSION,
        "current_coefficient_hash_of_daily_hashes": CURRENT_COEFFICIENT_HASH_OF_DAILY_HASHES,
        "active_for_production_planning": ACTIVE_FOR_PRODUCTION_PLANNING,
    }
