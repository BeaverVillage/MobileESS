# B2 — U4 Primal ALNS 600초 × 3 최종 비교

최선 원본 FULL 검증 UB는 **0.5461621302242249**, 우승 후보는 **N1**다. 기존 U4 대비 절대 개선은 **0.129891320241**(19.213173%)이며, 유지한 K48 Global LB **0.46498486997548166** 기준 Global Gap은 **14.86321657%**다. 세 후보는 동일 U4에서 독립 시작했으며 모든 채택값은 원본 FULL Replay PASS를 거쳤다. Actual Fresh AC96는 실행하지 않았으므로 **ACTUAL_NOT_RUN**이다.

## 1. Source와 공정한 시작점

연구 base는 PR215 `6ca7624d7eafd45d5b061ff33e262b0de32bfe8d`이며, 원본 Source18r/PR207은 `497609b46faa14ea7e32a9483a333ab32fd264ef`다. 대상은 IEEE123/B2/2025-05-01이다. PR207의 U4 엔진과 PR207/209/210/211/214/215 및 B1 PR212/213 기존 결과는 보존했다.

|권위|값|
|---|---|
|Case SHA|34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292|
|원본 FULL matrix SHA|0eca025d99a24d2ae91117cdfe3ae48dade189336ada61b3f8234d9bf99f3cec|
|원본 FULL domain SHA|9247e42b8119f60ef149d0963e31dd8a697af5426a5aaeec9450b2a2f246481e|
|동일 초기 point vector SHA|c9d63854a3ec0747a65d2c6724a5d413585f9a4f6754107fc593ba69ea4eda0d|
|동일 초기 point file SHA|2e4407a775ec3b10167baa05fc5aa45c2bcfd0f55ea6c5a0b921311338c1d290|
|초기 FULL 검증 UB|0.6760534504652341|
|Native 병렬성|순차 1 Worker × Threads=1|
|각 후보/총 actual Native 상한|600초 / 1,800초|

N1의 개선점을 N2 또는 N3의 시작점으로 사용하지 않았다. 각 알고리즘은 자신의 새 FULL 검증 개선점만 다음 중심점으로 사용한다. 원본 U4의 FINAL point와 RAW00는 UB가 같지만 일부 Q가 약1e−13 다르고 SHA도 다르다. 이번 동일 초기점은 검증된 FINAL의 `c9d638…`이다.

## 2. 이전 연구와 현재 U4 종료의 의미

PR169/179/183/194의 Model·계수·UB는 다른 Source의 연구 수치다. 이번 Source18r의 초기 UB 또는 후보 해로 재사용하지 않는다. 현재 초기점은 원본 FULL에서 검증된 U4의0.6760534504652341이며 세 후보 모두 그 동일 point/SHA에서 독립 시작한다. K32를 기본 LB 모델로 참조하되 같은 문제 K48의 더 높은 인증 하한0.46498486997548166도 보존하고 새 하한 최적화는 하지 않는다.

|Primary 연구|검증된 관측과 실제 한계|현재 설계 반영|
|---|---|---|
|PR169|차량4대 node/mode 슬롯64..84, 자유 Binary2100, Hamming24, TimeLimit300/Threads1. 실제112.52999997초에서 UB0.6694159238756877→0.6339776033797229, 원본 replay PASS. 모든 이산변수 고정 P/Q 재최적화는0.680초, 개선8.27e−12 수준.|Mode와 실제 이동을 함께 개방할 근거다. 과거21슬롯·radius24는 참고이며 현재 signed grid/ETA/SOC/return 가능성으로 결정한다. 과거 UB를 현재 UB로 옮기지 않는다.|
|PR179|Native control1800.183초에2 nodes, production3603.095초에1 node. Cold child53시도 중52 OPTIMAL, 중앙197.566초/p90275.129초이나 인증하한 상승·exact pruning0. Global gap9.82144% 정체.|새 unrestricted Full B&B를 실행하지 않고 FULL 모든 물리를 유지하는 제한 neighborhood만 비교한다. Restricted BestBound를 Global LB로 사용하지 않는다.|
|PR183|20개 기존 이산배정의 feasible recourse는 median2.002초/p902.231초이고 당시 UB0.6306505800→0.6284141956 개선. 첫 새 master 배정의 recourse120초는 TIME_LIMIT, 유효 분리 cut 미완료로 canary 중단.|기존 가능한 경로의 P/Q와 새 경로의 recourse 난이도를 구분한다. TIME_LIMIT은 infeasibility 증명이 아니다. Raw point와 FULL replay 성공/실패를 모두 보존한다.|
|PR194|초기 stationary 점의 전압 한계 실패와 Seed 예산 소진·복구 누적을 감사했다. May01 저장 시도는 finite-bound exact LB 인증 예외로 IMPLEMENTATION_FAILURE, cumulative Native4538.198초이며 Adaptive에 진입하지 못했다.|이미 검증된 동일 U4 FULL point에서 시작해 Seed/새 LB Solve를 생략한다. 실패·중단도 해당 Ni의 actual Runtime에 누적하고 예산을 재설정하지 않는다. Unbounded helper를 임의 finite로 바꿔 인증을 만들지 않는다.|
|PR207|같은 Source18r FRESH_U4는 요청90초, 실제38.5069999695초, 제한 neighborhood OPTIMAL. 초기 UB와최종 UB가 동일하고0nodes/0simplex, presolve30.18초. Unrestricted Full600은 실제601.896999836초, ROOT528.89초까지 미완료.|U4의 빠른 제한 OPTIMAL은 FULL 전역 최적성이나 이동해 개선 불가능성 증명이 아니다. Mode/route 개방 범위와 signed grid를 확장할 여지가 있으며 실제600초 비교로 판단한다.|
|PR211|K32의0.4812227124583283 integer incumbent는 reduced Grid 해이며 원본 FULL Security 위반이 있었다. K32 LB0.46497617639758426와 추가K48 LB0.46498486997548166는 하한 인증 증거다.|K32 경로/Mode는 선정 진단에만 사용한다. K32 incumbent를 FULL UB 또는새 Global LB로 승격하거나 FULL 가능성 복구용 추가 Heavy Solve를 실행하지 않는다.|
|PR214|SOC32행은 BASE와같은 LP 목적값, 인증 correction 차이2.4e−8 수준. GRID16은 중단되어 효과 미인증. 물리적 강화로 material LB 개선을 입증하지 못했다.|가중치/Root LP/제약 반복 연구를 다시 실행하지 않는다. 현재 비교는 실제 원본 FULL 검증 UB 개선에 집중한다.|
|PR215|Snapshot75/82/94와 compact896B Window[88,96)의 유효 LB는 기존0.46498486997548166보다 약했다. 자유 Window 경계와 외부 시간 완화는 FULL보다 넓은 영역이다.|Snapshot/Window incumbent는 FULL 초기점·UB로 재사용하지 않는다. 이번96슬롯 원본 SOC·경로·전체 Grid를 모두 보존한 Primal neighborhood와 수학적으로 구분한다.|

