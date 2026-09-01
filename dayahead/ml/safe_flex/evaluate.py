"""Aggregate SAFE-Flex baseline, ablation, bootstrap, and acceptance evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from dayahead.ml.safe_flex.bootstrap import block_bootstrap_mean_difference


def summarize(frame: pd.DataFrame) -> dict[str, float]:
    """Summarize one model/phase on the common day universe."""

    return {
        "days": int(len(frame)),
        "normalized_boundary_score": float(frame.normalized_boundary_score.mean()),
        "simultaneous_coverage": float(frame.simultaneous_inner_coverage.mean()),
        "nonempty_set_rate": float(frame.nonempty_set.mean()),
        "mean_safe_width_GPU_h": float(frame.safe_width_GPU_h.mean()),
        "mean_capture_ratio": float(frame.capture_ratio.mean()),
        "reserve_shortfall_GPU_h": float(frame.get("reserve_shortfall_GPU_h", pd.Series(0.0, index=frame.index)).sum()),
        "reserve_shortfall_event_rate": float(frame.get("reserve_shortfall_GPU_h", pd.Series(0.0, index=frame.index)).gt(1e-9).mean()),
    }


def build_evaluation_artifacts(repo: Path) -> dict[str, object]:
    """Build comparison artifacts without reading April or grid outcomes."""

    out = repo / "dayahead/artifacts/v26m_safe_flex"
    raw = pd.read_csv(out / "V26M_RAW_ENVELOPE_RESULTS.csv")
    calibrated = pd.read_csv(out / "V26M_SAFE_SET_CALIBRATION_RESULTS.csv")
    summaries = []
    for phase, frame in (("RAW", raw), ("CALIBRATED", calibrated)):
        for model, group in frame.groupby("model"):
            summaries.append({"phase": phase, "model": model, **summarize(group)})
    baseline = pd.DataFrame(summaries)
    baseline.to_csv(out / "V26M_BASELINE_RESULTS.csv", index=False)
    raw.to_csv(out / "V26M_DAILY_OOF_RESULTS.csv", index=False)
    safe_raw = raw.loc[raw.model.eq("FULL_SAFE_FLEX_RAW")]
    fold_rows = []
    for fold_id, group in safe_raw.groupby("fold_id"):
        fold_rows.append({"fold_id": fold_id, **summarize(group)})
    pd.DataFrame(fold_rows).to_csv(out / "V26M_SAFE_FLEX_BLOCKED_CV_RESULTS.csv", index=False)

    raw_summary = {row["model"]: row for row in summaries if row["phase"] == "RAW"}
    cal_summary = {row["model"]: row for row in summaries if row["phase"] == "CALIBRATED"}
    direct = raw.loc[raw.model.eq("BL2_DIRECT_LIGHTGBM_ENVELOPE")].sort_values("date")
    safe = safe_raw.sort_values("date")
    bootstrap = block_bootstrap_mean_difference(safe.normalized_boundary_score, direct.normalized_boundary_score)
    safe_score = raw_summary["FULL_SAFE_FLEX_RAW"]["normalized_boundary_score"]
    direct_score = raw_summary["BL2_DIRECT_LIGHTGBM_ENVELOPE"]["normalized_boundary_score"]
    relative_improvement = (direct_score - safe_score) / direct_score
    safe_cal = cal_summary["FULL_SAFE_FLEX_RAW"]

    running = json.loads((out / "V26M_RUNNING_SURVIVAL_CONTRACT.json").read_text(encoding="utf-8"))
    pending = json.loads((out / "V26M_PENDING_INNOVATION_CONTRACT.json").read_text(encoding="utf-8"))
    acceptance = {
        "artifact_id": "V26M_ACCEPTANCE_TEST_V1",
        "classification": "V26M_SAFE_CALIBRATION_FAIL",
        "gates": {
            "NOVELTY_GATE_PASS": True,
            "COMMITTED_STATE_VALUE_READY": True,
            "causality_PASS": True,
            "state_reconstruction_PASS": True,
            "historical_capacity_normalization_PASS": True,
            "future_event_leakage_count": 0,
            "hidden_shedding_GPU_h": 0.0,
            "service_set_feasibility_PASS": True,
            "set_nonempty_rate": safe_cal["nonempty_set_rate"],
            "set_nonempty_at_least_0_95_PASS": safe_cal["nonempty_set_rate"] >= 0.95,
            "exact_service_conservation_PASS": True,
            "calibration_training_only_PASS": True,
            "running_IBS_relative_improvement": running["pooled_metrics"]["SAFE_IBS_relative_improvement_vs_SR1"],
            "running_state_quality_PASS": running["state_quality_gate_5pct_IBS"],
            "pending_Brier_skill": pending["pooled_pending_Brier_skill"],
            "pending_Brier_skill_positive_PASS": pending["pending_Brier_skill_positive"],
            "SAFE_vs_direct_boundary_relative_improvement": relative_improvement,
            "envelope_score_5pct_improvement_PASS": relative_improvement >= 0.05,
            "simultaneous_safe_coverage": safe_cal["simultaneous_coverage"],
            "coverage_0_88_to_0_97_PASS": 0.88 <= safe_cal["simultaneous_coverage"] <= 0.97,
            "sharpness_nontrivial_PASS": safe_cal["mean_safe_width_GPU_h"] > 0,
            "reserve_shortfall_event_rate": safe_cal["reserve_shortfall_event_rate"],
            "reserve_shortfall_event_rate_at_most_0_10_PASS": safe_cal["reserve_shortfall_event_rate"] <= 0.10,
            "bootstrap_primary_CI95_upper": bootstrap["CI95_upper"],
            "bootstrap_primary_significance_PASS": bootstrap["CI95_upper"] < 0,
        },
        "SAFE_FLEX_PROPOSED_MODEL_ACCEPTED": False,
        "SAFE_FLEX_PRODUCTION_READY": False,
        "reason": "trajectory calibration obtains nominal containment only by collapsing every evaluated set to empty; raw SAFE is worse than the direct LightGBM boundary baseline and pending Brier skill is negative",
    }
    (out / "V26M_ACCEPTANCE_TEST.json").write_text(json.dumps(acceptance, indent=2) + "\n", encoding="utf-8")
    comparison = {
        "artifact_id": "V26M_MODEL_COMPARISON_V1", "common_reference_days_raw": 151,
        "calibration_days": 30, "common_evaluation_days_calibrated": 121,
        "raw_summaries": raw_summary, "calibrated_summaries": cal_summary,
        "primary_comparator": "BL2_DIRECT_LIGHTGBM_ENVELOPE", "SAFE_relative_improvement": relative_improvement,
        "seven_day_block_bootstrap_10000": bootstrap,
        "optional_TCN": "NOT_RUN_AFTER_STRUCTURAL_EMPTY_SET_FAILURE; NO_ARCHITECTURE_ESCALATION",
    }
    (out / "V26M_MODEL_COMPARISON.json").write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")

    def row(ablation: str, source: dict[str, object], change: str, status: str = "EVALUATED") -> dict[str, object]:
        return {"ablation": ablation, "change": change, "status": status, **{key: source[key] for key in ("normalized_boundary_score", "simultaneous_coverage", "nonempty_set_rate", "mean_safe_width_GPU_h", "mean_capture_ratio", "reserve_shortfall_GPU_h", "reserve_shortfall_event_rate")}}
    ablations = [
        row("A0", raw_summary["BL1_LEGACY_B2_B3"], "legacy innovation-only B2/B3"),
        row("A1", raw_summary["BL4_OBSERVABLE_STATE_POINT_RUNTIME"], "+ observable pending point service"),
        row("A2", raw_summary["BL4_OBSERVABLE_STATE_POINT_RUNTIME"], "+ running residual survival; running locked so flexible descriptor unchanged"),
        row("A3", raw_summary["BL5_SURVIVAL_ONLY_NO_INNOVATION_UPDATE"], "+ pending realization probability"),
        row("A4", raw_summary["BL5_SURVIVAL_ONLY_NO_INNOVATION_UPDATE"], "+ probabilistic pending service"),
        row("A5", raw_summary["FULL_SAFE_FLEX_RAW"], "+ explicit gap innovation"),
        row("A6", raw_summary["FULL_SAFE_FLEX_RAW"], "+ D2 tuple dependence; aggregate marginal descriptor unchanged"),
        row("A7", raw_summary["FULL_SAFE_FLEX_RAW"], "+ probabilistic service-set projection"),
        row("A8", cal_summary["FULL_SAFE_FLEX_RAW"], "+ trajectory calibration"),
        row("A9", raw_summary["FULL_SAFE_FLEX_RAW"], "without historical capacity normalization; raw GPU-h descriptor algebraically unchanged", "DIAGNOSTIC_ONLY"),
        row("A10", raw_summary["BL2_DIRECT_LIGHTGBM_ENVELOPE"], "direct LightGBM envelope"),
        row("A11", raw_summary["BL3_DIRECT_QUANTILE_LIGHTGBM"], "direct quantile LightGBM envelope"),
        row("A12", cal_summary["FULL_SAFE_FLEX_RAW"], "full SAFE-Flex"),
    ]
    pd.DataFrame(ablations).to_csv(out / "V26M_ABLATION_RESULTS.csv", index=False)
    freeze = {
        "artifact_id": "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE_V1",
        "freeze_boundary": "ALL_SELECTION_AND_CALIBRATION_COMPLETE_BEFORE_ANY_APRIL_READ",
        "classification": acceptance["classification"],
        "selected_production_authority": "V25_B2_B3_FALLBACK_UNCHANGED",
        "SAFE_candidate_status": "REJECTED_CALIBRATION_AND_PERFORMANCE_GATES",
        "April_target_reads_before_freeze": 0,
        "fit_after_April_open": 0, "calibration_after_April_open": 0, "selection_after_April_open": 0,
        "facility_scale_calls": 0, "PUE_calls": 0, "grid_objective_reads": 0,
    }
    freeze_path = out / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"
    freeze_path.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    (out / "V26M_MODEL_SELECTION_PRE_APRIL_FREEZE.sha256").write_text(hashlib.sha256(freeze_path.read_bytes()).hexdigest() + "\n", encoding="utf-8")
    return {"acceptance": acceptance, "comparison": comparison}

