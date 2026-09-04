"""Immutable causal Day-Ahead traffic forecast bundle."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import io
import json
from typing import Sequence

import numpy as np

from dayahead.v33m.contracts import LinkTravelTimeForecast
from .dataset import LINK_COUNT, TARGET_STEPS


@dataclass(frozen=True)
class DayAheadTrafficForecastBundle:
    forecast_day: date
    issue_time: datetime
    max_input_timestamp: datetime
    target_timestamps: tuple[datetime, ...]
    link_ids: tuple[str, ...]
    q10_sec: np.ndarray
    q50_sec: np.ndarray
    q90_sec: np.ndarray
    model_id: str
    model_sha: str
    data_sha: str
    graph_sha: str
    normalization_sha: str
    causality_pass: bool
    future_actual_read_count: int

    def __post_init__(self) -> None:
        if self.issue_time.tzinfo is None or self.max_input_timestamp.tzinfo is None:
            raise ValueError("bundle times must be timezone-aware")
        if self.max_input_timestamp > self.issue_time:
            raise ValueError("bundle contains post-issue input")
        if len(self.target_timestamps) != TARGET_STEPS or len(self.link_ids) != LINK_COUNT:
            raise ValueError("bundle axes must be exactly 288 steps and 509 links")
        if len(set(self.link_ids)) != LINK_COUNT:
            raise ValueError("bundle link IDs must be unique")
        for name in ("q10_sec", "q50_sec", "q90_sec"):
            value = np.asarray(getattr(self, name), dtype=np.float32)
            if value.shape != (TARGET_STEPS, LINK_COUNT):
                raise ValueError(f"{name} must have shape [288,509]")
            if not np.isfinite(value).all() or np.any(value <= 0):
                raise ValueError(f"{name} must be finite and positive")
            value.setflags(write=False)
            object.__setattr__(self, name, value)
        if np.any(self.q10_sec > self.q50_sec) or np.any(self.q50_sec > self.q90_sec):
            raise ValueError("bundle quantiles cross")
        if not self.causality_pass or self.future_actual_read_count != 0:
            raise ValueError("bundle causality gate failed")

    @property
    def canonical_sha256(self) -> str:
        meta = {
            "forecast_day": self.forecast_day.isoformat(),
            "issue_time": self.issue_time.isoformat(),
            "max_input_timestamp": self.max_input_timestamp.isoformat(),
            "target_timestamps": [value.isoformat() for value in self.target_timestamps],
            "link_ids": list(self.link_ids),
            "model_id": self.model_id,
            "model_sha": self.model_sha,
            "data_sha": self.data_sha,
            "graph_sha": self.graph_sha,
            "normalization_sha": self.normalization_sha,
            "causality_pass": self.causality_pass,
            "future_actual_read_count": self.future_actual_read_count,
        }
        digest = hashlib.sha256(json.dumps(meta, sort_keys=True, separators=(",", ":")).encode())
        for value in (self.q10_sec, self.q50_sec, self.q90_sec):
            digest.update(np.ascontiguousarray(value, dtype="<f4").tobytes())
        return digest.hexdigest()

    def to_link_forecast(self) -> LinkTravelTimeForecast:
        return LinkTravelTimeForecast.from_arrays(
            self.link_ids, self.q10_sec, self.q50_sec, self.q90_sec, self.canonical_sha256
        )

    def save_npz(self, path) -> None:
        meta = json.dumps({
            "forecast_day": self.forecast_day.isoformat(),
            "issue_time": self.issue_time.isoformat(),
            "max_input_timestamp": self.max_input_timestamp.isoformat(),
            "target_timestamps": [value.isoformat() for value in self.target_timestamps],
            "link_ids": list(self.link_ids),
            "model_id": self.model_id,
            "model_sha": self.model_sha,
            "data_sha": self.data_sha,
            "graph_sha": self.graph_sha,
            "normalization_sha": self.normalization_sha,
            "causality_pass": self.causality_pass,
            "future_actual_read_count": self.future_actual_read_count,
            "bundle_sha": self.canonical_sha256,
        }, sort_keys=True)
        np.savez_compressed(path, metadata=np.asarray(meta), Q10_sec=self.q10_sec,
                            Q50_sec=self.q50_sec, Q90_sec=self.q90_sec)
