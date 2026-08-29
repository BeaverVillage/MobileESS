import copy
import math
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from dayahead.aidc_rack_model import RackTensorShape
from dayahead.authority import CURRENT_FROZEN_DIMENSIONS, load_dimension_authority
from dayahead.benders import BendersMethod, BoundState, cuts_for_iteration, critical_times
from dayahead.grid_lp import (
    BranchPhase,
    CapacityGridLPFactory,
    FeederLPData,
    FeasibilityCut,
    GridLPSolution,
    OptimalityCut,
    PhaseAwareGridLPFactory,
    V_MAX_SQUARED,
    V_MIN_SQUARED,
    phase_mask_metrics,
    validate_squared_voltage,
    voltage_pu_from_squared,
)
from dayahead.input_contract import FIXED_AEST, InputContractError, operating_axis
from dayahead.mapping_authority import MappingAuthority
from dayahead.master import CaseName, build_master_structure
from dayahead.mess_physics import (
    E_TERMINAL_KWH,
    PCS_KVA,
    MessSlot,
    MobilityMode,
    conservative_connection_delay_slots,
    pcs_inner_polygon_satisfied,
    validate_occupancy,
    validate_trajectory,
)
from dayahead.mobility_energy_da import MobilityEnergyProfiles, assert_departure_feasible, departure_energy_required
from dayahead.opendss_qsts import assert_namespace_non_overwrite, run_qsts
from dayahead.reference_compute import build_reference_schedule
from dayahead.result_schema import ResultManifest
from dayahead.science_firewall import CURRENT_AIDC_GATE, FORBIDDEN_FALLBACK_TOKENS, reject_aidc_fallback
from dayahead.traffic_da import (
    RouteForecast,
    ScatsObservation,
    aggregate_scats_15min,
    assert_separate_namespaces,
    localize_scats_time,
)


FIXTURE = Path(__file__).parents[1] / "fixtures" / "non_scientific" / "aidc_dimensions_10x4.json"


def test_current_frozen_dimension_authority_is_exactly_12_by_48() -> None:
    assert len(CURRENT_FROZEN_DIMENSIONS.aidc_ids) == 12
    assert len(CURRENT_FROZEN_DIMENSIONS.rack_ids) == 48
    CURRENT_FROZEN_DIMENSIONS.validate(production=True)


def test_alternative_10_by_40_fixture_requires_no_source_edit() -> None:
    authority = load_dimension_authority(FIXTURE)
    assert (len(authority.aidc_ids), len(authority.rack_ids)) == (10, 40)
    shape = RackTensorShape.from_authority(authority)
    assert shape.rack_ids[-1] == "AIDC10_LP04"


def test_non_scientific_fixture_is_rejected_by_production_loader() -> None:
    with pytest.raises(ValueError, match="NON_SCIENTIFIC"):
        load_dimension_authority(FIXTURE, production=True)


def test_master_indexes_follow_runtime_authority_dimensions() -> None:
    authority = load_dimension_authority(FIXTURE)
    master = build_master_structure(CaseName.B3_JOINT_PROPOSED, authority, ("SERVICE_A",))
    assert len(master.variable_index["rack_allocation"]) == 40 * 96


def test_scientific_master_uses_refrozen_v16_authority() -> None:
    result = build_master_structure(CaseName.B0_NO_FLEXIBILITY, CURRENT_FROZEN_DIMENSIONS, ("SERVICE_A",), production=True)
    assert len(result.variable_index["rack_allocation"]) == 48 * 96


def test_reference_schedule_does_not_materialize_missing_aidc_workload() -> None:
    with pytest.raises(ValueError, match="FORECAST_COHORT"):
        build_reference_schedule(CURRENT_FROZEN_DIMENSIONS, None, production=True)


def test_traffic_roles_are_independent_and_same_node_can_hold_both() -> None:
    authority = MappingAuthority.from_mapping({
        "authority_id": "ROLE_TEST", "scientific_eligible": False,
        "nodes": [
            {"traffic_node": "N1", "latitude": -37.8, "longitude": 145.0, "scats_id": "S1", "aidc_anchor": "AIDC01", "mess_service_site": "SERVICE01"},
            {"traffic_node": "N2", "latitude": -37.9, "longitude": 145.1, "scats_id": "S2", "aidc_anchor": None, "mess_service_site": None},
        ], "route_edges": [["N1", "N2"]],
    })
    assert authority.aidc_to_traffic == {"AIDC01": "N1"}
    assert authority.service_to_traffic == {"SERVICE01": "N1"}
    assert authority.nodes[1].traffic_node == "N2"