Source18r U4 실제 log/result/parameter/replay bytes는 원본 Git evidence index 및 중첩 native receipt SHA와 독립 대조하고 historical_primary/PR207에 보존했다. U4의 raw log는 presolve 이후840 Binary와 loaded user MIP start를 보여주며,38.507초 종료의 정확한 제한영역 결과를 뒷받침한다. 이것은 전체 FULL 가능영역의 최적성 인증이 아니다.

원래 v42_common_mess.engine.optimize_case는 U4의 유한 탐색 종료 후 _full_milp_phase fallback으로 이동할 수 있다. 이번 연구 Adapter는 이 fallback을 호출하지 않으며 모든 Native를 N1/N2/N3의 검증된 Restricted Neighborhood로만 실행해야 한다. 원본 모듈은 덮어쓰지 않는다. 기존 U4가 모든 mode0이라고 PR169 이력에서 추정하지 않고 현재 point의 실제 Mode/P/Q/경로를 별도로 진단한다.

요청의 중심 정의는 각 Ni의 실제 Native Runtime 합계600초다. 각 호출의 요청 TimeLimit·실제 Runtime·반환 overhead를 따로 기록하며, 조기 OPTIMAL 호출의 사용하지 않은 요청시간을 Native 사용량으로 차감하지 않는다. 다음 호출은600−누적actual Runtime의 남은 예산에서1초 반환 여유를 두고 TimeLimit을 설정한다. 따라서 조기 종료가 여러 번이면 요청 TimeLimit 합계가600을 넘을 수 있지만 실제 Native 사용량은 리셋되지 않고600초 이내로 관리한다. 실제 Runtime 미확정은 해당 후보 예산을 격리하며 임의0으로 만들지 않는다. 동일 실패 neighborhood 반복·parameter sweep·후보 간 예산 이월은 금지한다. Solver 반환 초과는 숨기거나 Runtime을600으로 잘라내지 않고 실제 초과 여부도 보고한다.

Primary code/result/proof의 exact Git blob OID/SHA256와 원문 사본 목록은 HISTORICAL_PRIMAL_ALNS_AUDIT.json에 있다. 사본 Python을 import/실행하지 않았고, 감사 Native/Gurobi import/모델 생성은0회다.


## 3. 현재 U4의 실제 물리 운전

권위 FINAL point에서 4대 모두 96개 charge_mode가 0이고 Pch/Pdis 및 선택 이동 Arc가 0이었다. 97개 SOC 경계는 모두760kWh다. 따라서 이 초기점은 Q를 사용하는 정지 운전이다. 이는 과거 PR169에서 추정한 현상이 아니라 현재 원본 좌표 복원값의 관측이다.

|차량|초기 위치|Mode=1|Pch/Pdis AC(kWh)|\|Q\| 슬롯 합(kvar)|최대 \|Q\|(kvar)|SOC min/max(kWh)|이동|
|---|---|---|---|---|---|---|---|
|MESS01|STA01|0|0.000/0.000|29796.100|392.314112|760.000/760.000|0|
|MESS02|STA12|0|0.000/0.000|25025.837|392.314112|760.000/760.000|0|
|MESS03|STA08|0|0.000/0.000|25137.538|392.314112|760.000/760.000|0|
|MESS04|STA06|0|0.000/0.000|27091.288|392.314112|760.000/760.000|0|

초기·종단 SOC가 같고 이동·충전이 없는 관측점에서는 원본 에너지 보존과 Pdis≥0가 하루 방전합0을 뜻한다. Mode를 하루 전체에서 선택하는 N1은 이런 초기 패턴에서도 사전 충전과 방전·SOC 복원을 함께 탐색할 수 있다.

## 4. 세 정식화와 원본 FULL 관계

|후보|Mode|Node/경로|다른 차량|Hamming|
|---|---|---|---|---|
|N1|4대 ×96=384 전체 개방|모든 원본 Node·continuous route·alias 고정|4대 P/Q/SOC 연속 재최적화|384, 전체 Mode 변경 허용|
|N2|선택 1대96 전체 개방|선택 차량 실제 경로와 관련 시간 Node 개방|다른 3대 이산 및 continuous route/alias 고정; P/Q/SOC 재최적화|48|
|N3|선택 2대192 전체 개방|두 차량 실제 경로와 관련 시간 Node 공동 개방|다른 2대 이산 및 continuous route/alias 고정; P/Q/SOC 재최적화|96|

모든 후보는 원본 4-MESS·96슬롯 DAG·실제 이동 ETA/에너지·97 SOC·초기/종단 SOC·전후 에너지 보존·충방전 Mode·PCS16·이동 중 P/Q 금지·전체 Thermal/NormalAmps/변압기/전압·SVR11·고정 AIDC Forecast/PCC를 유지한다. 원래 terminal 위치 의미를 바꾸거나 출발점 복귀를 새로 강제하지 않았다. N3는 두 차량의 독립 SOC/PCS를 유지하며 가상 합산 ESS를 만들지 않았다.

