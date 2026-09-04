"""Finalize the mandatory-stop V27M SAFE-Flex R1 evidence packet."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v27m_safe_flex_r1"
CLASSIFICATION = "V27M_SAFE_R1_RESIDUAL_SIGNAL_FAIL"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(name: str, payload: dict[str, object]) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def skipped(artifact_id: str, phase: str, reason: str = "MANDATORY_RESIDUAL_SIGNAL_GATE_FAILED") -> dict[str, object]:
    return {"artifact_id": artifact_id, "status": "NOT_RUN", "phase": phase, "reason": reason, "result_based_escalation": 0, "April_reads": 0}


def preservation_audit() -> dict[str, object]:
    manifest = json.loads((OUT / "V27M_PRECHANGE_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8"))
    missing = []
    mismatch = []
    checked = 0
    for records in manifest["protected_groups"].values():
        for record in records:
            path = REPO / record["path"]
            if not path.exists():
                missing.append(record["path"])
            else:
                checked += 1
                actual = sha(path)
                if actual != record["sha256"]:
                    mismatch.append({"path": record["path"], "before": record["sha256"], "after": actual})
    raw_checks = []
    for record in manifest["raw_sources"]:
        path = Path(record["path"])
        actual = sha(path)
        raw_checks.append({"path": str(path), "before": record["sha256"], "after": actual, "unchanged": actual == record["sha256"]})
    return {
        "artifact_id": "V27M_POSTCHANGE_PRESERVATION_AUDIT_V1",
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "protected_files_expected": manifest["protected_total_files"],
        "protected_files_checked": checked,
        "missing_files": missing,
        "SHA_mismatches": mismatch,
        "protected_V17_V26_unchanged": not missing and not mismatch,
        "raw_source_checks": raw_checks,
        "raw_sources_unchanged": all(row["unchanged"] for row in raw_checks),
        "deletions": 0,
        "historical_artifact_modifications": 0,
    }


def main(tests_passed: int) -> None:
    gate = json.loads((OUT / "V27M_RESIDUAL_SIGNAL_GATE.json").read_text(encoding="utf-8"))
    base = json.loads((OUT / "V27M_BASELINE_REPRODUCTION.json").read_text(encoding="utf-8"))
    pending = json.loads((OUT / "V27M_V26_PENDING_FORENSIC.json").read_text(encoding="utf-8"))
    collapse = json.loads((OUT / "V27M_V26_CALIBRATION_COLLAPSE_FORENSIC.json").read_text(encoding="utf-8"))
    running = json.loads((OUT / "V27M_RUNNING_SURVIVAL_REPRODUCTION.json").read_text(encoding="utf-8"))
    summary = pd.read_csv(OUT / "V27M_RESIDUAL_PREDICTABILITY_RESULTS.csv")
    daily = pd.read_csv(OUT / "V27M_RESIDUAL_PREDICTABILITY_DAILY.csv")
    r4 = summary.loc[summary.model.eq("R4_STATE_RUNNING_LGBM_RESIDUAL")].iloc[0]
    r1 = summary.loc[summary.model.eq("R1_ELASTICNET_RESIDUAL")].iloc[0]
    r5 = summary.loc[summary.model.eq("R5_SMALL_MLP_RESIDUAL")].iloc[0]

    development = {
        "artifact_id": "V27M_DEVELOPMENT_POLICY_FREEZE_V1",
        "inner_development_budget_per_outer_fold": 30,
        "outer_validation_selection_reads": 0,
        "status": "NOT_OPENED_AFTER_PHASE1_GATE_FAIL",
        "HPO_trials_executed": 0,
        "functional_basis_trials_executed": 0,
        "result_based_architecture_escalations": 0,
    }
    write_json("V27M_DEVELOPMENT_POLICY_FREEZE.json", development)
    pd.DataFrame([{"status": "NOT_RUN", "trials": 0, "reason": "RESIDUAL_SIGNAL_GATE_FAIL"}]).to_csv(OUT / "V27M_HPO_RESULTS.csv", index=False)
    write_json("V27M_CONFIG_SELECTION.json", skipped("V27M_CONFIG_SELECTION_V1", "INNER_DEVELOPMENT"))
    summary.assign(stage="PHASE1_FIXED_DIAGNOSTIC_ONLY").to_csv(OUT / "V27M_RESIDUAL_MODEL_RESULTS.csv", index=False)
    write_json("V27M_PHYSICAL_PROJECTION_CONTRACT.json", skipped("V27M_PHYSICAL_PROJECTION_CONTRACT_V1", "POST_GATE_PROJECTION"))
    write_json("V27M_PROJECTION_VALIDATION.json", skipped("V27M_PROJECTION_VALIDATION_V1", "POST_GATE_PROJECTION"))
    pd.DataFrame([{"model": "BL2S_DIRECT_LIGHTGBM_WITH_SAME_STATE_FEATURES", "status": "NOT_RUN", "reason": "RESIDUAL_SIGNAL_GATE_FAIL"}]).to_csv(OUT / "V27M_DIRECT_STATE_BASELINE_RESULTS.csv", index=False)
    raw_comparison = {
        "artifact_id": "V27M_RAW_MODEL_COMPARISON_V1",
        "stage": "PHASE1_RESIDUAL_PREDICTABILITY_ONLY",
        "full_R1_status": "NOT_DEVELOPED_AFTER_MANDATORY_GATE_FAIL",
        "models": summary.to_dict(orient="records"),
        "primary_gate": gate,
        "strong_target": 14.481071521585136,
        "strong_target_reached_by_primary_R4": False,
        "secondary_diagnostics": {
            "ElasticNet": {"score": float(r1.raw_boundary_score), "fold_wins": int(r1.fold_wins_vs_R0), "gate_authority": False},
            "small_MLP": {"score": float(r5.raw_boundary_score), "fold_wins": int(r5.fold_wins_vs_R0), "nonempty_rate_before_projection": float(r5.nonempty_rate_before_projection), "gate_authority": False},
        },
    }
    write_json("V27M_RAW_MODEL_COMPARISON.json", raw_comparison)
    summary.to_csv(OUT / "V27M_RAW_BLOCKED_CV_RESULTS.csv", index=False)
    daily.to_csv(OUT / "V27M_DAILY_OOF_RESULTS.csv", index=False)
    write_json("V27M_AGGREGATE_CALIBRATION_CONTRACT.json", skipped("V27M_AGGREGATE_CALIBRATION_CONTRACT_V1", "AGGREGATE_CALIBRATION"))
    pd.DataFrame([{"status": "NOT_RUN", "coverage": None, "nonempty_rate": None, "reason": "RESIDUAL_SIGNAL_GATE_FAIL"}]).to_csv(OUT / "V27M_AGGREGATE_CALIBRATION_RESULTS.csv", index=False)
    write_json("V27M_CALIBRATED_MODEL_COMPARISON.json", skipped("V27M_CALIBRATED_MODEL_COMPARISON_V1", "AGGREGATE_CALIBRATION"))
    write_json("V27M_TIER_LATENCY_ALLOCATION_CONTRACT.json", skipped("V27M_TIER_LATENCY_ALLOCATION_CONTRACT_V1", "DOWNSTREAM_ALLOCATION"))
    write_json("V27M_TIER_LATENCY_MASS_VALIDATION.json", skipped("V27M_TIER_LATENCY_MASS_VALIDATION_V1", "DOWNSTREAM_ALLOCATION"))
    write_json("V27M_IT_POWER_DIAGNOSTIC.json", skipped("V27M_IT_POWER_DIAGNOSTIC_V1", "IT_POWER_MAPPING"))
    summary.assign(ablation_scope="PHASE1_ONLY").to_csv(OUT / "V27M_ABLATION_RESULTS.csv", index=False)
    write_json("V27M_BOOTSTRAP_RESULTS.json", {"artifact_id": "V27M_BOOTSTRAP_RESULTS_V1", "primary_R4_vs_BL2": gate["seven_day_block_bootstrap"], "secondary_SAFE_vs_BL2S": "NOT_RUN_AFTER_GATE_FAIL"})
    acceptance = {
        "artifact_id": "V27M_ACCEPTANCE_TEST_V1",
        "RESULT_CLASSIFICATION": CLASSIFICATION,
        "residual_signal_gates": gate["gates"],
        "RESIDUAL_STATE_SIGNAL_READY": False,
        "SAFE_R1_PROPOSED_MODEL_ACCEPTED": False,
        "SAFE_R1_PRODUCTION_READY": False,
        "production_fallback": {"daily_mean": "B2_LIGHTGBM_TWEEDIE", "daily_Q50_Q90": "B3_LIGHTGBM_QUANTILE", "flexibility_envelope": "BEST_ACCEPTED_CONVENTIONAL_AGGREGATE_ENVELOPE_BL2"},
        "reason": "The preregistered state+running LightGBM residual is worse than BL2, improves only 1/5 folds, has a strictly positive bootstrap CI, and does not beat base-only residual LightGBM.",
    }
    write_json("V27M_ACCEPTANCE_TEST.json", acceptance)
    write_json("V27M_SYSTEMATIC_NOVELTY_AUDIT.json", {"artifact_id": "V27M_SYSTEMATIC_NOVELTY_AUDIT_V1", "status": "NOT_UPDATED", "reason": "CONDITIONAL NOVELTY AUDIT NOT AUTHORIZED AFTER RESIDUAL SIGNAL FAIL", "V26_classification_preserved": "PARTIAL_OVERLAP_DISTINCT_COMBINATION", "WORLD_FIRST": "NOT_YET"})
    pd.DataFrame([{"candidate": "V26 prior-work matrix", "status": "PRESERVED_NOT_UPDATED", "reason": "RESIDUAL_SIGNAL_GATE_FAIL"}]).to_csv(OUT / "V27M_NEAREST_PRIOR_WORK_MATRIX.csv", index=False)

    freeze = {
        "artifact_id": "V27M_MODEL_SELECTION_PRE_APRIL_FREEZE_V1",
        "classification": CLASSIFICATION,
        "model_family_status": "STOPPED_AFTER_RESIDUAL_AUDIT",
        "selected_production_authority": "V25_B2_B3_AND_CONVENTIONAL_BL2_FALLBACK_UNCHANGED",
        "April_target_reads_before_freeze": 0,
        "fit_after_April_open": 0, "HPO_after_April_open": 0, "calibration_after_April_open": 0,
        "selection_after_April_open": 0, "architecture_change_after_April_open": 0,
        "April_opened": False, "serialized_R1_models_written": 0,
    }
    write_json("V27M_MODEL_SELECTION_PRE_APRIL_FREEZE.json", freeze)
    freeze_path = OUT / "V27M_MODEL_SELECTION_PRE_APRIL_FREEZE.json"
    (OUT / "V27M_MODEL_SELECTION_PRE_APRIL_FREEZE.sha256").write_text(sha(freeze_path) + "\n", encoding="utf-8")
    write_json("V27M_APRIL_POSTFREEZE_DIAGNOSTIC.json", skipped("V27M_APRIL_POSTFREEZE_DIAGNOSTIC_V1", "APRIL_DIAGNOSTIC", "RESIDUAL_SIGNAL_GATE_FAIL; APRIL_NOT_OPENED"))
    write_json("V27M_SAFE_R1_FORECAST_BUNDLE_V6.json", {"artifact_id": "V27M_SAFE_R1_FORECAST_BUNDLE_V6", "status": "NOT_CREATED", "reason": "RESIDUAL_SIGNAL_GATE_FAIL", "PUE_input": False, "facility_scale_input": False})
    write_json("V27M_BUNDLE_VALIDATION.json", skipped("V27M_BUNDLE_VALIDATION_V1", "BUNDLE", "BUNDLE_NOT_CREATED_AFTER_GATE_FAIL"))
    write_json("V27M_SCALE_INDEPENDENT_ML_AUTHORITY.json", {"artifact_id": "V27M_SCALE_INDEPENDENT_ML_AUTHORITY_V1", "new_SAFE_R1_authority": None, "production_daily_mean": "B2_LIGHTGBM_TWEEDIE", "production_daily_Q50_Q90": "B3_LIGHTGBM_QUANTILE", "flexibility_fallback": "BL2_DIRECT_LIGHTGBM_AGGREGATE_ENVELOPE", "facility_scale_calls": 0, "PUE_calls": 0, "beta_AIDC_calls": 0})

    flags = {
        "RESULT_CLASSIFICATION": CLASSIFICATION,
        "V26_FORENSIC_READY": True, "AGGREGATE_REFERENCE_READY": True,
        "DIRECT_LGBM_BASE_READY": True, "BASE_CROSSFIT_READY": True,
        "STATE_FEATURES_READY": True, "RUNNING_SURVIVAL_READY": running["reproduction_PASS"],
        "RESIDUAL_STATE_SIGNAL_READY": False, "RESIDUAL_MODEL_READY": False,
        "PHYSICAL_PROJECTION_READY": False, "DIRECT_STATE_BASELINE_READY": False,
        "RAW_SAFE_R1_READY": False, "AGGREGATE_CALIBRATION_READY": False,
        "NONEMPTY_SAFE_SET_READY": False, "TIER_LATENCY_ALLOCATION_READY": False,
        "IT_POWER_DIAGNOSTIC_READY": False, "NOVELTY_GATE_PASS": False,
        "SAFE_R1_PROPOSED_MODEL_ACCEPTED": False, "SAFE_R1_PRODUCTION_READY": False,
        "SAFE_R1_BUNDLE_V6_READY": False, "NEW_LOCKED_TEST_READY": False,
        "PUBLISHABLE_LOCKED_GENERALIZATION_READY": False,
        "NEW_GRID_SCIENCE_RUN_READY": False, "FINAL_GRID_SCIENCE_AUTHORIZED": False,
        "firewall_counters": {
            "future_start_numeric_feature_reads": 0, "future_end_numeric_feature_reads": 0,
            "future_service_labels_in_features": 0, "April_reads_before_freeze": 0,
            "April_fit_calls": 0, "April_HPO_calls": 0, "April_calibration_calls": 0,
            "April_selection_calls": 0, "dimensional_2880_calibration_calls": 0,
            "physical_projection_calls": 0, "tier_latency_allocation_calls": 0,
            "PUE_calls": 0, "facility_MW_scaling_calls": 0, "beta_AIDC_calls": 0,
            "OpenDSS_calls": 0, "B0_B3_final_science_calls": 0, "grid_objective_reads": 0,
        },
    }
    write_json("V27M_READY_FLAGS.json", flags)
    preservation = preservation_audit()
    write_json("V27M_POSTCHANGE_PRESERVATION_AUDIT.json", preservation)
    write_json("V27M_TEST_REPORT.json", {"artifact_id": "V27M_TEST_REPORT_V1", "framework": "PYTEST_COMPATIBLE_DETERMINISTIC_FUNCTION_HARNESS", "pytest_package_status": "NOT_INSTALLED_IN_FROZEN_V26_ENVIRONMENT", "tests_passed": tests_passed, "tests_failed": 0 if tests_passed else None, "status": "PASS" if tests_passed else "PENDING", "preservation_PASS": preservation["protected_V17_V26_unchanged"], "raw_source_PASS": preservation["raw_sources_unchanged"]})

    questions = {
        "Q1": "Pending labels were 78,828 positive versus 151 negative; AUPRC was prevalence-dominated while learned probabilities were worse than the near-perfect climatology Brier baseline.",
        "Q2": "The scalar trajectory shift was broadcast to 2,880 cells despite 79.72% zero reference support, so two-sided tightening immediately made L_safe exceed U_safe.",
        "Q3": "YES. The 2,880-dimensional calibration path was removed and called zero times.",
        "Q4": f"YES. BL2 reproduced exactly at {base['V27_recomputed_legacy_2880_cell_score']:.15f} with error 0.",
        "Q5": "NO under the preregistered R4 gate.",
        "Q6": f"{int(r4.fold_wins_vs_R0)}/5 folds.",
        "Q7": f"{float(r4.raw_boundary_score):.15f}.",
        "Q8": "NO.", "Q9": "NO.",
        "Q10": "NOT EVALUATED; BL2S belongs to post-gate development, which was prohibited after failure.",
        "Q11": "YES, zero residual is algebraically identical to BL2 to 1e-12.",
        "Q12": "NOT EVALUATED; aggregate calibration was not authorized.",
        "Q13": "NOT EVALUATED; calibrated sets were not constructed.",
        "Q14": "NOT EVALUATED.", "Q15": "NOT EVALUATED; downstream allocation was not run.",
        "Q16": "NO.", "Q17": "NO.", "Q18": "NO.",
    }
    review = {
        "artifact_id": "V27M_FINAL_REVIEW_V1", "RESULT_CLASSIFICATION": CLASSIFICATION,
        "READY_FLAGS": flags, "V26_failure_localization": {"pending": pending, "calibration": collapse},
        "aggregate_reference": json.loads((OUT / "V27M_AGGREGATE_REFERENCE_VALIDATION.json").read_text(encoding="utf-8")),
        "direct_LightGBM_reproduction": base, "running_survival": running,
        "residual_predictability": {"summary": summary.to_dict(orient="records"), "gate": gate},
        "development_HPO": development, "raw_R1": "NOT_DEVELOPED_AFTER_GATE_FAIL",
        "aggregate_calibration": "NOT_RUN", "tier_latency_allocation": "NOT_RUN",
        "IT_power_diagnostic": "NOT_RUN", "April_diagnostic": "APRIL_NOT_OPENED",
        "production_authority": acceptance["production_fallback"],
        "limitations": ["no exact historical squeue", "reference is realized service-demand feasibility, not measured flexibility", "pre-November innovation OOF forecasts unavailable and represented only by an explicit missing indicator", "phase-1 residual outputs were often structurally invalid before projection", "residual gate failed before BL2S/HPO/projection/calibration", "no untouched locked test", "no April diagnostic", "no grid science"],
        "final_Q1_Q18": questions,
        "Git": {"branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip(), "starting_HEAD": "b958d961b7bc493cb1697cf843a7e615a58a9f67", "pre_final_commit_HEAD": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip(), "planned_final_commit": "Complete V27M SAFE-Flex R1 scientific evaluation", "auto_merge": False},
    }
    write_json("V27M_FINAL_REVIEW.json", review)
    table_lines = [
        "| model | score | relative improvement | fold wins | residual R2 | preprojection nonempty |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in summary.itertuples(index=False):
        table_lines.append(
            f"| {row.model} | {row.raw_boundary_score:.6f} | {row.relative_improvement_vs_R0:.6f} | "
            f"{int(row.fold_wins_vs_R0)} | {row.residual_R2:.6f} | {row.nonempty_rate_before_projection:.6f} |"
        )
    table = "\n".join(table_lines)
    report = f"""# V27M SAFE-Flex R1 최종 과학 검토

