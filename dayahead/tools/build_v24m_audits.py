"""Audit V23M recurrence integrity and V24M FASER-Flex novelty."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, log_loss
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from dayahead.ml.c_mass_tpp.data import (
    TRAIN_END_EXCLUSIVE,
    TRAIN_START,
    conflict_ids,
    expanding_blocked_folds,
    load_h100_source,
    semantic_flexible_targets,
    source_valid_input_events,
)
from dayahead.tools.build_v23m_audits import FEATURES, add_recurrence_labels, occurrence_rows


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"
V23 = ROOT / "dayahead" / "artifacts" / "v23m_racq_flex"
ACCESS_DATE = "2026-09-01"


def sha256(path: Path) -> str:
    """Return one file SHA256."""

    digest = hashlib.sha256(path.read_bytes())
    return digest.hexdigest()


def write_json(name: str, payload: object) -> None:
    """Write one deterministic UTF-8 JSON artifact."""

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def corrected_probabilities(
    train: pd.DataFrame, valid: pd.DataFrame, features: list[str]
) -> np.ndarray:
    """Fit calibrated-prior occurrence probabilities without GPU-h sample weights."""

    if train.target.nunique() < 2:
        return np.full(len(valid), float(train.target.mean()))
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(C=1.0, max_iter=2000, random_state=20260901),
    )
    model.fit(train[features], train.target)
    return np.clip(model.predict_proba(valid[features])[:, 1], 1e-6, 1 - 1e-6)


def recurrence_integrity_audit() -> None:
    """Recompute a non-authority unweighted diagnostic using training months only."""

    raw, source = load_h100_source(min_month=202407, max_month=202503)
    events = source_valid_input_events(raw)
    targets = semantic_flexible_targets(
        raw, TRAIN_START, TRAIN_END_EXCLUSIVE, conflict_ids()
    )
    jobs = add_recurrence_labels(targets)
    hourly = occurrence_rows(jobs)
    corrected_rows: list[dict[str, object]] = []
    for fold in expanding_blocked_folds():
        train = hourly.loc[
            (hourly.date >= fold.train_start) & (hourly.date <= fold.train_end)
        ]
        valid = hourly.loc[
            (hourly.date >= fold.validation_start)
            & (hourly.date <= fold.validation_end)
        ]
        for name, features in FEATURES.items():
            probabilities = corrected_probabilities(train, valid, features)
            y = valid.target.to_numpy(int)
            weight = np.maximum(valid.target_GPU_h.to_numpy(float), 1.0)
            corrected_rows.append(
                {
                    "fold_id": fold.fold_id,
                    "model": name,
                    "observed_frequency": float(y.mean()),
                    "mean_predicted_probability": float(probabilities.mean()),
                    "brier_score": float(brier_score_loss(y, probabilities)),
                    "log_loss": float(log_loss(y, probabilities, labels=[0, 1])),
                    "GPU_h_weighted_brier_diagnostic": float(
                        np.average((probabilities - y) ** 2, weights=weight)
                    ),
                }
            )

    historical = json.loads(
        (V23 / "V23M_RECURRENCE_PREDICTIVE_LIFT.json").read_text(encoding="utf-8")
    )
    historical_r1 = [
        row
        for row in historical["fold_metrics"]
        if row["model"] == "R1_CALENDAR_AGGREGATE"
    ]
    corrected_r1 = [
        row for row in corrected_rows if row["model"] == "R1_CALENDAR_AGGREGATE"
    ]
    payload = {
        "artifact_id": "V24M_V23M_RECURRENCE_GATE_INTEGRITY_AUDIT_V1",
        "classification": "V23M_GATE_METRIC_OR_CALIBRATION_DEFECT_FOUND",
        "historical_authority_preserved": True,
        "historical_artifact_sha256": sha256(
            V23 / "V23M_RECURRENCE_PREDICTIVE_LIFT.json"
        ),
        "defect": {
            "location": "dayahead/tools/build_v23m_audits.py:fitted_probabilities",
            "positive_class_direction": "CORRECT",
            "target_label_construction": "CORRECT_FOR_HOURLY_RECURRING_OCCURRENCE",
            "hourly_recurrence_event_definition": "CORRECT",
            "class_weight": "NONE",
            "oversampling": False,
            "sample_weight": "max(target_GPU_h,1.0)",
            "sample_weight_normalization": "SCIKIT_LEARN_INTERNAL_OBJECTIVE_SCALING_ONLY",
            "probability_prior_correction": "ABSENT",
            "probability_calibration": "ABSENT",
            "feature_scaling": "TRAIN_ONLY_STANDARD_SCALER_VALID",
            "same_target_recurrence_feature_leakage": False,
            "finding": (
                "GPU-h magnitude weights change the fitted class prior and make the output an "
                "importance-weighted score, not a calibrated hourly occurrence probability. "
                "The same target_GPU_h weighting is then reused in the gate Brier metric."
            ),
        },
        "historical_R1_fold_probabilities": historical_r1,
        "corrected_unweighted_diagnostic_R1": corrected_r1,
        "corrected_all_models": corrected_rows,
        "authority_label": "NON_AUTHORITY_INTEGRITY_CORRECTION_DIAGNOSTIC",
        "RACQ_selection_reopened": False,
        "FASER_architecture_modified_from_this_result": False,
        "April_data_read": False,
        "source": source,
    }
    write_json("V24M_V23M_RECURRENCE_GATE_INTEGRITY_AUDIT.json", payload)


QUERIES = [
    "signature kernel workload forecasting",
    "signature Gaussian process event sequence forecasting",
    "signature kernel intermittent demand forecasting",
    "retrieval augmented probabilistic forecasting",
    "historical analog event workload forecasting",
    "factorized workload mass forecasting",
    "requested walltime runtime ratio forecasting",
    "flexible workload share forecasting data center",
    "GPU job requested service mass forecasting",
    "event path Gaussian process data center workload",
    "signature retrieval time series forecasting",
    "factorized Gaussian process demand forecasting",
    "Bayesian analog ensemble workload forecasting",
    "mass first workload forecasting",
    "top down intermittent workload forecasting",
    "AI data center probabilistic workload forecasting",
    "GPU workload retrieval augmented forecasting",
]


PRIOR_WORKS: list[dict[str, object]] = [
    {
        "paper_model": "GP with Signature Covariances",
        "year": 2020,
        "url": "https://proceedings.mlr.press/v119/toth20a.html",
        "ordered_path_representation": True,
        "signature_kernel": True,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": False,
        "flexible_share_factor": False,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": False,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": False,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "Signature covariance GP for sequential data.",
        "distinct": "No workload factorization, analog gate, or GPU mass/shape contract.",
    },
    {
        "paper_model": "Recurrent Sparse Spectrum Signature GP",
        "year": 2025,
        "url": "https://proceedings.mlr.press/v258/toth25a.html",
        "ordered_path_representation": True,
        "signature_kernel": True,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": False,
        "flexible_share_factor": False,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": False,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": False,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "Bayesian signature-based time-series forecasting.",
        "distinct": "No factor product, historical future retrieval, or physical bridge.",
    },
    {
        "paper_model": "Retrieval Augmented Time Series Forecasting (RAFT)",
        "year": 2025,
        "url": "https://openreview.net/forum?id=GUDnecJdJU",
        "ordered_path_representation": True,
        "signature_kernel": False,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": False,
        "flexible_share_factor": False,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": True,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": False,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "Retrieves similar historical inputs and their futures.",
        "distinct": "No signature GP, physical factor identity, or constrained reliability gate.",
    },
    {
        "paper_model": "Retrieval Augmented Forecasting (RAF)",
        "year": 2024,
        "url": "https://arxiv.org/abs/2411.08249",
        "ordered_path_representation": True,
        "signature_kernel": False,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": False,
        "flexible_share_factor": False,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": True,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": False,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "Retrieval augmentation for time-series foundation models.",
        "distinct": "No small-sample GP factorization or GPU workload semantics.",
    },
    {
        "paper_model": "Analog Ensemble",
        "year": 2013,
        "url": "https://doi.org/10.1175/MWR-D-12-00281.1",
        "ordered_path_representation": False,
        "signature_kernel": False,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": False,
        "flexible_share_factor": False,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": True,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": False,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "Probabilistic distribution from outcomes following similar historical states.",
        "distinct": "Meteorological post-processing; no signature GP or factor product.",
    },
    {
        "paper_model": "Dirichlet Proportions Model",
        "year": 2023,
        "url": "https://proceedings.mlr.press/v216/das23b.html",
        "ordered_path_representation": False,
        "signature_kernel": False,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": False,
        "flexible_share_factor": True,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": False,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": True,
        "time_tier_latency_shape_transfer": True,
        "exact_mass_coherence": True,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "Probabilistic top-down root mass and coherent proportions.",
        "distinct": "No requested/flexible/runtime identity, signature path, or analog mixture.",
    },
    {
        "paper_model": "TweedieGP",
        "year": 2025,
        "url": "https://arxiv.org/abs/2502.19086",
        "ordered_path_representation": False,
        "signature_kernel": False,
        "Bayesian_factor_forecast": True,
        "requested_mass_factorization": False,
        "flexible_share_factor": False,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": False,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": True,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "GP probabilistic intermittent-demand mass forecast.",
        "distinct": "No path signature, factor product, analog gate, or GPU semantics.",
    },
    {
        "paper_model": "Chronos",
        "year": 2024,
        "url": "https://arxiv.org/abs/2403.07815",
        "ordered_path_representation": True,
        "signature_kernel": False,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": False,
        "flexible_share_factor": False,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": False,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": True,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "Pretrained probabilistic time-series distribution forecast.",
        "distinct": "Foundation model, not event-path factorized retrieval GP.",
    },
    {
        "paper_model": "Deep Renewal Processes",
        "year": 2019,
        "url": "https://arxiv.org/abs/1911.10416",
        "ordered_path_representation": True,
        "signature_kernel": False,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": True,
        "flexible_share_factor": False,
        "runtime_realization_factor": False,
        "historical_analog_retrieval": False,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": False,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": False,
        "near_duplicate": False,
        "overlap": "Inter-arrival and mark decomposition for intermittent demand.",
        "distinct": "No signature GP, analog retrieval, or GPU mass identity.",
    },
    {
        "paper_model": "HPC Runtime Prediction Methodology",
        "year": 2023,
        "url": "https://www.nrel.gov/docs/fy23osti/86526.pdf",
        "ordered_path_representation": False,
        "signature_kernel": False,
        "Bayesian_factor_forecast": False,
        "requested_mass_factorization": False,
        "flexible_share_factor": False,
        "runtime_realization_factor": True,
        "historical_analog_retrieval": False,
        "reliability_aware_distribution_mixing": False,
        "mass_first_forecast": False,
        "time_tier_latency_shape_transfer": False,
        "exact_mass_coherence": False,
        "GPU_data_center_application": True,
        "near_duplicate": False,
        "overlap": "Predicts realized runtime from requested walltime and job history.",
        "distinct": "Per-job runtime task, not next-day flexible aggregate distribution.",
    },
]


def novelty_audit() -> None:
    """Write the systematic novelty matrix and conservative claim classification."""

    OUT.mkdir(parents=True, exist_ok=True)
    columns = list(PRIOR_WORKS[0])
    with (OUT / "V24M_NEAREST_PRIOR_WORK_MATRIX.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(PRIOR_WORKS)
    payload = {
        "artifact_id": "V24M_SYSTEMATIC_NOVELTY_AUDIT_V1",
        "access_date": ACCESS_DATE,
        "queries": QUERIES,
        "source_classes_searched": [
            "PMLR/ICML/AISTATS/UAI",
            "OpenReview/ICLR",
            "arXiv",
            "ACM/IEEE/Springer/ScienceDirect discoverable records",
            "official author/project pages",
        ],
        "Web_of_Science_Scopus": "NOT_ACCESSED",
        "nearest_prior_works": PRIOR_WORKS,
        "classification": "PARTIAL_OVERLAP_DISTINCT_COMBINATION",
        "near_identical_architecture_found": False,
        "NOVELTY_GATE_PASS": True,
        "MODEL_DEVELOPMENT_READY": True,
        "WORLD_FIRST": "NOT_YET",
        "claim_allowed": (
            "Distinct application-specific combination subject to empirical validation; "
            "no world-first claim and no component-level novelty claim."
        ),
    }
    write_json("V24M_SYSTEMATIC_NOVELTY_AUDIT.json", payload)
    lines = [
        "# V24M FASER-Flex systematic novelty audit",
        "",
        "- Classification: `PARTIAL_OVERLAP_DISTINCT_COMBINATION`",
        "- Near-identical architecture found: `false`",
        "- WORLD_FIRST: `NOT_YET`",
        "",
        "Signature-GP, retrieval-augmented forecasting, analog ensembles, factorized "
        "intermittent demand, probabilistic top-down proportions, and HPC runtime "
        "prediction all have strong prior art. The accessed works did not combine these "
        "with the exact R_ALL × PI_F × KAPPA_F identity, past-only reliability-gated "
        "distribution mixing, and GPU-h mass-first shape transfer.",
        "",
        "This permits implementation and testing of the combination, not a world-first claim.",
    ]
    (OUT / "V24M_SYSTEMATIC_NOVELTY_AUDIT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Create both phase-1 and phase-2 audit packets."""

    recurrence_integrity_audit()
    novelty_audit()
    print("V24M_GATE_IMPLEMENTATION_AUDIT=DEFECT_FOUND_NON_AUTHORITY")
    print("V24M_NOVELTY=PARTIAL_OVERLAP_DISTINCT_COMBINATION")


if __name__ == "__main__":
    main()
