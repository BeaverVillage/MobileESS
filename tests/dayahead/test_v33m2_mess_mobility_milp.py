from __future__ import annotations

from dataclasses import replace
import importlib
import math
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB
import pytest

from dayahead.v33m import (
    LinkTravelTimeForecast,
    MessElectricalAuthority,
    MessMobilityInputs,
    Mobility15MinAdapter,
    RoadGraphAuthority,
    RoadLink,
    ServicePCCMapping,
    add_mess_mobility_block,
    build_mobility_route_table,
    extract_mess_trajectory,
)
from dayahead.v33m.contracts import MobilityContractError
from dayahead.v33m.mess_mobility_milp import END_OF_HORIZON_MOVE_RULE
from dayahead.v33m.mobility_physics_adapter import PhysicsMobilityEnergyAdapter


SERVICES = ("A", "B", "C")


def _adapter(
    horizon: int = 8,
    *,
    q10_sec: float = 300.0,
    q50_sec: float = 360.0,
    q90_sec: float = 480.0,
) -> Mobility15MinAdapter:
    links = tuple(
        RoadLink(f"L_{origin}_{destination}", origin, destination, 1.0, 3.0, 2.0)
        for origin in SERVICES
        for destination in SERVICES
        if origin != destination
    )
    graph = RoadGraphAuthority(
        links,
        {service: service for service in SERVICES},
        "synthetic-graph-sha",
    )
    steps = 3 * (horizon - 1) + 1
    width = len(links)
    forecast = LinkTravelTimeForecast.from_arrays(
        tuple(link.link_id for link in links),
        [[q10_sec] * width] * steps,
        [[q50_sec] * width] * steps,
        [[q90_sec] * width] * steps,
        "synthetic-traffic-sha",
    )
    return Mobility15MinAdapter(graph, forecast)


def _build_case(
    horizon: int = 8,
    *,
    q10_sec: float = 300.0,
    q50_sec: float = 360.0,
    q90_sec: float = 480.0,
    authority: MessElectricalAuthority | None = None,
    initial_energy: float | None = None,
):
    adapter = _adapter(
        horizon, q10_sec=q10_sec, q50_sec=q50_sec, q90_sec=q90_sec
    )
    table = build_mobility_route_table(adapter, range(horizon))
    authority = authority or MessElectricalAuthority.from_repository()
    model = gp.Model("v33m2_test")
    model.Params.OutputFlag = 0
    model.Params.Threads = 1
    model.Params.Seed = 0
    model.Params.MIPGap = 0.0
    inputs = MessMobilityInputs.create(
        table,
        horizon,
        {"MESS01": "A"},
        ServicePCCMapping({service: f"pcc_{service.lower()}" for service in SERVICES}, "synthetic"),
        electrical_authority=authority,
        initial_energy_by_mess=(
            None if initial_energy is None else {"MESS01": initial_energy}
        ),
    )
    return model, add_mess_mobility_block(model, inputs)


def _solve_synthetic_smoke():
    model, block = _build_case()
    throughput = gp.quicksum(block.p_discharge.values()) + gp.quicksum(block.p_charge.values())
    timed_throughput = gp.quicksum(
        (key[1] + 1) * variable for key, variable in block.p_discharge.items()
    ) + gp.quicksum(
        (key[1] + 1) * variable for key, variable in block.p_charge.items()
    )
    objective = (
        10000.0 * block.stay["MESS01", 0, "A"]
        + 10000.0 * block.stay["MESS01", 1, "A"]
        + 10.0 * block.p_injection_by_service_slot["C", 4]
        + block.q_injection_by_service_slot["C", 4]
        - 0.1 * block.number_move_departures
        - 0.001 * block.total_travel_energy
        - 1e-7 * throughput
        - 1e-9 * timed_throughput
    )
    model.setObjective(objective, GRB.MAXIMIZE)
    model.optimize()
    assert model.Status == GRB.OPTIMAL
    return model, block, extract_mess_trajectory(block)


