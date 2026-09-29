# V42 / Runtime-vNext15 / CC4 최종 검토

SEMANTIC_INTERFACE_READY_MODELS_NOT_PROMOTED. Runtime 선택: NONE, CC4 기준 유지/선택: C0. 이 구현은 원래 RADDiT 배포 embedding이 아니다.

| Runtime | pooled Q90 | min-fold | >4h | >12h | >24h | Q90 pinball |
|---|---:|---:|---:|---:|---:|---:|
| R0 | 91.84% | 70.70% | 69.72% | 64.25% | 46.88% | 4752.7617 |
| R1 | 91.77% | 66.11% | 67.11% | 60.12% | 51.65% | 4852.5745 |
| R2 | 91.50% | 66.75% | 66.87% | 58.98% | 45.81% | 4720.1813 |

이 실험의 새 정보는 user/submit_line 익명 범주의 recurrence와 co-occurrence다. 실제 application 설명·script 내용·workflow 의미를 평가한 실험은 아니다. 따라서 runtime의 본질적 무작위성, 예측 불가능성, semantic 정보의 무용성 또는 hidden-variable 원인을 증명하지 않는다. 다음 연구에서는 시점과 join이 입증된 workflow/application semantic information 및 external telemetry의 추가 가치를 별도 preregistered experiment로 평가해야 한다.

실행 수리: 기존 CC4 환경에서 첫 SVD 준비가 네이티브 접근 위반으로 종료되어 실패 로그와 Windows 이벤트를 보존했다. CC4 validation을 보기 전에, 같은 학습 코드·TRAIN membership·차원·seed로 Runtime에서 검증한 환경을 사용해 semantic 준비만 완료했다. CC4 LightGBM은 원래 환경을 유지했다. 완료한 historical SVD 6회와 실패한 준비 시도 1회를 구분한다.

## 1. 왜 private RADDiT vector 복구를 중단했는가?

V14R2 종료와 사용자 결정에 따라 비공개 exporter/stripping/vector 환경 복구를 재개하지 않았다. V6–V14R2는 해시로 보존했다.

## 2. 새 representation은 RADDiT와 어떤 관계인가?

RADDiT의 제출 정보 활용 개념에서 영감을 받은 독립적인 submission-metadata latent representation이다. 배포 RADDiT embedding, private script 또는 Linq 모델을 사용하지 않았다.

## 3. Original Kestrel에서 어떤 submission field가 존재하는가?

원본 pre-April 6,326,884행을 조사했다. user/account/name/submit_line/script/job_type/workdir의 hash, partition/qos 및 array_pos/array_range가 있다. GPU 621,583행은 V13 원본 모집단과 정확히 일치한다.

## 4. 각 field는 semantic/category/opaque/missing 중 무엇인가?

Hash 필드는 STABLE_ANON_IDENTITY, partition/qos/array metadata는 STRUCTURED_SEMANTIC이다. modules/conda_envs/reservation/dependency는 MISSING이다. 안정된 토큰 반복과 원래 의미의 보존은 다르며 7자리 hash collision 가능성도 남는다.

## 5. 실제 free text는 존재하는가?

사용 가능한 실제 free text는 없다. name/submit_line/script의 비결측 값은 익명 hash이므로 TEXT_SEMANTIC_CHANNEL_AVAILABLE=FALSE, R3는 NOT_APPLICABLE이다.

## 6. 어떤 field가 submit 시점에 관측 가능한가?

새 historical whitelist는 제출자 user와 원래 제출 명령 submit_line이다. account/partition/qos/name 등의 최종 snapshot은 mutable하며 최초 버전이 미확인이고, custom script/job_type capture·derivation 시점도 입증되지 않아 새 semantic family에서 제외했다. 기존 R0는 원래 trace-proxy 한계를 그대로 유지한다.

## 7. V42 interface에 어떤 field를 추가했는가?

SubmissionRuntimeRequest에 optional semantic_payload, semantic_observed_at, semantic_feature_version을 추가했다. Payload는 10개 후보 개념을 표현할 수 있지만 현재 학습 whitelist는 2개다. Policy Arrival에는 raw 문자열 대신 NumericSemanticFeatures만 추가했고, 별도 adapter가 제출 경계에서 변환한다.

## 8. 미래정보가 들어가는 field는 없는가?

새 adapter는 허용한 두 필드만 투영한다. runtime/start/end/final state/future queue의 교란은 새 semantic 특징을 바꾸지 않는다. Logical event-time 검증이며 archive ingestion latency나 mutable request의 최초 버전까지 인증한 것은 아니다.

## 9. SEM_COOCCUR32는 어떻게 생성되는가?

