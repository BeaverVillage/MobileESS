# PR230 AIDC 공통 DW 압축 검토

1,555개 개별 Job을 정확한 수학적 동등성으로 집계한 May01 229 Class를 B1 A1 및 B3 A1/A2가 호출하는 공통 DW 경로에 통합했다. Class는 날짜·Stage·고정 MESS·Domain·목적함수별로 다시 계산하며 May01 UID/229 Class/LB를 다른 날짜에 이전하지 않는다. B0/B2 Reference는 DW를 호출하지 않는다.

DW 최종 목표 크기는 1,030,845행 / 195,578변수 / 11,165,284 NNZ이다. 원본 FULL 정수 MILP 2,108,858행 / 946,756변수 / 272,044 Binary / 21,126,591 NNZ는 축소하지 않는다. DW 연속 LP에 대한 양방향 합/균등 분배 사영과 실제 Local/Global 계수·Bounds·RHS·목적함수 및 전체 Pricing 도메인을 독립 비교한다. 정수 동치성을 증명했다고 주장하지 않는다.

기존 Runtime Auxiliary 69,542개 제거를 한 번만 적용하고, 정확히 중복인 행 69,028개와 영행 항진식 5,194개를 제거했다. 물리·서비스 Coupling 행과 작은 계수는 임의 삭제하지 않는다. 각 원본-투영-집계-중복 제거 행렬의 실제 수와 SHA는 JSON 인증서/CSV가 권위이다.

기존 Layout과 새 CSC materialization의 메모리 차이를 Class 집계 효과로 혼동하지 않는다. 저장 행렬 Native0 재조립과 실제 Gurobi 모델 생성의 Wall 범위를 분리한다. 이전 B1 소비 Native 1,736.792초와 Raw는 SUPERSEDED_BY_VERIFIED_CLASS_AGGREGATION으로 보존하며 과학적 무효를 선언하지 않는다.

월간 실제 대형 Native0는 11일 완료와 May08 부분 결과를 보존하고 일시 중단했다. May01/10/12/25/31 우선 행렬 검증은 이전 Source에서 PASS했고, 최종 MESS Source가 결합된 May01에서 현재 Source/Case 및 행렬 증거를 새로 검증한다. 현재 M1이 없는 B3 A2는 FULL 행렬 검증 PASS로 표시하지 않는다. 실제 M1 후 A2에서 고정 MESS 조건을 다시 검증한다.

최종 회귀는 1,114개 PASS, 실패/Skip/실제 Native 시도 0이며 기존 682 ID와 과거 원장의 바이트를 보존했다. May01 네 Arm은 사용자 승인에 따라 최종 Source Freeze와 Launch Gate를 통과한 이후 새 실행 주기로 수행한다. Native 내부 재시작은 누적하며 실패 후 새 예산을 만들지 않는다. May02–31 Heavy, P2 및 R2는 실행하지 않는다.
