# May23 targeted terminal-state audit

**MAY23_TERMINAL_CONSISTENCY = FAIL. May23 Actual은 HOLD이며, live DA 통합은 보류했다.**

기존 May23 repair를 terminal-consistent라고 표현했던 판단을 정정한다. 추가 post-H GPU-h가 0인 것은 timing/총량 보존만 나타낸다. Cross-boundary PENDING 작업 5개의 baseline-relative terminal site state는 달라졌다. 이 5건을 허용하는 예외는 추가하지 않았다.

## 작업별 비교

아래 시각은 모두 May23 issue 기준 15분 slot이다. Issue는 2025-05-22 18:00 AEST, H=120은 2025-05-24 00:00 AEST다. 모든 작업은 32 GPU, `normal`, issue 시점 PENDING이며 V39H standby timing repair 대상은 아니다. 하지만 terminal site 보존 계약은 적용된다.

| job_uid | RSP start/end | Repair start/end | Base site → repair site | H 이후 예약 구간 | D+1 snapshot / DA |
|---|---|---|---|---|---|
| 9062282 | 86 / 129 | 86 / 129 | AIDC03 → AIDC02 | [120,129), baseline AIDC03 | snapshot·DA에 없음 |
| 9062283 | 86 / 129 | 86 / 129 | AIDC07 → AIDC03 | [120,129), baseline AIDC07 | snapshot·DA에 없음 |
| 9062284 | 86 / 129 | 86 / 129 | AIDC09 → AIDC07 | [120,129), baseline AIDC09 | snapshot·DA에 없음 |
| 9062285 | 87 / 130 | 87 / 130 | AIDC02 → AIDC09 | [120,130), baseline AIDC02 | RUNNING / AIDC02 |
| 9062286 | 90 / 133 | 90 / 133 | AIDC03 → AIDC12 | [120,133), baseline AIDC03 | snapshot·DA에 없음 |

현재 production B1과 SHA가 연결된 V39H schedule, refreeze 전 원본 B1, 원본 RSP ledger를 비교했다. 전체 585개 작업 중 cross-boundary PENDING은 8개이고, terminal site 차이는 위 5개다. Terminal timing 차이는 0개다. 5개 작업의 post-H 예약량은 400 GPU-h이며 site별 per-job 대칭 차이는 800 GPU-h다. 이는 추가 작업량이나 RUNNING migration 횟수가 아니다.

## 왜 H 이전 initial placement 차이만으로 분류할 수 없는가

V39H에서는 PENDING의 site를 재선택할 수 있었고, refreeze는 선택된 site를 production assignment에 그대로 기록했다. 물리 궤적의 `active_end_slot=96`은 target slot 96, 즉 issue slot 120에서 물리 검증을 자른다는 뜻이다. 원본 전체 reservation은 각각 issue slot 129/130/133까지 계속된다.

V39J addendum은 cross-boundary PENDING에 대해 **refreeze 전 same-day frozen RSP witness의 site label을 terminal state로 보존**하도록 명시한다. 위 작업에는 그 label이 실제로 존재하므로, 물리 궤적이 H에서 끝난다는 이유로 H 이후를 UNASSIGNED로 바꿔 해석할 수 없다. Post-H grid feasibility를 주장하지 않는 것과 terminal site 보존 의무는 별개다.

관련 source는 live `dayahead/tools/run_v39h_shadow.py`의 `candidate_options` 및 `daily_metrics`, `dayahead/v39e/temporal_refreeze.py` 78–92행의 reservation/assignment materialization이다. 기존 지표는 PENDING site 차이를 집계했지만 cross-boundary site 불변 조건으로 차단하지 않았다. 과거 grid/primary 인증은 해당 조건을 인증한 것이 아니다.

## D+1 비교의 범위

사용자가 요청한 D+1 비교는 May24 D-1 snapshot 및 May24의 현재/원본 B0–B3 frozen DA에 한정했다. Actual/Fresh 결과는 읽지 않았다. Snapshot에는 측정 AIDC/site 필드가 없다. 9062285의 AIDC02는 별도 날짜의 RW-anchored synthetic initial/DA authority다.

May24 snapshot issue는 **2025-05-23 18:00 AEST**, 즉 May23의 H보다 6시간 앞선다. 이는 H 이후 관측이 아니다. 나머지 4개의 부재는 완료 또는 UNASSIGNED를 증명하지 않는다. Inter-day independent / intra-day stateful 평가이므로 D+1 자료를 May23의 terminal site authority로 역주입하거나 연속 multi-day simulation의 증거로 사용하지 않았다. FAIL 판정은 May23 same-day 자료만으로 이미 성립한다.

