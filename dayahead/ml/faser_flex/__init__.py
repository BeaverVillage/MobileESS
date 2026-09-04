"""V24M FASER-Flex causal probabilistic workload forecasting package."""

from .contracts import FOLDS, LATENCY_CLASSES, POWER_TIERS
from .factorization import DailyFactorTarget, build_daily_factor_targets

__all__ = [
    "DailyFactorTarget",
    "FOLDS",
    "LATENCY_CLASSES",
    "POWER_TIERS",
    "build_daily_factor_targets",
]