NFC·바깥 공백 정리 → field/namespace별 SHA256 pseudonym → 정렬·중복 제거한 field-prefixed token → FeatureHasher(262144,string,alternate_sign=False) → TRAIN-only TruncatedSVD(32,seed1401) → float32 sem_00..31이다. Linguistic embedding이 아니다.

## 10. 왜 anonymized ID의 숫자 크기를 사용하지 않는가?

익명화 ID의 숫자는 의미나 순서를 보증하지 않는다. 전체 값을 하나의 범주로 처리하고 숫자 magnitude·ID 문자 ngram·인접 ID 유사도를 사용하지 않는다.

## 11. SVD는 TRAIN only인가?

예. Runtime은 각 기존 fold TRAIN에서만 SVD를 fit했다. CC4는 최초 DEVELOPMENT issue 전의 기존 TRAIN 날짜에 제출된 작업으로 한 번 fit하고 이후 transform-only다.

## 12. recurrence feature도 TRAIN only인가?

예. user/submit_line 각각과 user-submit_line 조합의 TRAIN count/log1p/seen만 사용한다. VALID 빈도나 runtime target encoding은 없다.

## 13. historical row와 replay event의 semantic vector가 동일한가?

예. 5개 fold 각각에서 64개 행의 저장 후 로드·shuffled transform, 그중 8개 행의 direct·record 변환을 bitwise 확인했다. 전체 행이 같은 transformer 코드를 사용하지만 전수 replay 검사를 했다고 주장하지 않는다. 별도 fresh process에서도 미래 입력 변환을 검사했다.

## 14. unseen future job도 transform 가능한가?

예. 알려진 범주, 새 user/command, 결측 optional, 새 account, Unicode 입력 5사례 × R1/R2 10개에서 finite 특징·Q50/Q90을 얻었다. 새 account는 현재 whitelist에서 제외되므로 수용하되 특징에는 사용하지 않는다. 이것은 연구 모델 호출성이고 운영 승인과 별개다.

## 15. raw semantic 문자열이 optimizer에 전달되는가?

전달하지 않는다. Runtime request 경계의 payload만 원문을 일시 처리하고 policy Arrival은 숫자 타입만 허용한다. 기본 repr도 원문을 가린다.

## 16. privacy boundary는 무엇인가?

저장은 pseudonym 빈도·numeric vector·feature version·bundle digest로 제한한다. 미래 실제 값은 archive hash와 자동 정렬되지 않으므로 별도 namespace의 unseen으로 처리한다. SHA256은 작은 후보 공간의 역추측 방지까지 보장하지 않는다.

## 17. R0 baseline은 정확히 재현됐는가?

정확한 V13 EXPANDING_S4 저장 예측과 해시를 재사용하고 pooled 주요 지표를 독립 재계산했다. R0 재학습은 0회다. pooled Q90 91.84%, min-fold 70.70%, >4h 69.72%, >12h 64.25%, >24h 46.88%, Q90 pinball 4752.7617, reservation/actual 3.3921, W0 대비 0.6599.

## 18. R1 결과는?

pooled Q90 91.77%, min-fold 66.11%, >4h 67.11%, >12h 60.12%, >24h 51.65%, Q90 pinball 4852.5745, reservation/actual 3.5360, W0 대비 0.6878.

## 19. R2 결과는?

pooled Q90 91.50%, min-fold 66.75%, >4h 66.87%, >12h 58.98%, >24h 45.81%, Q90 pinball 4720.1813, reservation/actual 3.4665, W0 대비 0.6743.

## 20. R3은 실행됐는가?

실행하지 않았다. 실제 free text가 없어 NOT_APPLICABLE이며 대형 LLM 다운로드는 0이다.

## 21. Runtime pooled Q90은?

R0: 91.84% / R1: 91.77% / R2: 91.50%

## 22. Runtime min-fold는?

R0: 70.70% / R1: 66.11% / R2: 66.75%; 고정 하한은 85%다.

## 23. >4h/>12h/>24h는?

R0: >4h 69.72%, >12h 64.25%, >24h 46.88% / R1: >4h 67.11%, >12h 60.12%, >24h 51.65% / R2: >4h 66.87%, >12h 58.98%, >24h 45.81%

## 24. pinball은?

R0: Q90 pinball 4752.7617, proper interval NLL 8.0716 / R1: Q90 pinball 4852.5745, proper interval NLL 7.9549 / R2: Q90 pinball 4720.1813, proper interval NLL 7.9408; V13의 동일 1초 event-interval likelihood와 censor score다.

## 25. reservation ratio는?

