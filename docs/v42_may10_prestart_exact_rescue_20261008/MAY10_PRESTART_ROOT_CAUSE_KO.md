# May10 PRESTART 근본 원인 분석

분석 기준은 최신 로컬 소스 `1b891dbe5b1dd454d89b657efec7cba469c0cf94`와 완료된 May10 PRESTART 원시 receipt이다. 기존 PR181 게시 HEAD는 `0cc77b3…`이다. 기존 worktree와 산출물은 읽기만 하며, 새 대규모 optimize는 아직 실행하지 않았다.

## 확정된 비용 분해

| 항목 | 원시 측정 |
|---|---:|
| 원본 PRESTART rows / cols / nnz | 740,149 / 893,243 / 63,388,855 |
| continuous / integer / binary | 39,709 / 853,534 / 207,106 |
| 목적계수 1인 열 | 763,771 |
| 첫 presolve | 8.20초 |
| 첫 presolve 이후 rows / cols / nnz | 35,593 / 803,528 / 4,372,408 |
| 첫 presolve 이후 integer / binary | 799,976 / 432,248 |
| 두 번째 presolve | 1,960.33초 |
| 두 번째 presolve 제거 rows / cols | 10,615 / 4,320 |
| Root LP rows / cols / nnz | 24,791 / 798,900 / 3,839,424 |
| 완료된 root relaxation | objective 0, 71,811 iterations, 19.54초, Work 28.00 |
| root factor nnz / 로그 memory 추정 | 3,431,000 / 360 MB |
| 최종 B&B nodes / simplex iterations | 30 / 130,407 |
| PRESTART 실제 native Runtime / Work | 3,016.664초 / 2,046.083839 |
| solver 내부 callback 시간 | 240.86초 |
| 최종 native status | TIME_LIMIT (9), OPTIMAL 아님 |
| 최종 global LB / validated UB / gap | 2 / 60 / 96.6667% |

위 값의 로그 line과 receipt SHA256은 `BASELINE_LOG_SUMMARY.json` 및 `SAVED_BASELINE_SMALL_EVIDENCE_MANIFEST.json`에 연결한다. Root relaxation의 objective 0과 최종 전체 B&B bound 2는 다른 값이다.

## 우선순위 1: 두 번째 MIP presolve의 비용 대비 열 감소가 작다

두 번째 presolve는 PRESTART native 시간의 약 65.0%를 사용했다. 첫 presolve 이후 열 중 약 0.54%만 추가 제거했다. 따라서 원본 74만 행을 줄이는 첫 presolve보다, 거의 80만 개의 정수 시작 선택 열과 coupling/lock/cut을 다루는 추가 MIP presolve가 직접적인 시간 병목이다.

첫 presolve가 이미 행을 약 95.2% 제거했으므로 C1의 원본 중복 행 제거만으로 1,960초 병목을 해결한다고 주장할 수 없다. C2는 SHIFT=74에서 논리적으로 불가능한 정수 시작 선택과 count upper bound를 solver에 제출하기 전에 제거·강화하는 것이 우선이다. 열별 증명과 실제 감소량 검증이 필요하다.

특정 histogram/weighted-CG cut이나 presolve 내부 알고리즘을 단독 원인으로 확정할 instrumentation/동일 조건 ablation은 현재 없다. 기존 cut과 lock은 유효성 receipt를 보존하고, 개선 비교에서 별도로 측정한다.

## 우선순위 2: root bound 0과 정수 incumbent 사이의 차이가 크다

원래 목적에 대한 root LP는 실제로 objective 0까지 완료됐다. 첫 root MIP 행의 fractional integer infeasibility count는 753이며, 최종 검증된 정수 schedule의 PRESTART는 60이다. 이는 해당 relaxation의 bound가 incumbent에 비해 약하다는 증거다.

LB=2만으로 최적 정수값이나 정확한 integrality gap을 알 수는 없다. 30개 처리 node와 남은 open nodes를 포함한 최종 native global bound가 2라는 뜻이다. 미해결 탐색 영역은 infeasible로 표시하지 않는다. Bound trajectory와 integer incumbent 개선을 구분한다.

원시 root X/Pi/RC 및 class별 분수 선택은 기존 실행에 저장되지 않았다. 최종 raw X는 정수 incumbent이며 root point를 대신하지 못한다. 따라서 class별 LP relocation 구성, GPU/rack/WAN/grid 활성 행, LP와 스케줄의 지배적인 차이는 현재 직접 측정할 수 없다. 필요한 최소 추가 실험은 전체 원본 lock과 강화 행을 유지한 LP relaxation 1회와 raw X/Pi/RC 보존이며, May12 보호 gate 이후에만 수행한다.

## 우선순위 3: incumbent 검증과 탐색 비용

기존 warm start는 PRESTART 2,705였고 16.62초에 처리됐다. 이후 2,703 → 2,655 → … → 62 → 61 → 60으로 개선됐으며, UB60은 원본 physical replay PASS이다. 신규 실험에서는 이미 검증된 UB60을 독립 복원해 warm start로 사용할 수 있다. 이는 하한 개선의 증명이 아니며 baseline과 warm-start 조건 차이를 명시한다.