원본 FULL은1,130,336행×344,967열이며, Native는 기존 인증된 Dense C3A의715,596행×354,277열·9,322 Binary를 사용한다. 원본과의 변수/행 제거 및 helper lift는 기존 exact Source transport 인증으로 관계를 보존한다. Native에서 추가하는 행은 center를 포함하는 Hamming1행이고, 모든 모델에 원본 RHS/sense/type/objective를 유지한다. 원본 FULL CSR Replay는 Native model과 worker를 종료·해제한 뒤 수행한다.

수학적으로 고정 bound는 원본 box 안에서 현재 FULL 가능점의 좌표에만 설정한다. 모든 free Binary의 중심 Hamming 거리는0이며, `Σ(center=0)x + Σ(center=1)(1−x) ≤ radius`로 중심을 포함한다. unselected 차량 원본 Arc는 고정 retained route/Node 및 정확한 alias만의 함수임을 독립 감사했다. 모든 비route 연속 P/Q/SOC bound는 원본과 같다. 따라서 각 제한영역은 원본 FULL 가능영역의 부분집합이며 중심점은 항상 포함된다. 제한 Solver BestBound는 원본 FULL Global LB가 아니다.

## 5. Signed Grid·시간 결합·유한 적응 정책

원본 U4에서814,560개 Security 행 전체를 검사하고 thermal12/변압기4/NormalAmps2/상한전압4/하한전압4개 최대26 Critical Row를 선택했다. response auxiliary·injection P/Q·고정 보정항·원본 RHS를 정확한 dyadic Fraction으로 제거해 MESS별 Pch/Pdis/Q signed 계수를 복원하고 별도 checker가 원본 NPZ scalar를 직접 대조했다.

|U4 계통 family|최대/활성 원본 행|Asset/Phase|Slot|원본 정규화 잔차|facet loading|
|---|---|---|---|---|---|
|line_thermal_face|line_thermal_face[33,33,15]|line.sw2/A|33|1.998e-15|0.6760534504652361|
|transformer_kVA|transformer_kVA[29,0,1]|transformer.reg1a/A|29|-2.087e-01|0.791315462|
|NormalAmps|NormalAmps[29,transformer.reg1a::a]|transformer.reg1a/a|29|-2.950e-01|0.705043146|
|voltage_upper|voltage_upper[49,412]|svr_sta01_regulated/3|49|1.243e-14|hard 전압 한계 활성|
|voltage_lower|voltage_lower[49,367]|mess_sta06_pcc/3|49|1.388e-16|hard 전압 한계 활성|

변압기/NormalAmps loading은 원본 정격 대비 facet/선형 current 제약의 정규화 잔차에1을 더한 값이며 Actual AC phasor loading이 아니다. 전압은 원본 행의 활성 잔차로 표시한다. 선택한 행별 exact Pch/Pdis/Q 계수·고정항·helper closure는 SIGNED_SELECTION_CONTEXT.json과 독립 source raw packet에 보존했다.

후보 점수는 현재 차량 signed 기여와 원본 PCS16의 exclusive charging/discharging support 차이를 이용하며, actual ETA와 이동에너지로 할인한다. 직접 rho를 제한하는 thermal row를 먼저 정렬하고, 단위가 다른 hard 전압/current row는 signed guard로 기록한다. 단순 절댓값 민감도나 가중치 최적화는 사용하지 않는다. 점수와 DAG witness는96슬롯 SOC/PCS/Grid 가능성을 증명하지 않으며 그 판단은 전체 원본 MILP와 FULL Replay가 수행한다.

출발 후보는 현재 중심 경로의 실제 점유 DAG vertex와 원본 upper>0인 허용 Arc만 사용한다. 사전 충전 source STAY 슬롯·출발·connect ETA·Critical Slot·후속 SOC 복원 시간을 함께 기록한다. 선택 차량 Mode는96슬롯 전부 개방하므로 초기 충전 이력이 없어도 임의 한두 슬롯에 묶이지 않는다.

N2는 초기 순위 MESS02→MESS04→MESS03→MESS01의4개 primary와 각1개 expanded 후보, N3는6개 실제 차량 쌍의 유한 큐다. N2 요청 cap150초, N3 cap200초를 남은 actual 예산으로 줄인다. expanded는 동일 radius48에서 Node 시간 범위만 최대16슬롯 넓히며 radius sweep을 하지 않는다. 동일 center/free set/route fix/radius signature는 Native 없이 건너뛴다. MESS02의 최초 primary가 이미[0,96]이어서 동일 중심의 expanded는 중복이며, 이를 실패한 Native처럼 실행하지 않는다.

새 FULL 개선점을 채택하면 현재 원본 Security814,560행 전체를 다시 검사해 Critical Row·signed score·Node 시간 창을 갱신한다. 초기26행만 재정렬하는 방식으로 끝내지 않는다. 같은 point SHA는 캐시를 재사용하며, 다른 중심은 별도 exact projection/raw/independent audit packet을 생성한다. Native0의 다른 검증 중심 회귀에서는 기존26행 중25개와 다른 새 행을 선택했고 독립 검사 PASS를 받았다. 그 N1 point는 helper 회귀에만 사용했으며 N2/N3 초기 seed로 사용하지 않았다.

## 6. 모든 Native 호출과 UB 궤적

