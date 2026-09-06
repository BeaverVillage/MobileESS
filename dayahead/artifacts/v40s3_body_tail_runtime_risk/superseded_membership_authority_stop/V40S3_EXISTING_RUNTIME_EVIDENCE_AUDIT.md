# V40S3 기존 증거 재사용

Current PR baseline은 V40J/V35R3D-R1이다. T7/S2 survival을 current RSP로 대체하지 않았다. March rolling prediction과 현재 formula의 일치를 확인했지만 Apr01 final model-state 동일성은 주장하지 않는다. 기존 q를 선택했던 calibration 표본 재사용이며 독립 Q90 검증이 아니다.

K의 조건부 point bias, L의 N=4 support 부족, N/Q의 시간·구조별 실패, S의 historical feature/state authority 부족, S2의 causal-clock survival safety 실패를 그대로 보존했다. April 결과는 새 u/eta 선택에 사용하지 않았다.

요청한 다섯 duration threshold별 위험 집중과 runtime 구간별 분산은 THRESHOLD_FORENSIC에 있다. 긴 작업이라는 사실과 GPU 양의 과소예측 질량은 별도로 집계한다. body oracle은 실제 runtime을 사용한 진단이며 분류기가 아니다. D1 PENDING authority 부족으로 새 fit을 실행하지 않는다.
