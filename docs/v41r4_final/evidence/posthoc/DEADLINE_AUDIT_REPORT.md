FINAL_DEADLINE_AUDIT_CLASSIFICATION: C

**DEADLINE_AUTHORITY_NOT_ESTABLISHED**

619 total job-policy-day records(고유 job UID 297개)를 독립적으로 재계산했다. 실제 허용된 job별 completion deadline/window를 archive와 frozen method authority에서 확정하지 못했다. 따라서 **within deadline 수, deadline violation 수, 최소 slack, 최대 violation은 모두 NOT_AVAILABLE**이다. 미확정은 619/619이며, “위반 0건” 또는 “619건 모두 deadline 이내”라는 의미가 아니다.

RW_completion_slot은 requested-walltime 기준으로 생성한 reference schedule의 완료 좌표다. eligible standalone time shifting에서는 이를 상한 계산에 쓰지만 checkpoint migration의 job-level deadline이라는 authority는 없다. `DEADLINE_AUTHORITY_EVIDENCE.md`에 생성 경로, 활성 계약의 SHA 일치, 검사 분기, 코드 줄 링크를 기록했다.

## Population과 판정

| policy | flagged records | unique flagged UID | all migrations | flagged authority available | within | violations | unavailable |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B1 | 306 | 284 | 333 | 0 | NOT_AVAILABLE | NOT_AVAILABLE | 306 |
| B3 | 313 | 290 | 344 | 0 | NOT_AVAILABLE | NOT_AVAILABLE | 313 |
| ALL | 619 | 297 | 677 | 0 | NOT_AVAILABLE | NOT_AVAILABLE | 619 |

B0/B2는 checkpoint migration이 0건이다. B1 전체 migration 333건, B3 전체 migration 344건, 합계 677건 모두 deadline compliance를 판정할 authority가 없다. 124개 최종 policy-day의 canonical job record 총 188,036개를 읽었고, selected 184,368개(각 policy 46,092개)의 deadline field coverage를 확인했다. 명시적 deadline 필드 보유 selected record는 0개다.

619는 unique job 수가 아니다. B1은 284개 UID/306 records, B3은 290개 UID/313 records이며, 합집합은 297개 UID다. 서로 다른 independent D-day에 재등장한 flagged UID는 17개, unique UID-day는 320개다. 동일 UID의 B1/B3 비교와 여러 D-day 출현을 별개의 job-policy-day로 유지했다. 월간 연속 job 실행으로 합치지 않았다.

## 경계와 계산

좌표는 D-1 issue 기준 15분 슬롯, 구간은 [start,end)이다. D00=24, D24=120이고 day-origin에서는 0과 96이다. `final_completion_slot = optimized_completion_slot = max(final frozen compute_segments.end)`로 계산했다. reference completion은 같은 날 B0의 max end다. `post_day_extension_slots=max(0,final_completion-120)`은 평가 경계 이후의 wall-clock 연장량이며, migration으로 추가된 연장량은 별도 completion_delay_slots 및 additional_post_horizon_GPUh다.

677건 전부 segment service 합이 B0 및 safe_duration_slots와 같고, final completion-reference completion = restart-checkpoint임을 확인했다. Transfer end는 event의 exclusive end를 사용했다; `WAN_transfer_complete_slot`의 마지막 occupied slot과 혼동하지 않았다. 이 completion은 사용자가 지정한 **frozen planned compute completion**이며 관측된 Actual runtime completion으로 바꾸지 않았다.

Authoritative deadline이 없으므로 deadline_slack_slots/hours와 within_deadline은 677행 전부 NOT_AVAILABLE로 보존했다. N_at_deadline, min/median/mean/P10/P90/max deadline slack도 계산 불가다. Post-horizon이라는 이유만으로 feasible/infeasible을 새로 판정하지 않았다.

## RW reference와의 진단 비교 — deadline 판정 아님

| policy | flagged final <= RW | flagged final = RW | flagged final > RW | all migrations final > RW | min(RW-final), h |
| --- | --- | --- | --- | --- | --- |
| B1 | 114 | 0 | 192 | 202 | -23.5 |
| B3 | 117 | 0 | 196 | 210 | -23.5 |
| ALL | 231 | 0 | 388 | 412 | -23.5 |

