"""Read-only reuse of the frozen V37 affine planning feasibility gate."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from dayahead.v33m.mess_trajectory import MessTrajectory
from dayahead.v35.execution import _planning_grid
from dayahead.v37.context import load_day_context
from dayahead.v37r3.voltage_authority import joint_repaired_coefficients
from dayahead.v38.authority import canonical_sha256
from dayahead.v39c.freeze import atomic_json

from .contracts import CACHE_ROOT


def planning_feasibility_gate(
    repo_text: str, operating_day: str, candidate_pcc: dict[str, list[list[float]]],
) -> dict[str, dict[str, Any]]:
    """Evaluate RW/RSP candidates without invoking Fresh or restoration."""

    repo = Path(repo_text).resolve()
    candidate_sha = canonical_sha256(candidate_pcc)
    cache = repo / CACHE_ROOT / operating_day / f"{candidate_sha}.json"
    if cache.is_file():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if cached.get("candidate_SHA256") == candidate_sha:
            return dict(cached["modes"])
    _data, electrical = load_day_context(repo, operating_day)
    try:
        coefficients = joint_repaired_coefficients(repo, electrical)
        modes: dict[str, dict[str, Any]] = {}
        for mode in sorted(candidate_pcc):
            if mode not in {"RW", "RSP"}:
                raise RuntimeError(f"V39D_PLANNING_MODE:{mode}")
            pcc = np.asarray(candidate_pcc[mode], dtype=float)
            if pcc.shape != (96, 12) or not np.isfinite(pcc).all():
                raise RuntimeError(f"V39D_PLANNING_PCC_AXIS:{operating_day}:{mode}")
            _arrays, summary = _planning_grid(
                coefficients, electrical.voltage, pcc, MessTrajectory(())
            )
            modes[mode] = {
                "status": "PASS" if bool(summary["pass"]) else "INFEASIBLE",
                "planning_pass": bool(summary["pass"]),
                "planning_rho": float(summary["rho"]),
                "Vmin_pu": float(summary["Vmin_pu"]),
                "Vmax_pu": float(summary["Vmax_pu"]),
                "voltage_violation_count": int(summary["voltage_violation_count"]),
                "line_current_violation_count": int(summary["line_current_violation_count"]),
                "transformer_current_violation_count": int(
                    summary["transformer_current_violation_count"]
                ),
                "transformer_kva_violation_count": int(
                    summary["transformer_kva_violation_count"]
                ),
                "Fresh_calls": 0,
                "restoration_calls": 0,
                "decision_oracle": "FROZEN_V37_PLANNING_MODEL",
            }
    finally:
        electrical.voltage.close()
        electrical.current.close()
    atomic_json(cache, {
        "artifact_id": "V39D_SAME_DAY_PLANNING_GATE_CACHE_V1",
        "operating_day": operating_day,
        "candidate_SHA256": candidate_sha,
        "cross_day_result_read_count": 0,
        "modes": modes,
    })
    return modes


__all__ = ["planning_feasibility_gate"]
