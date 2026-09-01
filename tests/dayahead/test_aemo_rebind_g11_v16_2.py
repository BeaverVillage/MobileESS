from __future__ import annotations

import json
from pathlib import Path

from dayahead.pcc_transformer_v16_2 import AUTHORITY_SHA256, V3_SHA256, sha256_file


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "dayahead/artifacts/v16_2"


def test_v16_2_c7_g10_use_v4_and_preserve_frozen_boundaries() -> None:
    c7 = json.loads((ARTIFACTS / "C7_FULL_IEEE123_REPORT_V16_2_AEMO_REBIND.json").read_text(encoding="utf-8"))
    g10 = json.loads((ARTIFACTS / "G10_V16_2_AEMO_REBIND_REPORT.json").read_text(encoding="utf-8"))
    manifest = json.loads((ARTIFACTS / "DAYAHEAD_INPUT_MANIFEST_V16_2_APRIL.json").read_text(encoding="utf-8"))
    assert c7["status"] == "PASS_FULL_IEEE123_V16_2"
    assert g10["status"] == "PASS"
    assert c7["P_RES_SYS_kw"]["negative_slot_count"] == 0
    assert c7["G_RES_SYS"]["negative_slot_count"] == 0
    assert c7["power_reconstruction_max_abs_error_kw"] <= 1e-9
    assert c7["rack_gpu_cap_violation_count"] == 0
    assert c7["service_parity_residual"] == 0.0
    assert c7["pue_application_count"] == 1
    assert c7["full_ieee123_compile"]["all_aidc_hosts_present"]
    assert c7["pcc_transformer_contract"]["active_aidc_rating_kva"] == 1500.0
    assert not c7["pcc_transformer_contract"]["old_750_aidc_authority_active"]
    assert c7["pcc_transformer_contract"]["mess_pcc_rating_change_count"] == 0
    assert c7["pcc_transformer_contract"]["v3_preserved_sha256"] == V3_SHA256
    assert c7["transformer_schedule_audit"]["violation_count_aidc_slots"] == 0
    assert manifest["aemo_vintage_contract_sha256"] == "b11cd2548afc24cb123dd995e5d4ae0cdf3ca8a39d9ad9eadc8da4e93c6fb3c9"
    assert manifest["scientific_authority_sha256"] == AUTHORITY_SHA256
    assert not manifest["aemo_vintage_reselected"]


def test_v16_2_g11_stops_fail_closed_on_exact_upstream_grid_blockers() -> None:
    g11 = json.loads((ARTIFACTS / "G11_V16_2_FULL_IEEE123_AEMO_REBIND_REPORT.json").read_text(encoding="utf-8"))
    execution = g11["execution"]
    blocker = g11["exact_physical_blocker"]
    audit = g11["independent_deterministic_hard_constraint_audit"]
    assert g11["status"] == "FAIL_FULL_IEEE123_BASELINE_INFEASIBLE"
    assert execution["grid_lp_count"] == 96
    assert execution["feasible_grid_lp_count"] == 0
    assert not execution["baseline_feasible_incumbent_admitted"]
    assert execution["master_dependent_row_registry_complete"]
    assert execution["pi_sign_convention"] == "PASS"
    assert execution["farkasdual_sign_convention"] == "PASS"
    assert execution["sampled_perturbation_cut_validity"]["status"] == "PASS"
    assert execution["infeasible_incumbent_exclusion"]["status"] == "PASS"
    assert "tx_hard[transformer.reg1a,A,1]" in execution["baseline_time_0_iis"]["constraint_names"]
    assert blocker["classification"] == "FULL_IEEE123_UPSTREAM_TRANSFORMER_LINE_AND_VOLTAGE_HARD_INFEASIBILITY"
    assert audit["violating_transformer_branches"] == ["transformer.reg1a"]
    assert audit["transformer_violation_time_count"] == 96
    assert audit["line_hard_violation_count"] > 0
    assert audit["voltage_hard_violation_count"] > 0
    assert g11["dedicated_aidc_pcc_transformer_audit"]["violation_count_aidc_slots"] == 0
    assert g11["mess_pcc"]["rating_change_count"] == 0
    assert set(g11["downstream_call_counts"].values()) == {0}
    assert not g11["ready_for_final_g12_preproduction"]
    assert not g11["may_primary_unlock_ready"]
    assert g11["stop_rule_applied"]
    assert set(g11["firewall"].values()) <= {0, False}


def test_v16_2_authority_and_v4_entrypoint_are_frozen() -> None:
    authority = ARTIFACTS / "V16_2_AIDC_PCC_TRANSFORMER_REFREEZE_AUTHORITY.json"
    contract = json.loads((ARTIFACTS / "AIDC_PCC_TRANSFORMER_CONTRACT_V2.json").read_text(encoding="utf-8"))
    assert sha256_file(authority) == AUTHORITY_SHA256
    assert contract["generated_three_phase_pcc_v4"]["role"] == "ACTIVE_V16_2_PCC_ASSET"
    assert contract["generated_three_phase_pcc_v3"]["role"] == "HISTORICAL_EVIDENCE_ONLY"
    assert contract["hard_constraint_semantics"]["rating_fitting_runtime_call_count"] == 0
    assert contract["hard_constraint_semantics"]["transformer_rating_optimization_variable_count"] == 0
    assert contract["hard_constraint_semantics"]["transformer_constraint_slack_variable_count"] == 0
