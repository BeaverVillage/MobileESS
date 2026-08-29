import hashlib
import json
from pathlib import Path

from dayahead.run_full_ieee123_input_forensic_v1 import ALPHA_GRID, P95_REFERENCE_MW


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "dayahead/artifacts/v16_2"


def _json(name: str) -> dict[str, object]:
    return json.loads((ARTIFACTS / name).read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_scale_and_native_role_are_explicit() -> None:
    report = _json("FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json")
    assert abs(P95_REFERENCE_MW - 9490.53 * ALPHA_GRID) < 1e-9
    assert report["recovered_historical_semantics"]["is_native_ieee123_load"] == (
        "B_SPATIAL_TEMPLATE_REFERENCE_BASIS_ALREADY_INCORPORATED"
    )
    assert report["current_path_semantics"]["native_background_double_count_call_count"] == 0
    assert report["scale_and_unit_audit"]["alpha_grid_application_count"] == 1
    assert report["scale_and_unit_audit"]["pwc_30_to_15_application_count"] == 1
    assert len(report["slot_by_slot_component_totals"]) == 96


def test_primary_classification_uses_authority_correct_lp_and_ac() -> None:
    composition = _json("FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json")
    ac = _json("FULL_IEEE123_BASELINE_AC_DIAGNOSTIC_V1.json")
    expected = "GRID_CLASS_D_TRUE_FROZEN_FEEDER_CAPACITY_INCOMPATIBILITY"
    assert composition["primary_classification"] == expected
    assert ac["primary_classification"] == expected
    assert composition["planning_lp"]["CASE_AUTHORITY_SEMANTIC"]["hard_feasible"] is False
    assert ac["CASE_AUTHORITY_SEMANTIC"]["summary"]["hard_feasible"] is False
    assert ac["CASE_CURRENT"]["summary"]["convergence_count"] == 96
    assert ac["CASE_AUTHORITY_SEMANTIC"]["summary"]["convergence_count"] == 96
    assert ac["G13_marked_or_called"] is False


def test_forensic_firewalls_and_sha_binding() -> None:
    composition_path = ARTIFACTS / "FULL_IEEE123_INPUT_COMPOSITION_FORENSIC_V1.json"
    composition = _json(composition_path.name)
    ac = _json("FULL_IEEE123_BASELINE_AC_DIAGNOSTIC_V1.json")
    assert ac["composition_forensic_sha256"] == _sha(composition_path)
    for key in (
        "scientific_authority_change_count",
        "rating_change_count",
        "alpha_grid_change_count",
        "source_voltage_change_count",
    ):
        assert composition[key] == 0
        assert ac[key] == 0
    for key in (
        "may_scientific_loader_access_count",
        "june_scientific_loader_access_count",
        "G12_call_count",
        "G13_call_count",
        "G14_call_count",
        "C12_call_count",
    ):
        assert composition["firewall"][key] == 0
        assert ac[key] == 0
    assert composition["preserved_state"]["v16_2_authority_sha256"] == (
        "53392a53ac73930fa1336cfd8daf97497fcb455f0569162bf3608c0459759a2d"
    )
    assert composition["preserved_state"]["pcc_v3_sha256"] == (
        "3c3e27020e266dc8f1c4e28e90d49f298d6ca741ef6b54599e44265882cd747c"
    )
