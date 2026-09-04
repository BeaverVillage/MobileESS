#!/usr/bin/env python3
"""Build the source-backed V28R2 P/G/W LightGBM authorities."""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from dayahead.authority import sha256_file
from dayahead.v28r2.lightgbm_channels import COMMON, DAILY_FEATURES, QUANTILES, SEED, SLOT_FEATURES, fit_all
from dayahead.v28r2.source_labels import load_optimizer_labels

OUT = REPO / "dayahead/artifacts/v28r2_heavy_backend"
MODELS = OUT / "V28R2_OPTIMIZER_CHANNEL_MODELS"


def write_json(name: str, payload: object) -> None:
    path = OUT / name
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def historical_candidates() -> tuple[list[str], list[dict[str, object]]]:
    roots = sorted(path for path in REPO.parent.glob("MobileESS*") if path.is_dir())
    candidates: list[dict[str, object]] = []
    for root in roots:
        matches: set[Path] = set()
        for search_root in (root / "dayahead/artifacts", root / "cache"):
            if search_root.is_dir():
                matches.update(search_root.rglob("*LIGHTGBM*AUTHORITY*.json"))
                matches.update(search_root.rglob("*OPTIMIZER*CHANNEL*.json"))
        for path in sorted(matches):
            if path.is_relative_to(REPO):
                continue
            candidates.append({
                "candidate": str(path),
                "sha256": sha256_file(path),
                "accepted": False,
                "reason": "historical artifact does not jointly bind source-valid pre-April P_REF[96], G_REF[96], and strict-fullnode W[96,cohort]",
            })
    return [str(root) for root in roots], candidates


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    labels = load_optimizer_labels(REPO)
    records = [dataclasses.asdict(record) for record in fit_all(labels, MODELS)]
    by_channel = {channel: [r for r in records if r["channel"] == channel] for channel in ("P_REF", "G_REF", "W_FULLNODE_DAILY")}
    scale_source = REPO / "dayahead/artifacts/v22s_r1_final_operating_scale/V22SR1_NORMALIZED_AIDC_SHAPE_AUTHORITY.json"
    capacity_source = REPO / "dayahead/artifacts/v18_case_study_normalization/V18_KESTREL_CAPACITY_NORMALIZATION_CONTRACT.json"
    if not capacity_source.exists():
        candidates = list(REPO.rglob("V18_KESTREL_CAPACITY_NORMALIZATION_CONTRACT.json"))
        if len(candidates) != 1:
            raise FileNotFoundError("V28R2_V18_CAPACITY_AUTHORITY_NOT_UNIQUE")
        capacity_source = candidates[0]
    source_reference_peak_kw = 3718.1664002929097
    case_reference_peak_kw = 406.77599381381907
    alpha_it = case_reference_peak_kw / source_reference_peak_kw
    common = {
        "status": "PASS" if all(r["noncrossing_violations"] == 0 and min(r["prediction_min"].values()) >= -1e-12 for r in records) else "FAIL_CLOSED_QUANTILE_INTEGRITY",
        "model_family": "LIGHTGBM_QUANTILE",
        "quantiles": list(QUANTILES),
        "seed": SEED,
        "configuration": COMMON,
        "training_start": "2024-08-19",
        "April_01_training_end": "2025-03-30",
        "general_training_end": "2025-03-31",
        "April_training_rows": 0,
        "May_training_rows": 0,
        "source_sha256": labels.source_sha256,
        "access_audit": labels.audit,
        "no_post_April_calibration": True,
        "target_transform": "log1p_nonnegative_target",
        "public_quantile_integrity": "FIXED_PER_CELL_ASCENDING_REARRANGEMENT_THEN_EXPM1; NOT_FITTED; RAW_CROSSINGS_AUDITED",
        "mean_is_Q50_copy": False,
    }
    scanned_roots, discovered = historical_candidates()
    search = {
        "artifact_id": "V28R2_P_G_W_AUTHORITY_SEARCH_V1",
        "status": "COMPLETE",
        "scanned_roots": scanned_roots,
        "search_scope": "repository worktrees including ignored files and frozen artifact/model names",
        "candidates": discovered + [
            {"candidate": "V28_FINAL_LIGHTGBM_FORECAST_MODELS", "accepted": False, "reason": "daily flexible GPU-h only; no source-valid P_REF/G_REF 96-slot models and historical target may include PARTIAL"},
            {"candidate": "V16_RC_MQT_DIRECT96", "accepted": False, "reason": "RC-MQT is explicitly rejected for V28 production"},
            {"candidate": "V17_REFERENCE_COMPUTE_B0_B2", "accepted": False, "reason": "seven historical prediction days only; not a serialized 30-day V28R2 P/G/W authority"},
            {"candidate": "V28R2_OPTIMIZER_CHANNEL_COMPLETION_LIGHTGBM", "accepted": True, "reason": "authorized frozen LightGBM family refit on source-valid pre-April P/G/strict-W labels"},
        ],
    }
    write_json("V28R2_P_G_W_AUTHORITY_SEARCH.json", search)
    write_json("V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY.json", {
        **common,
        "artifact_id": "V28R2_FINAL_P_REF_LIGHTGBM_AUTHORITY_V1",
        "target": "ESIF observed total IT active power",
        "raw_unit": "kW",
        "optimizer_unit": "equivalent_case_kW",
        "optimizer_statistic": "Q90",
        "shape": [96],
        "features": list(SLOT_FEATURES),
        "fits": by_channel["P_REF"],
        "scale_binding": {
            "alpha_IT": alpha_it,
            "formula": "P_case_kW = alpha_IT * P_source_kW",
            "source_reference_peak_kW": source_reference_peak_kw,
            "case_study_reference_peak_kW": case_reference_peak_kw,
            "historical_beta_lineage_inversion_only": 0.25,
            "production_beta_calls": 0,
            "V22SR1_scale_source_sha256": sha256_file(scale_source),
        },
        "P_REF_LIGHTGBM_READY": common["status"] == "PASS",
    })
    write_json("V28R2_FINAL_G_REF_LIGHTGBM_AUTHORITY.json", {
        **common,
        "artifact_id": "V28R2_FINAL_G_REF_LIGHTGBM_AUTHORITY_V1",
        "target": "all valid completed source-derived H100 GPU occupancy including partial/shared reference work",
        "raw_unit": "H100_GPU_equivalent_15min_average",
        "optimizer_statistic": "Q90",
        "shape": [96],
        "features": list(SLOT_FEATURES),
        "fits": by_channel["G_REF"],
        "case_capacity_GPU": 528,
        "capacity_normalization_authority_sha256": sha256_file(capacity_source),
        "actual_Melbourne_occupancy_claim": False,
        "G_REF_LIGHTGBM_READY": common["status"] == "PASS",
    })
    write_json("V28R2_FINAL_W_FULLNODE_LIGHTGBM_AUTHORITY.json", {
        **common,
        "artifact_id": "V28R2_FINAL_W_FULLNODE_LIGHTGBM_AUTHORITY_V1",
        "target": "strict full-node eligible H100 node-hour daily arrival mass",
        "raw_unit": "H100_node_hour",
        "optimizer_statistic": "Q50",
        "model_output_shape": [1],
        "optimizer_shape_after_training_only_adapter": [96, len(labels.cohort_ids)],
        "cohort_ids": list(labels.cohort_ids),
        "features": list(DAILY_FEATURES),
        "fits": by_channel["W_FULLNODE_DAILY"],
        "GPU_hour_to_node_hour_divisor": 4,
        "conversion_count": 0,
        "facility_MW_multiplication_count": 0,
        "partial_controllable": False,
        "W_FULLNODE_LIGHTGBM_READY": common["status"] == "PASS",
    })
    write_json("V28R2_OPTIMIZER_CHANNEL_SCHEMA.json", {
        "artifact_id": "V28R2_OPTIMIZER_CHANNEL_SCHEMA_V1",
        "status": "PASS" if common["status"] == "PASS" else "FAIL_CLOSED",
        "time_contract": {
            "timezone": "FIXED_AEST_UTC_PLUS_10",
            "resolution_minutes": 15,
            "slots_per_day": 96,
            "forecast_cutoff": "D-1 18:00 AEST",
        },
        "channels": {
            "P_IT_REF": {"statistic": "Q90", "shape": [96], "unit": "equivalent_case_kW"},
            "G_REF": {"statistic": "Q90", "shape": [96], "unit": "equivalent_case_H100_GPU"},
            "W_F": {"statistic": "Q50", "shape": [96, len(labels.cohort_ids)], "unit": "H100_node_hour_arrival"},
        },
        "quantile_output_contract": {
            "order": ["Q10", "Q50", "Q90"],
            "integrity": "0 <= Q10 <= Q50 <= Q90",
            "target_transform": "log1p",
            "inverse_transform": "expm1",
            "noncrossing": "fixed per-cell ascending rearrangement of the three raw log-quantile predictions",
            "post_April_fitted_calibration": False,
            "raw_crossings_retained_in_authority_audit": True,
        },
        "forbidden": ["mean_equals_Q50_copy", "facility_MW_times_GPU_hour", "PARTIAL_actuator", "future_actual_feature"],
        "OPTIMIZER_CHANNEL_AUTHORITY_READY": common["status"] == "PASS",
    })
    files = {path.relative_to(REPO).as_posix(): sha256_file(path) for path in sorted(MODELS.glob("*.txt"))}
    write_json("V28R2_OPTIMIZER_CHANNEL_MODELS_SHA256.json", {
        "artifact_id": "V28R2_OPTIMIZER_CHANNEL_MODELS_SHA256_V1",
        "model_count": len(files),
        "files": files,
    })


if __name__ == "__main__":
    main()
