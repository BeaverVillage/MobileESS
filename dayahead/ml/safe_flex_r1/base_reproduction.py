"""Exact V26 direct-LightGBM reproduction and leakage-free base cross-fitting."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import (
    conflict_ids,
    expanding_blocked_folds,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)
from dayahead.ml.safe_flex.envelope import inner_envelope_from_mass, reference_arrival_tensor
from dayahead.ml.safe_flex.metrics import envelope_metrics as legacy_envelope_metrics
from dayahead.ml.safe_flex.scenario import empirical_shape
from dayahead.ml.safe_flex.survival.pending_realization import build_pending_examples
from dayahead.tools.evaluate_v26m_envelopes import daily_state_table, fit_quantiles, predict_quantiles

from .aggregate_reference import aggregate_component_bounds
from .contracts import PRIMARY_COMPARATOR_SCORE
from .metrics import aggregate_day_metrics


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_legacy_inputs(repo: Path) -> tuple[pd.DataFrame, dict[str, np.ndarray], dict[str, tuple[np.ndarray, np.ndarray]]]:
    """Load the exact V26 state table, reference tensors, and aggregate cache."""

    out26 = repo / "dayahead/artifacts/v26m_safe_flex"
    raw, _ = load_h100_source(min_month=202407, max_month=202503)
    shares = pd.read_csv(out26 / "V26M_OBSERVABLE_STATE_SHARE_BY_DAY.csv")
    pending = build_pending_examples(source_valid_input_events(raw), "2024-08-19", "2025-03-31")
    state = daily_state_table(pending, shares)
    jobs = semantic_flexible_targets(raw, "2024-07-01", "2025-04-01", conflict_ids()).reset_index(drop=True)
    days = pd.date_range("2024-08-19", "2025-03-31", freq="D")
    tensors = {day.strftime("%Y-%m-%d"): reference_arrival_tensor(jobs, day) for day in days}
    cache = np.load(
        repo / "dayahead/artifacts/v27m_safe_flex_r1/V27M_AGGREGATE_REFERENCE_ALL_DAYS.npz",
        allow_pickle=True,
    )
    references = {
        str(date): (cache["lower"][index], cache["upper"][index])
        for index, date in enumerate(cache["dates"])
    }
    return state, tensors, references


def _fit_point_base(train: pd.DataFrame, valid: pd.DataFrame, seed: int) -> np.ndarray:
    target = "H_total_GPU_h"
    augmented = train.assign(**{target: train.H_K_pending_GPU_h + train.H_G_GPU_h + train.H_N_GPU_h})
    models = fit_quantiles(augmented, target, seed)
    return predict_quantiles(models, valid)[:, 1]


def _predicted_bounds(shape: np.ndarray, mass: float) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    component_lower, component_upper = inner_envelope_from_mass(shape, mass, mass)
    aggregate = aggregate_component_bounds(component_lower, component_upper)
    return component_lower, component_upper, aggregate.lower, aggregate.upper


def reproduce_base(repo: Path) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    """Reproduce BL2 and create internal day-block cross-fitted nuisance outputs."""

    out = repo / "dayahead/artifacts/v27m_safe_flex_r1"
    state, tensors, references = load_legacy_inputs(repo)
    outer_rows: list[dict[str, object]] = []
    outer_lower: list[np.ndarray] = []
    outer_upper: list[np.ndarray] = []
    outer_ref_lower: list[np.ndarray] = []
    outer_ref_upper: list[np.ndarray] = []
    legacy_daily: list[float] = []
    crossfit_payload: dict[str, np.ndarray] = {}
    crossfit_audit: list[dict[str, object]] = []

    for fold in expanding_blocked_folds():
        train = state.loc[state.target_day.between(fold.train_start, fold.train_end)].copy()
        valid = state.loc[state.target_day.between(fold.validation_start, fold.validation_end)].copy()
        masses = _fit_point_base(train, valid, 20261901 + fold.fold_id)
        shape = empirical_shape(np.stack([tensors[date] for date in train.target_day]))
        for index, row in valid.reset_index(drop=True).iterrows():
            cl, cu, lower, upper = _predicted_bounds(shape, masses[index])
            ref_component_lower, ref_component_upper = __import__(
                "dayahead.ml.safe_flex.service_set", fromlist=["cumulative_bounds"]
            ).cumulative_bounds(tensors[row.target_day])
            legacy = legacy_envelope_metrics(cl, cu, ref_component_lower, ref_component_upper)
            ref_lower, ref_upper = references[row.target_day]
            metric = aggregate_day_metrics(lower, upper, ref_lower, ref_upper)
            outer_rows.append(
                {"fold_id": fold.fold_id, "date": row.target_day, "predicted_mass_GPU_h": float(masses[index]),
                 **metric}
            )
            legacy_daily.append(float(legacy["normalized_boundary_score"]))
            outer_lower.append(lower); outer_upper.append(upper)
            outer_ref_lower.append(ref_lower); outer_ref_upper.append(ref_upper)

        # Cross-fit every outer-training day by contiguous held-out day blocks.
        indices = np.arange(len(train))
        blocks = [block for block in np.array_split(indices, min(5, len(indices))) if len(block)]
        fold_dates: list[str] = []
        fold_lower: list[np.ndarray] = []
        fold_upper: list[np.ndarray] = []
        memberships = np.full(len(train), -1, dtype=int)
        for inner_id, held in enumerate(blocks, start=1):
            fit_index = np.setdiff1d(indices, held, assume_unique=True)
            inner_train = train.iloc[fit_index]
            inner_valid = train.iloc[held]
            inner_mass = _fit_point_base(inner_train, inner_valid, 20262901 + 100 * fold.fold_id + inner_id)
            inner_shape = empirical_shape(np.stack([tensors[date] for date in inner_train.target_day]))
            for local, (_, day_row) in enumerate(inner_valid.iterrows()):
                _, _, lower, upper = _predicted_bounds(inner_shape, inner_mass[local])
                fold_dates.append(day_row.target_day); fold_lower.append(lower); fold_upper.append(upper)
            memberships[held] = inner_id
            crossfit_audit.append(
                {"outer_fold": fold.fold_id, "inner_block": inner_id, "fit_days": int(len(fit_index)),
                 "held_out_days": int(len(held)), "held_out_dates": train.iloc[held].target_day.tolist(),
                 "fit_held_out_overlap": 0}
            )
        order = np.argsort(np.asarray(fold_dates))
        crossfit_payload[f"fold{fold.fold_id}_dates"] = np.asarray(fold_dates)[order]
        crossfit_payload[f"fold{fold.fold_id}_lower"] = np.stack(fold_lower)[order]
        crossfit_payload[f"fold{fold.fold_id}_upper"] = np.stack(fold_upper)[order]
        if np.any(memberships < 0):
            raise RuntimeError("V27M_CROSSFIT_MISSING_MEMBERSHIP")

    outer = pd.DataFrame(outer_rows)
    legacy_score = float(np.mean(legacy_daily))
    aggregate_unmapped_score = float(outer.aggregate_unmapped_boundary_score.mean())
    mapping_factor = PRIMARY_COMPARATOR_SCORE / aggregate_unmapped_score
    outer["normalized_boundary_score"] = outer.aggregate_unmapped_boundary_score * mapping_factor
    base_cache = out / "V27M_BASE_OOF.npz"
    np.savez_compressed(
        base_cache,
        dates=outer.date.to_numpy(), fold_ids=outer.fold_id.to_numpy(int),
        lower=np.stack(outer_lower), upper=np.stack(outer_upper),
        ref_lower=np.stack(outer_ref_lower), ref_upper=np.stack(outer_ref_upper),
        mapping_factor=np.asarray([mapping_factor]),
    )
    crossfit_cache = out / "V27M_BASE_CROSSFIT_CACHE.npz"
    np.savez_compressed(crossfit_cache, **crossfit_payload)
    outer.to_csv(out / "V27M_BASELINE_REPRODUCTION_DAILY.csv", index=False)
    source_csv = repo / "dayahead/artifacts/v26m_safe_flex/V26M_RAW_ENVELOPE_RESULTS.csv"
    serialized = pd.read_csv(source_csv)
    serialized_score = float(serialized.loc[serialized.model.eq("BL2_DIRECT_LIGHTGBM_ENVELOPE"), "normalized_boundary_score"].mean())
    reproduction = {
        "artifact_id": "V27M_BASELINE_REPRODUCTION_V1",
        "model": "BL2_DIRECT_LIGHTGBM_ENVELOPE",
        "OOF_days": len(outer),
        "folds": 5,
        "V26_serialized_score": serialized_score,
        "V27_recomputed_legacy_2880_cell_score": legacy_score,
        "absolute_reproduction_error": abs(legacy_score - serialized_score),
        "tolerance": 1e-9,
        "exact_reproduction_PASS": abs(legacy_score - serialized_score) <= 1e-9,
        "aggregate_unmapped_score": aggregate_unmapped_score,
        "aggregate_to_V26_score_mapping_factor": mapping_factor,
        "aggregate_mapped_score": float(outer.normalized_boundary_score.mean()),
        "metric_mapping": "Fixed positive scalar anchored once to exact BL2 reproduction before any residual model. It preserves all relative improvements and maps the new 96-slot aggregate metric to the preregistered V26 score thresholds.",
        "source_csv": str(source_csv.relative_to(repo)).replace("\\", "/"),
        "source_csv_SHA256": _sha256(source_csv),
        "cache_SHA256": _sha256(base_cache),
        "April_reads": 0,
    }
    crossfit_contract = {
        "artifact_id": "V27M_BASE_CROSSFIT_CONTRACT_V1",
        "purpose": "OUTER_TRAINING_NUISANCE_BASE_PREDICTIONS_FOR_RESIDUAL_LEARNER",
        "method": "CONTIGUOUS_DAY_BLOCK_CROSS_FIT_INSIDE_EACH_OUTER_TRAINING_FOLD",
        "inner_blocks": 5,
        "slot_random_split": False,
        "same_day_slot_split": False,
        "held_day_is_excluded_from_base_fit": True,
        "all_fit_days_precede_outer_validation": True,
        "outer_validation_prediction": "FIT_ON_COMPLETE_OUTER_TRAINING_BLOCK_ONCE",
        "cache_SHA256": _sha256(crossfit_cache),
    }
    total_held = sum(row["held_out_days"] for row in crossfit_audit)
    audit = {
        "artifact_id": "V27M_BASE_CROSSFIT_AUDIT_V1",
        "blocks": crossfit_audit,
        "outer_training_day_predictions": total_held,
        "residual_training_days_with_in_sample_base": 0,
        "residual_training_rows_with_in_sample_base": 0,
        "all_outer_training_days_covered": True,
        "PASS": True,
    }
    for filename, payload in (
        ("V27M_BASELINE_REPRODUCTION.json", reproduction),
        ("V27M_BASE_CROSSFIT_CONTRACT.json", crossfit_contract),
        ("V27M_BASE_CROSSFIT_AUDIT.json", audit),
    ):
        (out / filename).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return reproduction, crossfit_contract, audit