R0: actual 대비 3.3921, W0 대비 0.6599 / R1: actual 대비 3.5360, W0 대비 0.6878 / R2: actual 대비 3.4665, W0 대비 0.6743; short-job inflation과 Q90/runtime median/P90도 별도 CSV에 보존했다.

## 26. 어떤 semantic family가 Runtime을 개선했는가?

R1−R0: min-fold -4.59pp, >4h -2.60pp, pinball +2.10%; R2−R0: min-fold -3.95pp, >4h -2.84pp, pinball -0.69%. R2−R1: pinball -2.73%, min-fold +0.64pp. 이는 predictive contribution 비교이며 causal effect가 아니다.

## 27. improvement가 temporal fold 전반에서 유지되는가?

Fold별 결과를 모두 유지했다. 선택은 NONE; 첫 fold를 포함한 전체 safety gate를 만족하지 않으면 pooled 개선으로 대체하지 않았다.

## 28. CC4에서 미래 job semantic을 직접 사용했는가? 반드시 NO.

NO. CC4는 미제출 미래 작업의 개별 semantic을 사용하지 않는다. issue와 같은 시각의 제출도 제외한다.

## 29. CC4 semantic state는 어떤 과거 window를 사용하는가?

1h/6h/24h/72h 과거 제출의 32D centroid·count·dispersion·recurrence와 두 centroid L2 변화를 사용한다. C2는 1h/6h/24h K=8 count/fraction/entropy 및 composition change를 추가한다. 미승인 account/script-family 비율은 만들지 않았다.

## 30. future perturbation test를 통과했는가?

예. Synthetic poisoned future payload와 실제 12개 무작위 issue-time의 미래 vector/recurrence/cluster 교란에서 특징이 같았다. 한 과거 작업의 user를 바꾸는 positive control도 확인했다. 별도 12개 issue에서는 저장 cluster 중심과 future-facing record 경로로 재구성한 201개 특징이 historical 상태와 bitwise 일치했다. 빈 window가 있으면 해당 지원 범위를 명시한다.

## 31. C0 baseline은?

사용자 지정 기존 T0/B0다. 타깃은 제출 시간대에 귀속한 요청 GPU 수 × 실제 runtime GPUh이며 24개 hourly 출력, 71개 기본 특징, 동결 LightGBM·일별 expanding refit·30일 가중치를 유지한다. EXPOSED_EVALUATION: calibrated hourly Q90 91.19%, daily requirement coverage 95.45%, pinball 226.3494, requirement ratio 3.2482, burst 30.30%, WAPE 0.9382; raw hourly Q90 86.03%. OOS_EXTENSION: calibrated hourly Q90 84.34%, daily requirement coverage 96.55%, pinball 234.5920, requirement ratio 2.5717, burst 29.21%, WAPE 0.9347; raw hourly Q90 76.58%.

## 32. C1 결과는?

EXPOSED_EVALUATION: calibrated hourly Q90 90.96%, daily requirement coverage 95.45%, pinball 227.9132, requirement ratio 3.2652, burst 31.82%, WAPE 0.9395; raw hourly Q90 86.41%. OOS_EXTENSION: calibrated hourly Q90 83.62%, daily requirement coverage 96.55%, pinball 236.0522, requirement ratio 2.5525, burst 26.97%, WAPE 0.9364; raw hourly Q90 75.14%.

## 33. C2 결과는?

EXPOSED_EVALUATION: calibrated hourly Q90 90.72%, daily requirement coverage 95.45%, pinball 225.8968, requirement ratio 3.2270, burst 31.82%, WAPE 0.9377; raw hourly Q90 86.27%. OOS_EXTENSION: calibrated hourly Q90 83.91%, daily requirement coverage 96.55%, pinball 234.5266, requirement ratio 2.5063, burst 29.21%, WAPE 0.9366; raw hourly Q90 75.14%.

## 34. hourly Q90 coverage는?

각 arm의 raw/calibrated hourly Q90은 CC4_MODEL_COMPARISON.csv에 DEV/CAL/EXPOSED/OOS_EXTENSION으로 분리했다. EXPOSED_EVALUATION: calibrated hourly Q90 91.19%, daily requirement coverage 95.45%, pinball 226.3494, requirement ratio 3.2482, burst 30.30%, WAPE 0.9382; raw hourly Q90 86.03%. OOS_EXTENSION: calibrated hourly Q90 84.34%, daily requirement coverage 96.55%, pinball 234.5920, requirement ratio 2.5717, burst 29.21%, WAPE 0.9347; raw hourly Q90 76.58%.

## 35. daily Q90 coverage는?

