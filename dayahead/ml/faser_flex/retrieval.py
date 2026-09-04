"""Past-only historical analog retrieval with auditable distances and weights."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RetrievalConfig:
    """One preregistered neighbor-count and temperature configuration."""

    name: str
    neighbors: int
    temperature: float


RETRIEVAL_CONFIGS = {
    "RET-A": RetrievalConfig("RET-A", 10, 0.5),
    "RET-B": RetrievalConfig("RET-B", 20, 0.5),
    "RET-C": RetrievalConfig("RET-C", 20, 1.0),
    "RET-D": RetrievalConfig("RET-D", 30, 1.0),
}


@dataclass(frozen=True)
class AnalogResult:
    """Past-only neighbor indices, distances, weights, and reliability diagnostics."""

    indices: np.ndarray
    dates: tuple[str, ...]
    distances: np.ndarray
    weights: np.ndarray
    nearest_distance: float
    effective_neighbors: float
    outcome_cv: float
    analog_age_days: np.ndarray
    weekday_match_rate: float


def _standardized_distance(train: np.ndarray, query: np.ndarray) -> np.ndarray:
    """Return RMS Euclidean distance after training-library standardization."""

    scale = np.maximum(np.std(train, axis=0), 1e-6)
    return np.sqrt(np.mean(((train - query) / scale) ** 2, axis=1))


def retrieve_analogs(
    library_dates: list[str],
    signature_features: np.ndarray,
    macro_features: np.ndarray,
    calendar_features: np.ndarray,
    outcomes: np.ndarray,
    query_date: str,
    query_signature: np.ndarray,
    query_macro: np.ndarray,
    query_calendar: np.ndarray,
    config: RetrievalConfig,
) -> AnalogResult:
    """Retrieve weighted analogs strictly earlier than the forecast date."""

    eligible = np.asarray([date < query_date for date in library_dates], dtype=bool)
    if not np.any(eligible):
        raise RuntimeError(f"V24M_NO_PAST_ANALOGS:{query_date}")
    original_indices = np.flatnonzero(eligible)
    sig_distance = _standardized_distance(signature_features[eligible], query_signature)
    macro_distance = _standardized_distance(macro_features[eligible], query_macro)
    calendar_distance = _standardized_distance(calendar_features[eligible], query_calendar)
    distance = 0.50 * sig_distance + 0.35 * macro_distance + 0.15 * calendar_distance
    count = min(config.neighbors, len(distance))
    local = np.argsort(distance)[:count]
    indices = original_indices[local]
    selected_distance = distance[local]
    logits = -(selected_distance - selected_distance.min()) / config.temperature
    weights = np.exp(logits)
    weights /= weights.sum()
    selected_outcomes = outcomes[indices]
    mean = float(np.dot(weights, selected_outcomes))
    dispersion = float(
        np.sqrt(np.dot(weights, (selected_outcomes - mean) ** 2)) / max(abs(mean), 1e-12)
    )
    query_day = np.datetime64(query_date)
    ages = np.asarray(
        [(query_day - np.datetime64(library_dates[index])).astype(int) for index in indices],
        dtype=float,
    )
    query_weekday = int(query_day.astype("datetime64[D]").astype(int) % 7)
    analog_weekdays = np.asarray(
        [int(np.datetime64(library_dates[index]).astype("datetime64[D]").astype(int) % 7) for index in indices]
    )
    return AnalogResult(
        indices=indices,
        dates=tuple(library_dates[index] for index in indices),
        distances=selected_distance,
        weights=weights,
        nearest_distance=float(selected_distance[0]),
        effective_neighbors=float(1.0 / np.sum(weights**2)),
        outcome_cv=dispersion,
        analog_age_days=ages,
        weekday_match_rate=float(np.mean(analog_weekdays == query_weekday)),
    )
