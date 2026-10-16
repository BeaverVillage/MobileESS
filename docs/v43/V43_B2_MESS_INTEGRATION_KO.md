# V43 May01 B2 연결

공식 범위는 2025-05-01 B0/B1/B2/B3뿐이다. May02~31은 승인되지 않았고 자동 활성화하지 않는다.

B0는 PR189 NATIVE_INPUT이 참조하는 원본 R0의 사이트와 시작시각을 유지한다. 서비스는 `v42_final.native.canonical_jobs`의 현재 Q50 해석이다. 옛 Q90/요청 잔여시간을 새 서비스로 가져오지 않는다. 별도 FCFS 캐시는 RUNNING 사이트가 달라 B0로 대체하지 않는다. `V43_MAY01_B0_REFERENCE_003`은 nominal 1,499개, D-day Known 5,759.75 GPUh를 보존한다. CC4는 literal forecast와 기존 grid-blind backlog allocator를 쓴다. 슬롯20 backlog 117.269 GPU는 다음 슬롯으로 보존되고 종단 backlog는 0이다. 총 CC4 5,503.441472156033 GPUh 및 cohort/CDF/carry replay는 Native0 PASS다.

`v43_mess.library`는 기존 K16/K32/K48, Adaptive Beam, Direct Joint를 SHA로 고정해 제자리에서 읽는다. 역사적 Case/UB/LB/point globals와 D0 모델은 불러오지 않는다. 원본 M Case builder에 B0 고정 P/Q를 공급하고 V43 Arm/Stage/Source/parent/AIDC anchor를 명시한다. 실제 FULL/Compact transport와 K16 projection 검증 후 Native를 허용한다.

M Joint 1,800초와 별도 K48 300초 원장을 분리한다. K16/32/48 원본 cap 90/180/180초, Joint cap 140초, Worker1/Threads1 및 6개 공유 OS lock을 유지한다. 독립 K48 bound만 Global LB 후보이고 제한 pool ObjBound는 진단값이다. STAY/MOVE를 강제하거나 초기 FULL MILP seed를 실행하지 않는다.

`v43_arms`는 기존 Actual 비교 함수와 이벤트 엔진을 호출하고 동결 AIDC/최종 MESS만 Arm별로 연결한다. Current AC와 Fresh는 원본 7-RegControl snapshot/static 계약이다. MESS 주입은 기존 mapper의 MESS 부분을 사용한다. B2/B3 민감도 packet에도 자신의 실제 MESS P/Q를 넣는다. Source 동의 없는 Unknown Pre-site는 실행하지 않는다. 초기 44개 MODEL_ASSUMED와 원본 210개 사이트를 구분하며 지연 TIME actuation은 NOT_CERTIFIED다.

현재 15개 소스·산술·binding guard와 B0 cohort Native0 PASS는 실제 M FULL Native0/Native 최적화/Actual96/Fresh96 인증이 아니다. Gate B 종료 전 경쟁하는 M build/Gurobi/OpenDSS를 시작하지 않는다. B3 A2의 PR189 고정-M1 연결은 아직 구현해야 한다. Golden003은 B1 A1 인증이며 B3 A2 인증이 아니다.
