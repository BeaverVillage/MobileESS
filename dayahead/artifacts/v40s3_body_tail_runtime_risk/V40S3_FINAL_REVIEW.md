# V40S3 최종 검토

- final classification: **V40S3_CAUSAL_TAIL_RISK_INFORMATION_INSUFFICIENT**
- selected runtime threshold u: **NONE**
- selected body model: **NONE**
- selected tail classifier: **NONE**
- selected eta: **NONE**
- selected robust policy: **NONE**
- causal authority: **PASS — normative PENDING reconstruction + strict submit_hour/weekday**
- body safety: **최종 방법 PASS 없음**. DEV+CAL에서는 4h B1/B2/B3 body gate PASS; 노출 평가 4h는 FAIL. 일부 body의 안전성을 부정하지 않는다.
- tail detection: **FAIL** — selective/temporal/calibration 조건 동시 충족 없음
- hybrid safety: **FAIL** — eligible method 없음
- production integration: **NO**

사용자 보정에 따라 membership authority와 predictor-feature provenance를 분리했다. contemporaneous saved snapshot 부재로 종료하지 않았다. 기존 조기 종료 기록은 superseded 디렉터리에 보존하고, 수정 사전등록 commit 이후 CPU body/tail 실험을 끝까지 실행했다. 새 resource/proxy predictor, 추가 architecture, 사후 retuning은 없다.

1. Live PR #27 head: `a2a21c904535125c66668a294f91d73a66f5d4a7`; branch `codex/v40a-bounded-iterative-aidc-mess-coopt`. 역사적8ff3dc는 ancestor이며 최신 head로 사용하지 않았다. 작업 branch `codex/v40s3-body-tail-runtime-risk`.
2. 원본 S2 identity 73,504 / positive72,292 / zero1,212 / negative0 / duplicate0 / missing start/end0, exact end−start PASS. 성공 COMPLETED-only가 아닌 terminal-event source다.
3. PENDING panel 10,883 job-issue / 7,603 unique jobs. TRAIN1,190 / DEV4,346 / CAL2,634 / exposedEVAL2,713. 동일 job의 일별 반복 의사결정을 보존한다. TRAIN beforeMar22 08UTC, DEV beforeApr01 08UTC, CAL beforeApr08 08UTC, EVAL beforeApr24 00UTC에 end_time이 알려진 행만 사용했다. 원본 terminal selection과 incomplete-job 누락 때문에 전체 PENDING backlog census로 일반화하지 않는다.
4. Causal features: recorded UTC submit_hour, weekday만. submit<=issue 확인. tree는2열 numeric, logistic은 이 두 시계 feature의 고정24+7 one-hot. 새 body35 primary/repeat tree·logistic fit은 모두CPU single-thread; 실제 모델 primary35+repeat35, empirical quantile5/base-rate5. 독립 반복 학습+train prediction bytes35쌍 maxdifference0.
5. requested walltime/GPU/nodes/cores/memory/partition/QoS/hardware/standby/user/account/support derivatives를 새 predictor로 거부했다. GPU는 평가 weight, walltime/K0는 existing comparator에만 사용한다. start/end는 membership·availability·label에만 사용한다.

6. TRAIN/development threshold forensic (current-recipe B0 raw safe seconds; 실제 body membership oracle):

| u(h) | TRAIN percentile | DEV tail N / % | tail GPU miss mass % | body Q90 / GPU coverage % | body safe MAE(s) / WAPE |
|---:|---:|---:|---:|---:|---:|
| 4 | 53.025 | 1792 / 41.233 | 99.521 | 99.491 / 97.489 | 34901.888 / 12.0983 |
| 6 | 78.235 | 1569 / 36.102 | 98.207 | 99.028 / 95.727 | 34496.780 / 8.5142 |
| 8 | 85.126 | 1490 / 34.284 | 97.032 | 98.599 / 94.900 | 34005.850 / 7.3488 |
| 12 | 89.664 | 1447 / 33.295 | 94.432 | 97.930 / 93.630 | 33694.513 / 6.6714 |
| 24 | 95.798 | 117 / 2.692 | 76.698 | 67.463 / 74.495 | 24778.745 / 1.1223 |

