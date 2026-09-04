"""Capacity-proportional decomposition of the frozen aggregate AIDC model."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from dayahead.v28r2.c1_affine import exact_c1_pcc_kw, load_c1
from dayahead.v28r2.formulation import PF_TAN
from dayahead.v28r2.source_cache import day_root
from dayahead.v36.aidc import _site_weights
from dayahead.v36.contracts import SOURCE_DATA_REPOSITORY

from .contracts import (
    CENTER_SWING_W_PER_GPU,
    C_REF_W_PER_GPU,
    FULL_ACTIVE_IT_KW,
    GPU_CAPACITY,
    IDLE_W_PER_GPU,
    POWER_TOLERANCE_KW,
)


def site_it_power_kw(site_capacity_gpu: int, active_gpu: int) -> Decimal:
    """Return the mandated synthetic site power without binary-float drift."""

    capacity = int(site_capacity_gpu)
    active = int(active_gpu)
    if capacity < 0 or not 0 <= active <= capacity:
        raise ValueError("V39A_SITE_GPU_RANGE")
    return (
        Decimal(capacity) * IDLE_W_PER_GPU
        + Decimal(active) * CENTER_SWING_W_PER_GPU
    ) / Decimal(1000)


def aggregate_it_power_kw(active_gpu: int) -> Decimal:
    active = int(active_gpu)
    if not 0 <= active <= GPU_CAPACITY:
        raise ValueError("V39A_AGGREGATE_GPU_RANGE")
    return FULL_ACTIVE_IT_KW - (
        Decimal(GPU_CAPACITY - active) * CENTER_SWING_W_PER_GPU / Decimal(1000)
    )


def validate_power_conservation(
    site_capacity: Mapping[str, int], site_active: Mapping[str, int]
) -> dict[str, Any]:
    if set(site_capacity) != set(site_active):
        raise ValueError("V39A_SITE_POWER_AXIS")
    total_active = sum(int(value) for value in site_active.values())
    site_total = sum(
        (site_it_power_kw(site_capacity[site], site_active[site]) for site in site_capacity),
        Decimal(0),
    )
    aggregate = aggregate_it_power_kw(total_active)
    error = abs(site_total - aggregate)
    return {
        "status": "PASS" if error <= POWER_TOLERANCE_KW else "FAIL",
        "active_GPU": total_active,
        "site_IT_power_sum_kW": str(site_total),
        "aggregate_V37_IT_power_kW": str(aggregate),
        "absolute_error_kW": str(error),
        "tolerance_kW": str(POWER_TOLERANCE_KW),
    }


def frozen_site_to_pcc(repo: Path) -> dict[str, str]:
    """Expose canonical AIDC keys over the frozen legacy PCC-node labels."""

    aidcs, _weights, legacy_pcc = _site_weights(repo)
    mapping = dict(zip(aidcs, legacy_pcc, strict=True))
    if len(mapping) != 12:
        raise RuntimeError("V39A_AIDC_PCC_MAPPING_AXIS")
    return mapping


def site_pcc_power(
    repo: Path,
    operating_day: str,
    site_it: pd.DataFrame,
) -> pd.DataFrame:
    """Apply unchanged C1 independently at every frozen AIDC PCC mapping."""

    mapping = frozen_site_to_pcc(repo)
    weather = pd.read_parquet(
        day_root(SOURCE_DATA_REPOSITORY, operating_day) / "gfs_d1_weather.parquet"
    )
    if len(weather) != 96:
        raise RuntimeError("V39A_GFS_AXIS")
    parameters = load_c1(
        repo / "dayahead/artifacts/v24t_thermal_aware_aidc/"
        "V24T_C1_QUASISTATIC_MODEL.json"
    )
    rows: list[dict[str, Any]] = []
    for row in site_it.itertuples(index=False):
        slot = int(row.slot)
        it_kw = float(row.IT_power_kW)
        p_kw = float(exact_c1_pcc_kw(
            it_kw,
            float(weather.iloc[slot]["t_wb_c"]),
            float(weather.iloc[slot]["rh_pct"]),
            parameters,
        ))
        rows.append({
            "operating_day": operating_day,
            "slot": slot,
            "temporal_mode": str(row.temporal_mode),
            "AIDC": str(row.AIDC),
            "existing_feeder_PCC_node": mapping[str(row.AIDC)],
            "IT_power_kW": it_kw,
            "PCC_P_kW": p_kw,
            "PCC_Q_kvar": p_kw * PF_TAN,
            "C1_changed": False,
            "additional_1_30_multiplier_used": False,
        })
    return pd.DataFrame(rows)


__all__ = [
    "aggregate_it_power_kw",
    "frozen_site_to_pcc",
    "site_it_power_kw",
    "site_pcc_power",
    "validate_power_conservation",
]
