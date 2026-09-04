from __future__ import annotations

import json
from pathlib import Path
import subprocess

import gurobipy as gp
from gurobipy import GRB
import numpy as np
import pytest

from dayahead.v17_ac_restoration_contract import K_MAX, RHO, RestorationCut, ViolationType
from dayahead.v33m.contracts import RouteParameters15Min
from dayahead.v33m.grid_interface import ServicePCCMapping
from dayahead.v33m.mess_mobility_milp import (
    MessElectricalAuthority,
    MessMobilityInputs,
    add_mess_mobility_block,
)
from dayahead.v33m.mess_trajectory import MessTrajectory, MessTrajectorySlot
from dayahead.v33m.route_table import MobilityRouteTable
from dayahead.v34.integrated_mess import (
    _add_restoration_cuts,
    _add_restoration_recourse_trust_region,
    _fix_discrete_trajectory_and_load_start,
)
from dayahead.v37.aidc import build_day, validate_cohort_contract
from dayahead.v37.contracts import EXPECTED_DATES
from dayahead.v37.preflight import validate_anchor_pair, validate_preflight_manifest
from dayahead.v37r3.voltage_authority import (
    load_joint_voltage_authority,
    load_may_voltage_applicability,
)


REPO = Path(__file__).resolve().parents[2]
R4 = REPO / "dayahead/artifacts/v37_r4_may_campaign_repair"


def _route(slot: int, origin: str, destination: str) -> RouteParameters15Min:
    moving = origin != destination
    return RouteParameters15Min(
        departure_slot_15=slot,
        origin_service_id=origin,
        destination_service_id=destination,
        road_origin_node=origin,
        road_destination_node=destination,
        route_link_ids=("link",) if moving else (),
        route_distance_km=1.0 if moving else 0.0,
        cumulative_ascent_m=0.0,
        cumulative_descent_m=0.0,
        route_q10_eta_sec=600.0 if moving else 0.0,
        route_q50_eta_sec=900.0 if moving else 0.0,
        route_q90_eta_sec=1200.0 if moving else 0.0,
        route_safe_eta_sec=1500.0 if moving else 0.0,
        travel_slots_15min=2 if moving else 0,
        connection_ready_slots_15min=2 if moving else 0,
        energy_nominal_kwh=0.5 if moving else 0.0,
        energy_safe_kwh=1.0 if moving else 0.0,
        route_graph_sha="a" * 64,
        traffic_forecast_sha="b" * 64,
        physics_contract_sha="c" * 64,
    )


def _trajectory_slot(
    slot: int, mode: str, service: str | None, energy: float,
) -> MessTrajectorySlot:
    moving = mode == "TRANSIT"
    return MessTrajectorySlot(
        mess_id="MESS01",
        slot=slot,
        mode=mode,
        service_id=service,
        origin_service_id="A" if moving else None,
        destination_service_id="B" if moving else None,
        route_link_ids=("link",) if moving else (),
        departure_slot=1 if moving else None,
        route_q10_eta_sec=600.0 if moving else 0.0,
        route_q50_eta_sec=900.0 if moving else 0.0,
        route_q90_eta_sec=1200.0 if moving else 0.0,
        route_safe_eta_sec=1500.0 if moving else 0.0,
        travel_slots_15min=2 if moving else 0,
        connection_ready_slot=3 if moving else None,
        energy_nominal_kwh=0.5 if moving else 0.0,
        energy_safe_kwh=1.0 if moving else 0.0,
        p_kw=0.0,
        q_kvar=0.0,
        battery_energy_kwh=energy,
        soc_fraction=energy / 100.0,
    )


