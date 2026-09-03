"""Production V35 day execution with immutable, reload-verified storage.

The module deliberately keeps one day in one process.  Route/forecast and
electrical coefficient authorities are built once per day and reused by the
four official cases; MESS subproblems remain deterministic and sequential.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, datetime, timezone
import csv
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time
from typing import Mapping, Sequence

import numpy as np

from dayahead.mess_physics import CAPACITY_KWH, E_INITIAL_KWH
from dayahead.v28r2.electrical_cache_prepare import prepare_electrical_context
from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2.electrical_subproblem import (
    anchored_polygon_loading,
    is_dominated_mess_current_row,
    slot_coefficients,
)
from dayahead.v28r2.formulation import materialize_formulation_data
from dayahead.v28r2.opendss_backend import run_fresh_opendss
from dayahead.v28r2.reference_compute import CASE_CAPACITY_GPU
from dayahead.v28r2.solver_runner import solve_monolithic
from dayahead.v28r2.trajectory import FrozenTrajectory
from dayahead.v28r2.workload_replay import materialize_actual_workload
from dayahead.v33m import MobilityRouteTable, RouteParameters15Min, load_road_graph_authority
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority
from dayahead.v33m.mess_trajectory import MessTrajectory, MessTrajectorySlot
from dayahead.v33m3 import CausalityLedger, DayAheadTrafficForecastBundle, causal_sample_contract, replay_committed_move
from dayahead.v34.actual_resource_recourse import ResourceRecourseResult, solve_resource_only_recourse
from dayahead.v34.correction import StaticCorrection
from dayahead.v34.integrated_mess import solve_integrated_mess

from .contracts import (
    ACTUAL_AIDC_FIREWALL_FIELDS,
    AIDC_STAGE_CASE,
    CASE_ACTUATORS,
    MESS_IDS,
    OFFICIAL_CASES,
    PHASE_MAY,
    SLOTS,
    assert_may_access,
)
from .effects import aidc_effect_watchdog, mess_effect_watchdog
from .storage import (
    CheckpointDependencies,
    array_sha256,
    atomic_json,
    atomic_npz,
    canonical_sha256,
    checkpoint_payload,
    sha256_file,
    storage_schema_sha256,
)
from .traffic_authority import (
    ELEVATED,
    LINK_ORDER,
    PHYSICAL,
    SERVICE_NODES,
    actual_sumo_authority,
    build_route_table,
)


DEFAULT_SOURCE_REPO = Path(
    r"C:\Users\kjw39\OneDrive\문서\ChatGPT\Mobile ESS 2\MobileESS_v28r2_heavy_backend"
)
DEFAULT_SERVICE_MAPPING = Path(
    r"C:\Users\kjw39\OneDrive\Desktop\4-2\Mobile ESS\work\power_side_p4f_review_20260731_190038"
    r"\power_side_p4f_hardening_v1\rating_contract_all_transformers"
    r"\service_node_electrical_mapping_v1.csv"
)
# V35R2 exogenous depot authority: deterministic farthest-point coverage on
# the frozen physical road-distance graph over the 12 station-class nodes.
# Seed STA01 and lexical tie-breaking are fixed; no electrical or April
# objective value participates in this selection.
MESS_INITIAL = dict(zip(MESS_IDS, ("STA01", "STA12", "STA08", "STA06"), strict=True))
COMMON_RHO_CURRENT_MODEL = "ANCHOR_GRADIENT_MATCHED_16_FACE_APPARENT_POWER_EPIGRAPH_V1"


def git_head(repo: Path) -> str:
    value = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if len(value) != 40:
        raise RuntimeError("V35_GIT_HEAD_INVALID")
    return value


def load_static_correction(path: Path | None) -> StaticCorrection | None:
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    source = payload.get("correction", payload)
    return StaticCorrection(
        family=str(source["family"]),
        up={str(key): float(value) for key, value in source["up"].items()},
        low={str(key): float(value) for key, value in source["low"].items()},
        fallback_count=int(source.get("fallback_count", 0)),
        calibration_days=tuple(map(str, source["calibration_days"])),
        calibration_cases=tuple(map(str, source["calibration_cases"])),
    )


def _service_mapping(path: Path = DEFAULT_SERVICE_MAPPING) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    mapping = {str(row["service_node_id"]): str(row["electrical_host_bus"]).lower() for row in rows}
    if len(mapping) != 24:
        raise RuntimeError("V35_SERVICE_PCC_MAPPING_AXIS")
    return mapping


def _route_cache_paths(cache_root: Path, phase: str, day: str) -> tuple[Path, Path]:
    # The forecast and 55,296-row route authority are independent of AC
    # correction phase, so prospective/corrected passes reuse the same bytes.
    root = cache_root / "shared/traffic" / day
    return root / "TRAFFIC_FORECAST.npz", root / "ROUTE_TABLE.json.gz"


def _save_forecast(path: Path, bundle: DayAheadTrafficForecastBundle) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.stem + ".tmp.npz")
    bundle.save_npz(temporary)
    os.replace(temporary, path)


def _load_forecast(path: Path) -> DayAheadTrafficForecastBundle:
    with np.load(path, allow_pickle=False) as payload:
        metadata = json.loads(str(payload["metadata"]))
        target = date.fromisoformat(str(metadata["forecast_day"]))
        contract = causal_sample_contract(
            target, (target.fromordinal(target.toordinal() - 7), target.fromordinal(target.toordinal() - 1)),
        )
        result = DayAheadTrafficForecastBundle(
            target,
            datetime.fromisoformat(str(metadata["issue_time"])),
            datetime.fromisoformat(str(metadata["max_input_timestamp"])),
            contract.target_timestamps,
            tuple(map(str, metadata["link_ids"])),
            np.asarray(payload["Q10_sec"], dtype=np.float32),
            np.asarray(payload["Q50_sec"], dtype=np.float32),
            np.asarray(payload["Q90_sec"], dtype=np.float32),
            str(metadata["model_id"]),
            str(metadata["model_sha"]),
            str(metadata["data_sha"]),
            str(metadata["graph_sha"]),
            str(metadata["normalization_sha"]),
            bool(metadata["causality_pass"]),
            int(metadata["future_actual_read_count"]),
        )
    if result.canonical_sha256 != metadata["bundle_sha"]:
        raise RuntimeError("V35_TRAFFIC_FORECAST_CACHE_SHA")
    return result


def _save_route_table(path: Path, route_table: MobilityRouteTable) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with gzip.open(temporary, "wb", compresslevel=6) as stream:
        stream.write(route_table.canonical_json_bytes())
    os.replace(temporary, path)
    with gzip.open(path, "rb") as stream:
        if hashlib.sha256(stream.read()).hexdigest() != route_table.canonical_sha256:
            raise RuntimeError("V35_ROUTE_TABLE_WRITE_RELOAD_SHA")


def _load_route_table(path: Path) -> MobilityRouteTable:
    with gzip.open(path, "rb") as stream:
        payload = json.loads(stream.read())
    records = {}
    for row in payload["routes"]:
        source = dict(row)
        source["route_link_ids"] = tuple(map(str, source["route_link_ids"]))
        record = RouteParameters15Min(**source)
        records[(record.departure_slot_15, record.origin_service_id, record.destination_service_id)] = record
    return MobilityRouteTable(
        tuple(map(int, payload["departure_slots"])),
        tuple(map(str, payload["service_ids"])),
        records,
    )


def daily_traffic_authority(
    repo: Path,
    cache_root: Path,
    phase: str,
    day: str,
    admission: Mapping[str, object] | None,
) -> tuple[DayAheadTrafficForecastBundle, object, MobilityRouteTable, tuple[dict[str, object], ...]]:
    forecast_path, route_path = _route_cache_paths(cache_root, phase, day)
    graph = load_road_graph_authority(LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED)
    if forecast_path.is_file() and route_path.is_file():
        bundle = _load_forecast(forecast_path)
        route_table = _load_route_table(route_path)
        with gzip.open(route_path, "rb") as stream:
            route_digest = hashlib.sha256(stream.read()).hexdigest()
        if route_table.canonical_sha256 != route_digest:
            raise RuntimeError("V35_ROUTE_TABLE_CACHE_SHA")
    else:
        bundle, built_graph, route_table = build_route_table(repo, day, may_admission=admission)
        if built_graph.route_graph_sha != graph.route_graph_sha:
            raise RuntimeError("V35_ROAD_GRAPH_AUTHORITY_DRIFT")
        _save_forecast(forecast_path, bundle)
        _save_route_table(route_path, route_table)
        bundle = _load_forecast(forecast_path)
        route_table = _load_route_table(route_path)
    if bundle.forecast_day.isoformat() != day or route_table.canonical_sha256 == "":
        raise RuntimeError("V35_DAILY_TRAFFIC_AUTHORITY_DAY_OR_SHA")
    files = (
        {"path": str(forecast_path.resolve()), "sha256": sha256_file(forecast_path)},
        {"path": str(route_path.resolve()), "sha256": sha256_file(route_path)},
    )
    return bundle, graph, route_table, files


def _electrical_context(repo: Path, source_repo: Path, cache_root: Path, phase: str, day: str, data: object):
    source_cache = source_repo / "frozen_artifacts/v28r2_april_full_month_preflight" / day / "dayahead/electrical_cache"
    local_cache = cache_root / "shared/electrical" / day
    candidate = source_cache if source_cache.is_dir() else local_cache
    try:
        return build_electrical_context(source_repo, data, candidate)
    except RuntimeError as error:
        if not str(error).startswith("V28R2_D1_ELECTRICAL_CACHE_MISSING:"):
            raise
        return prepare_electrical_context(source_repo, data, local_cache)


def _schedule_from_payload(payload: object, *, day: str, correction_sha: str) -> dict[str, object]:
    source = payload.canonical_payload()
    fields = (
        "case", "controls", "workload_service_tensor", "aidc_rack_cohort_allocation",
        "site_it_power_kw", "rack_it_power_kw", "rack_gpu", "site_gpu",
        "planning_pcc_power_kw", "planning_pcc_reactive_kvar", "backlog_nodeh",
        "formulation_fingerprint", "input_sha256",
    )
    result = {field: source[field] for field in fields}
    result.update({
        "day": day,
        "aidc_stage_case": source["case"],
        "MESS_stage": "DISABLED_ZERO_STATIONARY_NOT_MODELLED_AS_LEGACY_ROUTE",
        "common_rho_current_model": COMMON_RHO_CURRENT_MODEL,
        "correction_sha256": correction_sha,
        "solver_evidence": {
            "solver": payload.solver,
            "status": payload.status,
            "objective": payload.objective,
            "best_bound": payload.lower_bound,
            "MIP_gap": payload.gap,
            "runtime_seconds": payload.runtime_seconds,
        },
    })
    result["schedule_sha256"] = canonical_sha256(result)
    return result


def prepare_aidc_stages(
    repo: Path,
    source_repo: Path,
    cache_root: Path,
    phase: str,
    day: str,
    correction: StaticCorrection | None,
):
    data = materialize_formulation_data(source_repo, day, disable_legacy_mess_source=True)
    electrical = _electrical_context(repo, source_repo, cache_root, phase, day, data)
    correction_sha = "0" * 64 if correction is None else correction.canonical_sha256
    root = cache_root / phase / day / "shared/aidc_stages"
    paths = {case: root / f"AIDC_ONLY_{case}.json" for case in ("B0", "B1")}
    schedules: dict[str, dict[str, object]] = {}
    valid = True
    for case, path in paths.items():
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            stored = value.pop("schedule_sha256")
            valid = (
                valid
                and stored == canonical_sha256(value)
                and value["day"] == day
                and value["correction_sha256"] == correction_sha
                and value.get("common_rho_current_model") == COMMON_RHO_CURRENT_MODEL
            )
            value["schedule_sha256"] = stored
            schedules[case] = value
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            valid = False
    if not valid:
        schedules.clear()
        for case in ("B0", "B1"):
            payload = solve_monolithic(
                data=data,
                context=electrical.legacy_context,
                voltage=electrical.voltage,
                current=electrical.current,
                case=case,
                voltage_correction=correction,
                mess_disabled=True,
            )
            schedule = _schedule_from_payload(payload, day=day, correction_sha=correction_sha)
            atomic_json(paths[case], schedule)
            reloaded = json.loads(paths[case].read_text(encoding="utf-8"))
            stored = reloaded.pop("schedule_sha256")
            if stored != canonical_sha256(reloaded):
                raise RuntimeError("V35_AIDC_STAGE_STORAGE_SHA")
            reloaded["schedule_sha256"] = stored
            schedules[case] = reloaded
    return data, electrical, schedules


def _combined_trajectory_arrays(trajectory: MessTrajectory | None):
    p = np.zeros((SLOTS, 4), dtype=float)
    q = np.zeros((SLOTS, 4), dtype=float)
    energy = np.full((SLOTS, 4), 760.0, dtype=float)
    locations = np.repeat(np.asarray([[MESS_INITIAL[mess] for mess in MESS_IDS]], dtype="U64"), SLOTS, axis=0)
    modes = np.full((SLOTS, 4), "CONNECTED", dtype="U32")
    if trajectory is None:
        return p, q, energy, locations, modes
    by = {(row.mess_id, row.slot): row for row in trajectory.slots}
    for column, mess in enumerate(MESS_IDS):
        for slot in range(SLOTS):
            row = by[(mess, slot)]
            p[slot, column] = row.p_kw
            q[slot, column] = row.q_kvar
            energy[slot, column] = row.battery_energy_kwh
            # The OpenDSS replay contract recognizes unavailable mobile units
            # by a TRANSIT_* location token.  A bare "TRANSIT" is interpreted
            # as a physical service and leads to a nonexistent generator name.
            locations[slot, column] = (
                str(row.service_id)
                if row.service_id
                else f"TRANSIT_ROUTE_{column + 1:02d}"
            )
            modes[slot, column] = row.mode
    return p, q, energy, locations, modes


def _planning_grid(
    coefficients: Sequence[object],
    voltage_authority: object,
    aidc_p: np.ndarray,
    trajectory: MessTrajectory | None,
) -> tuple[dict[str, np.ndarray], dict[str, object]]:
    controls = tuple(map(str, voltage_authority["control_names"]))
    services = tuple(name[10:-1] for name in controls[12:36])
    by_p: dict[tuple[str, int], float] = {}
    by_q: dict[tuple[str, int], float] = {}
    if trajectory is not None:
        for row in trajectory.slots:
            if row.service_id is not None:
                key = (row.service_id, row.slot)
                by_p[key] = by_p.get(key, 0.0) + row.p_kw
                by_q[key] = by_q.get(key, 0.0) + row.q_kvar
    voltage_rows, current_rows, affine_current_rows = [], [], []
    exact_flow_current_rows, flow_p_rows, flow_q_rows, kva_rows = [], [], [], []
    for slot, coefficient in enumerate(coefficients):
        x = np.asarray(
            list(aidc_p[slot])
            + [by_p.get((service, slot), 0.0) for service in services]
            + [by_q.get((service, slot), 0.0) for service in services],
            dtype=float,
        )
        voltage_rows.append(np.sqrt(np.maximum(0.0, coefficient.voltage_constant + coefficient.voltage_matrix.T @ x)))
        affine_current = coefficient.current_constant + coefficient.current_matrix.T @ x
        repaired_current = anchored_polygon_loading(coefficient, x)
        line_branch = np.asarray([
            not name.startswith("transformer.") and not is_dominated_mess_current_row(name)
            for name in coefficient.branch_names
        ])
        current_rows.append(np.where(line_branch, repaired_current, affine_current))
        affine_current_rows.append(affine_current)
        p_flow = coefficient.flow_p_constant + coefficient.flow_p_matrix @ x
        q_flow = coefficient.flow_q_constant + coefficient.flow_q_matrix @ x
        flow_p_rows.append(p_flow); flow_q_rows.append(q_flow)
        exact_flow_current_rows.append(
            np.hypot(p_flow, q_flow) / np.asarray(coefficient.branch_limits, dtype=float)
        )
        kva_rows.append(np.asarray([
            0.0 if rating is None else math.hypot(float(p_flow[index]), float(q_flow[index])) / float(rating)
            for index, rating in enumerate(coefficient.transformer_ratings)
        ]))
    arrays = {
        "voltage_pu": np.asarray(voltage_rows),
        "phase_current_loading_pu": np.asarray(current_rows),
        "phase_current_affine_loading_pu": np.asarray(affine_current_rows),
        "phase_current_exact_flow_loading_pu": np.asarray(exact_flow_current_rows),
        "flow_p_kw": np.asarray(flow_p_rows),
        "flow_q_kvar": np.asarray(flow_q_rows),
        "transformer_kva_loading_pu": np.asarray(kva_rows),
    }
    branches = tuple(map(str, coefficients[0].branch_names))
    line_mask = np.asarray([
        not name.startswith("transformer.") and not is_dominated_mess_current_row(name)
        for name in branches
    ])
    tx_mask = np.asarray([name.startswith("transformer.") for name in branches])
    line_values = arrays["phase_current_loading_pu"][:, line_mask]
    rho_index = np.unravel_index(int(np.argmax(line_values)), line_values.shape)
    line_branches = np.asarray(branches)[line_mask]
    voltage = arrays["voltage_pu"]
    summary = {
        "rho": float(np.max(line_values)),
        "rho_model": COMMON_RHO_CURRENT_MODEL,
        "binding_asset": str(line_branches[rho_index[1]]),
        "binding_slot": int(rho_index[0]),
        "Vmin_pu": float(voltage.min()),
        "Vmax_pu": float(voltage.max()),
        "voltage_violation_count": int(np.count_nonzero((voltage < 0.95 - 1e-7) | (voltage > 1.05 + 1e-7))),
        "line_current_violation_count": int(np.count_nonzero(line_values > 1.0 + 1e-7)),
        "transformer_current_violation_count": int(np.count_nonzero(arrays["phase_current_loading_pu"][:, tx_mask] > 1.0 + 1e-7)),
        "transformer_kva_violation_count": int(np.count_nonzero(arrays["transformer_kva_loading_pu"][:, tx_mask] > 1.0 + 1e-7)),
    }
    summary["pass"] = not any(summary[name] for name in (
        "voltage_violation_count", "line_current_violation_count",
        "transformer_current_violation_count", "transformer_kva_violation_count",
    ))
    return arrays, summary


def _solver_record(mess_id: str, item: object) -> dict[str, object]:
    def finite_or_none(value: object) -> float | None:
        if value is None:
            return None
        number = float(value)
        return number if math.isfinite(number) else None

    return {
        "mess_id": mess_id,
        "solver_status": item.solver_status,
        "termination": item.termination,
        "bounded_compute_classification": item.bounded_compute_classification,
        "objective_value": finite_or_none(item.objective),
        "best_bound": finite_or_none(item.best_bound),
        "MIP_gap": finite_or_none(item.mip_gap),
        "work_limit_tiers_attempted": list(item.work_limit_tiers_attempted),
        "runtime_seconds": item.solve_seconds,
        "model_build_seconds": item.model_build_seconds,
        "variable_count": item.variable_count,
        "constraint_count": item.constraint_count,
        "binary_count": item.binary_count,
        "MOVE_binary_count": item.move_binary_count,
        "STAY_variable_count": item.stay_variable_count,
        "restricted_stationary_objective": finite_or_none(item.restricted_stationary_objective),
        "restricted_stationary_best_bound": finite_or_none(item.restricted_stationary_best_bound),
        "restricted_stationary_MIP_gap": finite_or_none(item.restricted_stationary_mip_gap),
        "restricted_stationary_status": item.restricted_stationary_status,
        "restricted_stationary_sum_abs_P_kW_slots": item.restricted_stationary_sum_abs_p_kw_slots,
        "restricted_stationary_sum_abs_Q_kvar_slots": item.restricted_stationary_sum_abs_q_kvar_slots,
        "restricted_incumbent_improves_zero": item.restricted_incumbent_improves_zero,
        "MIPStart_accepted": item.mip_start_accepted,
        "preferred_restricted_objective": finite_or_none(item.preferred_restricted_objective),
        "selected_restricted_start": item.selected_restricted_start,
        "preferred_MIPStart_loaded": item.preferred_mip_start_loaded,
        "zero_actuation_objective": item.zero_actuation_objective,
        "escalation_reason": item.escalation_reason,
        "peak_rss_bytes": item.peak_rss_bytes,
    }


def _solve_mess(
    case: str,
    aidc_p: np.ndarray,
    electrical: object,
    coefficients: Sequence[object],
    route_table: MobilityRouteTable,
    mapping: Mapping[str, str],
    correction: StaticCorrection | None,
) -> tuple[MessTrajectory, list[dict[str, object]], float]:
    fixed_p: dict[tuple[str, int], float] = {}
    fixed_q: dict[tuple[str, int], float] = {}
    slots: list[MessTrajectorySlot] = []
    records: list[dict[str, object]] = []
    objective = math.nan
    for mess_id in MESS_IDS:
        item = solve_integrated_mess(
            case=case,
            aidc_pcc_kw_96x12=aidc_p,
            electrical_context=electrical.legacy_context,
            voltage_authority=electrical.voltage,
            current_authority=electrical.current,
            route_table=route_table,
            service_to_pcc=mapping,
            initial_service_by_mess={mess_id: MESS_INITIAL[mess_id]},
            fixed_mess_p_by_service=fixed_p,
            fixed_mess_q_by_service=fixed_q,
            grid_coefficients=coefficients,
            correction=correction,
        )
        records.append(_solver_record(mess_id, item))
        slots.extend(item.trajectory.slots)
        objective = float(item.objective)
        for row in item.trajectory.slots:
            if row.service_id is not None:
                key = (row.service_id, row.slot)
                fixed_p[key] = fixed_p.get(key, 0.0) + row.p_kw
                fixed_q[key] = fixed_q.get(key, 0.0) + row.q_kvar
    return MessTrajectory(tuple(slots)), records, objective


def _actual_aidc(
    repo: Path,
    source_repo: Path,
    day: str,
    base: Mapping[str, object],
) -> tuple[ResourceRecourseResult, object]:
    actual = materialize_actual_workload(source_repo, day)
    rack = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    weights = np.asarray(rack["gpu_weights"], dtype=float)
    capacity = np.repeat((CASE_CAPACITY_GPU * weights * .25 / 4.0)[None, :], SLOTS, axis=0)
    result = solve_resource_only_recourse(
        np.asarray(base["workload_service_tensor"], dtype=float),
        actual.arrivals_nodeh,
        capacity,
        np.ones((15, 48), dtype=bool),
    )
    return result, actual


def _actual_mess(
    day: str,
    bundle: DayAheadTrafficForecastBundle,
    graph: object,
    trajectory: MessTrajectory | None,
    admission: Mapping[str, object] | None,
) -> tuple[dict[str, object], np.ndarray]:
    availability = np.ones((SLOTS, 4), dtype=bool)
    if trajectory is None:
        return {
            "DA_commitments": [], "actual_replays": [], "route_identity": "PASS",
            "actual_MESS_optimizer_calls": 0, "actual_MESS_reroute_calls": 0,
            "actual_route_change_count": 0,
            "terminal_SoC": [E_INITIAL_KWH / CAPACITY_KWH] * 4,
        }, availability
    commitments = trajectory.planned_move_commitments()
    ledger = CausalityLedger(bundle.issue_time)
    freeze = ledger.freeze(trajectory.canonical_sha256)
    authority = actual_sumo_authority(day, bundle.link_ids, may_admission=admission)
    replays = [
        replay_committed_move(
            item, authority, graph, ledger, freeze,
            battery_capacity_kwh=CAPACITY_KWH,
        )
        for item in commitments
    ]
    ledger.assert_clean()
    terminal = {mess: E_INITIAL_KWH for mess in MESS_IDS}
    for replay in replays:
        terminal[replay.mess_id] += replay.planned_energy_kwh - replay.actual_energy_kwh
        column = MESS_IDS.index(replay.mess_id)
        availability[replay.departure_slot:min(SLOTS, replay.actual_connection_ready_slot), column] = False
    return {
        "DA_commitments": [asdict(item) for item in commitments],
        "actual_replays": [asdict(item) for item in replays],
        "route_identity": "PASS",
        "actual_MESS_optimizer_calls": ledger.actual_mess_optimizer_calls,
        "actual_MESS_reroute_calls": ledger.actual_reroute_calls,
        "actual_route_change_count": ledger.actual_route_change_count,
        "terminal_SoC": [terminal[mess] / CAPACITY_KWH for mess in MESS_IDS],
    }, availability


def _files_valid(records: Sequence[Mapping[str, object]]) -> bool:
    try:
        return all(
            Path(str(row["path"])).is_file()
            and Path(str(row["path"])).stat().st_size > 0
            and sha256_file(Path(str(row["path"]))) == str(row["sha256"])
            for row in records
        )
    except (OSError, KeyError, TypeError):
        return False


def normalize_v35_fresh_storage(output: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Encode non-applicable transformer kVA rows without non-finite sentinels."""

    arrays_path = output / "OPENDSS_PHASE_ARRAYS.npz"
    manifest_path = output / "OPENDSS_OUTPUT_MANIFEST.json"
    with np.load(arrays_path, allow_pickle=False) as source:
        arrays = {name: np.asarray(source[name]) for name in source.files}
    kinds = np.asarray(arrays["branch_kinds"]).astype(str)
    applicable = kinds == "transformer"
    kva = np.asarray(arrays["transformer_total_kva_loading_pu"], dtype=float)
    if kva.shape != (SLOTS, len(kinds)):
        raise RuntimeError("V35_FRESH_TRANSFORMER_KVA_AXIS")
    if not np.isfinite(kva[:, applicable]).all():
        raise RuntimeError("V35_FRESH_APPLICABLE_TRANSFORMER_KVA_NONFINITE")
    non_applicable = kva[:, ~applicable]
    if not (np.isnan(non_applicable) | (non_applicable == 0.0)).all():
        raise RuntimeError("V35_FRESH_NONAPPLICABLE_TRANSFORMER_KVA_ENCODING")
    arrays["transformer_total_kva_loading_pu"] = np.where(applicable[None, :], kva, 0.0)
    arrays["transformer_total_kva_applicable"] = applicable
    numeric = tuple(
        name for name, array in arrays.items()
        if np.issubdtype(np.asarray(array).dtype, np.number)
    )
    arrays_record = atomic_npz(
        arrays_path, arrays, {name: np.asarray(array).shape for name, array in arrays.items()},
        require_finite=numeric,
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][arrays_path.name] = {
        "sha256": arrays_record["sha256"], "bytes": arrays_path.stat().st_size,
    }
    manifest["V35_transformer_kVA_encoding"] = {
        "non_applicable_value": 0.0,
        "applicability_array": "transformer_total_kva_applicable",
        "applicable_branch_kind": "transformer",
        "all_numeric_arrays_finite": True,
    }
    manifest.pop("manifest_payload_sha256", None)
    manifest["manifest_payload_sha256"] = canonical_sha256(manifest)
    manifest_sha = atomic_json(manifest_path, manifest)
    with np.load(arrays_path, allow_pickle=False) as reloaded:
        if not np.array_equal(np.asarray(reloaded["transformer_total_kva_applicable"]), applicable):
            raise RuntimeError("V35_FRESH_TRANSFORMER_KVA_MASK_RELOAD")
        for name in numeric:
            if not np.isfinite(np.asarray(reloaded[name])).all():
                raise RuntimeError(f"V35_FRESH_NUMERIC_RELOAD_NONFINITE:{name}")
    return arrays_record, {"path": str(manifest_path.resolve()), "sha256": manifest_sha}


