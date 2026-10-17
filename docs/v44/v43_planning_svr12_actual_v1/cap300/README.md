# Joint 호출 cap 300초 및 K48 완료 지점 재개

직접 사용자 지시로 `V44_JOINT_CALL300_COMPLETED_K48_RESUME_V1` 실행 정책을 추가했다. 기존 과학적 Source/물리/행렬·Case SHA를 바꾸지 않고 별도 운영 정책 Source SHA와 Permit을 모든 새 Worker 요청·Stage 체크포인트에 기록한다. 기존 기본 140초 경로는 보존하며 활성 캠페인은 `python -m v44.cap300 --resume`로 실행한다.

활성 경로에서 Adaptive Beam의 Joint cap과 Native 예산 검사 cap을 모두 300초로 적용한다. K48 총300초, Joint 총900초, Threads1, 기존10초 반환 여유, 목적함수·모든 제약·후보 생성·Solver 수치 설정은 유지한다. 시간은 measured Native Runtime이다. 사용한 Joint 예산을 초기화하지 않으며 각각 560.957/561.121초를 차감해 약339초가 남았다.

기존 May01/May02 Worker는 마지막 호출을 정상 종료한 뒤 다음 호출 전에 정산해 멈췄다. 이전 의도적 STOP이 기존 엔진에서 IMPLEMENTATION_FAILURE 라벨로 봉인된 결과와 Raw는 보존한다. 새 Attempt는 그 종료 결과를 최종 답으로 재사용하지 않고, 검증된 Binary 행렬·역변환·완료 K48와 정산 원장으로 M1을 재개한다. K48 재최적화와 모델/Presolve 재생성은 하지 않는다. Gurobi B&B 상태는 복원하지 않는다. 유효한 기존 FULL incumbent가 있으면 원래 검증 후 재사용한다.

재개 어댑터에 남아 있던 SVR11 계수 로더와 메타데이터 경로는 이 운영 경로에서 원래 V43의 날짜별 7-RegControl 계수 생성자로 연결했다. 변압기 정격도 원래 생성된 coefficient 객체에서 가져온다. 실제 May01 Binary 복원 Native0에서 96개 계수·원래 Case SHA·961472×316743 FULL 및 Transport 검사를 통과했다. 추가 회귀7개 포함 총191 PASS/0 FAIL이다. 캠페인 내부 추가 검증 루프와 실제 Actual/Fresh 재실행은 추가하지 않았다.

실행 정책 및 과학적 Source 식별자, 원장과 검증은 POLICY_AND_RESUME_REPORT.json을 따른다. B2 2-worker 먼저, 이후 Main 1-worker 날짜별 B0→B1→B3 순서는 유지한다. 새로운 실제 FULL 가능해/Actual/Fresh PASS는 실행 결과가 있을 때만 인정한다.