## 기존 fallback 확인

**원본 base RSP + 기존 exact minimum RUNNING migration 4회 witness는 사용 가능한 것으로 확인했다.** B1/B3 원본 파일 SHA와 canonical decision SHA, 원본 migration audit의 최소 4회 인증을 검증했다. 새 migration 해는 만들지 않았다.

기존 witness의 정확한 timing/runtime/GPU 보존, site capacity, Rack compatibility, gang indivisibility, C1/PCC 일치, planning voltage/current/transformer/inner polygon, 고정 WAN 경로·전송량·checkpoint·READY·restart 순서를 solver 없이 검사했다. Vmax=1.0474468560672427, Vmin=0.971702088436085이며 검증한 grid 위반은 0이다. Derived grid cache는 이번 감사에서 SHA를 기록했고, raw D1 입력은 기존 production certificate의 SHA와 대조했다. 계산 결과는 원본 frozen planning verdict와 일치한다. Cache 자체가 과거 required manifest에 포함됐다고 주장하지 않는다.

참고로 현재 repair timing과 나머지 assignment를 고정한 채 위 5개 site만 원복하는 산술 검사는 용량 위반 31개 site-slot을 보였다. 예를 들어 issue slot 90의 AIDC03은 96 GPU / 용량 64다. 이는 그 단순 치환이 실패한다는 뜻이며, **가능한 모든 May23 terminal-safe repair가 infeasible하다는 증명은 아니다.** 그런 최적화는 수행하지 않았다.

## Migration accounting과 live 상태

- 수정 fallback 후보: May23=4, May24=2, May25=8, May26=15.
- 해당 fallback들을 적용하는 월간 후보 총계: **105 = 76 + 4 + 2 + 8 + 15**. 기존 101 후보를 대체하며 원래 105 대비 감소는 0이다.
- 이 값은 기존 인증 migration witness들을 재사용하는 구성의 총계다. 새 terminal-safe repair 전체에 대한 global minimum을 새로 풀었다는 주장이 아니다.
- Live 통합은 계속 보류했다. Live migration accounting은 아직 76이며 124개 DA freeze 모두 SHA가 그대로다. May17 authority도 그대로다. 31일 readiness 재조립 또는 DA refreeze는 수행하지 않았다.
- May23/24/25/26은 모두 HOLD. May23 FAIL 증거가 완성된 후 사용자 지시에 따라 May23을 admission 검사 대상과 gate에 추가했다. 기존 코드가 May24–26만 검사했으므로 JSON 항목 추가만으로는 May23 Actual을 차단할 수 없었다.
- Live 변경은 admission용 `v39h_terminal_launch_gate.py`의 날짜 목록/주석과 `TERMINAL_AUDIT_LAUNCH_GATE.json`뿐이다. 공통 과학 소스 fingerprint, DA 결정, monitor는 그대로다.
- Orchestrator PID 30196 및 monitor PID 42504 유지. 마지막 확인에서 May10–13 worker 4개가 실행 중이며 완료 날짜 기록은 9개다. May23 결과는 아직 생성되지 않았다. 중복 날짜 worker 없음.
- Admission regression checks PASS: May23 포함 4일 차단, 다른 27일 허용, 누락 authority fail-closed, 동적 release는 격리 사본에서만 시험했다. 기존 fixed queue에서 HOLD worker가 실제로 대기하면 worker slot을 점유한다. 네 HOLD 날짜가 모두 대기하면 뒤 날짜 입장은 정체될 수 있으므로, 장기 HOLD를 무제한 skip으로 표현하지 않는다.
- Optimization=0, migration MILP=0, orchestrator restart=0, running worker stop=0, push=NO, PR=NO.

작업별 원자료는 `MAY23_FIVE_JOB_COMPARISON.json/csv`, 전체 비교는 `MAY23_ALL_JOB_TERMINAL_COMPARISON.csv`, fallback 검증은 `MAY23_EXISTING_FOUR_MIGRATION_FALLBACK_CHECK.json`, HOLD 적용 및 보존 증거는 `MAY23_HOLD_APPLICATION_RECEIPT.json`과 `MAY23_POST_HOLD_PRESERVATION.json`에 기록했다. 과거 101/May23 terminal-consistent 표현의 정정은 이 감사 결과가 우선하며, 과거 sealed artifact를 소급 덮어쓰지 않았다.