|알고리즘|Iter|후보|중심UB|free B|R|TL(s)|Native(s)|build wall(s)|replay wall(s)|Status|Incumbent|제한Bound|LocalGap(%)|Peak RSS(GiB)|Peak Private(GiB)|
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
|N1|1|N1_ALL96_MODES|0.6760534504652341|384|384|599.000|39.555|24.190|13.749|2|0.5461621302242249|0.5461621302242249|0.0000|1.862|3.712|
|N2|1|N2_MESS02_primary|0.6760534504652341|2331|48|150.000|152.032|17.064|5.345|9|0.6760534504652341|0.29392437281101547|56.5235|2.263|3.330|
|N2|2|N2_MESS04_primary|0.6760534504652341|1824|48|150.000|29.676|16.627|5.386|2|0.6760534504652341|0.6760534504652341|0.0000|2.015|3.056|
|N2|3|N2_MESS03_primary|0.6760534504652341|2256|48|150.000|32.197|17.265|5.293|2|0.6760534504652341|0.6760534504652341|0.0000|2.014|3.055|
|N2|4|N2_MESS01_primary|0.6760534504652341|2319|48|150.000|32.814|16.957|5.291|2|0.6760534504652341|0.6760534504652341|0.0000|2.014|3.055|
|N2|6|N2_MESS04_expanded|0.6760534504652341|2208|48|150.000|31.901|16.849|5.279|2|0.6760534504652341|0.6760534504652341|0.0000|2.015|3.056|
|N2|7|N2_MESS03_expanded|0.6760534504652341|2334|48|150.000|150.191|16.782|5.376|9|0.6760534504652341|0.2939245141946695|56.5235|2.264|3.332|
|N2|8|N2_MESS01_expanded|0.6760534504652341|2328|48|150.000|150.195|17.549|5.277|9|0.6760534504652341|0.2935004851157428|56.5862|2.257|3.326|
|N3|1|N3_MESS02_MESS04|0.6760534504652341|4155|96|200.000|202.750|17.605|5.284|9|0.6760534504652341|0.29252958715867594|56.7298|2.473|3.587|
|N3|2|N3_MESS02_MESS03|0.6760534504652341|4587|96|200.000|200.182|17.875|5.287|9|0.6760534504652341|0.2925184469188785|56.7315|2.475|3.590|
|N3|3|N3_MESS04_MESS03|0.6760534504652341|4080|96|196.068|23.260|17.657|5.313|2|0.6760534504652341|0.6760534504652341|0.0000|2.028|3.068|
|N3|4|N3_MESS02_MESS01|0.6760534504652341|4650|96|172.808|44.270|17.435|5.268|2|0.6760534504652341|0.6760534504652341|0.0000|2.032|3.071|
|N3|5|N3_MESS04_MESS01|0.6760534504652341|4143|96|128.538|128.738|17.785|5.259|9|0.6760534504652341|0.0|100.0000|2.486|3.606|

Status2는 승인한 파라미터에서의 OPTIMAL, Status9는 TIME_LIMIT이다. 표의 Incumbent·제한 Bound·LocalGap은 현재 제한 문제의 값이다. FULL UB는 독립 Replay에서만 채택한다. 미측정 속성은 “—”로 표시한다. build wall은 모델 로드·구성·readback 단계를 포함하며 전체 wall과 임의로 빼서 순수 조립 성능이라고 해석하지 않는다.

|알고리즘|Iter|이전 누적Native(s)|중심FULL UB|종료FULL UB|FULL PASS 수|FULL FAIL 수|
|---|---|---|---|---|---|---|
|N1|1|0.000|0.6760534504652341|0.5461621302242249|2|0|
|N2|1|0.000|0.6760534504652341|0.6760534504652341|1|0|
|N2|2|152.032|0.6760534504652341|0.6760534504652341|1|0|
|N2|3|181.708|0.6760534504652341|0.6760534504652341|1|0|
|N2|4|213.905|0.6760534504652341|0.6760534504652341|1|0|
|N2|6|246.719|0.6760534504652341|0.6760534504652341|1|0|
|N2|7|278.620|0.6760534504652341|0.6760534504652341|1|0|
|N2|8|428.811|0.6760534504652341|0.6760534504652341|1|0|
|N3|1|0.000|0.6760534504652341|0.6760534504652341|1|0|
|N3|2|202.750|0.6760534504652341|0.6760534504652341|1|0|
|N3|3|402.932|0.6760534504652341|0.6760534504652341|1|0|
|N3|4|426.192|0.6760534504652341|0.6760534504652341|1|0|
|N3|5|470.462|0.6760534504652341|0.6760534504652341|1|0|

|알고리즘|Iter|후보|Native 없는 상태|보존 사유|Native calls|
|---|---|---|---|---|---|
|N2|5|N2_MESS02_expanded|SKIPPED_IDENTICAL_NEIGHBORHOOD|—|0|

## 7. 동일 시작점 최종 비교

|항목|Original U4|N1|N2|N3|
|---|---|---|---|---|
|초기 검증 UB|0.6760534504652341|0.6760534504652341|0.6760534504652341|0.6760534504652341|
|최종 검증 UB|0.6760534504652341|0.5461621302242249|0.6760534504652341|0.6760534504652341|
|절대 UB 개선|0.000000000000|0.129891320241|0.000000000000|0.000000000000|
|상대 UB 개선(%)|0.000000|19.213173|0.000000|0.000000|
|첫 개선 Native(s)|—|39.168|—|—|
|최선 확보 Native(s)|역사적 기준|39.168|—|—|
|개선 횟수|0|1|0|0|
|총 Native(s)|38.507 (역사적)|39.555|579.006|599.200|
|전체 알고리즘 Wall(s)|역사적 값, 동일 예산 Wall 비교 아님|86.891|792.419|750.467|
|이동 횟수|0|0|0|0|
|이동에너지(kWh)|0.000000|0.000000|0.000000|0.000000|
|충전 AC(kWh)|0.000000|4976.312412|0.000000|0.000000|
|방전 AC(kWh)|0.000000|4491.121952|0.000000|0.000000|
|SOC min/max(kWh)|760.000000/760.000000|440.000000/1080.000000|760.000000/760.000000|760.000000/760.000000|
|FULL Replay|PASS|PASS|PASS|PASS|
|Global Gap(%)|31.22069421|14.86321657|31.22069421|31.22069421|