@pytest.fixture(scope="module")
def synthetic_smoke():
    return _solve_synthetic_smoke()


def test_q10_q50_q90_order_is_required():
    with pytest.raises(MobilityContractError, match="Q10 <= Q50 <= Q90"):
        LinkTravelTimeForecast.from_arrays(("L",), [[2.0]], [[1.0]], [[3.0]])


def test_dijkstra_still_uses_q50_only_and_sums_all_quantiles_on_same_path():
    graph = RoadGraphAuthority(
        (
            RoadLink("DIRECT", "A", "B", 1.0),
            RoadLink("VIA1", "A", "C", 1.0),
            RoadLink("VIA2", "C", "B", 1.0),
        ),
        {"A": "A", "B": "B"},
        "sha",
    )
    forecast = LinkTravelTimeForecast.from_arrays(
        ("DIRECT", "VIA1", "VIA2"),
        [[1.0, 2.0, 2.0]],
        [[10.0, 3.0, 4.0]],
        [[10.0, 5.0, 6.0]],
    )
    route = Mobility15MinAdapter(graph, forecast).route(0, "A", "B")
    assert route.route_link_ids == ("VIA1", "VIA2")
    assert (route.route_q10_eta_sec, route.route_q50_eta_sec, route.route_q90_eta_sec) == (
        4.0, 7.0, 11.0
    )


def test_safe_energy_is_max_of_physics_at_q10_q50_q90():
    adapter = _adapter()
    route = adapter.route(0, "A", "B")
    physics = PhysicsMobilityEnergyAdapter()
    geometry = physics.geometry_for_path(route.route_link_ids, adapter.graph.links_by_id)
    energies = [
        physics.physics.energy_kwh(geometry.physics_mapping(), eta)
        for eta in (
            route.route_q10_eta_sec,
            route.route_q50_eta_sec,
            route.route_q90_eta_sec,
        )
    ]
    assert route.energy_nominal_kwh == pytest.approx(energies[1])
    assert route.energy_safe_kwh == pytest.approx(max(energies))


def test_route_table_uses_one_single_source_per_slot_origin_and_hashes(monkeypatch):
    adapter = _adapter(horizon=3)
    calls = 0
    original = adapter.router.single_source

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(adapter.router, "single_source", counted)
    first = build_mobility_route_table(adapter, range(3))
    second = build_mobility_route_table(_adapter(horizon=3), range(3))
    assert calls == 3 * len(SERVICES)
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    assert first.canonical_sha256 == second.canonical_sha256


def test_core_block_leaves_objective_ownership_to_parent_and_exposes_tiebreaks():
    model, block = _build_case(horizon=3)
    assert model.getObjective().size() == 0
    assert block.total_travel_energy.size() > 0
    assert block.number_move_departures.size() > 0
    assert block.total_unavailable_slots.size() > 0
    assert block.deterministic_move_ordinal.size() > 0


def test_service_and_pcc_injection_interfaces_are_identical_for_one_to_one_map():
    model, block = _build_case(horizon=3)
    model.addConstr(block.p_injection_by_service_slot["A", 0] == 25.0)
    model.addConstr(block.q_injection_by_service_slot["A", 0] == 10.0)
    model.optimize()
    assert model.Status == GRB.OPTIMAL
    assert block.p_injection_by_pcc_slot["pcc_a", 0].getValue() == pytest.approx(25.0)
    assert block.q_injection_by_pcc_slot["pcc_a", 0].getValue() == pytest.approx(10.0)


def test_synthetic_smoke_selects_stay_move_destination_and_departure(synthetic_smoke):
    _, _, trajectory = synthetic_smoke
    by_slot = {row.slot: row for row in trajectory.slots}
    assert by_slot[0].mode == by_slot[1].mode == "CONNECTED"
    assert by_slot[0].service_id == by_slot[1].service_id == "A"
    assert by_slot[2].mode == "TRANSIT"
    assert by_slot[2].origin_service_id == "A"
    assert by_slot[2].destination_service_id == "C"
    assert by_slot[2].departure_slot == 2
    assert by_slot[3].mode == "CONNECTION_DELAY"
    assert by_slot[4].mode == "CONNECTED" and by_slot[4].service_id == "C"