7. u는 NONE. 120개 새 body×classifier×R0/R1×u 조합 중 DEV+CAL 전체 gate 통과0. B0 reference-only40개는 새 causal body winner 후보가 아니다. 사전등록되지 않은 u/threshold/fallback을 추가하지 않았다.
8. B0 current-recipe, B1 LightGBM quantile, B2 XGBoost quantile, B3 global empirical TRAIN-body quantile. 새 Q50/Q90는 positive finite, raw crossing을 공개하고 사전등록한 순서대로 두 quantile을 정렬했다. DEV+CAL raw crossing2,568 / exposed505 (candidate×threshold×job-issue 출력 단위), nonpositive0. 정렬 후 Q50<=Q90 전부 충족. 추가 body calibration C0=none; globalq 자동 가산 없음.
9–12. 노출 평가 oracle body 지표. MAE/WAPE/positive mass는 raw Q90 기준; Q50 MAE, log-MAE, slot error, 일별/GPU-band 상세는 BODY_METRICS.csv에 있다. 이 표는 선택 결과를 바꾸지 않는다.

| u | body | N | Q90% | GPU% | Q90 MAE(s) | Q50 MAE(s) | WAPE | GPU miss sec |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 4 | B0 | 1484 | 61.860 | 65.788 | 4750.91 | 4684.79 | 0.7313 | 2524208.29 |
| 4 | B1 | 1484 | 88.679 | 90.385 | 7170.82 | 6219.01 | 1.1038 | 160927.70 |
| 4 | B2 | 1484 | 87.197 | 88.679 | 7125.87 | 6727.13 | 1.0968 | 213005.71 |
| 4 | B3 | 1484 | 89.016 | 90.199 | 7027.64 | 5353.81 | 1.0817 | 164147.00 |
| 6 | B0 | 2123 | 43.570 | 47.545 | 5536.21 | 7137.12 | 0.5715 | 10734544.62 |
| 6 | B1 | 2123 | 95.478 | 91.735 | 10066.78 | 6097.59 | 1.0391 | 522930.98 |
| 6 | B2 | 2123 | 89.119 | 85.892 | 9083.18 | 7223.48 | 0.9376 | 1010777.58 |
| 6 | B3 | 2123 | 92.699 | 93.624 | 9079.64 | 5853.22 | 0.9372 | 389774.00 |
| 8 | B0 | 2404 | 38.727 | 42.871 | 6569.17 | 8614.38 | 0.5845 | 17384444.44 |
| 8 | B1 | 2404 | 96.090 | 92.742 | 12644.44 | 6994.79 | 1.1250 | 1088380.35 |
| 8 | B2 | 2404 | 93.344 | 90.078 | 13058.18 | 8101.73 | 1.1618 | 1040452.26 |
| 8 | B3 | 2404 | 86.398 | 87.910 | 9879.73 | 6412.40 | 0.8790 | 1275895.60 |
| 12 | B0 | 2651 | 35.119 | 40.015 | 7453.52 | 9827.75 | 0.5554 | 23241102.86 |
| 12 | B1 | 2651 | 89.891 | 88.679 | 17108.09 | 9503.82 | 1.2747 | 5578881.84 |
| 12 | B2 | 2651 | 89.928 | 88.567 | 19668.06 | 9114.35 | 1.4654 | 5707528.78 |
| 12 | B3 | 2651 | 87.514 | 90.460 | 12265.30 | 7840.25 | 0.9139 | 4148946.60 |
| 24 | B0 | 2694 | 34.558 | 39.186 | 7848.55 | 10273.89 | 0.5620 | 26938746.55 |
| 24 | B1 | 2694 | 82.665 | 85.823 | 27068.69 | 9999.91 | 1.9382 | 8343588.19 |
| 24 | B2 | 2694 | 83.073 | 87.132 | 26017.26 | 14404.33 | 1.8629 | 9983451.17 |
| 24 | B3 | 2694 | 90.794 | 92.875 | 17791.84 | 8233.99 | 1.2740 | 3586870.20 |

13. Exposed tail prevalence: 4h45.300%, 6h21.747%, 8h11.390%, 12h2.285%, 24h0.700%. DEV tail prevalence와 섞지 않는다.
14–18. Exposed classifier 지표 및 CAL에서 고정된 eta. Mass capture는 B3 body Q90 기준 비교이며 body별 전체 수치는 별도 CSV에 있다. u12 exposed tailN62는 recall gate support 부족, u24 CAL tailN43은 eta 자체를 선정하지 않는다.

