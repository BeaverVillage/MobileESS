"""Read-only forensic helpers for V25M summary and base-distribution integrity."""

from __future__ import annotations

import pandas as pd


MEAN_STATISTIC_MODELS = {
    "C-B0_B2_LIGHTGBM_TWEEDIE",
    "C-B2_V24M_DIRECT_LIGHTGBM",
    "C-B3_V24M_FACTORIZED_LIGHTGBM",
    "C-B4_WEEKDAY_FACTORIZED",
    "C-B5_B2_B3_PRODUCTION_HYBRID",
}


def canonical_field_forensic(canonical: pd.DataFrame) -> dict[str, object]:
    """Separate conditional-mean candidates from quantile-only rows on identical OOF days."""

    all_row_minimum = canonical.loc[canonical.Mean_WAPE.idxmin()]
    mean_candidates = canonical.loc[canonical.model.isin(MEAN_STATISTIC_MODELS)]
    mean_row_minimum = mean_candidates.loc[mean_candidates.Mean_WAPE.idxmin()]
    b2 = canonical.loc[canonical.model.eq("C-B0_B2_LIGHTGBM_TWEEDIE")].iloc[0]
    weekday = canonical.loc[canonical.model.eq("C-B4_WEEKDAY_FACTORIZED")].iloc[0]
    return {
        "all_model_rows_minimum": {"model": all_row_minimum.model, "Mean_WAPE": float(all_row_minimum.Mean_WAPE)},
        "conditional_mean_model_rows_minimum": {"model": mean_row_minimum.model, "Mean_WAPE": float(mean_row_minimum.Mean_WAPE)},
        "B2_Mean_WAPE": float(b2.Mean_WAPE), "weekday_factorized_Mean_WAPE": float(weekday.Mean_WAPE),
        "same_pooled_OOF_days": bool(canonical.target_days.nunique() == 1 and int(canonical.target_days.iloc[0]) == 151),
        "diagnosis": "SUMMARY_FIELD_MODEL_UNIVERSE_MAPPING_DEFECT",
    }


def q50_reconciliation_forensic(reconciled: pd.DataFrame, daily: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, object]]:
    """Compare raw B3 Q50 OOF values with V25M reconciled Q50 without touching April raw data."""

    raw = daily.loc[daily.model.eq("C-B1_B3_LIGHTGBM_QUANTILE"), ["date", "Q50_GPU_h"]].rename(columns={"Q50_GPU_h": "raw_B3_Q50_GPU_h"})
    joined = reconciled.merge(raw, on="date", how="inner", validate="one_to_one")
    collapsed = joined.loc[joined.Q50_GPU_h.lt(1e-8)].copy()
    collapsed["raw_positive"] = collapsed.raw_B3_Q50_GPU_h.gt(1e-6)
    summary = {
        "OOF_rows": len(joined), "reconciled_Q50_near_zero_rows": len(collapsed),
        "collapsed_rows_using_BR_A": int(collapsed.selected_method.eq("BR-A").sum()),
        "collapsed_rows_with_positive_raw_B3_Q50": int(collapsed.raw_positive.sum()),
        "BR_A_median_Q50_change_GPU_h": float((joined.loc[joined.selected_method.eq("BR-A"), "Q50_GPU_h"] - joined.loc[joined.selected_method.eq("BR-A"), "raw_B3_Q50_GPU_h"]).median()),
        "diagnosis": "BR_A_MEAN_ANCHORED_PROJECTION_CAN_COLLAPSE_POSITIVE_RAW_Q50_TO_ZERO",
    }
    return collapsed, summary