첫/최선 확보 시각은 이후 FULL Replay를 통과한 Raw incumbent가 Native callback에서 발견된 누적 시각이다. FULL 검증은 해당 worker 종료 후 수행하므로 callback 시점에 원본 검증이 끝났다는 뜻은 아니다. Original U4는 역사적 실측38.507초로, 이번 각600초 상한과 같은 실제 사용예산이 아니다.

|후보|분류|중단 사유|actual Native(s)|요청 TL 합계(s)|잔여 actual 예산(s)|
|---|---|---|---|---|---|
|N1|UB_GAIN_STRONG|WHOLE_96_SLOT_MODE_MODEL_OPTIMAL_WITH_APPROVED_MIPGAP|39.555|599.000|560.445|
|N2|NO_VALID_IMPROVEMENT|FINITE_NONREPEATING_CANDIDATE_POLICY_EXHAUSTED|579.006|1050.000|20.994|
|N3|NO_VALID_IMPROVEMENT|CUMULATIVE_NATIVE_BUDGET_EXHAUSTED|599.200|897.414|0.800|

## 8. 차량별 물리 운전과 Rebound

### Original U4

|MESS|Mode1|이동|이동kWh|충전ACkWh|방전ACkWh|\|Q\| 슬롯 합|최대 \|Q\||SOC min/max|종단SOC/위치|에너지 최대 잔차kWh|
|---|---|---|---|---|---|---|---|---|---|---|
|MESS01|0|0|0.000000|0.000000|0.000000|29796.100|392.314112|760.000/760.000|760.000/STA01|0.000e+00|
|MESS02|0|0|0.000000|0.000000|0.000000|25025.837|392.314112|760.000/760.000|760.000/STA12|0.000e+00|
|MESS03|0|0|0.000000|0.000000|0.000000|25137.538|392.314112|760.000/760.000|760.000/STA08|0.000e+00|
|MESS04|0|0|0.000000|0.000000|0.000000|27091.288|392.314112|760.000/760.000|760.000/STA06|0.000e+00|

선택 이동 Arc는0개다.

### N1

|MESS|Mode1|이동|이동kWh|충전ACkWh|방전ACkWh|\|Q\| 슬롯 합|최대 \|Q\||SOC min/max|종단SOC/위치|에너지 최대 잔차kWh|
|---|---|---|---|---|---|---|---|---|---|---|
|MESS01|68|0|0.000000|1384.326577|1249.354736|28873.294|392.314112|440.000/1080.000|760.000/STA01|7.816e-14|
|MESS02|71|0|0.000000|939.872701|848.235112|24566.337|392.314112|511.338/1080.000|760.000/STA12|1.030e-13|
|MESS03|74|0|0.000000|1307.784276|1180.275309|24724.361|392.314112|440.000/1080.000|760.000/STA08|1.386e-13|
|MESS04|71|0|0.000000|1344.328858|1213.256794|25287.589|392.314112|440.000/1080.000|760.000/STA06|1.279e-13|

선택 이동 Arc는0개다.

### N2

|MESS|Mode1|이동|이동kWh|충전ACkWh|방전ACkWh|\|Q\| 슬롯 합|최대 \|Q\||SOC min/max|종단SOC/위치|에너지 최대 잔차kWh|
|---|---|---|---|---|---|---|---|---|---|---|
|MESS01|0|0|0.000000|0.000000|0.000000|29796.100|392.314112|760.000/760.000|760.000/STA01|0.000e+00|
|MESS02|0|0|0.000000|0.000000|0.000000|25025.837|392.314112|760.000/760.000|760.000/STA12|0.000e+00|
|MESS03|0|0|0.000000|0.000000|0.000000|25137.538|392.314112|760.000/760.000|760.000/STA08|0.000e+00|
|MESS04|0|0|0.000000|0.000000|0.000000|27091.288|392.314112|760.000/760.000|760.000/STA06|0.000e+00|

선택 이동 Arc는0개다.

### N3

|MESS|Mode1|이동|이동kWh|충전ACkWh|방전ACkWh|\|Q\| 슬롯 합|최대 \|Q\||SOC min/max|종단SOC/위치|에너지 최대 잔차kWh|
|---|---|---|---|---|---|---|---|---|---|---|
|MESS01|0|0|0.000000|0.000000|0.000000|29796.100|392.314112|760.000/760.000|760.000/STA01|0.000e+00|
|MESS02|0|0|0.000000|0.000000|0.000000|25025.837|392.314112|760.000/760.000|760.000/STA12|0.000e+00|
|MESS03|0|0|0.000000|0.000000|0.000000|25137.538|392.314112|760.000/760.000|760.000/STA08|0.000e+00|
|MESS04|0|0|0.000000|0.000000|0.000000|27091.288|392.314112|760.000/760.000|760.000/STA06|0.000e+00|

선택 이동 Arc는0개다.

Mode1은 charge_mode Binary가1인 슬롯 수이며 Pch가 양수인 슬롯 수와 같다고 가정하지 않는다. 실제 충전량은 별도 AC kWh 열로 표시했다. 차량별97개 SOC,96슬롯 Mode/P/Q, 접속/이동 상태와 원본 에너지 보존 잔차를 [operating_plans](operating_plans)에 보존했다. 종단 SOC 복원은 원본760kWh 조건을 유지하며 free boundary, SOC 합산 또는 PCS 확대가 없다. Critical 시점 이후 Rebound를 포함한 모든 슬롯의 실제 충방전과 이동에너지는 [Original_U4_SOURCE96_PLAN.csv](operating_plans/Original_U4_SOURCE96_PLAN.csv), [N1_SOURCE96_PLAN.csv](operating_plans/N1_SOURCE96_PLAN.csv), [N2_SOURCE96_PLAN.csv](operating_plans/N2_SOURCE96_PLAN.csv), [N3_SOURCE96_PLAN.csv](operating_plans/N3_SOURCE96_PLAN.csv)에서 확인하며 DAG 증거로 대체하지 않는다.

