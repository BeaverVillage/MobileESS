# V40I 최종 causal chain

학습 population과 fitted tree의 직접 인과 효과, workload occupancy 역전, 전기 모델 fidelity를 분리한다. 아래 HIGH는 지정한 frozen/simulated scope의 신뢰도다. 물리 현장 측정의 의미로 확장하지 않는다.

| 연결 | Evidence | Authority artifact | Confidence | Unresolved gap |
|---|---|---|---|---|
| TRAINING POPULATION → POINT PREDICTION | H100 87,319 rows; FAILED 54,057 versus COMPLETED 28,394; source MoE XGBoost reg:absoluteerror | V40I_H100_STATUS_RUNTIME_DISTRIBUTION.json / V40I_H100_FEATURE_VISIBILITY_AUDIT.json | Population mix HIGH; fitted-tree cause NOT PROVEN | Final model/encoder state discarded; FAILED effect PLAUSIBLE_NOT_PROVEN. |
| POINT PREDICTION → POOLED q | Existing completed calibration N=2,562, mean error +7,064s, underprediction64.13%; frozen pooled positive-residual q90=5,576.44921875s | V40I_H100_COMPLETED_POINT_MODEL_METRICS.json | HIGH for saved predictions | Rolling calibration evidence is not an independent final fitted-state holdout. |
| POOLED q → SAFE DURATION | min(requested,max(point+q,900)); ceil to900s. +29 jobs have effective22,500s | V40I_H100_COMPLETED_DIAGNOSTIC_RESIDUAL_QUANTILES.json / ../pending_runtime_forensic/V40I_PENDING_RUNTIME_PREDICTOR_LINEAGE.json | HIGH | No conditional coverage guarantee; diagnostic q not applied. |
| SAFE DURATION → PLANNED OCCUPANCY | Frozen DA service/start/site yields downstream B0 223, B1 182 GPU at slot73 | ../may01_actual_forensic/DA_VS_ACTUAL_JOB_COMPARISON.parquet | HIGH in modeled domain | D-1 closed cohort excludes later arrivals. |
| PLANNED OCCUPANCY → B1 SITE/TIME DECISION | Saved 539 site changes and461 start changes; primary bound matches optimum; hierarchy preserved | ../../v40g_joint_aidc/V40G_MAY01_FINAL_REPORT.json | HIGH historical Planning | No fresh V40I optimization; not a future execution authorization. |
| B1 DECISION + ACTUAL RUNTIME → ACTUAL OCCUPANCY | 29 one-GPU jobs run28,577–43,227s; frozen dispatcher with segment migration/conservation | V40I_MAY01_29JOB_H100_TAIL_POSITION.csv / ../may01_actual_forensic/B1_CRITICAL_ACTIVE_UID_SET.json | HIGH for frozen replay | Timing derived from original start/end; physical execution-site authority is separate and not promoted. |
| ACTUAL OCCUPANCY → DOWNSTREAM LOAD | B0 171, B1 173; temporal−2 + spatial9 + interaction−4 + migration−1 = +2 GPU | ../pending_runtime_forensic/V40I_SLOT73_FROZEN_DECISION_DECOMPOSITION.json | HIGH exact UID reconciliation | Factorial intermediate dispatch is causal diagnostic, not a certified feasible new policy. |
| DOWNSTREAM GPU → P PROFILE | CENTER incremental GPU power plus C1 PCC model; downstream delta≈1.09545kW | ../pending_runtime_forensic/V40I_AIDC_CONTROLLABLE_PENETRATION.json | HIGH within frozen power model | Synthetic power mapping, not independent per-job measured PCC. |
| P PROFILE → Q/P REPRESENTATION | Q=P*tan(acos(.95)), both cases and all namespaces | V40I_AIDC_REACTIVE_MODEL_LINEAGE.json | HIGH code/setpoint identity; physical fidelity OPEN | PCC_Q/readback is derived; no independent facility time-varying Q authority. |
| P/Q REPRESENTATION → FEEDER P/Q FLOW | Frozen IEEE123 model, native mapping, background/PV, regulators/capacitors; existing AC results | V40I_AIDC_PCC_Q_AUTHORITY_AUDIT.json | HIGH simulated lineage | Flow Q is a network response conditioned on prescribed AIDC Q; no measured Q validation. |
| FEEDER P/Q FLOW → PHASE-A CURRENT | Fixed-PF directional gradient predicts+0.14891585A; saved+0.14624173A; mismatch1.8286% | V40I_AIDC_PQ_SENSITIVITY_FORENSIC.json | HIGH saved numbers; approximate differential | AIDC pure P/Q derivatives unavailable; separate-PCC MESS proxies cannot certify AIDC Q partials. |
| PHASE-A CURRENT → rho | Fixed418A rating; Actual B1 rho0.5895856573 versus B0 0.5892357967 | ../../v40g_joint_aidc/V40G_MAY01_FINAL_REPORT.json | HIGH saved electrical result | Actual outcome sign is scientific result, not an integrity-failure gate. |

Actual timing과 execution-site authority는 별개다. 122 case 중 50개는 timing으로 legitimate pre-day completion을 입증했으나 actual site를 승인한 case는 0개, 72개는 unresolved다. May-01의 historical synthetic replay forensic은 이 72개 production blocker를 해제하지 않는다.

Runtime/site occupancy 역전은 재현됐다. 고정 PF에 연결된 P/Q 전류 변화도 저장 결과와 근접한다. 다만 이것을 Q를 고정한 순수 P 효과 또는 PF=0.95 현실성 검증으로 바꾸지 않는다.
