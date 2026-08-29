"""Evaluation-only realized natural-component removal then fixed-schedule add."""

from __future__ import annotations

from typing import Sequence

AUTHORITY_ID = "AIDC_REALIZED_REFERENCE_DECOMPOSITION_V1"


def realized_replay(
    actual_total: Sequence[float], actual_natural_flex: Sequence[float], executed_flex_by_rack: Sequence[Sequence[float]], weights: Sequence[float]
) -> dict[str, tuple]:
    if len(actual_total) != 96 or len(actual_natural_flex) != 96 or len(executed_flex_by_rack) != 96:
        raise ValueError("REALIZED_DECOMPOSITION_REQUIRES_96_SLOTS")
    if abs(sum(weights) - 1.0) > 1e-9 or any(weight < 0 for weight in weights):
        raise ValueError("FROZEN_REALIZED_MAPPING_WEIGHTS_INVALID")
    system_residual = tuple(float(total) - float(natural) for total, natural in zip(actual_total, actual_natural_flex))
    if any(value < -1e-9 for value in system_residual):
        raise ValueError("FAIL_REALIZED_REFERENCE_DECOMPOSITION")
    rack_residual = tuple(tuple(max(0.0, value) * weight for weight in weights) for value in system_residual)
    replay = tuple(tuple(a + b for a, b in zip(residual, executed)) for residual, executed in zip(rack_residual, executed_flex_by_rack))
    return {
        "system_residual": system_residual,
        "rack_residual": rack_residual,
        "rack_replay": replay,
        "solver_call_count": 0,
        "opendss_call_count": 0,
    }
