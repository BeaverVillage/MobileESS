"""Public cache reader for the frozen V27M base cross-fit contract."""

from __future__ import annotations

from pathlib import Path

import numpy as np


def load_outer_training_base(repo: Path, fold_id: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    cache = np.load(repo / "dayahead/artifacts/v27m_safe_flex_r1/V27M_BASE_CROSSFIT_CACHE.npz")
    return cache[f"fold{fold_id}_dates"], cache[f"fold{fold_id}_lower"], cache[f"fold{fold_id}_upper"]

