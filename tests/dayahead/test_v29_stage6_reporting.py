from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np


REPO = Path(__file__).resolve().parents[2]
ARTIFACT = REPO / "dayahead/artifacts/v29_grid_responsive_aidc"
RESULT = REPO / "frozen_artifacts/v29_development_regression_apr01_04"
DAYS = ("2025-04-01", "2025-04-02", "2025-04-03", "2025-04-04")


def rows(name: str) -> list[dict[str, str]]:
    with (ARTIFACT / name).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def test_v29_stage6_frozen_day_contracts() -> None:
    formulation = set()
    for day in DAYS:
        payload = json.loads((RESULT / day / "V29_DAY_RESULT.json").read_text(encoding="utf-8"))
        assert payload["status"] == "PASS"
        assert payload["OpenDSS_trajectory_count"] == 10
        assert payload["OpenDSS_solve_count"] == 960
        assert payload["actual_namespace_open_before_freeze"] == 0
        assert payload["actual_optimizer_calls"] == 0
        assert payload["rho_AIDC"] == 0.1
        assert payload["connection_delay_slots"] == 1
        assert all(payload["dominance"].values())
        formulation.add(payload["formulation_fingerprint"])
    assert len(formulation) == 1


def test_v29_stage6_reporting_and_mechanism_gate() -> None:
    objective = rows("V29_4DAY_OBJECTIVE_RESULTS.csv")
    actuation = rows("V29_4DAY_AIDC_ACTUATION.csv")
    solver = rows("V29_4DAY_SOLVER_RESOLUTION.csv")
    opendss = rows("V29_4DAY_OPENDSS_RESULTS.csv")
    actual = rows("V29_4DAY_ACTUAL_RESULTS.csv")
    comparison = rows("V29_V28_VS_V29_MECHANISM_COMPARISON.csv")
    assert len(objective) == len(actuation) == len(solver) == 4
    assert len(opendss) == 40
    assert len(actual) == 20
    assert all(row["dominance_pass"] == "True" for row in objective)
    assert all(float(row["B3_relative_solver_range"]) <= 1e-4 for row in solver)
    assert all(row["increment_resolution_status"] == "STRONGLY_RESOLVED" for row in solver)
    assert all(int(row["convergence_count"]) == 96 and int(row["clean_engine_count"]) == 1 for row in opendss)
    pooled = comparison[-1]
    assert pooled["day"] == "POOLED_MEAN"
    l1_gate = float(pooled["V29_critical_time_AIDC_L1_action_kw"]) > float(pooled["V28_critical_time_AIDC_L1_action_kw"])
    weighted_gate = float(pooled["V29_signed_sensitivity_weighted_action_pu"]) > float(pooled["V28_signed_sensitivity_weighted_action_pu"])
    assert l1_gate and weighted_gate and pooled["MECHANISM_IMPROVED"] == "True"


def test_v29_stage6_mass_and_carryin_conservation() -> None:
    carry = rows("V29_4DAY_CARRYIN_USAGE.csv")
    actual = rows("V29_4DAY_ACTUAL_RESULTS.csv")
    assert len(carry) == 8
    assert max(abs(float(row["carryin_conservation_error_nodeh"])) for row in carry) <= 1e-9
    assert max(abs(float(row["workload_mass_error_nodeh"])) for row in actual) <= 1e-9
    assert all(int(row["actual_optimizer_calls"]) == 0 for row in actual)
    assert np.isclose(sum(float(row["carryin_queue_nodeh"]) for row in carry if row["case"] == "B1"), 1236.0)
