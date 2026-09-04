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
AUTHORITY_SCHEMA = "V37_R2_DIRECT_AFFINE_VOLTAGE_AUTHORITY_V1"


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
    return payload, _file_sha256(path)


def _entries_by_key(authority: Mapping[str, Any]) -> dict[tuple[str, str], Mapping[str, Any]]:
    entries: dict[tuple[str, str], Mapping[str, Any]] = {}
    for raw in authority.get("corrections", []):
        service = str(raw["service"]).upper()
        phase = str(raw["phase"]).upper()
        key = (service, phase)
        if key in entries or phase not in "ABC":
            raise RuntimeError(f"V37_R2_VOLTAGE_AUTHORITY_KEY:{key}")
        for field in ("P_scale", "Q_scale"):
            value = float(raw[field])
            if not np.isfinite(value) or value < 1.0:
                raise RuntimeError(f"V37_R2_NONCONSERVATIVE_SCALE:{key}:{field}:{value}")
        entries[key] = raw
    if not entries:
        raise RuntimeError("V37_R2_EMPTY_VOLTAGE_AUTHORITY")
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
    repaired = []
    for coefficient in base:
        matrix = np.asarray(coefficient.voltage_matrix, dtype=float).copy()
        for (service, phase), entry in entries.items():
            node = str(entry["target_bus_phase_key"])
            phase_index = "ABC".index(phase) + 1
            expected_node = f"mess_{service.lower()}_pcc.{phase_index}"
            if node != expected_node:
                raise RuntimeError(f"V37_R2_PCC_PHASE_MAPPING:{service}:{phase}:{node}")
            try:
                node_index = nodes.index(node)
                p_index = controls.index(f"mess_p_kw[{service}]")
                q_index = controls.index(f"mess_q_kvar[{service}]")
            except ValueError as error:
                raise RuntimeError(f"V37_R2_AUTHORITY_AXIS:{service}:{phase}") from error
            old_p = float(matrix[p_index, node_index])
            old_q = float(matrix[q_index, node_index])
            matrix[p_index, node_index] = old_p * float(entry["P_scale"])
            matrix[q_index, node_index] = old_q * float(entry["Q_scale"])
            if np.sign(matrix[p_index, node_index]) != np.sign(old_p):
                raise RuntimeError(f"V37_R2_P_SIGN_REVERSAL:{service}:{phase}")
            if np.sign(matrix[q_index, node_index]) != np.sign(old_q):
                raise RuntimeError(f"V37_R2_Q_SIGN_REVERSAL:{service}:{phase}")

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
