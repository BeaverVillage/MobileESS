import numpy as np
import pandas as pd
from pathlib import Path

from dayahead.v28r2.lightgbm_channels import (
    DAILY_FEATURES, SLOT_FEATURES, causal_optimizer_predictions, daily_features,
    enforce_quantile_integrity, slot_features,
)
from dayahead.v28r2 import lightgbm_channels
from dayahead.v28r2.source_labels import AEST, OptimizerLabels


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


def test_april_month_rollout_recursively_supplies_causal_lag_features(tmp_path, monkeypatch):
    timestamps = pd.date_range("2025-03-01", periods=31 * 96, freq="15min", tz=AEST)
    labels = OptimizerLabels(
        timestamps=timestamps,
        p_it_kw=np.linspace(100.0, 200.0, len(timestamps)),
        p_observed=np.ones(len(timestamps), dtype=bool),
        g_h100_gpu=np.linspace(10.0, 20.0, len(timestamps)),
        w_nodeh=np.ones((len(timestamps), 15), dtype=float),
        cohort_ids=tuple(f"cohort-{index}" for index in range(15)),
        source_paths={}, source_sha256={}, audit={},
    )
    calls = []

    def fake_predict(_model_dir, channel, variant, features, _cache=None):
        calls.append((channel, variant, str(features.index[0].date())))
        return np.vstack([
            np.full(len(features), 1.0),
            np.full(len(features), 2.0),
            np.full(len(features), 3.0),
        ])

    monkeypatch.setattr(lightgbm_channels, "predict_serialized_quantiles", fake_predict)
    p_quantiles, g_quantiles, w_quantiles = causal_optimizer_predictions(
        labels, "2025-04-30", tmp_path,
    )
    assert p_quantiles.shape == g_quantiles.shape == (3, 96)
    assert w_quantiles.shape == (3,)
    assert np.isfinite(p_quantiles).all() and np.isfinite(g_quantiles).all() and np.isfinite(w_quantiles).all()
    assert len(calls) == 90
    assert all(sum(channel == expected for channel, _variant, _day in calls) == 30 for expected in (
        "P_REF", "G_REF", "W_FULLNODE_DAILY",
    ))
    assert all((channel, "GENERAL_THROUGH_MARCH_31_FIT", "2025-04-03") in calls for channel in (
        "P_REF", "G_REF", "W_FULLNODE_DAILY",
    ))


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
