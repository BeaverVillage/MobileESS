from __future__ import annotations

import logging
import math

import pandas as pd

from .context import PipelineContext


QUANTILES = {"low": 0.10, "median": 0.50, "high": 0.90}


def build_paired_power_scenarios(
    ctx: PipelineContext, logger: logging.Logger
) -> pd.DataFrame:
    if ctx.stage_k4b_source_dir is None:
        return pd.DataFrame()

    feature_path = (
        ctx.stage_k4b_source_dir / "outputs/nlr_genai_run_power_features.csv"
    )
    mapping_path = (
        ctx.stage_k4b_source_dir
        / "outputs/training_kestrel_mapping_parameters.csv"
    )
    features = pd.read_csv(feature_path)
    mapping = pd.read_csv(mapping_path)
    training = features.loc[
        features["family_id"].astype(str).eq("training")
    ].copy()
    for column in [
        "gpu_count_configured",
        "gross_mean_kw_per_gpu",
        "incremental_mean_kw_per_gpu",
    ]:
        training[column] = pd.to_numeric(training[column], errors="coerce")
    training = (
        training.dropna(
            subset=["gross_mean_kw_per_gpu", "incremental_mean_kw_per_gpu"]
        )
        .sort_values(["gross_mean_kw_per_gpu", "run_id"])
        .reset_index(drop=True)
    )
    if training.empty:
        raise ValueError("No training runs available for paired power scenarios")

    independent = mapping.set_index("scenario")
    rows: list[dict] = []
    count = len(training)
    for scenario, quantile in QUANTILES.items():
        rank = max(0, min(count - 1, math.ceil(quantile * count) - 1))
        row = training.iloc[rank]
        gross = float(row["gross_mean_kw_per_gpu"])
        incremental = float(row["incremental_mean_kw_per_gpu"])
        idle = gross - incremental
        rows.append(
            {
                "scenario": scenario,
                "quantile": quantile,
                "paired_run_rank_zero_based": rank,
                "paired_run_id": row["run_id"],
                "model_family": row.get("model_family"),
                "nodes": row.get("nodes"),
                "gpu_count_configured": row.get("gpu_count_configured"),
                "gross_it_kw_per_gpu": gross,
                "incremental_it_kw_per_gpu": incremental,
                "idle_it_kw_per_gpu": idle,
                "identity_error_kw_per_gpu": abs(gross - incremental - idle),
                "independent_gross_kw_per_gpu": float(
                    independent.loc[scenario, "gross_mean_kw_per_gpu"]
                ),
                "independent_incremental_kw_per_gpu": float(
                    independent.loc[scenario, "incremental_mean_kw_per_gpu"]
                ),
                "method": "gross_order_statistic_paired_run",
                "interpretation": (
                    "Gross, incremental, and idle values are retained from one "
                    "empirical NLR training run."
                ),
            }
        )
    result = pd.DataFrame(rows)
    result.to_csv(
        ctx.output_dir / "paired_training_power_scenarios.csv",
        index=False,
        encoding="utf-8-sig",
    )
    logger.info(
        "Paired NLR training-power scenarios generated from %d runs", count
    )
    return result
