# M1 Hamming48 / 600초 최종 검토

HAMMING48_600_PRIMAL_IMPROVEMENT_CONFIRMED. 유효 UB 0.6324498168172089 → 0.6306505800203936; 추가 감소 0.0017992367968152623. 기존 global LB 0.5687116003498334 유지, 새 global gap 9.821441799%.

| 필수 결과 | 값 |
|---|---|
| Old valid UB | 0.6324498168172089 |
| New valid UB | 0.6306505800203936 |
| Absolute improvement | 0.0017992367968152623 |
| Relative improvement | 0.002844868871762641 (0.284486887%) |
| Global gap | 0.09821441798809942 (9.821441799%) |
| Native Runtime(s) | 600.2430000305176 |
| Native Work | 1390.782673909808 |
| Native nodes | 107.0 |
| Native status | 9 / TIME_LIMIT |
| Restricted ObjBound | 0.6249513568059877 |
| Restricted native MIPGap | 0.009037053790106195 |
| Improving incumbents (initial 제외) | 15 |
| MIPSOL events (초기/중복 포함) | 17 |
| Native solution pool count | 10 |
| Best valid-point Hamming | 47 |
| Radius48 boundary active | False |
| Best solver candidate full replay | True |
| Best valid point full replay | True |
| Changed node_activity B | 40 |
| Changed charge_mode B | 7 |
| Changed discrete MESS | MESS02, MESS03, MESS04 |
| Changed discrete slots | [64, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84] |
| Optimize calls | 1 |

| 탐색 | Center UB | 반경 | Native Runtime(s) | Best valid UB | 개선 |
|---|---:|---:|---:|---:|---:|
| Hamming24 | 0.6694159238756877 | 24 | 112.52999997138977 | 0.6339776033797229 | 0.03543832049596485 |
| Hamming48_300 | 0.6339776033797229 | 48 | 300.1989998817444 | 0.6324498168172089 | 0.0015277865625139553 |
| Hamming48_600 | 0.6324498168172089 | 48 | 600.2430000305176 | 0.6306505800203936 | 0.0017992367968152623 |

이번 gain / 직전300초 gain = 1.1776754953614978. 진단: still strong. 각각 새 검증 incumbent로 center를 갱신했으므로 순수한 TimeLimit 인과 비교는 아니다. 실패 또는 작은 개선은 전역 최적성/포화 증명이 아니다. 남은 UB−LB=0.06193897967056028도 증명된 integrality gap이라고 부르지 않는다.

같은600초 실행에서 native_Runtime≤300에 저장된 최선 후보를 별도 original replay로 확인한 checkpoint valid UB=0.6315029472167656. 그 뒤 얻은 추가 valid gain=0.0008523671963719393. 이는 같은 실행의 저장 point 비교이며, 다른600s-run 또는300s로 중단했을 경우의 반사실 solver 결과와 같다고 주장하지 않는다. 추가 optimize0회.

Exact base HEAD는 `bf455bbea26d644d8952d1d2da90f8f645cf0df1`(PR170), scientific authority는 PR162 selected C3A `1d922c91eb27056a5ccc79c92ef18146707099ab`이다. 실행 사전등록 source commit은 `65125393415e065b4df2539f00cdf11531421560`. 중심은 PR170 `docs/v42_m1_hamming48_20261007/BEST_VALID_POINT.npz`의 x, rho=0.6324498168172089, SHA256=f9192e2d6a8eb04b4096f983bdc1abbf65c1abab5613e02cd759713299d5c6cc. Center original C3A/full physical/grid/A1 replay=True; start 제한 model replay=True, H=0, Start 배열 bit-identical, native start 수락=True. Center나 start 수리0.

실제 PR170 실행 source와 저장 restriction을 읽어 free indices/names/순서가 같음을 확인했다. 2100 B=node_activity2016+charge_mode84, MESS01..04, slots64..84, radius48. 밖의 원래7222 B는 새 center로 고정한다. 원래296718 continuous bounds와582808 original rows/objective를 유지하고 Hamming row 하나만 덧붙였다. `sum(center=0: x)+sum(center=1:1−x)≤48`이며 continuous 변수는 Hamming에 세지 않는다.

설정: {'Threads': 1, 'TimeLimit': 600, 'Method': 2, 'NodeMethod': 1, 'Crossover': 2, 'MIPFocus': 3, 'MIPGap': 0.005, 'FeasibilityTol': 1e-08, 'OptimalityTol': 1e-08, 'IntFeasTol': 1e-08, 'Seed': 20260929, 'DegenMoves': 0}. PR170의 모든 effective native params를 비교했고 algorithm 변경은 TimeLimit300→600뿐이다. LogFile 경로는 새 namespace로 변경했다. Thread1, solver13.0.2. Native Runtime은 실제값을 그대로 기록했으며600초로 잘라 쓰지 않았다. Parameters는 solve 전후 동일하다.

Native optimize=1회. Exclusive ONCE token와 guard, 별도 presolve call0, sweep0, 더 큰 radius0, full global B&B0, 추가 수동 LB cut/hull0, formulation/physics/objective/tolerance 변경0. 모든 MIPSOL full C3A point·UTC·discovery wall/native time·Work·rho·Hamming·nodes·restricted bound/gap를 저장했다. 최초 center와 종료시 중복 event를 포함한 event 수와 native pool 수는 정의가 다르다. Native callback 오류=[], solver exception=None.