def test_scats_dst_fall_back_fold_maps_to_two_distinct_fixed_aest_times() -> None:
    wall = datetime(2025, 4, 6, 2, 30)
    first = localize_scats_time(wall, fold=0)
    second = localize_scats_time(wall, fold=1)
    assert first.utcoffset() == second.utcoffset() == timedelta(hours=10)
    assert abs((second - first).total_seconds()) == 3600


def test_scats_dst_spring_forward_nonexistent_time_fails_closed() -> None:
    with pytest.raises(InputContractError, match="NONEXISTENT"):
        localize_scats_time(datetime(2025, 10, 5, 2, 30))


def test_scats_aggregation_is_deterministic_and_audits_duplicates() -> None:
    day = date(2025, 11, 3)
    rows = [
        ScatsObservation("S1", datetime(2025, 1, 5, 0, 1), 2.0, datetime(2025, 11, 2, 17, tzinfo=FIXED_AEST)),
        ScatsObservation("S1", datetime(2025, 1, 5, 0, 9), 4.0, datetime(2025, 11, 2, 17, tzinfo=FIXED_AEST)),
    ]
    values, audit = aggregate_scats_15min(rows, day)
    assert list(values.values()) == [3.0]
    assert audit["duplicate_rows_aggregated"] == 1


def test_route_forecast_has_ordered_96_slot_safe_interface() -> None:
    day = date(2025, 11, 3)
    forecast = RouteForecast("R1", operating_axis(day), (1.0,) * 96, (2.0,) * 96, (3.0,) * 96, (2.1,) * 96, (3.5,) * 96, (True,) * 96)
    forecast.validate(day)


def test_forecast_and_actual_namespaces_cannot_collapse() -> None:
    assert_separate_namespaces("TRAFFIC_DA_FORECAST", "TRAFFIC_DA_ACTUAL")
    with pytest.raises(InputContractError):
        assert_separate_namespaces("TRAFFIC_DA_FORECAST", "TRAFFIC_DA_FORECAST")


def test_mobility_energy_5_to_15_sum_preserves_signed_total_and_hash() -> None:
    profile = MobilityEnergyProfiles((2.0, -1.0, 3.0) * 2, (1.0, -0.5, 2.0) * 2, "SAFE_V1", "MODEL_V1", ("a" * 64,))
    safe, q50, manifest = profile.aggregate()
    assert safe == (4.0, 4.0)
    assert sum(safe) == pytest.approx(sum(profile.safe_kwh))
    assert len(manifest["aggregation_sha256"]) == 64


def test_future_regeneration_is_not_precredited_at_departure() -> None:
    assert departure_energy_required((10.0, -9.0, 5.0)) == 15.0
    with pytest.raises(InputContractError, match="NO_FUTURE_REGEN"):
        assert_departure_feasible(450.0, 440.0, (10.0, -9.0, 5.0))


def _zero_slots(last_mode=MobilityMode.CONNECTED):
    result = [MessSlot("SERVICE_A", MobilityMode.CONNECTED, 0.0, 0.0, 0.0) for _ in range(96)]
    result[-1] = MessSlot("SERVICE_B", last_mode, 0.0, 0.0, 0.0)
    return result


def test_mess_soc_recursion_and_exact_terminal_energy() -> None:
    energy = validate_trajectory(_zero_slots())
    assert len(energy) == 97 and energy[0] == energy[-1] == E_TERMINAL_KWH


def test_mess_cannot_clone_location() -> None:
    with pytest.raises(ValueError, match="TWO_PLACES"):
        validate_occupancy({("MESS01", 0): ("A", "B")})


@pytest.mark.parametrize("mode", [MobilityMode.TRANSIT, MobilityMode.CONNECTION_DELAY])
def test_transit_and_connection_delay_force_p_q_zero(mode) -> None:
    slots = _zero_slots()
    slots[4] = MessSlot("ROAD", mode, 1.0, 0.0, 0.0)
    with pytest.raises(ValueError, match="REQUIRES_P_Q_ZERO"):
        validate_trajectory(slots)


