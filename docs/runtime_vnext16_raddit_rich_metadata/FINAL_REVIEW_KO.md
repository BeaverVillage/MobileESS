# Runtime-vNext16 최종 검토

판정: **LIMITED_OR_MIXED_INFORMATION_VALUE**. 운영 Runtime 선택: **NONE**. CC4: **C0**, rich 단계 **미실행**.

## 확정된 native 결과

| Arm | Pooled Q90 | Min-fold | >4h | >12h | >24h | Pinball (s) | Nodeh 예약/실제 |
|---|---:|---:|---:|---:|---:|---:|---:|
| D0 | 84.74% | 82.02% | 63.69% | 34.75% | 16.19% | 3723.84 | 2.550 |
| D1 | 82.28% | 78.81% | 57.95% | 26.59% | 16.33% | 3461.57 | 2.038 |
| D2 | 83.71% | 80.23% | 60.53% | 25.32% | 15.88% | 3368.10 | 2.086 |
| D3 | 85.29% | 81.83% | 62.35% | 26.88% | 13.56% | 3417.55 | 2.143 |
| D4 | 86.04% | 80.57% | 59.95% | 25.43% | 12.31% | 3525.65 | 2.160 |
| IDENTITY_ONLY | 83.71% | 78.69% | 57.33% | 24.35% | 14.09% | 3453.64 | 2.063 |
| SOFTWARE_STACK | 85.87% | 82.68% | 70.77% | 43.50% | 18.59% | 3432.02 | 2.572 |
| NEG_SHUFFLE | 84.36% | 80.12% | 59.69% | 27.79% | 13.30% | 3482.96 | 2.330 |

모집단은 RADDiT historic의 완료 export 작업이다. 유일하게 매핑된 행과 기존 GPU Runtime 검증 fold의 교집합은 0건이며, 미매핑 행까지 모두 CPU 전용이라고 증명한 것은 아니다. Nodeh와 GPUh를 혼동하지 않는다. 초기 제출 시점의 metadata snapshot이 입증되지 않은 B 필드의 역사적 예측 연관성이므로, 관측된 개선을 실제 제출 경계의 인과적 효용으로 단정하지 않는다.

## 공개 embedding의 별도 진단

| 동일 표본 진단 | Min-fold | >4h | >12h | Pinball (s) |
|---|---:|---:|---:|---:|
| EMB_D0 | 83.42% | 65.74% | 35.38% | 4014.67 |
| EMB_D2 | 83.56% | 71.03% | 38.77% | 3370.08 |
| D_EMB_DIAGNOSTIC_ONLY | 77.92% | 62.98% | 23.09% | 3914.08 |

두 단계 모두 유일한 연구용 매핑만 사용했고 각 fold TRAIN을 동일한 10만 행으로 제한했다. 전체 4,096차원 좌표를 사용했다. 원본 표본의 D0–D4 수치와 직접 비교하지 않는다.

## 조건부 진단과 Runtime 단계

전체 native D1–D4 범위: 사전등록 material-win 조건을 충족한 arm이 없어 그룹 제거 학습은 NOT_RUN_NO_MATERIAL_WIN으로 기록했다. IDENTITY_ONLY와 SOFTWARE_STACK은 사전등록된 기본 정보 대비 실험이다. 별도로 같은 매핑·TRAIN cap 표본의 EMB_D2가 >4h +5.29pp, pinball 약16.06% 개선으로 사용자 그룹 제거 조건을 만족해 A–E를 제거하는 후속 진단을 완료했다(F는 채널 없음). 원 사전등록의 primary ablation 범위를 넘는 조건부 진단 확장이며, paired 결과 확인 후 실행 동결을 공개했다. Primary 판정·Runtime 선택에 소급 적용하지 않는다. 또한 사전등록 SOFTWARE_STACK 대비가 >4h +7.08pp와 pinball -7.84%로 사용자 조건을 만족해 별도 full-population 그룹 제거 진단을 완료했다. A는 실제 학습, E는 동일 설계행렬을 확인한 D0 재사용이며 B/C/D/F는 해당 채널이 없다. 이 역시 primary D1–D4 판정을 바꾸지 않는 공개된 조건부 진단 확장이다.

