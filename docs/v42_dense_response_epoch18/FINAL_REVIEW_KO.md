# Source18r 최종 검증: Exact PASS, Root180 미달

실행 커밋 `85168a00256f4427c9895aa2ffb8623b6158ebef` / Source SHA `146bf39f5e4f9d720ef7118051edbcdc58b96ca3d83af31c3e7bd5349f1fecd8` / Case SHA `34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292`를 동결했다. 실제 선택 행렬 SHA는 `ed9fd6db73bf47948505cca3a616edf88c7caebdacce8f1dd1007617d6660ef0`다. 최종 원본 정수 영역과 분수 LP 사영 동등성, 독립 증명, Gurobi CSR/RHS/Sense/Objective/Type/Bound readback이 모두 PASS했다. 회귀 검사 174개 PASS, 실패·오류·skip 0개다.

14,890개의 같은 슬롯 전압 공통 선형식을 정확한 연속 보조변수와 상하한으로 공유했다. 최종 모델은 **715,596행 / 354,277열 / 9,322 Binary / 7,911,369 NNZ**다. C3A 대비 행 14,890개와 NNZ 698,341개(약 8.11%)를 줄였고 연속 변수 14,890개를 추가했다. Physical FULL 대비 Binary 감소율은 약 95.53%로 유지됐다. 소수 계수 제거·임의 경로 삭제는 없다. 모든 단계·변수/행 family와 4대×96슬롯 결과는 동봉한 census/CSV에 있다. Raw는 원본 입력 incidence로 계산한 분석 수치이고, 나머지 단계는 실제 저장 행렬에 연결해 확인했다.

Physical Prescreening은 완료/PASS다. 기존 Forward 제거 6,576개는 유지했고 신규 Forward/Backward/SOC 추가 제거는 0개다. 원본 이동에너지는 SOC[depart+1]에 차감하며 실제 효율과 0.25시간을 보존한다. LP 안전성을 증명하지 못한 경로별 SOC 후보는 진단만 수행하고 적용하지 않았다. 모든 MESS P/Q 외접 범위를 고려한 Grid 검사는 경로 삭제 없이 PASS했다. 실패한 Source18의 물리 producer 실측 4.9210012초는 상속된 기존 생성 측정이며, 이번에는 producer를 재실행하지 않았다. 저장 case 복원·독립 검증 wall은 346.7176337초다. 원본 Gurobi 모델 재생성은 0회이며 원본 생성 wall을 새 Source 성능으로 재사용하지 않았다. 최종 Full Gurobi CSR 입력 생성 wall은 3.395258초다.

새 초기화 Native 5.328초와 새 U4 38.507초를 실행했고 U4와 최종 점의 원본 FULL/96슬롯 물리 replay가 PASS했다. UB는 `0.6760534504652341`다. U4 제한 영역 bound를 Global LB로 사용하지 않았다.

Full C3A Root Native optimize는 **정확히 1회**, 실제 readback `TimeLimit=600`, sweep 0회다. API runtime은 **601.897000초**로 Gurobi가 마지막 Barrier 반복 후 약 1.897초 늦게 반환했다. 반복·추가 Full 실행은 없다. 초기화/U4 포함 총 Native runtime은 645.732000초다.

- Main MIP Presolve: **70.78초**, 610,100행 / 354,177열 / 9,326 Binary / **7,998,268 NNZ**. Binary 증가 4개는 Gurobi 내부 처리 결과이며 native family별 축은 export하지 않아 알 수 없다.
- 내부 Root LP Presolve: 555,551행 / 397,098열 / **7,903,205 NNZ**. 최종 내부 Root LP NNZ 감소는 작아 입력 NNZ 개선율을 Root 속도 개선율로 해석할 수 없다.
- Barrier: 56회 반복, 출력 elapsed native **601.63초**, TIME_LIMIT. 이 시간은 독립 Barrier 소요 시간이 아니며 Presolve와 합산하지 않는다.
- Crossover: 진입·완료 증거 없음, 시간 null.
- Root: `Root relaxation: time limit, 0 iterations, 528.89 seconds`; **미완료**. 528.89초는 중단 시 경과시간이며 완료 시간은 null이다.
- ObjBound / solver LB: `0.28940049108548904`. 검증 UB 기준 Gap **57.19266119%**. NodeCount 1, Status 9, Native error 없음.
- 측정 process peak RSS **6,404,554,752 bytes**, peak private commit **9,086,836,736 bytes**. Gurobi MaxMemUsed **3.263167186 GB**.

판정은 **ROOT_INCOMPLETE / Root180 미달**이다. Exact 증명 및 압축 PASS와 Root180 성능 PASS를 분리한다. 저장 증명 JSON 직렬화 불일치로 실패한 이전 Source18 시도는 Native optimize/presolve 0회였고 원본 소스·행렬·증거를 그대로 보존했다. 이 successor는 메타데이터 canonicalization과 검증된 저장 PhysicalDomain 복원만 수정했다. Native0 진행 파일의 호출 수 0은 고정된 단계 필드이며 실제 호출 횟수는 ledger의 3회(Full 1회)를 기준으로 한다.

5월 공식 캠페인은 **HOLD**다. 7개 과거 controller는 identity가 일치하는 suspended 상태, 캠페인 worker는 0개, Windows 예약은 Disabled, heartbeat는 PAUSED다. Source17과 실패 Source18은 변경되지 않았다. Root600 재실행·파라미터 sweep은 금지한다. 후속 Multi-Time 연구는 이 결과를 동결·PR 기록한 후 별도 브랜치에서 Native 0 정적 분석으로 시작한다. 현재 Root가 600초 내 완료되지 않았으므로 의미 있는 120초 LP 비교 조건이 충족되지 않아 Full-size Native를 추가 호출하지 않는다.
