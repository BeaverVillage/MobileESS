"""Fixed-schedule Actual replay with no optimizer import or call path."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.backend_contract import canonical_sha256, sha256_file
from dayahead.v28r2.c1_affine import exact_c1_pcc_kw, load_c1
from dayahead.v28r2.day_state import atomic_json
from dayahead.v28r2.mess_replay import MessReplay, replay_mess
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.source_cache import day_root
from dayahead.v28r2.workload_replay import ActualWorkload, WorkloadReplay, replay_workload


PF_TAN = math.tan(math.acos(0.95))


@dataclass(frozen=True)
class ActualReplay:
    day: str
    case: str
    workload: WorkloadReplay
    mess: MessReplay
    p_res_actual_kw: np.ndarray
    g_res_actual_gpu: np.ndarray
    rack_it_replay_kw: np.ndarray
    rack_gpu_replay: np.ndarray
    site_it_replay_kw: np.ndarray
    exact_pcc_p_kw: np.ndarray
    exact_pcc_q_kvar: np.ndarray
    trajectory: FrozenTrajectory
    source_sha256: Mapping[str, str]

    def validate(self) -> None:
        shapes = (
            (self.p_res_actual_kw, (96, 48)), (self.g_res_actual_gpu, (96, 48)),
            (self.rack_it_replay_kw, (96, 48)), (self.rack_gpu_replay, (96, 48)),
            (self.site_it_replay_kw, (96, 12)), (self.exact_pcc_p_kw, (96, 12)),
            (self.exact_pcc_q_kvar, (96, 12)),
        )
        if any(np.asarray(array).shape != shape or not np.isfinite(array).all() for array, shape in shapes):
            raise ValueError("V28R2_ACTUAL_REPLAY_AXIS_OR_FINITE")
        if np.any(self.p_res_actual_kw < -1e-9) or np.any(self.g_res_actual_gpu < -1e-9):
            raise RuntimeError("FAIL_AIDC_ACTUAL_DECOMPOSITION")
        self.trajectory.validate()

    @property
    def summary(self) -> dict[str, object]:
        self.validate()
        return {
            "artifact_id": "V28R2_ACTUAL_FIXED_SCHEDULE_REPLAY_RESULT_V1",
            "day": self.day, "case": self.case, "status": "PASS_REPLAY",
            "schedule_sha256": self.trajectory.source_schedule_sha256,
            "actual_reoptimization_calls": 0, "optimizer_import_count": 0,
            "command_time_shift_count": self.mess.command_time_shift_count,
            "substitute_vehicle_count": self.mess.substitute_vehicle_count,
            "hidden_shedding_nodeh": 0.0,
            "workload_mass_error_nodeh": self.workload.mass_error_nodeh,
            "terminal_backlog_nodeh": float(self.workload.backlog_nodeh[-1].sum()),
            "terminal_mess_energy_error_from_DA_target_kwh": float(np.max(np.abs(self.mess.energy_kwh[-1] - 760.0))),
            "negative_P_residual_min_kw": float(np.min(self.p_res_actual_kw)),
            "negative_G_residual_min_gpu": float(np.min(self.g_res_actual_gpu)),
            "exact_C1_evaluation_count": 96 * 12,
            "planning_affine_used_in_actual_physical_evaluation": False,
            "source_sha256": dict(self.source_sha256),
        }

    def write(self, output: Path) -> dict[str, object]:
        self.validate(); output.mkdir(parents=True, exist_ok=True)
        arrays_path = output / "ACTUAL_REPLAY_ARRAYS.npz"
        temporary = output / f"ACTUAL_REPLAY_ARRAYS.{os.getpid()}.tmp.npz"
        np.savez_compressed(
            temporary,
            workload_executed_nodeh=self.workload.executed_nodeh,
            workload_backlog_nodeh=self.workload.backlog_nodeh,
            workload_unexecuted_da_nodeh=self.workload.unexecuted_da_nodeh,
            mess_p_exec_kw=self.mess.p_exec_kw, mess_q_exec_kvar=self.mess.q_exec_kvar,
            mess_energy_kwh=self.mess.energy_kwh,
            mess_locations_96x4=self.mess.locations_96x4,
            mess_reasons_96x4=self.mess.reasons_96x4,
            p_res_actual_kw=self.p_res_actual_kw, g_res_actual_gpu=self.g_res_actual_gpu,
            rack_it_replay_kw=self.rack_it_replay_kw, rack_gpu_replay=self.rack_gpu_replay,
            site_it_replay_kw=self.site_it_replay_kw,
            exact_pcc_p_kw=self.exact_pcc_p_kw, exact_pcc_q_kvar=self.exact_pcc_q_kvar,
        )
        os.replace(temporary, arrays_path)
        summary_path = output / "ACTUAL_REPLAY_SUMMARY.json"
        atomic_json(summary_path, self.summary)
        manifest = {
            "artifact_id": "V28R2_ACTUAL_REPLAY_OUTPUT_MANIFEST_V1",
            "files": {
                path.name: {"sha256": sha256_file(path), "bytes": path.stat().st_size}
                for path in (arrays_path, summary_path)
            },
        }
        manifest["manifest_payload_sha256"] = canonical_sha256(manifest)
        atomic_json(output / "ACTUAL_REPLAY_OUTPUT_MANIFEST.json", manifest)
        return manifest


def _mapping(repo: Path) -> tuple[tuple[str, ...], tuple[str, ...], np.ndarray, np.ndarray]:
    payload = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    racks = tuple(payload["racks"])
    rack_ids = tuple(str(row["rack_id"]) for row in racks)
    rack_aidc = tuple(str(row["aidc_id"]) for row in racks)
    power = np.asarray(payload["power_weights"], dtype=float)
    gpu = np.asarray(payload["gpu_weights"], dtype=float)
    if len(rack_ids) != 48 or not np.isclose(power.sum(), 1.0) or not np.isclose(gpu.sum(), 1.0):
        raise RuntimeError("V28R2_ACTUAL_RACK_MAPPING")
    return rack_ids, rack_aidc, power, gpu


def _exact_site_power(
    repo: Path, day: str, rack_it_kw: np.ndarray, rack_aidc: Sequence[str],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    aidc_ids = tuple(dict.fromkeys(rack_aidc))
    site_it = np.asarray([
        [
            float(rack_it_kw[slot, [index for index, owner in enumerate(rack_aidc) if owner == aidc]].sum())
            for aidc in aidc_ids
        ]
        for slot in range(96)
    ])
    pcc, q = exact_pcc_from_site_it(repo, day, site_it)
    return site_it, pcc, q


def exact_pcc_from_site_it(
    repo: Path, day: str, site_it_kw: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    site_it = np.asarray(site_it_kw, dtype=float)
    if site_it.shape != (96, 12) or not np.isfinite(site_it).all() or np.any(site_it < 0):
        raise ValueError("V28R2_ACTUAL_SITE_IT_AXIS")
    weather = pd.read_parquet(day_root(repo, day) / "noaa_actual_weather.parquet")
    if len(weather) != 96:
        raise RuntimeError("V28R2_ACTUAL_NOAA_AXIS")
    parameters = load_c1(repo / "dayahead/artifacts/v24t_thermal_aware_aidc/V24T_C1_QUASISTATIC_MODEL.json")
    pcc = np.asarray([
        [
            float(exact_c1_pcc_kw(site_it[slot, aidc], float(weather.iloc[slot]["t_wb_c"]),
                                  float(weather.iloc[slot]["rh_pct"]), parameters))
            for aidc in range(12)
        ]
        for slot in range(96)
    ])
    return pcc, pcc * PF_TAN


def _residuals(
    actual: ActualWorkload, power_weights: np.ndarray, gpu_weights: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    p_total_residual = actual.total_it_kw - actual.flexible_natural_it_kw
    g_total_residual = actual.total_h100_gpu - actual.flexible_natural_gpu
    if p_total_residual.min() < -1e-9 or g_total_residual.min() < -1e-9:
        raise RuntimeError("FAIL_AIDC_ACTUAL_DECOMPOSITION")
    return p_total_residual[:, None] * power_weights[None, :], g_total_residual[:, None] * gpu_weights[None, :]


def replay_actual_case(
    repo: Path, day: str, schedule_payload: Mapping[str, object],
    actual: ActualWorkload, mobility_records: Sequence[Mapping[str, object]],
    initial_backlog_nodeh: np.ndarray | None = None,
) -> ActualReplay:
    """Execute one B0-B3 schedule at its original slots without optimization."""

    source_trajectory = FrozenTrajectory.from_schedule_payload(
        schedule_payload, day=day, namespace="ACTUAL",
    )
    rack_ids, rack_aidc, power_weights, gpu_weights = _mapping(repo)
    p_res, g_res = _residuals(actual, power_weights, gpu_weights)
    da = np.asarray(schedule_payload["workload_service_tensor"], dtype=float)
    rack_gpu_capacity = CASE_CAPACITY_GPU * gpu_weights
    capacity_nodeh = np.maximum(0.0, (rack_gpu_capacity[None, :] - g_res) * .25 / 4.0)
    workload = replay_workload(da, actual.arrivals_nodeh, capacity_nodeh, initial_backlog_nodeh)
    kappa = np.asarray([
        KAPPA_KW_PER_ACTIVE_H100_NODE[int(cohort[1:3])]
        for cohort in COHORT_IDS
    ])
    flexible_p = np.einsum("c,crh->hr", kappa, workload.executed_nodeh) / .25
    flexible_g = workload.executed_nodeh.sum(axis=0).T / .25 * 4.0
    rack_it = p_res + flexible_p; rack_gpu = g_res + flexible_g
    site_it, pcc_p, pcc_q = _exact_site_power(repo, day, rack_it, rack_aidc)
    mess = replay_mess(
        np.asarray(schedule_payload["mess_p_kw"], dtype=float),
        np.asarray(schedule_payload["mess_q_kvar"], dtype=float), mobility_records,
    )
    trajectory = FrozenTrajectory(
        day, "ACTUAL", str(schedule_payload["case"]), pcc_p, pcc_q,
        mess.p_exec_kw, mess.q_exec_kvar, mess.mess_ids,
        mess.locations_96x4, source_trajectory.source_schedule_sha256,
    )
    result = ActualReplay(
        day, str(schedule_payload["case"]), workload, mess, p_res, g_res,
        rack_it, rack_gpu, site_it, pcc_p, pcc_q, trajectory,
        {
            **actual.source_sha256,
            "noaa_actual": sha256_file(day_root(repo, day) / "noaa_actual_weather.parquet"),
            "traffic_mobility": sha256_file(day_root(repo, day) / "traffic_mobility.json"),
        },
    )
    result.validate()
    return result


def build_natural_actual(
    repo: Path, day: str, actual: ActualWorkload,
    mobility_records: Sequence[Mapping[str, object]], source_sha256: str,
) -> ActualReplay:
    """Build R0 natural realized physical trajectory (not an optimization policy)."""

    _rack_ids, rack_aidc, power_weights, gpu_weights = _mapping(repo)
    p_res, g_res = _residuals(actual, power_weights, gpu_weights)
    rack_it = actual.total_it_kw[:, None] * power_weights[None, :]
    rack_gpu = actual.total_h100_gpu[:, None] * gpu_weights[None, :]
    site_it, pcc_p, pcc_q = _exact_site_power(repo, day, rack_it, rack_aidc)
    zero = np.zeros((96, 4))
    mess = replay_mess(zero, zero, mobility_records)
    empty_workload = WorkloadReplay(
        np.zeros((15, 48, 96)),
        np.vstack((np.zeros((1, 15)), np.cumsum(actual.arrivals_nodeh, axis=0))),
        np.zeros((15, 48, 96)), 0.0, 0.0,
    )
    trajectory = FrozenTrajectory(
        day, "ACTUAL", "R0", pcc_p, pcc_q, zero, zero, mess.mess_ids,
        mess.locations_96x4, source_sha256,
    )
    result = ActualReplay(
        day, "R0", empty_workload, mess, p_res, g_res, rack_it, rack_gpu,
        site_it, pcc_p, pcc_q, trajectory, actual.source_sha256,
    )
    result.validate()
    return result
