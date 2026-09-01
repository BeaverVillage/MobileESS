import numpy as np
import pandas as pd
from pathlib import Path

from dayahead.v28r2.lightgbm_channels import (
    DAILY_FEATURES, SLOT_FEATURES, daily_features, enforce_quantile_integrity, slot_features,
)
from dayahead.v28r2.source_labels import AEST


def test_slot_features_are_d1_cutoff_safe_and_96_slot():
    index = pd.date_range("2024-08-01", periods=96 * 10, freq="15min", tz=AEST)
    values = np.arange(len(index), dtype=float)
    frame = slot_features(values, index)
    assert tuple(frame.columns) == SLOT_FEATURES
    assert frame.index.tz == AEST
    assert set(frame["slot"].iloc[-96:].astype(int)) == set(range(96))
    assert frame["lag_2d"].iloc[-1] == values[-1 - 192]
    assert "lag_1d" not in frame


def test_daily_features_do_not_use_previous_incomplete_day():
    index = pd.date_range("2024-08-01", periods=20, freq="D", tz=AEST)
    values = pd.Series(np.arange(20, dtype=float), index=index)
    frame = daily_features(values)
    assert tuple(frame.columns) == DAILY_FEATURES
    assert frame["lag_2d"].iloc[-1] == values.iloc[-3]
    assert "lag_1d" not in frame


def test_public_quantile_rearrangement_is_nonnegative_and_ordered():
    raw_log = np.asarray([[2.0, -1e-15], [1.0, 3.0], [4.0, 2.0]])
    output = enforce_quantile_integrity(raw_log)
    assert np.all(output >= 0)
    assert np.all(output[0] <= output[1])
    assert np.all(output[1] <= output[2])


def test_frozen_lightgbm_artifacts_have_no_april_or_may_training():
    import json

    root = Path(__file__).resolve().parents[2] / "dayahead/artifacts/v28r2_heavy_backend"
    for name in (
        "V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json",
        "V28R2_FINAL_G_REF_LIGHTGBM_AUTHORITY.json",
        "V28R2_FINAL_W_FULLNODE_LIGHTGBM_AUTHORITY.json",
    ):
        path = root / name
        if not path.exists():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["April_training_rows"] == 0
        assert payload["May_training_rows"] == 0
        assert payload["mean_is_Q50_copy"] is False
        assert payload["status"] == "PASS"
        assert all(fit["noncrossing_violations"] == 0 for fit in payload["fits"])
