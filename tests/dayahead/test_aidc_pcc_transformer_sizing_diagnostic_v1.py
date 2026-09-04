from __future__ import annotations

import json
from pathlib import Path

from dayahead.aidc_power_response import KAPPA_KW_PER_ACTIVE_H100_NODE
from dayahead.run_aidc_pcc_transformer_sizing_diagnostic_v1 import (
    linear_quantile,
    maximize_flexible_power_kw,
)


def test_resource_lp_greedy_uses_highest_kappa_and_respects_capacity() -> None:
    arrivals = {"N01_R00": 0.25, "N02_R00": 0.25, "N16_R00": 1.0}
    power, served, allocation = maximize_flexible_power_kw(arrivals, 0.375)
    assert served == 0.375
    assert allocation["N01_R00"] == 0.25
    assert allocation["N02_R00"] == 0.125
    assert allocation["N16_R00"] == 0.0
    expected = (
        KAPPA_KW_PER_ACTIVE_H100_NODE[1] * 0.25
        + KAPPA_KW_PER_ACTIVE_H100_NODE[2] * 0.125
    ) / 0.25
    assert abs(power - expected) <= 1e-12


def test_linear_quantile_matches_frozen_linear_definition() -> None:
    values = [0.0, 10.0, 20.0, 30.0, 40.0]
    assert linear_quantile(values, 0.0) == 0.0
    assert linear_quantile(values, 0.95) == 38.0
    assert linear_quantile(values, 0.99) == 39.6
    assert linear_quantile(values, 1.0) == 40.0


def test_materialized_v16_2_diagnostic_stops_with_grid_insufficient() -> None:
    artifacts = Path(__file__).resolve().parents[2] / "dayahead" / "artifacts" / "v16_2"
    provenance = json.loads((artifacts / "AIDC_PCC_TRANSFORMER_PROVENANCE_AUDIT_V1.json").read_text(encoding="utf-8"))
    sizing = json.loads((artifacts / "AIDC_PCC_TRANSFORMER_SIZING_DIAGNOSTIC_V1.json").read_text(encoding="utf-8"))
    assert provenance["scenario_authority"]["synthetic_engineering_scenario"]
    assert not provenance["scenario_authority"]["actual_dnsp_nameplate_claim"]
    assert provenance["mess_transformer"]["status"] == "UNCHANGED"
    assert provenance["generated_interface_asset"]["aidc_transformer_count"] == 12
    assert provenance["generated_interface_asset"]["mess_transformer_count"] == 24
    assert sizing["classification"] == "TX_CLASS_B_EXISTING_GRID_INSUFFICIENT"
    assert sizing["april_coverage"]["operating_day_count"] == 30
    assert sizing["april_coverage"]["evaluated_aidc_day_slot_case_count"] == 34560
    assert sizing["boundary_validity"]["status"] == "PASS"
    assert sizing["resource_feasible_maximum_s_envelope"]["s_required_continuous_kva"] > 700.0
    assert not sizing["common_rating_policy"]["common_existing_candidate_available"]
    assert all(not row["covers_all_12_aidcs_all_april_slots"] for row in sizing["candidate_coverage"])
    assert set(sizing["execution_firewall"].values()) == {0}