|최선 FULL point|원본 최대 thermal facet loading(수치)|Line|Phase|Slot|Facet|
|---|---|---|---|---|---|
|Original U4|0.6760534504652361|line.sw2|A|33|15|
|N1|0.5461621302242252|line.sw1|A|26|1|
|N2|0.6760534504652361|line.sw2|A|33|15|
|N3|0.6760534504652361|line.sw2|A|33|15|

|동일 U4 Critical 행|Slot|Original U4|N1|N2|N3|
|---|---|---|---|---|---|
|line_thermal_face[33,33,15]|33|0.6760534504652362|0.4737931503210028|0.6760534504652362|0.6760534504652362|
|line_thermal_face[70,26,1]|70|0.6760534504652361|0.5265340696581017|0.6760534504652361|0.6760534504652361|
|line_thermal_face[31,26,1]|31|0.6760534504652342|0.5060769536803683|0.6760534504652342|0.6760534504652342|
|line_thermal_face[73,64,15]|73|0.6760534504652342|0.46564058072017106|0.6760534504652342|0.6760534504652342|
|line_thermal_face[29,26,1]|29|0.6760534504652342|0.5422401132604894|0.6760534504652342|0.6760534504652342|
|line_thermal_face[89,64,14]|89|0.6760534504652341|0.46697044451238817|0.6760534504652341|0.6760534504652341|
|line_thermal_face[24,26,1]|24|0.6760534504652342|0.4760664382535413|0.6760534504652342|0.6760534504652342|
|line_thermal_face[32,33,15]|32|0.676053450465234|0.5270619507479699|0.676053450465234|0.676053450465234|
|line_thermal_face[34,33,15]|34|0.6760534504652342|0.5197028342302042|0.6760534504652342|0.6760534504652342|
|line_thermal_face[72,26,1]|72|0.6760534504652342|0.5244964888577966|0.6760534504652342|0.6760534504652342|
|line_thermal_face[83,64,15]|83|0.6760534504652341|0.5461621302242248|0.6760534504652341|0.6760534504652341|
|line_thermal_face[74,64,15]|74|0.676053450465234|0.46563445862062924|0.676053450465234|0.676053450465234|

같은 원본 thermal 행의 값은 fixed Forecast/보정항과 실제 Pch/Pdis/Q 기여를 exact Fraction으로 계산했다. 전체 Grid 최대값은 원본814,560행의 수치 스캔이며 새로운 UB/LB 인증을 대신하지 않는다. 차량별 signed 기여·원본 행 SHA와 새 Critical Row 증거는 ORIGINAL_CRITICAL_GRID_POINT_COMPARISON.json에 보존했다.

## 9. K32 진단과 Global LB

K32 정수 incumbent rho0.4812227124583283은 Reduced Grid 진단점으로만 유지한다. 추가 Native0 스캔에서 thermal3,662행·변압기24행·상한전압222행·하한전압140행이1e−8을 초과했고 NormalAmps 위반은0행이었다. FULL 가능해가 아니므로 UB 또는 새로운 Global LB로 승격하지 않는다. 원본 경로/Mode와 차량별 이동에너지는 U4_K32_SIGNED_DIAGNOSTICS.json에 보존했으며 추가 Heavy 복구 Solve를 실행하지 않았다.

|LB 권위|인증값|이번 처리|
|---|---|---|
|K32 / PR211|0.46497617639758426|기본 LB 모델 유지, 재계산 없음|
|K48 / PR211|0.46498486997548166|같은 Source/Case 더 강한 인증 LB 보존, Global Gap에 사용|
|새 LB optimize|0|제한 ObjBound를 Global LB에 사용하지 않음|

최종 Global Gap=(검증UB−0.46498486997548166)/검증UB=14.86321657%다. 이번 Global LB는 상승하지 않았으며 unrestricted Full global B&B·DW·Pricing·가중치 최적화를 실행하지 않았다.

## 10. Source 버전 사건과 실패 보존·독립 검증

N1 실행 중 준비 파일이 최초 ready 통지 이후 수정된 사실을 발견했다. signed 후보 순위를 혼합 단위 정렬에서 direct-rho-first로 수정한 사건이다. 원본 Source18r, 이미 구성한 N1 Native 모델, 고정/개방 집합, 목적과 파라미터는 변하지 않았고 N1은 변경된 순위 함수를 호출하지 않았다. 정확한 epoch01 파일 bytes와42개 N1 증거 파일을 보존하고 실제384Mode/전체 route 고정의 수학적 제한이 같음을 독립 감사했다. N1 실제 호출과 FULL PASS를 보존했으며 재실행·예산 초기화가 없었다. N2/N3는 새로운 epoch02 Native0·회귀·Source seal 후 각각 원래 U4에서 시작했다.

최초 PCS16 행 이름 가정 실패, alias 회귀 권위 읽기 실패, 목적값 인수 바인딩 실패, 혼합 단위 순위 심사, 버전 사건과 거부된 준비를 연구 디렉터리에 보존했다. 새 epoch02는 구성 전과 Optimize 직전에 실행 코드/정책 SHA를 검사하며 원본 Source 모듈을 덮어쓰지 않았다.

FULL Replay는 원본 CSR/RHS/sense/bounds, 전체96슬롯 경로·ETA·이동에너지, 초기/종단 위치, SOC, Mode, PCS16, 이동 중 P/Q, 모든 Grid, SVR11/AIDC와 objective identity를 검사한다. 원래 검증기의 수치 기준을 유지한다. C3A affine tolerance는1e−8이며, 원본 FULL의 flow·terminal_location·전압·NormalAmps·thermal·변압기 행은1e−8, 기타 행은1e−6이다. bounds/integrality tolerance는1e−8이고 원본 Binary/정수 패턴과 objective transport는 엄격히 일치한다. Raw clipping·rounding·repair 및 새 정확한 유리수 연속 가능성 인증은 없다. 실패 Raw/Replay를 삭제하거나 Solver ObjVal로 FULL 검증을 대체하지 않았다.

