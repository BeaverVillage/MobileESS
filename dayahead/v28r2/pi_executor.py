"""Realized-input Perfect-Information B3 execution and exact-C1 trajectory."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence
import copy

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.actual_replay import exact_pcc_from_site_it
from dayahead.v28r2.backend_contract import canonical_sha256, sha256_file
from dayahead.v28r2.benders_authority import solve_benders
from dayahead.v28r2.c1_affine import endpoint_secant, load_c1
from dayahead.v28r2.day_state import atomic_json
from dayahead.v28r2.electrical_cache_prepare import prepare_electrical_context
from dayahead.v28r2.formulation import DT_HOURS, V28R2FormulationData, _mess_authority, formulation_fingerprint
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.reference_compute import build_reference_schedule, case_rack_capacity_nodeh_per_slot
from dayahead.v28r2.reference_delta import build_reference_delta
from dayahead.v28r2.solver_payload import SolverPayload
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.workload_replay import ActualWorkload
from dayahead.v29.mess_availability import normalize_mess_record


def _axes(repo: Path) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], np.ndarray, np.ndarray]:
    payload = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    racks = tuple(payload["racks"])
    rack_ids = tuple(str(row["rack_id"]) for row in racks)
    rack_aidc = tuple(str(row["aidc_id"]) for row in racks)
    return (
        rack_ids, rack_aidc, tuple(dict.fromkeys(rack_aidc)),
        np.asarray(payload["power_weights"], dtype=float),
        np.asarray(payload["gpu_weights"], dtype=float),
    )


def materialize_pi_formulation_data(
    repo: Path, day: str, actual: ActualWorkload,
) -> V28R2FormulationData:
    """Apply the common formulation procedure to realized PI inputs."""

    rack_ids, rack_aidc, aidc_ids, power_weights, gpu_weights = _axes(repo)
    power_map = dict(zip(rack_ids, map(float, power_weights), strict=True))
    gpu_map = dict(zip(rack_ids, map(float, gpu_weights), strict=True))
    capacity = case_rack_capacity_nodeh_per_slot(rack_ids, gpu_map)
    reference = build_reference_schedule(
        actual.arrivals_nodeh, cohort_ids=actual.cohort_ids, rack_ids=rack_ids,
        rack_capacity_nodeh_per_slot=capacity,
        rack_power_envelope_kw=power_weights[:, None] * actual.total_it_kw[None, :],
        rack_gpu_envelope_gpu=gpu_weights[:, None] * actual.total_h100_gpu[None, :],
    )
    delta = build_reference_delta(
        actual.total_it_kw, actual.total_h100_gpu,
        reference.p_f_ref_kw, reference.g_f_ref_gpu,
        rack_ids=rack_ids, power_weights=power_map, gpu_weights=gpu_map,
    )
    weather = pd.read_parquet(day_root(repo, day) / "noaa_actual_weather.parquet")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}
    max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    coefficients = []
    for aidc in aidc_ids:
        indices = [rack_index[rack] for rack, owner in zip(rack_ids, rack_aidc, strict=True) if owner == aidc]
        for slot in range(96):
            p_min = float(delta.p_res_plan_kw[indices, slot].sum())
            p_max = p_min + float(capacity[indices].sum() / DT_HOURS * max_kappa)
            coefficients.append(endpoint_secant(
                aidc, slot, p_min, p_max, float(weather.iloc[slot]["t_wb_c"]),
                float(weather.iloc[slot]["rh_pct"]), parameters,
            ))
    aemo = pd.read_parquet(day_root(repo, day) / "aemo_actual.parquet")
    vintage = {
        "authority_id": "V28R2_PI_REALIZED_AEMO_INPUT_V1",
        "timestamps_96": [str(value) for value in aemo["ts_fixed_aest_end"]],
        "demand_mw_96": aemo["demand_mw"].astype(float).tolist(),
        "pv_mw_96": aemo["rooftop_pv_mw"].astype(float).tolist(),
    }
    mobility = json.loads((day_root(repo, day) / "traffic_mobility.json").read_text(encoding="utf-8"))
    pi_mobility = copy.deepcopy(mobility)
    pi_mobility["mess"] = [normalize_mess_record(record) for record in pi_mobility["mess"]]
    fingerprint = formulation_fingerprint(repo)
    input_sha = canonical_sha256({
        "namespace": "PERFECT_INFORMATION", "day": day,
        "arrivals": actual.arrivals_nodeh.tolist(),
        "P_actual": actual.total_it_kw.tolist(), "G_actual": actual.total_h100_gpu.tolist(),
        "NOAA_actual_sha256": sha256_file(day_root(repo, day) / "noaa_actual_weather.parquet"),
        "AEMO_actual_sha256": sha256_file(day_root(repo, day) / "aemo_actual.parquet"),
        "mobility_sha256": sha256_file(day_root(repo, day) / "traffic_mobility.json"),
        "source_sha256": actual.source_sha256,
    })
    result = V28R2FormulationData(
        day, actual.cohort_ids, rack_ids, rack_aidc, aidc_ids,
        capacity / DT_HOURS * 4.0, actual.arrivals_nodeh, reference, delta,
        actual.total_it_kw, actual.total_h100_gpu, tuple(coefficients), vintage,
        _mess_authority(pi_mobility), fingerprint, input_sha,
    )
    result.validate()
    return result


@dataclass(frozen=True)
class PIExecution:
    data: V28R2FormulationData
    payload: SolverPayload
    trajectory: FrozenTrajectory
    context: object


def execute_pi(
    *, repo: Path, day: str, actual: ActualWorkload,
    electrical_cache: Path, output: Path,
) -> PIExecution:
    """Run the real CL-MC-BD PI solve; this function is never imported by DA."""

    data = materialize_pi_formulation_data(repo, day, actual)
    context = prepare_electrical_context(repo, data, electrical_cache)
    payload = solve_benders(
        data=data, context=context.legacy_context, voltage=context.voltage,
        current=context.current, method="CL_MC_BD", raw_dir=output / "benders_raw",
    )
    pcc_p, pcc_q = exact_pcc_from_site_it(
        repo, day, np.asarray(payload.site_it_power_kw, dtype=float),
    )
    mobility = json.loads((day_root(repo, day) / "traffic_mobility.json").read_text(encoding="utf-8"))
    records = tuple(sorted(mobility["mess"], key=lambda row: str(row["mess_id"])))
    locations = np.asarray([list(map(str, row["location"])) for row in records], dtype=str).T
    trajectory = FrozenTrajectory(
        day, "PERFECT_INFORMATION", "B3", pcc_p, pcc_q,
        np.asarray(payload.mess_p_kw, dtype=float),
        np.asarray(payload.mess_q_kvar, dtype=float),
        tuple(str(row["mess_id"]) for row in records), locations,
        payload.schedule_sha256,
    )
    trajectory.validate()
    output.mkdir(parents=True, exist_ok=True)
    payload.write(output / "PI_B3_SOLVER_PAYLOAD.json")
    atomic_json(output / "PI_EXECUTION_SUMMARY.json", {
        "artifact_id": "V28R2_PI_EXECUTION_RESULT_V1",
        "status": payload.status, "hard_feasible": payload.hard_feasible,
        "solver": payload.solver, "objective": payload.objective,
        "LB": payload.lower_bound, "UB": payload.upper_bound, "gap": payload.gap,
        "iterations": payload.iterations, "optimality_cuts": payload.optimality_cuts,
        "feasibility_cuts": payload.feasibility_cuts,
        "formulation_fingerprint": payload.formulation_fingerprint,
        "input_sha256": payload.input_sha256,
        "actual_inputs": ["workload", "NOAA", "AEMO_demand", "AEMO_PV", "mobility_travel"],
        "exact_C1_physical_trajectory_ready": True,
        "DA_namespace_reads": 0,
    })
    return PIExecution(data, payload, trajectory, context)
