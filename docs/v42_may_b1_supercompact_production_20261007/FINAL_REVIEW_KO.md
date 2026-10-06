# PR134 정확 압축 및 독립 May B1 실행

압축 분류 **A_STAGE_SUPERCOMPACT_SELECTED**, 캠페인은 **MAY_B1_CAMPAIGN_RUNNING**이다. 아래 날짜 수치는 2026-10-06T18:47:17.155383+00:00의 스냅샷이다. 31일 완료나 repair queue 완료를 주장하지 않는다.

PR134 accepted 기준은 `52ef855a59144a7c561df44b81dc2ad265babdbd`이며 1,499개 작업·96슬롯의 current accepted freeze를 원본 원시 해로 재구성했다. input SHA `f18b9dea2686b49de73b6d5d6ec7cc9e409c82e47b7f3bf7d29bdf5b1ba31170`, accepted DATA SHA `79263899f1040d8b13b5af29dc881c52e83ac543c96f90f8e63e9061b637aa74`, 원본 matrix SHA `eee234d2b56c733cb8f52a8585ac6f93314f85de7f986adc709f40a05df8bc47`. 세부 source/input/model 축과 SHA는 Phase-I PR134_BASE_IDENTITY.json에 있다. PR150/151은 fixed replay·monitor·실행 운영 참고로만 사용했다.

| 항목 | 원본 | A2SC | 감소 |
|---|---:|---:|---:|
| 행 | 9,133,426 | 7,828,869 | 14.2833% |
| 열 | 7,449,002 | 6,852,953 | 8.0017% |
| Binary | 2,223,230 | 2,220,986 | 0.1009% |
| Continuous | 5,184,087 | 4,590,282 | 11.4544% |
| 일반 integer | 41,685 | 41,685 | 0% |
| nnz | 53,767,578 | 42,419,133 | 21.1065% |

모든 row/column family를 전수 감사했다. 채택된 삭제·고정·alias·bound·정확 signed power-of-two domination은 independent verifier가 exact Fraction/원본 계수로 별도 증명했다. full LP feasible set, 정수 domain, 네 목적, Runtime/WAN/서비스/carryout/rack/GPU/gang/CC4/grid를 보존했다. accepted witness 왕복 차이와 네 목적 차이는 0이고 전체 원본 행 최대 잔차 5.97575355e-7은 원래 numerical authority 안이다. 15개 physical fixture 및 22개 adversarial family PASS. 일반 affine/global rank/추가 semantic 제거 중 증명하지 못한 항목은 UNKNOWN으로 유지했다. 행렬이 작다는 이유만으로 선택하지 않았다.

각 arm 1회·최대300초·동일 accepted-start P1 진단의 native runtime은 126.074→80.557초(36.1034% 감소), sampled peak RSS는 18,364,227,584→16,940,888,064 bytes(7.7506% 감소)였다. 두 root LP는 interrupted였고 full four-pass 개발 비교는 실행하지 않았다. presolved nnz는 A2SC가 0.0468% 더 크다. 이 결과로 fresh 전체 A1 속도 개선이나 one-hour solvability를 주장하지 않는다.

최종 압축 authority 파일 SHA `b474eade1a5feb3e9d07c91d0649dd585b6cb72b51e34beafb4cdd24169a1389`. Phase-I implementation commit `0e66018480491f6c2c08e24d2249562a64af2a90`; production frozen implementation `b99f2778e47f8bfee22b4eb54f14af8eb9a2e3d1`, source digest `8c1173caca09b9c32707b9f8a4ff38e4998ffb90926dd7f22595e24ea58b28eb`. 이후 evidence-only commit은 frozen source bytes를 바꾸지 않는다. Git 저장 bytes와 manifest SHA의 독립 비교도 PASS이다.

기존 32개 캠페인 checkpoint와 31개 날짜를 읽기 전용으로 감사했다. 완료 payload가 없거나 현재 PR134 original source/model/input/Runtime/CC4/C0/C1/grid/objective/checker 동등성 증거가 부족해 proven-compatible completed 날짜는 **0일**이다. Git SHA 차이 하나만으로 판단하지 않았다. 재실행 계획 **31일**이며 기존 결과·partial incumbent/bound/clock/lock/start는 가져오지 않았다. DATE_REUSE_AUDIT.csv 및 ALL_EXISTING_DATE_REUSE_CASES.json에 날짜별 원인을 보존했다.

