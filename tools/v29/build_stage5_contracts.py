"""Write preregistered V29 development-backend contracts."""

from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v29_grid_responsive_aidc"


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    write("V29_SOLVER_EQUIVALENCE_CONTRACT.json", {
        "artifact_id": "V29_SOLVER_EQUIVALENCE_CONTRACT_V1", "status": "PASS",
        "B0": "MONOLITHIC", "B1": "MONOLITHIC", "B2": "MONOLITHIC", "B3_operational": "CL_MC_BD",
        "B3_comparison": ["MONOLITHIC", "STANDARD_BD", "CL_MC_BD"],
        "relative_objective_range_tolerance": 1e-4,
        "same_input_fingerprint_objective_constraints": True,
        "CL_MC_BD_better_optimum_claim": False,
    })
    write("V29_INCREMENT_RESOLUTION_CONTRACT.json", {
        "artifact_id": "V29_INCREMENT_RESOLUTION_CONTRACT_V1", "status": "PASS",
        "INCREMENT_RESOLVED": ["all three improvement signs identical", "operational increment magnitude > B3 absolute solver spread", "feasibility PASS"],
        "STRONGLY_RESOLVED": "absolute operational increment >= 10 * B3 solver spread",
        "UNRESOLVED": "otherwise; no scientific improvement claim",
    })
    write("V29_ACTUAL_REPLAY_CONTRACT.json", {
        "artifact_id": "V29_ACTUAL_REPLAY_CONTRACT_V1", "status": "PASS",
        "optimizer_calls": 0, "schedule": "frozen V29 Day-Ahead", "initial_workload_state": "frozen source-backed causal carry-in lower bound",
        "rules": ["0 <= x_EXEC <= x_DA", "no time shift", "no Rack substitution", "no AIDC reoptimization", "no event repair", "no local repair", "no rolling optimization"],
    })
    write("V29_PI_CONTRACT.json", {
        "artifact_id": "V29_PI_CONTRACT_V1", "status": "PASS",
        "horizon_hours": 24, "slots": 96, "case": "B3", "namespace": "PERFECT_INFORMATION",
        "same_carryin_definition": True, "actual_ex_post_inputs": True,
        "same_mobility_hardware_route": True, "connection_delay_slots": 1, "same_C1_grid": True,
    })
    write("V29_OPENDSS_CONTRACT.json", {
        "artifact_id": "V29_OPENDSS_CONTRACT_V1", "status": "PASS",
        "trajectories_per_day": 10, "slots_per_trajectory": 96, "clean_engine_per_trajectory": True,
        "trajectories": ["DA/B0", "DA/B1", "DA/B2", "DA/B3", "ACT/R0", "ACT/B0", "ACT/B1", "ACT/B2", "ACT/B3", "PI/B3"],
    })
    write("V29_BACKEND_CONTRACT.json", {
        "artifact_id": "V29_BACKEND_CONTRACT_V1", "status": "PASS",
        "execution_steps": 30, "day_processes": 4, "gurobi_threads_per_child": 4,
        "OMP_MKL_OPENBLAS_NUMEXPR_threads": 1, "within_day_heavy_solves": "sequential",
        "schedule_freeze_before_actual": True, "actual_optimizer_calls": 0,
        "output_roots": ["frozen_artifacts/v29_development_regression_apr01_04", "logs/v29_development_regression_apr01_04", "progress/v29_development_regression_apr01_04"],
    })


if __name__ == "__main__":
    main()
