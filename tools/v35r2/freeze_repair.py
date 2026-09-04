"""Freeze the evidence-led V35R2 common-current repair and invalidation scope."""

from __future__ import annotations

import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dayahead.grid_lp import LINE_POLYGON_FACES
from dayahead.v35.execution import COMMON_RHO_CURRENT_MODEL, MESS_INITIAL
from dayahead.v35.storage import atomic_json
from dayahead.v35r2.forensic import dependency_scoped_invalidation


OUTPUT = REPO / "dayahead/artifacts/v35r2_aidc_mess_forensic"


def main() -> None:
    q = json.loads((OUTPUT / "V35R2_Q_EXPLOIT_AUDIT.json").read_text(encoding="utf-8"))
    if q["classification"] != "AFFINE_CURRENT_Q_EXPLOIT_CONFIRMED":
        raise RuntimeError("V35R2_REPAIR_REQUIRES_CONFIRMED_Q_EXPLOIT")
    repair = {
        "artifact_id": "V35R2_COMMON_RHO_MODEL_REPAIR_V1",
        "status": "IMPLEMENTED_PENDING_APR01_20_RERUN",
        "defect_classification": "COMMON_RHO_CURRENT_IMPLEMENTATION_DEFECT",
        "specific_classification": "AFFINE_CURRENT_Q_EXPLOIT_CONFIRMED",
        "old_model": (
            "One signed affine tangent row for normalized current magnitude; "
            "the row was a local lower support and had no large-signal curvature."
        ),
        "new_model": COMMON_RHO_CURRENT_MODEL,
        "polygon_faces": LINE_POLYGON_FACES,
        "formula": (
            "max_k[(cos(theta_k) P_line(x)+sin(theta_k) Q_line(x))/apothem] "
            "+ anchor_bias + (J_current-J_active_polygon)^T(x-x_anchor)"
        ),
        "properties": {
            "convex": True,
            "anchor_current_value_preserved_exactly": True,
            "anchor_current_gradient_preserved_exactly": True,
            "existing_flow_coefficients_reused": True,
            "existing_line_ratings_reused": True,
            "new_physical_limit_invented": False,
            "Fresh_used_in_production_control": False,
            "rho_upper_bound": 1.0,
        },
        "representative_large_signal_evidence": {
            day: {
                "Q_given_P_Planning_affine_delta": row["marginal_effects"]["Q_given_P"]["Planning_affine_delta"],
                "Q_given_P_Planning_repaired_delta": row["marginal_effects"]["Q_given_P"]["Planning_anchored_polygon_delta"],
                "Q_given_P_Fresh_delta": row["marginal_effects"]["Q_given_P"]["Fresh_delta"],
            }
            for day, row in q["large_signal_decomposition"].items()
        },
        "representative_solver_smoke": {
            "day": "2025-04-01",
            "case": "B2",
            "vehicle": "MESS01",
            "termination": "WORK_LIMIT",
            "objective": 0.5666022075877167,
            "restricted_stationary_objective": 0.5666022075877167,
            "MOVE_count": 0,
            "variables": 208703,
            "constraints": 746907,
        },
    }
    atomic_json(OUTPUT / "V35R2_COMMON_RHO_MODEL_REPAIR.json", repair)

    scope = dependency_scoped_invalidation(
        common_current_changed=True,
        aidc_mapping_changed=False,
        mess_mapping_changed=False,
    )
    invalidation = {
        "artifact_id": "V35R2_INVALIDATION_MANIFEST_V1",
        "status": "FROZEN_BEFORE_RERUN",
        "scope": ["2025-04-01", "2025-04-20"],
        "reason": [
            "common rho/current objective formulation changed",
            "MESS initial-location authority changed by topology-only rule",
        ],
        "preserved_case_days": list(scope.preserved_case_days),
        "preserved_case_day_count": len(scope.preserved_case_days),
        "invalidated_case_days": list(scope.invalidated_case_days),
        "invalidated_case_day_count": len(scope.invalidated_case_days),
        "rerun_case_days": list(scope.invalidated_case_days),
        "rerun_case_day_count": len(scope.invalidated_case_days),
        "B0_B1_policy": (
            "Rerun conservatively because the common objective changed; "
            "do not assume their feasible domains remain on one polygon face."
        ),
        "B2_B3_policy": "Rerun because both common current model and initial locations changed.",
        "AC_correction_rebuild_required": scope.correction_rebuild_required,
        "forbidden_days": "2025-04-21 and later",
    }
    atomic_json(OUTPUT / "V35R2_INVALIDATION_MANIFEST.json", invalidation)
    log = {
        "artifact_id": "V35R2_REPAIR_LOG_V1",
        "status": "IMPLEMENTED_PENDING_RERUN",
        "repairs": [
            {
                "component": "common line-current/rho model",
                "classification": "AFFINE_CURRENT_Q_EXPLOIT_REPAIRED",
                "implementation": COMMON_RHO_CURRENT_MODEL,
            },
            {
                "component": "MESS initial-location authority",
                "classification": "MESS_INITIAL_LOCATION_AUTHORITY_DEFECT_REPAIRED",
                "implementation": MESS_INITIAL,
                "selection_inputs": "frozen physical road graph only",
            },
        ],
        "not_repaired": [
            {
                "component": "service-node electrical mapping",
                "reason": "24 unique PCCs and 24 distinct sensitivity fingerprints; no mapping defect proven",
            },
        ],
        "movement_forced": False,
        "service_mapping_changed": False,
        "AIDC_mapping_changed": False,
    }
    atomic_json(OUTPUT / "V35R2_REPAIR_LOG.json", log)
    print(json.dumps({"repair": repair, "invalidation": invalidation, "log": log}, indent=2))


if __name__ == "__main__":
    main()

