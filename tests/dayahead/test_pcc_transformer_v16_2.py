from __future__ import annotations

import json
from pathlib import Path

from dayahead.pcc_transformer_v16_2 import (
    AIDC_RATING_KVA,
    AUTHORITY_SHA256,
    FREEZE_TOKEN,
    MESS_RATING_KVA,
    V3_SHA256,
    sha256_file,
    transformer_records,
)


REPO = Path(__file__).resolve().parents[2]
ARTIFACTS = REPO / "dayahead/artifacts/v16_2"


def test_v16_2_authority_is_premay_source_backed_and_immutable() -> None:
    path = ARTIFACTS / "V16_2_AIDC_PCC_TRANSFORMER_REFREEZE_AUTHORITY.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert sha256_file(path) == AUTHORITY_SHA256
    assert payload["prospective"]
    assert payload["minted_before_may_june_scientific_access"]
    assert payload["candidate_family"]["candidate_kva"] == [750.0, 1000.0, 1500.0, 2000.0]
    assert payload["selection_authority"]["selected_candidate_kva"] == AIDC_RATING_KVA
    assert payload["immutability"]["freeze_token"] == FREEZE_TOKEN
    assert not payload["immutability"]["rating_change_after_may_opened_allowed"]
    assert set(payload["execution_firewall_at_mint"].values()) == {0}


def test_v4_exact_ratings_voltage_mapping_and_v3_preservation() -> None:
    contract = json.loads((ARTIFACTS / "AIDC_PCC_TRANSFORMER_CONTRACT_V2.json").read_text(encoding="utf-8"))
    v4 = ARTIFACTS / "Generated_ThreePhase_PCC_v4.dss"
    records = transformer_records(v4.read_text(encoding="utf-8-sig"))
    aidc = [row for row in records if str(row["name"]).startswith("IDC_IDC")]
    mess = [row for row in records if str(row["name"]).startswith("MESS_")]
    assert contract["generated_three_phase_pcc_v3"]["sha256"] == V3_SHA256
    assert contract["generated_three_phase_pcc_v4"]["sha256"] == sha256_file(v4)
    assert len(aidc) == 12 and all(row["primary_kva"] == row["secondary_kva"] == AIDC_RATING_KVA for row in aidc)
    assert len(mess) == 24 and all(row["primary_kva"] == row["secondary_kva"] == MESS_RATING_KVA for row in mess)
    assert all(row["phases"] == 3 and row["primary_kv"] == 4.16 and row["secondary_kv"] == 0.48 for row in records)
    assert contract["host_mapping_identity_v3_v4"]
    assert contract["nonrating_electrical_property_identity_v3_v4"]
    assert contract["mess_pcc_rating_change_count"] == 0


def test_v16_2_contract_has_no_runtime_fitting_optimization_or_slack() -> None:
    contract = json.loads((ARTIFACTS / "AIDC_PCC_TRANSFORMER_CONTRACT_V2.json").read_text(encoding="utf-8"))
    semantics = contract["hard_constraint_semantics"]
    assert semantics["rating_fitting_runtime_call_count"] == 0
    assert semantics["transformer_rating_optimization_variable_count"] == 0
    assert semantics["transformer_constraint_slack_variable_count"] == 0
    assert semantics["transformer_current_loading_max_pu"] == 1.0
    assert semantics["transformer_kva_loading_max_pu"] == 1.0
    assert not semantics["post_freeze_rating_change_allowed"]
    assert set(contract["firewall"].values()) == {0}