동일 매핑·TRAIN cap 표본의 EMB_D2 그룹 제거:

| 제거 그룹 | >4h | Pinball (s) |
|---|---:|---:|
| A | 67.56% | 4208.17 |
| B | 69.28% | 3388.06 |
| C | 67.06% | 3949.94 |
| D | 67.79% | 3470.66 |
| E | 71.99% | 3408.17 |

전체 native SOFTWARE_STACK 그룹 제거:

| 제거 그룹 | 상태 | Min-fold | >4h | Pinball (s) |
|---|---|---:|---:|---:|
| A | COMPLETED | 77.93% | 59.40% | 4856.84 |
| E | REUSED_EXACT_D0 | 82.02% | 63.69% | 3723.84 |

기존 GPU Runtime 5-fold 비교:

| Runtime arm | 상태 | Min-fold | >4h | Pinball (s) |
|---|---|---:|---:|---:|
| R0 | FROZEN_REFERENCE_RECOMPUTED | 70.70% | 69.72% | 4752.76 |
| R15 | FROZEN_REFERENCE_RECOMPUTED | 66.75% | 66.87% | 4720.18 |
| R16-A | COMPLETED | 66.21% | 64.79% | 5083.33 |
| R16-B | COMPLETED | 65.49% | 50.53% | 4972.60 |
| R16-C | COMPLETED | 61.77% | 64.85% | 5006.08 |

R16-A/B/C의 exact 5-fold 평가를 완료했고 TOTAL 통과 모델은 없다. H1은 R16-A로 평가했다. H2는 modules/conda 권한 부재로 미실행이다. Stage C/provider, remaining, April은 TOTAL 실패로 미실행이며 May는 unopened다. CC4 rich 단계는 조건 미충족으로 미실행이며 C0를 유지했다. 미실행 지표는 빈 값이며 0·PASS·추정값으로 채우지 않았다.

## 보존과 해석 한계

V6–V15의 1,548개 tracked 파일, 531개 이전 local evidence, 원본 23,601개 크기/mtime fingerprint를 보존 대상으로 유지했다. 최종 재검증 결과는 VERIFICATION.json에 있다. 최초 경계 assertion과 잘못된 namespace 검사 결과도 삭제하지 않았다.

### 1. PR #89가 실제 추가한 필드는?

user와 submit_line의 익명 안정 ID이다. recurrence/co-occurrence/SVD32로 표현했다.

### 2. 왜 PR #89는 full RADDiT 실험이 아니었는가?

account, name/script/job_type, modules/conda, 공개 배포 벡터의 정보가치를 모두 평가하지 않았기 때문이다.

### 3. historic_job_trace의 실제 필드는?

submit_time, start_time, end_time, nodes_req, processors_req, qos, wallclock_used_sec, avg_power_per_node, wallclock_req_sec, memory_req_raw, modules, conda_envs, user, name, account, partition, script, submit_line, job_type, job_id의 20개이다. 2,557,884행을 실제 감사했다.

### 4. 어떤 것이 익명 ID인가?

user/account/name/script/submit_line/job_type/partition 및 module/conda 토큰이다. 접미 숫자의 크기, 문자열 거리, 언어 임베딩 의미를 사용하지 않았다.

### 5. 실제 workflow/software-stack 정보는?

modules 225종과 conda 474종의 토큰 포함·반복 정보는 있다. 다만 익명 스택 정체성이고 실제 프로그램명·버전·스크립트 의미는 확인되지 않았다.

### 6. 어떤 것이 제출 시점에 관찰 가능한가?

