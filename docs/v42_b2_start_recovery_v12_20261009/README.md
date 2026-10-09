# B2 운영 시작 복구 V12

B1 전체 31/31 PASS를 보존한 상태에서 B2를 이어 실행한다. 최초 시작 게이트는 원본 FULL 생성과 transport 검증 이후 Grid 계수의 `SimpleNamespace` 내용 해시에 실패했다. V11은 모든 필드를 정확하게 해시하도록 수정했고, V12는 PASS한 게이트를 실행 중인 B2 워커가 다시 통과할 때 잘못 차단되는 조건도 수정했다. 검증 전 Native=0 FULL 생성과 실제 운영 중인 워커를 구분하는 상태 조건이다.

V10과 V11의 소스 및 출력은 보존한다. V11은 기존 산출물을 SHA 확인하던 단계에서 교체했으며 Native 워커가 없었다. V12는 완료된 B1 날짜를 재실행하지 않고 모든 완료 결과와 산출물 SHA를 다시 확인한다. 독립 파일 해시만 8개 작업으로 병렬화했으며 Native Threads=1, 모델 생성, 계산 예산, 정밀도 및 물리 제약은 변경하지 않았다.

실제 May01·May23의 BASELINE/OPTIMIZED FULL 생성 네 건은 Native=0으로 순차 수행한다. FULL/선택/Compact 행렬과 domain, graph, Grid 모든 계수, 고정 AIDC anchor 및 정확 transport 상태가 같아야 B2 운영 게이트가 PASS한다. 원본 MESS 모델 생성기를 유지하며 worker별 불변 입력, 원본 PCS 계산 재사용, 중복 Gurobi 모델 복사 제거를 연결했다. B1 AIDC Job/Graph 전용 가속은 B2의 AIDC 고정 입력 경로에 적용되지 않는다.

경량 회귀 238개가 통과했다. 여기에는 모든 namespace 필드의 변경 검출, 알 수 없는 타입 거부, B1 완료 행 보존, 완료 request byte 변조 거부, 실제 실패 원인 표시, 실행 중인 3워커의 PASS 게이트 재통과, 검증 전 워커 차단 및 병렬 SHA의 내용 변조 검출이 포함된다.

B2 운영 정책은 3워커, Threads=1, P2=0, 날짜별 Native 누적 5400초와 독립 인증 Gap 3%다. Coordinator/Monitor/Watchdog는 Windows Scheduler 소유로 실행한다. FULL 검증 및 운영 시작의 실제 상태는 runtime journal과 localhost:8793에서 확인한다. 운영 시작 증거는 FULL 비교와 실제 워커 모델 생성·Native 진입을 확인한 뒤 별도 기록한다.
