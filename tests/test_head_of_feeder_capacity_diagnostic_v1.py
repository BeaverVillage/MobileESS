import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ARTIFACTS = REPO / "dayahead" / "artifacts" / "v16_2"


def test_g12_thermal_support_is_programmatically_reg1a_a_only() -> None:
    report = json.loads(
        (ARTIFACTS / "G12_IIS_THERMAL_SUPPORT_AUDIT_V1.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "PASS"
    assert report["report_ilp_exact_row_identity"] is True
    assert report["rows"]
    assert {row["element"] for row in report["rows"]} == {"transformer.reg1a"}
    assert {row["phase"] for row in report["rows"]} == {"A"}
    assert report["grid_line_hard_count"] + report["grid_transformer_hard_count"] == len(report["rows"])


def test_headgrid_stop_classification_and_firewall() -> None:
    report = json.loads(
        (ARTIFACTS / "HEAD_OF_FEEDER_CAPACITY_ISOLATION_DIAGNOSTIC_V1.json").read_text(encoding="utf-8")
    )
    assert report["classification"] == "HEADGRID_CLASS_B_REG1A_PLUS_OTHER_THERMAL_MISMATCH"
    provenance = report["native_reg1a_provenance"]
    assert provenance["status"] == "PASS"
    assert provenance["phases"] == 3
    assert provenance["kVA_by_winding"] == [5000.0, 5000.0]
    assert provenance["production_planning_model_denominator"][
        "mathematically_consistent_with_frozen_3phase_5mva_authority"
    ] is True
    continuous = report["continuous_reg1a_diagnostic"]
    assert continuous["hard_feasible"] is False
    assert continuous.get("lambda_reg1a_min") is None
    assert {row["element"] for row in continuous["iis"]["thermal_rows"]} == {"line.l10"}
    assert {row["phase"] for row in continuous["iis"]["thermal_rows"]} == {"A"}
    assert report["april_validation_reference_envelope"]["status"] == "NOT_RUN_STOPPED_DEEPER_INCOMPATIBILITY"
    assert report["fresh_opendss_diagnostic"]["status"] == "NOT_RUN_NO_PLANNING_FEASIBLE_CANDIDATE"
    assert report["fresh_opendss_diagnostic"]["candidates"] == {}
    for key in (
        "scientific_authority_changes", "native_asset_changes", "line_rating_changes",
        "voltage_limit_changes", "alpha_grid_changes", "AIDC_scale_changes",
        "MESS_parameter_changes", "may_scientific_loader_access_count",
        "june_scientific_loader_access_count",
    ):
        assert report[key] == 0
    assert report["downstream_call_counts"] == {"G13": 0, "G14": 0, "C12": 0}
