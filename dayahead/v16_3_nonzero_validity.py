"""Pure contracts and metrics for the prospective V16.3 nonzero study.

This module deliberately contains no OpenDSS or optimizer call.  It freezes
the probe grid and implements the auditable classification/reduction pieces
used by the diagnostic runner.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np


RHO_GRID = (0.10, 0.25, 0.50, 0.75, 1.00)
VOLTAGE_LIMITS = (0.95, 1.05)
VOLTAGE_PROXIMITY_PU = 0.002
CURRENT_PROXIMITY_PU = 0.02
MONITOR_CURRENT_LOADING_PU = 0.80
VOLTAGE_TOLERANCE = {
    "max_abs_candidate_vs_frozen_pu": 0.010,
    "mean_abs_candidate_vs_frozen_pu": 0.003,
    "p95_abs_candidate_vs_frozen_pu": 0.005,
    "max_abs_candidate_vs_native_pu": 0.015,
}


@dataclass(frozen=True)
class ProbeDirection:
    probe_id: str
    family: str
    direction: str
    delta_at_rho1: tuple[float, ...]
    physical_basis: str


def payload_sha256(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_probe_directions(
    controls: Sequence[str],
    aidc_down_kw: Sequence[float],
    aidc_up_kw: Sequence[float],
) -> tuple[ProbeDirection, ...]:
    """Build all directions without using an electrical evaluation result."""

    if len(controls) != 60 or len(aidc_down_kw) != 12 or len(aidc_up_kw) != 12:
        raise ValueError("V163_NONZERO_CONTROL_AXIS_MISMATCH")
    if tuple(controls[:12]) != tuple(f"aidc_load_kw[AIDC{i:02d}]" for i in range(1, 13)):
        raise ValueError("V163_NONZERO_AIDC_AXIS_MISMATCH")
    p_controls = tuple(controls[12:36])
    q_controls = tuple(controls[36:60])
    if tuple(c.replace("mess_p_kw", "mess_q_kvar") for c in p_controls) != q_controls:
        raise ValueError("V163_NONZERO_MESS_AXIS_MISMATCH")

    rows: list[ProbeDirection] = []

    def add(probe_id: str, family: str, direction: str, changes: Mapping[int, float], basis: str) -> None:
        vector = [0.0] * 60
        for index, value in changes.items():
            vector[index] = float(value)
        if not any(abs(value) > 1e-12 for value in vector):
            return
        rows.append(ProbeDirection(probe_id, family, direction, tuple(vector), basis))

    for i in range(12):
        if aidc_up_kw[i] > 1e-9:
            add(f"A_AIDC{i+1:02d}_INC", "A_SINGLE_AIDC_P", "increase", {i: aidc_up_kw[i]},
                "FROZEN_GPU_HEADROOM_MAX_KAPPA_AND_1500KVA_PCC")
        if aidc_down_kw[i] > 1e-9:
            add(f"A_AIDC{i+1:02d}_DEC", "A_SINGLE_AIDC_P", "decrease", {i: -aidc_down_kw[i]},
                "FROZEN_FLEXIBLE_POWER_TO_ZERO_WITH_RESIDUAL_PRESERVED")

    for donor in range(12):
        receiver = (donor + 1) % 12
        capacity = min(float(aidc_down_kw[donor]), float(aidc_up_kw[receiver]))
        if capacity > 1e-9:
            add(f"B_AIDC{donor+1:02d}_TO_AIDC{receiver+1:02d}", "B_ZERO_SUM_AIDC_REDISTRIBUTION",
                "clockwise_ring", {donor: -capacity, receiver: capacity},
                "EQUAL_KW_MAX_KAPPA_EQUIVALENT_WORKLOAD_SHIFT")

    for service in range(24):
        add(f"C_{service+1:02d}_DISCHARGE", "C_SINGLE_MESS_P", "discharge", {12 + service: 550.0},
            "FROZEN_MESS_P_LIMIT_550KW")
        add(f"C_{service+1:02d}_CHARGE", "C_SINGLE_MESS_P", "charge", {12 + service: -550.0},
            "FROZEN_MESS_P_LIMIT_550KW")
        add(f"D_{service+1:02d}_QPOS", "D_SINGLE_MESS_Q", "positive_q", {36 + service: 700.0},
            "FROZEN_MESS_PCS_700KVA_AT_P_ZERO")
        add(f"D_{service+1:02d}_QNEG", "D_SINGLE_MESS_Q", "negative_q", {36 + service: -700.0},
            "FROZEN_MESS_PCS_700KVA_AT_P_ZERO")

    joint_q = math.sqrt(700.0**2 - 550.0**2)
    for donor in range(12):
        receiver = (donor + 1) % 12
        capacity = min(float(aidc_down_kw[donor]), float(aidc_up_kw[receiver]))
        if capacity <= 1e-9:
            continue
        service = donor
        p_sign = 1.0 if donor % 2 == 0 else -1.0
        q_sign = 1.0 if donor % 4 < 2 else -1.0
        add(f"E_JOINT_{donor+1:02d}", "E_JOINT_AIDC_MESS", "predeclared_alternating_sign",
            {donor: -capacity, receiver: capacity, 12 + service: p_sign * 550.0,
             36 + service: q_sign * joint_q},
            "AIDC_RING_SHIFT_PLUS_MESS_550KW_AND_SQRT_700SQ_MINUS_550SQ_KVAR")
    if not rows:
        raise ValueError("V163_NONZERO_NO_PHYSICAL_DIRECTIONS")
    return tuple(rows)


def expand_rho(direction: ProbeDirection, rho: float) -> np.ndarray:
    if rho not in RHO_GRID:
        raise ValueError("V163_NONZERO_RHO_NOT_PREDECLARED")
    delta = float(rho) * np.asarray(direction.delta_at_rho1, dtype=float)
    if not np.any(np.abs(delta) > 1e-12):
        raise ValueError("V163_NONZERO_ZERO_DELTA_PROBE")
    return delta


def voltage_class(values: np.ndarray, tolerance: float = 1e-9) -> np.ndarray:
    low, high = VOLTAGE_LIMITS
    result = np.zeros(values.shape, dtype=np.int8)
    result[values < low - tolerance] = -1
    result[values > high + tolerance] = 1
    return result


def voltage_comparison(predicted: Sequence[float], actual: Sequence[float], nodes: Sequence[str]) -> dict[str, object]:
    pred = np.asarray(predicted, dtype=float)
    ac = np.asarray(actual, dtype=float)
    if pred.shape != ac.shape or pred.ndim != 1 or len(nodes) != pred.size:
        raise ValueError("V163_NONZERO_VOLTAGE_AXIS_MISMATCH")
    error = np.abs(pred - ac)
    pc = voltage_class(pred)
    ac_class = voltage_class(ac)
    worst = int(np.argmax(error))
    return {
        "max_abs_error_pu": float(error.max()),
        "mean_abs_error_pu": float(error.mean()),
        "p95_abs_error_pu": float(np.quantile(error, 0.95)),
        "predicted_Vmin_pu": float(pred.min()),
        "predicted_Vmax_pu": float(pred.max()),
        "actual_Vmin_pu": float(ac.min()),
        "actual_Vmax_pu": float(ac.max()),
        "worst_node_phase": str(nodes[worst]),
        "false_feasible_count": int(np.sum((pc == 0) & (ac_class != 0))),
        "false_infeasible_count": int(np.sum((pc != 0) & (ac_class == 0))),
        "lower_limit_disagreement_count": int(np.sum((pc == -1) != (ac_class == -1))),
        "upper_limit_disagreement_count": int(np.sum((pc == 1) != (ac_class == 1))),
    }


def validated_radius(rows: Sequence[Mapping[str, object]]) -> float | None:
    """Largest cumulative predeclared radius for which every inner probe passes."""

    accepted: float | None = None
    for rho in RHO_GRID:
        inner = [row for row in rows if float(row["rho"]) <= rho + 1e-12]
        if not inner or not all(bool(row["trust_region_pass"]) for row in inner):
            break
        accepted = float(rho)
    return accepted


def current_root_classification(evidence: Mapping[str, float | int | bool]) -> str:
    """Choose one predeclared primary root cause from measured forensic flags."""

    tap = bool(evidence.get("tap_side_conversion_material"))
    kva = bool(evidence.get("kva_vs_phase_current_material"))
    linear = bool(evidence.get("linear_flow_error_material"))
    phase = bool(evidence.get("phase_unbalance_material"))
    active = sum((tap, kva, linear, phase))
    if active > 1:
        return "CURR_CLASS_E_COMBINED"
    if tap:
        return "CURR_CLASS_A_TAP_SIDE_CURRENT_CONVERSION"
    if kva:
        return "CURR_CLASS_B_KVA_VS_PHASE_CURRENT_SEMANTICS"
    if linear:
        return "CURR_CLASS_C_LINEAR_FLOW_APPROXIMATION"
    if phase:
        return "CURR_CLASS_D_PHASE_UNBALANCE_OR_MUTUAL_COUPLING"
    return "CURR_CLASS_F_OTHER"


def trust_region_contract(rho_valid: float | None) -> dict[str, object]:
    return {
        "rho_valid": rho_valid,
        "form": "ASYMMETRIC_WEIGHTED_L_INFINITY_BOX_PLUS_EXISTING_MESS_PCS_POLYGON",
        "equations": [
            "-rho_valid*s_down[j,t] <= Delta_u[j,t] <= rho_valid*s_up[j,t]",
            "existing 16-face MESS PCS polygon retained",
        ],
        "affine": True,
        "auxiliary_variables": 0,
        "tap_variables_added": 0,
        "time_local_grid_lp_count": 96,
        "Pi_cut_form_preserved": True,
        "Farkas_cut_form_preserved": True,
    }