제출 이벤트와 요청 자원 및 일부 제출 메타데이터는 개념상 관찰 가능하다. 개념적 가능성과 이 아카이브의 초기값/수집 시점 증명은 별개이다. 각 source-field의 A/B/C를 authority CSV에 기록했다.

### 7. 미래 V42에서 무엇을 재현할 수 있는가?

기존 user/submit_line 개념은 immutable accepted-submit receipt와 동일 namespace가 필요하다. 다른 rich field는 capture/version/namespace authority가 추가로 필요하다. 새 운영 모델을 승인하지 않았다.

### 8. 어떤 것은 diagnostic-only인가?

RADDiT rich metadata, software stack, 배포 좌표 및 초기값이 입증되지 않은 요청 snapshot이다. native 정보가치 시험의 B 정보가 운영 A 정보로 자동 승격되지 않는다.

### 9. 금지 필드는?

실제 runtime/start/end, 실제 전력, 미래 queue/scheduler outcome이다. start/end는 인덱스·완료 자격·연결 감사에만, runtime은 label/엄격히 완료된 이웃 통계에만 사용했다. positional job_id는 예측변수가 아니다.

### 10. 연구용 proxy 연결률은?

Historic→Kestrel 2,069,804/2,557,884 (80.92%). 두 단계 모두 유일한 embedding 연결은 1,504,846/1,780,972 (84.50%)이다. 운영 출처 증명은 아니다.

### 11. 모호한 행은 몇 개인가?

Embedding→historic EKEY2에서 5,458행을 제외했다. 그 유일 후보 중 Kestrel 단계에서 270,668행이 추가로 모호했다. Historic 전체에서는 488,080행이 모호했다. 모호한 행을 임의 순서로 매칭하지 않았다.

### 12. 보류 필드 충돌은?

비교 가능한 start_time/QoS 충돌은 0건이다. 첫 구현에서 서로 다른 partition namespace를 직접 비교한 오류를 수정했고 최초 결과·행 ledger를 보존했다. partition 대응표는 추정하지 않았으며 해당 필드는 NOT_COMPARABLE이다.

### 13. rich metadata가 native Runtime을 개선하는가?

사전등록 판정은 LIMITED_OR_MIXED_INFORMATION_VALUE이다. D0–D4의 동일 세 expanding fold 지표는 위 표와 CSV에 고정했다. pooled 수치만으로 선택하지 않았다.

### 14. user/account identity는 도움이 되는가?

IDENTITY_ONLY는 user/account/name/script의 공동 대비이며 user/account 단독 효과를 입증하지 않는다. 전체 native D1–D4 범위: 사전등록 material-win 조건을 충족한 arm이 없어 그룹 제거 학습은 NOT_RUN_NO_MATERIAL_WIN으로 기록했다. IDENTITY_ONLY와 SOFTWARE_STACK은 사전등록된 기본 정보 대비 실험이다. 별도로 같은 매핑·TRAIN cap 표본의 EMB_D2가 >4h +5.29pp, pinball 약16.06% 개선으로 사용자 그룹 제거 조건을 만족해 A–E를 제거하는 후속 진단을 완료했다(F는 채널 없음). 원 사전등록의 primary ablation 범위를 넘는 조건부 진단 확장이며, paired 결과 확인 후 실행 동결을 공개했다. Primary 판정·Runtime 선택에 소급 적용하지 않는다. 또한 사전등록 SOFTWARE_STACK 대비가 >4h +7.08pp와 pinball -7.84%로 사용자 조건을 만족해 별도 full-population 그룹 제거 진단을 완료했다. A는 실제 학습, E는 동일 설계행렬을 확인한 D0 재사용이며 B/C/D/F는 해당 채널이 없다. 이 역시 primary D1–D4 판정을 바꾸지 않는 공개된 조건부 진단 확장이다. Paired EMB_D2에서 user/account 그룹 C 제거: >4h 67.06%, pinball 3949.94s.

### 15. script/job identity는 도움이 되는가?

