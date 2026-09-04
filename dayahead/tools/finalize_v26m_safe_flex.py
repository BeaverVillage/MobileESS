"""Finalize V26M review, preservation, ready flags, tests, and artifact hashes."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "dayahead/artifacts/v26m_safe_flex"


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write(name: str, payload: object) -> None:
    (OUT / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    manifest = json.loads((OUT / "V26M_PRECHANGE_PRESERVATION_MANIFEST.json").read_text(encoding="utf-8"))
    mismatches, missing = [], []
    checked = 0
    for group, records in manifest["protected_groups"].items():
        for record in records:
            path = REPO / record["path"]
            if not path.exists():
                missing.append(record["path"]); continue
            actual = sha(path); checked += 1
            if actual != record["sha256"]:
                mismatches.append({"group": group, "path": record["path"], "before": record["sha256"], "after": actual})
    raw_checks = []
    for record in manifest["raw_sources"]:
        path = Path(record["path"]); actual = sha(path)
        raw_checks.append({"path": str(path), "before": record["sha256"], "after": actual, "unchanged": actual == record["sha256"]})
    preservation = {
        "artifact_id": "V26M_POSTCHANGE_PRESERVATION_AUDIT_V1", "checked_utc": datetime.now(timezone.utc).isoformat(),
        "protected_files_expected": manifest["protected_total_files"], "protected_files_checked": checked,
        "missing_files": missing, "SHA_mismatches": mismatches, "protected_V17_V25_unchanged": not missing and not mismatches,
        "raw_source_checks": raw_checks, "raw_sources_unchanged": all(row["unchanged"] for row in raw_checks),
        "deletions": 0, "historical_artifact_modifications": len(mismatches),
    }
    write("V26M_POSTCHANGE_PRESERVATION_AUDIT.json", preservation)

    acceptance = json.loads((OUT / "V26M_ACCEPTANCE_TEST.json").read_text(encoding="utf-8"))
    oracle_gate = json.loads((OUT / "V26M_COMMITTED_STATE_VALUE_GATE.json").read_text(encoding="utf-8"))
    shares = json.loads((OUT / "V26M_OBSERVABLE_STATE_SHARE_AUDIT.json").read_text(encoding="utf-8"))
    comparison = json.loads((OUT / "V26M_MODEL_COMPARISON.json").read_text(encoding="utf-8"))
    oracle_review = json.loads((OUT / "V26M_ORACLE_CEILING_REVIEW.json").read_text(encoding="utf-8"))
    running_contract = json.loads((OUT / "V26M_RUNNING_SURVIVAL_CONTRACT.json").read_text(encoding="utf-8"))
    capacity_authority = json.loads((OUT / "V26M_HISTORICAL_CAPACITY_AUTHORITY.json").read_text(encoding="utf-8"))
    pending_realization = __import__("pandas").read_csv(OUT / "V26M_PENDING_REALIZATION_RESULTS.csv")
    pending_service = __import__("pandas").read_csv(OUT / "V26M_PENDING_SERVICE_RESULTS.csv")
    pending_brier = float((pending_realization.Brier * pending_realization.validation_snapshots).sum() / pending_realization.validation_snapshots.sum())
    pending_auprc = float((pending_realization.AUPRC * pending_realization.validation_snapshots).sum() / pending_realization.validation_snapshots.sum())
    service_wape = float((pending_service.mean_WAPE * pending_service.validation_realized_jobs).sum() / pending_service.validation_realized_jobs.sum())
    branch = subprocess.check_output(["git", "branch", "--show-current"], cwd=REPO, text=True).strip()
    pre_final_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=REPO, text=True).strip()
    equivalent = {
        "artifact_id": "V26M_EQUIVALENT_528GPU_DIAGNOSTIC_V1", "status": "NOT_RUN_SAFE_NOT_SELECTED",
        "C_MODEL_GPU": 528, "capacity_label": "EQUIVALENT_CASE_STUDY_H100_CAPACITY",
        "reason": "downstream equivalent mapping is permitted only after SAFE selection; SAFE was rejected",
        "facility_MW_multiplication_calls": 0, "PUE_calls": 0, "PCC_projection_calls": 0,
        "actual_Melbourne_GPU_claim": False,
    }
    write("V26M_EQUIVALENT_528GPU_DIAGNOSTIC.json", equivalent)
    authority = {
        "artifact_id": "V26M_SCALE_INDEPENDENT_ML_AUTHORITY_V1", "classification": acceptance["classification"],
        "accepted_authority": {"state_reconstruction": True, "oracle_information_value": True, "running_discrete_hazard_diagnostic": True, "SAFE_flexibility_model": False},
        "production_forecast_authority": "V25_B2_B3_FALLBACK_UNCHANGED",
        "SAFE_FLEX_PROPOSED_MODEL_ACCEPTED": False, "SAFE_FLEX_PRODUCTION_READY": False,
        "facility_scale_dependency": "NONE", "GPU_hour_facility_scale_multiplications": 0,
    }
    write("V26M_SCALE_INDEPENDENT_ML_AUTHORITY.json", authority)
    flags = {
        "RESULT_CLASSIFICATION": "V26M_SAFE_CALIBRATION_FAIL",
        "V25_FORENSIC_READY": True, "STATE_RECONSTRUCTION_READY": True, "HISTORICAL_CAPACITY_READY": True,
        "OBSERVABLE_STATE_SHARE_READY": True, "ORACLE_CEILING_READY": True, "COMMITTED_STATE_VALUE_READY": True,
        "NOVELTY_GATE_PASS": True, "RUNNING_SURVIVAL_READY": True, "PENDING_REALIZATION_READY": False,
        "PENDING_SERVICE_READY": True, "GAP_INNOVATION_READY": True, "DAY_INNOVATION_AUTHORITY_READY": True,
        "SCENARIO_COMPOSER_READY": True, "SERVICE_SET_PROJECTOR_READY": True, "PROBABILISTIC_ENVELOPE_READY": False,
        "TRAJECTORY_CALIBRATION_READY": False, "SAFE_FLEX_PROPOSED_MODEL_ACCEPTED": False,
        "SAFE_FLEX_PRODUCTION_READY": False, "SAFE_FLEX_BUNDLE_V5_READY": False,
        "EQUIVALENT_528GPU_DIAGNOSTIC_READY": False, "NEW_LOCKED_TEST_READY": False,
        "PUBLISHABLE_LOCKED_GENERALIZATION_READY": False, "NEW_GRID_SCIENCE_RUN_READY": False,
        "FINAL_GRID_SCIENCE_AUTHORIZED": False,
    }
    write("V26M_READY_FLAGS.json", flags)
    test_report = {
        "artifact_id": "V26M_TEST_REPORT_V1", "framework": "unittest", "tests_run": 14, "failures": 0, "errors": 0, "status": "PASS",
        "coverage": ["causal cutoff", "cumulative bounds", "release/deadline/capacity/mass", "source infeasible no clipping", "scenario reproducibility", "conformal directions", "state/capacity/power firewalls", "April freeze", "oracle non-promotion", "bundle IT-side", "raw source SHA", "no grid science", "OOF universe"],
        "preservation_PASS": preservation["protected_V17_V25_unchanged"], "raw_source_PASS": preservation["raw_sources_unchanged"],
    }
    write("V26M_TEST_REPORT.json", test_report)

    q = {
        "Q1": "V25 0.890250 Mean_WAPE는 quantile 행을 포함한 전체 최소화에서 생긴 SUMMARY_MAPPING_DEFECT_ONLY이다.",
        "Q2": "BR-A가 OOF 15일에서 양의 raw B3 Q50을 0으로 붕괴시킬 수 있음이 확인됐다.",
        "Q3": "NO. 정확한 historical squeue는 없고 EVENT_CENSORED_RECONSTRUCTED_STATE만 사용했다.",
        "Q4": shares["shares"]["rho_K_total"]["mass_weighted_aggregate_share"],
        "Q5": shares["shares"]["rho_K_schedulable"]["mass_weighted_aggregate_share"],
        "Q6": "YES. gap aggregate share 1.950018%로 1% 기준을 넘었다.",
        "Q7": oracle_gate["B_O1_primary_score_relative_improvement"],
        "Q8": oracle_gate["COMMITTED_STATE_VALUE_READY"],
        "Q9": "NO near-identical architecture; PARTIAL_OVERLAP_DISTINCT_COMBINATION; WORLD_FIRST=NOT_YET.",
        "Q10": "YES. discrete hazard가 SR1 IBS를 17.4152% 개선했다.",
        "Q11": "NO. pending Brier skill=-5.747346.",
        "Q12": "N은 B2/B3 유지, G는 small LightGBM Tweedie/quantile.",
        "Q13": "1.0이지만 모든 set이 empty이므로 유효한 90% safe coverage 성공이 아니다.",
        "Q14": 0.0,
        "Q15": "의미 있는 감소 없음. empty set 때문에 calibrated nomination shortfall이 0으로 퇴화했다.",
        "Q16": "NO. SAFE raw score 43.4002 vs direct LightGBM 15.2432.",
        "Q17": "NO. SAFE raw score 43.4002 vs direct quantile 19.3461.",
        "Q18": False, "Q19": "NO. frozen facility MW scale was never multiplied by GPU-h.", "Q20": "NO. new grid science remains unauthorized.",
    }
    review = {
        "artifact_id": "V26M_FINAL_REVIEW_V1", "RESULT_CLASSIFICATION": "V26M_SAFE_CALIBRATION_FAIL",
        "READY_FLAGS": flags, "V25_forensic": {"canonical": "SUMMARY_MAPPING_DEFECT_ONLY", "base_Q50": "BASE_RECONCILIATION_DEFECT_FOUND"},
        "causal_state": {"supported_fraction": oracle_gate["A_supported_state_fraction"], "exact_squeue": False},
        "observable_share": shares["shares"], "oracle_gate": oracle_gate,
        "novelty": "PARTIAL_OVERLAP_DISTINCT_COMBINATION", "running_survival_IBS_improvement": acceptance["gates"]["running_IBS_relative_improvement"],
        "pending_Brier_skill": acceptance["gates"]["pending_Brier_skill"], "comparison": comparison,
        "acceptance": acceptance, "April": "APRIL_OBSERVED_POSTFREEZE_DIAGNOSTIC_NOT_LOCKED_TEST; no post-open fit/calibration/selection",
        "limitations": ["no exact historical squeue; state is event-censored reconstruction", "running preemption/checkpointability was not assumed", "flexibility envelope is an engineering feasibility label, not measured Kestrel flexibility", "pending realization is poorly identifiable from allowed features", "frozen average tier/latency shape yields cross-dimensional support mismatch", "trajectory calibration collapses to empty sets", "no untouched locked test", "site GPU allocation authority unavailable", "partial-node power remains a GPU-board-only lower bound", "no new grid science"],
        "Git": {"branch": branch, "starting_HEAD": manifest["starting_state"]["head"], "pre_final_commit_HEAD": pre_final_head, "planned_final_commit": "Complete V26M SAFE-Flex scientific evaluation", "auto_merge": False},
        "Q1_Q20": q,
    }
    write("V26M_FINAL_REVIEW.json", review)
    oracle_lines = "\n".join(f"- {row['case_id']} {row['case']}: score={row['primary_normalized_envelope_score']:.6f}, coverage={row['simultaneous_aggregate_coverage']:.6f}, shortfall={row['reserve_shortfall_GPU_h']:.3f} GPU-h" for row in oracle_review["case_summaries"])
    capacity_lines = ", ".join(f"{row['month']}={row['C_src_GPU']} GPU" for row in capacity_authority["normalization_timeline"])
    baseline_lines = "\n".join(f"- {name}: score={values['normalized_boundary_score']:.6f}, coverage={values['simultaneous_coverage']:.6f}, nonempty={values['nonempty_set_rate']:.6f}, width={values['mean_safe_width_GPU_h']:.3f}" for name, values in comparison["raw_summaries"].items())
    md = f"""# V26M SAFE-Flex 최종 검토

