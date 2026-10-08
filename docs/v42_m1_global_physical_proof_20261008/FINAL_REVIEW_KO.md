# M1 전역 가능성 검증 결과

판정: **INCONCLUSIVE**. `rho_max ≤ 0.60`인 원본 정수 운전계획의 존재 여부는 이번 증거로 확정하지 못했다. **NOT_PROVEN**을 유지한다.

기존 Global LB **0.5687116104049206**, UB **0.6284141956452488**에서 LB **0.5687116104049206**, UB **0.6284141956452488**로 비교한다. Gap은 **9.500515051069%**, 목표는 **0.5%**이며 **M1_ACCEPTED=false**다. production·P2·downstream 실행은 모두 0회다.

## 원본 모델 동결과 증거 범위

PR #188 exact HEAD `4b19e85089171729a3225529a40cb00bf31f43d5`에서 D:의 독립 worktree로 시작했다. 원본 C3A의 582,808행, 306,040열, 5,351,612개 비영 계수와 9,322개 binary를 보존했다. 4대 MESS, 24개 서비스 지점, 96개 15분 슬롯 및 기존 B2 651행도 유지했다. 목적함수는 원래의 `min rho_max`, ObjCon은 +0이다. Objective SHA256은 `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`다.

원본 계수·bounds·types·변수축, frozen A1, Route Table, 교통 ML authority를 exact HEAD의 Git blob과 SHA256으로 대조했다. 기존 UB의 C3A·B2·원본 inverse Route/SOC/PCS/PQ/Grid/A1 replay는 작성기와 독립 checker에서 모두 PASS다. 원본 cutoff 진단 모델에는 `rho_cutoff_0p60` 한 행만 추가했다. 원본 binary와 경로·시점·차량 선택 영역은 그대로 유지했다.

ROOT 및 PR167·169·179·182·187·188의 저장된 계통 행·primal·dual·RC 증거를 재사용했다. 지시의 과거 시작점은 95개 활성 thermal 행이었지만, 현재 저장된 thermal descriptor는 101개이고 B2의 활성 행 목록은 100개다. 실제 source census를 기준으로 분석했고 전압·변압기 제약도 함께 검토했다. 과거의 특정 fractional point가 물리적으로 위반됐다는 사실을 전역 불가능성 증명으로 사용하지 않았다. 기존 증거와 다른 A/M 작업·프로세스는 보존했다.

## A: 계통 요구량과 차량 지원능력

선택한 방향 `B2_ACTIVE_ALL_SECURITY`의 필요조건은 `weighted support ≥ D(3/5)`이며, **D=0.0130951605623203**다. 원본 부등식의 sign cone에 맞는 비음수 multiplier를 사용하고, 모든 grid binding 등식을 affine RHS까지 정확히 소거했다. Frozen grid/AIDC 상수도 포함했다. 원시 Pi를 유효한 dual certificate라고 가정하지 않았다. Binary64 원본 계수의 dyadic 값과 유리수 `3/5`로 exact 연산하고, 표시값은 outward rounding했다.

차량별 analytical 상한은 원본 96슬롯 경로, 이동·연결 준비 시간, 이동 중 P/Q=0, PCS 및 charge/discharge mode를 반영한다. Terminal energy 등식에 `SOC66 ≤ 1080`, terminal SOC `760`을 적용하면 차량마다 suffix `E[66,96) ≤ 320 kWh`가 된다. 이를 더한 **ΣU=0.0445024823893487**이며 **D−ΣU=-0.0314073218270283**다. SOC suffix는 이전 route/terminal 상한을 합계 **0.1756313703726912**, 약 **79.8%** 줄였지만 양의 모순은 성립하지 않았다. 그 밖의 모든 중간 SOC 조건까지 풀어서 얻은 상한이라고 주장하지 않는다.

선택한 scalar 방향의 한계는 별도의 exact 하한 witness로 확인했다. 4개의 독립 차량 물리 모델에서 정확히 가능한 지원량의 합계는 **0.0342492521133151**로, D보다 **0.0211540915509947** 크다. 따라서 이 방향의 Method A에서 각 차량의 진짜 최대 지원량을 완벽히 계산하더라도 `Σmax ≥ 이 하한 > D`가 된다. 같은 가중치와 독립 차량 capacity 합계만으로는 불가능성 모순을 만들 수 없다.

이 witness는 각 차량이 초기 위치에서 96슬롯 정차하는 계획이다. 0–65슬롯의 충전은 원본 에너지 계수로 계산한 exact rational 약 16.11685 kW, 66–95슬롯의 방전은 32 kW이며 |Q|는 최대 392 kvar다. SOC는 760에서 약 1012.63158까지 증가한 뒤 정확히 760으로 돌아온다. 모든 원본 차량 물리 제약과 B2 행을 exact rational로 검사했고, 별도 checker가 frozen inverse를 복원해 원본 FULL 물리 제약과 binary STAY arc도 다시 검증했다.

