"""Build the PFR3 2024-only joint mobility calibration artifact.

This tool performs no download and reads no 2025 realized labels.  ETA and
energy are coupled only after aggregation to a shared OD-date block.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
from math import ceil, sqrt
from pathlib import Path
from typing import Iterable


HORIZON_STEPS = (1, 3, 6, 12, 18, 24, 36, 54)
ALPHA = 0.05
ETA_SCALE_FLOOR_SECONDS = 1.0
ENERGY_SCALE_FLOOR_KWH = 1e-6
STRESS_FACTORS = (1.10, 1.25)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def wilson_interval(successes: int, count: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if count <= 0:
        raise ValueError("Wilson interval requires observations")
    proportion = successes / count
    denominator = 1.0 + z * z / count
    center = (proportion + z * z / (2.0 * count)) / denominator
    radius = z * sqrt(
        (proportion * (1.0 - proportion) / count) + z * z / (4.0 * count * count)
    ) / denominator
    return max(0.0, center - radius), min(1.0, center + radius)


def summarize_scores(scores: Iterable[float], quantile: float) -> dict[str, float | int]:
    values = tuple(float(value) for value in scores)
    successes = sum(value <= quantile for value in values)
    low, high = wilson_interval(successes, len(values))
    return {
        "block_count": len(values),
        "covered_blocks": successes,
        "empirical_joint_coverage": successes / len(values),
        "wilson95_low": low,
        "wilson95_high": high,
        "maximum_joint_score": max(values),
    }


def build(args: argparse.Namespace) -> dict:
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    ml1 = args.ml1_root
    ml7 = args.ml7_root
    origins_path = ml7 / "eta_store" / "origins.int64.npy"
    truth_path = ml7 / "eta_store" / "td_eta_truth.float32.npy"
    quantiles_path = ml7 / "eta_store" / "td_eta_quantiles.float32.npy"
    ordinal_path = ml1 / "tensor_store" / "date_ordinal_5m.int32.npy"

    origins = np.load(origins_path)
    ordinals = np.load(ordinal_path, mmap_mode="r")
    eta_truth = np.load(truth_path, mmap_mode="r")
    eta_quantiles = np.load(quantiles_path, mmap_mode="r")
    if eta_truth.shape != (len(origins), len(HORIZON_STEPS), 1656):
        raise ValueError(f"unexpected ETA truth shape: {eta_truth.shape}")
    if eta_quantiles.shape != eta_truth.shape + (3,):
        raise ValueError(f"unexpected ETA quantile shape: {eta_quantiles.shape}")

    origins_by_date: dict[str, list[int]] = defaultdict(list)
    for position, origin in enumerate(origins):
        origin_date = str(date.fromordinal(int(ordinals[int(origin)])))
        if not origin_date.startswith("2024-"):
            raise ValueError("non-2024 ETA origin entered PFR3 calibration authority")
        origins_by_date[origin_date].append(position)

    columns = [
        "date",
        "split",
        "od_index",
        "path_rank",
        "operational_net_energy_aux_aligned_kWh",
        "v22_move_energy_q50_kWh",
        "residual_scale_kWh",
        "energy_horizon_steps",
    ]
    energy = pq.read_table(args.energy_parquet, columns=columns).to_pandas()
    energy = energy[energy["date"].str.startswith("2024-")].copy()
    if set(energy["split"]) != {"calibration", "temporal_audit", "spatial_audit"}:
        raise ValueError("unexpected 2024 energy split identities")

    row_records: list[dict] = []
    horizon_array = np.asarray(HORIZON_STEPS)
    for row in energy.itertuples(index=False):
        positions = np.asarray(origins_by_date.get(row.date, ()), dtype=int)
        if positions.size == 0:
            raise ValueError(f"no 2024 ETA origins for energy date {row.date}")
        horizon_index = int(
            np.argmin(np.abs(horizon_array - int(row.energy_horizon_steps)))
        )
        route_index = int(row.od_index) * 3 + int(row.path_rank) - 1
        if not 0 <= route_index < 1656:
            raise ValueError("native K=3 route index is outside the frozen route universe")

        actual_eta = np.asarray(
            eta_truth[positions, horizon_index, route_index], dtype=float
        )
        eta_q50 = np.asarray(
            eta_quantiles[positions, horizon_index, route_index, 1], dtype=float
        )
        eta_q90 = np.asarray(
            eta_quantiles[positions, horizon_index, route_index, 2], dtype=float
        )
        eta_scale = np.maximum(eta_q90 - eta_q50, ETA_SCALE_FLOOR_SECONDS)
        eta_score = float(np.max((actual_eta - eta_q50) / eta_scale))

        energy_scale = max(float(row.residual_scale_kWh), ENERGY_SCALE_FLOOR_KWH)
        energy_score = (
            float(row.operational_net_energy_aux_aligned_kWh)
            - float(row.v22_move_energy_q50_kWh)
        ) / energy_scale
        row_records.append(
            {
                "date": row.date,
                "split": row.split,
                "od_index": int(row.od_index),
                "eta_score": eta_score,
                "energy_score": energy_score,
                "joint_score": max(eta_score, energy_score),
            }
        )

    rows = pd.DataFrame(row_records)
    blocks = (
        rows.groupby(["date", "split", "od_index"], as_index=False)[
            ["eta_score", "energy_score", "joint_score"]
        ]
        .max()
        .sort_values(["date", "od_index"])
    )
    calibration_scores = sorted(
        blocks.loc[blocks["split"] == "calibration", "joint_score"].astype(float)
    )
    rank = min(ceil((len(calibration_scores) + 1) * (1.0 - ALPHA)), len(calibration_scores))
    joint_quantile = calibration_scores[rank - 1]

    split_summaries = {
        split: summarize_scores(group["joint_score"], joint_quantile)
        for split, group in blocks.groupby("split")
    }
    stress = {}
    for factor in STRESS_FACTORS:
        stress[str(factor)] = {}
        for split, group in blocks.groupby("split"):
            stressed = np.maximum(
                group["eta_score"].to_numpy(dtype=float) * factor,
                group["energy_score"].to_numpy(dtype=float) * factor,
            )
            stress[str(factor)][split] = summarize_scores(stressed, joint_quantile)

    audit_targets_include_95 = all(
        summary["wilson95_low"] <= 0.95 <= summary["wilson95_high"]
        for split, summary in split_summaries.items()
        if split != "calibration"
    )
    stage_pass = (
        len(calibration_scores) == 96
        and rank == 93
        and split_summaries["calibration"]["empirical_joint_coverage"] >= 0.95
        and audit_targets_include_95
    )

    return {
        "stage": "PFR3",
        "status": "PASS" if stage_pass else "FAIL",
        "authority": "2024_CALIBRATION_ONLY_OD_DATE_BLOCK_JOINT_CONFORMAL",
        "target_joint_coverage": 0.95,
        "alpha": ALPHA,
        "score": "max((T_actual-T_q50)/max(T_q90-T_q50,1s),(E_actual-E_q50)/residual_scale_E)",
        "block_aggregation": "maximum_within_shared_OD_date_block",
            "row_wise_cross_dataset_merge": False,
        "calibration": {
            "year": 2024,
            "split": "calibration",
            "row_count": int((energy["split"] == "calibration").sum()),
            "block_count": len(calibration_scores),
            "finite_sample_rank": rank,
            "joint_quantile": joint_quantile,
            "fallback": "global_2024_OD_date_block_quantile",
        },
        "empirical_coverage": split_summaries,
        "distribution_shift_residual_inflation": stress,
        "uncertainty_universe_interface": "U_t = U_mob x U_work x U_grid",
        "source_shapes": {
            "eta_origins": int(len(origins)),
            "eta_truth": list(eta_truth.shape),
            "eta_quantiles": list(eta_quantiles.shape),
            "energy_2024_rows": int(len(energy)),
            "joint_OD_date_blocks": int(len(blocks)),
        },
        "source_sha256": {
            "origins": sha256(origins_path),
            "eta_truth": sha256(truth_path),
            "eta_quantiles": sha256(quantiles_path),
            "date_ordinals": sha256(ordinal_path),
            "energy_v4": sha256(args.energy_parquet),
        },
        "no_2025_retuning": True,
        "next_authorized_stage": "PFR4" if stage_pass else None,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ml1-root", type=Path, required=True)
    parser.add_argument("--ml7-root", type=Path, required=True)
    parser.add_argument("--energy-parquet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build(args)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "status": result["status"],
        "joint_quantile": result["calibration"]["joint_quantile"],
        "output": str(args.output),
    }))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
