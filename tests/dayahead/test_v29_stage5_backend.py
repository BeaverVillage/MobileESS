import ast
import json
from pathlib import Path

import numpy as np

from dayahead.v28r2.workload_replay import replay_workload
from dayahead.v29.backend_contract import increment_resolution


REPO = Path(__file__).resolve().parents[2]
ART = REPO / "dayahead/artifacts/v29_grid_responsive_aidc"


def test_actual_replay_accepts_causal_initial_backlog_and_conserves_mass():
    da = np.zeros((15, 48, 96)); arrivals = np.zeros((96, 15)); capacity = np.ones((96, 48))
    initial = np.zeros(15); initial[0] = 2.0
    da[0, 0, 0] = 1.0; da[0, 0, 1] = 1.0
    result = replay_workload(da, arrivals, capacity, initial)
    assert result.backlog_nodeh[0, 0] == 2.0
    assert result.executed_nodeh[0, 0, 0] == 1.0
    assert result.executed_nodeh[0, 0, 1] == 1.0
    assert result.backlog_nodeh[-1, 0] == 0.0
    assert result.mass_error_nodeh == 0.0


def test_increment_resolution_is_separate_from_solver_equivalence():
    resolved = increment_resolution(0.6, {"CL_MC_BD": 0.59, "MONOLITHIC": 0.59001, "STANDARD_BD": 0.59002})
    assert resolved["status"] == "STRONGLY_RESOLVED"
    unresolved = increment_resolution(0.6, {"CL_MC_BD": 0.59999, "MONOLITHIC": 0.60001, "STANDARD_BD": 0.59998})
    assert unresolved["status"] == "UNRESOLVED"
    assert unresolved["scientific_improvement_claim_allowed"] is False


def test_actual_binding_has_no_optimizer_import():
    tree = ast.parse((REPO / "dayahead/v29/actual_replay.py").read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    imports += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
    assert not any(any(token in module for token in ("gurobi", "solver_runner", "benders_authority")) for module in imports)


def test_stage5_static_contracts():
    solver = json.loads((ART / "V29_SOLVER_EQUIVALENCE_CONTRACT.json").read_text(encoding="utf-8"))
    actual = json.loads((ART / "V29_ACTUAL_REPLAY_CONTRACT.json").read_text(encoding="utf-8"))
    opendss = json.loads((ART / "V29_OPENDSS_CONTRACT.json").read_text(encoding="utf-8"))
    assert solver["relative_objective_range_tolerance"] == 1e-4
    assert actual["optimizer_calls"] == 0
    assert opendss["trajectories_per_day"] == 10 and opendss["slots_per_trajectory"] == 96
