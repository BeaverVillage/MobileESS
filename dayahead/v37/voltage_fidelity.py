"""V37-R2 phase/PCC-specific direct-affine voltage authority.

The base D-1 AC anchor remains unchanged.  This module applies only the
calibrated MESS P/Q slope multipliers recorded by the V37-R2 authority and
recomputes the affine constant so the original zero-MESS anchor is preserved
exactly.  It does not add cuts or call OpenDSS from an optimizer.
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
    "dayahead/artifacts/v37_r2_voltage_fidelity_repair/"
    "V37_R2_REPAIRED_VOLTAGE_AUTHORITY.json"
)
AUTHORITY_SCHEMA = "V37_R2_DIRECT_AFFINE_VOLTAGE_AUTHORITY_V3"


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_voltage_fidelity_authority(repo: Path) -> tuple[dict[str, Any], str]:
    path = repo.resolve() / AUTHORITY_RELATIVE_PATH
    if not path.is_file():
        raise RuntimeError(f"V37_R2_VOLTAGE_AUTHORITY_MISSING:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_id") != AUTHORITY_SCHEMA:
        raise RuntimeError("V37_R2_VOLTAGE_AUTHORITY_SCHEMA")
    if payload.get("classification") != "DIRECT_AFFINE_VOLTAGE_FIDELITY_REPAIR":
        raise RuntimeError("V37_R2_VOLTAGE_AUTHORITY_CLASSIFICATION")
    if payload.get("Benders_changed") is not False:
        raise RuntimeError("V37_R2_BENDERS_FIREWALL")
    if payload.get("authority_frozen") is not True:
        raise RuntimeError("V37_R2_VOLTAGE_AUTHORITY_NOT_FROZEN")
    if payload.get("selectable_service_PCC_coverage") != "24/24":
        raise RuntimeError("V37_R2_VOLTAGE_AUTHORITY_PCC_COVERAGE")
    if payload.get("cross_PCC_sensitivity") is not True:
        raise RuntimeError("V37_R2_VOLTAGE_AUTHORITY_CROSS_PCC")
    if payload.get("phase_coverage") != ["A", "B", "C"]:
        raise RuntimeError("V37_R2_VOLTAGE_AUTHORITY_PHASE_COVERAGE")
    if payload.get("April_background_coverage_PASS") is not True:
        raise RuntimeError("V37_R2_VOLTAGE_AUTHORITY_APRIL_COVERAGE")
    return payload, _file_sha256(path)


def _entries_by_key(authority: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    entries: dict[tuple[str, str], Mapping[str, Any]] = {}
    for raw in authority.get("corrections", []):
        source_service = str(raw["source_service"]).upper()
        target_node = str(raw["target_bus_phase_key"]).lower()
        phase = str(raw["phase"]).upper()
        key = (source_service, target_node)
        if key in entries or phase not in "ABC":
            raise RuntimeError(f"V37_R2_VOLTAGE_AUTHORITY_KEY:{key}")
        for axis in ("P", "Q"):
            floor = float(raw[f"{axis}_minimum_abs_H"])
            sign = int(raw[f"{axis}_physical_sign"])
            if not np.isfinite(floor) or floor < 0.0 or sign not in {-1, 0, 1}:
                raise RuntimeError(
                    f"V37_R2_INVALID_SIGNED_H_FLOOR:{key}:{axis}:{sign}:{floor}"
                )
            if (floor == 0.0) != (sign == 0):
                raise RuntimeError(f"V37_R2_SIGNED_H_FLOOR_ZERO:{key}:{axis}")
        entries[key] = raw
    if len(entries) != 24 * 24 * 3:
        raise RuntimeError(f"V37_R2_VOLTAGE_AUTHORITY_AXIS:{len(entries)}")
    return entries


def repaired_coefficients(repo: Path, electrical: Any) -> tuple[Any, ...]:
    """Build the normal 96 direct-affine rows, then apply the R2 slope authority."""

    authority, authority_sha = load_voltage_fidelity_authority(repo)
    day = str(electrical.voltage["operating_day"])
    expected = authority.get("base_voltage_authority_sha256_by_day", {}).get(day)
    if expected is None:
        raise RuntimeError(f"V37_R2_DAY_NOT_CALIBRATED:{day}")
    voltage_path = Path(electrical.voltage_path)
    if _file_sha256(voltage_path) != str(expected):
        raise RuntimeError(f"V37_R2_BASE_VOLTAGE_AUTHORITY_SHA:{day}")

    base = tuple(
        slot_coefficients(
            electrical.legacy_context, electrical.voltage, electrical.current, slot,
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
        raise RuntimeError("V37_R2_SELECTABLE_SERVICE_AXIS")
    indexed_entries = []
    for (source_service, node), entry in entries.items():
        target_service = str(entry["target_service"]).upper()
        phase = str(entry["phase"]).upper()
        phase_index = "ABC".index(phase) + 1
        expected_node = f"mess_{target_service.lower()}_pcc.{phase_index}"
        if node != expected_node:
            raise RuntimeError(
                f"V37_R2_PCC_PHASE_MAPPING:{source_service}:{target_service}:{phase}:{node}"
            )
        try:
            node_index = nodes.index(node)
            p_index = controls.index(f"mess_p_kw[{source_service}]")
            q_index = controls.index(f"mess_q_kvar[{source_service}]")
        except ValueError as error:
            raise RuntimeError(
                f"V37_R2_AUTHORITY_AXIS:{source_service}:{target_service}:{phase}"
            ) from error
        indexed_entries.append((
            source_service, target_service, phase, p_index, q_index, node_index,
            int(entry["P_physical_sign"]), int(entry["Q_physical_sign"]),
            float(entry["P_minimum_abs_H"]), float(entry["Q_minimum_abs_H"]),
        ))
    repaired = []
    for coefficient in base:
        matrix = np.asarray(coefficient.voltage_matrix, dtype=float).copy()
        for (
            source_service, target_service, phase, p_index, q_index, node_index,
            p_sign, q_sign, p_floor, q_floor,
        ) in indexed_entries:
            old_p = float(matrix[p_index, node_index])
            old_q = float(matrix[q_index, node_index])
            new_p = (
                old_p if p_sign == 0
                or (int(np.sign(old_p)) == p_sign and abs(old_p) >= p_floor)
                else float(p_sign) * p_floor
            )
            new_q = (
                old_q if q_sign == 0
                or (int(np.sign(old_q)) == q_sign and abs(old_q) >= q_floor)
                else float(q_sign) * q_floor
            )
            matrix[p_index, node_index] = new_p
            matrix[q_index, node_index] = new_q
            if p_sign and int(np.sign(matrix[p_index, node_index])) != p_sign:
                raise RuntimeError(
                    f"V37_R2_P_PHYSICAL_SIGN:{source_service}:{target_service}:{phase}"
                )
            if q_sign and int(np.sign(matrix[q_index, node_index])) != q_sign:
                raise RuntimeError(
                    f"V37_R2_Q_PHYSICAL_SIGN:{source_service}:{target_service}:{phase}"
                )

        anchor = np.asarray(coefficient.anchor, dtype=float)
        anchor_v_squared = np.asarray(
            electrical.voltage["anchor_v_squared"][coefficient.slot], dtype=float,
        )
        constant = anchor_v_squared - matrix.T @ anchor
        if not np.allclose(constant + matrix.T @ anchor, anchor_v_squared, atol=1e-14, rtol=0.0):
            raise RuntimeError(f"V37_R2_ANCHOR_NOT_PRESERVED:{coefficient.slot}")
        digest = hashlib.sha256(json.dumps({
            "base_coefficient_sha256": coefficient.coefficient_sha256,
            "repair_authority_sha256": authority_sha,
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