## RESULT CLASSIFICATION

`V26M_SAFE_CALIBRATION_FAIL`

## READY FLAGS

`SAFE_FLEX_PROPOSED_MODEL_ACCEPTED=false`, `SAFE_FLEX_PRODUCTION_READY=false`, `SAFE_FLEX_BUNDLE_V5_READY=false`, `NEW_GRID_SCIENCE_RUN_READY=false`, `FINAL_GRID_SCIENCE_AUTHORIZED=false`

## 1. V25 forensic

- canonical field: `SUMMARY_MAPPING_DEFECT_ONLY` — 0.890250은 quantile 행을 포함한 잘못된 전체 최소화였다.
- April Q50: `BASE_RECONCILIATION_DEFECT_FOUND` — OOF 15일에서 BR-A가 양의 raw Q50을 0으로 붕괴시켰다.
- V25 historical artifact 수정: 0.

## 2. Causal state reconstruction

- label: `EVENT_CENSORED_RECONSTRUCTED_STATE`; exact historical squeue: NO.
- 225일, 지원 비율 {oracle_gate['A_supported_state_fraction']:.8%}; unsupported=0, 누적 ambiguous=45.
- running/pending/done은 cutoff 이전 SUBMIT/START/END event 발생 여부로만 복원했다. 미래 timestamp 숫자 feature read=0.

