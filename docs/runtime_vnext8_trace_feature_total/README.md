# Runtime-vNext8 연구 결과

`FINAL_REVIEW_KO.md`와 `FINAL_VERDICT.json`을 먼저 읽는다. 검증된 운영/연구 승격 모델은 없다. RUNTIME_PROVIDER는 frozen 진단 후보이며 기본 로더는 연구 opt-in을 요구한다.

재현은 Python3.11, numpy1.26.4, pandas2.2.3, LightGBM4.6.0, pyarrow18.1.0 기준이다. baseline import용 tqdm4.67.1이 필요하다. SOURCE_MANIFEST의 정확한 원자료/이전 frozen 경로를 준비하고 **빈 독립 output 디렉터리**에서 register8→prepare8→baseline8→train8→benchmark_selected8→freeze_provider8 순서로 실행한다. 이전 결과를 덮어쓰지 않는다. `common8.py`의 경로를 새 환경에 맞춘다. 이미 동결된 결과에서 새 fit을 실행하지 않는다.

세 freeze 후 evaluate_april8는 raw April을1회만 읽는다. 이후 queue_replay8, report8, verify8, delivery8을 실행한다. 기존 산출물 검증에는 verify8만 사용한다. May는 필요 없다. provider folder를 Python module path에 두고 `RuntimeProvider(bundle_path,allow_research=True).predict_total(job_record,event_time=None)`를 호출한다. 입력은 feature_contract와 preprocessing의 normalized request keys를 따른다. 학습·baseline 코드 없이 CPU inference가 가능하다.

feature_count29는 engineered/indicator/encoded 열의 수다. total-runtime subtraction은 조건부 survival quantile이 아니다. 원본 요청 authority FALSE, 직렬화 PASS, predictive validation FAIL을 구분한다.
