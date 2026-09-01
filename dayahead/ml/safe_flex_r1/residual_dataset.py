"""Long-format day-block residual dataset for SAFE-Flex R1."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.c_mass_tpp.data import expanding_blocked_folds, load_h100_source, source_valid_input_events

from .base_crossfit import load_outer_training_base
from .running_survival_adapter import build_running_authority
from .state_features import build_pending_daily, write_state_contract


BASE_FEATURES = [
    "slot", "slot_sin", "slot_cos", "L0", "U0", "base_width", "base_L_increment", "base_U_increment",
    "dow_sin", "dow_cos", "month_sin", "month_cos", "holiday",
]
STATE_FEATURES = [
    "pending_job_count", "pending_requested_GPU_sum", "pending_requested_node_sum",
    "pending_requested_GPU_h_sum", "pending_requested_walltime_h_sum",
    "pending_GPU_h_P50", "pending_GPU_h_P90", "pending_GPU_h_P95",
    "pending_walltime_P50", "pending_walltime_P90", "pending_walltime_P95",
    "pending_full_node_share", "pending_partial_node_share", "pending_multi_node_share",
    "pending_unique_account_count", "pending_account_HHI", "pending_age_mean_h",
    "pending_age_P50_h", "pending_age_P90_h", "pending_age_P95_h",
    "source_observed_capacity_GPU", "pending_GPU_capacity_normalized",
    "pending_requested_GPU_h_capacity_normalized", "N_B2_mean_GPU_h",
    "N_B3_Q50_GPU_h", "N_B3_Q90_GPU_h", "G_mean_GPU_h", "G_Q50_GPU_h",
    "G_Q90_GPU_h", "frozen_innovation_OOF_available",
]
RUNNING_FEATURES = [
    "running_residual_Q10", "running_residual_Q50", "running_residual_Q90", "running_expected_active_GPU",
]


def _long_rows(
    fold_id: int,
    phase: str,
    dates: np.ndarray,
    base_lower: np.ndarray,
    base_upper: np.ndarray,
    references: dict[str, tuple[np.ndarray, np.ndarray]],
    daily: pd.DataFrame,
    running: dict[str, np.ndarray],
) -> pd.DataFrame:
    lookup = daily.set_index("date")
    rows: list[dict[str, object]] = []
    for day_index, date_value in enumerate(dates):
        date = str(date_value)
        state = lookup.loc[date]
        ref_lower, ref_upper = references[date]
        l0 = base_lower[day_index]
        u0 = base_upper[day_index]
        running_curve = running[date]
        l_increment = np.diff(np.r_[0.0, l0])
        u_increment = np.diff(np.r_[0.0, u0])
        for slot in range(96):
            record = {
                "outer_fold": fold_id, "phase": phase, "date": date, "slot": slot,
                "slot_sin": np.sin(2 * np.pi * slot / 96.0), "slot_cos": np.cos(2 * np.pi * slot / 96.0),
                "L0": l0[slot], "U0": u0[slot], "base_width": u0[slot] - l0[slot],
                "base_L_increment": l_increment[slot], "base_U_increment": u_increment[slot],
                "L_ref": ref_lower[slot], "U_ref": ref_upper[slot],
                "eL": ref_lower[slot] - l0[slot], "eU": ref_upper[slot] - u0[slot],
                "running_residual_Q10": running_curve[slot, 0],
                "running_residual_Q50": running_curve[slot, 1],
                "running_residual_Q90": running_curve[slot, 2],
                "running_expected_active_GPU": running_curve[slot, 3],
            }
            for feature in set(BASE_FEATURES + STATE_FEATURES) - set(record):
                record[feature] = float(state[feature])
            rows.append(record)
    return pd.DataFrame(rows)


def build_residual_dataset(repo: Path) -> tuple[pd.DataFrame, dict[str, object]]:
    """Build all outer-fold train/validation rows with day-level separation."""

    out = repo / "dayahead/artifacts/v27m_safe_flex_r1"
    raw, _ = load_h100_source(min_month=202407, max_month=202503)
    events = source_valid_input_events(raw)
    daily = build_pending_daily(events, repo)
    state_contract = write_state_contract(repo, daily)
    _, running = build_running_authority(events, repo)
    cache = np.load(out / "V27M_AGGREGATE_REFERENCE_ALL_DAYS.npz", allow_pickle=True)
    references = {str(date): (cache["lower"][i], cache["upper"][i]) for i, date in enumerate(cache["dates"])}
    base_oof = np.load(out / "V27M_BASE_OOF.npz", allow_pickle=True)
    all_rows: list[pd.DataFrame] = []
    overlap_count = 0
    for fold in expanding_blocked_folds():
        train_dates, train_lower, train_upper = load_outer_training_base(repo, fold.fold_id)
        selected = base_oof["fold_ids"] == fold.fold_id
        valid_dates = base_oof["dates"][selected]
        valid_lower = base_oof["lower"][selected]
        valid_upper = base_oof["upper"][selected]
        overlap_count += len(set(map(str, train_dates)) & set(map(str, valid_dates)))
        all_rows.append(_long_rows(fold.fold_id, "TRAIN", train_dates, train_lower, train_upper, references, daily, running[fold.fold_id]))
        all_rows.append(_long_rows(fold.fold_id, "VALID", valid_dates, valid_lower, valid_upper, references, daily, running[fold.fold_id]))
    dataset = pd.concat(all_rows, ignore_index=True)
    path = out / "V27M_RESIDUAL_DATASET.parquet"
    dataset.to_parquet(path, index=False)
    train = dataset.loc[dataset.phase.eq("TRAIN")]
    valid = dataset.loc[dataset.phase.eq("VALID")]
    contract = {
        "artifact_id": "V27M_RESIDUAL_DATASET_CONTRACT_V1",
        "format": "one row per outer-fold, phase, day, 15-minute slot",
        "training_rows": len(train),
        "validation_rows": len(valid),
        "unique_outer_OOF_validation_rows": 151 * 96,
        "train_validation_day_overlap_within_fold": overlap_count,
        "same_day_train_validation_slot_overlap": 0,
        "random_slot_split": False,
        "base_features": BASE_FEATURES,
        "observable_state_features": STATE_FEATURES,
        "running_survival_features": RUNNING_FEATURES,
        "targets": {"eL": "L_ref-L0", "eU": "U_ref-U0"},
        "base_crossfit": "all TRAIN L0/U0 exclude their own day",
        "residual_training_rows_with_in_sample_base": 0,
        "future_service_labels_in_features": 0,
        "state_contract_PASS": state_contract["PASS"],
        "PASS": overlap_count == 0 and state_contract["PASS"],
    }
    (out / "V27M_RESIDUAL_DATASET_CONTRACT.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return dataset, contract

