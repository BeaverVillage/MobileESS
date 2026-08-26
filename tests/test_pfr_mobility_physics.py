from __future__ import annotations

import ast
from pathlib import Path

import pytest

from pfr.mobility_physics import MobilityPhysics


REPO = Path(__file__).resolve().parents[1]
CONTRACT = REPO / "pfr/contracts/MESS_MOBILITY_PHYSICS_V1.json"


def test_frozen_vehicle_coefficients_reproduce_physics_bridge() -> None:
    physics = MobilityPhysics.from_contract(CONTRACT)
    flat_one_km = {
        "route_distance_km": 1.0,
        "cumulative_ascent_m": 0.0,
        "cumulative_descent_m": 0.0,
    }
    uphill_one_m = {
        "route_distance_km": 1.0,
        "cumulative_ascent_m": 1.0,
        "cumulative_descent_m": 0.0,
    }
    downhill_one_m = {
        "route_distance_km": 1.0,
        "cumulative_ascent_m": 0.0,
        "cumulative_descent_m": 1.0,
    }

    flat = physics.energy_components_kwh(flat_one_km, 1e9)
    uphill = physics.energy_components_kwh(uphill_one_m, 1e9)
    downhill = physics.energy_components_kwh(downhill_one_m, 1e9)

    assert flat["rolling_kwh"] == pytest.approx(0.5932417901234568)
    assert uphill["grade_kwh"] == pytest.approx(0.08474882716049384)
    assert downhill["grade_kwh"] == pytest.approx(-0.04576436666666667)


def test_safe_energy_is_worst_physics_value_across_eta_quantiles() -> None:
    physics = MobilityPhysics.from_contract(CONTRACT)
    route = {
        "route_distance_km": 50.0,
        "cumulative_ascent_m": 100.0,
        "cumulative_descent_m": 80.0,
    }
    eta = (2400.0, 3000.0, 4200.0)

    q50, safe = physics.forecast_energy_kwh(route, eta)
    expected = [physics.energy_kwh(route, value) for value in eta]

    assert q50 == expected[1]
    assert safe == max(expected)


def test_runtime_cannot_read_legacy_energy_or_e4_arrays() -> None:
    source = (REPO / "pfr/tools/run_pfr_matrix.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden = {
        "energy_quantiles_kWh",
        "safe_energy_kWh",
        "route_safe_eta_sec",
        "e4b_template_id",
        "profile_safe_horizon_steps",
    }
    accessed = {
        node.slice.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
        and node.slice.value in forbidden
    }

    assert accessed == set()
