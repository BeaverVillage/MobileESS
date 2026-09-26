# 실행·감사 기록

모델 선택과 평가의 순서는 `PROTOCOL.json`, `CODE_FREEZE.json`, `STAGE_A_FREEZE.json`, `FINAL_SELECTION_FREEZE.json` 및 실행 로그의 시각으로 확인한다. 이전 frozen 자료는 읽기 전용 authority로 사용했다.

## 기준선 재현

과거 MoE의 첫 재현은 다른 NumPy/scikit-learn 환경 및 pandas record 변환에서 저장된 예측과 일치하지 않았다. 해당 결과는 기준선으로 채택하지 않았다. 당시 라이브러리 버전을 독립 환경에 설치하고 Arrow `to_pylist()`의 null·정수 자료형을 보존한 재현은 245개 예측과 adapter 비교에서 오차 0을 확인했다. 최신 LightGBM도 저장된 전처리의 원래 feature 순서로 May 31일분을 정확히 재생했다. 전처리 JSON의 정렬된 key 순서는 모델 feature 순서가 아니다.

`PRODUCTION_COHORT_BRIDGE.json`은 추가적인 읽기 전용 감사다. May 31개 issue 모두에서 raw 자료로 재구성한 최신 production 학습 membership의 개수와 SHA-256이 frozen snapshot과 정확히 일치했다. 공통 연구 cohort의 expanding membership도 같다. 과거 전체 Job MoE와 positive-GPU 연구 cohort 사이의 모집단 차이는 여전히 남는다. 이 감사는 예측 성능이나 모델 선택을 계산하지 않는다.

최종 선택 freeze 전에 추가한 대표 issue 재학습도 통과했다. 2025-05-01 예측용 cutoff는 2025-04-30 08:00 UTC이고 마지막 training Job 종료는 07:52:26 UTC다. 667,375개 완료 Job으로 재학습한 최신 production Q90은 모든 tree 및 model text 해시가 원본과 같았고 Pending 1,395개 예측의 최대 차이는 0이었다. 이 검증은 May label을 점수화하거나 선택에 사용하지 않는다.

## 평가 전 코드 수정

`CODE_AMENDMENT_CHAIN.json`과 단계별 사본, 각 `*_sources/`는 수정 전 bytes를 보존한다. feature-control 수정은 공통 MoE 입력과 학습된 OHE/SVD 표현을 두 새 architecture에 동일하게 적용한다. process lock은 같은 issue의 중복 writer를 막는다. 기존 PR31 Q90 reference에 새 모델의 Q50/Q95/Q99가 상속되지 않도록 비권위 필드를 비웠다. major subgroup 정의, bootstrap의 관측 issue-day 경계, matched population의 unmatched 개수도 평가 전에 고정했다.

LightGBM의 1-thread와 4-thread 비교는 모든 tree, 전체 causal training 예측 및 target-free query 예측의 완전 일치로 검증했다. 성능 평가값을 사용한 계산 설정 선택이 아니다. 기존 production 재현과 공통 cohort 연구의 실행 환경을 구분해서 기록한다.

최종 freeze 뒤 CC4 작업이 끝나면서 남은 CPU 용량을 확인하고, 동일 frozen worker를 하나 더 실행했다. 21개 frozen source 및 protocol/temporal 설정은 변경하지 않았다. 추가 helper는 이 해시들을 검증한 후 독립 issue fit만 수행하고, 선택·scoring·calibration에는 관여하지 않는다. 계산 배치 변경의 근거와 시각은 `RESOURCE_SCHEDULING_RECEIPT.json`에 있다.

## 범위

request 수정 이력·실제 feature ingestion 시각은 인증되지 않았다. historical event-time proxy에 대한 offline 결과이며 production promotion의 근거로 사용하지 않는다. exact training/calibration membership, source digest, 두 기준선 재현, seed/recipe와 checkpoint digest를 저장한다. 모델 binary는 로컬에 보존하고 대량 중복 checkpoint를 Git에 넣지 않는다.

optimizer, MESS, IEEE123/8500, Actual/OpenDSS는 실행하거나 수정하지 않았다.
