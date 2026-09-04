"""Prospective V17 common Fresh-AC restoration operator contract.

This module contains only the frozen operator vocabulary and the pre-replay
margin derivation.  The scientific runner is deliberately kept in a separate
module so the contract bytes do not change when the execution adapter evolves.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Sequence

from .authority import sha256_file
from .v17_deferrability_semantics import write_json


CONTRACT_ID = "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1"
CUT_VALIDATION_ID = "V17_AC_RESTORATION_CUT_VALIDATION_V1"
K_MAX = 5
RHO = 0.10
NUMERICAL_REPEAT_TOLERANCE = 1e-6
DEBUG_DAYS = (
    "2025-04-02", "2025-04-03", "2025-04-12", "2025-04-13",
    "2025-04-15", "2025-04-22", "2025-04-23",
)


class ViolationType(str, Enum):
    VOLTAGE_UPPER = "VOLTAGE_UPPER"
    VOLTAGE_LOWER = "VOLTAGE_LOWER"
    LINE_CURRENT = "LINE_CURRENT"
    TRANSFORMER_CURRENT = "TRANSFORMER_CURRENT"
    TRANSFORMER_KVA = "TRANSFORMER_KVA"


def canonical_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class ACViolation:
    violation_type: ViolationType
    operating_day: str
    case: str
    slot: int
    asset: str
    phase: str | None
    actual_value: float
    hard_limit: float
    signed_violation: float
    fresh_opendss_state_sha256: str
    schedule_sha256: str

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["violation_type"] = self.violation_type.value
        return value

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.payload())


@dataclass(frozen=True)
class RestorationCut:
    violation_sha256: str
    local_ac_operating_point_sha256: str
    derivative_sha256: str
    violation_type: ViolationType
    slot: int
    relation: str
    actual_value: float
    hard_limit: float
    margin: float
    trust_region_rho: float
    iteration_index: int
    control_names: tuple[str, ...]
    anchor_controls: tuple[float, ...]
    coefficients: tuple[float, ...]
    local_radius: tuple[float, ...]

    def __post_init__(self) -> None:
        width = len(self.control_names)
        if not (width == len(self.anchor_controls) == len(self.coefficients) == len(self.local_radius)):
            raise ValueError("V17_AC_CUT_AXIS_MISMATCH")
        if self.relation not in {"<=", ">="}:
            raise ValueError("V17_AC_CUT_RELATION_INVALID")
        if self.trust_region_rho != RHO:
            raise ValueError("V17_AC_CUT_RHO_NOT_FROZEN")
        if any(radius < 0.0 for radius in self.local_radius):
            raise ValueError("V17_AC_CUT_NEGATIVE_LOCAL_RADIUS")

    def payload(self) -> dict[str, Any]:
        value = asdict(self)
        value["violation_type"] = self.violation_type.value
        return value

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.payload())


def _firewall() -> dict[str, int]:
    return {
        "May_scientific_input_reads": 0,
        "June_scientific_input_reads": 0,
        "May_result_content_reads": 0,
        "June_result_content_reads": 0,
        "remaining_April_day_runs": 0,
        "AIDC_site_changes": 0,
        "beta_changes": 0,
        "PUE_changes": 0,
        "PF_changes": 0,
        "effect_selected_parameters": 0,
        "grid_benefit_selected_parameters": 0,
        "OpenDSS_calls_inside_Benders": 0,
        "scientific_replay_calls_before_contract": 0,
    }


def mint_contract(repo: Path, output: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Freeze K_MAX, rho and conservative margins from the prior probe set."""

    repo = repo.resolve(); output = output.resolve()
    validation_path = output / "V17_V5_CURRENT_REPAIR_7DAY_SURROGATE_VALIDATION.json"
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if validation["status"] != "PASS" or int(validation["probe_count"]) != 9072:
        raise RuntimeError("V17_AC_MARGIN_SOURCE_VALIDATION_NOT_FROZEN_PASS")
    if tuple(validation["debug_days"]) != DEBUG_DAYS:
        raise RuntimeError("V17_AC_MARGIN_SOURCE_DAY_AXIS_MISMATCH")
    voltage_residual = float(validation["voltage"]["max_abs_error_pu"])
    current_residual = float(
        validation["hard_current_non_dominated_gate"]["max_abs_normalized_current_error_pu"]
    )
    m_voltage = voltage_residual + NUMERICAL_REPEAT_TOLERANCE
    m_current = current_residual + NUMERICAL_REPEAT_TOLERANCE
    selected_probe_support = [
        {
            "operating_day": row["operating_day"],
            "slots": row["selected_slots"]["slots"],
            "probe_count": row["probe_count"],
        }
        for row in validation["days"]
    ]
    validation_set_sha = canonical_sha256({"support": selected_probe_support})
    cut_validation = {
        "artifact_id": CUT_VALIDATION_ID,
        "status": "PASS_FROZEN_BEFORE_APR12_REPLAY",
        "source_validation": {
            "path": str(validation_path),
            "sha256": sha256_file(validation_path),
            "debug_days": list(DEBUG_DAYS),
            "probe_count": int(validation["probe_count"]),
            "probe_support": selected_probe_support,
            "probe_support_sha256": validation_set_sha,
            "Fresh_OpenDSS_probe_reruns_for_margin_selection": 0,
        },
        "method": "max absolute local residual over frozen validation probes + deterministic repeat tolerance",
        "numerical_repeat_tolerance": NUMERICAL_REPEAT_TOLERANCE,
        "margins": {
            "m_V_pu": m_voltage,
            "m_I_pu": m_current,
            "m_transformer_kva_pu": m_current,
        },
        "residual_sources": {
            "voltage_max_abs_local_residual_pu": voltage_residual,
            "non_dominated_current_max_abs_local_residual_pu": current_residual,
            "transformer_kva_margin_rule": "conservatively inherits m_I unless a separately predeclared source-backed validation is frozen",
        },
        "Apr12_B2_outcome_used_for_margin_selection": False,
        "margin_reselection_after_replay_authorized": False,
        **_firewall(),
    }
    write_json(output / "V17_AC_RESTORATION_CUT_VALIDATION.json", cut_validation)

    contract_source = repo / "dayahead/v17_ac_restoration_contract.py"
    contract = {
        "artifact_id": CONTRACT_ID,
        "status": "FROZEN_BEFORE_APR12_REPLAY",
        "scope": ["B0", "B1", "B2", "B3"],
        "scientific_role": "COMMON_FEASIBILITY_CLOSURE_NOT_PROPOSED_METHOD_ADVANTAGE",
        "state_machine": [
            "optimization",
            "frozen_schedule_serialization",
            "Primary_Fresh_OpenDSS",
            "exact_immutable_violation_extraction",
            "PASS_OR_LOCAL_CUT_REOPTIMIZE",
        ],
        "termination": {
            "K_MAX": K_MAX,
            "iteration_zero_is_original_optimization": True,
            "pass": "terminate after Primary Fresh OpenDSS hard-feasibility PASS",
            "fail": "if FAIL at k==K_MAX, fail closed without repair or parameter change",
            "rationale": [
                "bounded sequential-feasibility restoration",
                "fixed computational guard",
                "independent of Apr-12 violation magnitude",
                "not selected from B0-B3 outcomes",
            ],
        },
        "local_trust_region": {
            "rho": RHO,
            "authority": "existing validated V16.3/V17 V5 local control radius",
            "cut_valid_only_inside_anchor_neighborhood": True,
            "second_effect_selected_radius": False,
        },
        "violation_object": {
            "immutable": True,
            "types": [item.value for item in ViolationType],
            "required_fields": list(ACViolation.__dataclass_fields__),
        },
        "cut": {
            "method": "Fresh-OpenDSS frozen-tap central finite difference at the failed schedule",
            "upper_voltage": "V_AC(u_k)+J_V_k(u-u_k)<=V_MAX-m_V",
            "lower_voltage": "V_AC(u_k)+J_V_k(u-u_k)>=V_MIN+m_V",
            "current": "I_AC(u_k)+J_I_k(u-u_k)<=1-m_I",
            "transformer_kva": "S_AC(u_k)+J_S_k(u-u_k)<=1-m_transformer_kva",
            "guard_fields": list(RestorationCut.__dataclass_fields__),
            "stale_cut_policy": "REJECT/CONSTRAIN outside the exact stored local anchor and rho neighborhood",
            "validation_artifact_sha256": sha256_file(output / "V17_AC_RESTORATION_CUT_VALIDATION.json"),
        },
        "case_authorized_controls": {
            "B0": [],
            "B1": ["AIDC_COMPUTE_FLEX"],
            "B2": ["MESS_P", "MESS_Q"],
            "B3": ["AIDC_COMPUTE_FLEX", "MESS_P", "MESS_Q"],
        },
        "objective": {
            "preserve_original_primary_objective": True,
            "weighted_restoration_objective_added": False,
            "report_original_restored_and_degradation": True,
        },
        "OpenDSS_calls_inside_Benders": 0,
        "source": {"path": str(contract_source), "sha256": sha256_file(contract_source)},
        **_firewall(),
    }
    write_json(output / "V17_AC_RESTORATION_OUTER_LOOP_CONTRACT_V1.json", contract)
    return contract, cut_validation


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("dayahead/artifacts/v17_candidate"))
    args = parser.parse_args(argv)
    contract, validation = mint_contract(args.repo, args.output)
    print(json.dumps({"contract": contract["status"], "validation": validation["status"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