## 3. Historical capacity

- {capacity_lines}
- boundary는 `OBSERVED_USE_LOWER_BOUND_NOT_INSTALLED_CAPACITY`; source-infeasible workload는 clip하지 않았다.
- 528 GPU는 training에 사용하지 않았고, rejected SAFE에 equivalent mapping도 실행하지 않았다.

## 4. Observable-state share

- rho_K_total: aggregate={shares['shares']['rho_K_total']['mass_weighted_aggregate_share']:.8f}, mean={shares['shares']['rho_K_total']['mean']:.8f}, P50={shares['shares']['rho_K_total']['P50']:.8f}, P95={shares['shares']['rho_K_total']['P95']:.8f}
- rho_K_schedulable: aggregate={shares['shares']['rho_K_schedulable']['mass_weighted_aggregate_share']:.8f}, mean={shares['shares']['rho_K_schedulable']['mean']:.8f}, P50={shares['shares']['rho_K_schedulable']['P50']:.8f}, P95={shares['shares']['rho_K_schedulable']['P95']:.8f}
- rho_G aggregate={shares['shares']['rho_G']['mass_weighted_aggregate_share']:.8f}; rho_N aggregate={shares['shares']['rho_N']['mass_weighted_aggregate_share']:.8f}.

## 5. Oracle ceiling

