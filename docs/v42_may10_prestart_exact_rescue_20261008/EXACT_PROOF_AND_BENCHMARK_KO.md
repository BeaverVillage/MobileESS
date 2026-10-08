# May10 PRESTART exact 보존 증명과 사전 실험 계획

기준은 로컬 exact HEAD `1b891dbe5b1dd454d89b657efec7cba469c0cf94`이다. 기존 PR181 게시본을 덮어쓰지 않는다. 기존 실행 소스 798개를 바이트 대조하고 checkout의 줄바꿈이 다른 18개 파일은 새 worktree에만 기존 실행 바이트로 복사했다. 원래 worktree에는 쓰지 않았다.

## 원본과 compact의 정수 동치성

전체 575개 class, 3,156개 원래 작업의 migration-zero block을 실제 원래 타입으로 독립 rebuild했다. 원래 물리 행 prefix와 저장된 PRESTART native matrix/bounds/type/sense/RHS, 네 목적 계수 및 상수가 일치해야 통과한다. 원본 fingerprint는 `84f517309ddaa693f4c1f582f9a490dbc8a33c42ec0fa74c98d4678004ed4178`이다. 선행 P1/Migration/Shift의 optimize 호출은 없다.

독립적으로 재구성한 원본 SHIFT lock은 비음수 계수 `a_j`와 비음수 하한의 합 `sum(a_j*x_j)=74`이다. 정수 또는 binary 열은 `x_j <= floor(74/a_j)`를 만족한다. 연속 열은 정수화하지 않는다. 실제로 498,121개 upper bound를 이 논리적 함의로 강화했고, 원래 하한 0과 증명된 상한 0인 74,761개 열만 제거했다. 원래 가능한 시작을 경험적으로 제외하지 않는다.

Forward는 증명된 zero 좌표가 정확히 0인 원본 점에서 retained 좌표를 선택한다. Inverse는 제거 좌표에 정확한 0을 삽입한다. 나머지 bounds/type과 모든 목적 계수/상수는 그대로 매핑한다. 원본의 물리적인 유효 정수 스케줄은 SHIFT 함의를 만족하므로 Forward가 존재한다. Compact의 점을 Inverse하면 삭제된 열이 0이고 원본 SHIFT와 retained 행을 만족한다. 삭제 행은 정확하게 자명한 zero row 또는 계수·sense·RHS가 모두 동일한 retained witness row이므로 원래 행도 만족한다. 따라서 정수 feasible schedules와 네 objective가 양방향으로 보존된다.

실제 원본 UB60은 반올림/클리핑 없이 forward/inverse 바이트 동치와 원본 physical replay, 원본 lock, 작업별 objective 재계산을 통과했다. 모델은 740,149행 / 893,243열 / 63,388,855nnz에서 551,780행 / 818,482열 / 58,088,865nnz로 줄었다. Rebuild/독립 검증은 622.775초이며 native optimize 0회이다. 이는 모델 축소 증거이며 성능 성공 판정은 별도 측정한다.

## 유효 부등식

Time-window/shift relocation 후보는 원본 cardinality 행과 전체 합법 STAY 선택을 독립 대조한다. 기준 사이트에 머무는 선택은 window 자원을 최소 g만큼 쓰거나 SHIFT를 최소 delta만큼 쓰고, 나머지는 relocation이다. 따라서 `relocation >= N-floor(C/g)-floor(74/delta)`가 유효하다. 다른 변수는 원본 box의 정확한 rational 최소 기여량으로 처리한다. 실제 444 histogram / 975 threshold 검토에서 양의 신규 부등식은 0개였다. 실패한 GPU-only 후보의 receipt와 snapshot을 보존했다. 이 후보의 효과를 주장하지 않는다.

SHIFT 정수 cover는 원본 SHIFT 행에서 계수 `a_j>=d`인 비음수 정수 좌표 집합 S에 대해 `d*sum(S x_j)<=74`를 이용한다. `sum(S x_j)`가 정수이므로 `sum(S x_j)<=floor(74/d)`이다. 다른 모든 원본 항의 비음수성을 실제 계수와 하한으로 확인한다. 연속적인 finish/occupation lane은 S에 포함하지 않는다. 사전에 정한 d=2,3,4,5,8,16,25,38의 8개 cover만 추가한다. 소규모 원래 정수 스케줄과 연속 잔여 lane을 전수 검증하고 실제 source SHIFT objective와 lock 행을 대조했다.

별도의 `PRE>=2` 행은 기존 전체 영역 native global bound의 재사용이다. 기존 원본 compiled model과 전체 class/open-branch authority를 대조했다. 이 행으로 LP bound가 2가 되더라도 새 하한 발견으로 보고하지 않는다. 추가 행을 모두 포함한 B2는 551,789행 / 818,482열 / 63,620,861nnz다. Cover의 비용과 root/global bound 개선은 실제 측정한다. 압축의 nnz 절감이 dense cover에 의해 상쇄되는 한계도 숨기지 않는다.