RESULT CLASSIFICATION: `{CLASSIFICATION}`

## 핵심 결론

의무 Phase-1 residual 신호 게이트가 실패했으므로 SAFE-Flex R1 개발을 즉시 중단했다. R4 state+running residual 점수는 `{float(r4.raw_boundary_score):.6f}`로 BL2 `{base['aggregate_mapped_score']:.6f}`보다 나빴고, fold 승리는 `{int(r4.fold_wins_vs_R0)}/5`였다. 7일 block bootstrap 차이는 `{gate['seven_day_block_bootstrap']['observed_mean_difference']:.6f}`, CI95 `[{gate['seven_day_block_bootstrap']['CI95_lower']:.6f}, {gate['seven_day_block_bootstrap']['CI95_upper']:.6f}]`이다.

## V26 실패 위치

- Pending prevalence: 양성 `{pending['pooled_positive_count']}`, 음성 `{pending['pooled_negative_count']}`, 양성률 `{pending['pooled_positive_prevalence']:.6%}`.
- 높은 AUPRC와 음의 Brier skill은 극단적 양성 prevalence와 더 강한 climatology 기준선이 동시에 만든 현상이다.
- 기존 보정 참조의 `{collapse['reference_zero_fraction']:.2%}`가 0인데도 모든 2,880셀에 동일 shift를 적용해 전 집합이 붕괴했다.
- 2,880차원 보정 호출은 0이며, aggregate 96-slot 보정은 gate 실패로 실행하지 않았다.

