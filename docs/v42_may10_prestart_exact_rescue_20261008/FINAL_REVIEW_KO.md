# May10 PRESTART 최종 검토

최종 검토 classification은 **PRESTART_COMPRESSION_RUNTIME_IMPROVED**이고 scientific status는 **INCONCLUSIVE**이다. 검증된 원본 정수 UB=60, 전체 원본 영역 global LB=2, gap=96.666667%다. Acceptance 기준은 처음부터 0.5%이며, 기존 May10 결과는 그대로 INCONCLUSIVE/UB60/LB2로 보존한다. Runtime 개선 category는 완료된 LP의 비교로 한정하며, 독립 bound-only classification `PRESTART_TRACTABILITY_FAIL`과 구분한다. 시간 개선을 optimality 성공으로 표시하지 않는다.

Raw global bound는 `2.0000000000000275`다. 원래 repository의 integer bound 정책 `ceil(LB-1e-6)`로 재해석했으며, `2.0000000000000275` 같은 부동소수점 잔차를 하한 개선으로 세지 않는다. Raw loop의 strict-float classification `PRESTART_BOUND_IMPROVED_NOT_ACCEPTED`는 원시 evidence로 보존하고 scientific 판정은 독립 재검토했다. Native parameter/허용오차/physics/objective는 바꾸지 않았다.

## 실제 실행과 결과

| case | native status | raw objective | native bound | Runtime s | Work | 실제 rows/cols/nnz | fractional original integer 좌표 |
|---|---:|---:|---:|---:|---:|---|---:|
| B0_SOURCE_LP | 2 | 0.000000 | 0.000000 | 29.931000 | 35.589818 | 740,149/893,243/63,388,855 | 36 |
| B1_COMPACT_LP | 2 | 0.000000 | 0.000000 | 22.633000 | 40.756486 | 551,780/818,482/58,088,865 | 37 |
| B2_CUTS_LP | 9 | N/A | N/A | 90.396000 | 119.316272 | 551,789/818,482/63,620,861 | N/A |
| B1_COMPACT_MIP | 9 | 60.000000 | 0.000000 | 483.047000 | 381.535209 | 551,780/818,482/58,088,865 | N/A |
| B2_CUTS_MIP | 9 | 60.000000 | 2.000000 | 2103.142000 | 4529.754908 | 551,789/818,482/63,620,861 | N/A |
| B3_CUTOFF_MIP | 9 | N/A | 2.000000 | 660.053000 | 1093.593698 | 551,790/818,482/64,316,101 | N/A |

실제 신규 native 최적화는 6회, 누적 Runtime 3389.202000초, Work 6200.546392다. solver 진입 전 guard 거부 2회는 Runtime=Work=0으로 별도 보존했다. 기존 누적 3,623.408001661301초를 수정/초기화하지 않았고, 역사적 실행과 신규 실행의 합계는 7012.610001초다. 새 3,600초 상한 준수 여부는 True다. Presolve/root/search/callback은 native Runtime에 포함하고 중복 합산하지 않는다. 모델 rebuild 622.775초 및 materialization/readback/진단의 별도 wall 비용을 native Runtime과 혼동하지 않는다.

모든 실제 compiled matrix/attrs readback 통과 여부는 True이다. Status9는 TIME_LIMIT이며 OPTIMAL/전체 infeasibility가 아니다. LP의 raw point/dual는 진단 목적이며 정수 스케줄 인증이 아니다. MIP raw objective와 independently restored/physical-validated UB를 구분한다. Call별 full-domain bound audit는 575개 클래스 동치성, 유효 cut, 실제 native 전체 open branch와 cutoff 보완 partition을 연결한다.

## 정확성 및 실제 모델 축소

원본 740,149행 / 893,243열 / 63,388,855nnz를 압축하면 551,780행 / 818,482열 / 58,088,865nnz다. 증명된 zero 열 74,761개와 정확한 중복/자명한 행 188,369개만 제거했다. SHIFT74 함의로 강화한 integer upper bound는 498,121개다. 원본 575클래스/3,156작업, original objective coefficient/constant, continuous lane 타입, rho/MG0/SHIFT74 lock, forward/inverse 및 original physical replay는 모두 대조했다.