def test_single_flow_no_teleport_or_double_departure(synthetic_smoke):
    _, _, trajectory = synthetic_smoke
    assert len(trajectory.slots) == 8
    assert len(trajectory.planned_move_commitments()) == 1
    unavailable = [row for row in trajectory.slots if row.mode != "CONNECTED"]
    assert [row.slot for row in unavailable] == [2, 3]
    assert all(row.service_id is None for row in unavailable)


def test_one_slot_travel_and_connection_delay_are_distinct(synthetic_smoke):
    _, _, trajectory = synthetic_smoke
    move = trajectory.planned_move_commitments()[0]
    assert trajectory.slots[2].travel_slots_15min == 1
    assert move.planned_connection_ready_slot == 4
    assert trajectory.slots[2].mode == "TRANSIT"
    assert trajectory.slots[3].mode == "CONNECTION_DELAY"


def test_multi_slot_travel_has_no_early_arrival():
    model, block = _build_case(horizon=4, q10_sec=800.0, q50_sec=900.0, q90_sec=1000.0)
    model.addConstr(block.move["MESS01", 0, "A", "B"] == 1)
    model.optimize()
    assert model.Status == GRB.OPTIMAL
    trajectory = extract_mess_trajectory(block)
    assert [trajectory.slots[index].mode for index in (0, 1)] == ["TRANSIT", "TRANSIT"]
    assert trajectory.slots[2].mode == "CONNECTED"
    assert trajectory.slots[2].service_id == "B"


def test_end_of_horizon_moves_are_not_created():
    _, block = _build_case(horizon=3)
    assert END_OF_HORIZON_MOVE_RULE == "READY_ARRIVAL_MUST_BE_WITHIN_MODELED_HORIZON"
    assert all(
        slot + route.connection_ready_slots_15min <= 3
        for (_, slot, _, _), route in block.move_route.items()
    )
    assert not any(key[1] == 2 for key in block.move)


def test_transit_and_connection_delay_force_p_q_zero(synthetic_smoke):
    _, _, trajectory = synthetic_smoke
    for row in trajectory.slots:
        if row.mode in {"TRANSIT", "CONNECTION_DELAY"}:
            assert row.p_kw == 0.0
            assert row.q_kvar == 0.0


def test_p_and_q_are_location_gated_and_enabled_after_arrival(synthetic_smoke):
    _, _, trajectory = synthetic_smoke
    arrival = trajectory.slots[4]
    assert arrival.service_id == "C"
    assert arrival.p_kw > 0.0
    assert arrival.q_kvar > 0.0
    assert all(
        row.p_kw == row.q_kvar == 0.0 for row in trajectory.slots if row.mode != "CONNECTED"
    )


def test_active_power_and_pcs_inner_polygon_limits(synthetic_smoke):
    _, block, trajectory = synthetic_smoke
    authority = block.inputs.electrical_authority
    for row in trajectory.slots:
        assert abs(row.p_kw) <= authority.active_power_limit_kw + 1e-7
        if row.mode == "CONNECTED":
            assert math.hypot(row.p_kw, row.q_kvar) <= authority.pcs_kva + 1e-6
            assert all(
                row.p_kw * math.cos(2 * math.pi * face / authority.pcs_polygon_faces)
                + row.q_kvar * math.sin(2 * math.pi * face / authority.pcs_polygon_faces)
                <= authority.pcs_kva * math.cos(math.pi / authority.pcs_polygon_faces) + 1e-6
                for face in range(authority.pcs_polygon_faces)
            )


def test_safe_travel_energy_is_debited_at_departure(synthetic_smoke):
    _, _, trajectory = synthetic_smoke
    departure = trajectory.slots[2]
    after_departure = trajectory.slots[3]
    assert departure.battery_energy_kwh - after_departure.battery_energy_kwh == pytest.approx(
        departure.energy_safe_kwh, abs=1e-8
    )


