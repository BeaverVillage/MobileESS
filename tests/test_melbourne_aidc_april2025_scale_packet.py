import csv
import hashlib
import json
import math
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "dayahead" / "artifacts" / "melbourne_aidc_april2025_scale"


def load_json(name):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def packet():
    return load_json("MELBOURNE_AIDC_APRIL2025_SCALE_DECISION_PACKET.json")


def test_scaling_reference_period_is_exactly_april_2025():
    correction = load_json("MELBOURNE_AIDC_SCALE_TEMPORAL_CORRECTION.json")
    assert correction["scale_reference_period"] == {
        "start": "2025-04-01T00:00:00+10:00",
        "end": "2025-04-30T23:59:59+10:00",
        "timezone": "AEST",
    }
    assert "scaling_information_cutoff" not in packet()


def test_march_training_and_scaling_firewall_is_zero():
    counters = packet()["firewall_counters"]
    assert counters["March_training_artifact_changes"] == 0
    assert counters["March_training_retraining_calls"] == 0
    assert counters["March_real_scale_selection_calls"] == 0
    assert counters["March_result_based_scaling_calls"] == 0
    assert packet()["scientific_contract_statements"] == [
        "2025-03-31 is the ML training cutoff only.",
        "April 2025 is the real-world AIDC/host-grid scaling reference period.",
        "No March scaling authority was created or modified.",
    ]


def test_v4r1_and_all_v17_candidate_files_are_byte_preserved():
    manifest = load_json("MELBOURNE_AIDC_APRIL2025_PRECHANGE_MANIFEST.json")
    assert manifest["preserved_file_count"] == 369
    by_name = {Path(row["path"]).name: row for row in manifest["preserved_files"]}
    for required in manifest["required_named_files"]:
        assert required in by_name
    for row in manifest["preserved_files"]:
        path = REPO / row["path"]
        assert path.stat().st_size == row["bytes"]
        assert sha256(path) == row["sha256"]


def test_no_post_april_or_ultimate_capacity_is_back_projected():
    rows = packet()["April_2025_capacity_evidence"]
    by_id = {row["aidc_id"]: row for row in rows}
    assert by_id["AIDC05"]["APRIL_IT_MW_PRIMARY"] == 42
    assert by_id["AIDC05"]["ultimate_it_mw"] == 60
    assert by_id["AIDC06"]["APRIL_IT_MW_PRIMARY"] == 13.5
    assert by_id["AIDC06"]["ultimate_it_mw"] == 150
    assert by_id["AIDC12"]["APRIL_IT_MW_PRIMARY"] == 36
    assert by_id["AIDC12"]["ultimate_it_mw"] == 72
    assert by_id["AIDC10"]["APRIL_IT_MW_PRIMARY"] is None


def test_mid_april_change_contract_is_explicit():
    p = packet()
    assert p["April_capacity_change_events"] == []
    known = [r for r in p["April_2025_capacity_evidence"] if r["APRIL_IT_MW_PRIMARY"] is not None]
    assert known
    assert all(r["APRIL_STATE"] == "APRIL_STATE_CONSTANT" for r in known)
    assert all(r["APRIL_CAPACITY_CHANGE_DATE"] is None for r in known)
    assert all(r["APRIL_IT_MW_PRE"] == r["APRIL_IT_MW_POST"] for r in known)


def test_capacity_boundary_and_pue_are_not_double_counted():
    allowed = {"IT_SIDE", "FACILITY_SIDE", "UTILITY_CONNECTION", "SUBSTATION_CONNECTION", "ULTIMATE_CAMPUS", "UNKNOWN"}
    for row in packet()["April_2025_capacity_evidence"]:
        assert row["CAPACITY_BOUNDARY"] in allowed
        assert row["PUE_DOUBLE_COUNT_CHECK"] == "PASS"
        if row["APRIL_IT_MW_PRIMARY"] is not None:
            assert row["CAPACITY_BOUNDARY"] == "IT_SIDE"
            assert row["PUE_APPLIED"] is True
            assert math.isclose(row["PCC_EQUIVALENT_MW_PUE130"], row["APRIL_IT_MW_PRIMARY"] * 1.30)
        else:
            assert row["PUE_APPLIED"] is False
            assert row["PCC_EQUIVALENT_MW_PUE130"] is None


def test_unique_host_denominators_are_not_double_counted():
    p = packet()
    hosts = p["unique_host_set"]
    assert len(hosts) == len({h["host_id"] for h in hosts}) == 12
    denoms = {d["id"]: d for d in p["April_denominator_variants"]}
    expected = {
        "D_APRIL_FIRM_MW": sum(h["firm_mw"] or 0 for h in hosts),
        "D_APRIL_NORMAL_MW": sum(h["normal_mw"] or 0 for h in hosts),
        "D_APRIL_2025_FORECAST_PEAK_MW": sum(h["forecast_mw"] or 0 for h in hosts),
        "D_APRIL_2024_HISTORICAL_PEAK_MW": sum(h["historical_mw"] or 0 for h in hosts),
        "D_APRIL_FIRM_MVA": sum(h["firm_mva"] or 0 for h in hosts),
        "D_APRIL_NORMAL_MVA": sum(h["normal_mva"] or 0 for h in hosts),
    }
    for key, value in expected.items():
        assert math.isclose(denoms[key]["value"], value)


