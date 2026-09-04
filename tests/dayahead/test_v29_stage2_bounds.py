import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2] / "dayahead/artifacts/v29_grid_responsive_aidc"


def test_stage2_bounds_are_complete_non_authority_and_dimensionally_consistent():
    payload = json.loads((ROOT / "V29_CRITICAL_TIME_FLEXIBILITY_UPPER_BOUND.json").read_text(encoding="utf-8"))
    assert payload["status"] == "PASS"
    assert payload["production_authority"] is False
    assert payload["certificate_created"] is False
    assert len(payload["rows"]) == len(payload["relief_rows"]) == 8
    assert {row["rho_AIDC"] for row in payload["rows"]} == {0.1, 1.0}
    assert all(row["MESS_grid_support"] == "OFF" for row in payload["rows"])
    assert all(0.0 <= row["workload_limited_fraction"] <= 1.0 for row in payload["rows"])
    assert all(0.0 <= row["trust_limited_fraction"] <= 1.0 for row in payload["rows"])
    assert all(row["maximum_feasible_critical_time_aggregate_downshift_kw"] >= -1e-9 for row in payload["rows"])
    assert all(abs(row["maximum_baseline_critical_row_relief_pu"] - row["maximum_sensitivity_weighted_relief_pu"]) <= 2e-6 for row in payload["relief_rows"])
    assert all(item["classification"] == "MIXED" for item in payload["day_classifications"])
    assert payload["tuning_after_result"] is False


def test_stage2_csv_axes_match_json():
    with (ROOT / "V29_CRITICAL_TIME_FLEXIBILITY_UPPER_BOUND.csv").open(encoding="utf-8-sig", newline="") as stream:
        upper = list(csv.DictReader(stream))
    with (ROOT / "V29_CRITICAL_ROW_RELIEF_UPPER_BOUND.csv").open(encoding="utf-8-sig", newline="") as stream:
        relief = list(csv.DictReader(stream))
    assert len(upper) == len(relief) == 8
    assert {(row["day"], row["rho_AIDC"]) for row in upper} == {(row["day"], row["rho_AIDC"]) for row in relief}
