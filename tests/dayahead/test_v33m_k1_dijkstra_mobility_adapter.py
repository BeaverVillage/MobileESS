from __future__ import annotations

from dataclasses import fields
import gzip
import importlib
import json
import math
from pathlib import Path

import pytest

from dayahead.v33m.contracts import (
    ROUTING_TIME_MODEL,
    SAFE_ETA_AUTHORITY,
    LinkTravelTimeForecast,
    MobilityContractError,
    RoadGraphAuthority,
    RoadLink,
    RouteParameters15Min,
)
from dayahead.v33m.dijkstra_router import (
    DeterministicDijkstraRouter,
    UnreachableDestinationError,
)
from dayahead.v33m.mobility_15min_adapter import (
    Mobility15MinAdapter,
    connection_ready_slots_15min,
    forecast_step_for_departure_slot,
    travel_slots_15min,
)
from dayahead.v33m.mobility_physics_adapter import (
    PhysicsMobilityEnergyAdapter,
    RouteGeometry,
)
from dayahead.v33m.road_graph_authority import load_road_graph_authority


def graph() -> RoadGraphAuthority:
    return RoadGraphAuthority(
        links=(
            RoadLink("L_DIRECT", "A", "B", 3.0, 2.0, 1.0),
            RoadLink("L_AC", "A", "C", 1.0, 1.0, 0.0),
            RoadLink("L_CB", "C", "B", 1.0, 1.0, 1.0),
            RoadLink("L_BA", "B", "A", 3.0, 0.0, 2.0),
        ),
        service_to_road_node={"IDC01": "A", "IDC02": "B", "STA01": "C"},
        route_graph_sha="graph-sha",
    )


def forecast(
    q10=(8.0, 2.0, 3.0, 7.0),
    q50=(10.0, 3.0, 4.0, 9.0),
    q90=(10.0, 5.0, 6.0, 10.0),
):
    return LinkTravelTimeForecast.from_arrays(
        ("L_DIRECT", "L_AC", "L_CB", "L_BA"),
        [q10] * 288,
        [q50] * 288,
        [q90] * 288,
        "traffic-sha",
    )


def test_q50_dijkstra_selects_lower_time_route_and_k1_only():
    adapter = Mobility15MinAdapter(graph(), forecast())
    route = adapter.route(0, "IDC01", "IDC02")
    assert route.route_link_ids == ("L_AC", "L_CB")
    assert "k" not in {field.name.lower() for field in fields(RouteParameters15Min)}
    assert "rank" not in {field.name.lower() for field in fields(RouteParameters15Min)}


def test_equal_cost_tie_uses_lexicographic_link_sequence_then_nodes():
    tied = RoadGraphAuthority(
        (
            RoadLink("z_direct", "A", "D", 1.0),
            RoadLink("a_first", "A", "B", 1.0),
            RoadLink("a_second", "B", "D", 1.0),
        ),
        {"O": "A", "D": "D"},
        "sha",
    )
    path = DeterministicDijkstraRouter(tied).single_source(
        "A", {"z_direct": 2.0, "a_first": 1.0, "a_second": 1.0}
    )["D"]
    assert path.link_ids == ("a_first", "a_second")


@pytest.mark.parametrize("invalid", [0.0, -1.0, math.inf, math.nan])
def test_all_dijkstra_edge_costs_must_be_positive_finite(invalid):
    costs = {link.link_id: 1.0 for link in graph().links}
    costs["L_DIRECT"] = invalid
    with pytest.raises(MobilityContractError, match="finite and positive"):
        DeterministicDijkstraRouter(graph()).single_source("A", costs)


def test_unreachable_destination_fails_explicitly():
    disconnected = RoadGraphAuthority(
        (RoadLink("AB", "A", "B", 1.0), RoadLink("CD", "C", "D", 1.0)),
        {"O": "A", "D": "D"},
        "sha",
    )
    forecast_disconnected = LinkTravelTimeForecast.from_arrays(
        ("AB", "CD"), [[1.0, 1.0]], [[1.0, 1.0]], [[1.0, 1.0]]
    )
    adapter = Mobility15MinAdapter(disconnected, forecast_disconnected)
    with pytest.raises(UnreachableDestinationError, match="unreachable"):
        adapter.route(0, "O", "D")


def test_q50_and_q90_sum_same_selected_path():
    route = Mobility15MinAdapter(graph(), forecast()).route(7, "IDC01", "IDC02")
    assert route.route_q10_eta_sec == 2.0 + 3.0
    assert route.route_q50_eta_sec == 3.0 + 4.0
    assert route.route_q90_eta_sec == 5.0 + 6.0
    assert SAFE_ETA_AUTHORITY == "DEVELOPMENT_Q90_ONLY_PENDING_CALIBRATION_AUDIT"
    assert ROUTING_TIME_MODEL == "DEPARTURE_EPOCH_STATIC_FORECAST_SNAPSHOT"


def test_15_minute_slot_maps_to_corresponding_5_minute_snapshot():
    rows50 = [(100.0, 100.0, 100.0, 100.0)] * 288
    rows90 = [(110.0, 110.0, 110.0, 110.0)] * 288
    rows10 = [(90.0, 90.0, 90.0, 90.0)] * 288
    rows10[15] = (18.0, 1.0, 2.0, 8.0)
    rows50[15] = (20.0, 2.0, 3.0, 10.0)
    rows90[15] = (30.0, 4.0, 5.0, 12.0)
    route = Mobility15MinAdapter(
        graph(),
        LinkTravelTimeForecast.from_arrays(
            ("L_DIRECT", "L_AC", "L_CB", "L_BA"), rows10, rows50, rows90
        ),
    ).route(5, "IDC01", "IDC02")
    assert forecast_step_for_departure_slot(5) == 15
    assert route.route_link_ids == ("L_AC", "L_CB")
    assert route.route_q50_eta_sec == 5.0


