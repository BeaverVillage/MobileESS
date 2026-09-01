"""Cross-correlation and lag-response diagnostics for NLR thermal dynamics."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .contracts import ARTIFACT_ROOT


def lag_correlations(repo: Path) -> list[dict[str, Any]]:
    """Return pre-registered IT-to-cooling correlations at 0..60 minutes."""
    frame = pd.read_parquet(repo / ARTIFACT_ROOT / "V24T_NLR_ALIGNED_THERMAL_DATASET.parquet", columns=["it_power_kw", "cooling_system_kw"])
    x = frame["it_power_kw"].to_numpy(dtype=float)
    y = frame["cooling_system_kw"].to_numpy(dtype=float)
    rows = []
    for lag in (0, 5, 10, 15, 30, 60):
        rows.append({"lag_minutes": lag, "correlation": float(np.corrcoef(x[: len(x)-lag or None], y[lag:])[0, 1])})
    return rows
