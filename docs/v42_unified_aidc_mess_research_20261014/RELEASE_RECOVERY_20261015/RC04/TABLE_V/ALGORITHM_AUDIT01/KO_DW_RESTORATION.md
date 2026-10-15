# AIDC DW/Phase I/P1 pricing/Integer Recovery 복원 소스 감사

판정: **기존 알고리즘 소스는 존재하며 재사용 가능하다. 현재 Table V D0 E1 실행에는 그 경로가 연결되지 않았다.** D0/E1/현재 Source·Case에 대한 adapter와 독립 동등성 검증이 먼저 필요하다. 이 감사는 파일·Git·PR 읽기와 보고서 작성만 수행했으며, 새 Native·모델 build·presolve·IIS·테스트·Actual 실행 및 기존 Source 수정은 모두0이다. 진행 중인 EXECUTION02 B1 UB 프로세스는 건드리지 않았다.

## PR별 원본과 실제 기능

| PR | 확인한 최종 commit | 소스와 역할 |
|---|---|---|
| [180](https://github.com/BeaverVillage/MobileESS/pull/180) | `8b90bdda26de480715e243249f62d46ff9bf1a54` | `v42_a_stage_phase1/{core,producer,backend,oracle}.py`, `v42_a_stage_compact_rowgen/{assembly,kernel,rowgen,lift}.py`, `v42_a_stage_canary/{phase,pricing,integer}.py`. Global elastic Phase I, 전체 원본 local native LP block pricing, 원본 행 분리, SUM/perspective+physical columns, exact LB, 원래 N integer lanes 복원과 UB 검증. May19 과거 결과이며 D0 E1 수치로 이전할 수 없다. |
| [186](https://github.com/BeaverVillage/MobileESS/pull/186) | `9a1b41260aff3bc70d2e36d7e1c293c03ea114de` | 핵심 수정 commit `8806e48d1072e3ad7c11a7fb1d280ac5bfb84929`. `canary.phase.activate`의 artificial-free P1 원점 inclusion을 분리하고, `may12_rescue.activation.batch_graphs` 및 `may12_rescue.contract.decide`의 P1-only 수용 경로 추가. Phi>0에서 frozen artificial weight/sign 검증을 보존한다. 과거 May12의130class/점/dual/예산은 현재 권위가 아니다. |
| [191](https://github.com/BeaverVillage/MobileESS/pull/191) | `40b6f94dcd80e470f93c73b7479fdd2d9d91c3f2` | `v42_may_build_v6/a_stage.py` 기존 fresh-date adapter와 `v42_b3_joint/a_source.py:ASourceBridge` A1/A2/current fixed-MESS 연결, SourceRegistry·단계별 ledger·독립 저장증거 재검산. V6 파일은 `0f3da66e6edadc45f75d55011affcd3d2ec6954d`에서 생성되어 PR191의 `66f15fcb8c2ac3b1714fb5920af4aa4b7024ed77`에서 B3 연결. PR191 자체 실제 FULL/Native는 NOT_RUN이므로 소스 구현과 실측 인증을 구분한다. |

현재 Git에서 위 세 commit 객체와 실제 diff를 확인했다. `v42_may_build_v6/a_stage.py`, `canary/phase.py`, `phase1/producer.py`, `native90/a_routing.py`는 PR191 commit과 현재 HEAD 사이 내용 차이가 없다. 현재 `b3_joint/a_source.py`는 이후 state-I/O 재사용·독립 재검증 경로 및 anytime FULL/gap 구분 등의 후속 변경이 있으므로 PR191 exact source와 혼동하지 않는다.

## 이미 있는 fresh-date/P1-only 경로

1. `v42_may_build_v6/a_stage.py:111 _prepare(request,progress)`가 현재 날짜 NATIVE_INPUT/WINDOWS를 읽고 fresh DATA를 만든다. 286행 부근에서 inherited canary prepare의 `OUT/STATIC/DAYS/PRODUCTION/load_frozen/load_physical_cache/required_supports/bind/build`를 별도 namespace로 route한다. `DayDirectory`, `InputDirectory`, `rebound/group`은 `v42_may_campaign_native90/a_routing.py`에 있다. **과거 May19 OUT·날짜가 여기서는 이미 우회되어 있다.**
2. `a_stage.py:61 _scientific_active_graph`가 작은 engineering seed 하나를 full-domain fixed constant로 잘못 접지 않게 보호한다. `verify_case:324`는 현재 jobs/classes/domains/complete oracle roster/cache SHA·GPU tail axes를 독립 검증한다.
3. `a_stage.py:425 _native`는 `v42_a_stage_acceptance.native.Native.solve`를 그대로 사용하면서 Source/output/day와 측정 Native account를 route한다. `P1_COMPONENTS`는 PHASE_I/ORIGINAL_P1/LOCAL_PRICING/INTEGER_CONTROL뿐이다. `_NativeBudget:388`은 중복 Runtime charge를 거부한다. **만료된28800초 wall budget이나 P2 자동 실행은 이 adapter의 결함이 아니다.**
4. `a_stage.py:584 run` → `:610–617`에서 complete pricing/targeted HISTORY를 현재 output으로 route → `v42_may_phase_v4.phase.routed_group`의 frozen Phase-I weights → `canary.phase.run` → exact full-domain LP LB/closure 보존 → `:632 restore_types` → `INTEGER_CONTROL`. `may12_rescue.contract.decide`의 과거130class 상수도 `dated_acceptance`가 실제 현재 class 수로 교체한다.
5. `v42_b3_joint/a_source.py:406 ASourceBridge._configure`는 위 V6를 A1/A2로 연결한다. `_binding:236`은 current coefficients와 A2 fixed M1의 전체 P/Q를 original grid에 주입한다. `_physical:321`은 literal 날짜/Stage와 original physical checker를 route한다. `execute:523` 및 `_recorded_pricing:594`는 저장된 모든 current original matrix/dual/local cache/원본 정수점으로 LB·UB·물리 증거를 독립 재검산한다. 기존 adapter를 우선 재사용할 정확한 출발점이다.

## 지금 Table V가 다른 알고리즘을 실행하는 정확한 이유

`v42_integration/table_v_a.py:62 execute_current_a`는 `build_flex_native_model:103` 후 `budget.solve(...ORIGINAL_P1...):153`에서 전체 정수 F2-CRA 모델을 단일 호출한다. `bound:158`은 그 MILP의 `ObjBound`다. V6 `run`, Phase I, complete local pricing, CG support activation, separate DW/LP LB, integer recovery를 호출하지 않는다. `accept_current_a:16`도 current FULL point와 native matrix gap을 받으며 complete pricing closure를 입력받지 않는다.

따라서 현재 실행을 **기존 DW LB + UB-MILP 복원 완료**라고 부를 수 없다. 현재 UB/Native bound/raw는 실행한 알고리즘의 증거로 보존하고, 없는 DW LB/closure를0이나 과거값으로 채우지 않아야 한다.

## D0 E1에 필요한 adapter 범위

| 연결 지점 | 현재 구체 차이 | 필요한 최소 검증/연결 |
|---|---|---|
| fresh DATA 입력 | V6 `_prepare`는 original `data_module.prepare()/load_native()`를 호출한다. 현재 승인 D0 data는 `table_v_flex_planning.compile_flex_descriptors` + `a_engine.authorized_data`가 만든 별도 tuple이다. | 기존 V6 routing 방식으로 승인 D0 E1 jobs/bounds/resources/raw/receipts/classes를 주입하고 reloaded bundle,1624공개Known/1555positive+69physical holds, 미래Unknown UID0 및 Source/input SHA를 exact 검증. 원래 issuer를 다시 돌려 D0가 아닌 D-1 객체를 만들면 안 된다. |
| grid/CC4/Runtime | PR191 `_binding`은 원본 compact grid를 route하지만 D0 current-hard Runtime 중복 제거, 현재 initial/fixed GPU·D0 issue는 새 context에 있다. | current `D0PlanningGridContext.bind`와 native24→D0slot0·96slot CC4 Q50/CDF/shortfall 및 전체 C1/all-phase/transformer rows를 그대로 base/global snapshot으로 유지. A1OFF/A2accepted-current-M1도 exact. |
| Runtime finish aux | `v42_root/native.py:116–122`는 authority가 old V2일 때만 direct finish sum. E1 authority에서는 units 뒤 `finish_count`열/`exact_Runtime_finish_count`행이 추가된다. `snapshot.capture` unit ownership에는 없고 `phase1.producer.row_partition:114–117`은 모든 local열 owner를 요구한다. | 실제 class-owned equality auxiliary로 분리/조립하거나 이미 있는 `runtime_projection.finish_count` exact substitution을 별도 동등성 증거로 검증. authority 문자열을 거짓 V2로 바꾸지 않는다. 현재 D0 matrix로 재현 build는 하지 않았다. |
| receipt/class 및 seed | `authorized_data` grouping은 UID/receiptSHA를 제외하지만 `prepare_fast_active:341–344` literal job 비교는 receiptSHA까지 포함한다. Full `authorized_data` graph를 원래 seed로 넣으면 `active.py:350`이 모든 STAY를 mandatory로 받아 작은 RMP가 되지 않는다. | UID별 receipt 권위를 보존하고 물리·hard window·Runtime가 정확히 같은 class임을 검증. full domain과 작은 engineering seed/inactive pool을 분리하되 후보 삭제0. 기존 `_scientific_active_graph` singleton 보호 유지. |
| D0 independent replay/export | V6 `_planning:555`의 known_GPU는 selected positive-service만 더한다. D0 expired69/187GPU fixed-current hold가 별도다. 과거 `exact.validation.check`의 Runtime-reserve replay도 current-hard target 보정 전 의미다. | 기존 original FULL rows/types/Option/WAN/grid checks는 보존하며 D0의 fixed occupancy/adjusted runtime-reserve 의미를 exact 대조. 현재 `d0_a_planning._export_d0_point:403`은 fixed GPU+selected,69hold 및1624roster를 이미 검증하므로 그 계약을 보존한다. Physical currentGPU와 nominal completion 혼동 금지. |
| budget/source guards | V6 budget protocol은 `native_used/native_optimize/check/wall/cost`이고 TableV는 현재 arm/stage ledger다. 이미 `StageSolveBridge`가 일부 Native route를 제공한다. | 기존 TableV stage account/잔여시간에 facade만 연결. PhaseI/master/localpricing/UB 모두 같은 A1/A2 누적5400Native, 중복charge/reset0, P2=0, serial heavy guard/최신 수치정책 유지. 새 Native 원장으로 이전 비용 삭제 금지. |
| current receipt | PR191 SourceRegistry/StageRequest authority와 current TableV context/acceptance schema가 다르다. | current Source·Case·Stage·physical-domain·MESSanchor·original full-point SHA + current complete roster/dual/globalbox/LB certificate를 서로 exact bind. Current D0 planning/Actual export는 adapter 결과로 검증. 과거 May19/May12 numeric·class·bound·clock 이전0. |

위 연결은 **기존 알고리즘의 입력/namespace/Source/예산/검증 adapter** 범위다. 새 pricing 목적, 새 컷, relaxation, Source 권한, GPU/Runtime/CC4/전압 한계 변경을 요구하지 않는다. 구현·fixture·Native0 동등성 확인 전 대형 Solver를 재실행해서는 안 된다.

## 권고 순서와 인증 경계

1. additive adapter로 기존 V6/PR191 경로를 명시 사용하고 위 입력·ownership·Source 차이의 작은 fixture/정적 동등성부터 확인한다. 이 감사에서는 실행하지 않았다.
2. Root가 별도로 승인한 Native0 준비에서 original global/local matrix projection·모든 domain class/UID·Source/QoS·fixed current GPU·현재 MESS·행/box/objective exact 동등성을 먼저 입증한다.
3. 그 뒤 승인된 serial stage budget에서만 Phase I→Phi0 원본 artificial-free replay→P1 full pricing→integer recovery를 실행한다. 모든 local oracle/minimum/globalbox 증거가 있어야 LB로 인정한다. RMP objective·미완료 pricing·finite path scan만으로 Global LB를 주장하지 않는다.
4. 기존 monolithic UB 실행과 원시 증거는 보존한다. 동일 immutable math/domain/source가 독립 확인되는 경우에만 별도 DW LB와 UB를 비교한다. 알고리즘 복원 자체가 infeasibility 해소나 성능 PASS를 보장하지 않는다.

현재 상태: **SOURCE_REUSE_AVAILABLE / D0_E1_ADAPTER_NOT_CONNECTED / D0_DW_LB_NOT_RUN / CURRENT_UB_PRESERVED / P2=0**.

앞서 `DW_SOURCE_AUDIT01`의 bare-canary 날짜·만료예산·P2 분석은 예비 조사로 보존한다. 최종 복원 판단에서는 이를 기존 V6/PR191 adapter에 이미 해결된 engineering 문제로 명확히 정정하며, bare canary를 처음부터 재개발해야 한다는 뜻으로 사용하지 않는다.
