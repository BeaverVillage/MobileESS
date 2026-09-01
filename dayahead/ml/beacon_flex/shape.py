"""Hierarchical regime shapes and exact daily-mass tensor disaggregation."""

from __future__ import annotations

import numpy as np


def normalize_shapes(tensors:np.ndarray)->tuple[np.ndarray,np.ndarray]:
    """Normalize positive 96x6x5 target tensors; never turn null mass into a shape."""

    totals=tensors.sum(axis=(1,2,3)); positive=totals>0
    shapes=np.zeros_like(tensors,dtype=float); shapes[positive]=tensors[positive]/totals[positive,None,None,None]
    return shapes,positive


def hierarchical_shape(tensors:np.ndarray)->np.ndarray:
    """Estimate hourly, within-hour, tier and latency shares without sparse-cell regression."""

    total=np.asarray(tensors,float).sum(axis=0)
    if total.sum()<=0:
        raise ValueError("V25M_EMPTY_SHAPE_TRAINING_MASS")
    hourly=total.reshape(24,4,6,5).sum(axis=(1,2,3)); hourly/=hourly.sum()
    within=total.reshape(24,4,6,5).sum(axis=(2,3)); within/=np.maximum(within.sum(axis=1,keepdims=True),1e-12)
    tier=total.reshape(24,4,6,5).sum(axis=(0,1,3)); tier/=tier.sum()
    latency=total.reshape(24,4,6,5).sum(axis=(0,1,2)); latency/=latency.sum()
    shape=hourly[:,None,None,None]*within[:,:,None,None]*tier[None,None,:,None]*latency[None,None,None,:]
    shape=shape.reshape(96,6,5); return shape/shape.sum()


def coherent_tensor(daily_GPU_h:float,shape:np.ndarray)->np.ndarray:
    """Scale a normalized shape and correct final IEEE-754 summation drift exactly."""

    normalized=np.maximum(np.asarray(shape,float),0.0); normalized/=normalized.sum()
    tensor=float(daily_GPU_h)*normalized
    flat=tensor.reshape(-1); flat[int(np.argmax(flat))]+=float(daily_GPU_h)-float(tensor.sum())
    if tensor.min()<-1e-12:
        raise RuntimeError("V25M_NEGATIVE_DISAGGREGATED_MASS")
    return tensor


def regime_index(value:float,thresholds:np.ndarray)->int:
    """Return BODY, P80-90, P90-95, or P95+ regime index."""

    u80,u90,u95=np.asarray(thresholds,float)[2:]
    return 0 if value<=u80 else 1 if value<=u90 else 2 if value<=u95 else 3

