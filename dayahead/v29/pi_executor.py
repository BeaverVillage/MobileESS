"""Ex-post V29 PI B3 with the same causal carry-in state definition."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.actual_replay import exact_pcc_from_site_it
from dayahead.v28r2.backend_contract import canonical_sha256, sha256_file
from dayahead.v28r2.benders_authority import solve_benders
from dayahead.v28r2.c1_affine import endpoint_secant, load_c1
from dayahead.v28r2.electrical_cache_prepare import prepare_electrical_context
from dayahead.v28r2.formulation import DT_HOURS, _mess_authority
from dayahead.v28r2.reference_compute import case_rack_capacity_nodeh_per_slot
from dayahead.v28r2.reference_delta import build_reference_delta
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.workload_replay import ActualWorkload
from .carryin import carryin_by_cohort
from .formulation import V29FormulationData, formulation_fingerprint
from .mess_availability import normalize_mess_record
from .reference_compute_v3 import build_reference_schedule_v3


def materialize_pi_formulation_data_v29(repo: Path, day: str, actual: ActualWorkload) -> V29FormulationData:
    mapping = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    racks = tuple(mapping["racks"]); rack_ids = tuple(str(row["rack_id"]) for row in racks)
    rack_aidc = tuple(str(row["aidc_id"]) for row in racks); aidc_ids = tuple(dict.fromkeys(rack_aidc))
    power_weights = np.asarray(mapping["power_weights"], dtype=float); gpu_weights = np.asarray(mapping["gpu_weights"], dtype=float)
    capacity = case_rack_capacity_nodeh_per_slot(rack_ids, dict(zip(rack_ids, map(float, gpu_weights), strict=True)))
    initial = carryin_by_cohort(repo, day)
    reference = build_reference_schedule_v3(
        actual.arrivals_nodeh, initial, cohort_ids=actual.cohort_ids, rack_ids=rack_ids,
        rack_capacity_nodeh_per_slot=capacity,
        rack_power_envelope_kw=power_weights[:, None] * actual.total_it_kw[None, :],
        rack_gpu_envelope_gpu=gpu_weights[:, None] * actual.total_h100_gpu[None, :],
    )
    delta = build_reference_delta(
        actual.total_it_kw, actual.total_h100_gpu, reference.p_f_ref_kw, reference.g_f_ref_gpu,
        rack_ids=rack_ids, power_weights=dict(zip(rack_ids, map(float, power_weights), strict=True)),
        gpu_weights=dict(zip(rack_ids, map(float, gpu_weights), strict=True)),
    )
    weather = pd.read_parquet(day_root(repo, day) / "noaa_actual_weather.parquet")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    rack_index = {rack: index for index, rack in enumerate(rack_ids)}; max_kappa = max(KAPPA_KW_PER_ACTIVE_H100_NODE.values())
    coefficients = []
    for aidc in aidc_ids:
        indices = [rack_index[rack] for rack, owner in zip(rack_ids, rack_aidc, strict=True) if owner == aidc]
        for slot in range(96):
            p_min = float(delta.p_res_plan_kw[indices, slot].sum())
            p_max = p_min + float(capacity[indices].sum() / DT_HOURS * max_kappa)
            coefficients.append(endpoint_secant(aidc, slot, p_min, p_max, float(weather.iloc[slot]["t_wb_c"]), float(weather.iloc[slot]["rh_pct"]), parameters))
    aemo = pd.read_parquet(day_root(repo, day) / "aemo_actual.parquet")
    vintage = {"authority_id": "V29_PI_REALIZED_AEMO_INPUT_V1", "timestamps_96": [str(value) for value in aemo["ts_fixed_aest_end"]], "demand_mw_96": aemo["demand_mw"].astype(float).tolist(), "pv_mw_96": aemo["rooftop_pv_mw"].astype(float).tolist()}
    mobility = json.loads((day_root(repo, day) / "traffic_mobility.json").read_text(encoding="utf-8"))
    mobility["mess"] = [normalize_mess_record(record) for record in mobility["mess"]]
    fingerprint = formulation_fingerprint(repo)
    input_sha = canonical_sha256({
        "namespace": "PERFECT_INFORMATION", "day": day,
        "carryin": initial.tolist(), "arrivals": actual.arrivals_nodeh.tolist(),
        "P_actual": actual.total_it_kw.tolist(), "G_actual": actual.total_h100_gpu.tolist(),
        "NOAA_actual_sha256": sha256_file(day_root(repo, day) / "noaa_actual_weather.parquet"),
        "AEMO_actual_sha256": sha256_file(day_root(repo, day) / "aemo_actual.parquet"),
        "source_sha256": actual.source_sha256,
    })
    result = V29FormulationData(
        day, actual.cohort_ids, rack_ids, rack_aidc, aidc_ids, capacity / DT_HOURS * 4.0,
        initial, actual.arrivals_nodeh, reference, delta, actual.total_it_kw, actual.total_h100_gpu,
        tuple(coefficients), vintage, _mess_authority(mobility), fingerprint, input_sha,
    )
    result.validate(); return result


@dataclass(frozen=True)
class PIExecutionV29:
    data: V29FormulationData
    payload: object
    trajectory: FrozenTrajectory
    context: object


def execute_pi_v29(repo: Path, day: str, actual: ActualWorkload, electrical_cache: Path, output: Path) -> PIExecutionV29:
    data = materialize_pi_formulation_data_v29(repo, day, actual)
    context = prepare_electrical_context(repo, data, electrical_cache)
    payload = solve_benders(data=data, context=context.legacy_context, voltage=context.voltage, current=context.current, method="CL_MC_BD", raw_dir=output / "benders_raw", tolerance=1e-4)
    pcc_p, pcc_q = exact_pcc_from_site_it(repo, day, np.asarray(payload.site_it_power_kw, dtype=float))
    records = tuple(sorted(data.mess_records.items()))
    locations = np.asarray([list(map(str, record[1]["location_96"])) for record in records], dtype=str).T
    trajectory = FrozenTrajectory(day, "PERFECT_INFORMATION", "B3", pcc_p, pcc_q, np.asarray(payload.mess_p_kw), np.asarray(payload.mess_q_kvar), tuple(record[0] for record in records), locations, payload.schedule_sha256)
    trajectory.validate(); output.mkdir(parents=True, exist_ok=True); payload.write(output / "PI_B3_SOLVER_PAYLOAD.json")
    return PIExecutionV29(data, payload, trajectory, context)