Cutoff는 원래 전체 정수 영역을 `PRE<=59`와 `PRE>=60`으로 나눈다. 기존 검증 UB60을 외부 witness로 보존한다. 하위 query의 검증 LB와 보완 영역 LB60의 최솟값만 전체 영역 LB로 사용한다. 하위 query의 완전한 INFEASIBLE 증거가 있으면 전체 LB60이다. TIME_LIMIT이나 제한 후보/부분 LP infeasibility는 전체 infeasibility 또는 OPTIMAL이 아니다.

## 사전에 고정할 유한 실험

| case | 목적 | 최대 native 초 | Presolve |
|---|---|---:|---:|
| B0_SOURCE_LP | 원래 lock 모델의 누락된 raw LP X/Pi/RC 진단 | 90 | -1 |
| B1_COMPACT_LP | 압축 LP 대조 | 90 | -1 |
| B2_CUTS_LP | 압축+cover+기존 LB2 LP 대조 | 90 | -1 |
| B1_COMPACT_MIP | 압축 단독, 기존 알고리즘 | 480 | -1 |
| B2_CUTS_MIP | cut와 conservative presolve의 명시적인 결합 후보 | 2100 | 1 |
| B3_CUTOFF_MIP | B2와 PRE<=59 전체 정수 partition | 660 | 1 |

합계 예정 3,510초, reserve 90초다. 새 날짜별 native 누적 상한은 3,600초이며 모든 실제 Runtime을 합산한다. 이전 3,623.408초 receipt/예산은 별도로 불변 보존한다. Native TimeLimit의 실제 overshoot도 원시 receipt로 보고한다. 원래 UB60을 동일하게 warm start로 제공하되 cutoff에서는 유효할 때만 제공한다. 전체 검증 gap<=0.5%면 남은 case를 실행하지 않는다. 사후 parameter sweep이나 동일 case 재실행은 없다. 오래된 B0 MIP는 원시 baseline을 사용하며 재실행하지 않는다.

Threads=1, 동시 native 1개, Method=2, NodeMethod=1, MIPFocus=3, Crossover=-1과 원래 seed/cuts/heuristics/수치 허용오차를 유지한다. Presolve=1은 별도 algorithmic 후보이며 B1과 B2 MIP 비교에서 cut 효과와 설정 효과를 분리해 단독 인과효과를 주장할 수 없다. [Gurobi 공식 parameter 문서](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html)는 Presolve=1을 conservative 설정으로 정의한다.

MemLimit/SoftMemLimit는 무한대다. RSS는 관측만 하며 메모리 사용량에 따른 종료/제한/스로틀은 없다. 각 native case는 predeclared matrix fingerprint/algorithm/source SHA/순서/새 budget 불변 검사를 통과해야 호출된다. 실제 compiled matrix/attrs/네 목적 출처를 기록하고 native Runtime/Work/raw point와 log를 보존한다. 개선 UB는 원본 전체 query, original physics 및 작업별 objective를 독립 검증한 것만 채택한다.

## May12 보호 gate 해제 경위

대규모 신규 실행은 기존 May12가 살아 있는 동안 시작 gate로 보류했다. 대상 PID76188은 외부 조작 없이 자연 종료했고 기존 실행 session exit0을 읽기만 했다. 기존 결과는 `INCONCLUSIVE`, `PRIOR_WITNESS_FROZEN_ARTIFICIAL_WEIGHT_OR_SIGN_DRIFT`다. 이 작업은 May12를 종료/중단/재시작/수정하지 않는다. 선행 root-cause 문서의 RESOURCE_ISOLATION_PENDING은 초기 상태이며, 자연 종료 후 새 독립 namespace에서만 대규모 rebuild와 제한 benchmark를 수행한다.

준비 중 발견한 cutoff sense 연결 오류는 native 호출 전에 수정하고 전용 테스트를 추가했다. 실패한 준비 log도 새 static namespace에 보존했다. 실패한 scientific 후보를 통과로 표시하지 않는다.

첫 source epoch의 LP 두 호출은 기존 stress guard에서 `STRESS_DATE_OPTIMIZATION_NOT_AUTHORIZED`로 거부되어 실제 native Runtime/Work가 모두 0이었다. 세 번째 모델 준비 도중 새 May10 프로세스만 식별해 중단했다. 두 거부 receipt, 원래 ledger/source freeze와 원래 실행 소스 archive를 보존했다. 예산과 모델/설정/사전 순서는 바꾸지 않았다. 새 May10/PRESTART의 정확한 model 객체·compiled receipt·source freeze·budget/Threads/no-RAM-limit에 한정하는 ContextVar 권한을 기존 backstop에 연결했다. May12 및 P1/Planning/Actual/Fresh AC는 이 권한으로 실행할 수 없다. Guard 연결·복사된 다른 model·다른 날짜·production action 거부 테스트를 포함해 374개 A-stage 테스트가 통과한 후 source epoch 2를 고정한다. 두 pre-solver 거부는 실제 optimize 실행 횟수와 분리해 보고한다.
