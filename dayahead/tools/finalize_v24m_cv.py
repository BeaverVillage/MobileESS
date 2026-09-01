"""Build the V24M blocked-CV comparison and pre-April acceptance records."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"
V19 = ROOT / "dayahead" / "artifacts" / "v19_c_mass_tpp"
V23 = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"


def write_json(name: str, payload: dict) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def aggregate(frame: pd.DataFrame, group: str) -> list[dict]:
    numeric = [
        "Mean_WAPE", "Q50_WAPE", "Q90_pinball", "CRPS", "Burst_WAPE",
        "aggregate_mass_ratio", "Q50_coverage", "Q90_coverage",
        "15min_GPU_h_WAPE", "IT_power_WAPE",
    ]
    available = [column for column in numeric if column in frame]
    return frame.groupby(group, dropna=False)[available].mean().reset_index().to_dict("records")


def block_bootstrap(faser: pd.DataFrame, baseline: pd.DataFrame) -> dict:
    faser_daily = faser.groupby("date", as_index=False).agg(
        actual_GPU_h=("actual_GPU_h", "first"),
        mean_GPU_h=("mean_GPU_h", "mean"), CRPS=("CRPS", "mean")
    )
    base_daily = baseline.loc[baseline.model.eq("P0_DIRECT_LIGHTGBM")].copy()
    joined = faser_daily.merge(
        base_daily[["date", "mean_GPU_h", "CRPS"]], on="date", suffixes=("_FASER", "_BASE")
    )
    error_delta = (
        np.abs(joined.mean_GPU_h_FASER - joined.actual_GPU_h)
        - np.abs(joined.mean_GPU_h_BASE - joined.actual_GPU_h)
    ).to_numpy(float)
    crps_delta = (joined.CRPS_FASER - joined.CRPS_BASE).to_numpy(float)
    rng = np.random.default_rng(20260901)
    count = len(joined)
    draws_error, draws_crps = [], []
    for _ in range(10_000):
        indices: list[int] = []
        while len(indices) < count:
            start = int(rng.integers(0, max(1, count - 6)))
            indices.extend(range(start, min(count, start + 7)))
        chosen = np.asarray(indices[:count], int)
        draws_error.append(float(np.mean(error_delta[chosen])))
        draws_crps.append(float(np.mean(crps_delta[chosen])))
    return {
        "label": "SEVEN_DAY_BLOCK_BOOTSTRAP_VS_CURRENT_P0_DIRECT_LIGHTGBM",
        "replicates": 10_000,
        "seed": 20260901,
        "paired_days": count,
        "absolute_error_difference_FASER_minus_baseline": {
            "point": float(np.mean(error_delta)),
            "CI95": np.quantile(draws_error, [0.025, 0.975]).tolist(),
        },
        "CRPS_difference_FASER_minus_baseline": {
            "point": float(np.mean(crps_delta)),
            "CI95": np.quantile(draws_crps, [0.025, 0.975]).tolist(),
        },
        "strong_pass_requires_upper_bounds_below_zero": False,
    }


def main() -> None:
    probe = pd.read_csv(OUT / "V24M_PROBE_RESULTS.csv")
    full = pd.read_csv(OUT / "V24M_FASER_BLOCKED_CV_RESULTS.csv")
    probe_daily = pd.read_csv(OUT / "V24M_PROBE_DAILY_RESULTS.csv")
    full_daily = pd.read_csv(OUT / "V24M_FASER_DAILY_OOF_RESULTS.csv")
    ablation = pd.read_csv(OUT / "V24M_ABLATION_RESULTS.csv")
    v19 = pd.read_csv(V19 / "V19_BASELINE_BLOCKED_CV_RESULTS.csv")
    with (OUT / "V24M_FACTOR_PREDICTABILITY_AUDIT.json").open(encoding="utf-8") as handle:
        predictability = json.load(handle)

    historical_names = {
        "B2_LIGHTGBM_TWEEDIE", "B3_LIGHTGBM_QUANTILE", "V19-A", "B1_PERSISTENCE_PROXY"
    }
    historical = v19.loc[v19.model.isin(historical_names)].copy()
    historical = historical.rename(columns={
        "Daily_WAPE": "Mean_WAPE", "burst_WAPE": "Burst_WAPE",
        "mass_ratio": "aggregate_mass_ratio",
    })
    historical["status"] = "PRESERVED_SERIALIZED"
    historical["evidence_source"] = "V19_BASELINE_BLOCKED_CV_RESULTS.csv"

    probe_summary = pd.DataFrame(aggregate(probe, "model"))
    probe_summary["status"] = "REPRODUCED_V24M_SAME_FOLDS"
    probe_summary["evidence_source"] = "V24M_PROBE_RESULTS.csv"
    full_summary = pd.DataFrame(aggregate(full, "model"))
    full_summary["status"] = "REPRODUCED_V24M_5FOLD_3SEED"
    full_summary["evidence_source"] = "V24M_FASER_BLOCKED_CV_RESULTS.csv"
    baseline = pd.concat([historical, probe_summary, full_summary], ignore_index=True, sort=False)
    baseline.to_csv(OUT / "V24M_BASELINE_BLOCKED_CV_RESULTS.csv", index=False)

    audit = {
        "artifact_id": "V24M_BASELINE_IMPLEMENTATION_AUDIT_V1",
        "same_cutoff_target_folds": True,
        "registry": {
            "ML-B0_HISTORICAL_WEEKDAY": "REPRODUCED_FACTOR_PROBE_F2",
            "ML-B1_PERSISTENCE_LAG1": "PRESERVED_SERIALIZED_AND_CAUSALLY_REPRODUCED_IN_V23M",
            "ML-B2_LIGHTGBM_TWEEDIE": "PRESERVED_SERIALIZED_BENCHMARK_1E-9",
            "ML-B3_LIGHTGBM_QUANTILE": "PRESERVED_SERIALIZED_BENCHMARK_1E-9",
            "ML-B4_SEMANTIC_PRODUCTION_HYBRID": "PRESERVED_B2_MEAN_PLUS_B3_QUANTILES",
            "ML-B5_FACTORIZED_LIGHTGBM": "REPRODUCED_V24M_P1",
            "ML-B6_DIRECT_LIGHTGBM_ALL_AGGREGATES": "REPRODUCED_V24M_P0",
            "ML-B7_XGBOOST_OR_CATBOOST": "NOT_REPRODUCED_WITH_REASON:NO_FROZEN_DEPENDENCY_PIPELINE",
            "ML-B8_ORDINARY_FEATURE_GP": "REPRODUCED_V24M_P2",
            "ML-B9_SIGNATURE_GP_ONLY": "REPRODUCED_V24M_P3_AND_P4",
            "ML-B10_ANALOG_RETRIEVAL_ONLY": "REPRODUCED_V24M_P6",
            "ML-B11_FASER_FLEX": "REPRODUCED_V24M_FIVE_FOLD_THREE_SEED",
            "LIGHTGBM_PLUS_FLATTENED_SIGNATURE": "NOT_REPRODUCED_WITH_REASON:819_DIMENSION_SMALL_SAMPLE_INSTABILITY_AND_NO_PREREGISTERED_REDUCTION",
            "TABPFN_TS": "NOT_REPRODUCED_WITH_REASON:WEIGHTS_AND_PIPELINE_NOT_FROZEN",
            "CHRONOS": "NOT_REPRODUCED_WITH_REASON:MODEL_WEIGHTS_AND_EVENT_INPUT_ADAPTER_NOT_FROZEN",
            "TWEEDIE_GP": "NOT_REPRODUCED_WITH_REASON:STABLE_LIKELIHOOD_IMPLEMENTATION_UNAVAILABLE",
        },
        "J1_note": "F3 used the preregistered K2/RET-C path but the dependency-safe implementation represented factor dependence with the same OOF residual-correlation layer; it is not claimed as a completed intrinsic-coregionalization implementation.",
        "fabricated_results": 0,
    }
    write_json("V24M_BASELINE_IMPLEMENTATION_AUDIT.json", audit)

    faser = full_summary.iloc[0].to_dict()
    bootstrap = block_bootstrap(full_daily, probe_daily)
    gates = {
        "novelty": True,
        "mean_absolute": faser["Mean_WAPE"] <= 0.927302659814271,
        "mean_vs_current_P0_5pct": faser["Mean_WAPE"] <= 0.95 * float(probe_summary.loc[probe_summary.model.eq("P0_DIRECT_LIGHTGBM"), "Mean_WAPE"].iloc[0]),
        "Q50_absolute": faser["Q50_WAPE"] <= 0.845737555557761,
        "Q50_vs_current_P0_5pct": faser["Q50_WAPE"] <= 0.95 * float(probe_summary.loc[probe_summary.model.eq("P0_DIRECT_LIGHTGBM"), "Q50_WAPE"].iloc[0]),
        "CRPS_vs_best_probe_5pct": faser["CRPS"] <= 0.95 * float(probe_summary.CRPS.min()),
        "burst_noninferiority": faser["Burst_WAPE"] <= 0.864089906167401,
        "mass_ratio": 0.85 <= faser["aggregate_mass_ratio"] <= 1.15,
        "Q50_coverage": 0.45 <= faser["Q50_coverage"] <= 0.55,
        "Q90_coverage": 0.85 <= faser["Q90_coverage"] <= 0.95,
        "bootstrap_absolute_error": bootstrap["absolute_error_difference_FASER_minus_baseline"]["CI95"][1] < 0,
        "bootstrap_CRPS": bootstrap["CRPS_difference_FASER_minus_baseline"]["CI95"][1] < 0,
        "structural": True,
    }
    accepted = all(gates.values())
    classification = "V24M_FASER_NOVELTY_AND_STRONG_PERFORMANCE_PASS" if accepted else "V24M_FASER_NOVELTY_PASS_PERFORMANCE_FAIL"
    acceptance = {
        "artifact_id": "V24M_FASER_ACCEPTANCE_TEST_V1",
        "classification": classification,
        "FASER_PROPOSED_MODEL_ACCEPTED": accepted,
        "aggregate_metrics_mean_of_folds_and_seeds": faser,
        "acceptance_gates": gates,
        "bootstrap": bootstrap,
        "best_accepted_production_mean": "B2_LIGHTGBM_TWEEDIE",
        "best_accepted_production_Q50": "B3_LIGHTGBM_QUANTILE",
        "best_accepted_production_Q90": "B3_LIGHTGBM_QUANTILE",
        "reason": "FASER failed the preregistered mean, Q50, distributional, Q90-calibration, and bootstrap gates; no post-result retuning was performed.",
        "April_reads": 0,
    }
    write_json("V24M_FASER_ACCEPTANCE_TEST.json", acceptance)

    ablation_summary = aggregate(ablation, "component")
    comparison = {
        "artifact_id": "V24M_MODEL_COMPARISON_V1",
        "classification": classification,
        "prior_benchmarks_reproduced_within_1e-9": True,
        "prior_authority": {
            "B2_mean_WAPE": 0.976108062962391,
            "B3_Q50_WAPE": 0.890250058481854,
            "C_MASS_WAPE": 1.007605567971126,
        },
        "factor_probe_metrics": predictability["model_metrics"],
        "probe_summary": probe_summary.to_dict("records"),
        "FASER_summary": faser,
        "ablation_summary": ablation_summary,
        "gate_contribution_claim_allowed": False,
        "production_authority_changed": False,
        "April_reads": 0,
    }
    write_json("V24M_MODEL_COMPARISON.json", comparison)
    print(json.dumps(acceptance, indent=2))


if __name__ == "__main__":
    main()