def test_routes_for_origin_runs_one_single_source_search(monkeypatch):
    adapter = Mobility15MinAdapter(graph(), forecast())
    calls = 0
    original = adapter.router.single_source

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(adapter.router, "single_source", counted)
    routes = adapter.routes_for_origin(0, "IDC01")
    assert calls == 1
    assert {route.destination_service_id for route in routes} == {
        "IDC01", "IDC02", "STA01"
    }


def test_stay_is_canonical_zero_option():
    stay = Mobility15MinAdapter(graph(), forecast()).stay(9, "IDC01")
    assert stay.origin_service_id == stay.destination_service_id == "IDC01"
    assert stay.road_origin_node == stay.road_destination_node == "A"
    assert stay.route_link_ids == ()
    assert stay.route_q10_eta_sec == stay.route_q50_eta_sec == stay.route_q90_eta_sec == 0.0
    assert stay.travel_slots_15min == stay.connection_ready_slots_15min == 0
    assert stay.energy_nominal_kwh == stay.energy_safe_kwh == 0.0


@pytest.mark.parametrize(
    ("eta", "travel", "ready"),
    [
        (1.0, 1, 1),
        (900.0, 1, 2),
        (901.0, 2, 2),
        (4 * 60.0, 1, 1),
        (8 * 60.0, 1, 2),
        (20 * 60.0, 2, 2),
    ],
)
def test_travel_and_combined_connection_slot_ceils(eta, travel, ready):
    assert travel_slots_15min(eta) == travel
    assert connection_ready_slots_15min(eta) == ready


def test_formula_energy_is_positive_and_safe_is_max_of_q50_q90():
    nominal, safe = PhysicsMobilityEnergyAdapter().route_energy_kwh(
        RouteGeometry(10.0, 20.0, 10.0), 600.0, 900.0, 1200.0
    )
    assert nominal > 0.0
    assert safe >= nominal


def test_longer_eta_changes_auxiliary_energy_by_frozen_power_rule():
    physics = PhysicsMobilityEnergyAdapter().physics
    geometry = RouteGeometry(10.0, 0.0, 0.0).physics_mapping()
    short = physics.energy_components_kwh(geometry, 600.0)
    long = physics.energy_components_kwh(geometry, 1200.0)
    assert long["auxiliary_kwh"] - short["auxiliary_kwh"] == pytest.approx(5.0 / 6.0)
    assert long["aerodynamic_kwh"] < short["aerodynamic_kwh"]


def test_ascent_increases_energy_and_descent_regeneration_reduces_it():
    physics = PhysicsMobilityEnergyAdapter().physics
    flat = physics.energy_kwh(RouteGeometry(10.0, 0.0, 0.0).physics_mapping(), 900.0)
    uphill = physics.energy_kwh(RouteGeometry(10.0, 10.0, 0.0).physics_mapping(), 900.0)
    descent = physics.energy_kwh(RouteGeometry(10.0, 0.0, 10.0).physics_mapping(), 900.0)
    assert uphill > flat > descent
    components = physics.energy_components_kwh(
        RouteGeometry(10.0, 0.0, 10.0).physics_mapping(), 900.0
    )
    assert components["grade_kwh"] < 0.0


def test_no_energy_ml_fresh_opendss_or_aidc_imports():
    package = Path(importlib.import_module("dayahead.v33m").__file__).parent
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    lowered = source.lower()
    assert "energy_quantiles" not in lowered
    assert "e4b_template" not in lowered
    assert "energy residual" not in lowered
    assert "opendss" not in lowered
    assert "dayahead.aidc" not in lowered


def test_route_serialization_is_byte_deterministic():
    adapter = Mobility15MinAdapter(graph(), forecast())
    first = adapter.route(0, "IDC01", "IDC02")
    second = adapter.route(0, "IDC01", "IDC02")
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    assert json.loads(first.canonical_json_bytes())["route_link_ids"] == ["L_AC", "L_CB"]


def test_loader_binds_adjacency_service_mapping_distance_and_elevation(tmp_path):
    link_order = tmp_path / "link_order.csv"
    link_order.write_text(
        "tensor_index,reduced_link_id,from_node,to_node\n0,RL_01_02_01,1,2\n",
        encoding="utf-8",
    )
    services = tmp_path / "services.csv"
    services.write_text(
        "service_id,traffic_node\nIDC01,TN_01\nSTA01,TN_02\n", encoding="utf-8"
    )
    catalog = tmp_path / "physical.csv.gz"
    with gzip.open(catalog, "wt", encoding="utf-8", newline="") as handle:
        handle.write("reduced_link_id,source_position,edge_id,length_m\n")
        handle.write("RL_01_02_01,0,E1,1000\n")
    network = tmp_path / "elevated.net.xml"
    network.write_text(
        '<net><edge id="E1" from="n1" to="n2">'
        '<lane id="E1_0" length="1000" shape="0,0,10 500,0,20 1000,0,15"/>'
        "</edge></net>",
        encoding="utf-8",
    )
    authority = load_road_graph_authority(
        link_order, services, catalog, network,
        expected_link_count=1, expected_service_count=2,
    )
    assert authority.node_count == 2
    assert authority.link_count == 1
    assert dict(authority.service_to_road_node) == {"IDC01": "TN_01", "STA01": "TN_02"}
    assert authority.links[0].distance_km == 1.0
    assert authority.links[0].cumulative_ascent_m == 10.0
    assert authority.links[0].cumulative_descent_m == 5.0
    assert len(authority.route_graph_sha) == 64
