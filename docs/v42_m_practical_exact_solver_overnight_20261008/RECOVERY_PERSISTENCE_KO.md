외부 OPEN 큐의 재시도는 실패한 LP 시도의 원본 바이트를 보존한다. 과학적 모델과 유효 LB/UB는 변경하지 않는다.

복구 순서는 durable intent 기록 → 실패 시도 폴더 이동 → SHA가 고정된 다음 checkpoint 원본 바이트 교체 → commit 표시이다. 프로세스가 어느 단계에서 중단되어도 다음 시작에서 intent를 먼저 재생한 뒤 OPEN 큐를 읽는다. 각 단계에서 강제 중단을 모사한 fixture가 PASS이며 재생은 idempotent이다. Windows 줄바꿈까지 보존한다.

재시작 audit는 모든 저장된 LP 인증서를 독립적으로 다시 계산하고 현재 incumbent 파일·replay SHA·원본 full replay·rho/UB 일치를 검증한다. 저장된 완료 receipt를 수용한 직후에도 다음 노드 선택 전에 audit한다. 인증 불능·중단 LP는 동일 도메인의 OPEN으로 남는다.

이 fixture는 optimize 호출 0이다. 실제 production 외부 LP의 속도, basis 재사용 또는 전역 gap 개선을 입증한 것으로 해석하지 않는다. native Gurobi tree의 checkpoint/restart를 주장하지 않는다.
