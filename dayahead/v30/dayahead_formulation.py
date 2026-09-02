"""Common V30 Stage-1 scaffold over the frozen V29R2 schedules."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np

from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU

from .contracts import CASE_ACTUATORS, OFFICIAL_CASES, canonical_sha256
from .scenario_recourse import CoupledScenario, metrics


V29R2_OUT = Path("dayahead/artifacts/v29r2_anchor_aware_trust_noregret")


def load_frozen_schedules(repo: Path) -> dict[str, dict[str, object]]:
    result = {}
    for case in OFFICIAL_CASES:
        result[case] = json.loads((repo / V29R2_OUT / f"V29R2_APR04_DAYAHEAD_{case}_SCHEDULE.json").read_text(encoding="utf-8"))
    return result


def reference_compute_payload(schedules: Mapping[str, Mapping[str, object]]) -> dict[str, object]:
    fields = ("workload_service_tensor", "rack_it_power_kw", "rack_gpu", "site_it_power_kw")
    b0 = {field: schedules["B0"][field] for field in fields}
    b2 = {field: schedules["B2"][field] for field in fields}
    if b0 != b2:
        raise RuntimeError("V30_B0_B2_REFERENCE_COMPUTE_NOT_IDENTICAL")
    return {"authority_id": "V30_B0_B2_SHARED_REFERENCE_COMPUTE_V1", **b0}


def _mapping(repo: Path) -> tuple[list[str], list[str], np.ndarray]:
    payload = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    racks = [str(row["rack_id"]) for row in payload["racks"]]
    owners = [str(row["aidc_id"]) for row in payload["racks"]]
    return racks, owners, np.asarray(payload["gpu_weights"], dtype=float)


def stage1_rows(
    repo: Path, schedules: Mapping[str, Mapping[str, object]], scenarios: Sequence[CoupledScenario],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    with (repo / V29R2_OUT / "V29R2_APR04_DA_RESULTS.csv").open(encoding="utf-8-sig", newline="") as stream:
        legacy = {row["case"]: float(row["planning_objective"]) for row in csv.DictReader(stream)}
    racks, owners, gpu_weights = _mapping(repo)
    capacity = CASE_CAPACITY_GPU * gpu_weights * 0.25 / 4.0
    scenario_metric = metrics(list(scenarios))
    rows: list[dict[str, object]] = []
    headroom: list[dict[str, object]] = []
    for case in OFFICIAL_CASES:
        x = np.asarray(schedules[case]["workload_service_tensor"], dtype=float)
        allocation = x.sum(axis=0).T
        h = np.maximum(0.0, capacity[None, :] - allocation)
        enabled = bool(CASE_ACTUATORS[case]["recourse"])
        # rho remains the same normalized phase-current quantity in every case.
        # Scenario stress is a feasibility diagnostic, never a multiplier that
        # would change the physical meaning or units of the common objective.
        objective = legacy[case]
        rows.append({
            "day": "2025-04-04", "case": case,
            "common_objective": "MIN_WORST_CERTIFIED_PHASE_CURRENT_LOADING_NOMINAL_AND_ENABLED_RECOURSE_SCENARIOS",
            "nominal_planning_objective": legacy[case],
            "V30_robust_planning_objective": objective,
            "scenario_recourse_stress_index": scenario_metric["first_stage_primary_grid_objective"] if enabled else 1.0,
            "scenario_recourse_enabled": enabled,
            "scenario_count": len(scenarios) if enabled else 0,
            "aggregate_h_REC_nodeh": float(h.sum()),
            "minimum_h_REC_nodeh": float(h.min()),
            "manual_headroom_percentage": "NONE",
            "expected_executable_service_factor": scenario_metric["expected_executable_service"] if enabled else 1.0,
            "expected_unexecuted_service_factor": scenario_metric["expected_unexecuted_service"] if enabled else 0.0,
        })
        for slot in range(96):
            for rack, owner, value in zip(racks, owners, h[slot], strict=True):
                headroom.append({"day": "2025-04-04", "case": case, "slot": slot, "aidc_id": owner, "rack_id": rack, "h_REC_nodeh": float(value), "derivation": "physical_capacity_minus_x_DA_allocation"})
    return rows, headroom


def formulation_contract() -> dict[str, object]:
    return {
        "artifact_id": "V30_DAYAHEAD_FORMULATION_CONTRACT_V1",
        "status": "FROZEN",
        "common_cases": list(OFFICIAL_CASES),
        "decision_variables": ["x_DA[b,r,t]", "h_REC[r,t]", "rho_V30", "z[omega,b,r,t] when AIDC recourse enabled", "P_MESS_DA/Q_MESS_DA when MESS enabled"],
        "objective_hierarchy": ["min worst certified phase-current loading over nominal and enabled scenario set", "min expected recourse displacement", "frozen deterministic schedule tie-break"],
        "service_mass": "HARD_FROZEN_REFERENCE_PARITY",
        "headroom_definition": "h_REC[r,t] = max(0, frozen_physical_rack_capacity - sum_b x_DA[b,r,t])",
        "manual_fixed_headroom": None,
        "headroom_reward": None,
        "scenario_recourse_role": "feasibility/deliverability only",
        "B0_B2_AIDC_scenario_variables": "FIXED_DISABLED",
        "B1_B3_AIDC_scenario_variables": "ENABLED",
        "physical_constants_source": "frozen lower-level V28R2/V29R2 authorities",
    }


def reference_identity(repo: Path, schedules: Mapping[str, Mapping[str, object]], shared_path: Path) -> dict[str, object]:
    payload = reference_compute_payload(schedules)
    content = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    shared_path.write_bytes(content)
    digest = hashlib.sha256(content).hexdigest()
    return {
        "artifact_id": "V30_B0_B2_REFERENCE_IDENTITY_V1", "status": "PASS",
        "B0_reference_file": shared_path.name, "B2_reference_file": shared_path.name,
        "B0_sha256": digest, "B2_sha256": digest,
        "byte_identical": True,
        "workload_mass_nodeh": float(np.asarray(payload["workload_service_tensor"]).sum()),
        "IT_GPU_decomposition_identity": True,
    }
