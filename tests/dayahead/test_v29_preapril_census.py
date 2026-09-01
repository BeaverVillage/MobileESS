from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from tools.v29.run_preapril_census import ARTIFACT_NAMES, OUTPUT_REL, queue_age_bin, wallclock_bin


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / OUTPUT_REL


def load(name: str):
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_fixed_bins_are_predeclared_and_total():
    assert [wallclock_bin(value) for value in (0.5, 2, 8, 20, 30)] == [
        "W00_LE_1H",
        "W01_1_TO_4H",
        "W02_4_TO_12H",
        "W03_12_TO_24H",
        "W04_GT_24H",
    ]
    assert [queue_age_bin(value) for value in (None, 0.5, 4, 12, 48, 100)] == [
        "Q00_NOT_IN_D1_QUEUE",
        "Q01_LE_1H",
        "Q02_1_TO_6H",
        "Q03_6_TO_24H",
        "Q04_24_TO_72H",
        "Q05_GT_72H",
    ]


def test_all_required_artifacts_exist_and_hash_match():
    manifest = load("V29_PREAPRIL_CENSUS_ARTIFACT_SHA256.json")
    assert manifest["status"] == "PASS"
    assert set(manifest["files"]) == set(ARTIFACT_NAMES)
    for name, expected in manifest["files"].items():
        assert (OUT / name).is_file()
        assert digest(OUT / name) == expected


def test_daily_population_is_complete_and_nonnegative():
    with (OUT / "V29_PREAPRIL_DAILY_CARRYIN_CENSUS.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 456
    assert rows[0]["day"] == "2024-01-01"
    assert rows[-1]["day"] == "2025-03-31"
    assert len({row["day"] for row in rows}) == 456
    assert all(float(row["D0_0000_predicted_carryin_nodeh"]) >= 0 for row in rows)


def test_absolute_causal_label_rules_pass():
    audit = load("V29_PREAPRIL_CAUSAL_LABEL_AUDIT.json")
    assert audit["status"] == "PASS"
    assert audit["FIT_ROWS_WITH_LABEL_AVAILABLE_AFTER_CUTOFF"] == 0
    assert audit["APRIL_LABEL_ROWS_IN_PREAPRIL_FIT"] == 0
    assert audit["ROLLING_TRAIN_ROWS_WITH_LABEL_AFTER_FOLD_CUTOFF"] == 0
    assert audit["ROLLING_APRIL_ROWS_IN_TRAIN"] == 0


def test_grid_value_is_fail_closed_without_historical_authority():
    summary = load("V29_PREAPRIL_GRID_VALUE_POTENTIAL_SUMMARY.json")
    assert summary["status"] == "NOT_IDENTIFIABLE_SOURCE_ELECTRICAL_AUTHORITY_INSUFFICIENT"
    assert summary["study_days_with_frozen_D1_electrical_critical_row"] == 0
    assert summary["full_10x96_OpenDSS_runs"] == 0
    assert summary["P50_grid_value_ceiling"] is None


def test_no_retuning_or_production_mutation_claimed():
    review = load("V29_PREAPRIL_CENSUS_FINAL_REVIEW.json")
    assert review["production_mutations"] == 0
    assert review["full_OpenDSS_10x96_runs"] == 0
    unchanged = review["answers"]["9_must_remain_unchanged"]
    assert "rho" in unchanged
    assert any("eligibility" in item for item in unchanged)


def test_ratio_summary_has_requested_statistics():
    summary = load("V29_PREAPRIL_SERVICE_CALIBRATION_SUMMARY.json")
    overall = summary["overall"]
    assert overall["row_count"] > 0
    assert set(overall["R_percentiles"]) == {"P05", "P10", "P25", "P50", "P75", "P90", "P95", "P99"}
    assert overall["requested_service_nodeh"] > 0
    assert overall["realized_service_nodeh"] >= 0


def test_rolling_origin_uses_only_declared_candidates():
    with (OUT / "V29_PREAPRIL_ROLLING_ORIGIN_CALIBRATION.csv").open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    candidates = {row["candidate"] for row in rows}
    assert candidates == {
        "RAW_WALLCLOCK_REQ",
        "HISTORICAL_MEDIAN_REALIZATION_FRACTION",
        "HISTORICAL_P25_REALIZATION_FRACTION",
        "FIXED_SIMPLE_LIGHTGBM_Q50_RATIO",
    }
    assert len({row["validation_month"] for row in rows}) >= 10


@pytest.mark.parametrize("name", ARTIFACT_NAMES)
def test_artifact_is_nonempty(name: str):
    assert (OUT / name).stat().st_size > 0
