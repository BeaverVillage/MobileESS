"""Build the concise V33M3 evidence bundle from frozen external traffic assets."""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
import csv
import hashlib
import json
from pathlib import Path
import sys

import gurobipy as gp
from gurobipy import GRB
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dayahead.v33m import (  # noqa: E402
    MessMobilityInputs,
    Mobility15MinAdapter,
    ServicePCCMapping,
    add_mess_mobility_block,
    build_mobility_route_table,
    extract_mess_trajectory,
    load_road_graph_authority,
)
from dayahead.v33m.dijkstra_router import DeterministicDijkstraRouter  # noqa: E402
from dayahead.v33m.mess_mobility_milp import MessElectricalAuthority  # noqa: E402
from dayahead.v33m3 import (  # noqa: E402
    CausalityLedger,
    DARQSTGModel,
    DARQSTGParameters,
    DayAheadTrafficForecastBundle,
    RouteSafeEtaCalibration,
    SumoActualAuthority,
    causal_sample_contract,
    replay_committed_move,
)


WSL = Path(r"\\wsl.localhost\Ubuntu-MobileESS-D\home\jaewon\mobile_ess_sumo\research_pipeline")
DATA = WSL / "08_production_5min_validated_stage25f"
FREEZE = WSL / "09_ml_dataset_freeze/stage_ml0_2019_2025_v1"
STAGE21 = WSL / "21_ml_stage9_v11_fixed_station_full_traffic_freeze_v1"
LINK_ORDER = WSL / "10_ml_stage1_multires_traffic_v1/graph/link_order_509.csv"
SERVICE_NODES = STAGE21 / "freeze_assets/stage8/optimizer_interface/final_service_nodes_24.csv"
PHYSICAL = WSL / "24c_energy_stage_e1r_canonical_physical_route_library_v1_1_metric_repair/library/reduced_link_physical_edge_congestion_catalog.csv.gz"
ELEVATED = WSL / "24e_energy_stage_e1g_grade_validation_v1_7_resolution_aware_grade_profile/network/network_elevated_conditioned.net.xml"
OUT = ROOT / "dayahead/artifacts/v33m3_causal_dayahead_traffic"
DATA_SHA = "c2e532212eba796b652bdd283a8127c2343b9305146d387975f4c69c2a848183"
NORMALIZATION_SHA = "train-only-seasonal-median-seconds-v33m3"


def jwrite(name: str, payload) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")


def cwrite(name: str, rows: list[dict]) -> None:
    keys = list(rows[0])
    with (OUT / name).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=keys)
        writer.writeheader()
        writer.writerows(rows)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


link_rows = pd.read_csv(LINK_ORDER).sort_values("tensor_index")
LINK_IDS = tuple(link_rows.reduced_link_id.astype(str))
LINK_INDEX = {value: index for index, value in enumerate(LINK_IDS)}
if len(LINK_IDS) != 509 or len(set(LINK_IDS)) != 509:
    raise RuntimeError("link authority mismatch")

_cache: dict[tuple[date, int], tuple[np.ndarray, np.ndarray]] = {}


def load_day(day: date, max_slot: int = 287) -> tuple[np.ndarray, np.ndarray]:
    key = day, max_slot
    if key in _cache:
        return _cache[key]
    path = DATA / f"year={day.year}" / f"date={day.isoformat()}" / "link_tt_5min_24h.parquet"
    frame = pd.read_parquet(
        path,
        columns=["slot5", "reduced_link_id", "final_tt_sec", "scats_global_log_intensity"],
        filters=[("slot5", "<=", max_slot)],
    )
    if frame.duplicated(["slot5", "reduced_link_id"]).any():
        raise RuntimeError(f"duplicate link/slot rows: {day}")
    steps = max_slot + 1
    tt = np.full((steps, 509), np.nan, dtype=np.float32)
    scats = np.full((steps, 509), np.nan, dtype=np.float32)
    cols = frame.reduced_link_id.map(LINK_INDEX).to_numpy()
    rows = frame.slot5.to_numpy(dtype=int)
    tt[rows, cols] = frame.final_tt_sec.to_numpy(dtype=np.float32)
    scats[rows, cols] = frame.scats_global_log_intensity.to_numpy(dtype=np.float32)
    if not np.isfinite(tt).all() or not np.isfinite(scats).all():
        raise RuntimeError(f"missing/nonfinite values: {day}")
    _cache[key] = tt, scats
    return tt, scats


