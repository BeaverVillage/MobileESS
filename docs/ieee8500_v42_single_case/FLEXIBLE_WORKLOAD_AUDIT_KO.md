# 원본 Job 기반 AIDC 유연성 상한 감사

2025-05-01의 원본 Native/B1·현재 Planning·현재 B0 Reference 1,649개 UID를 전부 대조했다. state/GPU gang/service slots는 동일하며 Job 복제·수요 배율·유연성 비율 조작을 하지 않았다. 현재 B0의 정확한 초 단위 마지막 슬롯 점유율을 독립 계산하여 frozen known_gpu 배열과 최대 오차 0 GPU로 일치시켰다. 원본 식별 Job만 계산하고 익명 CC4, 설치 GPU의 idle 및 C1 intercept 전력은 제거 가능한 유연성으로 세지 않았다.

현재 A loader는 NATIVE_INPUT의 역사적 can_timeshift 값을 같은 폴더 WINDOWS의 승인 mask/allowed_starts로 대체한다. 따라서 raw TS=true는 0개지만 실제 current WINDOW TS=true는 1024개다. 이를 새 권한으로 만들어낸 것이 아니라 현재 source binding 그대로 보존했다. prestart flag는 원본 Native 것을 유지했고 checkpoint는 원본 checkpoint_records·causal elapsed·양자화·24≤cp<118을 확인했다. 시간별 migration 기여는 해당 checkpoint가 도달한 이후만 계산했다. 보호/QoS를 완화하거나 WAN 경로·용량을 늘리지 않았다.

96×12 셀마다 `eligible known active GPU × 원본 IT swing(0.547723909020 kW/GPU) × 해당 슬롯/site의 원본 C1 slope`를 계산했다. known GPUh=6469.344262, 후보 유연 known GPUh=6465.344262(99.938%)이며 사이트 한 셀 최대 P 상한=43.817913 kW, 계통 합 최대 상한=342.875172 kW다. 이는 모든 AIDC 전력을 없애는 계산이 아니다. 각 셀의 UID·TS/PS/도달한 MG mask는 CSV에 있고 전체 원본 mask·시작/위치 대조는 `FLEXIBLE_WORKLOAD_JOB_MASKS.csv`에 있다.

AIDC PF=0.95를 그대로 사용했다. 소비 P를 줄이면 소비 Q도 ΔQ=0.328684105179×ΔP로 같이 줄어든다. 따라서 전기 민감도를 적용할 때 AIDC 방향은 dI/dP+0.328684105179×dI/dQ이며 P/Q를 독립 제어하는 MESS와 구별해야 한다. 개별 P/Q 편미분만으로 AIDC Q 제어 성능을 주장할 수 없다.

현재 B0 Reference와 Native B1 Reference는 같은 Job 수량에도 site 1290개, 시작 1024개가 다르며 현재 B0 시작이 원본 source window 밖인 admitted Job은 1024개다. 따라서 이 파일은 현재 B0 위치/시간에 UID 후보 mask를 투영한 **명시적 상한 완화**이며 Native A-stage와 물리적으로 동치인 실행 가능 dispatch 또는 인증된 candidate weighting이 아니다. 실제 재배치/시간 이동은 전체 compute service, destination GPU/Rack, checkpoint/WAN·restart, QoS와 finite window를 동시에 만족해야 한다. 이 공동 검증·reference adapter가 완료되기 전에는 표의 상한을 Production 성능이나 글로벌 최적해로 승격할 수 없다. Native Solver·최적화·OpenDSS는 실행하지 않았고 활성 캠페인과 입력은 읽기만 했다.

`KNOWN_JOB_FLEXIBILITY_BOUND.npz`에는 현재 B0 배열과 **원본 Native B1 R0 위치/시작을 별도 계산한** 배열을 함께 저장했다. 별도 Native R0 known GPUh=5664.864208, 후보 유연 GPUh=5660.864208, 계통 합 최대 P 상한=278.791474 kW이며 이것도 공동 dispatch 인증은 아니다. portable 입력은 `data/workload_flexibility/NATIVE_INPUT.json`·`WINDOWS.json`과 SHA manifest의 원본 byte 사본이고 Actual·성과 결과를 추가하지 않았다. `python -m ieee8500_v42.workload_flexibility`로 D: 활성 캠페인 없이 동일 감사를 재현한다.
