import ast
import json
from pathlib import Path

import numpy as np
import pytest

from dayahead.v28r2.authority import COHORT_IDS
from dayahead.v28r2.actual_replay import build_natural_actual, replay_actual_case
from dayahead.v28r2.backend_contract import canonical_sha256
from dayahead.v28r2.mess_replay import replay_mess
from dayahead.v28r2.pi_executor import materialize_pi_formulation_data
from dayahead.v28r2.workload_replay import (
    ActualWorkload, materialize_actual_workload, replay_workload,
)


def _mess_records():
    records = []
    for index in range(4):
        mode = ["CONNECTED"] * 96
        location = [f"STA{index + 1:02d}"] * 96
        available = [True] * 96
        energy = [0.0] * 96
        if index == 0:
            mode[1] = "TRANSIT"; location[1] = "TRANSIT_ROUTE_01"; available[1] = False; energy[1] = 2.5
        records.append({
            "mess_id": f"MESS{index + 1:02d}", "mode": mode,
            "location": location, "available": available,
            "safe_travel_energy_kwh": energy, "initial_energy_kwh": 760.0,
        })
    return records


def test_workload_replay_is_fixed_rack_causal_and_mass_conserving():
    da = np.zeros((15, 48, 96)); arrivals = np.zeros((96, 15)); capacity = np.ones((96, 48))
    da[0, 0, 0] = 1.0; da[0, 0, 1] = 1.0
    arrivals[1, 0] = 2.0
    replay = replay_workload(da, arrivals, capacity)
    assert replay.executed_nodeh[0, 0, 0] == 0.0
    assert replay.executed_nodeh[0, 0, 1] == 1.0
    assert replay.backlog_nodeh[2, 0] == 1.0
    assert replay.mass_error_nodeh == 0.0


def test_mess_replay_enforces_transit_and_one_slot_connection_delay_without_shift():
    p = np.zeros((96, 4)); q = np.zeros((96, 4))
    p[1, 0] = 10.0; p[2, 0] = 10.0; p[3, 0] = 10.0
    result = replay_mess(p, q, _mess_records())
    assert result.p_exec_kw[1, 0] == 0.0
    assert result.p_exec_kw[2, 0] == 0.0
    assert result.p_exec_kw[3, 0] == 10.0
    assert result.reasons_96x4[2, 0] == "CONNECTION_DELAY"
    assert result.command_time_shift_count == 0
    assert result.energy_kwh[2, 0] == 757.5


def test_actual_modules_have_no_optimizer_or_solver_import():
    repo = Path(__file__).resolve().parents[2]
    imports = []
    for name in ("actual_replay.py", "workload_replay.py", "mess_replay.py"):
        tree = ast.parse((repo / "dayahead/v28r2" / name).read_text(encoding="utf-8"))
        imports.extend(node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom))
        imports.extend(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names)
    denied = ("solver_runner", "benders_authority", "variable_registry", "gurobipy", "lightgbm")
    assert not any(any(token in module for token in denied) for module in imports)


def test_april1_actual_materialization_and_pi_system_identity_without_solve():
    repo = Path(__file__).resolve().parents[2]
    source = repo / "cache/v28r2_campaign_sources/april_2025/days/2025-04-01"
    if not source.is_dir():
        return
    actual = materialize_actual_workload(repo, "2025-04-01")
    assert actual.arrivals_nodeh.shape == (96, 15)
    assert np.all(actual.flexible_natural_gpu <= actual.total_h100_gpu + 1e-9)
    pi = materialize_pi_formulation_data(repo, "2025-04-01", actual)
    assert pi.cohort_ids == COHORT_IDS
    assert pi.arrivals_nodeh.shape == (96, 15)
    assert len(pi.c1_coefficients) == 12 * 96
    assert pi.vintage["authority_id"] == "V28R2_PI_REALIZED_AEMO_INPUT_V1"
    mobility = json.loads((source / "traffic_mobility.json").read_text(encoding="utf-8"))
    route = {}
    for record in mobility["mess"]:
        connected = next(
            location for location, mode in zip(record["location"], record["mode"], strict=True)
            if mode == "CONNECTED"
        )
        route[record["mess_id"]] = {
            "service_site": connected, "location_96": record["location"],
        }
    schedule = {
        "case": "B0", "workload_service_tensor": np.zeros((15, 48, 96)).tolist(),
        "planning_pcc_power_kw": np.zeros((96, 12)).tolist(),
        "planning_pcc_reactive_kvar": np.zeros((96, 12)).tolist(),
        "mess_p_kw": np.zeros((96, 4)).tolist(), "mess_q_kvar": np.zeros((96, 4)).tolist(),
        "mess_route_location": route,
    }
    schedule["schedule_sha256"] = canonical_sha256(schedule)
    replay = replay_actual_case(repo, "2025-04-01", schedule, actual, mobility["mess"])
    assert replay.summary["actual_reoptimization_calls"] == 0
    assert replay.trajectory.namespace == "ACTUAL"
    natural = build_natural_actual(repo, "2025-04-01", actual, mobility["mess"], "c" * 64)
    assert natural.case == "R0" and natural.trajectory.case == "R0"


def test_mess_replay_fails_when_travel_alone_crosses_physical_soc():
    records = _mess_records()
    records[0]["initial_energy_kwh"] = 440.0
    with pytest.raises(RuntimeError, match="TRAVEL_SOC_PHYSICAL_FAIL"):
        replay_mess(np.zeros((96, 4)), np.zeros((96, 4)), records)