D1·IDENTITY_ONLY에 포함했으며 익명 script의 fold별 unseen 비율이 높다. 단독 원인의 증명으로 해석하지 않는다. material-win 없는 자동 전수 ablation은 하지 않았다. Paired 그룹 D 제거: >4h 67.79%, pinball 3470.66s.

### 16. modules/conda는 도움이 되는가?

SOFTWARE_STACK: min-fold 82.68%, >4h 70.77%, pinball 3432.02s. D1→D2와 함께 평가해야 하며 실제 소프트웨어 의미 복원의 증거는 아니다. Paired 그룹 E 제거: >4h 71.99%, pinball 3408.17s. 전체 native SOFTWARE_STACK에서 자원 A 제거: min-fold 77.93%, >4h 59.40%, pinball 4856.84s. Stack E 제거는 정확히 D0이다. Stack 대비의 min-fold 개선은 +0.66pp로, 엄격한 +5pp 동시 개선 기준에는 미달한다. 이 신호는 workflow 의미를 복원하거나 미래 제출에서 같은 토큰을 확보했다는 증거가 아니다.

### 17. 요청 자원은 도움이 되는가?

D0: min-fold 82.02%, >4h 63.69%, pinball 3723.84s. 이 기준 대비 추가 정보의 효과를 측정했다. 초기 requested-walltime version의 운영 권한을 새로 인정한 것은 아니다.

### 18. 완료 이웃은 도움이 되는가?

D4: min-fold 80.57%, >4h 59.95%, pinball 3525.65s. D2에 추가한 k16/64 완료 이웃 통계의 대비이다. 제한 후보 집합에서의 결정적 검색이며 전역 완전 탐색은 아니다.

### 19. 개선이 시간에 걸쳐 안정적인가?

사전등록된 consistent_temporal_gain은 3개 중 2개 이상 fold에서 >4h와 pinball이 모두 개선되고 어느 fold도 >4h가 5pp 넘게 악화되지 않는 조건이다. 해당 여부: D1=False, D2=False, D3=False, D4=False

### 20. >4h 개선은?

D0 63.69%; 가장 낮은 pinball의 rich arm D2 60.53%. 모든 arm을 공개했다.

### 21. >12h 개선은?

D0 34.75%; D2 25.32%.

### 22. >24h 개선은?

D0 16.19%; D2 15.88%. 지원 표본수는 tail CSV에 있다.

### 23. pinball은?

D0 3723.84s; D2 3368.10s, 상대 변화 -9.55%. 이 순위는 보고용이며 배포 선택이 아니다.

### 24. 예약 비율은?

Nodeh 예약/실제: D0 2.550, D2 2.086. GPU량을 제공하지 않는 native에 GPUh를 만들어 넣지 않았다. short-job 비율과 requested-walltime 대비 비율도 공개했다.

### 25. randomized identity 대조군은?

user/account/script를 안정적인 무작위 ID로 일대일 치환해 전체 TRAIN/VALID 설계행렬이 정확히 같음을 확인했다. 같은 고정 모델 예측도 같다. 이는 이름 불변성 대조군이며 identity 정보를 제거하는 귀무 대조군이 아니다. 별도의 TRAIN 일별 공동 셔플 NEG_SHUFFLE은 실제로 재학습했다.

### 26. target encoding에 미래 정답이 들어갔는가?

아니다. 범주·토큰·recurrence는 label-free TRAIN fit이다. 이웃 target 통계는 엄격한 완료 시간 제한을 적용했다. VALID 정답과 이전 VALID 작업의 정답도 풀에 넣지 않았다.

### 27. 완료된 과거 이웃만 썼는가?

그렇다. 모든 선택 이웃 ID의 strict end<submit을 검사했고 위반은 0건이다. end==submit 및 미완료 후보 강제 주입, 미래 poison, fresh-process 재생 검사를 수행했다.

### 28. 공개 배포 embedding의 진단 가치는?

