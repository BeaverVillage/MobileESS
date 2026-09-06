# V41 운영 인터페이스 선택

Rolling Q90 Track-P L2와 H4 R85_B2를 사용하고 H24는 OFF로 고정한다. 기존 S5R1/R6R1 FAIL은 유지한다.

GPUh 부족 벌점 계수가 없다는 최초 감사는 보존한다. 사용자의 추가 승인에 따라 rho_max 다음에 평균 H4 부족량을 최소화하고, 이후 migration 수·기준 스케줄 편차·동률 해소를 기존 순서대로 수행한다. 새 lambda나 가중합을 사용하지 않는다.

The primary grid-loading objective remains unchanged. Among electrically equivalent solutions, the scheduler preferentially preserves actionable four-hour GPU-service headroom for forecast future workload.

과거 72개 policy-day의 문제는 V41_COUNTERFACTUAL_ACTUAL_REPLAY_V1로 의미상 해소했다. 정책 변수는 동결한 Day-Ahead 결정, 정책과 무관한 실제 값은 역사적 외생 데이터가 근거다. 누락 데이터를 복구했다고 주장하지 않는다.

Raw H4는 별도 보존한다. extreme raw reserve forecasts are saturated before optimization by causally historical and physically actionable capacity limits. 이는 raw 예측 정확도 개선 주장이 아니다.
