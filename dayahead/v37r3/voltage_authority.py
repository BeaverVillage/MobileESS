"""April-only joint P-Q voltage authority for V37-R3.

Each source-PCC/target-PCC/phase entry is one complete ``[H_P, H_Q]``
gradient observed in a single April Fresh state.  P and Q components are
never assembled from different operating states.  The original per-slot
MESS=0 AC anchor is retained exactly by recomputing the affine constant.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from dayahead.v28r2.electrical_subproblem import slot_coefficients
from dayahead.v36.storage import attach_context


AUTHORITY_RELATIVE_PATH = Path(
    "dayahead/artifacts/v37_r3_restore_intended_cuts/"
    "V37_R3_JOINT_VOLTAGE_AUTHORITY.json"
)
AUTHORITY_SCHEMA = "V37_R3_JOINT_DIRECTIONAL_AFFINE_VOLTAGE_AUTHORITY_V1"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_joint_voltage_authority(repo: Path) -> tuple[dict[str, Any], str]:
    path = repo.resolve() / AUTHORITY_RELATIVE_PATH
    if not path.is_file():
        raise RuntimeError(f"V37_R3_JOINT_VOLTAGE_AUTHORITY_MISSING:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != AUTHORITY_SCHEMA:
        raise RuntimeError("V37_R3_JOINT_VOLTAGE_AUTHORITY_SCHEMA")
    if payload.get("classification") != "JOINT_DIRECTIONAL_AFFINE_VOLTAGE_REPAIR":
        raise RuntimeError("V37_R3_JOINT_VOLTAGE_AUTHORITY_CLASSIFICATION")
    if payload.get("authority_frozen") is not True:
        raise RuntimeError("V37_R3_JOINT_VOLTAGE_AUTHORITY_NOT_FROZEN")
    if payload.get("May_data_used_for_derivation") is not False:
        raise RuntimeError("V37_R3_MAY_CALIBRATION_FIREWALL")
    if payload.get("selectable_service_PCC_coverage") != "24/24":
        raise RuntimeError("V37_R3_JOINT_VOLTAGE_AUTHORITY_PCC_COVERAGE")
    if payload.get("cross_PCC_sensitivity") is not True:
        raise RuntimeError("V37_R3_JOINT_VOLTAGE_AUTHORITY_CROSS_PCC")
    if payload.get("phase_coverage") != ["A", "B", "C"]:
        raise RuntimeError("V37_R3_JOINT_VOLTAGE_AUTHORITY_PHASE_COVERAGE")
    return payload, _file_sha256(path)


def _entries_by_key(
    authority: Mapping[str, Any],
) -> dict[tuple[str, str], Mapping[str, Any]]:
    entries: dict[tuple[str, str], Mapping[str, Any]] = {}
    for raw in authority.get("joint_gradients", []):
        source = str(raw["source_service"]).upper()
        node = str(raw["target_bus_phase_key"]).lower()
        key = (source, node)
        if key in entries:
            raise RuntimeError(f"V37_R3_DUPLICATE_JOINT_GRADIENT:{key}")
        p = float(raw["H_P_pu_squared_per_kW"])
        q = float(raw["H_Q_pu_squared_per_kvar"])
        if not np.isfinite(p) or not np.isfinite(q) or p <= 0.0 or q <= 0.0:
            raise RuntimeError(f"V37_R3_INVALID_JOINT_GRADIENT:{key}:{p}:{q}")
        if raw.get("P_Q_same_April_state") is not True:
            raise RuntimeError(f"V37_R3_MIXED_PQ_GRADIENT:{key}")
        entries[key] = raw
    if len(entries) != 24 * 24 * 3:
        raise RuntimeError(f"V37_R3_JOINT_VOLTAGE_AUTHORITY_AXIS:{len(entries)}")
    return entries


def joint_repaired_coefficients(repo: Path, electrical: Any) -> tuple[Any, ...]:
    """Apply the frozen same-state joint gradients to normal affine rows."""

    authority, authority_sha = load_joint_voltage_authority(repo)
    day = str(electrical.voltage["operating_day"])
    expected = authority.get("base_voltage_authority_sha256_by_day", {}).get(day)
    if expected is None:
        raise RuntimeError(f"V37_R3_DAY_NOT_AUTHORIZED:{day}")
    if _file_sha256(Path(electrical.voltage_path)) != str(expected):
        raise RuntimeError(f"V37_R3_BASE_VOLTAGE_AUTHORITY_SHA:{day}")

    base = tuple(
        slot_coefficients(
            electrical.legacy_context,
            electrical.voltage,
            electrical.current,
            slot,
        )
        for slot in range(96)
    )
    nodes = tuple(map(str, electrical.voltage["node_names"]))
    controls = tuple(map(str, electrical.voltage["control_names"]))
    entries = _entries_by_key(authority)
    selectable = tuple(
        name[10:-1] for name in controls if name.startswith("mess_p_kw[")
    )
    if set(map(str.upper, authority["selectable_service_PCCs"])) != set(selectable):
        raise RuntimeError("V37_R3_SELECTABLE_SERVICE_AXIS")

    indexed: list[tuple[int, int, int, float, float]] = []
    for (source, node), entry in entries.items():
        target = str(entry["target_service"]).upper()
        phase = str(entry["phase"]).upper()
        phase_index = "ABC".index(phase) + 1
        expected_node = f"mess_{target.lower()}_pcc.{phase_index}"
        if node != expected_node:
            raise RuntimeError(
                f"V37_R3_PCC_PHASE_MAPPING:{source}:{target}:{phase}:{node}"
            )
        try:
            indexed.append((
                controls.index(f"mess_p_kw[{source}]"),
                controls.index(f"mess_q_kvar[{source}]"),
                nodes.index(node),
                float(entry["H_P_pu_squared_per_kW"]),
                float(entry["H_Q_pu_squared_per_kvar"]),
            ))
        except ValueError as error:
            raise RuntimeError(
                f"V37_R3_JOINT_AUTHORITY_AXIS:{source}:{target}:{phase}"
            ) from error

    repaired = []
    for coefficient in base:
        matrix = np.asarray(coefficient.voltage_matrix, dtype=float).copy()
        for p_index, q_index, node_index, h_p, h_q in indexed:
            matrix[p_index, node_index] = h_p
            matrix[q_index, node_index] = h_q
        anchor = np.asarray(coefficient.anchor, dtype=float)
        anchor_v_squared = np.asarray(
            electrical.voltage["anchor_v_squared"][coefficient.slot], dtype=float,
        )
        constant = anchor_v_squared - matrix.T @ anchor
        if not np.allclose(
            constant + matrix.T @ anchor,
            anchor_v_squared,
            atol=1e-14,
            rtol=0.0,
        ):
            raise RuntimeError(f"V37_R3_ANCHOR_NOT_PRESERVED:{coefficient.slot}")
        digest = hashlib.sha256(json.dumps({
            "base_coefficient_sha256": coefficient.coefficient_sha256,
            "joint_voltage_authority_sha256": authority_sha,
            "slot": coefficient.slot,
        }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        repaired.append(replace(
            coefficient,
            voltage_constant=constant,
            voltage_matrix=matrix,
            coefficient_sha256=digest,
        ))
    result = tuple(repaired)
    attach_context(result, electrical.legacy_context)
    return result