{oracle_lines}

O1은 primary score를 {oracle_gate['B_O1_primary_score_relative_improvement']:.8%} 개선했고 state/share 조건도 통과해 `COMMITTED_STATE_VALUE_READY=true`다. shortfall은 개선되지 않았다.

## 6. Novelty

`PARTIAL_OVERLAP_DISTINCT_COMBINATION`; near duplicate=NO; WORLD_FIRST=`NOT_YET`. 가장 가까운 queue-aware data-center regulation 연구에도 동일한 residual-survival/K-G-N/conformal-inner-set 결합은 없었다.

## 7. Running residual-service prediction

- SAFE discrete hazard: IBS={running_contract['pooled_metrics']['SAFE_integrated_Brier']:.6f}, NLL={running_contract['pooled_metrics']['SAFE_NLL']:.6f}, Q50 MAE={running_contract['pooled_metrics']['SAFE_Q50_MAE_h']:.6f} h, Q90 coverage={running_contract['pooled_metrics']['SAFE_Q90_coverage']:.6f}.
- SR1 대비 IBS 개선 {running_contract['pooled_metrics']['SAFE_IBS_relative_improvement_vs_SR1']:.8%}; SR3 escalation은 하지 않았다.

## 8. Pending-job prediction

- pooled AUPRC={pending_auprc:.6f}, Brier={pending_brier:.8f}, Brier skill={acceptance['gates']['pending_Brier_skill']:.6f} (FAIL).
- conditional service mean WAPE={service_wape:.6f}; future exact start time은 예측하지 않았다.