동일 매핑·표본의 EMB_D0 min 83.42%, >4h 65.74%, pinball 4014.67s; 배포 좌표 모델 min 77.92%, >4h 62.98%, pinball 3914.08s. TRAIN 10만 cap·고정 LightGBM·완료 export 표본의 범위이며 모든 잠재 표현에 대한 부정적 증명이 아니다.

### 29. 그 벡터를 미래 V42 작업에 생성할 수 있는가?

입증되지 않았다. 저장된 4,096차원 좌표만 직접 읽었고 private inverse transform이나 새 LLM은 사용하지 않았다. 운영 선택 금지이다.

### 30. 배포 필터 뒤에 무엇이 남는가?

새 권한이 입증된 rich field는 없다. 기존 user/submit_line 개념만 receipt·namespace 조건부로 남고, modules/conda는 원본 Kestrel에 없다. Native 유일 매핑 행은 기존 GPU Runtime VALID 5개 fold와 교집합 0건이다.

### 31. 배포 모델에도 native 개선이 남는가?

원래와 동일한 GPU Runtime 5개 fold에서 R16-A/B/C를 실행했다. 전체 gate를 통과한 모델은 없다. Native 모집단의 개선을 직접 옮기지 않고 기존 receipt/namespace 계약의 user/submit_line만 추가했다. PR #89 이후 새로운 원본 정보축을 확보한 것이 아니라 기존 두 개념을 다른 고정 표현으로 평가했다. 위 Runtime 표와 각 fold CSV가 실제 결과이다.

### 32. CatBoost가 동일 정보 V13 hazard보다 좋은가?

CatBoost는 평가하지 않았다. 허용된 LightGBM direct quantile을 동일 입력의 V13 hazard와 비교했다. Direct quantile은 exact label TRAIN subset, hazard는 censoring likelihood도 사용하므로 순수 architecture 우위로 해석할 수 없다. H0=R0, H1=R16-A; H2는 modules/conda 권한 부재로 미실행이다.

### 33. 모델 개선인가 정보 개선인가?

Native D0–D4는 같은 family의 정보 대비이다. GPU bridge에서는 H0→H1이 동일 hazard family의 user/submit_line 정보 대비이고 R16-C는 완료 이웃 추가 대비이다. R16-B는 architecture와 censoring 처리도 달라 단독으로 순수 정보 효과나 CatBoost 우위를 주장하지 않는다.

### 34. R0 baseline은 유지됐는가?

그렇다. exact V13 EXPANDING_S4의 저장된 예측을 독립 재집계했다. pooled 91.84%, min-fold 70.70%, >4h 69.72%, >12h 64.25%, >24h 46.88%, pinball 4,752.7617s이다.

### 35. 결과 후 gate를 바꿨는가?

성공·STOP·Runtime 안전 threshold, 모델 family·표현·fold·seed는 바꾸지 않았다. 다만 제가 추가했던 회색 구간 자동 중단은 원문의 명시한 STOP에서만 중단하라는 지시와 달라, 일부 native 결과 이후 전체 STOP이 아니면 고정 bridge 평가를 계속하도록 실행 경로를 정정했다. EXECUTION_ROUTING_CORRECTION.json에 시점과 당시 보인 결과를 공개했고 원 사전등록도 보존했다. partition namespace 연결 오류 수정은 ML 전에 이루어졌다.

### 36. Runtime min-fold 85%를 통과했는가?

R0: 70.70%, 해당 gate=False; R16-A: 66.21%, 해당 gate=False; R16-B: 65.49%, 해당 gate=False; R16-C: 61.77%, 해당 gate=False. 개별 gate와 전체 TOTAL 승인은 별개이다.

### 37. Runtime >4h 85%를 통과했는가?

R0: 69.72%, 해당 gate=False; R16-A: 64.79%, 해당 gate=False; R16-B: 50.53%, 해당 gate=False; R16-C: 64.85%, 해당 gate=False. 개별 gate와 전체 TOTAL 승인은 별개이다.

