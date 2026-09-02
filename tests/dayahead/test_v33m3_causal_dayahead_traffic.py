from __future__ import annotations

from datetime import date, datetime, timedelta
import json

import numpy as np
import pytest

from dayahead.v33m import Mobility15MinAdapter, RoadGraphAuthority, RoadLink
from dayahead.v33m.mess_trajectory import PlannedMoveCommitment
from dayahead.v33m3 import (
    CausalityLedger,
    DARQSTGModel,
    DARQSTGParameters,
    DayAheadTrafficForecastBundle,
    RouteSafeEtaCalibration,
    SumoActualAuthority,
    causal_sample_contract,
    replay_committed_move,
)
from dayahead.v33m3.causality import CausalityError
from dayahead.v33m3.dataset import FIXED_AEST


def arrays(value=100.0):
    return np.full((288, 509), value, dtype=np.float32)


def sample():
    return causal_sample_contract(date(2024, 3, 15), (date(2023, 3, 17), date(2024, 3, 8)))


def model_prediction():
    model = DARQSTGModel(DARQSTGParameters(), np.eye(509, dtype=np.float32))
    mask = np.zeros(288, dtype=bool)
    mask[:216] = True
    return model.predict(arrays(100), arrays(110), arrays(90), mask)


def bundle():
    contract = sample()
    q10, q50, q90 = model_prediction()
    return DayAheadTrafficForecastBundle(
        contract.forecast_day, contract.issue_time, contract.max_input_timestamp,
        contract.target_timestamps, tuple(f"L{i:03d}" for i in range(509)),
        q10, q50, q90, "model", "m" * 64, "d" * 64, "g" * 64,
        "n" * 64, True, 0,
    )


def actual_case(actual_seconds=200.0):
    graph = RoadGraphAuthority(
        (RoadLink("AB", "A", "B", 1.0), RoadLink("BC", "B", "C", 1.0)),
        {"S1": "A", "S2": "C"}, "graph",
    )
    move = PlannedMoveCommitment(
        "MESS01", "S1", "S2", ("AB", "BC"), 4, 200.0, 250.0,
        300.0, 6, 3.0,
    )
    authority = SumoActualAuthority(("AB", "BC"), np.full((288, 2), actual_seconds), "actual")
    ledger = CausalityLedger(sample().issue_time)
    freeze = ledger.freeze("payload")
    return graph, move, authority, ledger, freeze


# DATASET / CAUSALITY 1-8
def test_01_issue_time_is_d_minus_one_1800():
    assert sample().issue_time == datetime(2024, 3, 14, 18, tzinfo=FIXED_AEST)


def test_02_max_input_timestamp_is_not_after_issue():
    assert sample().max_input_timestamp <= sample().issue_time


def test_03_dday_actual_scats_feature_read_fails_and_counts():
    ledger = CausalityLedger(sample().issue_time)
    with pytest.raises(CausalityError):
        ledger.record_feature_read(sample().target_start, "SCATS_ACTUAL")
    assert ledger.dday_actual_scats_feature_reads == 1


def test_04_dday_sumo_feature_read_fails_and_counts():
    ledger = CausalityLedger(sample().issue_time)
    with pytest.raises(CausalityError):
        ledger.record_feature_read(sample().target_start, "SUMO_REALIZED")
    assert ledger.dday_sumo_realized_feature_reads == 1


def test_05_target_axis_has_288_steps():
    assert len(sample().target_timestamps) == 288


def test_06_model_axis_is_exactly_509_links():
    assert model_prediction()[1].shape == (288, 509)


def test_07_source_days_must_precede_forecast_day():
    with pytest.raises(ValueError, match="source days"):
        causal_sample_contract(date(2024, 3, 15), (date(2024, 3, 15),))


def test_08_contract_encodes_date_order_not_random_rows():
    s = sample()
    assert tuple(sorted(s.source_days_used)) == s.source_days_used
    assert max(s.source_days_used) < s.forecast_day


# MODEL 9-13
def test_09_quantile_outputs_are_finite():
    assert all(np.isfinite(value).all() for value in model_prediction())


def test_10_travel_time_outputs_are_positive():
    assert all(np.all(value > 0) for value in model_prediction())


def test_11_quantile_heads_are_structurally_ordered():
    q10, q50, q90 = model_prediction()
    assert np.all(q10 <= q50) and np.all(q50 <= q90)


def test_12_output_is_direct_288_step_tensor():
    assert DARQSTGModel(DARQSTGParameters()).direct_output_shape() == (288, 509, 3)


def test_13_rolling_actual_assimilation_is_prohibited():
    ledger = CausalityLedger(sample().issue_time)
    with pytest.raises(CausalityError, match="rolling"):
        ledger.record_rolling_assimilation()


