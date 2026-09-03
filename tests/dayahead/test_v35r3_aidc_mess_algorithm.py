from __future__ import annotations

import inspect
import json
from pathlib import Path

import gurobipy as gp
from gurobipy import GRB
import pytest
import numpy as np

from dayahead.v33m.grid_interface import ServicePCCMapping
from dayahead.v33m.mess_mobility_milp import MessMobilityInputs, add_mess_mobility_block
from dayahead.v33m.mess_trajectory import extract_mess_trajectory
from dayahead.v33m.mess_trajectory import MessTrajectory, MessTrajectorySlot
from dayahead.v33m.contracts import RouteParameters15Min
from dayahead.v33m.route_table import MobilityRouteTable
from dayahead.v35.execution import _combined_trajectory_arrays
from dayahead.v35r3 import algorithm
from dayahead.v34.integrated_mess import _apply_preferred_restricted_start


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "dayahead/artifacts/v35r3_aidc_mess_algorithm"


def _route(slot: int, origin: str, destination: str, *, ready: int = 1) -> RouteParameters15Min:
    self_route = origin == destination
    return RouteParameters15Min(
        departure_slot_15=slot,
        origin_service_id=origin,
        destination_service_id=destination,
        road_origin_node=origin.lower(),
        road_destination_node=destination.lower(),
        route_link_ids=() if self_route else (f"{origin}_{destination}",),
        route_distance_km=0.0 if self_route else 1.0,
        cumulative_ascent_m=0.0,
        cumulative_descent_m=0.0,
        route_q10_eta_sec=0.0 if self_route else 300.0,
        route_q50_eta_sec=0.0 if self_route else 400.0,
        route_q90_eta_sec=0.0 if self_route else 500.0,
        route_safe_eta_sec=0.0 if self_route else 500.0,
        travel_slots_15min=0 if self_route else 1,
        connection_ready_slots_15min=0 if self_route else ready,
        energy_nominal_kwh=0.0 if self_route else 1.0,
        energy_safe_kwh=0.0 if self_route else 1.0,
        route_graph_sha="g",
        traffic_forecast_sha="f",
        physics_contract_sha="p",
    )


def _table(horizon: int, *, ready: int = 1) -> MobilityRouteTable:
    services = ("A", "B")
    records = {
        (slot, origin, destination): _route(slot, origin, destination, ready=ready)
        for slot in range(horizon)
        for origin in services
        for destination in services
    }
    return MobilityRouteTable(tuple(range(horizon)), services, records)


def test_apr01_only_guard_and_fixed_windows():
    algorithm.assert_apr01_only("2025-04-01")
    for day in ("2025-04-02", "2025-04-20", "2025-04-21", "2025-05-01"):
        with pytest.raises(PermissionError, match="V35R3_APR01_ONLY"):
            algorithm.assert_apr01_only(day)
    assert algorithm.fixed_critical_windows(74) == {
        "W1": (74,), "W3": (73, 74, 75), "W5": (72, 73, 74, 75, 76),
    }


def test_candidate_pruning_is_exact_and_self_is_stay():
    table = _table(96, ready=2)
    result = algorithm.enumerate_initial_relocations(
        day="2025-04-01", mess_id="MESS01", initial_service="A", route_table=table,
    )
    assert len(result.candidates) == 96  # STAY plus departures 0..94.
    assert sum(row.is_stay for row in result.candidates) == 1
    assert result.rejected_counts == {
        "self_destination_as_STAY": 96,
        "arrival_beyond_horizon": 1,
        "unreachable_route": 0,
        "travel_energy_infeasible": 0,
        "terminal_energy_infeasible": 0,
    }
    assert all(
        row.is_stay or row.departure_slot + 2 == row.connection_ready_slot <= 96
        for row in result.candidates
    )


