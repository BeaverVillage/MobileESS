# Runtime-vNext9 provider 사용

이 bundle은 Kestrel_trace_proxy 연구용이다. 학습과 호출이 가능하다는 사실은 안전성 gate 통과 또는 strict submission-time authority 확보를 뜻하지 않는다. FINAL_VERDICT.json을 먼저 확인한다.

Python3.11, NumPy1.26.4, pandas2.2.3, LightGBM4.6.0, XGBoost3.0.5, SciPy 환경에서 검증한다. CPU 추론만으로 동작한다. RUNTIME_PROVIDER 디렉터리를 Python import path에 넣고 provider.RuntimeProvider(bundle_path, allow_research=True)를 생성한다. BUNDLE_INTEGRITY.json의 파일 hash를 초기화 때 검증한다.

- predict_total(job_record, event_time=None): q50_total_seconds, q90_total_seconds, distribution_metadata, model_version, feature_contract_version, provenance_mode를 반환한다.
- predict_remaining(job_record, elapsed_seconds, event_time=None): 같은 total distribution의 조건부 q50/q90_remaining_seconds, survival_probability, log_survival_probability, model_version을 반환한다.
- predict_batch(records, event_time=None): CPU의 N×2 total Q50/Q90 배열을 반환한다.
- running_action(...): 관측상 RUNNING이면 GPU를 유지한다. 계획 초과는 STAY, 강제 종료 없이 한 control interval900초를 연장하며 conditional_remaining도 반환한다.
- observe_completed(job_record, runtime_seconds, completion_time): 외부 완료 관측자가 전달한 결과로 보정 residual 상태만 갱신한다. base booster를 학습하지 않는다. submit_time이 필요하고 TRAIN 이전 제출 및 역순 완료는 거부한다. 호출자는 실제 완료 이벤트를 중복 전달하지 않아야 한다.

입력은 num_gpus_req, num_nodes_req, num_cores_req, requested_memory_mib, requested_seconds, array_index, qos, partition, account다. job_id는 무시한다. 모르는 category는 UNKNOWN0이다. 누락/비정상 수치는 고정 missing flag와 NaN 경로를 사용한다. state/start/end/runtime 같은 outcome key를 predict API에 넣으면 거부한다. event_time과 submit_time은 시간 검증용이며 모델 feature가 아니다.

예시 신규 record: job_id="never-seen", num_gpus_req=4, num_nodes_req=1, num_cores_req=32, requested_memory_mib=262144, requested_seconds=14400, array_index=None, qos="normal", partition="gpu", account="unseen-account". predict_total(record, event_time="2025-04-02T00:00:00Z"), RUNNING 관측 후 predict_remaining(record, elapsed_seconds=3600, event_time="2025-04-02T01:00:00Z")로 호출한다. 실제 반환값은 선택 모델에 의존한다.

보정이 NONE이면 관측 residual은 예측에 영향을 주지 않는다. STATIC14이면 동결 scalar shift를 사용한다. ROLLING14/28이면 end<예측 UTC day인 residual만 사용한다. event_time 생략 시 모델 availability cutoff를 사용하므로 rolling 호출자는 event_time을 명시한다. 모델의 availability 이전 예측 요청은 거부한다. 잔여시간 API에는 그 시점 실제 RUNNING이라는 외부 관측이 전제된다.

분포는 Tcal=max(0,Tbase+delta)이며 walltime 기본 cap은 없다. 생존확률이 부동소수점에서0으로 underflow해도 log survival로 조건부 분위수를 계산한다. 이는 별도 remaining 모델이 아니다. 실측 remaining coverage 검증 결과는 CONDITIONAL_REMAINING_DIAGNOSTIC.csv와 FINAL_VERDICT.json에 있다.

May payload는 열지 않았다. April은 이미 노출된 regression 자료다. 이 디렉터리의 제공으로 V42 kernel이나 배포 provider를 교체하지 않는다.