| 캠페인 항목 | 현재 |
|---|---|
| run | `B1_PR134_SC_202505_20261006T183422_4fb25507` |
| PASS / timeout / FAIL | 1 / 0 / 0 |
| pending | 30 |
| 현재 날짜/단계 | 2025-05-02 / A1 |
| proven infeasible | 0; 단일 solver status를 증명으로 사용하지 않음 |
| 구현·수치·Fresh 실패 | 최종 날짜 상태 및 repair CSV에 개별 분류; 아직 월 전체 결과 없음 |
| 해결/미해결 | 현재 오류 ledger 참고; 최종 repair 감사 pending |
| 31일 first pass / repair queue 완료 | 둘 다 미완료 |
| Actual 재최적화 / P/Q repair | 0 / 0 |
| memory guard / 감속 / parameter sweep | false / false / false |

May01 production static compressed matrix는 Phase-I 선택 matrix와 byte SHA가 동일하다. 31일 original R0와 현재 frozen Runtime/CC4/C0/C1/grid 입력은 준비 및 SHA audit PASS. accepted PR134 controls를 쓰는 별도 fixed replay fixture는 Actual 재최적화 없이 Fresh 96/96 수렴·물리위반0을 확인했다. 이는 production 날짜 재사용이나 warm start가 아니다. 12개 focused infrastructure regression PASS이며 검사 중 native optimization은 0회다.

coordinator·worker·monitor의 PID/생성시각/명령과 `svchost→services→wininit` 소유 계통을 확인했다. CPU Normal, MemoryPriority5, execution-speed throttling false, PT0S, logon 복구와 독립1시간 watchdog을 검증했다. Codex 앱 종료 실험 자체를 했다고 주장하지 않는다. 모니터 `http://127.0.0.1:8791/`는 현재 run을 1초마다 읽으며 실제 solver 보고 age를 별도로 보여준다. memory/commit 정보는 관찰용이다. 중복될 수 있는 예전 logon task는 정의를 보존하고 Disabled로 전환했다.

각 날짜는 네 원래 목적에 합계3600 native초를 공유한다. 타임아웃·수치·Fresh·검증 실패는 원본 증거와 repair queue를 보존하고 다음 독립 날짜로 이동한다. 인프라 재시도는 최대2회이며 중단 A1은 partial resume 없이0초로 시작한다. 모든 날짜 시도 후 safe 인프라 복구 이외의 미해결 과학·수치 결함은 정확 진단이 필요하다. 예산 확대·과학적 parameter 변경·결과 수정으로 PASS를 만들지 않는다. OS finalizer는 31일 실제 결과를 해당 docs namespace에 후속 commit/push하고 PASS/timeout/unresolved를 분리한다.

Draft PR [#163](https://github.com/BeaverVillage/MobileESS/pull/163). 최종 commit은 이 보고서와 SHA manifest를 담은 evidence commit이며, 별도 frozen production SHA를 위에 명시했다. 최종 월 감사는 아직 생성되지 않았다.

현재 완료 날짜의 5개 causal receipt·모든 payload SHA를 다시 감사했다. INITIAL_COMPLETED_DATE_AUDIT.json에 원시 native UB/LB/gap/runtime과 Fresh 요약을 보존했다.

2025-05-01: 전체5단계 PASS, native 합계 308.110초, Fresh 96/96, Actual 최대 선로 부하율 69.0820%, voltage/current/transformer current/kVA 위반 모두0. 이는 새 production 날짜의 실제 측정이며 paired fresh 원본 대비 속도 개선을 뜻하지 않는다.

추가 immutable dependency pin audit PASS: 외부 참조·최상위 과학 모듈 339개 파일의 SHA를 확인했다. 초기 manifest를 별도 보존했고 code/model/input bytes, solver 설정, run/stage identity와 native clock/start는 바꾸지 않았다. DEPENDENCY_CLOSURE_AUDIT.json을 참고한다.
