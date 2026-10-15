# D0 A1 별도 트랙 병목 검토

Unknown C0/C1 진단과 독립된 기존 D0 A1 모델이다. PR223 M2 고정 운전을 새 D0 공동 최적화 결과로 이전하지 않는다.

기존 Pilot는 요청25초, 실제 Native26.238초, SolCount0, TIME_LIMIT이다. INFEASIBLE 판정이나 모순 제약의 증명이 아니다. P1이 미인증이므로 P2와 신규 M1/A2/M2도 NOT_RUN이다.

원래 모델은844,129행 /36,931변수 /10,920,902 NNZ이다. Presolve 표기[12.97]초, Barrier 완료 누적 Native 시각[26.22], 중단 Root relaxation 표기[9.83]초를 보존했다. Barrier는19회에서 제한시간으로 중단되어 Root LP가 끝나지 않았다. 세 시간을 더하지 않는다.

마지막 Barrier의 primal residual은1.55e-6, dual residual은3.33e-8, complementarity는1.36e-5였다. 이는 수렴 중단 관측이며 모델의 구조적 infeasibility 증명이 아니다. 원래 numerical policy의 Method2/ScaleFlag2/NumericFocus3와1 Thread를 보존했다.

새 별도 runtime Native0 재생성 PASS: Matrix 29ddbc898bf954a607bde471014bd93c1e973ece3f661f24624a7b9798a88f34, Domain 5bb3e3a0bbda181fc483215b2878463da712d85c3f37418acf0e2f07b1a3592c, Objective 6bf133ea221f9f8e8e1509a88a6b9a11a0510a98e0c0ea8aca45cb68897530fd. optimize/presolve/IIS는 전역 차단했고 호출0이다. Case/Science와 Source13개 및 기존 FINAL_NATIVE0 모델 바인딩이 같다. 원래 출력과 Native 원장은 수정하지 않았다.

정적 bounds-only 필요조건 검사: 변수 bound 모순0개, row box 모순0개. 유한한 row 구간은15,983행이며 나머지828,146행은 무한 bounds 때문에 결론을 내리지 못했다. 모순을 찾지 못했다는 사실은 LP/MILP feasibility의 증명이 아니다.

다음 최적화는 추가 승인 전 HOLD다. 잔여41.319초에서30초 반환 여유를 빼면11.319초로, 이전 Presolve12.97초보다 짧다. 첫 제안은 모델·행·도메인·목적함수를 바꾸지 않는120초 P1 trial이다.120초와30초 반환 여유만 계산한 최소 총 한도는468.681초(108.681초 추가)다. 기존 Pilot의1.238초 overshoot도 고려해 총 한도480초(120초 추가)를 권고한다. 이 경우30초 반환 여유 외11.319초 buffer가 남는다. 이는 첫 정수해나 최적성의 성공 보장이 아니며 P2/M1/A2/M2 예산은 포함하지 않는다.

현재25초 Pilot adapter는 동결했다.120초 trial은 추가 예산과 별도 Supervisor admission이 승인된 뒤에만 준비하며 이번에 상한을 변경하거나 실행하지 않았다.

정수해 확보를 우선하려면 기존 bound-focused MIPFocus3 대신 feasibility-focused1을 승인된 별도 Solver 전략으로 검토할 수 있다. 이번에는 변경·실행하지 않았다. FeasibilityTol/원래 물리 계약/서비스·QoS/GPU·전력/CDF·Carry와 P1→P2→M1/A2/M2 순서는 유지한다. FCFS나 축소 도메인으로 PASS를 만들지 않는다.
