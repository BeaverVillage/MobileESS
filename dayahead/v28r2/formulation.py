"""Canonical V28R2 C1-aware formulation data materialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.authority import sha256_file
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.c1_affine import AffineCoefficient, endpoint_secant, load_c1
from dayahead.v28r2.lightgbm_channels import causal_optimizer_predictions
from dayahead.v28r2.reference_compute import (
    FullNodeDistributionAdapter, ReferenceSchedule, build_reference_schedule,
    case_rack_capacity_nodeh_per_slot,
)
from dayahead.v28r2.reference_delta import ReferenceDelta, build_reference_delta
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.source_labels import load_optimizer_labels


CASES = ("B0", "B1", "B2", "B3")
SOLVERS = ("MONOLITHIC", "STANDARD_BD", "CL_MC_BD")
DT_HOURS = 0.25
PF_AIDC = 0.95
PF_TAN = float(np.tan(np.arccos(PF_AIDC)))


def formulation_fingerprint(repo: Path) -> str:
    authority_root = repo / "dayahead/artifacts/v28r2_heavy_backend"
    authorities = {
        name: sha256_file(authority_root / name)
        for name in (
            "V28R2_WORKLOAD_ELIGIBILITY_BINDING.json",
            "V28R2_OPTIMIZER_CHANNEL_SCHEMA.json",
            "V28R2_REFERENCE_COMPUTE_SCHEDULE_CONTRACT.json",
            "V28R2_REFERENCE_DELTA_CONTRACT.json",
            "V28R2_C1_AFFINE_CONTRACT.json",
        )
    }
    return canonical_sha256({
        "authority_id": "V28R2_COMMON_C1_AWARE_FORMULATION_V1",
        "cases": CASES,
        "solvers": SOLVERS,
        "objective": "MIN_MAX_NORMALIZED_PHASE_LINE_CURRENT",
        "time": {"resolution_minutes": 15, "slots": 96},
        "workload": "strict_fullnode_fluid_service_with_reference_terminal_backlog_parity",
        "mess": "frozen_V16.3_four_unit_constraints_and_routes",
        "thermal": "one_C1_endpoint_secant_equality_per_site_slot",
        "reactive": "PCC_P_times_tan_acos_0.95",
        "grid": "V16.3_AC_anchored_phase_aware_LP_rows",
        "prohibited": ["PUE_PLAN", "beta_AIDC", "C2", "event_trigger", "local_repair", "rolling_MPC"],
        "authority_sha256": authorities,
    })


@dataclass(frozen=True)
class V28R2FormulationData:
    day: str
    cohort_ids: tuple[str, ...]
    rack_ids: tuple[str, ...]
    rack_aidc: tuple[str, ...]
    aidc_ids: tuple[str, ...]
    rack_gpu_capacity: np.ndarray
    arrivals_nodeh: np.ndarray
    reference: ReferenceSchedule
    delta: ReferenceDelta
    p_it_q90_kw: np.ndarray
    g_q90_gpu: np.ndarray
    c1_coefficients: tuple[AffineCoefficient, ...]
    vintage: Mapping[str, object]
    mess_records: Mapping[str, Mapping[str, object]]
    formulation_fingerprint: str
    input_sha256: str

    def validate(self) -> None:
        b, r, d = len(self.cohort_ids), len(self.rack_ids), len(self.aidc_ids)
        if (b, r, d) != (15, 48, 12):
            raise ValueError("V28R2_FORMULATION_FROZEN_AXES")
        if self.arrivals_nodeh.shape != (96, b) or self.rack_gpu_capacity.shape != (r,):
            raise ValueError("V28R2_FORMULATION_RESOURCE_SHAPE")
        if self.delta.p_res_plan_kw.shape != (r, 96) or self.delta.g_res_plan_gpu.shape != (r, 96):
            raise ValueError("V28R2_FORMULATION_DELTA_SHAPE")
        if len(self.c1_coefficients) != d * 96 or len(self.mess_records) != 4:
            raise ValueError("V28R2_FORMULATION_C1_OR_MESS_AXIS")
        if self.reference.cohort_ids != self.cohort_ids or self.reference.rack_ids != self.rack_ids:
            raise ValueError("V28R2_FORMULATION_REFERENCE_AXIS")
        if not self.delta.ready or any(not np.isfinite(value).all() for value in (
            self.arrivals_nodeh, self.rack_gpu_capacity, self.p_it_q90_kw, self.g_q90_gpu,
        )):
            raise ValueError("V28R2_FORMULATION_NONFINITE_OR_DELTA")
        if len(self.formulation_fingerprint) != 64 or len(self.input_sha256) != 64:
            raise ValueError("V28R2_FORMULATION_SHA")

    @property
    def c1_by_site_slot(self) -> dict[tuple[str, int], AffineCoefficient]:
        return {(row.aidc_id, row.slot): row for row in self.c1_coefficients}


def _mess_authority(payload: Mapping[str, object]) -> dict[str, dict[str, object]]:
    result = {}
    for record in payload["mess"]:
        mess_id = str(record["mess_id"])
        transit = tuple(
            index for index, (mode, available) in enumerate(zip(
                record["mode"], record["available"], strict=True,
            ))
            if mode != "CONNECTED" or not bool(available)
        )
        connected_locations = tuple(dict.fromkeys(
            location for location, mode, available in zip(
                record["location"], record["mode"], record["available"], strict=True,
            )
            if mode == "CONNECTED" and bool(available)
        ))
        if len(connected_locations) != 1 or not transit:
            raise RuntimeError(f"V28R2_MESS_ROUTE_AUTHORITY:{mess_id}")
        result[mess_id] = {
            "service_site": connected_locations[0],
            "transit_slots": list(transit),
            "safe_mobility_energy_kwh": float(sum(record["safe_travel_energy_kwh"])),
            "mode_96": list(record["mode"]),
            "location_96": list(record["location"]),
            "available_96": list(record["available"]),
            "travel_energy_kwh_96": list(record["safe_travel_energy_kwh"]),
            "initial_energy_kwh": float(record["initial_energy_kwh"]),
        }
    return result


def materialize_formulation_data(repo: Path, day: str) -> V28R2FormulationData:
    artifacts = repo / "dayahead/artifacts/v28r2_heavy_backend"
    models = artifacts / "V28R2_OPTIMIZER_CHANNEL_MODELS"
    labels = load_optimizer_labels(repo)
    p_quantiles, g_quantiles, w_quantiles = causal_optimizer_predictions(labels, day, models)
    p_authority = json.loads((artifacts / "V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json").read_text(encoding="utf-8"))
    p_q90 = p_quantiles[2] * float(p_authority["scale_binding"]["alpha_IT"])
    g_q90 = g_quantiles[2]

    adapter_payload = json.loads((artifacts / "V28R2_FULLNODE_DISTRIBUTION_ADAPTER.json").read_text(encoding="utf-8"))
    adapter = FullNodeDistributionAdapter(np.asarray(adapter_payload["probabilities"], dtype=float), labels.cohort_ids)
    arrivals = adapter.materialize(float(w_quantiles[1]), pd.Timestamp(day).dayofweek)
    rack_source = repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json"
    rack_payload = json.loads(rack_source.read_text(encoding="utf-8"))
    racks = tuple(rack_payload["racks"])
    rack_ids = tuple(str(row["rack_id"]) for row in racks)
    rack_aidc = tuple(str(row["aidc_id"]) for row in racks)
    aidc_ids = tuple(dict.fromkeys(rack_aidc))
    power_weights = dict(zip(rack_ids, map(float, rack_payload["power_weights"]), strict=True))
    gpu_weights = dict(zip(rack_ids, map(float, rack_payload["gpu_weights"]), strict=True))
    capacities_nodeh = case_rack_capacity_nodeh_per_slot(rack_ids, gpu_weights)
    rack_gpu_capacity = capacities_nodeh / DT_HOURS * 4.0
    mapped_p = np.asarray(rack_payload["power_weights"], dtype=float)[:, None] * p_q90
    mapped_g = np.asarray(rack_payload["gpu_weights"], dtype=float)[:, None] * g_q90
    reference = build_reference_schedule(
        arrivals, cohort_ids=labels.cohort_ids, rack_ids=rack_ids,
        rack_capacity_nodeh_per_slot=capacities_nodeh,
        rack_power_envelope_kw=mapped_p, rack_gpu_envelope_gpu=mapped_g,
    )
    delta = build_reference_delta(
        p_q90, g_q90, reference.p_f_ref_kw, reference.g_f_ref_gpu,
        rack_ids=rack_ids, power_weights=power_weights, gpu_weights=gpu_weights,
    )

    weather = pd.read_parquet(day_root(repo, day) / "gfs_d1_weather.parquet")
    if len(weather) != 96:
        raise RuntimeError("V28R2_FORMULATION_GFS_AXIS")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}
    max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    coefficients = []
    for aidc in aidc_ids:
        indices = [rack_index[row["rack_id"]] for row in racks if row["aidc_id"] == aidc]
        for slot in range(96):
            p_min = float(delta.p_res_plan_kw[indices, slot].sum())
            p_max = p_min + float(capacities_nodeh[indices].sum() / DT_HOURS * max_kappa)
            coefficients.append(endpoint_secant(
                aidc, slot, p_min, p_max, float(weather.iloc[slot]["t_wb_c"]),
                float(weather.iloc[slot]["rh_pct"]), parameters,
            ))

    source = day_root(repo, day)
    vintage = json.loads((source / "aemo_forecast.json").read_text(encoding="utf-8"))
    mobility = json.loads((source / "traffic_mobility.json").read_text(encoding="utf-8"))
    fingerprint = formulation_fingerprint(repo)
    input_sha = canonical_sha256({
        "day": day, "P_quantiles": p_quantiles.tolist(), "G_quantiles": g_quantiles.tolist(),
        "W_quantiles": w_quantiles.tolist(), "arrivals": arrivals.tolist(),
        "reference_sha256": canonical_sha256(json.loads(reference.canonical_bytes())),
        "delta_P": delta.p_res_plan_kw.tolist(), "delta_G": delta.g_res_plan_gpu.tolist(),
        "vintage": vintage,
        "source_day_sha256": json.loads((source / "source_day_manifest.json").read_text(encoding="utf-8"))["source_day_sha256"],
    })
    result = V28R2FormulationData(
        day, labels.cohort_ids, rack_ids, rack_aidc, aidc_ids, rack_gpu_capacity,
        arrivals, reference, delta, p_q90, g_q90, tuple(coefficients), vintage,
        _mess_authority(mobility), fingerprint, input_sha,
    )
    result.validate()
    return result
