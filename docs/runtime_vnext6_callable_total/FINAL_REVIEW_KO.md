# Runtime-vNext6 최종 검토

**결론: 작업은 완료했지만 운영 승격은 거절한다. 원본 요청 버전 authority가 없으며, 이를 제외한 무피처 총 실행시간 기준선은 성능·대기열 게이트를 통과하지 못했다.**

요청한 엄격 피처 원칙을 적용했다. 불변 작업별 피처가 0개이므로 callable 연구 패키지를 성공적인 production predictor로 포장하지 않는다. 새 원본 로그가 확보되기 전에는 full-feature comparator를 운영으로 승격할 수 없다.

## 동결·표본·권한

- 논리적 학습 cutoff: 2025-03-14 08Z, 논리적 번들 as-of: 2025-03-31 08Z. 실제 파일 생성은 2026년 9월의 소급 실험이다.
- TRAIN 222,182건(0초 111건), DEV 11,486 성숙/495 미성숙, CAL_FIT 5,438/498, CAL_VALID 14,623/13. September2024 이후 공개 partition 중 지정 end-window에 해당하는 표본이다.
- April 51,499건 중 pre-May 성숙·유효 라벨 49,712건, 미해결/부적격 1,787건. May partition과 May 완료 라벨은 사용하지 않았다. 완료는 end/start가 있는 종료 기록이며 성공 상태 COMPLETED만을 의미하지 않는다.
- 피처: constant_bias=1만 사용. 9개 요청 피처와 재큐잉에 민감한 submit hour/weekday 제외. 원본 요청 미검증 GPU는 연구 표본·가중치·strata에만 사용한다.
- `SUBMISSION_TIME_FEATURES_STRICTLY_VERIFIED=TRUE`는 상수 입력만의 성질이다. `REQUEST_VERSION_AUTHORITY_FOUND=FALSE`, `STRICT_CAUSAL_RUNTIME_PROVIDER_READY=FALSE`다.
- 선택·보정 동결 → 동일 TRAIN 최종 refit → standalone 호출/무학습/무캐시 검증 → 번들 hash 동결 → April 개방 순서를 보존했다. 모델은 April 이후 변경하지 않았다.

## 필수 질문 21개

### 1. walltime을 scheduling duration으로 쓰면 무엇이 문제인가?

실행시간과 다른 최대 요청값이다. April 예약/실제 GPUh는 4.302배, April2 늦은 코호트 요청/실제 중앙값은 10.217배였다. 이것만으로 ML 대체의 타당성이 증명되지는 않는다.

### 2. 기존 기준 모델을 재현했는가?

예. 2025-03-14 08Z의 PENDING 총 실행시간 Q50/Q90와 저장 전처리를 로드하여 275행을 오차 0으로 재현했다. 원본 요청 버전 미검증으로 연구 comparator만 허용한다.

### 3. 어떤 총 실행시간 모델을 선택했는가?

M2 log1p LightGBM 상수 입력 기준선을 연구 후보로 선택했다. M1과 pinball 차이는 0.000152초 수준의 수치적 차이이며 실질적인 우월성 주장은 없다. M3는 walltime 역변환이 미검증 요청값을 요구하므로 제외했다. 운영 모델은 선택·승격하지 못했다.

### 4. Q50/Q90의 의미는?

한 패키지의 무조건부 총 실행시간 분위수다. 최종 Q50=115.000초, Q90=55987초(약 15.55시간). Q90 전역 보정값 -313.989초. 작업별 조건부 Q90라는 주장을 하지 않는다.

### 5. Q90이 보정됐는가?

아니오. DEV 원시 coverage 91.41%지만 독립 CAL_VALID 99.22%, April 95.67%로 88–92% 게이트를 벗어났다. CAL_FIT 90.03%는 같은 표본의 보정 결과이므로 검증 통과로 쓰지 않는다.

### 6. high-GPU 보정은?

승인 불가. DEV 89건, CAL_VALID 6건으로 최소 100건 미달. April ≥16GPU 298건의 coverage 94.63%도 잠금 후 기술통계이며 사전 실패를 고칠 수 없다.

### 7. 4시간 초과 작업 보정은?

실패. DEV 원시 61.74%, CAL_VALID 63.46%, April 77.66%; April GPU 가중 coverage 70.09%.

### 8. 예약 과잉은 얼마나 남았는가?

April 예약/실제 GPUh 4.136배. 총 초 단위 예측/실제 비율 4.911배. 0초 50건은 개별 비율에서 제외하고 총량에서는 유지했다.

### 9. walltime보다 얼마나 작아졌는가?

April 전체 예약 GPUh 감소는 3.85%뿐으로 요구한 20% 이상 감소에 미달. April2 신규 코호트의 슬롯 예약은 22.20% 감소했지만 당일 시작은 악화됐다.

### 10. 실행시간을 얼마나 자주 과소예측하는가?

April 작업 기준 4.33%. 빈도는 낮아도 긴 overrun의 손실이 크므로 이를 단독 성공 지표로 보지 않는다.

### 11. GPU 가중 overrun은?

April GPU 요청수 가중 작업 비율 5.38%, 초과 실행 129,605.9 GPUh. checkpoint 가중 비율은 별도 분모로 42.28%.

### 12. 30분 체크포인트에서 단순 차감이 충분한가?

아니오. 299,805개 checkpoint의 remaining MAE 17.66시간, >15/>30/>60분 분류 정확도 66.66%/64.02%/59.65%. 사전 게이트 실패.

### 13. OVERRUN에 얼마나 들어가는가?

