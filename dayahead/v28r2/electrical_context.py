"""Load the audited V16.3 electrical coefficient context for V28R2 solvers.

This production-side module deliberately cannot generate coefficients.  The
OpenDSS preparation adapter lives in ``electrical_cache_prepare`` so the
Monolithic/Benders import graph only consumes frozen NPZ inputs.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from dayahead.full_ieee123_g11_v16_1 import build_full_grid_binding
from dayahead.grid_background_v16_2 import BackgroundSourcePaths, build_authority_background_binding
from dayahead.run_authority_semantic_g11_v16_2 import _default_background_paths
from dayahead.v28r2.formulation import V28R2FormulationData


@dataclass(frozen=True)
class ElectricalContext:
    legacy_context: tuple[object, ...]
    voltage: object
    current: object
    source_root: Path
    voltage_path: Path
    current_path: Path


@dataclass(frozen=True)
class LegacyReferenceView:
    authority_id: str
    allocation: object
    terminal_backlog: object
    flexible_power_kw: object
    flexible_gpu: object
    max_flexible_gpu_cap_violation: float
    legacy_rack_power_cap_active_constraint_call_count: int
    grid_signal_read_count: int
    mess_signal_read_count: int


def source_root(repo: Path) -> Path:
    return repo.parent / "tmp/c12_exact_sources_repo_cleanup/c12_exact_sources/v2038_parent/Conversation3_Exact_AC_Remediation_Sweep_From_Conversation1_V2038/reference"


def _portable(path: Path) -> Path:
    text = str(path)
    if os.name == "nt":
        return path
    if text.startswith("\\\\wsl.localhost\\Ubuntu-MobileESS-D\\"):
        return Path("/") / text.split("Ubuntu-MobileESS-D\\", 1)[1].replace("\\", "/")
    if len(text) >= 3 and text[1:3] == ":\\":
        return Path("/mnt") / text[0].lower() / text[3:].replace("\\", "/")
    return path


def portable_background_paths(repo: Path, source: Path) -> BackgroundSourcePaths:
    frozen = _default_background_paths(repo, source)
    return BackgroundSourcePaths(**{
        field: _portable(getattr(frozen, field))
        for field in frozen.__dataclass_fields__
    })


def _legacy_reference(data: V28R2FormulationData) -> dict[str, object]:
    allocation = {
        (cohort, rack, slot): float(data.reference.x_ref_nodeh[c, r, slot])
        for c, cohort in enumerate(data.cohort_ids)
        for r, rack in enumerate(data.rack_ids)
        for slot in range(96)
    }
    reference = LegacyReferenceView(
        authority_id="REFERENCE_COMPUTE_SCHEDULE_V2",
        allocation=allocation,
        terminal_backlog={cohort: float(data.reference.backlog_nodeh[-1, c]) for c, cohort in enumerate(data.cohort_ids)},
        flexible_power_kw=tuple(tuple(map(float, data.reference.p_f_ref_kw[:, slot])) for slot in range(96)),
        flexible_gpu=tuple(tuple(map(float, data.reference.g_f_ref_gpu[:, slot])) for slot in range(96)),
        max_flexible_gpu_cap_violation=0.0,
        legacy_rack_power_cap_active_constraint_call_count=0,
        grid_signal_read_count=0,
        mess_signal_read_count=0,
    )
    rack_index = {rack: index for index, rack in enumerate(data.rack_ids)}
    coefficients = data.c1_by_site_slot
    plan = np.zeros((96, 12), dtype=float)
    for aidc_index, aidc in enumerate(data.aidc_ids):
        indices = [rack_index[rack] for rack, owner in zip(data.rack_ids, data.rack_aidc, strict=True) if owner == aidc]
        for slot in range(96):
            it = float(data.delta.p_res_plan_kw[indices, slot].sum() + data.reference.p_f_ref_kw[indices, slot].sum())
            coefficient = coefficients[(aidc, slot)]
            plan[slot, aidc_index] = coefficient.slope * it + coefficient.intercept_kw
    return {
        "reference": reference,
        "plan_kw_96x12": tuple(tuple(map(float, row)) for row in plan),
        "gpu_capacities": tuple(map(float, data.rack_gpu_capacity)),
        "p_res_aidc": tuple(
            tuple(float(data.delta.p_res_plan_kw[
                [r for r, owner in enumerate(data.rack_aidc) if owner == aidc], slot
            ].sum()) for aidc in data.aidc_ids)
            for slot in range(96)
        ),
        "g_res_rack": tuple(tuple(map(float, data.delta.g_res_plan_gpu[:, slot])) for slot in range(96)),
    }


def _context_base(
    repo: Path, data: V28R2FormulationData, cache: Path,
) -> tuple[Path, tuple[object, ...], Path, Path]:
    source = source_root(repo)
    if not (source / "opendss_assets/IEEE123Master.dss").is_file():
        raise FileNotFoundError(f"V28R2_IEEE123_SOURCE_ROOT:{source}")
    vintage = data.vintage
    reference = _legacy_reference(data)
    background = build_authority_background_binding(
        timestamps_fixed_aest=vintage["timestamps_96"],
        demand_mw_96=vintage["demand_mw_96"], rooftop_pv_mw_96=vintage["pv_mw_96"],
        paths=portable_background_paths(repo, source),
    )
    binding = build_full_grid_binding(
        assets=source / "opendss_assets", contract=source / "power_v70_p4f_contract",
        demand_mw_96=vintage["demand_mw_96"], rooftop_pv_mw_96=vintage["pv_mw_96"],
        aidc_plan_kw_96x12=reference["plan_kw_96x12"],
        pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        background_binding=background,
    )
    voltage_path = cache / "data" / f"D1_AC_ANCHOR_SENSITIVITY_{data.day}.npz"
    legacy = (reference, vintage, background, binding, voltage_path, None)
    current_path = cache / "data" / f"D1_AC_ANCHOR_CURRENT_SENSITIVITY_{data.day}.npz"
    return source, legacy, voltage_path, current_path


def build_electrical_context(
    repo: Path, data: V28R2FormulationData, cache: Path,
) -> ElectricalContext:
    source, legacy, voltage_path, current_path = _context_base(repo, data, cache)
    if not voltage_path.is_file() or not current_path.is_file():
        raise RuntimeError(f"V28R2_D1_ELECTRICAL_CACHE_MISSING:{data.day}")
    voltage = np.load(voltage_path, allow_pickle=False)
    current = np.load(current_path, allow_pickle=False)
    return ElectricalContext(legacy, voltage, current, source, voltage_path, current_path)


def with_realized_background(
    repo: Path, base: ElectricalContext, *, timestamps_96: object,
    demand_mw_96: object, pv_mw_96: object, aidc_plan_kw_96x12: object,
) -> ElectricalContext:
    """Rebind only physical background inputs after the Actual namespace opens."""

    source = base.source_root
    background = build_authority_background_binding(
        timestamps_fixed_aest=timestamps_96,
        demand_mw_96=demand_mw_96,
        rooftop_pv_mw_96=pv_mw_96,
        paths=portable_background_paths(repo, source),
    )
    binding = build_full_grid_binding(
        assets=source / "opendss_assets",
        contract=source / "power_v70_p4f_contract",
        demand_mw_96=demand_mw_96,
        rooftop_pv_mw_96=pv_mw_96,
        aidc_plan_kw_96x12=aidc_plan_kw_96x12,
        pcc_asset=repo / "dayahead/artifacts/v16_2/Generated_ThreePhase_PCC_v4.dss",
        background_binding=background,
    )
    reference, vintage, _old_background, _old_binding, cache, authority = base.legacy_context
    rebound = dict(reference)
    rebound["plan_kw_96x12"] = tuple(tuple(map(float, row)) for row in aidc_plan_kw_96x12)
    legacy = (rebound, vintage, background, binding, cache, authority)
    return ElectricalContext(
        legacy, base.voltage, base.current, source, base.voltage_path, base.current_path,
    )