def test_connection_delay_maps_ten_minutes_to_one_slot() -> None:
    assert conservative_connection_delay_slots(10.0) == 1


def test_day_end_transit_is_forbidden_but_return_is_not_required() -> None:
    validate_trajectory(_zero_slots())
    with pytest.raises(ValueError, match="DAY_END_TRANSIT"):
        validate_trajectory(_zero_slots(MobilityMode.TRANSIT))


def test_16_face_pcs_polygon_is_strictly_inside_exact_circle() -> None:
    assert pcs_inner_polygon_satisfied(PCS_KVA * math.cos(math.pi / 16), 0.0)
    assert not pcs_inner_polygon_satisfied(PCS_KVA, 0.0)


def test_squared_voltage_bounds_and_round_trip() -> None:
    for value in (V_MIN_SQUARED, 1.0, V_MAX_SQUARED):
        validate_squared_voltage(value)
        assert voltage_pu_from_squared(value) ** 2 == pytest.approx(value)
    with pytest.raises(ValueError):
        validate_squared_voltage(0.8)


def test_absent_phases_are_excluded_from_reducers() -> None:
    values = {("L1", "A", 0): 0.8, ("L1", "B", 0): 99.0}
    metrics = phase_mask_metrics(values, {("L1", "A"): True, ("L1", "B"): False})
    assert metrics["max"] == 0.8


def test_real_gurobi_pi_produces_valid_sampled_optimality_cut() -> None:
    pytest.importorskip("gurobipy")
    factory = CapacityGridLPFactory(10)
    solution = factory.solve(0, {"y": 4.0}, 3)
    assert solution.pi_by_row["master_demand"] > 0
    for y in (0.0, 2.5, 9.5):
        exact = factory.solve(0, {"y": y}).objective
        assert solution.optimality_cut.evaluate({"y": y}) <= exact + 1e-8


def test_real_gurobi_farkas_ray_and_cut_exclude_infeasible_incumbent() -> None:
    pytest.importorskip("gurobipy")
    solution = CapacityGridLPFactory(10).solve(0, {"y": 11.0}, 4)
    assert not solution.feasible and any(abs(value) > 0 for value in solution.farkas_by_row.values())
    assert not solution.feasibility_cut.satisfied({"y": 11.0})
    assert solution.feasibility_cut.satisfied({"y": 10.0})


def test_phase_aware_lindistflow_factory_has_explicit_master_registry_and_pi_cut() -> None:
    pytest.importorskip("gurobipy")
    branch = BranchPhase("L1", "ROOT", "B1", "A", 0.0001, 0.0001, 80.0)
    data = FeederLPData(
        "ROOT", (branch,), {("ROOT", "A"): True, ("B1", "A"): True}, {("L1", "A"): True},
        {("B1", "A"): 5.0}, {("B1", "A"): 1.0}, {("L1", "A"): 100.0}, {},
        {("B1", "A"): {"mess_p": 1.0}}, {("B1", "A"): {}},
    )
    factory = PhaseAwareGridLPFactory(data)
    assert {row.row_name for row in factory.master_dependent_row_registry} == {"p_balance[B1,A]", "q_balance[B1,A]"}
    solution = factory.solve(0, {"mess_p": 1.0})
    assert solution.feasible and solution.objective >= 0
    other = factory.solve(0, {"mess_p": 2.0})
    assert solution.optimality_cut.evaluate({"mess_p": 2.0}) <= other.objective + 1e-8


def _solution(t, objective, loading, feasible=True):
    return GridLPSolution(
        t, feasible, objective if feasible else None, {}, {},
        OptimalityCut(t, objective, {}, 1) if feasible else None,
        None if feasible else FeasibilityCut(t, {"y": 1.0}, 10.0, 1),
        {("L", "A"): loading},
    )


def _solutions(infeasible=()):
    return tuple(_solution(t, float(t), 1.0 if t in (7, 8) else 0.5, t not in infeasible) for t in range(96))


