from __future__ import annotations

import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead/artifacts/v29r2_anchor_aware_trust_noregret"


def test_bridge_v2_is_causal_and_keeps_the_D0_boundary() -> None:
    contract = json.loads((OUT / "V29R2_BRIDGE_V2_CONTRACT.json").read_text(encoding="utf-8"))
    assert contract["status"] == "PASS"
    assert contract["future_actual_feature_count"] == 0
    assert contract["April_fit_rows"] == 0
    assert contract["optimization_horizon_extended"] is False
    assert contract["running_job_preemption"] is False
    assert contract["post_cutoff_arrival_bridge_count"] == 0
    assert contract["reference_v4_authorized"] is True


def test_bridge_v2_mass_bounds_and_coverage_pass() -> None:
    calibration = json.loads((OUT / "V29R2_BRIDGE_V2_CALIBRATION.json").read_text(encoding="utf-8"))
    with (OUT / "V29R2_BRIDGE_V2_ROLLING_ORIGIN.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert calibration["status"] == "PASS"
    assert calibration["lower_bound_coverage"] >= calibration["coverage_target"]
    assert calibration["predicted_mass_identity_max_error"] <= 1e-9
    assert calibration["actual_no_double_count_min_margin"] >= -1e-9
    assert rows and all(row["aggregation_level"] == "D_DAY_X_COHORT" for row in rows)
    for row in rows:
        cutoff_req = float(row["cutoff_H_REQ"])
        pre_nom = float(row["pre_D0_service_NOM"])
        requested, nominal, lower = map(float, (row["H0_REQ"], row["H0_NOM"], row["H0_LOW"]))
        assert abs(cutoff_req - pre_nom - requested) <= 1e-9
        assert 0 <= lower <= nominal + 1e-9 <= requested + 1e-9
        assert row["fit_rows_with_label_available_after_cutoff"] == "0"
        assert row["April_rows_used"] == "0"
