"""April/locked-May adapter for the frozen V33M3 causal traffic authority."""

from __future__ import annotations

from datetime import date
import hashlib
from pathlib import Path
from typing import Mapping

import numpy as np
import pandas as pd

from dayahead.v33m import Mobility15MinAdapter, build_mobility_route_table, load_road_graph_authority
from dayahead.v33m3 import DARQSTGModel, DayAheadTrafficForecastBundle, SumoActualAuthority, causal_sample_contract
from dayahead.v34.traffic_authority import (
    DATA_SHA,
    ELEVATED,
    LINK_ORDER,
    MODEL_ID,
    NORMALIZATION_ID,
    PHYSICAL,
    SERVICE_NODES,
    TRAFFIC_DATA,
    _adjacency,
    _sha_file,
    load_final_authority,
)

from .contracts import APRIL_DAYS, MAY_DAYS, assert_may_access


def _load_day(day: date, link_index: Mapping[str, int], max_slot: int = 287) -> tuple[np.ndarray, np.ndarray]:
    path = TRAFFIC_DATA / f"year={day.year}" / f"date={day.isoformat()}" / "link_tt_5min_24h.parquet"
    frame = pd.read_parquet(
        path,
        columns=["slot5", "reduced_link_id", "final_tt_sec", "scats_global_log_intensity"],
        filters=[("slot5", "<=", max_slot)],
    )
    if frame.duplicated(["slot5", "reduced_link_id"]).any():
        raise RuntimeError("V35_TRAFFIC_DUPLICATE_LINK_SLOT")
    steps = max_slot + 1
    tt = np.full((steps, 509), np.nan, dtype=np.float32)
    scats = np.full((steps, 509), np.nan, dtype=np.float32)
    rows = frame.slot5.to_numpy(dtype=int)
    columns = frame.reduced_link_id.map(link_index).to_numpy(dtype=int)
    tt[rows, columns] = frame.final_tt_sec.to_numpy(dtype=np.float32)
    scats[rows, columns] = frame.scats_global_log_intensity.to_numpy(dtype=np.float32)
    if not np.isfinite(tt).all() or not np.isfinite(scats).all():
        raise RuntimeError("V35_TRAFFIC_MISSING_OR_NONFINITE")
    return tt, scats


def forecast_day(
    repo: Path,
    day: str,
    *,
    may_admission: Mapping[str, object] | None = None,
) -> tuple[DayAheadTrafficForecastBundle, object]:
    if day not in set(APRIL_DAYS + MAY_DAYS):
        raise ValueError("V35_TRAFFIC_DAY_OUTSIDE_APRIL_MAY")
    assert_may_access(day, may_admission)
    target = date.fromisoformat(day)
    seasonal, links, parameters, calibration, authority = load_final_authority(repo)
    link_index = {value: index for index, value in enumerate(links)}
    week, _ = _load_day(target.fromordinal(target.toordinal() - 7), link_index)
    partial, scats = _load_day(target.fromordinal(target.toordinal() - 1), link_index, 215)
    base = seasonal[target.weekday()]
    previous = base.copy()
    previous[:216] = partial
    mask = np.zeros(288, dtype=bool)
    mask[:216] = True
    q10, q50, q90 = DARQSTGModel(parameters, _adjacency(links)).predict(
        base,
        week,
        previous,
        mask,
        partial[192:216],
        seasonal[(target.weekday() - 1) % 7, 192:216],
        scats[192:216],
    )
    contract = causal_sample_contract(
        target,
        (target.fromordinal(target.toordinal() - 7), target.fromordinal(target.toordinal() - 1)),
    )
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
        raise RuntimeError("V35_TRAFFIC_MODEL_AUTHORITY_CHANGED")
    return bundle, calibration


def build_route_table(
    repo: Path,
    day: str,
    *,
    may_admission: Mapping[str, object] | None = None,
):
    bundle, calibration = forecast_day(repo, day, may_admission=may_admission)
    graph = load_road_graph_authority(LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED)
    margins = {slot: calibration.margin_for_departure_slot(slot) for slot in range(96)}
    adapter = Mobility15MinAdapter(graph, bundle.to_link_forecast(), safe_eta_margin_sec_by_slot=margins)
    return bundle, graph, build_mobility_route_table(adapter, range(96))


def actual_sumo_authority(
    day: str,
    link_ids: tuple[str, ...],
    *,
    may_admission: Mapping[str, object] | None = None,
) -> SumoActualAuthority:
    if day not in set(APRIL_DAYS + MAY_DAYS):
        raise ValueError("V35_ACTUAL_TRAFFIC_DAY_OUTSIDE_APRIL_MAY")
    assert_may_access(day, may_admission)
    target = date.fromisoformat(day)
    index = {value: position for position, value in enumerate(link_ids)}
    realized, _ = _load_day(target, index)
    path = TRAFFIC_DATA / f"year={target.year}" / f"date={day}" / "link_tt_5min_24h.parquet"
    return SumoActualAuthority(link_ids, realized, _sha_file(path))
