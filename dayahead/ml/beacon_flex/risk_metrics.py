"""Risk outputs derived from the same deterministic daily predictive ensemble."""

from __future__ import annotations

import numpy as np


def exceedance_risks(samples_GPU_h:np.ndarray,thresholds_GPU_h:np.ndarray)->dict[str,float]:
    """Return empirical p80/p90/p95, EE90 and CTM90 in GPU-h units."""

    samples=np.asarray(samples_GPU_h,float); u80,u90,u95=np.asarray(thresholds_GPU_h,float)[2:]
    tail=samples>u90
    return {"p80":float(np.mean(samples>u80)),"p90":float(np.mean(tail)),"p95":float(np.mean(samples>u95)),
            "EE90_GPU_h":float(np.maximum(samples-u90,0).mean()),"CTM90_GPU_h":float(samples[tail].mean()) if np.any(tail) else float(u90)}

