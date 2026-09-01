"""Freeze V24M FASER architecture, gate, training, and blocked-CV contracts."""

from __future__ import annotations

import json
from pathlib import Path

from dayahead.ml.faser_flex.contracts import FOLDS, PREDICTIVE_SAMPLES, SEEDS
from dayahead.ml.faser_flex.retrieval import RETRIEVAL_CONFIGS


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"


def write_json(name: str, payload: object) -> None:
    """Write one deterministic architecture artifact."""

    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Freeze every scientific choice before outer FASER evaluation."""

    architecture = {
        "artifact_id": "V24M_FASER_ARCHITECTURE_CONTRACT_V1",
        "name": "Factorized Aggregate Signature-kernel Event-Retrieval Forecaster",
        "factor_identity": "H_F = R_ALL * PI_F * KAPPA_F for every sample",
        "components": {
            "A": "support-aware exact GP factor marginals",
            "B": "separate marginal GPs plus expanding-OOF Gaussian residual copula",
            "C": "past-only historical analog joint-tuple retrieval",
            "D": "six-parameter monotonic reliability gate or best single component",
            "E": "analog/global shrinkage shape transfer with exact mass reconciliation",
        },
        "R_model": "unweighted logistic hurdle plus fixed Matern-3/2 exact GP on positive log R_ALL",
        "PI_model": "unweighted logistic hurdle plus exact GP on positive logit PI_F",
        "KAPPA_model": "exact GP on logit KAPPA_F",
        "joint_dependence": "J2 OOF Gaussian copula",
        "negative_samples_allowed": False,
        "PI_support": [0.0, 1.0],
        "KAPPA_support": [0.0, 1.0],
        "queue_power_in_training_loss": False,
        "facility_scale_in_model": False,
    }
    write_json("V24M_FASER_ARCHITECTURE_CONTRACT.json", architecture)
    gate = {
        "artifact_id": "V24M_RELIABILITY_GATE_CONTRACT_V1",
        "alpha_semantics": "weight on historical analog distribution",
        "formula": "sigmoid(b0-softplus(b1)dmin+softplus(b2)log1p(neff)-softplus(b3)dispersion-softplus(b4)GPvariance-softplus(b5)drift)",
        "parameter_count": 6,
        "fit_data": "inner-validation only",
        "objective": "CRPS component preference",
        "fallback": "best single component when gate proxy does not improve both",
        "April_reads": 0,
        "outer_validation_tuning_reads": 0,
    }
    write_json("V24M_RELIABILITY_GATE_CONTRACT.json", gate)
    training = {
        "artifact_id": "V24M_TRAINING_POLICY_FREEZE_V1",
        "frozen_before_outer_FASER_evaluation": True,
        "seeds": SEEDS,
        "predictive_samples": PREDICTIVE_SAMPLES,
        "fit_inner_calibration_split_days": [14, 14],
        "early_fold_fallback_days": [10, 10],
        "signature_candidates": ["SIG-A", "SIG-B", "SIG-C"],
        "kernel_candidates": ["K1", "K2"],
        "joint_candidates": ["J1", "J2"],
        "retrieval_configs": {
            name: {"K": config.neighbors, "temperature": config.temperature}
            for name, config in RETRIEVAL_CONFIGS.items()
        },
        "full_configs": {
            "F1": ["SIG-A", "K1", "J2", "RET-A", 10],
            "F2": ["SIG-B", "K1", "J2", "RET-B", 10],
            "F3": ["SIG-A", "K2", "J1", "RET-C", 20],
            "F4": ["SIG-C", "K2", "J2", "RET-D", 20],
        },
        "if_both_probe_signals_false": "RUN_F1_ONLY",
        "otherwise": "SELECT_F1_TO_F4_ON_INNER_VALIDATION_ONLY",
        "result_based_config_additions": 0,
        "lucky_seed_selection": 0,
        "April_reads": 0,
    }
    write_json("V24M_TRAINING_POLICY_FREEZE.json", training)
    split = {
        "artifact_id": "V24M_BLOCKED_CV_SPLIT_CONTRACT_V1",
        "folds": [fold.__dict__ for fold in FOLDS],
        "forecast_cutoff": "D-1 18:00 AEST",
        "same_day_sample_leakage": 0,
        "hyperparameter_selection": "outer-training chronological inner validation only",
        "calibration": "outer-training chronological calibration only",
    }
    write_json("V24M_BLOCKED_CV_SPLIT_CONTRACT.json", split)
    print("V24M_ARCHITECTURE_FROZEN=true")


if __name__ == "__main__":
    main()
