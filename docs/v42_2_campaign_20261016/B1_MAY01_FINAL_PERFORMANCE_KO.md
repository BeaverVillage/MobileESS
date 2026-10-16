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

Local Hard 추가 축소는 전체 229 Class에서 독립 검증과 Native0 readback을 통과했다. 누적 261,414→197,359행(24.50% 감소), Local 변수 174,685→134,630개. 상세 증거는 `B1_LOCAL_REDUCTION_PROGRESS_KO.md`와 `LOCAL_REDUCTION_NATIVE0_03/RESULT.json`이다.

1차 축소의 전체 Master 통합은 B1_NATIVE0_08 PASS. Bounds 추가 축소의 전체 Master 통합은 B1_NATIVE0_09 PASS. 역방향·평행 행 정리까지 포함한 현재 Source 전체 Master 검증도 B1_NATIVE0_10 PASS. 전체 Hybrid는 1,026,045×190,778→961,990×150,723으로 줄었다. 실제 축소 후 최적화 속도, Phase I 종료, FULL/Actual96/Fresh96는 아직 검증하지 않았다.

현재 Source의 Global Master·Original lift·full-domain pricing 경로·M Native0·회귀·Gate를 통과한 새 Attempt에서만 실제 실행한다. 원본 과학·물리 계약, A 5,400초/Phase I 900초, Worker1/Threads1 및 V42.1 Freeze를 유지한다.