엄밀한 동치성 증명·rational 전수 테스트·실제 계수 대조는 `EXACT_PROOF_AND_BENCHMARK_KO.md`, `COMPRESSION_VALIDATION.json`과 `ORIGINAL_REBUILD`를 참조한다. P1·Migration·Shift를 재최적화하지 않았다. 원래 작업별 GPU/rack/WAN/deadline/workload/grid physics는 원본 replay가 authority이며 구현 중 수치 허용오차를 바꾸지 않았다.

## Cut의 효과와 한계

GPU time-window/SHIFT relocation cut은 전체 합법 선택을 포함하여 444개 histogram과 975개 threshold를 대조했으나 positive cut은 0개다. 실패 후보의 full raw receipt와 exact snapshot은 별도 보존했고 이 후보의 효과를 주장하지 않는다. SHIFT integer cover 8개는 d=2,3,4,5,8,16,25,38의 정확한 floor 부등식이다. 연속 lane을 정수화하지 않는다.

기존 전체 영역 LB2로부터 PRE>=2를 추가했다. B2 LP가 2를 보이면 그 자체는 새 하한 발견이 아니다. 강화 후 모델은 551,789행 / 818,482열 / 63,620,861nnz이며 dense cover가 압축의 nnz 절감을 상쇄한다. LP/실제 MIP bound 및 Work를 비교해야 실효성을 판단한다. B1은 기존 auto presolve, B2/B3는 conservative presolve이므로 MIP의 차이를 cut 단독의 효과로 단정하지 않는다. 같은 Presolve=-1의 LP 세 후보는 별도로 비교했다.

PRE<=59는 전체 원본 정수 영역을 보완 PRE>=60과 분할하는 진단이다. 이전 validated UB60은 항상 보존한다. 하위 모델의 partial result를 전체 OPTIMAL이나 infeasibility로 승격하지 않는다. 컷/단축 모델에 제한된 후보만으로 원본 full-domain bound를 만들지 않는다.

## 병목 진단

기존 MIP의 첫 presolve는 8.20초, 두 번째는 1,960.33초로 native의 약 65%를 사용했고, 추가 열 제거는 4,320개/약0.54%에 그쳤다. 완료된 root LP는 objective0, 19.54초/Work28이며 factor estimate360MB다. 최종 30 nodes의 global LB2는 root LP값과 다르고 원래 정수 최적값은 확정하지 못했다. 새 측정의 모든 presolve/root/factor/range-warning 원문은 `NATIVE_LOG_COMPARISON.json`과 case별 SOLVER.log에 저장한다. 특정 cut이나 presolve 내부 routine을 단독 직접 원인으로 확정할 instrumentation은 없다.

새 LP raw X/Pi/RC와 원본 좌표 복원, fractional class/site mass, 활성 coupling 축, row/bound 잔차, 네 affine objective 및 dual-RC replay는 case별 `LP_DIAGNOSTICS.json`에 보존한다. unavailable/partial 자료는 명시하며 근거 없는 integrality-gap 단정은 하지 않는다. 저장된 root LP는 Gurobi 내부 root와 presolve/cut 시점이 다를 수 있다. 시작 선택의 fractional mass는 실제 individual schedule과 구별한다.

Native 실행 중 2초 간격으로 관측한 RSS 최댓값은 16,467,230,720bytes다. 전체 task/build의 정확한 OS peak라고 주장하지 않는다. factor memory는 solver factor 추정으로 RSS와 다르다. Threads=1/동시 native1, MemLimit=SoftMemLimit=inf이며 RSS는 관측만 했다. 메모리 자동 종료/상한/스로틀은 없다. coefficient-range 경고는 conditioning 점검 근거이며 단독 numeric failure 증거가 아니다.

## 격리·보존·재현성

May12 PID76188/creation1791433742.0365353/cwd/부모 관계를 read-only로 식별했다. 대규모 시작 gate를 보류했고 May12는 외부 조작 없이 자연 종료했다. 기존 May12 status는 INCONCLUSIVE, witness-weight/sign-drift 오류다. 종료/중지/재시작/우선순위 변경 및 기존 code/checkpoint/log/cache/static/temp/env 쓰기는 없다. 종료 후 May12 3,599개 파일의 바이트가 그대로인지 재대조했다.