def test_frozen_state_flow_supports_multiple_relocations():
    table = _table(6)
    model = gp.Model("v35r3_multi_move_semantics")
    model.Params.OutputFlag = 0
    inputs = MessMobilityInputs.create(
        table, 6, {"MESS01": "A"}, ServicePCCMapping({"A": "pa", "B": "pb"}, "test"),
    )
    block = add_mess_mobility_block(model, inputs)
    model.addConstr(block.move["MESS01", 0, "A", "B"] == 1)
    model.addConstr(block.move["MESS01", 2, "B", "A"] == 1)
    model.setObjective(block.total_travel_energy, GRB.MINIMIZE)
    model.optimize()
    assert model.Status == GRB.OPTIMAL
    moves = extract_mess_trajectory(block).planned_move_commitments()
    assert [(row.origin_service_id, row.destination_service_id, row.departure_slot) for row in moves] == [
        ("A", "B", 0), ("B", "A", 2),
    ]


def test_complete_candidate_is_translated_to_exact_full_mipstart():
    table = _table(96)
    model = gp.Model("v35r3_mipstart_translation")
    model.Params.OutputFlag = 0
    inputs = MessMobilityInputs.create(
        table, 96, {"MESS01": "A"}, ServicePCCMapping({"A": "pa", "B": "pb"}, "test"),
    )
    block = add_mess_mobility_block(model, inputs)
    candidate = algorithm.enumerate_initial_relocations(
        day="2025-04-01", mess_id="MESS01", initial_service="A", route_table=table,
    ).candidates[1]
    energy = np.full(97, 760.0); energy[1:] -= 1.0
    p_charge = np.zeros(96); p_charge[1] = 1.0 / (0.95 * 0.25); energy[2:] = 760.0
    payload = {
        "candidate": candidate, "p_discharge_kw": np.zeros(96),
        "p_charge_kw": p_charge, "q_kvar": np.zeros(96), "energy_kwh": energy,
    }
    _apply_preferred_restricted_start(model, block, "MESS01", payload)
    assert block.move["MESS01", 0, "A", "B"].Start == 1.0
    assert block.stay["MESS01", 0, "A"].Start == 0.0
    assert block.stay["MESS01", 1, "B"].Start == 1.0
    assert block.p_charge["MESS01", 1, "B"].Start == pytest.approx(p_charge[1])
    assert block.energy["MESS01", 96].Start == pytest.approx(760.0)


def test_selection_module_has_no_fresh_or_actual_dependency():
    source = inspect.getsource(algorithm)
    assert "run_fresh_opendss" not in source
    assert "materialize_actual" not in source


def test_aidc_artifacts_preserve_mass_and_fixed_windows():
    windows = json.loads((ARTIFACT / "V35R3_AIDC_TEMPORAL_FLEXIBILITY_WINDOWS.json").read_text(encoding="utf-8"))
    assert windows["fixed_window_definitions"] == {
        "W1": [74], "W3": [73, 74, 75], "W5": [72, 73, 74, 75, 76],
    }
    for row in windows["results"].values():
        assert row["status"] == "OPTIMAL"
        assert abs(row["mass_conservation_error_nodeh"]) <= 1e-6
        assert row["grid_rows_in_envelope"] == row["Fresh_reads_in_envelope"] == 0
        assert row["binding_constraint_counts"]["service_balance_or_terminal"] >= 15