619건 중 388건(B1 192, B3 196)은 RW reference보다 늦고, 231건은 RW 이내다. 전체 migration에서는 412건이 RW보다 늦다. 가장 큰 RW reference 초과는 23.5시간이다. 이 수치는 **authoritative deadline violation count 또는 maximum violation이 아니다**. “모두 RW 안이다”라는 주장도 raw 결과와 맞지 않는다.

## 요청한 두 사례

| day | policy | job_uid | GPU | issue state | RW | B0 end | final end | deadline | deadline slack h |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-05-01 | B1 | 8571256 | 4 | RUNNING | 188 | 188 | 190 | NOT_AVAILABLE | NOT_AVAILABLE |
| 2025-05-01 | B3 | 8571256 | 4 | RUNNING | 188 | 188 | 190 | NOT_AVAILABLE | NOT_AVAILABLE |
| 2025-05-15 | B1 | 8952973 | 60 | PENDING | 192 | 168 | 249 | NOT_AVAILABLE | NOT_AVAILABLE |
| 2025-05-15 | B3 | 8952973 | 60 | PENDING | 192 | 168 | 249 | NOT_AVAILABLE | NOT_AVAILABLE |

**May15 job 8952973, B1/B3:** reference [0,168), final [0,24)+[105,249). Checkpoint=24, transfer=[99,104), restart complete=105. Service 24+144=168 slots 보존. Pause-to-restart interruption은 81 slots=20.25h(wait 75 slots=18.75h, transfer 5 slots=1.25h, restart 1 slot=0.25h)다. 사용자 예시의 23.5h는 이 사례의 값이 아니다. RW=192, final=249로 RW보다 57 slots=14.25h 늦다. Authoritative deadline과 slack은 NOT_AVAILABLE이다. issue 시점에는 PENDING/high지만 reference start=0이므로 D00에서는 이미 RUNNING이고 첫 checkpoint migration 대상이다. Restart=105<120이라 목적지 연산 15 slots가 D-day 안에 존재한다. 이 조건과 서비스 보존 때문에 frozen candidate formulation이 허용한 것이며, deadline 내 완료가 증명된 것은 아니다. Post-horizon service=1,935 GPUh, B0 대비 추가=1,215 GPUh이다.

**May01 B1 job 8571256:** reference [0,188), final [0,26)+[28,190). Checkpoint/transfer start=26, transfer end=27, restart=28; interruption=2 slots=0.5h. RW=188, final=190으로 RW보다 0.5h 늦다. Requested walltime=604800 seconds는 요청 duration이며 deadline으로 변환하지 않았다. Authoritative deadline과 slack은 NOT_AVAILABLE이다. B3에도 동일 timing이 존재한다.

## Worst 20 diagnostic records

실제 deadline slack 순위는 만들 수 없다. 아래는 **RW minus final 값이 작은 순**으로 정렬한 진단 사례 20건이다. 첫 10행이 요청한 worst 10 examples다. 동일 job의 B1/B3를 별도 record로 표시한다. 모든 행의 actual authoritative deadline/slack/violation은 NOT_AVAILABLE이다.

