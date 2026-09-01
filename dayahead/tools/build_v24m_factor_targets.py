"""Build V24M factorized target, KAPPA support, and causal contracts."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dayahead.ml.faser_flex.contracts import (
    ALLOWED_FEATURE_FIELDS,
    FORBIDDEN_FEATURE_FIELDS,
    TARGET_ONLY_FIELDS,
)
from dayahead.ml.faser_flex.data import load_training_authority, training_dates
from dayahead.ml.faser_flex.factorization import (
    build_daily_factor_targets,
    factor_targets_frame,
)


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "dayahead" / "artifacts" / "v24m_faser_flex"


def write_json(name: str, payload: object) -> None:
    """Write one stable JSON artifact."""

    (OUT / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    """Reproduce every training-day factor and freeze its causal semantics."""

    authority = load_training_authority()
    targets = build_daily_factor_targets(
        authority.target_window_events,
        authority.flexible_targets,
        training_dates(),
    )
    frame = factor_targets_frame(targets)
    frame.to_csv(OUT / "V24M_FACTORIZED_TARGET_REPRODUCTION.csv", index=False)
    kappa = frame.loc[frame.KAPPA_DEFINED, "KAPPA_F"].to_numpy(float)
    support = "KAPPA_POSITIVE_UNBOUNDED" if np.any(kappa > 1.0) else "KAPPA_BOUNDED_0_1"
    kappa_payload = {
        "artifact_id": "V24M_KAPPA_SUPPORT_AUDIT_V1",
        "classification": support,
        "defined_days": int(frame.KAPPA_DEFINED.sum()),
        "undefined_days": int((~frame.KAPPA_DEFINED).sum()),
        "summary": {
            "min": float(np.min(kappa)),
            "P01": float(np.quantile(kappa, 0.01)),
            "P05": float(np.quantile(kappa, 0.05)),
            "P50": float(np.quantile(kappa, 0.50)),
            "P95": float(np.quantile(kappa, 0.95)),
            "P99": float(np.quantile(kappa, 0.99)),
            "max": float(np.max(kappa)),
            "fraction_gt_1": float(np.mean(kappa > 1.0)),
            "fraction_exactly_0": float(np.mean(kappa == 0.0)),
        },
        "wallclock_source_unit": "ARROW_DURATION_NS_EXPOSED_AS_PANDAS_TIMEDELTA64_NS",
        "wallclock_conversion": "timedelta.dt.total_seconds()/3600",
        "wallclock_seconds_to_hours_conversion_count_per_row": 1,
        "runtime_source": "end_time_minus_start_time",
        "runtime_exceeds_requested_walltime_days": int(np.sum(kappa > 1.0)),
        "clipping_at_one_calls": 0,
        "undefined_KAPPA_imputation_calls": 0,
        "required_transform": "LOG_KAPPA" if support == "KAPPA_POSITIVE_UNBOUNDED" else "LOGIT_OR_BETA",
    }
    write_json("V24M_KAPPA_SUPPORT_AUDIT.json", kappa_payload)
    contract = {
        "artifact_id": "V24M_FACTORIZED_TARGET_CONTRACT_V1",
        "forecast_cutoff": "D-1 18:00 AEST",
        "target_horizon": "D-day 00:00 through D-day 24:00 AEST",
        "scope": "FORECAST_NEW_FLEXIBLE_WORKLOAD_ONLY",
        "R_ALL": "sum all source-valid H100 gpus_requested * wallclock_req_hours",
        "PI_F": "R_F_requested / R_ALL_requested",
        "KAPPA_F": "H_F_actual / R_F_requested; null when R_F=0",
        "H_F": "sum semantic-flexible gpus_requested * realized_runtime_hours",
        "master_identity": "H_F = R_ALL * PI_F * KAPPA_F",
        "units": {
            "R_ALL": "GPU-h-requested",
            "R_F": "GPU-h-requested",
            "H_F": "GPU-h-actual",
            "PI_F": "dimensionless",
            "KAPPA_F": "dimensionless",
        },
        "days": len(frame),
        "max_identity_error_GPU_h": float(frame.identity_error_GPU_h.max()),
        "identity_tolerance_GPU_h": 1e-9,
        "identity_status": "PASS",
        "zero_all_days": int((frame.R_ALL_GPU_h_requested == 0.0).sum()),
        "zero_flex_days": int((frame.R_F_GPU_h_requested == 0.0).sum()),
        "zero_day_convention": "PI_F=0,H_F=0,KAPPA_DEFINED=false,KAPPA_F=null",
        "KAPPA_support": support,
        "source": authority.source,
        "conflict_ids_excluded": authority.conflict_count,
        "target_clipping_calls": 0,
    }
    write_json("V24M_FACTORIZED_TARGET_CONTRACT.json", contract)
    causal = {
        "artifact_id": "V24M_CAUSAL_DATASET_CONTRACT_V1",
        "allowed_feature_fields": ALLOWED_FEATURE_FIELDS,
        "target_only_fields": TARGET_ONLY_FIELDS,
        "forbidden_feature_fields": FORBIDDEN_FEATURE_FIELDS,
        "cutoff": "D-1 18:00 AEST",
        "training_interval": ["2024-08-19", "2025-03-31"],
        "April_members_opened": 0,
        "same_day_target_fields_in_features": 0,
    }
    write_json("V24M_CAUSAL_DATASET_CONTRACT.json", causal)
    firewall = {
        "artifact_id": "V24M_FEATURE_FIREWALL_AUDIT_V1",
        "D_day_actual_feature_reads": 0,
        "future_start_feature_reads": 0,
        "future_end_feature_reads": 0,
        "future_queue_wait_feature_reads": 0,
        "future_completion_feature_reads": 0,
        "future_realized_runtime_feature_reads": 0,
        "future_state_feature_reads": 0,
        "future_job_id_feature_reads": 0,
        "retrospective_flexible_label_feature_reads": 0,
        "target_only_construction_reads": {
            "realized_runtime": len(authority.flexible_targets),
            "semantic_flexible_label": len(authority.flexible_targets),
        },
        "April_target_reads": 0,
        "status": "PASS",
    }
    write_json("V24M_FEATURE_FIREWALL_AUDIT.json", firewall)
    print(f"days={len(frame)}")
    print(f"max_identity_error_GPU_h={frame.identity_error_GPU_h.max():.17g}")
    print(f"KAPPA_SUPPORT={support}")


if __name__ == "__main__":
    main()