최선 solver 후보 C3A replay: PASS=True, 행 최대위반=5.798882690110201e-10, bounds 최대위반=2.158078169812345e-10, B integrality 최대위반=0.0. 전체306040 C3A vector를 저장한 뒤 frozen saved inverse로 원래 physical vector를 복원했다.

원래 physical replay=True, grid replay=True, grid checked rows=673920, grid maximum upper=8.525375955483475e-13. Route/SOC/PCS replay=True, exact circle maximum ratio=1.0, movement energy=95.2719047424662 kWh. Frozen A1 DATA/identity hashes를 동일 reader로 확인했다. 원래 B 밖의 고정값은 모두 유지했으며 saved inverse route auxiliary 차이=0.0. C3 raw vector를 수정하거나 candidate 수리를 하지 않았다. Native/C3 tolerance1e−8, 기존 full affine inverse tolerance1e−6, bound/route/grid1e−8, 기존 physical subvalidator1e−5 모두 유지했다.

최선 native 후보가 FAIL이면 그 점은 UB로 배제하고 저장된 다른 improving 점을 objective 순으로 검증한다. 채택 valid point SHA256=32fbc2036ef1fb874097d4dc38623818238510aaffd3b5b58f992e5ce519f2e3. 후보 검증 이력은 CANDIDATE_VALIDATION_HISTORY.json에 있다. Valid improvement가 없으면 baseline UB를 유지한다. 이번 valid full replay=True. Global LB를 변경하지 않았고 restricted ObjBound=0.6249513568059877를 global LB로 사용하지 않았다.

Discrete 변경 unit=['MESS02', 'MESS03', 'MESS04'], slots=[64, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84]. 원래 outside B 변경0. 물리 continuous 변경 unit=['MESS01', 'MESS02', 'MESS03', 'MESS04'], slots=[1, 4, 7, 10, 11, 14, 16, 18, 19, 20, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 46, 56, 58, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95]. STAY 결정 변경=39, MOVE 결정 변경=5; MOVE 개수 4→7, movement kWh 69.03977797111658→95.27190474246622. 원래 route auxiliary의 depart/connect 시각은 binary label 시간과 다를 수 있으며 neighborhood B를 추가로 연 것은 아니다.

충전 활성 event 15→19, 방전 26→30; 활성여부 변경 충전8/방전18개(진단 threshold1e−8 kW). 충전 energy 435.62034393417355→591.4077497661531 kWh, 방전 327.5595713281295→443.23718465866307 kWh. 모든 unit·96 slots Pch/Pdis/Q/SOC와 시작/말기 SOC, route changes는 TRAJECTORY_DIFF.json 및 시간 CSV에 기록했다.

원래 retained thermal rows 324871개를 모두 평가했다. Center-active 개선 상위100, 전체 개선 상위100, center/new 요구rho 각각 상위100 및 PR169 critical descriptors를 합친 272개 row를 CSV에 기록했다. 실제 native branch/time은 frozen row axes로 복구했다.

| Center critical grid row | Slot | C3A row | 요구 rho 감소 |
|---|---:|---:|---:|
| line.sw2::A | 39 | 314388 | 0.09885531465989916 |
| line.l116::A | 70 | 456606 | 0.03330065871022958 |
| line.sw2::A | 32 | 282455 | 0.03191344776629934 |
| line.sw2::A | 33 | 287004 | 0.02735035690932819 |
| line.sw2::A | 27 | 259682 | 0.02308369162465329 |
| line.sw1::A | 90 | 546996 | 0.0203135597761529 |

| Slots64..84 내 critical grid row | Slot | C3A row | 요구 rho 감소 |
|---|---:|---:|---:|
| line.l116::A | 70 | 456606 | 0.03330065871022958 |
| line.sw2::A | 80 | 501860 | 0.01840643821386534 |
| line.sw2::A | 81 | 506405 | 0.018126410841732832 |
| line.l116::A | 72 | 465698 | 0.012717802862453387 |
| line.sw2::A | 70 | 456451 | 0.006545786844613821 |
| line.l116::A | 72 | 465697 | 0.00518818831028367 |

Pch/Pdis/Q의 affine 기여와 grid 개선은 동반 관찰이며 인과 분해가 아니다. 원래 continuous 변수 전체가 자유로우므로 discrete 시간 block 밖의 grid 변화도 가능하다.

다음 행동은 정확히1개: **새 valid UB=0.6306505800203936 중심에서 동일 슬롯/Hamming48/params/600초의 단일 recenter primal 실험을 사전등록할 것. 이 작업에서는 실행하지 않는다.** 이유: Material improvement ΔUB=0.0017992367968152623, 직전300초 gain 대비1.1776754953614978배이다. H=47로 경계와 한 비트 차이이며 TIME_LIMIT로 종료했다. 새 검증 해를 중심으로 같은 제한을 유지한 한 번의 탐색을 추천하지만 local/global 최적성이나 포화를 주장하지 않는다. 실행=False. 이 작업은 여기서 끝나며 다른 solve는 수행하지 않는다.

Draft PR: Draft PR 생성 후 기록

최종40자리 HEAD는 Draft PR 본문의 `Final HEAD`와 사용자 최종 응답에 기록한다. `git rev-parse HEAD`로 확인한다. 동일 commit 파일에 자체 SHA를 넣는 순환을 만들지 않는다. Manifest는 자기 자신과 Python cache를 제외한 namespace 전체 파일의 원본 bytes를 SHA256으로 봉인한다. PR169/170 및 scientific 자료는 기존 hashes와 같아야 하며 최종 작업 트리는 clean이어야 한다.
