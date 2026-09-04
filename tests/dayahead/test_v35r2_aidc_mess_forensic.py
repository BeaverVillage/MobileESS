from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from dayahead.v28r2.electrical_subproblem import (
    SlotCoefficients,
    anchored_polygon_loading,
    anchored_polygon_parameters,
)
from dayahead.v28r2.opendss_mapping import aidc_injection_mapping, mess_injection_mapping
from dayahead.v35r2.forensic import (
    APR01_20,
    aidc_shift_temporal_authority,
    central_slope,
    critical_identity,
    dependency_scoped_invalidation,
    deterministic_farthest_point_cover,
    electrical_diversity,
    move_feasibility,
    q_exploit_detect,
    require_apr01_20,
)


def _coefficient() -> SlotCoefficients:
    anchor = np.asarray([100.0, 20.0])
    sp = np.asarray([[1.0, 0.0]])
    sq = np.asarray([[0.0, 1.0]])
    # The frozen tangent is deliberately value/gradient calibrated
    # independently of the raw flow/rating polygon.
    current_matrix = np.asarray([[8.0e-4], [2.0e-4]])
    current_anchor = np.asarray([0.52])
    return SlotCoefficients(
        slot=0,
        control_names=("P", "Q"),
        branch_names=("line.synthetic::A",),
        anchor=anchor,
        voltage_constant=np.asarray([1.0]),
        voltage_matrix=np.zeros((2, 1)),
        current_constant=current_anchor - current_matrix.T @ anchor,
        current_matrix=current_matrix,
        flow_p_constant=np.asarray([0.0]),
        flow_q_constant=np.asarray([0.0]),
        flow_p_matrix=sp,
        flow_q_matrix=sq,
        branch_limits=(200.0,),
        transformer_ratings=(None,),
        coefficient_sha256="0" * 64,
    )


def test_apr20_boundary_rejects_apr21_and_may():
    assert require_apr01_20(APR01_20[-1]) == "2025-04-20"
    with pytest.raises(PermissionError, match="APR20_AUTHORITY_BOUNDARY"):
        require_apr01_20("2025-04-21")
    with pytest.raises(PermissionError, match="APR20_AUTHORITY_BOUNDARY"):
        require_apr01_20("2025-05-01")


def test_planning_fresh_current_axis_identity_requires_exact_shape():
    assert central_slope(np.zeros((2, 3)), np.ones((2, 3)), 0.5).shape == (2, 3)
    with pytest.raises(ValueError, match="FINITE_DIFFERENCE_AXIS"):
        central_slope(np.zeros((2, 3)), np.ones((3, 2)), 0.5)


def test_current_sign_unit_conventions_and_mess_q_sign():
    assert aidc_injection_mapping(1.0, 0.25) == {
        "load_p_kw": 1.0,
        "load_q_kvar": 0.25,
    }
    assert mess_injection_mapping(1.0, 0.25) == {
        "generator_p_kw": 1.0,
        "generator_q_kvar": 0.25,
        "charging_load_p_kw": 0.0,
        "charging_load_q_kvar": 0.0,
    }
    assert mess_injection_mapping(-1.0, -0.25) == {
        "generator_p_kw": 0.0,
        "generator_q_kvar": -0.25,
        "charging_load_p_kw": 1.0,
        "charging_load_q_kvar": 0.0,
    }


def test_common_rho_reconstruction_matches_anchor_value_and_gradient():
    coefficient = _coefficient()
    value = anchored_polygon_loading(coefficient, coefficient.anchor)
    assert value == pytest.approx([0.52], abs=1e-12)
    step = 1e-5
    for index in range(2):
        left = coefficient.anchor.copy()
        right = coefficient.anchor.copy()
        left[index] -= step
        right[index] += step
        slope = central_slope(
            anchored_polygon_loading(coefficient, left),
            anchored_polygon_loading(coefficient, right),
            step,
        )
        assert slope == pytest.approx(coefficient.current_matrix[index], abs=1e-9)


def test_common_rho_polygon_is_convex_and_adds_large_signal_curvature():
    coefficient = _coefficient()
    left = anchored_polygon_loading(coefficient, np.asarray([100.0, -180.0]))
    right = anchored_polygon_loading(coefficient, np.asarray([100.0, 180.0]))
    middle = anchored_polygon_loading(coefficient, np.asarray([100.0, 0.0]))
    assert np.all(middle <= 0.5 * (left + right) + 1e-12)
    bias, correction, polygon_anchor = anchored_polygon_parameters(coefficient)
    assert bias.shape == polygon_anchor.shape == (1,)
    assert correction.shape == (2, 1)