def test_fixed_discrete_departure_boundary_occupancy_regression() -> None:
    services = ("A", "B")
    records = {
        (slot, origin, destination): _route(slot, origin, destination)
        for slot in range(4)
        for origin in services
        for destination in services
    }
    routes = MobilityRouteTable(tuple(range(4)), services, records)
    authority = MessElectricalAuthority(
        capacity_kwh=100.0,
        energy_min_kwh=0.0,
        energy_max_kwh=100.0,
        initial_energy_kwh=50.0,
        terminal_energy_kwh=49.0,
        active_power_limit_kw=10.0,
        pcs_kva=10.0,
        pcs_polygon_faces=8,
        interval_hours=0.25,
        charge_efficiency=1.0,
        discharge_efficiency=1.0,
    )
    inputs = MessMobilityInputs.create(
        routes,
        4,
        {"MESS01": "A"},
        ServicePCCMapping({"A": "bus_a", "B": "bus_b"}, "test"),
        electrical_authority=authority,
    )
    model = gp.Model("v37_r4_fixed_departure_boundary")
    model.Params.OutputFlag = 0
    block = add_mess_mobility_block(model, inputs)
    trajectory = MessTrajectory((
        _trajectory_slot(0, "CONNECTED", "A", 50.0),
        _trajectory_slot(1, "TRANSIT", None, 50.0),
        _trajectory_slot(2, "TRANSIT", None, 49.0),
        _trajectory_slot(3, "CONNECTED", "B", 49.0),
    ))
    _fix_discrete_trajectory_and_load_start(block, trajectory)
    model.setObjective(0.0, GRB.MINIMIZE)
    model.optimize()
    assert model.Status == GRB.OPTIMAL
    assert block.occupancy["MESS01", 1, "A"].X == pytest.approx(1.0)
    assert block.occupancy["MESS01", 2, "A"].X == pytest.approx(0.0)
    assert block.occupancy["MESS01", 2, "B"].X == pytest.approx(0.0)
    assert block.occupancy["MESS01", 3, "B"].X == pytest.approx(1.0)
    assert block.move["MESS01", 1, "A", "B"].X == pytest.approx(1.0)


@pytest.mark.parametrize(
    ("kind", "relation"),
    [
        (ViolationType.VOLTAGE_LOWER, ">="),
        (ViolationType.VOLTAGE_UPPER, "<="),
        (ViolationType.LINE_CURRENT, "<="),
        (ViolationType.TRANSFORMER_CURRENT, "<="),
        (ViolationType.TRANSFORMER_KVA, "<="),
    ],
)
def test_all_restoration_cut_types_insert_with_frozen_trust_region(
    kind: ViolationType, relation: str,
) -> None:
    model = gp.Model(f"v37_r4_{kind.value}")
    model.Params.OutputFlag = 0
    p = model.addVar(lb=-100.0, ub=100.0, name="mess_p")
    q = model.addVar(lb=-100.0, ub=100.0, name="mess_q")
    names = tuple(f"u[{index}]" for index in range(60))
    expressions = [tuple(0.0 for _ in range(60)) for _ in range(96)]
    expressions[2] = tuple([0.0] * 12 + [p] + [0.0] * 23 + [q] + [0.0] * 23)
    coefficients = [0.0] * 60
    coefficients[12] = 0.001
    coefficients[36] = 0.001
    radius = [0.0] * 60
    radius[12] = 55.0
    radius[36] = 70.0
    lower = relation == ">="
    cut = RestorationCut(
        violation_sha256="a" * 64,
        local_ac_operating_point_sha256="b" * 64,
        derivative_sha256="c" * 64,
        violation_type=kind,
        slot=2,
        relation=relation,
        actual_value=0.949 if lower else 1.01,
        hard_limit=0.95 if lower else 1.0,
        margin=0.0001,
        trust_region_rho=RHO,
        iteration_index=1,
        control_names=names,
        anchor_controls=(0.0,) * 60,
        coefficients=tuple(coefficients),
        local_radius=tuple(radius),
    )
    rows, trust_rows = _add_restoration_cuts(model, names, expressions, (cut,))
    model.setObjective(p + q if lower else -(p + q), GRB.MINIMIZE)
    model.optimize()
    assert model.Status == GRB.OPTIMAL
    assert len(rows) == 1
    assert trust_rows == 4
    assert abs(p.X) <= 55.0 + 1e-8
    assert abs(q.X) <= 70.0 + 1e-8
    lhs = cut.actual_value + 0.001 * p.X + 0.001 * q.X
    rhs = cut.hard_limit + cut.margin if lower else cut.hard_limit - cut.margin
    assert lhs >= rhs - 1e-8 if lower else lhs <= rhs + 1e-8


def test_restoration_recourse_trust_region_covers_every_slot() -> None:
    model = gp.Model("v37_full_horizon_recourse_trust")
    model.Params.OutputFlag = 0
    names = tuple(
        [f"aidc_load_kw[AIDC{index:02d}]" for index in range(1, 13)]
        + [f"mess_p_kw[S{index:02d}]" for index in range(1, 25)]
        + [f"mess_q_kvar[S{index:02d}]" for index in range(1, 25)]
    )
    expressions = []
    variables = []
    for slot in range(3):
        p = model.addVar(lb=-1000.0, ub=1000.0, name=f"p[{slot}]")
        q = model.addVar(lb=-1000.0, ub=1000.0, name=f"q[{slot}]")
        variables.append((p, q))
        expressions.append(tuple([0.0] * 12 + [p] + [0.0] * 23 + [q] + [0.0] * 23))
    anchor = np.zeros((3, 60), dtype=float)
    anchor[:, 12] = [10.0, 20.0, 30.0]
    anchor[:, 36] = [-10.0, -20.0, -30.0]
    rows = _add_restoration_recourse_trust_region(
        model, names, tuple(expressions), anchor,
        p_radius_kw=55.0, q_radius_kvar=70.0,
    )
    model.setObjective(
        -gp.quicksum(p - q for p, q in variables), GRB.MINIMIZE,
    )
    model.optimize()
    assert model.Status == GRB.OPTIMAL
    assert rows == 3 * 48 * 2
    for slot, (p, q) in enumerate(variables):
        assert p.X == pytest.approx(anchor[slot, 12] + 55.0)
        assert q.X == pytest.approx(anchor[slot, 36] - 70.0)