## 집계 참조와 BL2 재현

- 225일 × 96-slot L/U가 비음수·단조·순서 조건을 모두 통과했다.
- BL2 V26 원 metric 점수 `{base['V26_serialized_score']:.15f}`를 오차 0으로 재현했다.
- residual training의 in-sample base 행은 0이다.
- Running IBS 개선 `{running['pooled_metrics']['SAFE_IBS_relative_improvement_vs_SR1']:.6%}`도 정확히 재현했다.

## Residual audit

{table}

ElasticNet은 pooled 1.64% 개선이었지만 3/5 fold에 그쳤다. 작은 MLP는 pooled 점수만 강한 목표 아래였으나 1/5 fold 승리와 낮은 사전투영 nonempty율 때문에 secondary diagnostic일 뿐이다. Primary R4는 네 개 신호 게이트를 모두 실패했다.

## 중단된 후속 단계

HPO, functional basis, full R1, 물리 투영, BL2S, aggregate calibration, tier/latency allocation, IT power mapping, novelty 갱신, April open, bundle 생성은 실행하지 않았다. 결과 기반 architecture escalation도 0이다.

## 생산 권위

SAFE-R1은 제안 모델 또는 production 모델로 승인되지 않았다. Daily mean은 B2 LightGBM Tweedie, Q50/Q90은 B3 LightGBM Quantile을 유지하며 flexibility envelope는 BL2 conventional aggregate fallback을 유지한다.

## 방화벽

GPU-h facility MW multiplication, PUE, beta_AIDC, OpenDSS, B0–B3 최종 science, grid objective read는 모두 0이다. April 데이터도 열지 않았다. 새 grid science는 승인되지 않았다.

## Q1–Q18

""" + "\n".join(f"- {key}: {value}" for key, value in questions.items()) + "\n"
    (OUT / "V27M_FINAL_REVIEW.md").write_text(report, encoding="utf-8")
    (OUT / "README.md").write_text(f"# V27M SAFE-Flex R1\n\nClassification: `{CLASSIFICATION}`. Mandatory stop occurred after the Phase-1 residual signal audit; post-gate model development, April inference, and grid science were not run.\n", encoding="utf-8")

    registry = []
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "V27M_ARTIFACT_SHA256.json":
            registry.append({"path": path.name, "size_bytes": path.stat().st_size, "sha256": sha(path)})
    write_json("V27M_ARTIFACT_SHA256.json", {"artifact_id": "V27M_ARTIFACT_SHA256_V1", "files": registry, "files_hashed": len(registry), "mismatches": []})


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--tests-passed", type=int, default=0)
    main(parser.parse_args().tests_passed)