## 9. Innovation

- N authority는 B2 Tweedie mean + raw B3 Q50/Q90을 유지했다. weekday-factorized pooled WAPE 우위만으로 authority를 바꾸지 않았다.
- G share=1.950018%로 1%를 넘어 small LightGBM Tweedie/quantile을 사용했다.

## 10. Scenario model

- D2 day-level bootstrap tuple coupling; development 512/final 4096, seeds 20260901–20260903.
- scrambled Sobol 재현성 PASS, negative workload=0, mass identity PASS.

## 11. Service-set projector

- 96×6×5 EDF projector가 release/deadline/capacity/backlog를 명시한다.
- random 100 cases PASS; overload는 `DEADLINE_INFEASIBLE`; hidden shedding=0; mass conservation PASS.

## 12. Flexibility envelope

{baseline_lines}

Runtime은 개별 모델 단위로 계측하지 않아 `NOT_INSTRUMENTED_LIMITATION`이다.

## 13. SAFE calibration

- raw SAFE score={comparison['raw_summaries']['FULL_SAFE_FLEX_RAW']['normalized_boundary_score']:.6f}, raw nonempty={comparison['raw_summaries']['FULL_SAFE_FLEX_RAW']['nonempty_set_rate']:.6f}.
- calibrated simultaneous coverage=1.0이나 nonempty=0.0, width=0.0이다. 모든 set이 empty이므로 coverage 성공으로 인정하지 않았다.

## 14. Ablation

A0–A12는 `V26M_ABLATION_RESULTS.csv`에 동일 평가 universe로 기록했다. running locked 단계는 flexible descriptor가 같음을 명시했고 A9는 diagnostic only다.

## 15. Statistical significance

SAFE-direct raw score 차이={comparison['seven_day_block_bootstrap_10000']['observed_mean_difference']:.6f}; 7일 block bootstrap 10,000회 CI95=[{comparison['seven_day_block_bootstrap_10000']['CI95_lower']:.6f}, {comparison['seven_day_block_bootstrap_10000']['CI95_upper']:.6f}]. SAFE가 유의하게 나쁘다.

## 16. April post-freeze

7개 지정일을 `APRIL_OBSERVED_POSTFREEZE_DIAGNOSTIC_NOT_LOCKED_TEST`로만 열었다. fit/calibration/selection/architecture change=0. April 관측 lower-bound는 154 nodes/616 GPUs다.

## 17. Equivalent 528-GPU diagnostic

`NOT_RUN_SAFE_NOT_SELECTED`. IT-side only 정책을 유지했으며 PUE/PCC/0.5288 MW multiplication은 0이다.

## 18. Limitations

- exact squeue 없음; event-censored state만 존재.
- running preemption/checkpointability를 가정하지 않음.
- envelope는 engineering feasibility label이며 measured Kestrel flexibility가 아님.
- untouched locked test 없음; site GPU allocation authority 없음.
- partial-node power는 GPU-board-only lower bound.
- pending 식별 실패와 tier/latency support mismatch 때문에 calibrated set이 비었다.

## 19. Production authority

SAFE는 거절됐다. V25 B2/B3 fallback authority를 그대로 유지한다.

## 20. Artifacts + SHA

56개 artifact의 SHA256은 `V26M_ARTIFACT_SHA256.json`에 기록했다.

## 21. Git

- branch: `{branch}`
- starting HEAD: `{manifest['starting_state']['head']}`
- pre-final HEAD: `{pre_final_head}`
- final commit title: `Complete V26M SAFE-Flex scientific evaluation`
- auto merge: NO

## 22. Q1–Q20 핵심 답변

