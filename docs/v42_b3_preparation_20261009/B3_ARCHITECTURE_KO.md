# B3(AIDC + MESS) 공동최적화 준비 구현 — 2026-10-09

이 산출물은 **IMPLEMENTATION/PREPARATION**이다. `PRODUCTION_NOT_AUTHORIZED`이며 실제 B3를 풀지 않았다. 모든 시험 bound, 운전 배열, 물리 receipt는 소프트웨어 시험용 `MOCK`이다. 원본 FULL MILP 동치성, 실제 Global Gap, 원본 물리 실행 가능성, 논문 결과를 증명하지 않는다.

작업 위치는 `D:\MobileESS_v42_B3_prep`, 브랜치는 `codex/v42-b3-preparation`, 기준 commit은 `5ab907e384a5384f1505f851385f4953220f6634`이다. 원본 `D:\MobileESS_v42`의 checkout/reset/rebase, 실행 파일, 입력, cache, ledger, monitor/watchdog/scheduler를 수정하지 않았다. 실행 중 상태는 별도 읽기 전용 감사 JSON의 기준/최종 스냅샷을 확인한다. 기록된 PID와 현재 살아 있는 PID는 구분하며, 기존 HOLD나 자연적인 runtime 변경을 본 작업이 만들었다고 주장하지 않는다.

## 구현한 순서와 수용 계약

`A1 → M1 → A2 → M2 → PLANNING_FREEZE → ACTUAL → FRESH_AC → VALIDATION`

| 단계 | 최적화 결정 | 고정 입력 | P1 Global Gap 한도 |
|---|---|---|---|
| A1 | AIDC job 시간·허용 migration·원본 GPU/Rack/WAN/QoS 변수 | 동일 D-1 Authority, MESS 최적화 OFF | 0.5% |
| M1 | MESS 이동·경로·위치·Pch/Pdis·Q·SOC·충전 mode | A1 전체 AIDC 결정과 IT/PCC 전력 | 3% |
| A2 | AIDC 스케줄과 원본 물리 변수 | M1 전체 MESS 운전 결정 | 0.5% |
| M2 | MESS 이동·경로·위치·Pch/Pdis·Q·SOC·충전 mode | A2 전체 AIDC 결정과 IT/PCC 전력 | 3% |

모든 단계의 목적은 `min rho_max`, P2 호출은 0이다. 분수 문자열의 exact LB/UB로 `(UB-LB)/UB`를 검사한다. `LB=UB=0`의 Gap은 0이고, 음수/비유한 bound, LB>UB, 누락 bound, restricted/local/joint bound, 잘못된 stage/고정 입력/결정/원본 모델 SHA는 거부한다. 네 조건부 단계 인증으로 전체 공동 MILP 전역 최적성을 주장할 수 없다.

기존 `v42_unified.policy.Policy`는 모든 단계에 0.5%를 적용하고, `v42_unified.pipeline.require_stage`는 A1 예외 외 P2 인증을 요구한다. 이 공통 수용 함수를 호출하거나 PASS를 강제하지 않고 B3 버전의 독립 계약을 작성했다. B1/B2 실행 허가는 B3 허가가 되지 않는다.

## 데이터 고정과 물리 권한

`Authority`는 날짜, 96 슬롯, PCC 12개/MESS 4개 축, 입력·계통·PCC mapping·원본 물리 domain·forecast/runtime/source SHA를 함께 seal한다. 시각은 timezone-aware이며 한국 시간 기준 D-1 cutoff와 forecast 가용 시각을 검사한다. Actual 미래 관측을 사용했다는 입력은 거부한다. 이 시각/해시 검사는 원본 forecast 파일의 과학적 causality 검증을 대신하지 않는다.

AIDC 결정에는 job actions/unknown-arrival policy, 12×96 IT/PCC P/Q, GPU/Rack/WAN/QoS/runtime 상태 및 전체 변수 JSON이 들어간다. MESS 결정에는 4대 경로, 4×96 위치/Pch/Pdis/Q/이동 에너지, 4×97 SOC, 초기/최종 상태와 전체 movement/charge mode/route/P/Q/SOC 변수 JSON이 들어간다. tuple과 canonical JSON으로 caller의 가변 배열/사전과 분리한다. 배열뿐 아니라 모든 변수·보조 상태가 SHA에 포함된다.

M1/M2가 고정 AIDC를 바꾸거나 A2가 고정 MESS를 바꾸면 FAIL이다. 결정 SHA가 동일해도 다른 날짜·입력·계통·mapping·forecast/runtime Authority는 혼용할 수 없다. 최종 AIDC는 A2, 최종 MESS는 M2이고, 네 단계의 독립 수용 및 세 handoff 일치 후에만 Mock freeze를 만든다. 저장된 freeze는 네 request/result/certificate/physical/native receipt를 포함하며 다시 읽을 때 전체 chain을 재검사한다.

M1의 raw 해는 M2 후보로만 전달된다. A1 조건에서의 M1 물리 receipt는 A2 조건에서 실행 가능함을 증명하지 않는다. 기본 후보의 `eligible=false`, `feasibility_verified=false`이며 실제 원본 재검증 없이 Native warm start로 선택하지 않는다.

IEEE123, 원본 NormalAmps·transformer current·전압·PCS·배터리·교통·차량·charger·Service Boundary·QoS·CC4/runtime 권한은 기존 source에 남겨 둔다. 물리 공식이나 원본 scientific row를 B3에서 다시 계산하지 않는다. 인터페이스 shape 검사는 제약 완전성이나 단위·계통 replay의 증명이 아니다.

## 기존 알고리즘 재사용과 남은 연결