## 11. Native 예산·메모리·전체 Wall

실제 Native 로그 환경은 Gurobi13.0.2(build v13.0.2rc1, win64), Windows11+(26200.2), 13th Gen Intel Core i7-13620H의10 physical/16 logical cores다. 매 호출 최대1 thread를 사용했다. 총 RAM은34,049,220,608bytes(약31.71GiB)이며 CPU 사용률 백분율은 계측하지 않았다. 아래 Peak RSS/Private Commit은 메모리 실측이다.

총 actual Native는 **1217.761001초**, 상한은1,800초다. 각 알고리즘의 실제 Runtime을 초기화 없이 누적하며 조기 OPTIMAL에서 쓰지 않은 요청 시간은 소모로 계산하지 않는다. 따라서 요청 TimeLimit 합계2546.414초는 actual 예산보다 클 수 있지만 다음 호출은 잔여actual−1초 이하로 제한한다. 반환 overhead와 TimeLimit overrun을 실측 그대로 보존하며 Runtime을600으로 잘라내지 않는다.

|후보|Peak RSS(GiB)|Peak Private Commit(GiB)|build wall 합계(s)|독립FULL replay wall 합계(s)|
|---|---|---|---|---|
|N1|1.862|3.712|24.190|13.749|
|N2|2.264|3.332|119.093|37.247|
|N3|2.486|3.606|88.358|26.411|

비교 제어기의 두 epoch 전체 wall은3003.002초다. 공유 초기 검증/Native0·N1·버전 복구 중단·epoch02·각 호출 준비와 검증을 포함하며 보고/최종 독립 감사 wall은 별도 계측한다. 최소4GiB RAM Reserve·6GiB Windows Commit Reserve 및 구성 후 예상 성장 여유를 검사했고 매 Native 전/후와 callback 자원 심사를 수행했다. Peak Private Commit과 RSS를 구분하며 Gurobi 내부 MaxMemUsed와 동일한 지표라고 해석하지 않는다.

독립 자원/수치 감사에서 관측한 최소 가용 RAM은12.871GiB, 최소 가용 Windows Commit은22.738GiB다. 13개 Native 로그의 수치 경고는 기존 PR207과 동일한 `Model contains large matrix coefficient range`였으며 추가 수치 경고나 Status12 수치 오류는 관측하지 않았다. 승인 정밀도·NumericFocus3·ScaleFlag2·Seed0를 유지했다. 최대 Native TimeLimit 실측 초과는2.750000초이며 이후 호출에서 실제 소모를 차감해 각600초 한도를 지켰다. 메모리/수치 중단은 없고 전체 Raw FULL 채택은 별도 검증이다.

관측 worktree anchor부터 UTC 2026-10-12T04:30:23.907936+00:00의 post-run timing receipt까지4719.908초였다. 실행 두 epoch의 wall은3003.002초, 세 알고리즘 wall 합은1629.777초다. 초기 setup/history의 독점 소요시간과 사람 메시지 수신 시각은 미계측이며0이라고 간주하지 않는다. 마지막 보고 생성까지의 span은 아래 render timestamp에 별도로 추가했다.

|알고리즘|알고리즘 wall(s)|Native(s)|pre-Optimize build(s)|외부 Optimize return wall(s)|return wall−Runtime(s)|FULL Replay wall(s)|neighborhood prep(s)|
|---|---|---|---|---|---|---|---|
|N1|86.891|39.555|24.190|42.229|2.674|13.749|5.620|
|N2|792.419|579.006|119.093|590.257|11.251|37.247|40.463|
|N3|750.467|599.200|88.358|607.324|8.124|26.411|24.581|

각 component는 포함 관계가 있는 실측 scope다. build/replay/return 값을 알고리즘 wall에 다시 더하지 않으며 동시 준비 작업에 임의의 독점 시간을 배분하지 않는다. 보고 생성과 Git 전달은 timing receipt 이후 단계다.

## 12. 채택 판단과 후속 범위

동일 Source·초기 point와 각600초 상한에서 얻은 최선 FULL 검증 UB로 판단하면 현재 우승 후보는 N1이다. 절대 gain≥0.005는 MATERIAL, ≥0.010는 STRONG이며 분류는 FULL 검증값을 사용한다. N1은 전체96Mode 모델의 정상 OPTIMAL로 조기 종료할 수 있고, N2/N3는 유한한 다른 차량/차량 쌍을 탐색하며 첫 작은 모델 종료만으로 전체 알고리즘을 끝내지 않는다.

실제 호출은 N1 1회, N2 7회, N3 5회다. N2는7개의 서로 다른 모델과 중복1개 skip으로 유한 정책을 소진했고, N3는6개 쌍 중5개 실행 후 actual 예산을 소진했다. N2/N3의 TIME_LIMIT 결과는 더 좋은 경로가 없다는 증명이 아니다. 제한 모델에서 OPTIMAL과 UB0.67605345를 얻은 호출도 그 particular 고정/Hamming 영역의 결과다.

N1은 경로 고정 상태에서 전 차량의 Mode와 연속 에너지를 함께 선택해39.555초에 개선했다. 수천 개 Node/Mode와 실제 경로 선택을 개방한 N2/N3 모델에서는 일부 호출의 제한 Bound가 약0.29에 머물렀고 마지막 N3는0으로 기록되었다. 같은600초 상한에서 incumbent가 개선되지 않은 관측과 함께 제한 탐색의 진행 상태를 보여준다. 정식화 차이를 분리한 인과 실험은 수행하지 않았으므로 그 원인이나 원본 FULL 최적값 및 모든 이동 운전의 한계를 증명하지 않는다.