Daily coverage는 24개 marginal hourly Q90 requirement 합의 coverage다. 이것을 별도로 적합한 joint daily 90% quantile이라고 부르지 않는다. 수치는 각 arm/period CSV에 있다.

## 36. requirement ratio는?

C0/C1/C2의 requirement/actual 비율을 raw와 calibrated 양쪽에서 비교했다. EXPOSED_EVALUATION: calibrated hourly Q90 91.19%, daily requirement coverage 95.45%, pinball 226.3494, requirement ratio 3.2482, burst 30.30%, WAPE 0.9382; raw hourly Q90 86.03%. OOS_EXTENSION: calibrated hourly Q90 84.34%, daily requirement coverage 96.55%, pinball 234.5920, requirement ratio 2.5717, burst 29.21%, WAPE 0.9347; raw hourly Q90 76.58%.

## 37. burst coverage는?

기존 TRAIN positive target Q95=860.353222 GPUh를 사용했다. Validation으로 threshold를 고르지 않았고 각 arm/기간의 burst N과 coverage를 보존했다.

## 38. semantic feature가 coverage만 올리고 reserve를 과다하게 만들지는 않았는가?

Coverage 단독으로 선택하지 않았다. 고정 기준은 raw pinball paired CI, WAPE, raw/calibrated requirement 비율, calibrated nominal band 및 burst coverage를 함께 요구한다. 실패한 조건 전체는 CC4_SELECTION_FREEZE.json에 있다.

## 39. Runtime semantic model이 선택됐는가?

False. SELECTED_RUNTIME_ARM=NONE. 안전 gate 실패 arm을 provider로 승격하지 않았다.

## 40. CC4 semantic model이 선택됐는가?

False. SELECTED_CC4_ARM=C0. DEVELOPMENT에서 후보를 고정한 뒤 독립 gate를 적용했고 평가 결과로 차선 arm을 다시 고르지 않았다.

## 41. V42에서 실제 어떤 시점에 semantic 정보가 사용되는가?

구현 경계는 D-1의 관측된 과거 semantic state와 D-day 실제 SUBMIT payload다. 기본 flag는 FALSE이며 운영 policy에 새 semantic 모델을 활성화하거나 optimizer를 실행하지 않았다.

## 42. D-1 unknown job의 semantic을 미리 읽는가? 반드시 NO.

NO. D-1에는 submit_time < issue_time인 작업만 쓴다. 미제출 작업의 payload를 읽지 않는다.

## 43. D-day 도착 시 semantic을 사용할 수 있는가?

제출 시점 receipt가 있는 payload는 도착 handler에서 변환할 수 있다. 단, 모델의 실제 사용은 별도 선택·검증 gate를 통과해야 한다.

## 44. RUNNING job은 어떤 semantic state를 유지하는가?

제출 때 동결한 NumericSemanticFeatures와 bundle/version을 유지한다. End/runtime outcome으로 재계산하지 않으며 duplicate submit의 덮어쓰기를 거부한다.

## 45. online refit이 필요한가?

Semantic inference에는 refit이 없다. CC4의 기존 offline daily expanding 학습 cadence와 actual-arrival handler의 online refit은 다르다. 실제 도착 handler는 저장된 transformer만 사용한다.

## 46. private RADDiT exporter가 필요한가? 반드시 NO.

NO. PRIVATE_RADDIT_EXPORT_REQUIRED=FALSE. 추가 비공개 provenance 검색을 하지 않았다.

## 47. private encrypted vector가 필요한가? 반드시 NO.

NO. RADDIT_DISTRIBUTED_VECTOR_USED_FOR_V42=FALSE 및 PRIVATE_RADDIT_VECTOR_TRANSFORM_REQUIRED=FALSE다.

## 48. April을 selection에 썼는가? 반드시 NO.

NO. 모델 선택은 기존 pre-April 역할만 사용했다. CC4의 March26/27/28/31은 label이 April에 성숙하므로 동일 기준으로 양쪽 평가에서 제외했다. April target-day 배열이나 평가를 열지 않았다.

## 49. May를 열었는가? 반드시 NO.

NO. 원본 May archive member 및 CC4 May array rows를 디코딩하지 않았다. 전체 파일의 byte hash 검증과 payload row 해석을 구분했다.

## 50. 최종적으로 V42에 어떤 semantic 기능이 실제 활성화됐는가?

실제 완료된 기능은 backward-compatible payload/receipt, 공통 adapter, numeric arrival/cache, causal CC4 state 입력과 validation gate다. 기본 실행은 legacy이며 V42_RUNTIME_USES_SEMANTICS=FALSE, V42_CC4_USES_SEMANTICS=FALSE다. 연구 결과·호출 가능성·운영 활성화를 구분한다.
