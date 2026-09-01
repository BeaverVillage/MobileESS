"""Frozen IT-side power adapter for post-selection V24M diagnostics."""

from __future__ import annotations

import numpy as np

from dayahead.ml.racq_flex.power_bridge import service_to_IT_power_numpy_kW


def flexible_it_power_kW(scheduled_service_GPU_h: np.ndarray) -> np.ndarray:
    """Convert scheduled GPU-h to frozen IT-side kW; PUE and facility scale are excluded."""

    return service_to_IT_power_numpy_kW(np.asarray(scheduled_service_GPU_h, float))