def _load_cached_case(
    root: Path,
    *,
    phase: str,
    day: str,
    case: str,
    code_head: str,
    science_sha: str,
    correction_sha: str,
    forecast_sha: str,
    route_sha: str | None,
    aidc_sha: str,
    solver_sha: str,
) -> dict[str, object] | None:
    checkpoint_path = root / "CHECKPOINT.json"
    result_path = root / "CASE_RESULT.json"
    try:
        checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    expected = {
        "phase": phase, "day": day, "case": case, "status": "PASS",
        "code_HEAD": code_head, "science_authority_SHA": science_sha,
        "forecast_SHA": forecast_sha, "route_table_SHA": route_sha,
        "AIDC_schedule_SHA": aidc_sha, "solver_settings_SHA": solver_sha,
        "storage_schema_SHA": storage_schema_sha256(),
    }
    if any(checkpoint.get(key) != value for key, value in expected.items()):
        return None
    if result.get("correction_sha256") != correction_sha or not _files_valid(checkpoint.get("storage_files", [])):
        return None
    # CASE_RESULT cannot contain its own hash, so the immutable checkpoint is
    # authoritative for the complete storage-file list during resume.
    result["storage_files"] = list(checkpoint["storage_files"])
    return result


def _case_array_payload(root: Path) -> dict[str, np.ndarray]:
    with np.load(root / "DAYAHEAD_AIDC.npz", allow_pickle=False) as aidc, \
            np.load(root / "DAYAHEAD_MESS.npz", allow_pickle=False) as mess, \
            np.load(root / "PLANNING_GRID.npz", allow_pickle=False) as planning, \
            np.load(root / "fresh/OPENDSS_PHASE_ARRAYS.npz", allow_pickle=False) as fresh:
        return {
            "workload": np.asarray(aidc["workload_execution_tensor"]),
            "aidc_p": np.asarray(aidc["AIDC_P_kw"]),
            "aidc_q": np.asarray(aidc["AIDC_Q_kvar"]),
            "mess_p": np.asarray(mess["P_kw"]),
            "mess_q": np.asarray(mess["Q_kvar"]),
            "planning_voltage": np.asarray(planning["voltage_pu"]),
            "planning_current": np.asarray(planning["phase_current_loading_pu"]),
            "fresh_voltage": np.asarray(fresh["voltage_pu"]),
            "fresh_current": np.asarray(fresh["phase_current_loading_pu"]),
        }


