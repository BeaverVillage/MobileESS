B0 비교군 실행 복원

최신 사용자 지시에 따라 B0/B2는 데이터센터를 유지하되 Pre-site, Time-shift, Migration, C0/C1 민감도 제어와 후보별 Current AC를 사용하지 않는다. B1/B3의 Unknown C0와 분리했다. B2는 기존 B0 Reference를 고정하고 MESS만 최적화한다.

Attempt003은 잘못된 공통 C0 경로로 실행됐으므로 공식 중단했다. Wall121.0618816초, PID종료, Native0/0초/inflight없음, Source/Raw/STOP/원장을 보존했다. 이를 정상 B0 또는 성능 결과로 사용하지 않는다.

새 v43_baseline은 v42_capacity.actual.Controller.admit 원본 FCFS의 큐·선두 대기·GPU 입장 알고리즘을 재사용한다. 후보 사이트만 기존 grid-blind R0 기본 사이트로 고정하고 Source GPU/Rack/호환성/하드 시간 조건을 유지한다. Signed score, UniformArmController, C0/C1, 후보 Current AC를 호출하지 않는다. 실제 서비스는 private 환경이 제출/완료 관측 이벤트로만 알리며, RUNNING/Overrun GPU는 실제 관측 해제까지 유지한다. 실제 GPU 점유에서 기존 C1로 IT/PCC P/Q를 새로 계산한다. Planning 전력·GPU 궤적을 Actual에 복사하지 않는다.

입력·Known R0·Q50 Reference는 기존 V43_MAY01_B0_REFERENCE_003을 재사용하고 Planning/전기계수/Domain을 다시 생성하지 않는다. 민감도 packet도 B0 실행에 만들지 않는다. 실제 이벤트 실행 뒤 원본7Reg Snapshot/Static 순차120슬롯을 한 번만 독립 Fresh로 실행하고 Actual96을 평가한다. 후보 AC 호출/과거 슬롯 재생은0회여야 한다. 물리 위반은 그대로 실패로 보고하며 비교군을 AC 조건에 맞게 재배치하거나 지연시키지 않는다.

8개 집중 Native0 회귀 PASS: B0/B2의 C0 진입 차단, 정책 없는 B0 dispatch, Overrun 관측 해제, 실제 서비스에 따른 Actual GPU 변화, Pre-site/Time-shift/Migration 부재. 실제 B0 전체 실행 및 Fresh96은 새 독립 attempt에서 측정한다. May01만 허용한다.