N1은4대 Mode, N2는1대, N3는2대 Mode를 개방한다. 모든 차량의 연속 P/Q/SOC를 재최적화해도 세 영역은 이동 여부만 다르지 않다. 관측한 우열만으로 이동의 가치가 없거나 시험하지 않은 모든 영역이 개선하지 못한다고 결론내리지 않는다. 후속은 검증된 Mode 활성화 이득을 바탕으로 별도 승인된 실험에서 경로 연동을 평가할 후보이며 이번 Solver 추가 실행이나 U4 생산 엔진 수정은 없다.

이번 결과는 B2 May01 한 날짜의 Planning FULL 연구로, 5월 모든 날짜에 직접 외삽하거나 Production/Actual PASS를 선언하지 않는다. B1 worker·Windows Task·Supervisor·예약을 활성화하지 않았으며 B1 기존 결과와 원본 Source를 보존했다. 공식5월 campaign·B3·IEEE8500·Actual Fresh AC96 실행은0회다. 결과는 후속 방법 선택의 근거이고 기존 campaign HOLD와 예약 비활성 상태를 유지한다.

## 13. 검토 가능한 증거

- [COMPARISON.json](COMPARISON.json)：`1e33ace8f0b66415d0a6cbeb6843f25fa08995b2f4ebd7bb67eefe888d0ccb79`
- [ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json](ORIGINAL_SOURCE_OPERATING_PLAN_COMPARISON.json)：`1483a3f001940204be1bc9ec28749aac164de184ebeb94d5cdb7c64936e8047e`
- [FINAL_INDEPENDENT_UB_CERTIFICATE.json](FINAL_INDEPENDENT_UB_CERTIFICATE.json)：`7847a2b6354432a4476bb1f885bcfcd8fb1986c717bf41c89c08356c3de368d0`
- [POST_RUN_RESOURCE_SOURCE_AUDIT.json](POST_RUN_RESOURCE_SOURCE_AUDIT.json)：`5d6b35389d3291f1bc40fdeb4f86afdbf819cd288d345ba9bf276631b27654d2`
- [INDEPENDENT_FINAL_RESULT_RESOURCE_EPOCH_AUDIT.json](INDEPENDENT_FINAL_RESULT_RESOURCE_EPOCH_AUDIT.json)：`07ac4826a5023b7f2271b0de23eb046c74a09f93d9dbf46314f1dd4b6de40ebc`
- [HISTORICAL_PRIMAL_ALNS_AUDIT.json](HISTORICAL_PRIMAL_ALNS_AUDIT.json)：`bda5cc6fa0ef54908bec47544160b970abecc8f7879ef60791c78295b9d428c6`
- [INITIAL_U4_FULL_REPLAY.json](INITIAL_U4_FULL_REPLAY.json)：`32ab0e9de5bad0c88bea8640716ace06f9b2646cd856de1425c14153f92ec987`
- [U4_K32_SIGNED_DIAGNOSTICS.json](U4_K32_SIGNED_DIAGNOSTICS.json)：`23e2e5a4c389ba6f37caa3438f8f837d82cf0285374f49bde838826b63d2c83b`
- [N1_SOURCE_EPOCH_INCIDENT_INDEPENDENT_REVIEW.json](N1_SOURCE_EPOCH_INCIDENT_INDEPENDENT_REVIEW.json)：`2c7272a4d682e6685a2e89281c06c6c7c8960127de92e5bad461a2cd3be48bfa`
- [N1_PRESERVATION_PRE_RESUME_NATIVE0.json](N1_PRESERVATION_PRE_RESUME_NATIVE0.json)：`56bfc72b0a74f7f92ef0c35c36f9b6629077642d0315d8922e9296311a8f4a34`
- [INDEPENDENT_RESUME_AFTER_N1_REVIEW.json](INDEPENDENT_RESUME_AFTER_N1_REVIEW.json)：`ea176141d741b7e4205a89676b4c07c46e3b9243d5e1131440767de400491b07`
- [ADAPTIVE_CURRENT_GRID_NATIVE0_REGRESSION.json](ADAPTIVE_CURRENT_GRID_NATIVE0_REGRESSION.json)：`0e237efdf96535e0b591a0ce09f3d240d4c3f88c3887af33ac6e76b7dcd21104`
- [FINAL_POST_EPOCH_INDEPENDENT_CERTIFICATE.json](FINAL_POST_EPOCH_INDEPENDENT_CERTIFICATE.json)：`30f8ac2a1f2a38c22c79b28cb45e9714b575cea9e7709e60fefbcecae59d5e1f`
- [INDEPENDENT_NATIVE_RUNTIME_MEMORY_NUMERIC_AUDIT.json](INDEPENDENT_NATIVE_RUNTIME_MEMORY_NUMERIC_AUDIT.json)：`88a4c8b35fa84299127b980c51d4239b6c64f701510e8a5d4b44d82b9684da72`
- [RESEARCH_WALL_CLOCK.json](RESEARCH_WALL_CLOCK.json)：`3cd744981343430c151625f43d3574ab0333bf7969b2566fa420a09da865b104`
- [ORIGINAL_CRITICAL_GRID_POINT_COMPARISON.json](ORIGINAL_CRITICAL_GRID_POINT_COMPARISON.json)：`9b0cc2741034f0750c9ce91aea0408da5fa2a8a1349efe3b06a3e77ce03c8329`

관측 worktree 생성 UTC **2026-10-12T03:11:44Z**부터 보고 생성 UTC **2026-10-12T04:34:29.890848+00:00**까지 **4965.891초**다. 이 span은 setup/history/실패한 준비/N1/pause/회귀/resume/post-Native/보고를 포함하며, worktree 생성 이전 chat 읽기 시간은 미계측이다. 이 생성기의 JSON 읽기·표 생성 wall은0.140179초다.
