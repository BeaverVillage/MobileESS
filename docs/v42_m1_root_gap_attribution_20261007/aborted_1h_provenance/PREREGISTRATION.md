# PR162 C3A P1 native 1시간 단일 실행 사전등록

기준은 Draft PR162의 정확한 head `1d922c91eb27056a5ccc79c92ef18146707099ab`이다. 선택 authority는 `ULTRACOMPACT_EXACT_SELECTED`, C3A, N=4, H=96이다. P1은 기존 rho 최소화다.

고정 identity:

- matrix SHA256: `45cd48423b8d7f19fed376b71e181277f559c9e71527c17f9322d0100f7f0df8`
- data SHA256: `20aba68ffb3c4e29b0c9644d05e10ef33417ab92f6083edfb8906d6be8cb0467`
- start SHA256: `be02767838a1fe17b932c390303e5307e1c8385ba130fe9c36a7cb69804c54e5`
- 582,808 rows / 306,040 columns / 9,322 binaries / 296,718 continuous / 5,351,612 nnz

저장된 선택 C3A CSR와 attributes로 full MILP 하나를 새로 materialize한다. 모든 행·열·계수·이름·type·bound·RHS·목적 및 상수를 byte-exact transport 검사한다. 압축을 재검색하거나 C2를 재구축/benchmark하지 않는다. 저장된 역변환 인증서를 읽어 원래 물리 좌표를 감사하는 것은 모델 재구축이 아니다.

최적화 전에 동일 start의 C3A 행·경계·정수 잔차와 원래 route/P/Q/SOC/mode 및 grid 물리를 독립 재검증한다. start는 수정하지 않는다. identity 또는 replay 실패 시 optimize 전에 fail closed한다.

PR162 `C3_MILP_RESULT.json` 및 `v42_ultracompact/benchmark.py`의 production solver 설정을 상속한다. TimeLimit만 3600으로 변경한다. Method=2, Threads=1, NodeMethod=1, Crossover=2, MIPFocus=3, MIPGap=.005, FeasibilityTol=OptimalityTol=IntFeasTol=1e-8, Seed=20260929, DegenMoves=0, PreCrush=1, LazyConstraints=0을 유지한다. 나머지 solver parameter는 현재 default 및 PR162 effective 값과 대조한다. 새 LogFile 경로는 관측 산출물 위치만 변경한다.

실제 native optimize는 정확히 한 번이다. 별도 presolve/relax/root/NodeLimit/probe/retry/restart/P2 호출은 없다. 한 번 실행 토큰을 배타적으로 기록하고 두 번째 optimize 및 별도 presolve를 차단한다. PR162 짧은 benchmark의 arm wall timer, terminate callback, resource gate는 이번 실행에서 사용하지 않는다. build/audit/report 시간은 solver 예산 바깥이다.

callback은 관측만 수행한다. cut/lazy row/solution injection/parameter change/terminate를 호출하지 않는다. native incumbent/bound 변경과 약 60초 간격 Runtime/Work/node/gap을 기록한다. resource thread는 RSS/CPU/가용 RAM을 관측하며 solver와 독립된 event wait만 사용한다. resource state로 solver를 중단·감속·변경하지 않는다. 후보의 물리 검증은 optimize 종료 후 수행해 callback에서 solver를 지연시키지 않는다.

기존 LB는 비교표에서만 사용한다. 초기 또는 진행 LB로 이식하지 않는다. 새 gap은 이 실행의 native incumbent/global bound가 둘 다 존재할 때 `abs(UB-LB)/abs(UB)`로 계산하고 native MIPGap과 대조한다. 엄밀한 실수 산술 최적성 증명이 아닌 native tolerance 기준 인증임을 구분한다.

Gurobi가 .5% gap 또는 optimality에 정상 도달하면 조기 종료를 허용한다. 그렇지 않으면 자체 TimeLimit까지 실행한다. 결과는 OPTIMAL / GAP_TARGET_MET / TIME_LIMIT_VALID_GAP 또는 실제 예외·유효 해/경계 부재를 구분해 분류한다. P1-only이므로 M1_ACCEPTED는 false다. 종료 후 비교·보고·검증·commit 및 PR162 위 새 Draft PR 생성까지만 진행하고 과학 작업은 멈춘다.
