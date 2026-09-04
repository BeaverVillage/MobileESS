"""Frozen exact-scheduler adapter for post-selection V24M diagnostics."""

from __future__ import annotations

import numpy as np

from dayahead.ml.racq_flex.queue_layer import exact_scheduler


def schedule_gpu_h(tensor_GPU_h: np.ndarray) -> dict[str, object]:
    """Schedule one 96x6x5 workload tensor without shedding or rescaling."""

    return exact_scheduler(np.asarray(tensor_GPU_h, float))