Callback 240.86초는 native Runtime에 포함돼 있으므로 다시 합산하지 않는다. 독립 physical 검증을 제거해 시간을 줄이는 방법은 채택하지 않는다. 두 번째 presolve가 끝난 뒤 남은 약 1,000초에 root/cut/branch/callback이 모두 포함됐고, 최종 30 nodes만 처리됐다.

## 수치 범위와 확정되지 않은 원인

Matrix 계수 범위는 1e-13…1e2, RHS는 9e-8…1e6, 목적계수는 1이다. Solver가 coefficient-range 경고를 출력했다. 이 범위는 conditioning 점검의 근거지만 실제 condition number나 numeric failure의 증명은 아니다. 기존 native error는 없었고 최종 원본 physical replay는 PASS이다. 작은 계수를 삭제하거나 tolerance를 완화하지 않는다.

Factor memory 360 MB는 solver의 factor 추정치이며 프로세스 peak RSS와 다르다. 메모리 부족이나 RAM 제한이 이번 presolve 병목의 원인이었다고 주장하지 않는다. 신규 MemLimit/SoftMemLimit는 무한대로 유지한다.

## 보존된 예산과 격리

PRESTART 시작 전 native 606.744초, 적용 TimeLimit 2,993.255998초, PRESTART 실제 Runtime 3,016.664초다. 기존 하루 합계는 3,623.408초이며 23.408초 초과분을 보존한다. 이 역사적 budget을 수정하거나 재설정하지 않는다.

May12 보호 대상 PID/생성 시각/executable/cwd/parent chain은 `MAY12_PROTECTED_PROCESS_IDENTITY.json`에 기록했다. May10은 별도 branch/worktree와 static/temp namespace를 사용한다. 현재 대규모 model load 및 native 실험은 `RESOURCE_ISOLATION_PENDING`이며, 코드·수학적 증명·소규모 rational fixture 검증을 먼저 수행한다.

## 우선 구현할 exact 개선

1. SHIFT=74의 비음수 정수 시작 count에 대해 `count <= floor(74 / abs(start-reference_start))`를 증명하고, upper=0인 열을 exact forward/inverse mapping으로 제거한다. 모든 원래 가능한 시작을 임의로 제외하는 방식은 금지한다.
2. 남은 matrix의 동일한 행 및 정확하게 자명한 zero rows만 제거한다. 575개 class coverage와 모든 목적의 coefficient/constant 및 lock을 대조한다.
3. 시작 사이트/시각의 전체 선택 집합과 time-window capacity, shift budget으로부터 필수 relocation 하한을 증명한다. 소규모 전수 검증과 실제 계수 대조가 통과한 cut만 후보에 포함한다.
4. 원본 feasible UB60과 cutoff PRE<=59의 보완 partition을 명시해 전체 영역 bound authority를 검증한다. 제한된 candidate infeasibility 또는 partial LP를 전역 인증으로 승격하지 않는다.

## 신규 고정 실험 측정

최종 신규 raw model/runtime/root/presolve/Work 비교는 FINAL_REVIEW_KO.md 및 NATIVE_LOG_COMPARISON.json에 있다. Source LP는 objective0으로 완료했고 raw X/Pi/RC와 원본 행 잔차 재계산을 통과했다. 분수 original integer 좌표36개는 15 singleton native-flow 클래스와 2 histogram 클래스에 속한다. Global integer 좌표의 분수는 0개다. Histogram 두 개의 SHIFT mass는 30.9739065554 + 39.8167811010이며 모두 기준 사이트 AIDC11/AIDC10에 머무른다. 이는 이 LP point에서 SHIFT74의 약95.66%를 두 분수 histogram이 사용하는 관측이며, 정수 optimum이나 단독 causality 증거는 아니다. 기존 UB60은 relocation60개 중 시간 이동도 있는9개 작업의 총 SHIFT74를 원본 입력 reference로 독립 재구성했다.

압축 단독 auto MIP는 새 UB60 start를 사용했으나 483.047초의 TIME_LIMIT 중 second presolve468.28초를 사용하고 완료된 root 없이 global bound0으로 끝났다. 기존 certified LB2를 그대로 보존했다. 따라서 zero-column/동일 행 축소만으로 두 번째 presolve가 해결된 것이 아니다. Combined B2는 conservative 설정과 cover를 함께 사용하여 first presolve6.45초, second9.39초, root objective2/71.13초/factor360MB로 진입했다. 두 효과를 분리한 MIP ablation은 없다. Root2는 기존 LB2를 재사용한 행이며 새로운 수학적 하한이 아니다. Root cut/branch의 낮은 bound는 전처리와 독립적으로 남는 병목이다.

최종 전체 원본 영역 UB/LB/gap은 60/2/96.666667%이며, 새 native 총 3389.202000초다. Scientific status INCONCLUSIVE, 최종 검토 category PRESTART_COMPRESSION_RUNTIME_IMPROVED. 초기 문서의 RESOURCE_ISOLATION_PENDING은 May12의 자연 종료 후 해제된 역사적 상태이며, 기존 May12는 수정/중단하지 않았다.