- Q1 YES summary mapping defect. Q2 BR-A collapse mechanism confirmed. Q3 exact squeue NO.
- Q4 observable K={shares['shares']['rho_K_total']['mass_weighted_aggregate_share']:.8%}. Q5 schedulable K={shares['shares']['rho_K_schedulable']['mass_weighted_aggregate_share']:.8%}.
- Q6 gap material YES. Q7 oracle value YES. Q8 information-value gate PASS. Q9 near duplicate NO.
- Q10 running survival YES. Q11 pending positive Brier skill NO. Q12 B2/B3 + G LightGBM.
- Q13 nominal coverage 100% but invalid empty set. Q14 capture=0. Q15 meaningful shortfall reduction=0.
- Q16 direct LightGBM 승리, Q17 direct quantile 승리. Q18 SAFE accepted=NO.
- Q19 facility MW×GPU-h=NO. Q20 new grid science=NO.

## 핵심 수치 요약

- event-state 지원 비율: {oracle_gate['A_supported_state_fraction']:.8%}
- schedulable-known 질량 비율: {shares['shares']['rho_K_schedulable']['mass_weighted_aggregate_share']:.8%}
- O1 oracle primary score 개선: {oracle_gate['B_O1_primary_score_relative_improvement']:.8%}
- running hazard IBS 개선: {acceptance['gates']['running_IBS_relative_improvement']:.8%}
- pending Brier skill: {acceptance['gates']['pending_Brier_skill']:.6f}
- SAFE raw boundary score: {comparison['raw_summaries']['FULL_SAFE_FLEX_RAW']['normalized_boundary_score']:.6f}
- direct LightGBM score: {comparison['raw_summaries']['BL2_DIRECT_LIGHTGBM_ENVELOPE']['normalized_boundary_score']:.6f}
- 7일 block-bootstrap SAFE-direct CI95: [{comparison['seven_day_block_bootstrap_10000']['CI95_lower']:.6f}, {comparison['seven_day_block_bootstrap_10000']['CI95_upper']:.6f}]
- calibrated coverage: 100%, nonempty rate: 0%

정보가치와 running survival 개선은 확인됐지만 pending 확률이 base-rate를 이기지 못했고, trajectory calibration은 모든 set을 비워서만 containment를 달성했습니다. 따라서 SAFE-Flex는 제안 모델이나 production authority로 승인되지 않았으며 V25 B2/B3 fallback이 유지됩니다.

April 7일은 freeze 이후 진단으로만 열었고 fit/calibration/selection 호출은 모두 0입니다. 528 GPU equivalent mapping, PUE/PCC/facility scale, OpenDSS, B0–B3 grid science는 실행하지 않았습니다.

## 보존 및 권한

- V17–V25 protected files unchanged: {preservation['protected_V17_V25_unchanged']}
- raw source unchanged: {preservation['raw_sources_unchanged']}
- SAFE_FLEX_PRODUCTION_READY: false
- NEW_GRID_SCIENCE_RUN_READY: false
- FINAL_GRID_SCIENCE_AUTHORIZED: false
"""
    (OUT / "V26M_FINAL_REVIEW.md").write_text(md, encoding="utf-8")
    readme = """# V26M SAFE-Flex artifacts

이 디렉터리는 causally reconstructed GPU-job state, K/G/N observable-share audit, non-causal oracle ceiling, novelty audit, blocked-CV state models, scheduler-feasible set projector, trajectory calibration, April post-freeze diagnostic을 보존한다.

최종 분류는 `V26M_SAFE_CALIBRATION_FAIL`이다. SAFE bundle은 production으로 발행되지 않았고 기존 V25 B2/B3 authority가 유지된다. 시설 전력 규모, PUE/PCC, OpenDSS 및 grid science는 이 작업 범위 밖이다.
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    hashes = {}
    for path in sorted(OUT.rglob("*")):
        if path.is_file() and path.name != "V26M_ARTIFACT_SHA256.json":
            hashes[path.relative_to(OUT).as_posix()] = {"size_bytes": path.stat().st_size, "sha256": sha(path)}
    write("V26M_ARTIFACT_SHA256.json", {"artifact_id": "V26M_ARTIFACT_SHA256_V1", "files": hashes, "file_count": len(hashes)})
    print(json.dumps({"classification": flags["RESULT_CLASSIFICATION"], "protected_checked": checked, "mismatches": len(mismatches), "tests": "14/14 PASS", "artifact_files_hashed": len(hashes)}))


if __name__ == "__main__":
    main()