def _cross_case_effect_metrics(off: Mapping[str, object], on: Mapping[str, object]) -> dict[str, float]:
    off_actual = off["actual"]["actual_AIDC"]
    on_actual = on["actual"]["actual_AIDC"]

    def service_ratio(value: Mapping[str, object]) -> float:
        executed = float(value["executed_nodeh"])
        backlog = float(value["blocked_or_backlog_nodeh"])
        return executed / max(executed + backlog, 1e-12)

    return {
        "Fresh_losses_delta_kWh": float(on["fresh"]["losses_kwh"]) - float(off["fresh"]["losses_kwh"]),
        "actual_executed_nodeh_delta": float(on_actual["executed_nodeh"]) - float(off_actual["executed_nodeh"]),
        "actual_backlog_nodeh_delta": float(on_actual["blocked_or_backlog_nodeh"]) - float(off_actual["blocked_or_backlog_nodeh"]),
        "actual_service_ratio_delta": service_ratio(on_actual) - service_ratio(off_actual),
    }


def execute_day(
    *,
    repo: Path,
    source_repo: Path,
    artifact_root: Path,
    cache_root: Path,
    phase: str,
    day: str,
    run_id: str,
    science_sha: str,
    correction: StaticCorrection | None,
    admission: Mapping[str, object] | None = None,
    progress_callback=None,
) -> dict[str, object]:
    assert_may_access(day, admission)
    code_head = git_head(repo)
    correction_sha = "0" * 64 if correction is None else correction.canonical_sha256
    solver_sha = canonical_sha256({
        "seed": 20260828, "MESS_WorkLimit_tiers": [60, 180, 300],
        "vehicle_order": list(MESS_IDS), "AIDC_solver": "GUROBI_MONOLITHIC_OPTIMAL",
        "common_rho_current_model": COMMON_RHO_CURRENT_MODEL,
        "initial_service_by_mess": MESS_INITIAL,
        "correction_sha256": correction_sha,
    })
    bundle, graph, route_table, traffic_files = daily_traffic_authority(
        repo, cache_root, phase, day, admission,
    )
    data, electrical, base_schedules = prepare_aidc_stages(
        repo, source_repo, cache_root, phase, day, correction,
    )
    mapping = _service_mapping()
    coefficients = tuple(
        slot_coefficients(electrical.legacy_context, electrical.voltage, electrical.current, slot)
        for slot in range(SLOTS)
    )
    actual_by_stage: dict[str, tuple[ResourceRecourseResult, object]] = {}
    cases: dict[str, dict[str, object]] = {}
    try:
        for case in OFFICIAL_CASES:
            if progress_callback is not None:
                progress_callback(case)
            stage = AIDC_STAGE_CASE[case]
            base = base_schedules[stage]
            case_root = cache_root / phase / day / case
            route_sha = route_table.canonical_sha256 if CASE_ACTUATORS[case]["mess"] else None
            cached = _load_cached_case(
                case_root,
                phase=phase, day=day, case=case, code_head=code_head,
                science_sha=science_sha, correction_sha=correction_sha,
                forecast_sha=bundle.canonical_sha256, route_sha=route_sha,
                aidc_sha=str(base["schedule_sha256"]), solver_sha=solver_sha,
            )
            if cached is not None:
                cached["arrays"] = _case_array_payload(case_root)
                cases[case] = cached
                continue
            started = time.perf_counter()
            aidc_p = np.asarray(base["planning_pcc_power_kw"], dtype=float)
            aidc_q = np.asarray(base["planning_pcc_reactive_kvar"], dtype=float)
            if CASE_ACTUATORS[case]["mess"]:
                mess_trajectory, solver_records, objective = _solve_mess(
                    case, aidc_p, electrical, coefficients, route_table, mapping, correction,
                )
            else:
                mess_trajectory, solver_records, objective = None, [], math.nan
            p, q, energy, locations, modes = _combined_trajectory_arrays(mess_trajectory)
            planning_arrays, planning_summary = _planning_grid(
                coefficients, electrical.voltage, aidc_p, mess_trajectory,
            )
            if not math.isfinite(objective):
                objective = float(planning_summary["rho"])
            schedule_payload = {
                "day": day, "phase": phase, "case": case,
                "aidc_enabled": CASE_ACTUATORS[case]["aidc"],
                "mess_enabled": CASE_ACTUATORS[case]["mess"],
                "aidc_stage_case": stage,
                "aidc_schedule_sha256": base["schedule_sha256"],
                "mess_trajectory_sha256": None if mess_trajectory is None else mess_trajectory.canonical_sha256,
                "traffic_forecast_sha256": bundle.canonical_sha256,
                "route_table_sha256": route_sha,
                "correction_sha256": correction_sha,
                "AIDC_P_sha256": array_sha256(aidc_p),
                "AIDC_Q_sha256": array_sha256(aidc_q),
                "MESS_P_sha256": array_sha256(p),
                "MESS_Q_sha256": array_sha256(q),
            }
            combined_sha = canonical_sha256(schedule_payload)
            frozen = FrozenTrajectory(
                day, "DAYAHEAD", case, aidc_p, aidc_q, p, q, MESS_IDS, locations, combined_sha,
            )
            fresh = run_fresh_opendss(
                repo=source_repo, context=electrical, voltage=electrical.voltage,
                trajectory=frozen, output=case_root / "fresh",
            )
            if fresh.schedule_sha256 != combined_sha:
                raise RuntimeError("V35_PLANNING_FRESH_SCHEDULE_SHA_IDENTITY")
            fresh_array_record, fresh_manifest_record = normalize_v35_fresh_storage(case_root / "fresh")
            if stage not in actual_by_stage:
                actual_by_stage[stage] = _actual_aidc(repo, source_repo, day, base)
            actual_aidc, actual_workload = actual_by_stage[stage]
            actual_mess, mess_availability = _actual_mess(
                day, bundle, graph, mess_trajectory, admission,
            )
            if any(actual_aidc.firewall.values()) or any(int(actual_mess[field]) for field in (
                "actual_MESS_optimizer_calls", "actual_MESS_reroute_calls", "actual_route_change_count",
            )):
                raise RuntimeError("V35_CAUSALITY_FIREWALL_DEFECT")

            workload = np.asarray(base["workload_service_tensor"], dtype=float)
            backlog = np.asarray(base["backlog_nodeh"], dtype=float)
            aidc_record = atomic_npz(
                case_root / "DAYAHEAD_AIDC.npz",
                {
                    "workload_execution_tensor": workload,
                    "execution_slot_nodeh": workload.sum(axis=1).T,
                    "site_rack_allocation": workload.sum(axis=(0, 2)),
                    "authorized_workload": workload,
                    "deferred_backlog_workload": backlog,
                    "AIDC_P_kw": aidc_p,
                    "AIDC_Q_kvar": aidc_q,
                },
                {
                    "workload_execution_tensor": (15, 48, 96),
                    "execution_slot_nodeh": (96, 15),
                    "site_rack_allocation": (48,),
                    "authorized_workload": (15, 48, 96),
                    "deferred_backlog_workload": (97, 15),
                    "AIDC_P_kw": (96, 12), "AIDC_Q_kvar": (96, 12),
                },
                require_finite=(
                    "workload_execution_tensor", "execution_slot_nodeh", "site_rack_allocation",
                    "authorized_workload", "deferred_backlog_workload", "AIDC_P_kw", "AIDC_Q_kvar",
                ),
            )
            mess_record = atomic_npz(
                case_root / "DAYAHEAD_MESS.npz",
                {"P_kw": p, "Q_kvar": q, "energy_kwh": energy, "locations": locations, "modes": modes},
                {"P_kw": (96, 4), "Q_kvar": (96, 4), "energy_kwh": (96, 4), "locations": (96, 4), "modes": (96, 4)},
                require_finite=("P_kw", "Q_kvar", "energy_kwh"),
            )
            planning_record = atomic_npz(
                case_root / "PLANNING_GRID.npz", {
                    **planning_arrays,
                    "node_names": np.asarray(fresh.node_names),
                    "node_phases": np.asarray(fresh.node_phases),
                    "branch_names": np.asarray(fresh.branch_names),
                    "branch_phases": np.asarray(fresh.branch_phases),
                    "branch_kinds": np.asarray(fresh.branch_kinds),
                },
                {
                    "voltage_pu": (96, len(fresh.node_names)),
                    "phase_current_loading_pu": (96, len(fresh.branch_names)),
                    "phase_current_affine_loading_pu": (96, len(fresh.branch_names)),
                    "phase_current_exact_flow_loading_pu": (96, len(fresh.branch_names)),
                    "flow_p_kw": (96, len(fresh.branch_names)),
                    "flow_q_kvar": (96, len(fresh.branch_names)),
                    "transformer_kva_loading_pu": (96, len(fresh.branch_names)),
                    "node_names": (len(fresh.node_names),),
                    "node_phases": (len(fresh.node_names),),
                    "branch_names": (len(fresh.branch_names),),
                    "branch_phases": (len(fresh.branch_names),),
                    "branch_kinds": (len(fresh.branch_names),),
                },
                require_finite=tuple(planning_arrays),
            )
            actual_aidc_record = atomic_npz(
                case_root / "ACTUAL_AIDC.npz",
                {
                    "actual_arrivals_nodeh": actual_workload.arrivals_nodeh,
                    "executed_workload": actual_aidc.executed_nodeh,
                    "backlog": actual_aidc.backlog_nodeh,
                },
                {"actual_arrivals_nodeh": (96, 15), "executed_workload": (15, 48, 96), "backlog": (97, 15)},
                require_finite=("actual_arrivals_nodeh", "executed_workload", "backlog"),
            )
            actual_mess_record = atomic_npz(
                case_root / "ACTUAL_MESS.npz",
                {"PQ_availability": mess_availability, "terminal_SoC": np.asarray(actual_mess["terminal_SoC"])},
                {"PQ_availability": (96, 4), "terminal_SoC": (4,)},
                require_finite=("terminal_SoC",),
            )
            trajectory_path = case_root / "MESS_TRAJECTORY.json"
            atomic_json(trajectory_path, {
                "day": day, "case": case,
                "trajectory_sha256": None if mess_trajectory is None else mess_trajectory.canonical_sha256,
                "slots": [] if mess_trajectory is None else [row.to_dict() for row in mess_trajectory.slots],
                "solver_evidence": solver_records,
            })
            actual_summary_path = case_root / "ACTUAL_SUMMARY.json"
            same_site = float(np.minimum(actual_aidc.executed_nodeh, workload).sum())
            executed_total = actual_aidc.executed_total_nodeh
            actual_summary = {
                "day": day, "case": case,
                "actual_AIDC": {
                    "executed_nodeh": executed_total,
                    "same_site_nodeh": same_site,
                    "cross_site_recourse_nodeh": max(0.0, executed_total - same_site),
                    "blocked_or_backlog_nodeh": float(actual_aidc.backlog_nodeh[-1].sum()),
                    "resource_only_recourse_nodeh": actual_aidc.recourse_nodeh,
                    "solver_calls": actual_aidc.solver_calls,
                    "firewall": actual_aidc.firewall,
                    "read_fields": sorted({str(row["field"]) for row in actual_aidc.read_ledger}),
                },
                "actual_MESS": actual_mess,
            }
            actual_sha = atomic_json(actual_summary_path, actual_summary)
            fresh_arrays = case_root / "fresh/OPENDSS_PHASE_ARRAYS.npz"
            storage_files = [
                aidc_record, mess_record, planning_record, actual_aidc_record, actual_mess_record,
                {"path": str(trajectory_path.resolve()), "sha256": sha256_file(trajectory_path)},
                {"path": str(actual_summary_path.resolve()), "sha256": actual_sha},
                fresh_array_record, fresh_manifest_record,
                *traffic_files,
            ]
            files_compact = [{"path": row["path"], "sha256": row["sha256"]} for row in storage_files]
            authority = {
                "forecast_authority_SHA": bundle.canonical_sha256,
                "issue_time": bundle.issue_time.isoformat(),
                "feature_cutoff": bundle.max_input_timestamp.isoformat(),
                "AIDC_model_authority_SHA": data.formulation_fingerprint,
                "traffic_model_SHA": bundle.model_sha,
                "feeder_SHA": science_sha,
                "AIDC_scale_SHA": science_sha,
                "C1_SHA": science_sha,
                "road_graph_SHA": graph.route_graph_sha,
                "service_mapping_SHA": sha256_file(DEFAULT_SERVICE_MAPPING),
                "solver_settings_SHA": solver_sha,
            }
            result = {
                "artifact_id": "V35_PHASE_DAY_CASE_RESULT_V1",
                "phase": phase, "day": day, "case": case,
                "status": "PASS",
                "aidc_enabled": CASE_ACTUATORS[case]["aidc"],
                "mess_enabled": CASE_ACTUATORS[case]["mess"],
                "aidc_stage_case": stage,
                "aidc_schedule_sha256": base["schedule_sha256"],
                "mess_trajectory_sha256": None if mess_trajectory is None else mess_trajectory.canonical_sha256,
                "combined_schedule_sha256": combined_sha,
                "correction_sha256": correction_sha,
                "objective": objective,
                "objective_best_bound": objective if not solver_records else solver_records[-1]["best_bound"],
                "objective_unresolved_absolute_gap": (
                    0.0 if not solver_records else (
                        None if solver_records[-1]["best_bound"] is None
                        else abs(objective - float(solver_records[-1]["best_bound"]))
                    )
                ),
                "planning": planning_summary,
                "fresh": fresh.summary,
                "MESS": {
                    "MOVE_count": 0 if mess_trajectory is None else len(mess_trajectory.planned_move_commitments()),
                    "PQ_nonzero_slot_count": int(np.count_nonzero(np.any((np.abs(p) > 1e-7) | (np.abs(q) > 1e-7), axis=1))),
                    "sum_abs_P_kW_slots": float(np.abs(p).sum()),
                    "sum_abs_Q_kvar_slots": float(np.abs(q).sum()),
                    "throughput_kWh": float(np.abs(p).sum() * 0.25),
                    "travel_energy_kWh": 0.0 if mess_trajectory is None else float(sum(row.energy_safe_kwh for row in mess_trajectory.planned_move_commitments())),
                    "terminal_SoC": actual_mess["terminal_SoC"],
                    "solver_evidence": solver_records,
                },
                "actual": actual_summary,
                "input_authority": authority,
                "runtime_seconds": time.perf_counter() - started,
                "storage_validation": "PASS",
                "fresh_storage_contract": {
                    "all_numeric_arrays_finite": True,
                    "transformer_kVA_non_applicable_encoding": "ZERO_WITH_EXPLICIT_APPLICABILITY_MASK",
                },
                "storage_files": files_compact,
            }
            result_path = case_root / "CASE_RESULT.json"
            result_sha = atomic_json(result_path, result)
            files_compact.append({"path": str(result_path.resolve()), "sha256": result_sha})
            planning_sha = sha256_file(case_root / "PLANNING_GRID.npz")
            fresh_sha = sha256_file(fresh_arrays)
            dependencies = CheckpointDependencies(
                code_head, science_sha, bundle.canonical_sha256, route_sha,
                str(base["schedule_sha256"]),
                None if mess_trajectory is None else mess_trajectory.canonical_sha256,
                combined_sha, planning_sha, fresh_sha, actual_sha, solver_sha, storage_schema_sha256(),
            )
            checkpoint = checkpoint_payload(
                phase=phase, day=day, case=case, run_id=run_id,
                timestamp=datetime.now(timezone.utc).isoformat(), dependencies=dependencies,
                storage_files=files_compact,
            )
            atomic_json(case_root / "CHECKPOINT.json", checkpoint)
            if not _files_valid(files_compact):
                raise RuntimeError("V35_STORAGE_INTEGRITY_DEFECT_AFTER_RELOAD")
            result["arrays"] = _case_array_payload(case_root)
            cases[case] = result
    finally:
        electrical.voltage.close(); electrical.current.close()

    rack_contract = json.loads((repo / "dayahead/artifacts/v16/AIDC_RACK_MAPPING_CONTRACT.json").read_text(encoding="utf-8"))
    rack_site_ids = tuple(str(row["aidc_id"]) for row in rack_contract["racks"])
    comparisons: dict[str, dict[str, object]] = {}
    for name, off_case, on_case in (
        ("B1-B0", "B0", "B1"), ("B3-B2", "B2", "B3"),
    ):
        off, on = cases[off_case], cases[on_case]
        comparisons[name] = aidc_effect_watchdog(
            comparison=name,
            off_workload=off["arrays"]["workload"], on_workload=on["arrays"]["workload"],
            off_p=off["arrays"]["aidc_p"], on_p=on["arrays"]["aidc_p"],
            off_q=off["arrays"]["aidc_q"], on_q=on["arrays"]["aidc_q"],
            off_planning=off["arrays"]["planning_voltage"], on_planning=on["arrays"]["planning_voltage"],
            off_fresh=off["arrays"]["fresh_voltage"], on_fresh=on["arrays"]["fresh_voltage"],
            objective_off=float(off["objective"]), objective_on=float(on["objective"]),
            unresolved_gap_off=(
                1e30 if off["objective_unresolved_absolute_gap"] is None
                else float(off["objective_unresolved_absolute_gap"])
            ),
            unresolved_gap_on=(
                1e30 if on["objective_unresolved_absolute_gap"] is None
                else float(on["objective_unresolved_absolute_gap"])
            ),
            free_workload_count=int(np.asarray(on["arrays"]["workload"]).size),
            rack_site_ids=rack_site_ids,
            solver_status_off="OPTIMAL" if not off["MESS"]["solver_evidence"] else str(off["MESS"]["solver_evidence"][-1]["termination"]),
            solver_status_on="OPTIMAL" if not on["MESS"]["solver_evidence"] else str(on["MESS"]["solver_evidence"][-1]["termination"]),
            planning_rho_off=float(off["planning"]["rho"]),
            planning_rho_on=float(on["planning"]["rho"]),
            fresh_rho_off=float(off["fresh"]["rho_max_AC"]),
            fresh_rho_on=float(on["fresh"]["rho_max_AC"]),
        )
        comparisons[name].update(_cross_case_effect_metrics(off, on))
    for name, off_case, on_case in (
        ("B2-B0", "B0", "B2"), ("B3-B1", "B1", "B3"),
    ):
        off, on = cases[off_case], cases[on_case]
        comparisons[name] = mess_effect_watchdog(
            comparison=name,
            p_kw=on["arrays"]["mess_p"], q_kvar=on["arrays"]["mess_q"],
            move_count=int(on["MESS"]["MOVE_count"]),
            objective_off=float(off["objective"]), objective_on=float(on["objective"]),
            planning_rho_off=float(off["planning"]["rho"]), planning_rho_on=float(on["planning"]["rho"]),
            fresh_rho_off=float(off["fresh"]["rho_max_AC"]), fresh_rho_on=float(on["fresh"]["rho_max_AC"]),
            travel_energy_kwh=float(on["MESS"]["travel_energy_kWh"]),
            terminal_soc=on["MESS"]["terminal_SoC"],
            solver_records=on["MESS"]["solver_evidence"],
        )
        comparisons[name].update(_cross_case_effect_metrics(off, on))
    effect_path = artifact_root / "daily" / phase / day / "EFFECT_WATCHDOG.json"
    atomic_json(effect_path, {
        "day": day, "phase": phase, "status": "PASS" if all(row["status"] == "PASS" for row in comparisons.values()) else "DIAGNOSE",
        "comparisons": comparisons,
    })
    compact_cases = {}
    for case, row in cases.items():
        compact_cases[case] = {key: value for key, value in row.items() if key != "arrays"}
    day_result = {
        "artifact_id": "V35_PHASE_DAY_RESULT_V1", "phase": phase, "day": day,
        "status": "PASS" if all(row["status"] == "PASS" for row in cases.values()) else "FAIL",
        "cases": compact_cases, "effects": comparisons,
        "forecast_sha256": bundle.canonical_sha256,
        "route_table_sha256": route_table.canonical_sha256,
        "correction_sha256": correction_sha,
        "May_numeric_read": phase == PHASE_MAY,
    }
    output = artifact_root / "daily" / phase / day / "DAY_RESULT.json"
    atomic_json(output, day_result)
    return day_result