| u | C | ROC / PR | ECE | eta | recall% / GPU% | mass capture% | flagged% |
|---:|---|---:|---:|---:|---:|---:|---:|
| 4 | C0 | 0.5000 / 0.4530 | 0.0167 | 0.4697 | 100.000 / 100.000 | 100.000 | 100.000 |
| 4 | C1 | 0.5129 / 0.4453 | 0.1519 | 0.2274 | 96.420 / 93.373 | 72.135 | 97.383 |
| 4 | C2 | 0.2712 / 0.3645 | 0.3461 | 0.2505 | 92.514 / 89.465 | 71.328 | 93.734 |
| 4 | C3 | 0.2722 / 0.3650 | 0.3669 | 0.2368 | 92.514 / 89.465 | 71.328 | 93.734 |
| 6 | C0 | 0.5000 / 0.2175 | 0.0002 | 0.2176 | 100.000 / 100.000 | 100.000 | 100.000 |
| 6 | C1 | 0.4215 / 0.2106 | 0.1750 | 0.1666 | 74.915 / 68.617 | 56.312 | 91.080 |
| 6 | C2 | 0.2254 / 0.1543 | 0.3049 | 0.0540 | 75.424 / 78.273 | 91.290 | 88.832 |
| 6 | C3 | 0.2437 / 0.1592 | 0.3741 | 0.0672 | 75.424 / 78.273 | 91.290 | 88.758 |
| 8 | C0 | 0.5000 / 0.1139 | 0.0348 | 0.1487 | 100.000 / 100.000 | 100.000 | 100.000 |
| 8 | C1 | 0.5932 / 0.1878 | 0.0973 | 0.1485 | 58.576 / 36.976 | 25.454 | 29.709 |
| 8 | C2 | 0.3857 / 0.1129 | 0.1752 | 0.0303 | 92.880 / 95.446 | 93.208 | 88.832 |
| 8 | C3 | 0.2997 / 0.1006 | 0.1857 | 0.0408 | 92.880 / 95.446 | 92.557 | 83.708 |
| 12 | C0 | 0.5000 / 0.0229 | 0.0805 | 0.1034 | 100.000 / 100.000 | 100.000 | 100.000 |
| 12 | C1 | 0.4026 / 0.0201 | 0.0837 | 0.0486 | 30.645 / 31.579 | 37.609 | 28.787 |
| 12 | C2 | 0.4645 / 0.0235 | 0.0692 | 0.0094 | 82.258 / 76.842 | 80.570 | 87.541 |
| 12 | C3 | 0.6238 / 0.0427 | 0.0506 | 0.0206 | 100.000 / 100.000 | 99.753 | 82.013 |
| 24 | C0 | 0.5000 / 0.0070 | 0.0350 | N/A | N/A / N/A | N/A | N/A |
| 24 | C1 | 0.1022 / 0.0066 | 0.0331 | N/A | N/A / N/A | N/A | N/A |
| 24 | C2 | 0.1027 / 0.0068 | 0.0014 | N/A | N/A / N/A | N/A | N/A |
| 24 | C3 | 0.3311 / 0.0098 | 0.0327 | N/A | N/A / N/A | N/A | N/A |

19–20. R0/R1全組合을 optimizer 없이 replay했다. 예시4h B1+C2는 사전선정이 아닌 고정 후보 진단이다: R0 exposed coverage34.243% / GPU38.777%, miss+1,022,581 GPU·s, overreservation+18.550 GPUh. R1 coverage90.822% / GPU90.391%, miss−23,892,856 GPU·s, overreservation+44,378.596 GPUh (13.217배). 따라서 R1의 coverage 개선만으로 채택하지 않는다. walltime은 guaranteed ceiling이 아니다.
21. selected hybrid policy NONE. 최종 denominator는 BODY+TAIL 전체 job-issue다. u24는 eta support 부족으로 replay null; 다른 threshold로 대체하지 않았다.
22–25. selected overall/GPU coverage, underprediction reduction, overreservation delta는 모두 N/A. 현재 recipe reference exposed 2,713행은 15min coverage35.017% / GPU39.333%, miss32,291,178 GPU·s, overreserve3,632.428 GPUh. 이 값은 current production Apr01 final-state 동일성 주장이 아니다. full-panel exact-current-state 비교는 불가하다. 현재 head의 실제 Apr01 ledger도 조사했지만 해당 issue의 accepted panel행이0이라 exact match0; 없는 비교값은 만들지 않았다.
26. H=120 terminal transition: N/A. 해당 panel에 joined frozen scheduled start가 없으며 actual service start를 scheduling start로 대체하지 않았다. matched0을 transition0이라고 쓰지 않는다.
27. inherited migration touch count: N/A. PENDING panel에 join 가능한 inherited migration witness 없음. 새로운 witness/solve0.
28. **migration changed = NO**. RUNNING/A1/M1/MF/WAN/Rack/terminal/Fresh 수정0.
29. May scientific runtime/status/outcome/training/calibration/u/eta/model/hybrid selection reads 모두0. 초기 May path/code/index metadata discovery는 NONZERO이며 전체 read0을 주장하지 않는다. canonical cutoff May01 00:00 fixedAEST = Apr30 14:00UTC; 실제 source는 Apr24UTC 이전으로 더 제한했다.
30. TRUE_CONFIRMATORY_AVAILABLE=NO. Apr24–30 shadow SEALED; 행0read. 노출 평가는 확인용 untouched test가 아니다.
31. 73 PASS /0FAIL/0SKIP software/protocol tests. 모델과학적 safety PASS와 구분한다. 독립 eta 최대성, 전체 exposed hybrid GPU miss/reserve 수치, predictor 비허용 feature 불변성, label/timestamp/commit SHA 검증 포함.
32. Base의 모든 기존 tracked blob identity와 변경 경로를 검증했다. 변경은 dayahead/v40s3 및 artifacts/v40s3_body_tail_runtime_risk 내부뿐. q5576.44921875, PF.95, QcontrolNO, electricalHOLD, B0–B3NO, FULL_MAYNO 유지.
33. 미래 adapter는 정확히10 fields: job_uid, runtime_class, runtime_body_q50_sec, runtime_body_q90_sec, tail_probability, tail_threshold_sec, tail_flag, robust_tail_policy, candidate_duration_sec, flexibility_protected. 실제 추천행 export는[]; site/migration/MESS/electrical decision 필드 없음.
34. 이후 별도 integration revision에서 검토할 최소 consumer 파일은 아래 두 개다. 현재 수정0이며 optimizer 수학/solver 파일 변경 필요목록은[]다.
- `dayahead/v37/aidc_materializer.py:_jobs_and_ledger`: PENDING duration admission
- `dayahead/v40a/initial.py:build_initial`: PENDING metadata / eligible_standby admission
35. 반드시 보호할 optimizer/migration/WAN/terminal source 정확한 목록은 아래와 같다. 전체 기존 tracked파일도 보호하며 Git blob inventory는 PROTECTED_SCOPE_DIFF.json에 있다.

