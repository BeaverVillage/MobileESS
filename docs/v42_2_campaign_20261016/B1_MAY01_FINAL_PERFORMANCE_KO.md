# May01 B1 최종 성능 기록 — 아직 미완료

현재 B1 FULL/Actual96/Fresh96 PASS는 없다. 이 파일은 최종 결과를 채울 실행 기록이며 완료 증거가 아니다.

## 마지막 실제 실행: ATTEMPT005

- 실행 Commit: `6f8c851e83a7a9e5a7101c69cc434f2e65855b45`
- Science Source: `49e1ea5b416509ae6a499c0cb69a8c5a6026178f5fea77c14a779087aec1bec7`
- S0: OPTIMAL, 정확 Phi=0, Native 76.53399991989136초.
- S1: Method=0/LPWarmStart=1/Presolve=0, 실제 basis 수용, 초기 primal infeasibility=0. 사용자 요청으로 10.601999998092651초에 중지(status11, SolCount0).
- 전체 Native: 87.13599991798401초. 전체 Attempt Wall: 507.44920468330383초.
- 원본 Integer P1: NOT_RUN. UB/LB/Global Gap: NOT_CERTIFIED. FULL/Actual96/Fresh96: NOT_REACHED.
- 이 실행은 원인 분석 우선 지시에 따른 사용자 중지이며, Phase I 완료시간이나 속도 개선으로 해석하지 않는다. Raw와 원장은 `B1_ATTEMPT005_RECONCILIATION.json`에 보존했다.

## 실패·중단 이력

ATTEMPT001: basis 확장/수치 병목으로 공식 중지. ATTEMPT002: crossover 병목으로 공식 중지. ATTEMPT003: 검증된 Windows Update 재부팅 중단, 알려지지 않은 Native 시간은 NULL과 구간으로 유지. ATTEMPT004: Phase I 누적 900.0149998664856초 TIME_LIMIT 후 원본 Integer root 수치 병목으로 공식 중지. ATTEMPT005: 위 사용자 중지. 동일 설정의 자동 재시도는 하지 않았다.

## 현재 개발 단계

229개 전체 Local Polytope의 정확한 축소 Native0와 회귀 1,305개는 PASS했다. Local Hard 261,414→210,067행, local 변수 174,685→134,630열. 아직 전체 Hybrid Master에는 연결하지 않았고 실제 속도 개선은 미검증이다.

다음 실제 실행은 Global Master·Original lift·full-domain pricing 인증 경로의 검증과 현재 Source/Case/Policy Gate를 통과한 새 Attempt에서만 수행한다. 원본 과학·물리 계약, A 5,400초/Phase I 900초, Worker1/Threads1 및 V42.1 Freeze는 유지한다.