def test_debug_solver_and_scientific_run_counters_are_zero():
    counters = packet()["firewall_counters"]
    assert counters["April_debug_result_reads_for_scale_selection"] == 0
    assert counters["B0_B1_B2_B3_solver_calls"] == 0
    assert counters["Fresh_OpenDSS_calls"] == 0
    assert counters["OpenDSS_calls_inside_Benders"] == 0
    assert counters["April_scientific_runs"] == 0
    assert counters["May_scientific_reads"] == 0
    assert counters["June_scientific_reads"] == 0


def test_candidate_arithmetic_and_weights_are_reproducible():
    p = packet()
    numerators = {n["id"]: n for n in p["April_numerator_variants"]}
    assert numerators["N_APRIL_IT_PRIMARY"]["value_mw"] == 106.5
    assert math.isclose(numerators["N_APRIL_PCC_PRIMARY"]["value_mw"], 138.45)
    assert numerators["N_APRIL_LOW"]["value_mw"] == 106.5
    assert numerators["N_APRIL_HIGH"]["value_mw"] == 118.5
    denoms = {d["id"]: d for d in p["April_denominator_variants"]}
    for row in p["April_penetration_candidate_matrix"]:
        n = numerators[row["numerator_id"]]["value_mw"]
        d = denoms[row["denominator_id"]]["value"]
        assert math.isclose(row["value"], n / d)
    weights = p["April_site_weights"]
    known = [v for v in weights["KNOWN_SITE_NORMALIZED_WEIGHTS"].values() if v is not None]
    assert math.isclose(sum(known), 1.0)
    assert weights["FULL_12_SITE_WEIGHT_STATUS"] == "INCOMPLETE"
    model_denoms = {d["id"]: d for d in p["IEEE123_denominator_candidates"]}
    rhos = {r["rho_id"]: r for r in p["April_penetration_candidate_matrix"]}
    for row in p["model_AIDC_scale_candidate_matrix"]:
        boundary_value = rhos[row["rho_id"]]["value"] * model_denoms[row["model_denominator_id"]]["value_mw"]
        if row["input_boundary"] == "IT_SIDE":
            assert math.isclose(row["total_model_AIDC_IT_MW"], boundary_value)
            assert math.isclose(row["total_model_AIDC_PCC_MW"], boundary_value * 1.30)
        else:
            assert math.isclose(row["total_model_AIDC_PCC_MW"], boundary_value)
            assert math.isclose(row["total_model_AIDC_IT_MW"], boundary_value / 1.30)


def test_master_csv_has_exact_required_columns_and_12_rows():
    required = [
        "AIDC_ID", "MODEL_LOCALITY", "REPRESENTATIVE_REAL_FACILITY", "OPERATOR", "REAL_ADDRESS", "LAT", "LON",
        "DISTANCE_KM", "FACILITY_MATCH_CONFIDENCE", "APRIL_OPERATIONAL_STATUS", "APRIL_CAPACITY_CHANGE_DATE",
        "APRIL_IT_MW_PRE", "APRIL_IT_MW_POST", "APRIL_IT_MW_PRIMARY", "APRIL_IT_MW_LOW", "APRIL_IT_MW_HIGH",
        "APRIL_FACILITY_MW", "APRIL_GRID_CONNECTION_MVA", "CAPACITY_BOUNDARY", "PCC_EQUIVALENT_MW_PUE130",
        "PUE_APPLIED", "SOURCE_URL", "SOURCE_DATE", "SOURCE_APRIL_APPLICABILITY", "CAPACITY_AUTHORITY_GRADE",
        "DNSP", "REAL_HOST_GRID", "HOST_TYPE", "HOST_MAPPING_CLASS", "HOST_CONFIDENCE", "HOST_FIRM_MW",
        "HOST_NORMAL_MW", "HOST_2025_FORECAST_PEAK_MW", "HOST_2024_HISTORICAL_PEAK_MW", "HOST_FIRM_MVA",
        "HOST_NORMAL_MVA", "HOST_SOURCE_URL", "HOST_APRIL_APPLICABILITY", "HOST_AUTHORITY_GRADE", "APRIL_REAL_SITE_WEIGHT",
    ]
    with (OUT / "MELBOURNE_AIDC_APRIL2025_SCALE_DECISION_TABLE.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
        assert stream.closed is False
    assert len(rows) == 12
    assert list(rows[0]) == required


def test_packet_contains_no_final_scale_selection_language():
    text = (OUT / "MELBOURNE_AIDC_APRIL2025_SCALE_DECISION_PACKET.md").read_text(encoding="utf-8")
    assert text.startswith("=== COPY THIS SECTION TO CHATGPT ===")
    assert "2025-03-31 IS ML TRAINING CUTOFF ONLY." in text
    assert "APRIL 2025 IS THE REAL-WORLD SCALING REFERENCE PERIOD." in text
    assert "CODEX DID NOT SELECT THE FINAL SCALE." in text
    assert "recommended scale =" not in text.lower()
    assert "recommended rho =" not in text.lower()
    assert "selected penetration =" not in text.lower()


if __name__ == "__main__":
    tests = sorted((name, value) for name, value in globals().items() if name.startswith("test_") and callable(value))
    for name, test in tests:
        test()
        print(f"PASS {name}")
    print(f"{len(tests)} focused checks passed")
