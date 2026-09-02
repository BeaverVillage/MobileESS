from __future__ import annotations

import csv
import json
from pathlib import Path

from dayahead.v29r1.authority import Q_SCENARIOS
from dayahead.v29r2.mess_noregret import EPSILON_AC_NR, EPSILON_NR, RUNG_ORDER, select_first_safe_rung


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"


def _evaluation(plan: float, ac: float) -> dict[str, object]:
    return {"planning_delta_vs_B2": plan, "rho_AC_delta_vs_B2": ac, "all_converged": True}


def test_selector_uses_first_safe_rung_and_falls_back_deterministically() -> None:
    values = {
        "Q_RELEASE": {scenario: _evaluation(0.0, EPSILON_AC_NR * 2) for scenario in Q_SCENARIOS},
        "Q_ANCHOR": {scenario: _evaluation(EPSILON_NR / 2, EPSILON_AC_NR / 2) for scenario in Q_SCENARIOS},
    }
    selected, audit = select_first_safe_rung(values)
    assert selected == "Q_ANCHOR"
    assert [row["rung"] for row in audit] == ["Q_RELEASE", "Q_ANCHOR"]
    selected, audit = select_first_safe_rung({})
    assert selected == "B2_FALLBACK" and audit[-1]["safe"] is True


def test_frozen_contract_preserves_ratings_scenarios_and_thresholds() -> None:
    contract = json.loads((OUT / "V29R2_MESS_NOREGRET_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["status"] == "PASS"
    assert contract["rung_order"] == list(RUNG_ORDER)
    assert contract["scenario_set"] == list(Q_SCENARIOS)
    assert contract["epsilon_NR"] == contract["epsilon_AC_NR"] == 1e-4
    assert contract["rating_changes"] == 0
    assert contract["objective_change"] is False
    assert contract["Actual_reads"] == contract["April_result_reads"] == 0
    assert contract["MESS_rating_authority"]["P_LIMIT_KW"] > 0


def test_prefreeze_scenario_and_release_gate_artifacts_are_complete() -> None:
    with (OUT / "V29R2_MESS_NOREGRET_SCENARIOS.csv").open(encoding="utf-8-sig", newline="") as stream:
        scenarios = list(csv.DictReader(stream))
    with (OUT / "V29R2_MESS_NOREGRET_AC_GATE.csv").open(encoding="utf-8-sig", newline="") as stream:
        gates = list(csv.DictReader(stream))
    with (OUT / "V29R2_MESS_FALLBACK_DECISION.csv").open(encoding="utf-8-sig", newline="") as stream:
        decisions = list(csv.DictReader(stream))
    assert [row["scenario"] for row in scenarios] == list(Q_SCENARIOS)
    assert all(row["same_feeder_forecast_namespace"] == "True" and row["Actual_realization_used"] == "False" for row in scenarios)
    assert len(gates) == len(RUNG_ORDER) * len(Q_SCENARIOS)
    assert {(row["rung"], row["scenario"]) for row in gates} == {
        (rung, scenario) for rung in RUNG_ORDER for scenario in Q_SCENARIOS
    }
    if "prefreeze_status" in gates[0]:
        assert all(row["prefreeze_status"] == "PASS_GATE_DEFINED_AND_ENFORCED_BY_SELECTOR" for row in gates)
        assert [row["rung"] for row in decisions] == list(RUNG_ORDER)
    else:
        assert all(row["all_converged"] == "True" for row in gates)
        fallback = [row for row in gates if row["rung"] == "B2_FALLBACK"]
        assert all(float(row["planning_delta_vs_B2"]) == 0.0 for row in fallback)
        assert all(float(row["rho_AC_delta_vs_B2"]) == 0.0 for row in fallback)
        assert len(decisions) == 1 and decisions[0]["selected_rung"] == "Q_RELEASE"
        assert decisions[0]["safe"] == "True"
