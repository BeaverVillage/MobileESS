"""Read-only April adapter for the frozen V33M3 traffic authority."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.v33m import Mobility15MinAdapter, build_mobility_route_table, load_road_graph_authority
from dayahead.v33m3 import DARQSTGModel, DARQSTGParameters, DayAheadTrafficForecastBundle, RouteSafeEtaCalibration, SumoActualAuthority, causal_sample_contract

from .contracts import CALIBRATION_DAYS, VALIDATION_DAYS, reject_may


WSL_ROOT = Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline")
TRAFFIC_DATA = WSL_ROOT / "08_production_5min_validated_stage25f"
STAGE21 = WSL_ROOT / "21_ml_stage9_v11_fixed_station_full_traffic_freeze_v1"
LINK_ORDER = WSL_ROOT / "10_ml_stage1_multires_traffic_v1/graph/link_order_509.csv"
SERVICE_NODES = STAGE21 / "freeze_assets/stage8/optimizer_interface/final_service_nodes_24.csv"
PHYSICAL = WSL_ROOT / "24c_energy_stage_e1r_canonical_physical_route_library_v1_1_metric_repair/library/reduced_link_physical_edge_congestion_catalog.csv.gz"
ELEVATED = WSL_ROOT / "24e_energy_stage_e1g_grade_validation_v1_7_resolution_aware_grade_profile/network/network_elevated_conditioned.net.xml"
DATA_SHA = "c2e532212eba796b652bdd283a8127c2343b9305146d387975f4c69c2a848183"
MODEL_ID = "DA-RQSTG-DIRECT-288-V1"
NORMALIZATION_ID = "train-only-seasonal-median-seconds-v33m3"


def _sha_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_day(day: date, link_index: dict[str, int], max_slot: int = 287) -> tuple[np.ndarray, np.ndarray]:
    reject_may(day.isoformat())
    path = TRAFFIC_DATA / f"year={day.year}" / f"date={day.isoformat()}" / "link_tt_5min_24h.parquet"
    frame = pd.read_parquet(
        path,
        columns=["slot5", "reduced_link_id", "final_tt_sec", "scats_global_log_intensity"],
        filters=[("slot5", "<=", max_slot)],
    )
    if frame.duplicated(["slot5", "reduced_link_id"]).any():
        raise RuntimeError("V34_TRAFFIC_DUPLICATE_LINK_SLOT")
    steps = max_slot + 1
    tt = np.full((steps, 509), np.nan, dtype=np.float32)
    scats = np.full((steps, 509), np.nan, dtype=np.float32)
    rows = frame.slot5.to_numpy(dtype=int)
    columns = frame.reduced_link_id.map(link_index).to_numpy(dtype=int)
    tt[rows, columns] = frame.final_tt_sec.to_numpy(dtype=np.float32)
    scats[rows, columns] = frame.scats_global_log_intensity.to_numpy(dtype=np.float32)
    if not np.isfinite(tt).all() or not np.isfinite(scats).all():
        raise RuntimeError("V34_TRAFFIC_MISSING_OR_NONFINITE")
    return tt, scats


def load_final_authority(repo: Path) -> tuple[np.ndarray, tuple[str, ...], DARQSTGParameters, RouteSafeEtaCalibration, dict[str, object]]:
    root = repo / "dayahead/artifacts/v33m3_causal_dayahead_traffic"
    authority = json.loads((root / "V33M3_FINAL_MODEL_AUTHORITY.json").read_text(encoding="utf-8"))
    checkpoint = root / str(authority["checkpoint"])
    if _sha_file(checkpoint) != authority["checkpoint_sha256"]:
        raise RuntimeError("V34_V33M3_CHECKPOINT_SHA_MISMATCH")
    with np.load(checkpoint, allow_pickle=False) as payload:
        seasonal = np.asarray(payload["seasonal_median_sec"], dtype=np.float32)
        links = tuple(map(str, payload["link_ids"]))
        parameters = DARQSTGParameters(**json.loads(str(payload["parameters"])))
    safe = json.loads((root / "V33M3_SAFE_ETA_CALIBRATION.json").read_text(encoding="utf-8"))
    calibration = RouteSafeEtaCalibration(tuple(map(float, safe["margins_sec"])), float(safe["quantile"]), str(safe["fit_namespace"]))
    if seasonal.shape != (7, 288, 509) or len(links) != 509 or parameters.model_sha != authority["model_sha"]:
        raise RuntimeError("V34_V33M3_FINAL_AUTHORITY_AXIS_OR_MODEL_SHA")
    return seasonal, links, parameters, calibration, authority


def _adjacency(links: tuple[str, ...]) -> np.ndarray:
    rows = pd.read_csv(LINK_ORDER).sort_values("tensor_index")
    if tuple(rows.reduced_link_id.astype(str)) != links:
        raise RuntimeError("V34_TRAFFIC_GRAPH_LINK_AXIS")
    starts = rows.from_node.astype(str).to_numpy()
    ends = rows.to_node.astype(str).to_numpy()
    matrix = np.eye(509, dtype=np.float32)
    for index in range(509):
        matrix[index, np.where((starts == ends[index]) | (ends == starts[index]))[0]] = 1.0
    return matrix


def forecast_april_day(repo: Path, day: str) -> tuple[DayAheadTrafficForecastBundle, RouteSafeEtaCalibration]:
    reject_may(day)
    if day not in set(CALIBRATION_DAYS + VALIDATION_DAYS):
        raise ValueError("V34_TRAFFIC_DAY_OUTSIDE_APRIL")
    target = date.fromisoformat(day)
    seasonal, links, parameters, calibration, authority = load_final_authority(repo)
    link_index = {value: index for index, value in enumerate(links)}
    week, _ = _load_day(target.fromordinal(target.toordinal() - 7), link_index)
    partial, scats = _load_day(target.fromordinal(target.toordinal() - 1), link_index, 215)
    base = seasonal[target.weekday()]
    previous = base.copy(); previous[:216] = partial
    mask = np.zeros(288, dtype=bool); mask[:216] = True
    recent = partial[192:216]
    recent_base = seasonal[(target.weekday() - 1) % 7, 192:216]
    q10, q50, q90 = DARQSTGModel(parameters, _adjacency(links)).predict(
        base, week, previous, mask, recent, recent_base, scats[192:216],
    )
    contract = causal_sample_contract(target, (target.fromordinal(target.toordinal() - 7), target.fromordinal(target.toordinal() - 1)))
    graph = load_road_graph_authority(LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED)
    bundle = DayAheadTrafficForecastBundle(
        contract.forecast_day,
        contract.issue_time,
        contract.max_input_timestamp,
        contract.target_timestamps,
        links,
        q10,
        q50,
        q90,
        MODEL_ID,
        parameters.model_sha,
        DATA_SHA,
        graph.route_graph_sha,
        hashlib.sha256(NORMALIZATION_ID.encode()).hexdigest(),
        True,
        0,
    )
    if bundle.model_sha != authority["model_sha"]:
        raise RuntimeError("V34_TRAFFIC_MODEL_AUTHORITY_CHANGED")
    return bundle, calibration


def build_april_route_table(repo: Path, day: str):
    bundle, calibration = forecast_april_day(repo, day)
    graph = load_road_graph_authority(LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED)
    margins = {slot: calibration.margin_for_departure_slot(slot) for slot in range(96)}
    adapter = Mobility15MinAdapter(graph, bundle.to_link_forecast(), safe_eta_margin_sec_by_slot=margins)
    return bundle, graph, build_mobility_route_table(adapter, range(96))


def actual_sumo_authority(day: str, link_ids: tuple[str, ...]) -> SumoActualAuthority:
    reject_may(day)
    target = date.fromisoformat(day)
    index = {value: position for position, value in enumerate(link_ids)}
    realized, _ = _load_day(target, index)
    path = TRAFFIC_DATA / f"year={target.year}" / f"date={day}" / "link_tt_5min_24h.parquet"
    return SumoActualAuthority(link_ids, realized, _sha_file(path))


def authority_contract(repo: Path, day: str) -> dict[str, object]:
    bundle, calibration = forecast_april_day(repo, day)
    return {
        "day": day,
        "issue_time": bundle.issue_time.isoformat(),
        "max_input_timestamp": bundle.max_input_timestamp.isoformat(),
        "shape": [288, 509, 3],
        "bundle_sha256": bundle.canonical_sha256,
        "model_sha256": bundle.model_sha,
        "graph_sha256": bundle.graph_sha,
        "safe_eta": asdict(calibration),
        "D_DAY_SCATS_ACTUAL_FEATURE_READS": 0,
        "D_DAY_SUMO_FEATURE_READS": 0,
        "POST_ISSUE_ACTUAL_REFRESH_CALLS": 0,
    }