**이 4개 witness는 독립 private physics capacity 하한이다. 차량 간 coupled grid 제약을 만족하는 전역 운전계획이라는 주장이나 `rho_max ≤ 0.60`의 feasible counterexample 주장은 아니다.**

| MESS | 엄밀 DP 상한 U | Exact 차량 물리 하한 | Native status | 수치 incumbent support | 수치 MIP 상한 |
|---|---:|---:|---:|---:|---:|
| MESS01 | 0.0111256205973372 | 0.0092480606957998 | 2 | 0.01110839971157867 | 0.01112531752790385 |
| MESS02 | 0.0111256205973372 | 0.0093879810692216 | 2 | 0.011117210729453651 | 0.011125545856680392 |
| MESS03 | 0.0111256205973372 | 0.0078038826029501 | 2 | 0.011110529670901738 | 0.01112531752790385 |
| MESS04 | 0.0111256205973372 | 0.0078093277453436 | 2 | 0.011086947275713209 | 0.011125317527903845 |

차량별 native 진단 모델에는 해당 차량의 모든 원본 physical 행·bounds·정수 선택, 96슬롯 SOC·PCS 및 B2 행을 유지했다. Maximize의 incumbent는 지원능력 상한이 아니다. Native ObjBound도 독립 exact search-tree 증명이 없으므로 A3에 채택하지 않았다. 위 U는 별도 checker가 PCS polygon vertex, 모든 DAG edge potential, 원본 에너지 등식으로 검증한 analytical 상한이다. Native incumbent의 tolerance 기반 replay와 exact rational feasible witness를 구분했고, 차량별 capacity gap은 `VEHICLE_CAPACITY_GAP_DIAGNOSIS.json`에 기록했다.

## B: 여러 시점의 Route/SOC 충돌

원본 시간 확장 그래프의 53,626개 arc, 즉 이동 51,322개와 STAY 2,304개, 24개 지점 및 4개 초기 위치를 검사했다. 양의 지원 요구는 66행이고 critical 시점은 31개다. 단일 시점 모순은 0건, 두 시점 465개 조합에서 모순은 0건이다. 4대의 상호 대체 가능성을 포함해 계산했다.

별도 unit-multiplier 필요량은 **2.902806598708**, SOC를 완화한 route 상한은 **20.068034065763**다. 이 가중치의 스케일은 A와 달라 숫자를 직접 비교하지 않는다. 실제 도달이 불가능한 site 쌍은 있지만, 전체 4대가 모든 요구를 만족할 수 없다는 전역 모순은 증명하지 못했다. 특정 reward 최대 경로의 SOC 실패도 그 경로의 진단에 한정된다. F⊆R, PCS의 보수적 처리, transit P/Q=0, 두 시점 reachability는 독립 checker가 검증했다.

## C: 원본 Cutoff MILP 교차검증

단일 full-domain cutoff native 결과는 status **9**, SolCount **0**, NodeCount **1.0**, Runtime **1180.036000s**, Work **2621.129171038**다. 독립 분류는 **NOT_PROVEN**이며, 마지막 callback의 unexplored-node 관측값은 **0.0**다.

NodeCount와 callback의 open-node 관측은 solver의 처리 상태다. 이것만으로 원본 전체 정수 영역을 종결했다고 판단하지 않는다. Gurobi callback은 모든 실제 분기 변수의 목록을 제공하지 않으므로 그 목록과 미해결 정수 영역의 크기는 미측정으로 기록했다. 미완료 상태에서는 배제되지 않은 원본 cutoff 정수 영역이 남는다. 원본 9,322개 binary와 모든 차량 결합을 유지한 결과이며, 미처리 영역을 임의로 제외하거나 정수 영역을 축소하지 않았다.

TIME_LIMIT/no incumbent는 불가능성 증명이 아니다. INFEASIBLE이라는 수치 MIP 판정도 독립 exact 모순과 구분한다. Native RHS의 binary64(0.6)는 exact `3/5`보다 `1/45035996273704960` 작다. 이 미세하게 더 좁은 cutoff만으로 exact decimal 경계의 불가능성을 주장하지 않는다. 원시 상태·로그·trajectory·replay는 `ORIGINAL_CUTOFF_RESULT.json`과 관련 저장 파일에 보존했다.

## 수치 인증 손실과 구조적 완화

현재 known UB/LB gap은 **9.500515051069%**다. 원본 정수 최적값과 UB의 최적성이 아직 확정되지 않았으므로, 이 gap 전체를 진정한 integrality gap이라고 단정하지 않는다. 기존 UB에서 목표 0.5%를 만족하려면 LB **0.6252721246670225**가 필요하고, 현재 값에서 추가 상승량은 **0.0565605142621020**다.

