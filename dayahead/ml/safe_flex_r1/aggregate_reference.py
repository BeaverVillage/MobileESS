"""Correct aggregate projection of the frozen V26 realized-demand envelope."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import conflict_ids, load_h100_source, semantic_flexible_targets
from dayahead.ml.safe_flex.envelope import reference_arrival_tensor
from dayahead.ml.safe_flex.service_set import cumulative_bounds


@dataclass(frozen=True)
class AggregateEnvelope:
    lower: np.ndarray
    upper: np.ndarray


def aggregate_reference(arrivals_gpu_h: np.ndarray) -> AggregateEnvelope:
    """Project separable tier/latency cumulative bounds onto total service.

    The projection is the linear sum over component bounds.  It does not add
    an installed-capacity claim: V26 labels realized service demand, while the
    frozen monthly source-capacity series is only an observed-use lower bound.
    """

    component_lower, component_upper = cumulative_bounds(arrivals_gpu_h)
    lower = component_lower.sum(axis=(1, 2))
    upper = component_upper.sum(axis=(1, 2))
    validate_aggregate(lower, upper)
    return AggregateEnvelope(lower=lower, upper=upper)


def aggregate_component_bounds(lower: np.ndarray, upper: np.ndarray) -> AggregateEnvelope:
    """Project already-computed component bounds onto the aggregate axis."""

    lo = np.asarray(lower, dtype=float).sum(axis=(1, 2))
    hi = np.asarray(upper, dtype=float).sum(axis=(1, 2))
    validate_aggregate(lo, hi)
    return AggregateEnvelope(lower=lo, upper=hi)


def validate_aggregate(lower: np.ndarray, upper: np.ndarray) -> None:
    """Enforce the physical order of a 96-slot cumulative envelope."""

    lo = np.asarray(lower, dtype=float)
    hi = np.asarray(upper, dtype=float)
    if lo.shape != (96,) or hi.shape != (96,):
        raise ValueError(f"V27M_AGGREGATE_SHAPE:{lo.shape}:{hi.shape}")
    if not np.isfinite(lo).all() or not np.isfinite(hi).all():
        raise ValueError("V27M_AGGREGATE_NONFINITE")
    if np.any(lo < -1e-10) or np.any(hi < -1e-10):
        raise ValueError("V27M_AGGREGATE_NEGATIVE")
    if np.any(np.diff(lo) < -1e-9) or np.any(np.diff(hi) < -1e-9):
        raise ValueError("V27M_AGGREGATE_NONMONOTONE")
    if np.any(lo > hi + 1e-9):
        raise ValueError("V27M_AGGREGATE_EMPTY")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_reference_authority(repo: Path) -> tuple[dict[str, object], dict[str, object]]:
    """Build and serialize the all-training-day aggregate reference authority."""

    out = repo / "dayahead/artifacts/v27m_safe_flex_r1"
    raw, source = load_h100_source(min_month=202407, max_month=202503)
    jobs = semantic_flexible_targets(raw, "2024-07-01", "2025-04-01", conflict_ids()).reset_index(drop=True)
    days = pd.date_range("2024-08-19", "2025-03-31", freq="D")
    lower_rows: list[np.ndarray] = []
    upper_rows: list[np.ndarray] = []
    terminal_mass: list[float] = []
    for day in days:
        arrivals = reference_arrival_tensor(jobs, day)
        envelope = aggregate_reference(arrivals)
        lower_rows.append(envelope.lower)
        upper_rows.append(envelope.upper)
        terminal_mass.append(float(arrivals.sum()))
    lower = np.stack(lower_rows)
    upper = np.stack(upper_rows)
    cache = out / "V27M_AGGREGATE_REFERENCE_ALL_DAYS.npz"
    np.savez_compressed(cache, dates=np.asarray(days.strftime("%Y-%m-%d")), lower=lower, upper=upper)
    v26_contract = repo / "dayahead/artifacts/v26m_safe_flex/V26M_SERVICE_SET_CONTRACT.json"
    contract = {
        "artifact_id": "V27M_AGGREGATE_REFERENCE_ENVELOPE_CONTRACT_V1",
        "statistical_target": "AGGREGATE_TEMPORAL_CUMULATIVE_FEASIBLE_ENVELOPE",
        "label": "REFERENCE_AGGREGATE_FEASIBILITY_ENVELOPE_FROM_REALIZED_SERVICE_DEMAND",
        "not_label": "MEASURED_FLEXIBILITY",
        "target_shape_per_day": [96, 2],
        "boundary_values_per_day": 192,
        "legacy_target_shape_per_day": [96, 6, 5, 2],
        "projection": {
            "L_aggregate_t": "sum over tier and latency of V26 deadline-required cumulative lower bounds",
            "U_aggregate_t": "sum over tier and latency of V26 release-limited cumulative upper bounds",
            "mathematical_basis": "linear projection of separable component cumulative bounds onto total cumulative service",
        },
        "capacity_semantics": {
            "monthly_C_src_GPU": "OBSERVED_USE_LOWER_BOUND_NOT_INSTALLED_CAPACITY",
            "used_as_upper_bound": False,
            "reason": "A lower bound on observed source use cannot scientifically serve as an installed-capacity upper bound.",
            "applicable_frozen_upper": "realized release-limited workload mass only",
        },
        "date_range": {"start": "2024-08-19", "end_inclusive": "2025-03-31", "all_days": len(days), "outer_OOF_days": 151},
        "source_service_set_contract": str(v26_contract.relative_to(repo)).replace("\\", "/"),
        "source_service_set_contract_SHA256": _sha256(v26_contract),
        "raw_source_SHA256": source["source_sha256"],
        "cache": str(cache.relative_to(repo)).replace("\\", "/"),
        "cache_SHA256": _sha256(cache),
        "future_service_values_are_labels_only": True,
        "April_reads": 0,
    }
    terminal = np.asarray(terminal_mass)
    validation = {
        "artifact_id": "V27M_AGGREGATE_REFERENCE_VALIDATION_V1",
        "days": len(days),
        "lower_shape": list(lower.shape),
        "upper_shape": list(upper.shape),
        "nonnegative_lower_violations": int(np.sum(lower < -1e-10)),
        "nonnegative_upper_violations": int(np.sum(upper < -1e-10)),
        "lower_monotonicity_violations": int(np.sum(np.diff(lower, axis=1) < -1e-9)),
        "upper_monotonicity_violations": int(np.sum(np.diff(upper, axis=1) < -1e-9)),
        "lower_above_upper_violations": int(np.sum(lower > upper + 1e-9)),
        "terminal_upper_mass_max_abs_error_GPU_h": float(np.max(np.abs(upper[:, -1] - terminal))),
        "terminal_lower_at_most_upper": bool(np.all(lower[:, -1] <= upper[:, -1] + 1e-9)),
        "reference_width_GPU_h_slot_sum": {
            "mean": float(np.mean(np.sum(upper - lower, axis=1))),
            "P05": float(np.quantile(np.sum(upper - lower, axis=1), 0.05)),
            "P50": float(np.quantile(np.sum(upper - lower, axis=1), 0.50)),
            "P95": float(np.quantile(np.sum(upper - lower, axis=1), 0.95)),
        },
        "PASS": bool(
            np.all(lower >= -1e-10)
            and np.all(upper >= -1e-10)
            and np.all(np.diff(lower, axis=1) >= -1e-9)
            and np.all(np.diff(upper, axis=1) >= -1e-9)
            and np.all(lower <= upper + 1e-9)
            and np.max(np.abs(upper[:, -1] - terminal)) <= 1e-9
        ),
    }
    (out / "V27M_AGGREGATE_REFERENCE_ENVELOPE_CONTRACT.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    (out / "V27M_AGGREGATE_REFERENCE_VALIDATION.json").write_text(json.dumps(validation, indent=2) + "\n", encoding="utf-8")
    return contract, validation
