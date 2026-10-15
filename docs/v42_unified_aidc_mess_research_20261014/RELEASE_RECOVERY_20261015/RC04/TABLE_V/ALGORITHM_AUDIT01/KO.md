# May01 AIDC 알고리즘 연결 누락 감사

사용자가 확인한 AIDC 구성은 **LB Dantzig–Wolfe(Phase I, P1/full-domain pricing) + UB MILP**다. 현재 Table V 어댑터는 이 구성을 충족하지 않는다. `v42_integration/table_v_a.py:execute_current_a`는 원본 F2-CRA 모델의 단일 P1 MILP만 실행하며, DW Phase I/P1 또는 full-domain pricing을 호출하지 않는다. 이 누락은 통합 구현 결함이며, AIDC 알고리즘 전체가 연결됐다는 설명을 정정한다.

현재 MILP는 UB 후보 계산이다. Original FULL 검산을 통과한 점의 물리적 실행 가능성과 DW 하한 인증은 별개다. MILP 내부 `ObjBound/MIPGap`을 요청한 DW 하한·Global Gap으로 바꾸어 보고하지 않는다. 현재 케이스에 유효한 DW 하한 증거가 없으므로 해당 LB/Gap은 미인증이며 0%가 아니다. AIDC–MESS 전체 공동 최적성도 인증하지 않는다.

현재 EXECUTION02의 B1은 UB MILP 호출 중이다. 모델 build는 300.65601110001444초이며 현재 행렬은 2,108,858행/946,756변수/21,126,591 NNZ다. Native Runtime은 호출 반환 후 원장에 기록한다. 실행 중 호출의 wall을 최종 Native Runtime으로 대체하지 않는다. EXECUTION01에서 이미 소비한 B1 A1 Native 776.2689998149872초는 같은 Stage의 사용량으로 유지한다. 현재 호출 cap 4623.731000185013초는 남은 Stage 예산이며 추가 예산이 아니다. 과거 케이스의 INFEASIBLE·하한·Gap을 현재 케이스로 전이하지 않는다.

기존 DW 수학 kernel은 보존되어 있다.

- `v42_a_stage_phase1.producer`: row_partition, native_block, complete_graph
- `v42_a_stage_phase1.backend`: assemble_original
- `v42_a_stage_compact_rowgen.assembly`: build, compact_inverse
- `v42_a_stage_canary.phase`: Phase I, 원본 P1, full_pricing, inclusion 검증
- `v42_a_stage_canary.pricing`: 전체 클래스 pricing 및 원본 binary64 계수의 독립 하한 검산

PR191의 `v42_may_build_v6.a_stage` 및 `v42_b3_joint.a_source.ASourceBridge`에는 이미 fresh-date 입력·A1/A2·fixed-MESS·측정 Native account·P1-only 경로가 있다. 과거 bare Canary의 고정 날짜·예산·P2 자동 후속 문제는 이 기존 adapter에서 해결되어 있으며, 그것이 복원 불가 사유는 아니다. Table V가 기존 adapter를 호출하지 않은 것이 직접적인 누락 원인이다. 현재 D0/E1 데이터·Runtime 보조열 소유권·receipt/class/engineering seed·69 RUNNING hold·current grid/CC4/MESS·Stage 원장의 정확한 연결 및 독립 검증이 남아 있다. 이 감사는 그 연결을 구현·실행·인증했다는 증거가 아니다. 자세한 근거는 `KO_DW_RESTORATION.md`와 PR180/186/191 metadata에 보존한다.

MESS 어댑터의 지정 경로는 Adaptive Beam → 4-MESS Joint MILP → Original FULL → Registry와 별도 K48이다. 현재 EXECUTION02의 B2/B3는 아직 실행하지 않았으며, 지정 경로가 존재하는 것과 실제 May01 완료를 구분한다. MESS DW/S1, R2, P2를 재개하지 않는다.

B0의 Reference Actual96/Fresh96 물리 검증은 AIDC 최적화가 없는 별도 결과로 보존한다. B1/B3와 네 Arm 통합 완료·ReleaseFreeze·5월 31일 캠페인 PASS는 주장하지 않는다. DW 복구 전까지 이 실행을 요청한 AIDC LB–UB 알고리즘의 완료 결과로 승인하지 않는다.