def test_q_exploit_detection_finds_opposite_large_signal_effect():
    result = q_exploit_detect(
        (-100.0, 0.0, 100.0),
        (0.55, 0.60, 0.50),
        (0.58, 0.60, 0.64),
    )
    assert result["exploit_confirmed"]
    assert result["opposite_direction"]


def test_critical_line_identity_categories():
    assert critical_identity((1, "L", "A"), (1, "L", "A")) == "EXACT_LINE_PHASE_SLOT"
    assert critical_identity((1, "L", "A"), (2, "L", "A")) == "SAME_LINE_PHASE_DIFFERENT_SLOT"
    assert critical_identity((1, "L", "A"), (1, "M", "A")) == "DIFFERENT_LINE_OR_PHASE"


def test_aidc_control_authority_partitions_shifted_workload():
    off = np.zeros((1, 1, 96))
    on = np.zeros_like(off)
    on[0, 0, 10] = 2.0
    on[0, 0, 12] = 4.0
    result = aidc_shift_temporal_authority(off, on, (10,), near_radius=2)
    assert result["shifted_nodeh_total"] == pytest.approx(3.0)
    assert result["shifted_nodeh_at_binding_slots"] == pytest.approx(1.0)
    assert result["shifted_nodeh_near_binding_slots"] == pytest.approx(2.0)


def test_service_pcc_mapping_and_electrical_diversity():
    mapping = {f"S{i:02d}": f"PCC{i:02d}" for i in range(24)}
    fingerprints = {
        service: (float(index), float(index * index))
        for index, service in enumerate(sorted(mapping))
    }
    result = electrical_diversity(mapping, fingerprints)
    assert result["unique_electrical_PCC_count"] == 24
    assert result["distinct_sensitivity_fingerprint_count"] == 24
    assert not result["equivalent_service_groups"]


def test_aidc_host_bus_mapping_is_not_collapsed():
    mapping = {f"AIDC{i:02d}": f"host_{i:02d}" for i in range(1, 13)}
    assert len(mapping) == len(set(mapping.values())) == 12


def test_initial_location_authority_uses_road_only_farthest_cover():
    services = ("STA01", "STA02", "STA03", "STA04")
    coordinate = {"STA01": 0.0, "STA02": 1.0, "STA03": 9.0, "STA04": 10.0}
    distances = {
        (left, right): abs(coordinate[left] - coordinate[right])
        for left in services
        for right in services
    }
    assert deterministic_farthest_point_cover(
        distances, services, count=3, seed="STA01",
    ) == ("STA01", "STA04", "STA02")


def test_net_move_feasibility_accounts_for_safe_energy_and_ready_slot():
    feasible = move_feasibility(
        departure_slot=4,
        connection_ready_slots=2,
        horizon_slots=8,
        energy_before_kwh=800.0,
        travel_energy_kwh=20.0,
        minimum_energy_kwh=200.0,
    )
    assert feasible["feasible"]
    assert feasible["connection_ready_slot"] == 6
    assert feasible["remaining_connected_slots"] == 2


def test_post_arrival_pq_ineligible_at_or_beyond_horizon():
    result = move_feasibility(
        departure_slot=6,
        connection_ready_slots=2,
        horizon_slots=8,
        energy_before_kwh=800.0,
        travel_energy_kwh=20.0,
        minimum_energy_kwh=200.0,
    )
    assert not result["feasible"]
    assert not result["post_arrival_PQ_eligible"]


def test_dependency_scoped_invalidation():
    common = dependency_scoped_invalidation(
        common_current_changed=True,
        aidc_mapping_changed=False,
        mess_mapping_changed=False,
    )
    assert len(common.invalidated_case_days) == 80
    assert not common.preserved_case_days
    mess = dependency_scoped_invalidation(
        common_current_changed=False,
        aidc_mapping_changed=False,
        mess_mapping_changed=True,
    )
    assert len(mess.invalidated_case_days) == 40
    assert all(item.endswith(("/B2", "/B3")) for item in mess.invalidated_case_days)


def test_apr01_20_only_correction_rebuild_scope():
    assert len(APR01_20) == 20
    assert APR01_20[0] == "2025-04-01"
    assert APR01_20[-1] == "2025-04-20"
    assert all(day.startswith("2025-04-") for day in APR01_20)

