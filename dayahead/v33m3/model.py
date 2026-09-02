"""Compact one-shot DA-RQSTG graph-residual quantile model.

The model deliberately uses no recursive target-day assimilation.  Its graph
encoder is a fixed directed line-graph smoothing operator; temporal inputs are
causal seasonal, weekly, and available previous-day states.  Coefficients and
positive quantile increments are learned only from blocked historical folds.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Sequence

import numpy as np

from .dataset import LINK_COUNT, TARGET_STEPS


@dataclass(frozen=True)
class DARQSTGParameters:
    seasonal_weight: float = 0.55
    weekly_weight: float = 0.35
    available_previous_day_weight: float = 0.10
    graph_smoothing_weight: float = 0.08
    recent_state_weight: float = 0.04
    recent_scats_weight: float = 0.01
    lower_increment_fraction: tuple[float, float, float, float] = (0.12, 0.13, 0.14, 0.15)
    upper_increment_fraction: tuple[float, float, float, float] = (0.17, 0.18, 0.19, 0.20)

    @property
    def model_sha(self) -> str:
        return hashlib.sha256(
            json.dumps(self.__dict__, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class DARQSTGModel:
    """Direct 288-step ordered-quantile predictor."""

    def __init__(self, parameters: DARQSTGParameters, adjacency: np.ndarray | None = None):
        self.parameters = parameters
        if adjacency is None:
            adjacency = np.eye(LINK_COUNT, dtype=np.float32)
        adjacency = np.asarray(adjacency, dtype=np.float32)
        if adjacency.shape != (LINK_COUNT, LINK_COUNT):
            raise ValueError("adjacency must have shape [509,509]")
        rows = adjacency.sum(axis=1, keepdims=True)
        self.adjacency = adjacency / np.maximum(rows, 1.0)

    def predict(
        self,
        seasonal_median: np.ndarray,
        previous_week: np.ndarray,
        previous_day_available: np.ndarray,
        previous_day_mask: np.ndarray,
        recent_link_state: np.ndarray | None = None,
        recent_link_baseline: np.ndarray | None = None,
        recent_scats_log: np.ndarray | None = None,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        arrays = [np.asarray(value, dtype=np.float32) for value in (
            seasonal_median, previous_week, previous_day_available
        )]
        if any(value.shape != (TARGET_STEPS, LINK_COUNT) for value in arrays):
            raise ValueError("DA-RQSTG inputs must each have shape [288,509]")
        mask = np.asarray(previous_day_mask, dtype=bool)
        if mask.shape not in {(TARGET_STEPS,), (TARGET_STEPS, LINK_COUNT)}:
            raise ValueError("previous-day availability mask has invalid shape")
        if mask.ndim == 1:
            mask = mask[:, None]
        p = self.parameters
        prev_weight = p.available_previous_day_weight * mask
        denominator = p.seasonal_weight + p.weekly_weight + prev_weight
        center = (
            p.seasonal_weight * arrays[0]
            + p.weekly_weight * arrays[1]
            + prev_weight * arrays[2]
        ) / denominator
        graph_state = center @ self.adjacency.T
        q50 = (1.0 - p.graph_smoothing_weight) * center + p.graph_smoothing_weight * graph_state
        if recent_link_state is not None or recent_link_baseline is not None:
            recent = np.asarray(recent_link_state, dtype=np.float32)
            recent_base = np.asarray(recent_link_baseline, dtype=np.float32)
            if recent.shape != (24, LINK_COUNT) or recent_base.shape != recent.shape:
                raise ValueError("recent link state and baseline must have shape [24,509]")
            residual = np.mean(recent - recent_base, axis=0)
            residual = (1.0 - p.graph_smoothing_weight) * residual + p.graph_smoothing_weight * (residual @ self.adjacency.T)
            decay = np.exp(-np.arange(TARGET_STEPS, dtype=np.float32) / 72.0)[:, None]
            q50 = q50 + p.recent_state_weight * decay * residual[None, :]
        if recent_scats_log is not None:
            scats = np.asarray(recent_scats_log, dtype=np.float32)
            if scats.shape != (24, LINK_COUNT):
                raise ValueError("recent causal SCATS must have shape [24,509]")
            anomaly = np.clip(
                (np.mean(scats[-6:]) - np.mean(scats)) / (np.std(scats) + 1e-6), -2.0, 2.0
            )
            decay = np.exp(-np.arange(TARGET_STEPS, dtype=np.float32) / 48.0)[:, None]
            q50 = q50 * (1.0 + p.recent_scats_weight * anomaly * decay)
        q50 = np.maximum(q50, np.finfo(np.float32).eps)
        bands = np.repeat(np.arange(4), 72)
        lower = np.asarray(p.lower_increment_fraction, dtype=np.float32)[bands, None]
        upper = np.asarray(p.upper_increment_fraction, dtype=np.float32)[bands, None]
        # Positive increments structurally prevent quantile crossing.
        q10 = np.maximum(q50 * (1.0 - lower), np.finfo(np.float32).eps)
        q90 = q50 * (1.0 + upper)
        return q10.astype(np.float32), q50.astype(np.float32), q90.astype(np.float32)

    def direct_output_shape(self) -> tuple[int, int, int]:
        return TARGET_STEPS, LINK_COUNT, 3
