#!/usr/bin/env python3
"""Write final Day-Ahead formulation, solver, and OpenDSS bindings."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v28_final_dayahead_actual"


def sha(path: str) -> str:
    return hashlib.sha256((REPO / path).read_bytes()).hexdigest()


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def main() -> None:
    formulation = {
        "artifact_id": "V28_DAYAHEAD_FORMULATION_BINDING_V1",
        "authority_id": "V16_3_DA_AIDC_ICPS_AC_ANCHORED_FROZEN_D1_CONTROL",
        "authority_file": "dayahead/artifacts/v16_3_final/V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json",
        "authority_sha256": sha("dayahead/artifacts/v16_3_final/V16_3_FINAL_SCIENCE_EXECUTION_CONTRACT.json"),
        "resolution_minutes": 15, "slots_per_day": 96,
        "objective": "MINIMUM_MAXIMUM_NORMALIZED_PHASE_LINE_CURRENT_LOADING",
        "cases": {
            "B0": {"compute_flexibility": False, "MESS_flexibility": False},
            "B1": {"compute_flexibility": True, "MESS_flexibility": False},
            "B2": {"compute_flexibility": False, "MESS_flexibility": True},
            "B3": {"compute_flexibility": True, "MESS_flexibility": True},
        },
        "B0_B2_identical_reference_schedule_required": True,
        "event_trigger": False, "local_repair": False, "rolling_MPC": False,
        "input_binding_overrides": {"forecast": "V28_LIGHTGBM", "scale": "V22SR1_ABSOLUTE", "thermal": "V24T_C1"},
    }
    solver = {
        "artifact_id": "V28_DAYAHEAD_SOLVER_BINDING_V1",
        "primary_B3_solver": "CL_MC_BD",
        "comparison_order": ["CL_MC_BD", "MONOLITHIC", "STANDARD_SINGLE_CUT_BD"],
        "within_day_parallel": False,
        "threads": 4, "seed": 20260828, "MIPGap": 0.001,
        "FeasibilityTol": 1e-6, "OptimalityTol": 1e-6, "TimeLimit_seconds": 1800,
        "equivalence_tolerance": 0.001,
        "CL_MC_BD_semantics": "ALL_CRITICAL_TIME_FULL_LP_MULTI_CUT",
        "CL_MC_BD_expansion_not_spelled_in_repository": True,
        "historical_executor_sha256": sha("dayahead/v16_3_decomposition_executor.py"),
        "v28_monolithic_copy_sha256": sha("dayahead/v28/monolithic_authority.py"),
    }
    opendss = {
        "artifact_id": "V28_DAYAHEAD_OPENDSS_BINDING_V1",
        "feeder": "IEEE_123_NODE_THREE_PHASE",
        "engine": "FRESH_OPENDSS_QSTS",
        "required_slots": 96,
        "native_regulator_capacitor_semantics_common": True,
        "local_AC_repair": False,
        "physical_violation_is_pipeline_failure": False,
        "nonconvergence_is_pipeline_failure": True,
    }
    model = {"artifact_id": "FINAL_DAYAHEAD_MODEL_V1", "status": "IMPLEMENTATION_READY", "formulation": formulation, "solver": solver, "opendss": opendss}
    write("V28_DAYAHEAD_FORMULATION_BINDING.json", formulation)
    write("V28_DAYAHEAD_SOLVER_BINDING.json", solver)
    write("V28_DAYAHEAD_OPENDSS_BINDING.json", opendss)
    write("FINAL_DAYAHEAD_MODEL_V1.json", model)
    (OUT / "FINAL_DAYAHEAD_MODEL_V1.md").write_text("# Final Day-Ahead model V1\n\nOne-shot D-1 18:00 fixed-AEST, 96-slot B0–B3 authority. CL-MC-BD is primary; Monolithic and Standard single-cut BD are sequential equivalence benchmarks.\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