### 38. Runtime >12h 80%를 통과했는가?

R0: 64.25%, 해당 gate=False; R16-A: 57.05%, 해당 gate=False; R16-B: 38.12%, 해당 gate=False; R16-C: 57.17%, 해당 gate=False. 개별 gate와 전체 TOTAL 승인은 별개이다.

### 39. Runtime >24h 70%를 통과했는가?

R0: 46.88%, 해당 gate=False; R16-A: 47.86%, 해당 gate=False; R16-B: 25.30%, 해당 gate=False; R16-C: 43.39%, 해당 gate=False. 개별 gate와 전체 TOTAL 승인은 별개이다.

### 40. 미래 작업에 provider를 호출할 수 있는가?

저장한 연구 모델과 receipt adapter의 재생·미지 ID 처리·시간/필드 거부를 검증했다. 실제 V42 운영 provider는 TOTAL 실패로 통합·승격하지 않았다. Operational namespace/capture service가 검증됐다는 주장도 하지 않는다.

### 41. raw string이 optimizer 로그에 들어갔는가?

아니다. optimizer를 실행하지 않았다. V2 명세는 허용된 pseudonym·숫자·bundle digest·Q50/Q90만 optimizer 경계에 전달하도록 제한한다.

### 42. online refit이 필요한가?

연구용 고정 adapter/model 재생에는 필요 없다. 새 운영 provider가 준비됐다는 뜻은 아니다.

### 43. remaining-runtime을 조기에 실행했는가?

아니다. NOT_RUN_TOTAL_GATE_FAILURE이다.

### 44. CC4는 선행 증거에 의해 gate됐는가?

Runtime 평가·선택을 먼저 동결한 뒤 CC4 선행 information-value 조건이 충족되지 않아 C3/C4를 실행하지 않았다. NOT_RUN_CC4_INFORMATION_GATE. C0는 유지했다.

### 45. CC4가 미래 미제출 semantics를 봤는가?

아니다. CC4 rich 단계는 미실행이고 기존 evidence를 보존했다.

### 46. C0는 T0/B0인가?

그렇다. hourly submitted-GPUh LightGBM T0/B0를 유지했다. T2_F0/T3_F2는 연구 후보 상태이며 승격하지 않았다.

### 47. April을 선택에 썼는가?

아니다. 별도 April 평가도 미실행이다. 다만 3월 원본 파일의 UTC 4월 경계 10,760행은 경계 검사에서 읽힌 뒤 즉시 제외됐다. 이를 April payload를 전혀 읽지 않았다고 표현하지 않는다.

### 48. May를 열었는가?

2025년 May holdout을 열지 않았다. 2024년 May는 기존 과거 TRAIN 기간으로 별개의 데이터이다.

### 49. optimizer/MESS/OpenDSS를 변경했는가?

아니다. V42 기존 파일·flexibility branch·optimizer·MESS를 변경하지 않았고 OpenDSS를 실행하지 않았다.

### 50. 정당화되는 최종 과학적 결론은?

LIMITED_OR_MIXED_INFORMATION_VALUE. 이번에 관측한 익명 rich metadata와 고정 모델 실험은 native 정보가치, 미래 제출 재현성, GPU Runtime 안전성의 세 질문을 구분한다. 새 Runtime provider 승격 근거는 없다. Runtime의 본질적 무작위성·예측 불가능성·current-state 무용성·hidden-variable 원인은 증명되지 않았다. 다음 연구는 실제 workflow/application 의미와 정확히 job-level join 가능한 external telemetry, 초기 제출 receipt를 별도 사전등록 실험으로 검증해야 한다. 특히 native SOFTWARE_STACK은 >4h 63.69%→70.77%의 부분적 정보가치를 보였으므로 정보가 전혀 없다고 결론내릴 수 없다. 다만 min-fold 동시 개선과 source authority, GPU 모집단 전이를 함께 확립하지 못했다.
