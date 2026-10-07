# 관측 시각의 구분

Root 완료 후 수 분간 새 native callback/log가 없는 구간을 관측했다. 기존 frozen callback 및 모델/설정을 변경하지 않고 별도 read-only observer를 추가했다. 이는 CSV와 process 존재 여부만 읽으며 Gurobi를 import하지 않는다.

NATIVE_OBSERVATION_HEARTBEAT.csv는 약 60초 간격으로 wall clock과 마지막 실제 native callback의 Runtime/node/UB/LB/gap/Work 및 그 관측값의 age를 기록한다. 현재 native 상태로 갱신되지 않은 값은 last_observed로 명시한다. wall elapsed를 Gurobi Runtime으로 바꾸어 쓰거나 Work를 보간하지 않는다. 이 별도 관측은 solver를 중단·변경·감속하지 않는다.
