"""V29R2 common formulation with calibrated carry-in scenarios and V4 reference."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.c1_affine import AffineCoefficient, endpoint_secant, load_c1
from dayahead.v28r2.formulation import DT_HOURS, materialize_formulation_data
from dayahead.v28r2.reference_compute import case_rack_capacity_nodeh_per_slot
from dayahead.v28r2.reference_delta import ReferenceDelta, build_reference_delta
from dayahead.v28r2.source_cache import day_root
from dayahead.v29r1.authority import Q_SCENARIOS
from dayahead.v29r1.source_resume import sha256_file

from .anchor_forensic import OUT_REL
from .bridge_v2 import predict_bridge_day
from .reference_v4 import ReferenceScheduleV4, build_reference_v4


@dataclass(frozen=True)
class V29R2FormulationData:
    day: str
    scenario: str
    cohort_ids: tuple[str, ...]
    rack_ids: tuple[str, ...]
    rack_aidc: tuple[str, ...]
    aidc_ids: tuple[str, ...]
    rack_gpu_capacity: np.ndarray
    initial_backlog_nodeh: np.ndarray
    controllable_carryin_nodeh: np.ndarray
    arrivals_nodeh: np.ndarray
    reference: ReferenceScheduleV4
    delta: ReferenceDelta
    p_it_q90_kw: np.ndarray
    g_q90_gpu: np.ndarray
    c1_coefficients: tuple[AffineCoefficient, ...]
    vintage: Mapping[str, object]
    mess_records: Mapping[str, Mapping[str, object]]
    formulation_fingerprint: str
    input_sha256: str

    @property
    def c1_by_site_slot(self) -> dict[tuple[str, int], AffineCoefficient]:
        return {(row.aidc_id, row.slot): row for row in self.c1_coefficients}

    def validate(self) -> None:
        if self.scenario not in Q_SCENARIOS:
            raise ValueError("V29R2_SCENARIO_AXIS")
        if (len(self.cohort_ids), len(self.rack_ids), len(self.aidc_ids)) != (15, 48, 12):
            raise ValueError("V29R2_FORMULATION_FROZEN_AXES")
        if self.initial_backlog_nodeh.shape != (15,) or self.controllable_carryin_nodeh.shape != (15,):
            raise ValueError("V29R2_FORMULATION_CARRYIN_AXIS")
        if self.arrivals_nodeh.shape != (96, 15) or self.rack_gpu_capacity.shape != (48,):
            raise ValueError("V29R2_FORMULATION_RESOURCE_AXIS")
        if not (
            np.all(self.initial_backlog_nodeh >= 0)
            and np.all(self.controllable_carryin_nodeh >= 0)
            and np.all(self.controllable_carryin_nodeh <= self.initial_backlog_nodeh + 1e-12)
        ):
            raise ValueError("V29R2_FORMULATION_CARRYIN_MASS")
        self.reference.validate()
        if not np.array_equal(self.reference.initial_backlog_nodeh, self.initial_backlog_nodeh):
            raise ValueError("V29R2_FORMULATION_REFERENCE_INITIAL_IDENTITY")
        if not self.delta.ready or np.min(self.delta.p_res_plan_kw) < 0 or np.min(self.delta.g_res_plan_gpu) < 0:
            raise ValueError("V29R2_FORMULATION_RESIDUAL")
        if len(self.c1_coefficients) != 12 * 96 or len(self.formulation_fingerprint) != 64 or len(self.input_sha256) != 64:
            raise ValueError("V29R2_FORMULATION_CONTRACT")


def formulation_fingerprint(repo: Path) -> str:
    out = repo / OUT_REL
    names = (
        "V29R2_TRUST_CERT_DECISION.json", "V29R2_EXEC_SERVICE_MODEL_AUTHORITY.json",
        "V29R2_BRIDGE_V2_CONTRACT.json", "V29R2_REFERENCE_V4_CONTRACT.json",
        "V29R2_MESS_NOREGRET_CONTRACT.json",
    )
    return canonical_sha256({
        "authority_id": "V29R2_COMMON_FORMULATION_V1",
        "objective": "MIN_MAX_NORMALIZED_PHASE_LINE_CURRENT",
        "rho_AIDC": 1.0, "rho_MESS": .10,
        "scenarios": list(Q_SCENARIOS), "reference": "REFERENCE_COMPUTE_SCHEDULE_V4",
        "controllable_carryin": "H0_LOW only", "PARTIAL_shared_controllable": False,
        "running_job_preemption": False, "synthetic_deadline": False,
        "connection_delay_slots": 1,
        "authorities": {name: sha256_file(out / name) for name in names},
    })


def bridge_vectors(
    cohort_ids: Sequence[str], rows: Sequence[Mapping[str, object]],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    index = {name: position for position, name in enumerate(cohort_ids)}
    req = np.zeros(len(cohort_ids)); nom = np.zeros(len(cohort_ids)); low = np.zeros(len(cohort_ids))
    for row in rows:
        position = index[str(row["cohort_id"])]
        req[position] = float(row["H0_REQ"])
        nom[position] = float(row["H0_NOM"])
        low[position] = float(row["H0_LOW"])
    return req, nom, low


def materialize_formulation_data_v29r2(
    repo: Path, day: str, scenario: str, *, bridge_rows: Sequence[Mapping[str, object]] | None = None,
) -> V29R2FormulationData:
    if scenario not in Q_SCENARIOS:
        raise ValueError(f"V29R2_UNKNOWN_SCENARIO:{scenario}")
    base = materialize_formulation_data(repo, day)
    rows = list(bridge_rows if bridge_rows is not None else predict_bridge_day(repo, day))
    h0_req, h0_nom, h0_low = bridge_vectors(base.cohort_ids, rows)
    if scenario == "S_NOM":
        initial, controllable = h0_nom, h0_low
    elif scenario == "S_LOW":
        initial, controllable = h0_low, h0_low
    else:
        initial, controllable = np.zeros_like(h0_nom), np.zeros_like(h0_low)
    reference, delta = build_reference_v4(
        repo, day, h0_req=h0_req, h0_nom=initial, h0_low=controllable,
    )
    mapping = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    gpu_weights = dict(zip(base.rack_ids, map(float, mapping["gpu_weights"]), strict=True))
    capacities = case_rack_capacity_nodeh_per_slot(base.rack_ids, gpu_weights)
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
            coefficients.append(endpoint_secant(
                aidc, slot, p_min, p_max,
                float(weather.iloc[slot]["t_wb_c"]), float(weather.iloc[slot]["rh_pct"]), parameters,
            ))
    fingerprint = formulation_fingerprint(repo)
    input_sha = canonical_sha256({
        "day": day, "scenario": scenario, "base_input": base.input_sha256,
        "H0_REQ": h0_req.tolist(), "H0_NOM": h0_nom.tolist(), "H0_LOW": h0_low.tolist(),
        "scenario_initial": initial.tolist(), "reference_V4": hashlib_sha(reference.canonical_bytes()),
        "delta_P": delta.p_res_plan_kw.tolist(), "delta_G": delta.g_res_plan_gpu.tolist(),
    })
    result = V29R2FormulationData(
        day, scenario, base.cohort_ids, base.rack_ids, base.rack_aidc, base.aidc_ids,
        base.rack_gpu_capacity, initial, controllable, base.arrivals_nodeh,
        reference, delta, base.p_it_q90_kw, base.g_q90_gpu,
        tuple(coefficients), base.vintage, base.mess_records, fingerprint, input_sha,
    )
    result.validate()
    return result


def hashlib_sha(content: bytes) -> str:
    import hashlib
    return hashlib.sha256(content).hexdigest()
