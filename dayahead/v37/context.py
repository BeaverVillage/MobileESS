"""Portable May formulation and electrical-context loader."""

from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.v28r2.electrical_cache_prepare import prepare_electrical_context
from dayahead.v28r2.electrical_context import build_electrical_context
from dayahead.v28r2 import formulation
from dayahead.v28r2 import lightgbm_channels

from dayahead.v36.context import install_exact_source_lookup
from .contracts import CACHE_ROOT, SOURCE_DATA_REPOSITORY


def _causal_optimizer_predictions_may(labels: object, target_date: str, model_dir: Path):
    """Unchanged frozen V28R2 recursion with a V37 May-only scope guard."""

    target = pd.Timestamp(target_date, tz=labels.timestamps.tz)
    first = pd.Timestamp("2025-05-01", tz=labels.timestamps.tz)
    last = pd.Timestamp("2025-05-31", tz=labels.timestamps.tz)
    if not first <= target <= last:
        raise ValueError("V37_OPTIMIZER_MATERIALIZATION_MAY_ONLY")
    booster_cache: dict[tuple[str, str], tuple[object, ...]] = {}
    p_quantiles = lightgbm_channels._recursive_slot_predictions(
        labels.p_it_kw, labels.timestamps, target, model_dir, "P_REF", booster_cache,
    )
    g_quantiles = lightgbm_channels._recursive_slot_predictions(
        labels.g_h100_gpu, labels.timestamps, target, model_dir, "G_REF", booster_cache,
    )
    daily_index = pd.date_range(
        labels.timestamps[0].normalize(), labels.timestamps[-1].normalize(),
        freq="D", tz=labels.timestamps.tz,
    )
    daily_w = pd.Series(
        labels.w_nodeh.reshape(-1, 96, len(labels.cohort_ids)).sum(axis=(1, 2)),
        index=daily_index,
    )
    w_quantiles = lightgbm_channels._recursive_daily_predictions(
        daily_w, target, model_dir, booster_cache,
    )
    return p_quantiles, g_quantiles, w_quantiles


def load_day_context(repo: Path, day: str):
    install_exact_source_lookup()
    previous = Path.cwd()
    original_predictor = formulation.causal_optimizer_predictions
    try:
        formulation.causal_optimizer_predictions = _causal_optimizer_predictions_may
        data = formulation.materialize_formulation_data(
            SOURCE_DATA_REPOSITORY, day, disable_legacy_mess_source=True,
        )
        cache = repo / CACHE_ROOT / "electrical" / day
        try:
            electrical = build_electrical_context(SOURCE_DATA_REPOSITORY, data, cache)
        except RuntimeError as error:
            if not str(error).startswith("V28R2_D1_ELECTRICAL_CACHE_MISSING:"):
                raise
            electrical = prepare_electrical_context(SOURCE_DATA_REPOSITORY, data, cache)
        return data, electrical
    finally:
        formulation.causal_optimizer_predictions = original_predictor
        os.chdir(previous)
