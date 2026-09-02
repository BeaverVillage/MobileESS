"""Frozen V30 scientific contracts and canonical fingerprints."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping


STARTING_SHA = "261fb1ce7f13c758bb419b2e1b5eb1f12c49820b"
V29R2_SHA = "9db9adc1b1b2388c5e6939abdd46d089e1e7d831"
V29R2_ARTIFACT_SHA = "ca24e661450b7af0e894730602166c792711273e3b4a873976b7a61b4f96a3b2"
V29R3_ARTIFACT_SHA = "3ab09255797942f04a2aa0cd15f2c5c1870bcb71b6dff7b0676b76b853f6e223"
OFFICIAL_CASES = ("B0", "B1", "B2", "B3")
RECOURSE_CASES = ("B1", "B3")
ANCHOR_BY_CASE = {"B1": "B0", "B3": "B2"}
DT_HOURS = 0.25
SLOTS = 96
SCENARIO_CANDIDATES = (8, 16, 32, 64)
CASE_ACTUATORS = {
    "B0": {"aidc": False, "recourse": False, "mess": False},
    "B1": {"aidc": True, "recourse": True, "mess": False},
    "B2": {"aidc": False, "recourse": False, "mess": True},
    "B3": {"aidc": True, "recourse": True, "mess": True},
}


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode()


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False).encode() + b"\n")


def four_case_contract() -> dict[str, object]:
    return {
        "artifact_id": "V30_FOUR_CASE_CONTRACT_V1",
        "status": "FROZEN",
        "official_cases": list(OFFICIAL_CASES),
        "official_case_count": 4,
        "case_actuators": CASE_ACTUATORS,
        "comparisons": {"B0_to_B1": "AIDC_TWO_STAGE", "B0_to_B2": "MESS", "B2_to_B3": "AIDC_TWO_STAGE_WITH_MESS", "B1_to_B3": "MESS_WITH_AIDC"},
        "PI_status": "DIAGNOSTIC_ONLY_NOT_AN_OFFICIAL_CASE",
        "B0_B2_reference_compute": "BYTE_AND_SHA_IDENTICAL",
        "B1_B3_AIDC_policy": "CANONICAL_CONFIG_IDENTICAL",
    }


def two_stage_contract() -> dict[str, object]:
    return {
        "artifact_id": "V30_TWO_STAGE_RECOURSE_CONTRACT_V1",
        "status": "FROZEN",
        "stage_1": {
            "namespace": "DAYAHEAD",
            "decision_variables": ["x_DA[b,r,t]", "h_REC[r,t]", "rho_V30", "P_MESS_DA[m,t] when enabled", "Q_MESS_DA[m,t] when enabled", "scenario recourse feasibility z[omega,b,r,t] when enabled"],
            "objective_hierarchy": ["min worst certified phase-current loading", "min expected recourse displacement", "deterministic schedule tie-break"],
            "manual_headroom_percentage": None,
        },
        "stage_2": {
            "namespace": "ACTUAL_CAUSAL",
            "decision_variable": "y_ACT[b,r,t]",
            "resolution_minutes": 15,
            "epochs_per_complete_day": 96,
            "spatial_only": True,
            "same_slot_constraint": "sum_r y_ACT[b,r,t] <= sum_r x_DA[b,r,t]",
            "temporal_recourse_variable": None,
            "objective_hierarchy": ["physical/causal/safety feasibility", "max service", "min phase-aware grid metric", "min DA placement deviation"],
            "running_job_migration": False,
            "preemption": False,
            "mess_reoptimization": False,
            "full_system_reoptimization": False,
        },
    }


def information_firewall_contract() -> dict[str, object]:
    return {
        "artifact_id": "V30_ACTUAL_INFORMATION_FIREWALL_CONTRACT_V1",
        "status": "FROZEN",
        "allowed_at_slot_t": ["frozen DA schedule", "actual arrivals observed through t", "current backlog", "current rack residual capacity", "current realized demand/PV", "current realized weather/C1 inputs", "current MESS physical availability/state", "frozen feeder/model", "pre-April certified sensitivity/safety"],
        "forbidden": ["future workload arrivals", "future rack state", "future demand/PV/weather", "future grid loading", "end-of-day outcome", "PI trajectory", "April lookup", "Fresh OpenDSS decision oracle"],
        "required_future_actual_reads": 0,
    }


def eligibility_contract() -> dict[str, object]:
    return {
        "artifact_id": "V30_RECOURSE_ELIGIBILITY_CONTRACT_V1",
        "status": "FROZEN",
        "included": ["strict FULL-node", "source-backed actual availability", "not-yet-started", "no recorded sharing", "supported node count"],
        "excluded": ["PARTIAL/shared", "uncontrolled", "running", "synthetic"],
        "running_job_migration": 0,
        "preemption": 0,
        "checkpoint_restart": 0,
        "synthetic_workload": 0,
        "synthetic_deadline": 0,
    }


def aidc_policy_config(margin: float, scenario_count: int, scenario_sha: str) -> dict[str, object]:
    return {
        "policy_id": "V30_AIDC_TWO_STAGE_SPATIAL_RECOURSE_V1",
        "eligibility": eligibility_contract(),
        "spatial_domain": "ALL_AND_ONLY_48_FROZEN_CASE_STUDY_RACKS",
        "cross_site_semantics": "PRE_EXECUTION_REASSIGNMENT_NOT_LIVE_WAN_MIGRATION",
        "scenario_count": scenario_count,
        "scenario_set_sha256": scenario_sha,
        "no_regret_margin_pu": margin,
        "objective_hierarchy": ["MAX_SERVICE", "MIN_PHASE_CURRENT_METRIC", "MIN_DA_DEVIATION"],
        "tie_break": ["ORIGINAL_RACK", "SAME_AIDC", "OTHER_AIDC", "CANONICAL_RACK_ID"],
        "rho_AIDC": 1.0,
        "AIDC_PF": 0.95,
        "causal": True,
        "same_slot_only": True,
        "future_actual_reads": 0,
    }


def assert_official_case_map(values: Mapping[str, object]) -> None:
    if tuple(values) != OFFICIAL_CASES:
        raise ValueError("V30_OFFICIAL_CASE_SET_MUST_BE_EXACTLY_B0_B1_B2_B3")