def test_usage_ratio_and_sw2_axes_are_complete():
    usage = json.loads((ARTIFACT / "V35R3_AIDC_PRODUCTION_USAGE_RATIO.json").read_text(encoding="utf-8"))
    assert set(usage["usage"]) == {"W1", "W3", "W5"}
    for row in usage["usage"].values():
        assert row["usage_ratio"] == pytest.approx(
            row["actual_production_downward_shift_nodeh"] / row["maximum_removable_nodeh"]
        )
    import csv
    with (ARTIFACT / "V35R3_AIDC_SITE_SW2_SENSITIVITY.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert [row["AIDC_site"] for row in rows] == [f"AIDC{index:02d}" for index in range(1, 13)]
    assert sorted(int(row["relative_sensitivity_rank_abs"]) for row in rows) == list(range(1, 13))
    assert sum(row["line_sw2_on_source_path"] == "True" for row in rows) == 5


def test_complete_mobility_scan_uses_planning_and_respects_every_better_start():
    net = json.loads((ARTIFACT / "V35R3_MESS_NET_MOBILITY_VALUE.json").read_text(encoding="utf-8"))
    audit = json.loads((ARTIFACT / "V35R3_MESS_MIPSTART_AUDIT.json").read_text(encoding="utf-8"))
    assert net["Fresh_reads_during_ranking"] == 0
    assert net["ranking_authority"] == "CURRENT_REPAIRED_PLANNING_ONLY"
    assert len(net["vehicles"]) == 8
    assert all(row["classification"] == "BENEFICIAL_MOVE_EXISTS" for row in net["vehicles"])
    assert all(row["feasible_candidate_count"] > 0 for row in net["vehicles"])
    assert all(row["NET_MOBILITY_IMPROVEMENT"] > 1e-8 for row in net["vehicles"])
    assert all(row["best_MOVE"]["exact_optimality_certificate"] == "True" for row in net["vehicles"])
    assert all(
        int(row["best_MOVE"]["connection_ready_slot"]) > int(row["best_MOVE"]["departure_slot"])
        for row in net["vehicles"]
    )
    assert all(float(row["best_MOVE"]["safe_energy_kwh"]) > 0.0 for row in net["vehicles"])
    assert all(float(row["best_MOVE"]["terminal_energy_kwh"]) >= 240.0 for row in net["vehicles"])
    assert all(float(row["best_MOVE"]["post_arrival_sum_abs_q_kvar_slots"]) > 0.0 for row in net["vehicles"])
    assert audit["forced_MOVE"] is False
    assert audit["all_better_starts_respected"] is True
    assert all(row["MIPStart_accepted"] and row["preferred_MIPStart_loaded"] for row in audit["vehicles"])
    assert all(
        float(row["full_objective"]) <= float(row["best_restricted_objective"]) + 1e-6
        for row in audit["vehicles"]
    )


def test_fresh_revalidation_is_ex_post_complete_and_residual_is_small():
    fresh = json.loads((ARTIFACT / "V35R3_APR01_FRESH_REVALIDATION.json").read_text(encoding="utf-8"))
    voltage = json.loads((ARTIFACT / "V35R3_APR01_VOLTAGE_VIOLATION_DIAGNOSTIC.json").read_text(encoding="utf-8"))
    assert fresh["Fresh_role"] == "EX_POST_ONLY"
    assert fresh["selection_Fresh_reads"] == 0
    for case in ("B2", "B3"):
        result = fresh[case]["fresh"]
        diagnostic = voltage["new_V35R3"][case]
        assert result["convergence_count"] == result["OpenDSS_solve_count"] == 96
        assert result["line_current_violation_count"] == 0
        assert result["transformer_current_violation_count"] == 0
        assert result["transformer_kva_violation_count"] == 0
        assert diagnostic["classification"] == "SMALL_PLANNING_FRESH_VOLTAGE_RESIDUAL"
        assert diagnostic["maximum_lower_exceedance_pu"] < 0.005
        assert diagnostic["maximum_upper_exceedance_pu"] == 0.0


def test_transit_slots_use_the_frozen_opendss_unavailable_location_contract():
    payload = json.loads((ARTIFACT / "V35R3_MESS_FINAL_APR01_RESULT.json").read_text(encoding="utf-8"))
    rows = []
    for source in payload["cases"]["B3"]["trajectory_slots"]:
        source = dict(source)
        source["route_link_ids"] = tuple(source["route_link_ids"])
        rows.append(MessTrajectorySlot(**source))
    trajectory = MessTrajectory(tuple(rows))
    p, q, _energy, locations, _modes = _combined_trajectory_arrays(trajectory)
    by = {(row.mess_id, row.slot): row for row in trajectory.slots}
    for column, mess_id in enumerate(("MESS01", "MESS02", "MESS03", "MESS04")):
        for slot in range(96):
            if by[mess_id, slot].service_id is None:
                assert locations[slot, column] == f"TRANSIT_ROUTE_{column + 1:02d}"
                assert p[slot, column] == q[slot, column] == 0.0
