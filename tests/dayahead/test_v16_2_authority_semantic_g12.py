import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "dayahead/artifacts/v16_2"


def _payload(name: str) -> dict[str, object]:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def _sha(name: str) -> str:
    return hashlib.sha256((ARTIFACTS / name).read_bytes()).hexdigest()


def test_prior_forensics_and_g11_failure_evidence_are_immutable() -> None:
    assert _sha("FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json") == "dbfb342b18f3eedcff67630fae5b59b0fe0ac71084a7ed84ac1684cefbe0eeb5"
    assert _sha("FULL_IEEE123_BASELINE_AC_DIAGNOSTIC_V1.json") == "152d2d85d1a3c6864298bd8e99e134f6a643803b66d8e07e3f8572d5d162f947"
    assert _sha("G11_V16_2_FULL_IEEE123_AEMO_REBIND_REPORT.json") == "ad62c20846243510c7175fd2db721d9a74f1e6e8e59dee65f12af828527ba29f"


def test_authority_semantic_background_binding_is_exact_and_unfitted() -> None:
    contract = _payload("GRID_BACKGROUND_MAPPING_CONTRACT_V16_2_BINDING.json")
    assert contract["status"] == "PASS"
    assert contract["alpha_grid"] == 0.7481417265421424
    assert contract["alpha_grid_application_count"] == 1
    assert contract["native_background_double_count_call_count"] == 0
    assert contract["mapping_fitting_call_count"] == 0
    assert max(map(abs, contract["identity_maxima"].values())) <= 1e-8
    assert all(record["status"] == "PASS" for record in contract["source_paths_and_sha256"].values())


def test_g11_is_cut_validity_pass_with_infeasible_initial_reference() -> None:
    report = _payload("G11_V16_2_AUTHORITY_SEMANTIC_REPORT.json")
    execution = report["execution"]
    assert report["status"] == "PASS_FULL_IEEE123_V16_2"
    assert execution["grid_lp_count"] == 96
    assert execution["initial_infeasible_grid_lp_count"] == 96
    assert execution["initial_reference_grid_status"] == "INFEASIBLE_EXPECTED_FARKAS_PATH"
    assert execution["initial_reference_all_96_feasible_required_by_g11"] is False
    assert execution["pi_sign_convention"] == "PASS"
    assert execution["sampled_perturbation_cut_validity"]["status"] == "PASS"
    assert execution["farkasdual_sign_convention"] == "PASS"
    assert execution["infeasible_incumbent_exclusion"]["status"] == "PASS"
    assert execution["legacy_rack_kw_row_active_count"] == 0


def test_g12_stops_on_actual_monolithic_b3_iis_without_bd_or_downstream_calls() -> None:
    report = _payload("G12_V16_2_FULL_IEEE123_B3_REPORT.json")
    mono = report["monolithic"]
    iis = mono["iis"]
    assert report["status"] == "G12_FAIL_B3_PLANNING_INFEASIBLE"
    assert mono["hard_feasible"] is False
    assert mono["full_ieee123_grid_block_count"] == 96
    assert mono["compute_flexibility"] == "ON"
    assert mono["mess_flexibility"] == "ON_FIXED_FROZEN_ROUTES"
    assert iis["computed"] is True
    assert iis["constraint_count"] > 0
    assert iis["constraint_family_counts"]["grid_transformer_hard"] > 0
    assert any("transformer.reg1a,A" in name for name in iis["constraint_names"])
    assert report["standard_single_cut_bd"]["status"] == "NOT_RUN_MONOLITHIC_B3_INFEASIBLE"
    assert report["cl_mc_bd"]["status"] == "NOT_RUN_MONOLITHIC_B3_INFEASIBLE"
    assert report["downstream_call_counts"] == {"C12": 0, "G13": 0, "G14": 0, "realized_replay": 0}
    assert report["firewall"]["may_scientific_loader_access_count"] == 0
    assert report["firewall"]["june_scientific_loader_access_count"] == 0