def test_standard_bd_selects_only_worst_time_optimality_cut() -> None:
    cuts = cuts_for_iteration(BendersMethod.STANDARD_SINGLE_CUT, _solutions())
    assert [(cut.time_index, type(cut).__name__) for cut in cuts] == [(95, "OptimalityCut")]


def test_cl_mc_bd_selects_all_critical_times() -> None:
    assert critical_times(_solutions()) == (7, 8)
    cuts = cuts_for_iteration(BendersMethod.CL_MC_BD, _solutions())
    assert {cut.time_index for cut in cuts} == {7, 8}


def test_all_infeasible_times_receive_feasibility_cuts_regardless_of_criticality() -> None:
    cuts = cuts_for_iteration(BendersMethod.CL_MC_BD, _solutions(infeasible=(2, 7)))
    assert {cut.time_index for cut in cuts if isinstance(cut, FeasibilityCut)} == {2, 7}


def test_lb_uses_objbound_and_ub_waits_for_all_feasible() -> None:
    state = BoundState(lower_bound=1.0, upper_bound=100.0)
    state.update(master_obj_bound=5.0, master_incumbent_objective=50.0, solutions=_solutions(infeasible=(2,)))
    assert state.lower_bound == 5.0 and state.upper_bound == 100.0
    state.update(master_obj_bound=4.0, master_incumbent_objective=40.0, solutions=_solutions())
    assert state.lower_bound == 5.0 and state.upper_bound == 95.0


def test_gap_certificate_and_time_limit_status() -> None:
    state = BoundState(lower_bound=99.95, upper_bound=100.0)
    state.update(master_obj_bound=99.95, master_incumbent_objective=100.0, solutions=tuple(_solution(t, 100.0, 1.0) for t in range(96)))
    assert state.certified and state.termination_status(time_limit=True) == "OPTIMAL_CERTIFIED"
    state.lower_bound = 90.0
    state.gap = 0.1
    assert state.termination_status(time_limit=True) == "TIME_LIMIT_NOT_CERTIFIED"


class _FakeDSS:
    def __init__(self): self.closed = False
    def load_clean_ieee123(self): pass
    def solve_slot(self, slot, record):
        return {"line_current_a": {("L1", "A"): 80.0, ("L1", "B"): 9999.0}, "voltage_pu": {("B1", "A"): 1.0, ("B1", "B"): 99.0}, "transformer_loading_pu": {("TX", "A"): 0.7}}
    def close(self): self.closed = True


def test_opendss_96_slot_interface_masks_phases_and_keeps_schedule_immutable() -> None:
    schedule = tuple({"slot": index, "p": 0.0} for index in range(96))
    frozen_copy = copy.deepcopy(schedule)
    result = run_qsts(_FakeDSS, schedule, {("L1", "A"): 100.0}, {("L1", "A"): True, ("L1", "B"): False}, {("B1", "A"): True, ("B1", "B"): False}, namespace="FORECAST_PLANNING")
    assert schedule == frozen_copy and result.metrics["rho_max_AC"] == 0.8


def test_opendss_forecast_realized_namespace_cannot_overwrite() -> None:
    with pytest.raises(FileExistsError):
        assert_namespace_non_overwrite({"FORECAST_PLANNING": {}}, "FORECAST_PLANNING")


def test_result_manifest_production_rejects_fixture_dimensions() -> None:
    fixture = load_dimension_authority(FIXTURE)
    manifest = ResultManifest("RESULT_TEST", ("SOURCE",), ("a" * 64,), "DA15_96STEP_TIME_CONTRACT_V1", fixture.to_dict(), "FORECAST_PLANNING", False)
    with pytest.raises(ValueError, match="NON_SCIENTIFIC"):
        manifest.validate(production=True)


def test_current_aidc_gate_accepts_v16_refrozen_authority_without_fallback() -> None:
    status = CURRENT_AIDC_GATE.status()
    assert status["status"] == "PASS"
    assert status["unresolved"] == []
    assert status["synthetic_fallback_used"] is False


@pytest.mark.parametrize("strategy", FORBIDDEN_FALLBACK_TOKENS)
def test_every_forbidden_aidc_synthetic_or_imputation_fallback_is_rejected(strategy) -> None:
    with pytest.raises(RuntimeError, match="WAITING_AIDC_AUTHORITY"):
        reject_aidc_fallback(strategy)