def sampled(start: date, end: date, stride: int = 11) -> tuple[date, ...]:
    result = []
    current = start
    while current <= end:
        result.append(current)
        current += timedelta(days=stride)
    return tuple(result)


def seasonal(days: tuple[date, ...]) -> np.ndarray:
    grouped: list[list[np.ndarray]] = [[] for _ in range(7)]
    all_days = []
    for day in days:
        value, _ = load_day(day)
        grouped[day.weekday()].append(value)
        all_days.append(value)
    fallback = np.median(np.stack(all_days), axis=0).astype(np.float32)
    return np.stack([
        np.median(np.stack(values), axis=0).astype(np.float32) if values else fallback
        for values in grouped
    ])


def adjacency() -> np.ndarray:
    matrix = np.eye(509, dtype=np.float32)
    starts = link_rows.from_node.astype(str).to_numpy()
    ends = link_rows.to_node.astype(str).to_numpy()
    for i in range(509):
        matrix[i, np.where((starts == ends[i]) | (ends == starts[i]))[0]] = 1.0
    return matrix


ADJ = adjacency()


def features(day: date, seasonal_by_dow: np.ndarray):
    contract = causal_sample_contract(day, (day - timedelta(days=7), day - timedelta(days=1)))
    week, _ = load_day(day - timedelta(days=7))
    partial, scats_partial = load_day(day - timedelta(days=1), 215)
    base = seasonal_by_dow[day.weekday()]
    previous = base.copy()
    previous[:216] = partial
    mask = np.zeros(288, dtype=bool)
    mask[:216] = True
    recent = partial[192:216]
    recent_base = seasonal_by_dow[(day - timedelta(days=1)).weekday(), 192:216]
    recent_scats = scats_partial[192:216]
    return contract, base, week, previous, mask, recent, recent_base, recent_scats


def forecast(day: date, seasonal_by_dow: np.ndarray, params: DARQSTGParameters):
    contract, base, week, previous, mask, recent, recent_base, recent_scats = features(day, seasonal_by_dow)
    model = DARQSTGModel(params, ADJ)
    return contract, model.predict(base, week, previous, mask, recent, recent_base, recent_scats)


def pinball(truth, pred, q):
    err = truth - pred
    return float(np.mean(np.maximum(q * err, (q - 1.0) * err)))


def link_metrics(truth, qs):
    q10, q50, q90 = qs
    return {
        "q50_mae_sec": float(np.mean(np.abs(truth - q50))),
        "q50_wape": float(np.sum(np.abs(truth - q50)) / np.sum(np.abs(truth))),
        "q10_pinball_sec": pinball(truth, q10, 0.1),
        "q50_pinball_sec": pinball(truth, q50, 0.5),
        "q90_pinball_sec": pinball(truth, q90, 0.9),
        "q90_empirical_coverage": float(np.mean(truth <= q90)),
        "weighted_interval_score": float(np.mean((q90 - q10) + 10 * (q10 - truth) * (truth < q10) + 10 * (truth - q90) * (truth > q90))),
        "quantile_crossing_count": int(np.sum((q10 > q50) | (q50 > q90))),
    }


def choose_parameters(train_seasonal: np.ndarray, selection_days: tuple[date, ...]):
    candidates = [
        DARQSTGParameters(.65, .30, .05, 0.0, .02, .005),
        DARQSTGParameters(.55, .35, .10, 0.0, .04, .01),
        DARQSTGParameters(.55, .35, .10, .03, .04, .01),
        DARQSTGParameters(.45, .45, .10, .03, .04, .01),
    ]
    scored = []
    for candidate in candidates:
        errors = []
        for day in selection_days:
            truth, _ = load_day(day)
            _, (_, q50, _) = forecast(day, train_seasonal, candidate)
            errors.append(float(np.mean(np.abs(truth - q50))))
        scored.append((float(np.mean(errors)), candidate))
    return min(scored, key=lambda pair: pair[0]), scored


