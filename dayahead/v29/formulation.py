"""V29 common C1-aware formulation with causal D-day carry-in."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.backend_contract import canonical_sha256, sha256_file
from dayahead.v28r2.c1_affine import AffineCoefficient, endpoint_secant, load_c1
from dayahead.v28r2.formulation import DT_HOURS, materialize_formulation_data
from dayahead.v28r2.reference_compute import case_rack_capacity_nodeh_per_slot
from dayahead.v28r2.reference_delta import ReferenceDelta, build_reference_delta
from dayahead.v28r2.source_cache import day_root
from .authority import RHO_AIDC, require_carryin_authority
from .carryin import carryin_by_cohort
from .reference_compute_v3 import ReferenceScheduleV3, build_reference_schedule_v3


@dataclass(frozen=True)
class V29FormulationData:
    day: str
    cohort_ids: tuple[str, ...]
    rack_ids: tuple[str, ...]
    rack_aidc: tuple[str, ...]
    aidc_ids: tuple[str, ...]
    rack_gpu_capacity: np.ndarray
    initial_backlog_nodeh: np.ndarray
    arrivals_nodeh: np.ndarray
    reference: ReferenceScheduleV3
    delta: ReferenceDelta
    p_it_q90_kw: np.ndarray
    g_q90_gpu: np.ndarray
    c1_coefficients: tuple[AffineCoefficient, ...]
    vintage: Mapping[str, object]
    mess_records: Mapping[str, Mapping[str, object]]
    formulation_fingerprint: str
    input_sha256: str

    def validate(self) -> None:
        if (len(self.cohort_ids), len(self.rack_ids), len(self.aidc_ids)) != (15, 48, 12):
            raise ValueError("V29_FORMULATION_FROZEN_AXES")
        if self.initial_backlog_nodeh.shape != (15,) or self.arrivals_nodeh.shape != (96, 15):
            raise ValueError("V29_FORMULATION_WORKLOAD_AXIS")
        if np.any(self.initial_backlog_nodeh < 0) or not np.isfinite(self.initial_backlog_nodeh).all():
            raise ValueError("V29_FORMULATION_CARRYIN_INVALID")
        self.reference.validate()
        if not np.array_equal(self.reference.initial_backlog_nodeh, self.initial_backlog_nodeh):
            raise ValueError("V29_FORMULATION_REFERENCE_CARRYIN_IDENTITY")
        if not self.delta.ready or np.min(self.delta.p_res_plan_kw) < -1e-9 or np.min(self.delta.g_res_plan_gpu) < -1e-9:
            raise ValueError("FAIL_REFERENCE_DELTA")
        if len(self.c1_coefficients) != 12 * 96 or len(self.formulation_fingerprint) != 64 or len(self.input_sha256) != 64:
            raise ValueError("V29_FORMULATION_CONTRACT")

    @property
    def c1_by_site_slot(self) -> dict[tuple[str, int], AffineCoefficient]:
        return {(row.aidc_id, row.slot): row for row in self.c1_coefficients}


def formulation_fingerprint(repo: Path) -> str:
    root = repo / "dayahead/artifacts"
    files = {
        "carryin_authority": root / "v29_grid_responsive_aidc/V29_CARRYIN_AUTHORITY_DECISION.json",
        "queue_bridge": root / "v29_grid_responsive_aidc/V29_PRE_DAY_QUEUE_BRIDGE_CONTRACT.json",
        "source_namespace": root / "v29_grid_responsive_aidc/V29_SOURCE_NAMESPACE_CONTRACT.json",
        "workload_eligibility": root / "v28r2_heavy_backend/V28R2_WORKLOAD_ELIGIBILITY_BINDING.json",
        "P_authority": root / "v28r2_heavy_backend/V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json",
        "G_authority": root / "v28r2_heavy_backend/V28R2_FINAL_G_REF_LIGHTGBM_AUTHORITY.json",
        "W_authority": root / "v28r2_heavy_backend/V28R2_FINAL_W_FULLNODE_LIGHTGBM_AUTHORITY.json",
        "C1": root / "v28r2_heavy_backend/V28R2_C1_AFFINE_CONTRACT.json",
    }
    return canonical_sha256({
        "authority_id": "V29_COMMON_FORMULATION_V1",
        "time": {"cutoff": "D-1 18:00 fixed AEST", "slots": 96, "minutes": 15, "one_shot": True, "daily_independent": True},
        "objective": "MIN_MAX_NORMALIZED_PHASE_LINE_CURRENT",
        "cases": ["B0", "B1", "B2", "B3"], "rho_AIDC": RHO_AIDC,
        "initial_backlog": "source-backed PRE_DAY_QUEUE_BRIDGE_V1 carry-in",
        "reference": "REFERENCE_COMPUTE_SCHEDULE_V3",
        "terminal": "reference_V3_terminal_backlog_parity",
        "eligibility": "strict full-node only; PARTIAL/shared noncontrollable",
        "running_job_preemption": False, "synthetic_deadlines": False,
        "critical_reserve_constraint": False, "secondary_objective": False,
        "connection_delay_slots": 1,
        "authorities": {name: sha256_file(path) for name, path in sorted(files.items())},
    })


def materialize_formulation_data_v29(repo: Path, day: str) -> V29FormulationData:
    require_carryin_authority(repo)
    base = materialize_formulation_data(repo, day)
    initial = carryin_by_cohort(repo, day)
    mapping = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    power_weights = np.asarray(mapping["power_weights"], dtype=float)
    gpu_weights = np.asarray(mapping["gpu_weights"], dtype=float)
    capacities = case_rack_capacity_nodeh_per_slot(base.rack_ids, dict(zip(base.rack_ids, map(float, gpu_weights), strict=True)))
    reference = build_reference_schedule_v3(
        base.arrivals_nodeh, initial, cohort_ids=base.cohort_ids, rack_ids=base.rack_ids,
        rack_capacity_nodeh_per_slot=capacities,
        rack_power_envelope_kw=power_weights[:, None] * base.p_it_q90_kw[None, :],
        rack_gpu_envelope_gpu=gpu_weights[:, None] * base.g_q90_gpu[None, :],
    )
    delta = build_reference_delta(
        base.p_it_q90_kw, base.g_q90_gpu, reference.p_f_ref_kw, reference.g_f_ref_gpu,
        rack_ids=base.rack_ids,
        power_weights=dict(zip(base.rack_ids, map(float, power_weights), strict=True)),
        gpu_weights=dict(zip(base.rack_ids, map(float, gpu_weights), strict=True)),
    )
    weather = pd.read_parquet(day_root(repo, day) / "gfs_d1_weather.parquet")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    rack_index = {rack: index for index, rack in enumerate(base.rack_ids)}
    max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    coefficients = []
    for aidc in base.aidc_ids:
        indices = [rack_index[rack] for rack, owner in zip(base.rack_ids, base.rack_aidc, strict=True) if owner == aidc]
        for slot in range(96):
            p_min = float(delta.p_res_plan_kw[indices, slot].sum())
            p_max = p_min + float(capacities[indices].sum() / DT_HOURS * max_kappa)
            coefficients.append(endpoint_secant(aidc, slot, p_min, p_max, float(weather.iloc[slot]["t_wb_c"]), float(weather.iloc[slot]["rh_pct"]), parameters))
    fingerprint = formulation_fingerprint(repo)
    input_sha = canonical_sha256({
        "day": day, "base_input_sha256": base.input_sha256,
        "carryin_nodeh": initial.tolist(),
        "reference_V3_sha256": canonical_sha256(json.loads(reference.canonical_bytes())),
        "delta_P": delta.p_res_plan_kw.tolist(), "delta_G": delta.g_res_plan_gpu.tolist(),
        "prefreeze_namespaces": ["COMMON_STATIC", "DAYAHEAD_FORECAST"],
    })
    result = V29FormulationData(
        day, base.cohort_ids, base.rack_ids, base.rack_aidc, base.aidc_ids,
        base.rack_gpu_capacity, initial, base.arrivals_nodeh, reference, delta,
        base.p_it_q90_kw, base.g_q90_gpu, tuple(coefficients), base.vintage,
        base.mess_records, fingerprint, input_sha,
    )
    result.validate(); return result