저장된 B2 native LP 목적 진단값은 0.5687138902579907이다. Sign projection의 exact LB는 0.5659508784310822이며, 원본 binding 등식 4,500개의 multiplier repair 이후 exact LB는 0.5667436728775703이다. Native 값과 repair certificate의 진단 차이 0.001970217380420358가 남는다. 이는 목표에 필요한 LB 상승 0.05656051426210196의 약 3.48%다. Native LP 값 자체는 exact optimum이나 검증된 UB가 아니다. 따라서 관측된 인증 손실을 해소하는 것만으로 목표를 채운다는 근거는 없다.

기존 ROOT native 목적값 0.568711942993466과 inherited Global LB의 차이 약 3.33e−7은 서로 다른 authority 범위의 비교다. 같은 ROOT point에 대한 독립 exact certificate의 측정된 인증 손실이 아니다. Inherited Global LB는 기존 원본 native MILP bound 계약을 보존한 값이며 이번 작업에서 새 exact rational ROOT bound로 재분류하지 않았다.

B2 저장 LP에는 8,019개 분수 binary와 140,264개 분수 continuous route flow가 있었다. 이전 단일 mode/location 분기 이후에도 135,444–140,095개 분수 route flow가 남았고, 수천 개의 P/Q·SOC·경로 좌표를 다시 배분했다. 두 sibling pair의 인증된 전역 LB 상승은 0이었다. Native sibling 최소값의 진단 상승도 약 9.31e−8과 5.30e−6에 머물렀다. Child certificate의 finite-bound 손실과 Q 기여는 floating diagnostic이며 exact loss proof로 취급하지 않았다. 출처 SHA와 수치·구조 구분은 `GAP_ROOT_CAUSE_AUDIT.json`에 정리했다.

새 A/B certificate는 dyadic source와 exact rational 연산으로 상수·계수·row sign cone을 검사했다. D−ΣU의 부호도 exact로 판정했다. 또한 독립 exact 차량 하한이 D를 넘으므로 선택된 A 방향의 실패는 표시 rounding이나 남은 SOC 상한의 느슨함만으로 설명할 수 없다.

다음에 먼저 해결할 병목은 **66–95 critical 구간에서 4대 전체의 location/mode/PQ 선택을 함께 포괄하는 multi-time cover**다. 서로 다른 line/time 요구를 하나의 scalar 합으로 합치면 상호 충돌이 상쇄될 수 있다. 이번에 확인한 방향의 한계와 원본 native search의 미완료를 구분한다. 추가 실험은 이번 예산에서 자동 실행하지 않고, 실패한 방법을 production으로 승격하지 않는다.

## 실행 예산과 재현

신규 native 호출은 **5회**, 누적 Runtime은 **1213.109000s / 3,600s**, Work는 **2676.808747701**다. 원본 cutoff 최대 1,200s, 차량별 최대 600s를 지켰다. 등록한 TimeLimit은 cutoff 1,180s와 차량별 575s이며 시간 예산 reserve를 사용했다. Threads=1/worker, 차량 동시 worker 최대 2개다.

CPU·RSS·Native Runtime·Work·Controller Wall을 분리해 기록했다. MemLimit/SoftMemLimit과 RAM 기반 자동 중단은 추가하지 않았다. A/B 작성기와 독립 checker의 native optimize 호출은 0회다. RSS는 주기적으로 관측한 최대값이며 process lifetime의 실제 최고치와 같다고 주장하지 않는다. 전체 수치는 `NATIVE_RUNTIME_LEDGER.json`에 있다.

원본 모델·cutoff·계통 capacity·temporal·차량·exact local witness를 각각 독립 checker가 검증했다. 저장된 증거만 재검사하는 명령은 다음과 같다. 소비된 ONCE token을 삭제하거나 native cutoff/vehicle 실험을 재실행하지 않는다.

```text
python -m v42_global_proof.check_source_cutoff
python -m v42_global_proof.check_grid_capacity
python -m v42_global_proof.check_temporal
python -m v42_global_proof.check_vehicles
python -m v42_global_proof.check_local_exact_witness
```

## Git 및 v42 후속 기준

검증된 신규 M 변경을 먼저 commit하고 PR188 exact HEAD 위의 stacked Draft PR로 게시한다. 이후 origin/v42의 `V42_INTEGRATION_READY.json`과 최종 HEAD를 확인한다. 준비 완료 시 별도 임시 worktree에서 신규 namespace 변경만 반영하고, A/M 통합 회귀가 모두 PASS이며 충돌이 없을 때만 fast-forward push한다. 미준비·충돌·검증 미통과 상태에서는 M HEAD·파일·결과·적용 방법을 handoff 문서에 남긴다. Force merge/push와 실패 방법의 production 승격은 하지 않는다. 이후 개발 기준은 단일 v42이며, 실제 Git·통합 상태는 handoff와 최종 대화에 기록한다.