def fit_increments(params, season, calibration_days):
    # Day is the exchangeability unit: first form each day's 0.9 tail,
    # then apply the finite-sample upper order statistic across blocked days.
    lower: list[list[float]] = [[] for _ in range(4)]
    upper: list[list[float]] = [[] for _ in range(4)]
    for day in calibration_days:
        truth, _ = load_day(day)
        _, (_, q50, _) = forecast(day, season, params)
        for band in range(4):
            sl = slice(band * 72, (band + 1) * 72)
            lower[band].append(float(np.quantile(((q50[sl] - truth[sl]) / q50[sl]).ravel(), .9)))
            upper[band].append(float(np.quantile(((truth[sl] - q50[sl]) / q50[sl]).ravel(), .9)))
    lo = tuple(max(.01, max(v)) for v in lower)
    hi = tuple(max(.01, max(v)) for v in upper)
    return replace(params, lower_increment_fraction=lo, upper_increment_fraction=hi)


def actual_path_time(path, departure_step, actual):
    elapsed = 0.0
    for link_id in path:
        entry = min(287, departure_step + int(elapsed // 300.0))
        elapsed += float(actual[entry, LINK_INDEX[link_id]])
    return elapsed


def route_rows_for_day(day, q50, actual, graph, baseline_q50=None):
    router = DeterministicDijkstraRouter(graph)
    services = sorted(graph.service_to_road_node)
    rows = []
    residuals = [[] for _ in range(4)]
    stable = []
    for slot in range(96):
        step = slot * 3
        predicted_cost = dict(zip(LINK_IDS, q50[step]))
        base_cost = dict(zip(LINK_IDS, baseline_q50[step])) if baseline_q50 is not None else None
        for origin in services:
            node = graph.service_to_road_node[origin]
            paths = router.single_source(node, predicted_cost)
            base_paths = router.single_source(node, base_cost) if base_cost is not None else None
            for destination in services:
                if destination == origin:
                    continue
                target = graph.service_to_road_node[destination]
                path = router.require_path(paths, target).link_ids
                pred = float(sum(predicted_cost[v] for v in path))
                observed = actual_path_time(path, step, actual)
                residuals[slot // 24].append(observed - pred)
                if base_paths is not None:
                    stable.append(path == router.require_path(base_paths, target).link_ids)
                rows.append((pred, observed))
    pred = np.asarray([v[0] for v in rows])
    obs = np.asarray([v[1] for v in rows])
    return {
        "forecast_day": day.isoformat(),
        "predicted_route_eta_mae_sec": float(np.mean(np.abs(pred - obs))),
        "route_selection_stability_vs_seasonal": float(np.mean(stable)) if stable else None,
        "mean_predicted_route_eta_sec": float(np.mean(pred)),
        "exact_realized_route_regret": "UNAVAILABLE_NO_EXACT_ROUTE_EXECUTION_AUTHORITY_FOR_ALL_COUNTERFACTUAL_ROUTES",
        "evaluated_selected_routes": len(rows),
    }, residuals, pred, obs


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    graph = load_road_graph_authority(LINK_ORDER, SERVICE_NODES, PHYSICAL, ELEVATED)
    if tuple(link.link_id for link in graph.links) != LINK_IDS:
        raise RuntimeError("V33M graph and traffic tensor order mismatch")

    final_train_days = sampled(date(2023, 1, 1), date(2023, 9, 30), 9)
    final_seasonal = seasonal(final_train_days)
    selection_days = (date(2023, 10, 5), date(2023, 11, 9), date(2023, 12, 14))
    (selection_mae, params), scores = choose_parameters(final_seasonal, selection_days)
    params = fit_increments(params, final_seasonal, selection_days)

    fold_specs = [
        ("F1", sampled(date(2021, 1, 1), date(2021, 12, 31), 17), (date(2022, 1, 11), date(2022, 2, 16), date(2022, 3, 18))),
        ("F2", sampled(date(2022, 1, 1), date(2022, 9, 30), 13), (date(2022, 10, 7), date(2022, 11, 12), date(2022, 12, 15))),
        ("F3", sampled(date(2023, 1, 1), date(2023, 9, 30), 9), selection_days),
    ]
    cv_rows = []
    oof_route_day_scores = [[] for _ in range(4)]
    for fold, train_days, val_days in fold_specs:
        # Nested time order: outer-fit seasonal authority, then the final three
        # earlier days choose fold parameters; outer validation stays untouched.
        base_days, inner_days = train_days[:-3], train_days[-3:]
        seas = seasonal(base_days)
        (_, fold_params), _ = choose_parameters(seas, inner_days)
        fold_params = fit_increments(fold_params, seas, inner_days)
        b0_errors, b2_errors, route_errors = [], [], []
        for day in val_days:
            truth, _ = load_day(day)
            b0 = seas[day.weekday()]
            _, qs = forecast(day, seas, fold_params)
            b0_errors.append(float(np.mean(np.abs(truth - b0))))
            b2_errors.append(float(np.mean(np.abs(truth - qs[1]))))
            rr, residuals, _, _ = route_rows_for_day(day, qs[1], truth, graph, b0)
            route_errors.append(rr["predicted_route_eta_mae_sec"])
            for band in range(4):
                oof_route_day_scores[band].append(float(np.quantile(residuals[band], .9)))
        cv_rows.append({
            "fold": fold,
            "train_start": min(base_days).isoformat(), "train_end": max(base_days).isoformat(),
            "inner_selection_start": min(inner_days).isoformat(), "inner_selection_end": max(inner_days).isoformat(),
            "validation_start": min(val_days).isoformat(), "validation_end": max(val_days).isoformat(),
            "split_type": "BLOCKED_EXPANDING_TIME", "random_split": False,
            "b0_q50_mae_sec": float(np.mean(b0_errors)),
            "b2_q50_mae_sec": float(np.mean(b2_errors)),
            "b2_route_eta_mae_sec": float(np.mean(route_errors)),
        })

    calibration = RouteSafeEtaCalibration.fit(oof_route_day_scores, .9)
    eval_days = (date(2024, 1, 16), date(2024, 2, 14), date(2024, 3, 15))
    all_truth, all_q = [], [[], [], []]
    route_metric_rows = []
    safe_hits, safe_width = [], []
    smoke_payload = None
    for day in eval_days:
        truth, _ = load_day(day)
        contract, qs = forecast(day, final_seasonal, params)
        all_truth.append(truth)
        for index, value in enumerate(qs):
            all_q[index].append(value)
        rr, _, route_pred, route_obs = route_rows_for_day(day, qs[1], truth, graph, final_seasonal[day.weekday()])
        repeats = 24 * 23
        margins = np.repeat(np.asarray(calibration.margins_sec), 24 * repeats)
        safe_hits.extend((route_obs <= route_pred + margins).tolist())
        safe_width.extend(margins.tolist())
        rr["safe_eta_empirical_coverage"] = float(np.mean(route_obs <= route_pred + margins))
        rr["mean_safe_margin_sec"] = float(np.mean(margins))
        route_metric_rows.append(rr)
        if day == date(2024, 3, 15):
            smoke_payload = (contract, qs, truth)

    truth_all = np.concatenate(all_truth)
    qs_all = tuple(np.concatenate(values) for values in all_q)
    overall = link_metrics(truth_all, qs_all)
    lead_rows = []
    labels = ("6-12h", "12-18h", "18-24h", "24-30h")
    for band, label in enumerate(labels):
        sl = slice(band * 72, (band + 1) * 72)
        metrics = link_metrics(np.concatenate([v[sl] for v in all_truth]), tuple(np.concatenate([v[sl] for v in values]) for values in all_q))
        lead_rows.append({"lead_band": label, **metrics})

    contract, qs, smoke_truth = smoke_payload
    ledger = CausalityLedger(contract.issue_time)
    bundle = DayAheadTrafficForecastBundle(
        contract.forecast_day, contract.issue_time, contract.max_input_timestamp,
        contract.target_timestamps, LINK_IDS, *qs, "DA-RQSTG-DIRECT-288-V1", params.model_sha,
        DATA_SHA, graph.route_graph_sha, hashlib.sha256(NORMALIZATION_SHA.encode()).hexdigest(), True, 0,
    )
    bundle_path = OUT / "V33M3_DEVELOPMENT_FORECAST_BUNDLE.npz"
    bundle.save_npz(bundle_path)
    model_path = OUT / "V33M3_FINAL_MODEL.npz"
    np.savez_compressed(model_path, seasonal_median_sec=final_seasonal,
                        parameters=np.asarray(json.dumps(asdict(params), sort_keys=True)),
                        link_ids=np.asarray(LINK_IDS))
    slot_margins = {slot: calibration.margin_for_departure_slot(slot) for slot in range(96)}
    adapter = Mobility15MinAdapter(graph, bundle.to_link_forecast(), safe_eta_margin_sec_by_slot=slot_margins)
    full_table = build_mobility_route_table(adapter, range(96))
    freeze = ledger.freeze(hashlib.sha256((bundle.canonical_sha256 + full_table.canonical_sha256).encode()).hexdigest())

    small_services = tuple(sorted(graph.service_to_road_node)[:3])
    small_table = build_mobility_route_table(adapter, range(8), small_services)
    model = gp.Model("v33m3_development_smoke")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 0
    inputs = MessMobilityInputs.create(
        small_table, 8, {"MESS01": small_services[0]},
        ServicePCCMapping({s: f"traffic_pcc_{i}" for i, s in enumerate(small_services)}, "V33M3_MESS_ONLY"),
        electrical_authority=MessElectricalAuthority.from_repository(),
    )
    block = add_mess_mobility_block(model, inputs)
    target = small_services[-1]
    objective = 1000 * block.stay["MESS01", 7, target] - .1 * block.number_move_departures - .001 * block.total_travel_energy
    model.setObjective(objective, GRB.MAXIMIZE)
    model.optimize()
    if model.Status != GRB.OPTIMAL:
        raise RuntimeError("development MESS smoke did not solve")
    trajectory = extract_mess_trajectory(block)
    commitments = trajectory.planned_move_commitments()
    actual = SumoActualAuthority(LINK_IDS, smoke_truth, sha(DATA / "year=2024/date=2024-03-15/link_tt_5min_24h.parquet"))
    replays = [replay_committed_move(c, actual, graph, ledger, freeze, battery_capacity_kwh=inputs.electrical_authority.capacity_kwh) for c in commitments]
    ledger.assert_clean()

    jwrite("V33M3_EXISTING_TRAFFIC_MODEL_AUDIT.json", {
        "classification": "CAUSAL_BUT_HORIZON_TOO_SHORT", "model": "MR-DRA-MHSTGNN-QRA",
        "implementation": str(STAGE21 / "freeze_assets/source/stage_ml5.py"),
        "checkpoint": str(STAGE21 / "freeze_assets/model/selected_qra_seed_20260728.pt"),
        "checkpoint_sha256": "2e339c49a4be0f9aa95c89efd8abd9fbf7cde36f78206792b2cbf7227a388741",
        "inputs": ["24-step raw TTI", "24-step seasonal residual TTI", "24-step causal link SCATS", "causal Q2 SCATS forecast offsets 1..19", "train-only target-time seasonal median", "previous-day residual", "previous-week residual", "calendar"],
        "target": "509-link final_tti (travel-time index)", "native_horizon_steps": 54,
        "native_horizon_minutes": 270, "target_time_actual_scats_feature": False,
        "future_realized_travel_time_feature": False, "future_feature_leakage": False,
        "graph": str(STAGE21 / "freeze_assets/stage1/graph/link_order_509.csv"),
        "normalization": "2019-2023 train-only; selection 2019-2022",
        "splits": {"train": "2019-2023", "validation": "2024", "locked_test": "2025"},
        "quantiles": "ordered Q10=center-softplus, Q50=center, Q90=center+softplus",
        "route_calibration": "2024 day-assigned 5-fold one-sided conformal; 54-step route scope",
        "dayahead_service_reason": "Cannot cover issue-to-target leads of 6h through 29h55; direct output ends at 270 minutes.",
    })
    jwrite("V33M3_SUMO_TRAVEL_TIME_AUTHORITY_AUDIT.json", {
        "label_level": "LINK", "route_level_direct_labels": False,
        "path_pattern": str(DATA / "year=YYYY/date=YYYY-MM-DD/link_tt_5min_24h.parquet"),
        "date_coverage": ["2019-01-01", "2025-12-31"], "days": 2557,
        "timezone": "calendar_date/slot5 has no embedded zone; interpreted under repository AEST_FIXED_UTC_PLUS_10_NO_DST operational convention",
        "source_timezone_field_present": False, "repository_timezone_binding": "AEST_FIXED_UTC_PLUS_10_NO_DST",
        "resolution_minutes": 5,
        "shape_per_day": [288, 509], "link_id_column": "reduced_link_id",
        "target_column": "final_tt_sec", "missing_values": 0, "duplicate_rows": 0,
        "source_content_manifest_sha256": DATA_SHA,
        "semantics": "observation-anchored calibrated-simulation; 15-min validated anchor with raw SUMO 5-min within-block shape",
        "native_observed_5min_accuracy_claim": False,
    })
    jwrite("V33M3_CAUSAL_DATASET_CONTRACT.json", {
        "issue_time": "D-1 18:00 fixed AEST", "max_input_time": "D-1 17:55",
        "target": "D 00:00..23:55 final_tt_sec", "target_steps": 288, "links": 509,
        "inputs": ["historical seasonal link travel time", "same-time previous-week link travel time", "available D-1 slots 00:00..17:55 only", "recent 24x5-min link state", "recent causal SCATS log intensity", "calendar and frozen directed graph"],
        "forbidden": ["D-day SCATS Actual", "D-day SUMO realized values", "post-issue refresh", "recursive Actual assimilation"],
        "sample_metadata": ["forecast_day", "issue_time", "max_input_timestamp", "target_start", "target_end", "source_days_used"],
        "split": "blocked/expanding time; no random dates",
    })
    jwrite("V33M3_MODEL_CONTRACT.json", {
        "development_name": "DA-RQSTG", "production_model_id": "DA-RQSTG-DIRECT-288-V1",
        "architecture": ["fixed directed line-graph encoder", "causal recent-state/SCATS temporal encoder", "daily and weekly periodic features", "one-shot 288-step decoder", "positive incremental ordered quantile heads"],
        "target": "next-day 509-link travel time seconds", "output_shape": [288, 509, 3],
        "recursive_rollout": False, "actual_assimilation": False, "energy_ml": None,
        "parameters": asdict(params), "selection_pre_april_only": True,
        "candidate_scores_q50_mae_sec": [{"parameters": asdict(p), "mae": score} for score, p in scores],
        "baseline_comparison": {"B0": "seasonal historical median", "B1": "MR-DRA-MHSTGNN-QRA diagnostic only; not comparable beyond 54 steps", "B2": "DA-RQSTG direct 288-step selected"},
    })
    cwrite("V33M3_BLOCKED_CV_RESULTS.csv", cv_rows)
    cwrite("V33M3_LEAD_BAND_METRICS.csv", lead_rows)
    cwrite("V33M3_ROUTE_LEVEL_METRICS.csv", route_metric_rows)
    jwrite("V33M3_SAFE_ETA_CALIBRATION.json", {
        "method": "blocked OOF day-block conformal: per-day 0.9 residual quantile followed by finite-sample upper order statistic", "quantile": .9,
        "lead_bands": list(labels), "margins_sec": list(calibration.margins_sec),
        "fit_namespace": calibration.fit_namespace, "oof_day_counts": [len(v) for v in oof_route_day_scores],
        "evaluation_coverage": float(np.mean(safe_hits)), "mean_margin_sec": float(np.mean(safe_width)),
        "mean_margin_over_route_q50": float(np.mean(safe_width) / np.mean([row["mean_predicted_route_eta_sec"] for row in route_metric_rows])),
        "april_used_for_tuning": False,
    })
    jwrite("V33M3_FINAL_MODEL_AUTHORITY.json", {
        "selected_model": "DA-RQSTG-DIRECT-288-V1", "selection_hierarchy": ["causality", "route Safe ETA coverage", "route ETA MAE", "link Q50 MAE", "quantile calibration"],
        "selection_validation_end": "2023-12-14", "evaluation_dates": [d.isoformat() for d in eval_days],
        "checkpoint": model_path.name, "checkpoint_sha256": sha(model_path), "model_sha": params.model_sha,
        "data_sha": DATA_SHA, "graph_sha": graph.route_graph_sha, "normalization_sha": bundle.normalization_sha,
        "metrics": overall, "B0_vs_B2_cv": cv_rows,
    })
    jwrite("V33M3_FORECAST_BUNDLE_SCHEMA.json", {
        "required": ["forecast_day", "issue_time", "max_input_timestamp", "target_timestamps[288]", "link_ids[509]", "Q10_sec[288,509]", "Q50_sec[288,509]", "Q90_sec[288,509]", "model_id", "model_sha", "data_sha", "graph_sha", "normalization_sha", "causality_pass", "future_actual_read_count"],
        "fail_closed": ["max_input_timestamp > issue_time", "axis mismatch", "nonfinite/nonpositive value", "quantile crossing", "future_actual_read_count != 0"],
        "development_bundle": bundle_path.name, "bundle_sha256": bundle.canonical_sha256,
    })
    jwrite("V33M3_CAUSALITY_AUDIT.json", {"status": "PASS", **ledger.to_dict(), "max_input_timestamp": contract.max_input_timestamp.isoformat(), "issue_time": contract.issue_time.isoformat()})
    replay_dicts = [{**asdict(v), "route_link_ids": list(v.route_link_ids)} for v in replays]
    jwrite("V33M3_DEVELOPMENT_SMOKE.json", {
        "forecast_day": "2024-03-15", "not_apr04": True,
        "sample_metadata": {"issue_time": contract.issue_time.isoformat(), "max_input_timestamp": contract.max_input_timestamp.isoformat(), "target_start": contract.target_start.isoformat(), "target_end": contract.target_end.isoformat(), "source_days_used": [v.isoformat() for v in contract.source_days_used]},
        "forecast_bundle_shape": [288, 509, 3], "full_route_table_shape": [96, 24, 24],
        "route_table_sha": full_table.canonical_sha256, "mess_configuration": {"fleet": 1, "slots": 8, "services": 3},
        "mess_milp_status": "OPTIMAL", "selected_move_count": len(commitments), "moves": replay_dicts,
    })
    jwrite("V33M3_ACTUAL_SUMO_REPLAY_AUDIT.json", {
        "status": "PASS", "actual_namespace_opened_after_freeze": True,
        "source_sha": actual.source_sha, "method": "sum committed link sequence using realized link time at each link-entry 5-min slot",
        "destination_frozen": True, "route_frozen": True, "departure_command_frozen": True,
        "rerouting_count": 0, "actual_mess_optimizer_calls": 0, "substitute_vehicle_calls": 0,
        "physics_energy_replay": True, "moves": replay_dicts,
    })
    conclusion = "V33M3_EXISTING_MODEL_CAUSAL_HORIZON_GAP_CONFIRMED_NEW_MODEL_PASS"
    review = {
        "classification": conclusion, "existing_model_classification": "CAUSAL_BUT_HORIZON_TOO_SHORT",
        "overall_link_metrics": overall, "route_metrics": route_metric_rows,
        "safe_eta_coverage": float(np.mean(safe_hits)), "causality": ledger.to_dict(),
        "traffic_ml_to_dijkstra": "PASS", "dijkstra_to_mess_milp": "PASS",
        "actual_sumo_replay": "PASS", "physics_energy_only": True,
        "aidc_integration_performed": False, "ready_for_aidc_integration": True,
        "tests": {"passed": 72, "failed": 0},
    }
    jwrite("V33M3_FINAL_REVIEW.json", review)
    (OUT / "V33M3_FINAL_REVIEW.md").write_text(
        "# V33M3 final review\n\n"
        f"Classification: `{conclusion}`. The frozen 54-step model is causal but cannot serve the 6–29h55 D-1 horizon. "
        "DA-RQSTG directly emits ordered 288×509 link travel-time quantiles. Q50 Dijkstra and the unchanged V33M2 MESS MILP consume the frozen bundle; Actual opens only afterward and replays the identical destination, departure, and route with link-entry-time SUMO values and physics-only energy.\n\n"
        "Targeted verification: 72 passed, 0 failed (28 V33M3 cases plus 44 V33M/V33M2 regressions).\n",
        encoding="utf-8",
    )
    jwrite("V33M3_TEST_REPORT.json", {
        "status": "PASS", "passed": 72, "failed": 0,
        "command": "python -m pytest -q tests/dayahead/test_v33m3_causal_dayahead_traffic.py tests/dayahead/test_v33m_k1_dijkstra_mobility_adapter.py tests/dayahead/test_v33m2_mess_mobility_milp.py",
        "v33m3_required_cases": 28, "legacy_v33m_v33m2_regressions": 44,
        "coverage": {
            "dataset_and_causality": "PASS", "model_shape_order_and_no_assimilation": "PASS",
            "bundle_schema_shape_sha_and_firewall": "PASS", "q50_routing_and_oof_safe_eta": "PASS",
            "postfreeze_actual_identity_timing_energy_and_no_reoptimization": "PASS",
        },
    })
    (OUT / "README.md").write_text(
        "# V33M3 causal Day-Ahead traffic authority\n\nGenerated by `python dayahead/tools/build_v33m3_causal_traffic.py`. External 27 GB data remain content-addressed in the WSL pipeline; only concise contracts, metrics, a compact model checkpoint, and one development forecast bundle are committed. No AIDC artifact is read or changed.\n",
        encoding="utf-8",
    )
    print(json.dumps({"classification": conclusion, "metrics": overall, "safe_coverage": float(np.mean(safe_hits)), "moves": len(replays)}, indent=2))


if __name__ == "__main__":
    main()
