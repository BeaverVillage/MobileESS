"""Frozen D-day innovation authority selection."""

from __future__ import annotations


def day_innovation_authority() -> dict[str, object]:
    """Return the preregistered B2/B3 production authority without retuning."""

    return {
        "mean": "C-B0_B2_LIGHTGBM_TWEEDIE",
        "Q50_Q90": "C-B1_B3_LIGHTGBM_QUANTILE_RAW_LINEAGE",
        "weekday_factorized_pooled_Mean_WAPE": 0.9467355624694638,
        "B2_pooled_Mean_WAPE": 0.976108062962391,
        "selection": "RETAIN_B2_B3",
        "reason": "weekday-factorized pooled advantage lacks preregistered nested-OOF/significance authority; no silent production-authority change",
    }