- `dayahead/tools/run_v35r3e_r1_beam.py`
- `dayahead/v17_ac_restoration_runner.py`
- `dayahead/v35r3/algorithm.py`
- `dayahead/v37/runner.py`
- `dayahead/v37r3/__init__.py`
- `dayahead/v37r3/restoration.py`
- `dayahead/v37r3/voltage_authority.py`
- `dayahead/v38/__init__.py`
- `dayahead/v38/authority.py`
- `dayahead/v38/contracts.py`
- `dayahead/v38/home.py`
- `dayahead/v38/preflight.py`
- `dayahead/v38/rack.py`
- `dayahead/v38/wan.py`
- `dayahead/v39e/__init__.py`
- `dayahead/v39e/campaign.py`
- `dayahead/v39e/campaign_adapter.py`
- `dayahead/v39e/contracts.py`
- `dayahead/v39e/evaluate.py`
- `dayahead/v39e/full_preflight.py`
- `dayahead/v39e/full_spatial.py`
- `dayahead/v39e/initial_state.py`
- `dayahead/v39e/overnight.py`
- `dayahead/v39e/progress.py`
- `dayahead/v39e/runtime.py`
- `dayahead/v39e/temporal_refreeze.py`
- `dayahead/v40a/__init__.py`
- `dayahead/v40a/accepted_initial.py`
- `dayahead/v40a/authority.py`
- `dayahead/v40a/context.py`
- `dayahead/v40a/contracts.py`
- `dayahead/v40a/coordination.py`
- `dayahead/v40a/feedback.py`
- `dayahead/v40a/firewall.py`
- `dayahead/v40a/grid.py`
- `dayahead/v40a/initial.py`
- `dayahead/v40a/invariants.py`
- `dayahead/v40a/mobility.py`
- `dayahead/v40a/observability.py`
- `dayahead/v40a/outcome_guard.py`
- `dayahead/v40a/postfreeze.py`
- `dayahead/v40a/prefix.py`
- `dayahead/v40a/recourse.py`
- `dayahead/v40a/runtime.py`
- `dayahead/v40g/__init__.py`
- `dayahead/v40g/actual.py`
- `dayahead/v40g/authority.py`
- `dayahead/v40g/domain.py`
- `dayahead/v40g/optimizer.py`
- `dayahead/v40g/physical.py`
- `dayahead/v40g/report.py`
- `dayahead/v40g/reuse.py`
- `dayahead/v40g/smoke.py`

preregistration: `d1fb031ff3ce8e69a2dc24fb76716405188dce18`
model/method NONE freeze before exposed evaluation: `bbe797dca17af716d5b9c0d2b9d0a20d6b905d90`
최종 과학 commit/receipt는 V40S3_FINAL_COMMIT_RECEIPT.json에서 별도 검증한다.

결론의 범위: 이번 고정 cohort/splits/models에서 현재 입증된 clock features로 선택적 tail 처리를 충분히 식별·보정하지 못했다. 모든 가능한 causal model이 원리적으로 실패한다는 주장도, PENDING membership authority가 없다는 주장도 아니다.