# BUNDLE 14-17
def test_14_bundle_has_exact_schema_fields():
    required = {"forecast_day", "issue_time", "max_input_timestamp", "target_timestamps", "link_ids", "q10_sec", "q50_sec", "q90_sec", "model_id", "model_sha", "data_sha", "graph_sha", "normalization_sha", "causality_pass", "future_actual_read_count"}
    assert required.issubset(bundle().__dict__)


def test_15_bundle_rejects_inexact_shape():
    b = bundle()
    with pytest.raises(ValueError, match="shape"):
        DayAheadTrafficForecastBundle(**{**b.__dict__, "q50_sec": np.ones((287, 509))})


def test_16_bundle_sha_is_deterministic():
    assert bundle().canonical_sha256 == bundle().canonical_sha256


def test_17_bundle_rejects_future_actual_counter():
    b = bundle()
    with pytest.raises(ValueError, match="causality"):
        DayAheadTrafficForecastBundle(**{**b.__dict__, "future_actual_read_count": 1})


# ROUTING 18-20
def test_18_q50_dijkstra_consumes_bundle_model_output():
    graph = RoadGraphAuthority((RoadLink("L000", "A", "B", 1.0),), {"A": "A", "B": "B"}, "g")
    b = bundle()
    # Narrow the strict bundle only at the already-tested V33M interface boundary.
    forecast = b.to_link_forecast()
    graph509 = RoadGraphAuthority(tuple(RoadLink(link, "A", "B", 1.0) for link in forecast.link_ids), {"A": "A", "B": "B"}, "g")
    route = Mobility15MinAdapter(graph509, forecast).route(0, "A", "B")
    assert route.route_q50_eta_sec == pytest.approx(float(b.q50_sec[0, 0]))


def test_19_dijkstra_is_deterministic_for_identical_forecast():
    b = bundle().to_link_forecast()
    graph = RoadGraphAuthority(tuple(RoadLink(link, "A", "B", 1.0) for link in b.link_ids), {"A": "A", "B": "B"}, "g")
    adapter = Mobility15MinAdapter(graph, b)
    assert adapter.route(0, "A", "B").route_link_ids == adapter.route(0, "A", "B").route_link_ids


def test_20_safe_eta_calibration_is_oof_only():
    calibration = RouteSafeEtaCalibration.fit(([1, 2], [2, 3], [3, 4], [4, 5]))
    assert calibration.fit_namespace == "BLOCKED_OOF_ONLY"


# ACTUAL 21-28
def test_21_actual_route_is_the_frozen_route():
    graph, move, authority, ledger, freeze = actual_case()
    result = replay_committed_move(move, authority, graph, ledger, freeze, battery_capacity_kwh=100)
    assert result.route_link_ids == move.route_link_ids


def test_22_actual_destination_is_frozen():
    graph, move, authority, ledger, freeze = actual_case()
    result = replay_committed_move(move, authority, graph, ledger, freeze, battery_capacity_kwh=100)
    assert result.destination_service_id == move.destination_service_id


def test_23_actual_namespace_cannot_open_before_freeze():
    ledger = CausalityLedger(sample().issue_time)
    with pytest.raises(CausalityError, match="before Day-Ahead freeze"):
        ledger.open_actual_namespace(None)


def test_24_realized_eta_changes_connection_ready_slot():
    graph, move, authority, ledger, freeze = actual_case(1000.0)
    result = replay_committed_move(move, authority, graph, ledger, freeze, battery_capacity_kwh=100)
    assert result.actual_connection_ready_slot != result.planned_connection_ready_slot


def test_25_realized_eta_changes_physics_energy():
    graph, move, authority, ledger, freeze = actual_case(1000.0)
    result = replay_committed_move(move, authority, graph, ledger, freeze, battery_capacity_kwh=100)
    assert result.actual_energy_kwh != result.planned_energy_kwh


def test_26_actual_replay_never_reroutes():
    graph, move, authority, ledger, freeze = actual_case()
    replay_committed_move(move, authority, graph, ledger, freeze, battery_capacity_kwh=100)
    assert ledger.actual_reroute_calls == ledger.actual_route_change_count == 0


def test_27_actual_replay_never_calls_mess_optimizer():
    graph, move, authority, ledger, freeze = actual_case()
    replay_committed_move(move, authority, graph, ledger, freeze, battery_capacity_kwh=100)
    assert ledger.actual_mess_optimizer_calls == 0


def test_28_actual_replay_never_substitutes_vehicle():
    graph, move, authority, ledger, freeze = actual_case()
    result = replay_committed_move(move, authority, graph, ledger, freeze, battery_capacity_kwh=100)
    assert result.mess_id == move.mess_id