def test_may_authority_and_all_31_anchors_are_authorized() -> None:
    authority, authority_sha = load_joint_voltage_authority(REPO)
    applicability, _ = load_may_voltage_applicability(REPO, authority, authority_sha)
    assert tuple(applicability["authorized_dates"]) == EXPECTED_DATES
    assert applicability["coefficient_values_changed"] is False
    assert applicability["May_data_used_for_calibration"] is False
    assert all(validate_anchor_pair(REPO, day)["status"] == "PASS" for day in EXPECTED_DATES)


@pytest.mark.parametrize("day", ("2025-05-01", "2025-05-15", "2025-05-31"))
def test_aidc_cohort_rule_across_may(day: str) -> None:
    audit = validate_cohort_contract(build_day(REPO, day, "B1").ledger, day)
    assert audit["rule_validation"] == "PASS"
    assert audit["no_double_counting"] is True
    assert audit["D_minus_1_issue_time"].endswith("18:00:00+10:00")


def test_preflight_contract_fails_closed_when_one_day_is_not_ready() -> None:
    rows = [{"operating_day": day, "status": "READY"} for day in EXPECTED_DATES]
    rows[-1]["status"] = "NOT_READY"
    payload = {
        "expected_dates": 31,
        "ready_dates": 30,
        "not_ready_dates": 1,
        "missing_dates": 0,
        "MAY_STARTED": "NO",
        "MAY_CAMPAIGN_LAUNCH_READY": "NO",
        "dates": rows,
        "launch_fingerprints": [],
    }
    failures = validate_preflight_manifest(payload)
    assert "READY_DATES_NOT_31" in failures
    assert "DATE_NOT_READY" in failures
    assert "LAUNCH_FINGERPRINTS_MISSING" in failures


def test_completed_production_preflight_is_exactly_31_of_31() -> None:
    payload = json.loads(
        (R4 / "V37_R4_MAY_31DAY_PRODUCTION_PREFLIGHT.json").read_text(
            encoding="utf-8"
        )
    )
    assert validate_preflight_manifest(payload) == []
    assert payload["ready_dates"] == 31
    assert payload["not_ready_dates"] == 0
    assert payload["missing_dates"] == 0
    assert payload["optimization_calls"] == 0
    assert payload["Gurobi_optimize_calls"] == 0
    assert payload["MAY_STARTED"] == "NO"


def test_powershell_launcher_refuses_incomplete_readiness(tmp_path: Path) -> None:
    manifest = tmp_path / "incomplete.json"
    manifest.write_text(json.dumps({
        "branch": "codex/v37-may2025-locked-final",
        "expected_dates": 31,
        "ready_dates": 30,
        "not_ready_dates": 1,
        "missing_dates": 0,
        "MAY_STARTED": "NO",
        "MAY_CAMPAIGN_LAUNCH_READY": "NO",
        "launch_fingerprints": [],
    }), encoding="utf-8")
    result = subprocess.run(
        [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(REPO / "tools/v37/run_may_locked_final.ps1"),
            "-ValidateOnly", "-NoMonitor", "-ReadinessPathOverride", str(manifest),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    assert "MAY_CAMPAIGN_PREFLIGHT_FAIL" in result.stdout
    assert "CAMPAIGN_LAUNCHED" not in result.stdout


def test_repaired_forensic_decomposition_is_fixed_path_and_no_beam_rerun() -> None:
    root = json.loads((R4 / "V37_R4_RESTORATION_ROOT_CAUSE.json").read_text(encoding="utf-8"))
    assert root["primary_classification"] == "G_OTHER_IDENTIFIED_IMPLEMENTATION_BUG"
    assert set(root["post_repair"].values()) == {"FEASIBLE"}
    assert root["beam_rerun"] is False
    assert root["rho_changed"] is False
    assert RHO == 0.10
    assert K_MAX == 5