작업 단위 4.33%, 관측 체크포인트 단위 28.93%. 체크포인트는 30분 이상 생존 작업 중심의 다른 모집단이다. OVERRUN 시 GPU 유지·STAY·매 제어 간격 예약 연장 테스트는 통과했다.

### 14. 별도 remaining 모델이 필요한가?

INCONCLUSIVE. 실패한 무피처 TOTAL 모델의 차감 실패가 별도 시스템의 필수성을 입증하지 않는다. 먼저 원본 요청 권한과 유용한 TOTAL 예측 문제를 해결해야 한다.

### 15. survival/AFT 개발을 피했는가?

예. 별도 remaining, survival, AFT, 신경망 모델을 학습하지 않았다.

### 16. 완전히 새 작업에 호출 가능한가?

예, 연구 모드에서. 별도 폴더·새 프로세스·빈 요청 피처·새 ID로 예측했다. 과거 행의 ID를 제거해도 같고 예측 lookup 캐시는 없다. 모든 작업이 같은 예측을 받는 것이 이 엄격 기준선의 한계다.

### 17. 온라인 재학습이 필요한가?

아니오. 모델 선택/보정 동결 후 TRAIN 동일 표본으로 Q50/Q90 각각 한 번 최종 fit하고 저장했다. 로더와 predict에는 학습 경로가 없다. Q50/Q90 두 booster는 한 Runtime 패키지다.

### 18. CPU/GPU 어느 쪽이 빨랐는가?

동일 5만 행·4개 fit 작업에서 CPU 단일 0.351초, CPU4 2.147초, GPU 4.382초. 예측·지표 차이 0. CPU_SINGLE 선택. 상수 입력에는 유효 분할이 없어 프로세스 시작 비용이 지배적이며 일반적인 full-feature 모델 결과로 일반화하지 않는다.

### 19. CPU 추론 지연은?

1,000회 API 호출 P50 0.0474ms, P95 0.0649ms, P99 0.1097ms, 최대 0.2433ms. 배치10/100/1000 처리량은 INFERENCE_LATENCY.json 참조. GPU 불필요.

### 20. April start≥H가 얼마나 바뀌었는가?

정확 재현 W0 2,190/2,340 (93.59%) → 동결 Q90 2,340/2,340 (100%). 회복 0건, 당일 시작 150건 상실. 평균 대기시간은 77.83→64.35시간으로 줄어도 H 안의 시작은 악화된다. 기존 332건 배경 예약은 고정한 신규 도착 작업 개입이다.

### 21. V42로 넘길 준비가 됐는가?

아니오. callable/persisted 기술적 부분은 해결했지만 authorized/validated 모델이라는 핵심은 미해결이다. 기본 로더는 PermissionError로 차단하며 연구 모드만 명시적으로 허용한다. V42·CC4·MESS·IEEE/OpenDSS 및 optimizer를 수정하거나 실행하지 않았다.

## 해석과 한계

`Q90(T|x)-elapsed`는 제출 시점 고정 잔여 proxy이며 `Q90(T-elapsed | T>elapsed,x)`와 다르다. 본 상수 모델은 x에 작업 정보를 갖지 않는다. 30분 checkpoint 결과도 May1 전에 종료된 작업의 생존 checkpoint에 한정되며, 긴 우측 검열 작업의 성능을 보증하지 않는다.

요청 walltime cap을 primary에 적용하지 않았다. 사후 연구 진단은 WALLTIME_CAP_DIAGNOSTIC.csv에 보존했다. 초기 strata의 최상위 requested bin은 >=4h이며 사용자 지정 >4h 경계를 정확히 따르는 보완표는 EXACT_REQUESTED_BUCKET_METRICS.csv에 있다. 실제 실행 >4h 게이트는 처음부터 엄격한 >4h다.

기본 reservation replay는 미래 실행 라벨을 읽기 전에 저장했다. 별도의 실행 스트레스 재생은 매 15분 완료 여부만 scheduler에 전달한다. OVERRUN에는 GPU를 유지했으며 W0/ML 각각 209/3,597회 연장, 두 경우 용량 위반 0이었다. 이 현재-slot dispatch 진단은 정확한 V42 controller 재생이 아니며, 예약 재생의 start≥H 비교와 섞지 않는다. 실제-duration 반사실 가정도 새로운 시스템에서 관측된 사실이 아니다.

기존 연구 파일 해시를 보존했다. 중간 Windows 한글 경로 로딩 오류는 Python 문자열 로딩으로 동결 전에 수정했고 실패 로그를 남겼다. 모델·데이터 결과를 수정하거나 실패 게이트를 낮추지 않았다.

## 산출물

- `RUNTIME_PROVIDER/`: Q50/Q90, 전처리·계약·해시·예제. 연구용 호출은 `RuntimeProvider(allow_research=True)`.
- `REQUEST_VERSION_AUTHORITY_AUDIT_KO.md`: 필드별 원본성·수정·수집 근거.
- `MODEL_SELECTION_FREEZE.json`, `PROVIDER_BUNDLE_FREEZE.json`: 선택과 모델 bytes 동결.
- `MODEL_COMPARISON.csv`, `STRATIFIED_METRICS.csv`, `GPU_WEIGHTED_METRICS.csv`, `PAIRED_UNCERTAINTY.csv`: pre-April 비교.
- `APRIL_LOCKED_RUNTIME_METRICS.csv`, `APRIL_WALLTIME_VS_ML_QUEUE_REPLAY.csv`, `CHECKPOINT_SUBTRACTION_DIAGNOSTIC.csv`: 잠금 평가.
- `FINAL_VERDICT.json`, `DELIVERY_MANIFEST.json`: 최종 flag와 배달 검증.