| day | policy | job_uid | GPU | B0 end | RW reference end | final end | RW minus final (h; diagnostic) | post-H GPUh |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2025-05-12 | B1 | 8893072 | 4 | 145 | 145 | 239 | -23.5 | 119.0 |
| 2025-05-12 | B3 | 8893072 | 4 | 145 | 145 | 239 | -23.5 | 119.0 |
| 2025-05-18 | B1 | 9017735 | 8 | 158 | 158 | 251 | -23.25 | 262.0 |
| 2025-05-18 | B3 | 9017735 | 8 | 158 | 158 | 251 | -23.25 | 262.0 |
| 2025-05-07 | B1 | 8818579 | 2 | 134 | 134 | 226 | -23.0 | 53.0 |
| 2025-05-07 | B3 | 8818579 | 2 | 134 | 134 | 226 | -23.0 | 53.0 |
| 2025-05-18 | B1 | 9017728 | 8 | 142 | 142 | 234 | -23.0 | 228.0 |
| 2025-05-18 | B3 | 9017728 | 8 | 142 | 142 | 234 | -23.0 | 228.0 |
| 2025-05-18 | B1 | 9017714 | 8 | 134 | 134 | 225 | -22.75 | 210.0 |
| 2025-05-18 | B3 | 9017714 | 8 | 134 | 134 | 225 | -22.75 | 210.0 |
| 2025-05-01 | B1 | 8710966 | 8 | 173 | 173 | 255 | -20.5 | 270.0 |
| 2025-05-01 | B3 | 8710966 | 8 | 173 | 173 | 255 | -20.5 | 270.0 |
| 2025-05-01 | B1 | 8696212 | 4 | 162 | 162 | 242 | -20.0 | 122.0 |
| 2025-05-01 | B3 | 8696212 | 4 | 162 | 162 | 242 | -20.0 | 122.0 |
| 2025-05-01 | B1 | 8683269 | 4 | 590 | 590 | 669 | -19.75 | 549.0 |
| 2025-05-01 | B1 | 8683270 | 4 | 590 | 590 | 669 | -19.75 | 549.0 |
| 2025-05-01 | B3 | 8683269 | 4 | 590 | 590 | 669 | -19.75 | 549.0 |
| 2025-05-01 | B3 | 8683270 | 4 | 590 | 590 | 669 | -19.75 | 549.0 |
| 2025-05-02 | B1 | 8683270 | 4 | 494 | 494 | 572 | -19.5 | 452.0 |
| 2025-05-02 | B3 | 8683270 | 4 | 494 | 494 | 572 | -19.5 | 452.0 |

## Candidate가 왜 허용되었는가

**Checkpoint migration candidate generation이 job-specific completion deadline을 직접 검사했는가? NO.**

활성 경로는 allow_cross_midnight=True이다. Candidate final end는 reference end + (restart-checkpoint)로 연장된다. 첫 checkpoint 고정, 기존 시작/입장 결정 보존, GPU/rack/WAN 조건, 1회 migration, 재시작과 유효한 목적지 연산이 D24 전에 존재하는지, 전체 compute service 보존을 검사한다. RW 필드는 원본과 동일한지만 확인하며 final end <= RW 조건은 없다. standalone time-shifting의 RW 상한 검사는 migration 분기와 별개다.

따라서 job-level latest-completion gate가 migration formulation에 없는 것은 확인된다. 다만 이 gate를 요구하는 job-specific scientific contract를 확정하지 못했으므로, 확립된 deadline hard constraint를 implementation bug로 우회했다거나 final archive가 실제 deadline을 위반했다고 단정할 수 없다. 사용자 계약은 cross-midnight migration을 허용하고 terminal residual 제약을 비활성화한다. 이 감사는 새로운 SLA를 도입하거나 결과를 재최적화하지 않았다.

## 논문에서 사용할 수 있는 표현

“Checkpoint migration can defer planned compute service beyond the D-day evaluation boundary while preserving total planned compute service. Job-level completion-deadline compliance could not be established from the archived authority.”

한계는 별도로 유지한다: “Independent daily experiments do not propagate post-horizon service as next-day backlog.”

현재 근거로 “within the job deadline”, “within the authorized job-completion window”, 또는 “admissible post-horizon compute deferral”이라고 deadline 준수를 보증하는 표현은 사용하지 않는다. 관측된 현상은 planned post-horizon compute deferral이며, 이것만으로 workload dumping 또는 deadline violation을 확정하지 않는다. 향후 deadline authority가 확보되어도 deadline compliance PASS가 inter-day backlog accounting 해결을 뜻하지 않는다.

## 산출물과 보존

- 01_FLAGGED_619_DEADLINE_AUDIT.csv: 619행, 모든 요청 timing/authority 필드 및 raw source SHA.
- 02_ALL_MIGRATIONS_DEADLINE_AUDIT.csv: 전체 migration 677행, 같은 스키마.
- 03_DEADLINE_SUMMARY.csv: B1/B3/ALL, deadline 미확정과 RW 진단 통계를 분리.
- DEADLINE_AUTHORITY_EVIDENCE.md: 정의와 static source evidence.
- DEADLINE_AUDIT_MANIFEST.json: 원본 검증, source hash, field coverage, 반복 UID, candidate 검사, 감사 코드 SHA와 CSV readback 검증.

최종 accepted 124/124를 변경하지 않았다. Gurobi, DA/Actual, OpenDSS, ML, SUMO, route search 실행은 모두 0회. External workspace result read count = 0. PR은 method semantics만 읽었고 수정/업로드하지 않았다.