def test_insufficient_departure_energy_is_infeasible():
    probe = _adapter(horizon=4).route(0, "A", "B")
    authority = MessElectricalAuthority.from_repository()
    initial = authority.energy_min_kwh + probe.energy_safe_kwh - 0.1
    model, block = _build_case(horizon=4, initial_energy=initial)
    model.addConstr(block.move["MESS01", 0, "A", "B"] == 1)
    model.optimize()
    assert model.Status == GRB.INFEASIBLE


def test_charge_discharge_soc_dynamics_bounds_and_terminal(synthetic_smoke):
    _, block, _ = synthetic_smoke
    a = block.inputs.electrical_authority
    for slot in range(block.inputs.horizon_slots):
        dis = sum(block.p_discharge["MESS01", slot, service].X for service in SERVICES)
        ch = sum(block.p_charge["MESS01", slot, service].X for service in SERVICES)
        move_energy = sum(
            block.move_route[key].energy_safe_kwh * variable.X
            for key, variable in block.move.items()
            if key[0] == "MESS01" and key[1] == slot
        )
        expected = (
            block.energy["MESS01", slot].X
            + a.charge_efficiency * a.interval_hours * ch
            - a.interval_hours * dis / a.discharge_efficiency
            - move_energy
        )
        assert block.energy["MESS01", slot + 1].X == pytest.approx(expected, abs=1e-7)
        assert not (dis > 1e-7 and ch > 1e-7)
    assert all(
        a.energy_min_kwh - 1e-7 <= variable.X <= a.energy_max_kwh + 1e-7
        for variable in block.energy.values()
    )
    assert block.energy["MESS01", block.inputs.horizon_slots].X == pytest.approx(
        a.terminal_energy_kwh
    )


def test_identical_inputs_produce_identical_trajectory():
    first = _solve_synthetic_smoke()[2]
    second = _solve_synthetic_smoke()[2]
    assert first.canonical_json_bytes() == second.canonical_json_bytes()
    assert first.canonical_sha256 == second.canonical_sha256


def test_deterministic_destination_tie_break_uses_canonical_move_ordinal():
    model, block = _build_case(horizon=4)
    model.addConstr(block.number_move_departures == 1)
    model.setObjective(block.deterministic_move_ordinal, GRB.MINIMIZE)
    model.optimize()
    assert model.Status == GRB.OPTIMAL
    commitment = extract_mess_trajectory(block).planned_move_commitments()[0]
    assert commitment.departure_slot == 0
    assert commitment.destination_service_id == "B"


def test_repository_authority_values_are_reused():
    authority = MessElectricalAuthority.from_repository()
    from dayahead import mess_physics

    assert authority.capacity_kwh == mess_physics.CAPACITY_KWH
    assert authority.energy_min_kwh == mess_physics.E_MIN_KWH
    assert authority.energy_max_kwh == mess_physics.E_MAX_KWH
    assert authority.initial_energy_kwh == mess_physics.E_INITIAL_KWH
    assert authority.terminal_energy_kwh == mess_physics.E_TERMINAL_KWH
    assert authority.active_power_limit_kw == mess_physics.P_LIMIT_KW
    assert authority.pcs_kva == mess_physics.PCS_KVA
    assert authority.charge_efficiency == authority.discharge_efficiency == 0.95


def test_no_energy_ml_aidc_fresh_or_production_case_imports():
    package = Path(importlib.import_module("dayahead.v33m").__file__).parent
    source = "\n".join(path.read_text(encoding="utf-8") for path in package.glob("*.py"))
    lowered = source.lower()
    forbidden = (
        "energy_quantiles",
        "e4b_template",
        "energy residual",
        "dayahead.aidc",
        "opendss",
        "dayahead.v30",
        "dayahead.v32",
    )
    assert not [token for token in forbidden if token in lowered]