39개 source API의 정확한 AST signature와 25개 source 파일 SHA를 기록했다. 이 API들은 import/실행하지 않았다. `adapters.py`는 pin된 API 목록, 배열 축 permutation, 고정 source payload, 원본 verifier 역할 및 proof binding을 준비한다.

A-stage는 `v42_a_stage_domain_v2.domain.physical_domain/contains`, `v42_a_stage_canary.phase.run/pricing.full_pricing`, `v42_a_stage_practical.integer_model.restore_types`, `v42_a_stage_acceptance.native.Native.solve/physical.Physical.verify`, `v42_pr134_sc.snapshot.certify`와 `v42_may_recovery_v5.a_stage`의 complete-domain/pricing/integer 경로를 재사용할 후보로 확인했다.

M-stage는 `v42_m1_hybrid.blocks/pricing/dw/verify`, `v42_m1_anytime.core/algorithms`, `v42_m1_research.check_lb/check_ub`, 원본 `v42_native.mess.solve/validate`를 연결 대상으로 확인했다. `v42_may_campaign_native90.m_model.build_case`는 same-day payload를 받아 원본 FULL/Compact/C3A를 구성하며, `m_stage.run`은 P1-only 3% hybrid 경로다. May01에 pin된 standalone hybrid `load_case`/runner의 결과나 matrix를 다른 날짜에 전용하지 않는다.

**A2의 실제 모델 연결은 미완료다.** recovery A prepare는 F2-CRA의 MESS OFF 입력을 사용하고 `_planning`은 non-AIDC controls를 거부하며 zero MESS를 출력한다. M1의 고정 운전 packet을 원본 grid row·materializer·physical replay·complete pricing block에 반영하는 B3 경로가 추가로 필요하다. 지금 구현한 것은 immutable fixed packet, family/축 매핑, proof 결속 및 변경 거부이다.

**M2의 실제 모델 연결도 미완료다.** 현재 source builder/runner의 B2/M1 고정 stage, ConstructionDeadline/grid/voltage/native/output provenance를 M2로 일반화해야 한다. A1/A2의 job option·GPU/known_gpu·PCC Q materializer와 same-day 원본 bundle을 원본 권한으로 연결해야 한다. 인터페이스 배열에서 GPU 또는 Q 공식을 임의로 추정하지 않았다. `source_payload_ready_for_native_build=false`이다.

실제 native adapter의 실행은 무조건 거부한다. 기존 lower API invocation은 별도 승인 이후 stage-correct source bridge와 독립 과학적 검증을 완성한 버전에서만 가능하다. 단순 callable placeholder를 실제 실행 구현 완료로 보고하지 않는다.

## Native-only 90분과 실행 차단

각 stage의 독립 Ledger는 5,400초이다. 남은 시간 이월·reset은 없다. stage/Authority/request/fixed input을 Ledger에 먼저 bind하고 다른 입력으로 rebind하거나 비용을 기록한 후 bind할 수 없다. LP/pricing/QCP/MILP 및 실패한 entered-call Runtime이 누적되고, 측정 불가능한 Runtime은 quarantine한다. Presolve/simplex/barrier/B&B는 optimize 내부 Runtime에 포함되는 계약이다. 모델 생성/domain/matrix/인증/Actual/Fresh AC 비용은 wall에만 기록된다. wall 90분 제한, memory 제한, process priority 제한을 도입하지 않았다.

이번 Ledger는 MockClock 및 숫자를 받는 Fake backend로만 확인했다. 실제 모델 객체나 실행 callback을 받지 않는다. Native Runtime의 실제 Gurobi 측정과 기존 source DateBudget bridge는 NOT_RUN/미연결이다. Threads=1, P2=0의 parameter와 계약은 준비했다.

Production guard는 환경변수·module flag·B1/B2 scope와 관계없이 항상 거부한다. `run_production`, `NativeStageAdapter.execute`, `NativeStageBudget.native_optimize`는 이번 작업에서 호출하지 않는다. 첫 실행문이 guard임을 AST로 확인하고 guard 자체의 거부를 시험한다. REAL certificate/physical admission도 거부하여 caller가 flag/SHA를 꾸며 과학 인증을 만들지 못하게 한다.

`verify_preparation.py`는 B3 전용 unittest만 한 프로세스에서 순차 실행한다. Native/OpenDSS/COM/과학 계산 package import firewall과 test 중 process 시작 금지를 적용한다. 전체 pytest, 실제 model build, domain/pricing 재생성, 실제 데이터 대량 loading을 하지 않는다.

## Planning freeze 이후

Mock Actual은 final seal과 모든 결정 SHA를 유지하고 P/Q repair와 full MILP 재최적화를 거부한다. Mock Fresh receipt에는 `OpenDSS_calls=0`, `fresh_AC_executed=false`, `NOT_RUN_MOCK_INTERFACE_ONLY`가 기록된다. `PASS`, 수렴 또는 선로/전압 만족을 꾸미지 않는다.

원본 경로 `v42_native.planning.freeze_day_ahead_plan` 및 `v42_native.actual.run_dday_actual → ActualBackend.fresh_ac → require_fresh_ac`를 source catalog에 준비했다. 실제 realized input, unknown arrival/causal runtime policy, 원본 freeze 권한, Actual 물리 reconstruction, Fresh OpenDSS 연결 및 검증은 실행하지 않았다.

검사 수/결과는 `B3_NATIVE_ZERO_VERIFICATION.json`과 `B3_IMPLEMENTATION_STATUS.json`, 원본 불변성/자원 상태는 `B3_RESOURCE_ISOLATION_AUDIT.json`, 정확한 source SHA는 `B3_SOURCE_SHA_MANIFEST.json`을 따른다. 무거운 미실행 검증은 `B3_PENDING_HEAVY_VALIDATION.md`에 명시했다. **Production ready=false**이다.
