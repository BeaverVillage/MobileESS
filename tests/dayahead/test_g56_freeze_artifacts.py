from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ARTIFACTS = Path(__file__).parents[2] / "dayahead" / "artifacts" / "v16"


def test_g56_freeze_has_no_may_june_access_and_exactly_one_refit() -> None:
    evidence = json.loads((ARTIFACTS / "AIDC_G5_G6_TEST_EVIDENCE.json").read_text(encoding="utf-8"))
    freeze = json.loads((ARTIFACTS / "AIDC_ML_FREEZE_REPORT.json").read_text(encoding="utf-8"))
    assert evidence["status"] == "PASS"
    assert evidence["checks"]["may_june_loader_access_count"] == 0
    assert evidence["checks"]["expost_d1_eligibility_field_access_count"] == 0
    assert evidence["checks"]["production_refit_count"] == 1
    assert evidence["checks"]["production_seed"] == 20260828
    assert evidence["checks"]["positive_scaling_inverse_transform_roundtrip"] is True
    assert evidence["checks"]["deterministic_math_sdp_only"] is True
    assert freeze["may_june_forecast_rows"] == 0


def test_april_validation_forecast_is_direct96_finite_and_monotone() -> None:
    frame = pd.read_parquet(ARTIFACTS / "AIDC_APRIL_VALIDATION_FORECAST.parquet")
    assert set(frame["namespace"]) == {"APRIL_VALIDATION_ONLY"}
    assert frame["forecast_day"].min() == "2025-04-01"
    assert frame["forecast_day"].max() == "2025-04-30"
    assert frame["forecast_day"].nunique() == 30
    assert sorted(frame["slot"].unique()) == list(range(96))
    assert np.isfinite(frame["prediction"]).all()
    probabilistic = frame[frame["model"].isin(["Vanilla Transformer", "Proposed AIDC RC-MQT"])]
    keys = ["model", "forecast_day", "slot", "target"]
    wide = probabilistic.pivot(index=keys, columns="quantile", values="prediction")
    assert (wide[0.1] <= wide[0.5]).all()
    assert (wide[0.5] <= wide[0.9]).all()


def test_production_weight_file_and_config_fingerprints_are_reproducible() -> None:
    torch = __import__("torch")
    from dayahead.aidc_ml_backend import verify_saved_weight_fingerprint

    card = json.loads((ARTIFACTS / "AIDC_MODEL_CARD.json").read_text(encoding="utf-8"))
    weights = ARTIFACTS / card["weights_file"]
    assert hashlib.sha256(weights.read_bytes()).hexdigest() == card["weights_file_sha256"]
    assert verify_saved_weight_fingerprint(weights)["final_weight_config_fingerprint"] == card[
        "final_weight_config_fingerprint"
    ]
    assert torch.__version__.startswith("2.8.0")


def test_mapping_authority_is_exact_sha_pass_and_c7_ready() -> None:
    mapping = json.loads((ARTIFACTS / "FROZEN_MAPPING_AUTHORITY.json").read_text(encoding="utf-8"))
    assert mapping["status"] == "PASS"
    assert mapping["new_mapping_created"] is False
    assert mapping["mapping_fitting_call_count"] == 0
    assert mapping["c7_integrated_scientific_solve_allowed"] is True
    assert len(mapping["sources"]) == 6
