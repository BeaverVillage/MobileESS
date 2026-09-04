# V37-R4 최종 검토

## 캠페인 중단

- 캠페인 dispatcher, 날짜 worker, monitor는 중단 조치 시 이미 종료되어 별도 signal이 필요하지 않았다.
- May-05의 `RUNNING/B2_MESS02/5 of 14` 상태는 live worker가 없는 orphan 상태이므로 과학적 FAIL로 분류하지 않았다.
- 완료·부분 결과, beam/restricted/full-MILP/restoration/Fresh/P1 캐시, 로그와 상태 JSON을 삭제하지 않았다.

## May-01 B2 복원 불능

- 최초 Fresh 실패는 restoration round 1의 A상 저전압 4건이었다.
- 수리 전 base/trust-only/cut-only/cut+trust 네 모델은 모두 Gurobi status 3이었다.
- 대표 IIS는 `mess_flow_in[MESS01,22,STA01]`과 `mess_z[MESS01,22,STA01]=0`, `mess_stay[MESS01,21,STA01]=1`의 모순이다.
- 원인은 `G_OTHER_IDENTIFIED_IMPLEMENTATION_BUG`: 출발 슬롯의 TRANSIT 상태를 출발 전 boundary occupancy로 직접 옮긴 off-by-one이다.
- occupancy를 초기 위치, 직전 stay, connection-ready arrival로 재귀 구성하도록 수정했다. 선택된 move/stay와 이산 경로는 그대로 고정했다.
- 수리 후 base/trust-only/cut-only/cut+trust가 모두 feasible이다. 빔 재실행은 없었다.

## 복원 계약

- 전압 하·상한, 선로전류, 변압기전류, 변압기 kVA cut 경로: PASS.
- 전압은 V pu, 전류는 loading pu, kVA는 loading pu이며 제곱량을 사용하지 않는다.
- recourse는 MESS P/Q만 허용하고 이산 경로는 고정한다.
- rho는 0.10, P radius는 55 kW, Q radius는 70 kvar, 최대 round는 5로 유지했다.
- May-01 최초 위반의 4개 cut 산술을 독립 재계산했고 IIS에는 cut이 포함되지 않았다.

## 권한과 앵커

- April-only 계수 payload는 변경하지 않았다.
- calibration 범위와 evaluation applicability를 분리하여 May-01~31을 31/31 승인했다.
- 전압/전류 D1 앵커는 31/31 존재하며 96슬롯, 386노드, A/B/C, 60제어, 383분기와 유한값을 검증했다.
- May-01의 Apr-30→May-01 cross-month 빈티지를 포함해 D-1 18:00 fixed-AEST cutoff를 모두 통과했다. causal-vintage 실패는 0건이다.

## AIDC

- Apr-01 실현 숫자를 일반 계약으로 사용하던 count gate를 제거했다.
- scheduler source, cutoff, workload class, GPU/node request, PARTIAL/shared, runtime authority, fail-closed와 no-double-counting 규칙을 검증한다.
- 현재 frozen Apr-01 template을 May에 평가한 결과 temporal cohort 범위는 339~339이고 31/31 규칙 검증 PASS이다.

## 생산 프리플라이트와 런처

- production-loader dry-run: EXPECTED 31, READY 31, NOT_READY 0, MISSING 0.
- Gurobi optimization 0, Fresh OpenDSS solve 0, campaign spawn 0이다.
- 런처는 R4 프리플라이트와 230개 최종 파일 SHA를 먼저 검증한다.
- 불완전 매니페스트는 `MAY_CAMPAIGN_PREFLIGHT_FAIL`로 거부하고, 완전 매니페스트의 `-ValidateOnly`는 PASS했다.
- 실제 캠페인은 시작하지 않았다.

## 동결 상태

- K=200, fallback 200→400→800→FULL, beam=2, seed=2, WorkLimit와 solver/목적함수/물리 한계를 변경하지 않았다.
- 향후 실행은 4 dates parallel, 4 workers/date, rolling pool, 10초 PowerShell monitor 구성을 유지한다.
- `MAY_STARTED=NO`, `MAY_CAMPAIGN_LAUNCH_READY=YES`.