기존 May10 6,281개/694,292,592bytes, 원래 실행 소스 798개 및 원래 input SHA를 마지막에 모두 대조했다. 결과 PASS=True이다. 새 worktree/branch/static/temp에서만 수정·실행했다. 기존 PR181 remote HEAD는 0cc77b3cecf8f46c02fa58633c2ded753aff14c5이며 이 작업은 기존 branch를 push하지 않는다.

실제 native executed source commit은 `dcb082811e9a71b9692ace2068745bcf15f03b11` / epoch2 / 815개 source SHA freeze다. 실패 epoch와 raw receipts도 보존한다. TEST_RESULTS_GUARD_CORRECTION의 374개 A-stage 테스트 PASS 및 실제 575클래스/physical/모델 gate를 함께 사용한다. Native 모델/point와 대형 matrix/context는 독립 static namespace에 보존하고 SHA256 receipt를 Git에 넣는다. `FINAL_NEW_EVIDENCE_SHA256_MANIFEST.json`과 `FINAL_OLD_EVIDENCE_BYTE_PRESERVATION.json`이 새/기존 증거를 연결한다.

## Git 제출

Exact 기반은 `1b891dbe5b1dd454d89b657efec7cba469c0cf94`, 새 branch는 `codex/v42-may10-prestart-exact-rescue-20261008`이다. 기존 PR181 게시본보다 앞선 로컬 source/provenance를 포함해 별도 Draft PR로 제출한다. 최종 HEAD, PR URL, remote와 PR exact HEAD 일치, clean worktree의 최종 receipt는 독립 static의 `FINAL_GIT_DELIVERY_RECEIPT.json`에 기록하고 최종 사용자 보고에 정확한 값을 제공한다. 기존 PR181은 덮어쓰지 않는다.

## 원래 flow의 세부 분수 구조

실제 원본 interface에서 분수 좌표 family 개수는 `{'f0': 34, 'y': 8}`다. 전체 17클래스 중 singleton flow 15클래스와 histogram 2클래스이며, global integer 좌표의 분수는 0개다. 원래 y/start/site/time 선택과 직접 대응하는 coordinate/family는 `LP0_ORIGINAL_FLOW_FAMILY_TIME_SITE_DIAGNOSTICS.json`에 보존했다. GPU coupling equality가 맞는다는 사실은 GPU 수용능력 포화의 증거가 아니다. 실제 box-bound binding을 별도로 집계했다. Rack/grid/deadline별 의미 있는 행 이름은 원래 saved matrix receipt에 없으므로 활성 semantic row 수를 추측해 채우지 않는다. 원본 최종 schedule의 해당 physics 검증은 independent replay PASS로 확인한다.

## 채택과 다음 한 가지 방법

압축 LP는 동일 Method/Presolve에서 29.931000초에서 22.633000초로 24.383% 감소했다. 다만 Work는 35.589818에서 40.756486로 14.517% 증가했다. 단일 완료 LP의 Runtime 실측 개선이며, 일반적인 속도 우위나 normalized work 감소를 입증한 것은 아니다. 압축 단독 auto MIP는 presolve TIME_LIMIT였으므로 실용적인 MIP 해결의 근거로 채택하지 않는다. 원본 integer-domain 동치성을 통과한 compression과 새 run의 conservative presolve는 비용 개선 후보로 보존하되, global gap 미달이면 acceptance solver로 채택하지 않는다. Dense SHIFT cover는 LP crossover 비용을 늘렸고 기존 LB2를 넘는 하한을 독립 증명하지 못했다면 별도 성능 근거 없이 production 기본값으로 채택하지 않는다.

목표 미달 시 다음 한 가지 유망한 방법은 이번 실제 분수 해의 original singleton start/finish flow와 histogram을 대상으로, locked rho/energy 행에서 지지되는 sparse disjunctive cover를 유도하는 것이다. GPU capacity만의 후보는 양의 cut이 없었고 전역 dense SHIFT 행은 비용이 컸으므로, 모든 원래 합법 대안을 포함한 짧은 지지집합과 정확한 rational proof가 우선이다. 아직 구현/효과/전체 bound가 검증된 방법이라고 주장하지 않는다. 이번 작업에서는 추가 native 호출이나 후속 parameter sweep을 실행하지 않고 종료한다.
