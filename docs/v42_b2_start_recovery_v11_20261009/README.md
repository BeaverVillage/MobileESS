# B2 FULL 검증기 복구 및 운영 시작 V11

B1 May01~31 전체가 PASS로 완료된 뒤 B2 시작 게이트가 실패했다. 원본 FULL 모델 생성과 원본 transport 검증은 완료됐지만, Grid 계수의 `types.SimpleNamespace`를 과학 내용 해시에 넣지 못해 `UNPROVEN_SCIENTIFIC_FINGERPRINT_TYPE:SimpleNamespace`가 발생했다. 상위 게이트가 이를 일반적인 receipt drift로만 표시했다.

V11은 정확한 SimpleNamespace 타입의 모든 필드를 재귀적으로 해시한다. 배열의 모든 byte, shape, dtype 및 추가 필드를 비교한다. 알려지지 않은 타입은 계속 거부하며 하위 실패의 실제 진단을 상위 게이트에 전달한다. 과거 V10 소스와 실패 출력은 보존하고 V11 별도 출력에서 재검증한다.

B1 31개 완료 행, 결과 SHA, 원본 Native 시간 ledger를 보존하며 완료 날짜를 재실행하지 않는다. 이전 완료 request를 handoff manifest에 byte SHA로 봉인해 과거 전체 소스 체인을 날짜마다 반복 검사하지 않는다. 현재 소스 체인은 여전히 검증하고 Coordinator는 모든 완료 결과의 모든 artifact를 직접 다시 해시한다. 봉인된 과거 request 경로는 새로운 Native 진입을 허용하지 않는다.

B2는 기존 원본 MESS graph/FULL/Compact/C3A 생성 경로를 사용한다. 적용 가능한 고속화는 worker별 불변 입력 메모화, 원본 PCS 삼각함수 계산 재사용, 중복 Gurobi 모델 복사 제거 및 단계별 시간 기록이다. B1 AIDC Job/Graph 전용 고속화는 B2 AIDC 고정 입력 경로의 실행 대상이 아니다. 다른 worker/날짜의 모델, 점, bound 또는 Native 시간은 공유하지 않는다.

경량 회귀 221개 PASS. 실제 May01·May23의 BASELINE/OPTIMIZED 네 개 FULL 생성은 Native=0으로 순차 수행한다. 과학 내용, FULL/선택/Compact 행렬과 domain, 계수, graph, 고정 AIDC anchor 및 정확 transport 상태가 모두 같아야 운영 B2가 시작된다. 이 검증이 끝나기 전 경량 테스트를 FULL 동치성 PASS로 간주하지 않는다.

운영 정책은 B2 3워커, Threads=1, P2=0, 날짜별 Native 누적 5400초와 인증 Gap 3%다. 기존 수치 정밀도 설정과 원본 알고리즘·물리 검증을 유지한다. Windows Scheduler가 Coordinator/Monitor/Watchdog를 소유하며 실제 상태는 캠페인 journal과 localhost:8793에 기록한다.
