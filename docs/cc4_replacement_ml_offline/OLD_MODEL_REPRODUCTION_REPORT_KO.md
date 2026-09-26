# 기존 CC4 재현 결과

검증 PASS. 지정 GitHub PR #42/#33/#34 및 네 고정 commit을 GitHub API로 확인했다. PR은 배경 참조이며 수정하지 않았다. 고정 commit의 파일은 로컬 Git object에서 독립 경로로 추출했다. GitHub source와 로컬 production source 7개 파일의 SHA 비교는 SOURCE_AND_MODEL_LINEAGE.json에 저장했다.

원본 CC4는 R6 L0 H4 LightGBM Q50/Q90이다. log1p(target_GPUh), num_leaves=15, learning_rate=0.03, n_estimators=400, min_child_samples=50, seed=20260907, CPU threads=1. H4 81 window/day × 167일 = 13,527 학습 row이며 random window split이 없다. 원본 feature ordering 71개는 history/B/.../V40R6_FEATURE_CONTRACT.json에서 읽어 byte hash를 연결했다. 과거 제출 수, 성숙한 GPUh/mask/age의 6시간·24시간·7일 요약, 마지막 상태, deterministic calendar/lead, 7/14/21/28일 15분 계절 특징과 H4 누적 계절합이다. GPU 요청·runtime의 미래 실현값은 predictor에 들어가지 않는다.

| role | calendar_start | calendar_end | eligible_start | eligible_end | N_eligible | excluded_days |
| --- | --- | --- | --- | --- | --- | --- |
| CALIBRATION | 2024-11-01 | 2024-11-29 | 2024-11-01 | 2024-11-27 | 26 | 2024-11-26;2024-11-28;2024-11-29 |
| DEVELOPMENT | 2024-09-01 | 2024-10-30 | 2024-09-01 | 2024-10-29 | 58 | 2024-10-28;2024-10-30 |
| EXPOSED_EVALUATION | 2024-12-01 | 2025-02-26 | 2024-12-01 | 2025-02-26 | 88 | nan |
| PURGE | 2024-08-31 | 2024-11-30 | nan | nan | 0 | 2024-08-31;2024-10-31;2024-11-30 |
| TRAIN | 2024-03-15 | 2024-08-30 | 2024-03-15 | 2024-08-28 | 167 | 2024-08-29;2024-08-30 |

범위 표기와 실제 적격 membership가 다르다. 예를 들어 TRAIN 8월 29/30일은 미성숙으로 제외되므로 마지막 적격일은 8월 28일이다. 개발/보정도 날짜 문자열로 생성하지 않고 원본 maturity ledger와 R6 fit receipt를 사용했다. R6의 CAL_FIT/CAL_SELECT는 calendar 순서 반분 후 기존 적격 마스크를 유지하는 offline 분할이고, R6R1/V41의 expanding rolling calibration과 별개다. 원본 계약은 history/B/.../V40R6_CAL_SUBSPLIT_CONTRACT.json 및 history/C에 보존했다.

target은 submit window에 들어온 양수 GPU 수량 authority와 유효 관측 start/end가 있는 작업의 전체 lifetime GPU·h 합계다. 전력, 동시 GPU 점유, 확보된 여유용량, 해당 window 내 완료 의무량이 아니다. raw archive 모든 partition을 검사해 349일 원본 15분 target을 재생성했고 원본 H1/H4/H8 feature matrix는 정확히 일치했다. May 원본 평가 target와의 최대 오차는 7.28e-12 GPU·h다. 12 synthetic AIDC를 독립 학습시계열로 복제하지 않았다.

모델 SHA256:
- Q50: 93337fe2d78aa03ee5554cbd7d1ddf5af3703db6d608edd58d795406edeb6f51
- Q90: 62c9aad38458f0f20127e4220c18ea82876241e07001ad5f66bfbf4f3379a0dc

두 모델은 GitHub B의 model bytes, 로컬 frozen model 및 May 31개 snapshot의 H4_model_authority에 모두 연결된다. 원본 H4_AUTHORITY 파일의 추가 탐색 결과는 AUTHORITY_SEARCH.json에 별도로 기록한다. snapshot 내 authority와 실제 model bytes를 우선 실행 증거로 사용했다.

고정 base trees로 chronological OOS 예측을 재생성한 뒤 max(target_day_end,target_label_available_at) < issue인 잔차만 모아 log1p one-sided 85% finite-sample order statistic을 재계산했다. 31일의 membership hash도 원본과 모두 일치했다. 기존 exposed Q50/Q90 최대 오차 0; May base Q90 최대 오차 0; May uncapped 최대 오차 0 GPU·h. 상세 수치는 FROZEN_REPRODUCTION.json.

F0의 Dec–Feb 85% 수치는 이번에 동일 frozen model로 원인과적 재계산한 역사 reference이며 과거 R6의 offline 90% CAL_FIT 판정 수치를 대체하지 않는다. May F0는 실제 frozen 85% snapshot을 재현한다. historical 99% cap과 physical cap을 구분하며 May physical oracle coverage 85.9418558343%를 확인했다.

기존 NONE/FAIL/NO_MODEL_PROMOTED는 그대로 유지한다. 새 모델을 production에 연결하지 않았다.
