# B2 Time-Decomposed Global LB 최종 보고

판정은 **TIME_DECOMPOSITION_NONMATERIAL**이다. 유효한 신규 Solver Global Bound는 확보했으나 기존 대비 개선이 0.001에 미달했다. 최종 Global LB는 **0.46498486997548166**, 동일 원본 U4 UB 대비 Global Gap은 **31.22069421%**다.

3% 목표 판정은 **GLOBAL_GAP_3PCT_NOT_REACHED**다. Snapshot Optimize는 사전등록 순서75→82→94의3회×30초, 사용자가 별도 승인한 Window[88,96)은1회×최대360초다. 전체4회 요청 TimeLimit 합450초, 실제 Native Runtime 합399.039000초이며 원본 Full96 Optimize·B1 실행·공식 캠페인 실행은0회다.

## 1. Source·Case Authority와 결과 계약

|항목|고정 값|
|---|---|
|대상|IEEE123 / B2 / 2025-05-01|
|Source18r PR207|497609b46faa14ea7e32a9483a333ab32fd264ef|
|Critical-Grid CG PR211|d12315a3757aec187c8da0685c28ef901466386a|
|정확한 부모 PR214|40ab888b884255e76fd6c89fd01933570b60c242|
|원본 Case SHA|34c0efffa9c05397552fb167667c0bbfe2f35cec89801a3169c00c64fe77f292|
|기존 인증 Global LB|0.46498486997548166|
|검증 원본 U4 UB|0.6760534504652341|
|3%에 필요한 LB|0.6557718469512771|

새 브랜치는 PR214 정확한 HEAD를 부모로 한다. 기존 Source18r/U4, K48 및 PR207/209/210/211/214·B1 PR212/213 결과와 Native Ledger는 읽기 전용 authority다. 이번 신규 Bound만 동일 Source·날짜의 기존 인증 하한과 max로 결합한다. Snapshot/Window incumbent는 원본 FULL UB나 Actual AC PASS로 승격하지 않는다.

## 2. FULL→Snapshot 포함관계

원본 정수 가능해 x에서 슬롯 t의 원본 STAY arc를 z[m,s,t]로 복사하고, charge_mode·Pch/Pdis/Q·rho_max와 계통 helper 값을 복사한다. 원본 nonnegative Binary unit-flow는 엄격한 시간 DAG의 한 경로이므로 z∈{0,1}, Σ_s z≤1이다. 이동 중이면 모든 STAY가 0이며 원본 접속 gate에 의해 P/Q=0이다. 기존 unused Mode 값은 그대로 허용한다.

위치·Mode·접속 P/Q·PCS16의 원본 저장 행을 STAY→z의 이름 치환만 거쳐 복사했다. 원본 전체 정수 가능해가 해당 슬롯에서 만족하던 모든 Grid 행과 helper 등식도 그대로 만족한다. 96슬롯 Route 연결·이동 가능성·SOC Balance·이동에너지·초기/종단 SOC·시간 간 Rebound 결합은 제거한다. 제거한 결합은 가능영역을 넓히므로 원본 FULL의 슬롯 사영을 제거하지 않는다.

따라서 π_t(F_FULL_integer) ⊆ F_Snapshot_t이고, 동일 rho bound/objective에서 OPT_Snapshot_t ≤ OPT_FULL이다. Window도 원본 FULL→Window 사영 포함관계를 별도 검증한다. 인증 Solver Global Bound가 해당 완화 문제 optimum 이하이므로 Global_LB_new=max(Global_LB_old, Certified_Snapshot_LBs, Certified_Window_LB)는 FULL의 유효한 Global LB다. 서로 다른 슬롯/창의 LB를 합산하지 않는다.

## 3. 4-MESS 즉시 정수 물리

각 MESS에서 원본 실제 접속 위치 24개(IDC01–12, STA01–12)를 전부 유지했다. 각 슬롯은 위치 Binary 96개와 원래 charge_mode Binary 4개, Pch/Pdis/Q 연속변수 288개를 가진다. 원본 Pch/Pdis box는 [0,300], Q box는 [-400,400]이며 원본 저장 gate와 PCS16의 더 강한 접속·Mode 제한을 함께 적용한다.

원본 즉시 행은 위치별 Pch≤300z, Pdis≤300z, -400z≤Q≤400z, Pch≤300d, Pdis≤300(1-d) 및 16개 PCS facet이다. PCS는 원본 저장 sin/cos 계수와 RHS를 그대로 사용하며 작은 계수를 삭제하지 않는다. Σz≤1의 4행을 포함해 즉시 물리 2,116행이다. z를 분수 위치로 허용하는 정수해는 없다. 모든 z=0 상태도 허용한다.

## 4. 해당 슬롯 전체 원본 Grid·Helper 복원

|Security 계열|슬롯별 원본 행|세 슬롯 합계|
|---|---|---|
|voltage_lower|838|2,514|
|voltage_upper|838|2,514|
|NormalAmps|153|459|
|transformer_kVA|2,448|7,344|
|line_thermal_face|4,208|12,624|

슬롯당 Security 8,485행을 전부 보존한다. Forecast/AIDC 고정항, injection P/Q, response line P/Q·transformer P/Q·line correction, 원본 RHS/Sense·rho 계수를 frozen FULL 저장 행에서 복원했다. Voltage는 실제 저장된 injection 직접 연결 행을 사용한다. 존재하지 않는 별도 response_voltage auxiliary를 가정하지 않았다.

원본 injection/response helper에는 고유 +1 pivot 등식이 있고 의존 그래프는 acyclic이다. 모든 저장 binary64를 정확한 Fraction으로 해석하여 helper를 재귀 소거했으며, 소거 후 rho 이외의 모든 leaf는 선택 슬롯의 원본 Pch/Pdis/Q다. 다른 시간 leaf·생략 Grid 행은 0개다. 고정항은 각 원본 등식 RHS에서 정확히 전파했다.

완전 소거 행렬은 슬롯별 약239만 NNZ로500,000 안전 상한을 초과한다. Native는 같은 수학적 영역의 원본 helper extended formulation을 사용한다: 원본 helper 등식1,140행·원본 Security8,485행이며 실제 Grid+helper NNZ는 슬롯75/82/94에서 각각158,068/158,051/158,096이다. Helper에 원본 free bound(-inf,+inf)와 목적계수0을 유지한다. 삼각 등식의 유일한 helper lift를 소거하면 정확히 같은 Fraction 물리 좌표식이 되므로 factoring은 가능영역을 바꾸지 않는다.

Native에는 모든 원본 저장 binary64 coefficient/RHS/Sense를 그대로 복사하므로 변환 오차가 정확히 0이다. Fraction 완전 소거식의 별도 binary64 검산에는 기존 보수적 절차 ceil_binary64(rhs_exact+Σmax((c_native-c_exact)lb,(c_native-c_exact)ub))를 사용했으며, 이 dense outward 식은 증거로만 저장했다. helper bound를 임의 유한화하거나 작은 계수·Security 행을 제거하지 않았다.

## 5. 사전등록 슬롯과 실제 행렬 규모

|Slot (0-based)|PR214 실제 선정 위반 수|최대 Thermal 위반|Rows|Columns|Binary|NNZ|dense 소거 Grid NNZ|
|---|---|---|---|---|---|---|---|
|75|6|0.28770955|11,741|1,529|100|164,884|2,396,484|
|82|3|0.26317533|11,741|1,529|100|164,867|2,396,540|
|94|1|0.28177296|11,741|1,529|100|164,912|2,396,628|

슬롯 75/82/94는 PR214 검증 Fractional BASE point의 실제 Thermal 위반으로 결과 이전에 고정했다. Snapshot 수치를 보고 재선정하지 않았다. 최종 Native 행렬은 Binary≤256, Rows≤30,000, NNZ≤500,000 세 상한을 모두 통과한다. Full96 CSR/model을 구성하지 않고 원본 raw NPZ member를 임시 read-only NPY memmap으로 읽어 필요한 슬롯/helper closure만 추출했다.

## 6. Native Readback·U4 Replay·실행 결과

각 슬롯/Window Native0는 독립 원본 행 재도출·모든 위치/Mode/PCS 대조·FULL 포함관계·원본 U4 사영 Replay를 통과한 뒤 실행했다. 실제 Gurobi Native Readback에서 matrix/RHS/Sense/Bounds/Types/Objective/ObjCon/행·열·Binary·NNZ를 저장 모델과 대조했다. Worker1, Threads1, FeasibilityTol/OptimalityTol/IntFeasTol=1e-8, MIPGap=1e-6이며 Snapshot3회는 TimeLimit30초, 이후 사용자가 승인한 Window1회는 최대360초로 순차 실행했다.

|Slot|Status|Root 완료|Root LP log 값¹|Solver ObjBound|Incumbent ObjVal|MIPGap|NodeCount|
|---|---|---|---|---|---|---|---|
|75|2|PASS|0.41549220|0.41579290|0.41579290|0.00000000|87.00000000|
|82|9|PASS|0.35757270|0.35779883|0.35805773|0.00072307|1101.00000000|
|94|2|PASS|0.28141090|0.28155936|0.28155936|0.00000000|700.00000000|
|Window[88,96)|9|PASS|0.30950700|0.30953111|0.31218312|0.00849506|74.00000000|

¹ Root LP 목적값은 Gurobi log에 반올림 출력된 관측값이다. Root 완료 flag는 root log 또는 실제 OPTIMAL MIPNODE 관측으로만 기록하며, 최종 OPTIMAL 상태만으로 Root 완료를 추정하지 않는다. Presolve 종료는 별도 Root LP 값을 확보했다는 뜻이 아니다. 별도 LP Optimize를 실행하거나 그 log 값을 정확한 LP optimum·독립 Global LB로 승격하지 않았다. ObjBound는 해당 Snapshot/Window MILP의 Solver Global Lower Bound이며 ObjVal은 해당 완화 모델의 incumbent다. 표의 MIPGap은 이 소규모 모델 내부 local Gap으로, 검증된 FULL U4 UB와 인증 Global LB를 사용하는 원본 Global Gap과 다르다.

|Slot|Native model 생성(s)|Native Runtime(s)|Optimize wall(s)|Callback wall(s)|U4 Native0 최대 위반|Native0·Readback·독립 인증|
|---|---|---|---|---|---|---|
|75|0.02000870|2.30600023|4.59609190|1.62838200|0.00000000|PASS/PASS/PASS|
|82|0.01816610|30.00300002|32.03336100|11.24789430|0.00000000|PASS/PASS/PASS|
|94|0.01875440|6.53199983|8.54580130|3.23531160|0.00000000|PASS/PASS/PASS|
|Window[88,96)|0.15171660|360.19799995|362.22682350|110.69976200|0.00000000|PASS/PASS/PASS|

## 7. 신규 Global Bound 독립 인증

|Slot/Window|독립 인증|Certified 모델 LB|기존 LB 대비 Δ|정확한 Snapshot 가능점 상한|Snapshot optimum Material 불가능 조기 증인|
|---|---|---|---|---|---|
|75|PASS|0.41579289927745045|-0.04919197|0.41579289927745045|PASS|
|82|PASS|0.35779883299591836|-0.10718604|미확보|아니오|
|94|PASS|0.28155936106370183|-0.18342551|0.28155936106370216|PASS|
|Window[88,96)|PASS|0.30953110526953526|-0.15545376|미확보|아니오|

인증은 original FULL→Snapshot 포함관계와 원본 저장 계수·Bound 계약, Native readback, 실제 Solver 상태/Global Bound/log, numerical error·resource stop 여부 및 incumbent replay를 독립 확인한다. Global Bound의 계산은 Gurobi 수치 B&B 계약을 사용한다. 전체 B&B 분기마다 exact arithmetic proof를 재구성한 인증이라고 주장하지 않는다. Incumbent/Root log를 Global LB로 대체하지 않는다.

## 8. 시간 결합 완화의 영향과 조기 판정

Snapshot은 각 시간의 네 차량 정수 접속·Mode/PQ/PCS와 전체 Grid를 보존하지만, 그 선택을 다른 시간에 연결하는 경로·SOC·Rebound를 제거했다. 따라서 Snapshot 목적값이 FULL보다 낮을 수 있다. 유효한 Snapshot 정수 가능해 목적값이 기존 LB+0.001 이하이면 해당 Snapshot optimum도 그 이하이며, 그 슬롯 단독 Material 강화가 불가능하다. 이 증인은 Snapshot 상한이며 FULL UB가 아니다.

- Slot 75: 조기 판정 PASS. exact Snapshot 가능점 인증 PASS, 보수적 목적값 상한 0.41579289927745045. 선택 위치/Mode의 정수 pattern을 유지한 power clamp·PCS scale·rho 계산을 거쳐 모든11,741개 행을 정확한 Fraction으로 검사한 증인이다. 상세 rational 값·repair·잔차는 슬롯 INDEPENDENT_CERTIFICATE.json에 보존했다.
- Slot 82: 조기 판정 아니오. exact Snapshot 가능점 인증 아니오, 보수적 목적값 상한 미확보. 정확한 가능점 증인이 미확정이면 incumbent 수치만으로 조기 불가능성을 인증하지 않는다. 상세 rational 값·repair·잔차는 슬롯 INDEPENDENT_CERTIFICATE.json에 보존했다.
- Slot 94: 조기 판정 PASS. exact Snapshot 가능점 인증 PASS, 보수적 목적값 상한 0.28155936106370216. 선택 위치/Mode의 정수 pattern을 유지한 power clamp·PCS scale·rho 계산을 거쳐 모든11,741개 행을 정확한 Fraction으로 검사한 증인이다. 상세 rational 값·repair·잔차는 슬롯 INDEPENDENT_CERTIFICATE.json에 보존했다.

Slot82의 optional strict rational point는 voltage_upper4행의 약1.17×10⁻¹⁷/1.78×10⁻¹⁷ 양의 exact 잔차가 남아 STRICT_RATIONAL_GRID_REPAIR_FAILED로 보존했다. 수치 incumbent replay와 Solver Global Bound 인증은 PASS지만 이 점을 정확한 Snapshot optimum 상한이나 Material 불가능 증인으로 사용하지 않는다.

Solver Global Bound의 수치 B&B 인증과 optional exact incumbent 가능점 증인은 별도 계약이다. 수치 incumbent replay가 허용오차를 통과하더라도 정확한 Fraction Grid 검산에서 미세 위반이 남으면 그 점의 strict upper 증인은 미인증으로 남기고 조기 불가능성을 주장하지 않는다.

Window 경계 SOC 완화에는 구체적인 물리적 약화 기전이 있다. E88/E96를 원본[440,1080] box로만 두면 차량당 최대640kWh net draw를 허용한다. 저장 β=4740631186705785/18014398509481984를 적용하면 이동·충전 없이 한 위치에서8슬롯 모두300kW 방전하는 에너지 소모는631.57894737kWh이고, E88=1080에서 E96=448.42105263≥440이다. 이 rational 증인은 literal17,608행과 compact18,472행의 전체 물리/box/integrality를 정확히 만족했다.

반면 원본 FULL의 E96=760과 E88≤1080을 유지한 no-charge/no-travel 운전은 net draw≤320kWh/차량이다. 이 차이는 사용자 요청의 자유 boundary가 하한을 약하게 만들 수 있는 이유를 보여준다. 예시가 해당 Grid를 만족한다거나 이 경계만 바꿨을 때 LB가 얼마 상승한다고 주장하지 않으며 실제 실행 모델도 수정하지 않았다. Original SOC/endpoints를 보존하는 K48 Selective 후보는 별도 검토 가치가 있을 수 있지만 향상·계산성은 미검증이다.

세 단일 슬롯의 성능으로 모든 다기간 Window의 개선 가능성을 배제하지 않는다. Route/SOC 완화의 원인 분리는 동일 물리를 추가한 대조 Solve 없이 정량 확정하지 않으며 이번 범위에서 추가 Solver를 실행하지 않았다.

## 9. 최종 Global LB·3% 목표

|항목|결과|
|---|---|
|최종 Global LB|0.46498486997548166|
|기존 대비 개선량|0|
|Material 기준 ≥0.001|아니오|
|검증 원본 U4 UB|0.6760534504652341|
|Global Gap (%)|31.22069421|
|3% 목표|미달성|
|성능 판정|TIME_DECOMPOSITION_NONMATERIAL|

## 10. Window [88,96) 경계 사영·360초 승인과 실제 정식화

Window는 슬롯94의 사전 Grid 위반과 종단 경계 부담으로 결과 전에 [88,96)로 고정했다. 원본 Arc는 depart<96 및 connect>88이면 모두 유지했다. 시작 이전 출발·구간 진입 transit arc도 자유 interface로 들어오며, 구간 내부 원본 incidence와 실제 이동시간을 유지한다. 시작 위치는 원래 origin에 고정하지 않고 시작/종료 SOC는 원본 box만 적용했다. 원본 initial/terminal SOC=760 등식은 부과하지 않았다.

이동에너지는 원본 departure debit 시점을 보존한다. 88 이전에 출발한 이동은 이전 시점에 이미 debit되므로 자유 E88 interface에 포함되고, [88,96)에서 출발한 이동은 해당 원본 energy_balance 행에서 차감한다. 진입 transit는 원본 도착 전까지 STAY=0·P/Q=0이다. 내부 SOC Balance·Mode·PCS·접속 gate를 유지하며 창 밖 미래 이동/충전·Rebound를 추가 제한하지 않는다. 원본 한 경로는 entry/exit cut을 각 한 번 통과하므로 이 boundary 사영이 원본 FULL을 포함한다.

|Window 표현|Rows|Columns|Binary|NNZ|원본 U4 사영 최대 위반|
|---|---|---|---|---|---|
|초기 literal 물리 부분|17,608|18,576|16,236|98,752|0.00000000|
|실제 Native 전체 모델|95,472|28,561|896|1,382,625|0.00000000|

처음 원본 Arc/Mode를 모두 Binary로 둔 literal 물리 표현은16,236 Binary로 원래1,500 상한을 넘었고, WINDOW_LITERAL_BINARY_RESOURCE_STOP 증거를 보존했다. 이는 Full96 K48의9,322 Binary와 표현 방식이 달랐기 때문이며 작은 창의 물리가 Full96보다 커졌다는 뜻이 아니다. 사용자는 이후 “Window에 최대360초 돌려봐”와 “예,16,236 Binary 모델로 최대360초 실행”을 명시했고, 이어 Source18r의 C-route+Binary-node 동등 표현을 우선 검토하도록 지시했다. 최초 Material 조건과120초 예산·literal Binary 상한의 예외는 USER_WINDOW_360_OVERRIDE.json 및 compact 검토의 최신 지시 증거에 분리 기록했다.

실제 실행은 C-route 연속 arc와 Binary node_activity/charge_mode의 compact 표현이다. 원본 각 내부 arc의(from site,time,to site,time) 중복이 없고 엄격한 시간 DAG에서 Binary node throughput과 단일 entry/exit flow가 내부 arc의 정수 경로를 강제한다. 창 이전 출발의 동일 arrival-node incoming parallel arc는 창 내 departure energy에 들어가지 않으므로 한 원본 incoming arc를 선택해 lift할 수 있다. 모든 원본 crossing arc·이동시간·SOC debit·PQ/PCS 행은 유지한다. 이 특정[88,96) Window의 정수 물리 사영은 literal Arc-Binary 모델과 동등하다는 독립 증명을 통과했고, 전체 원본 문제의 임의 영역/날짜에서 연속 route가 자동 정수라는 일반 주장을 하지 않는다.

|Compact 원본 물리 항목|실제 수/감사|
|---|---|
|유지한 원본 continuous Arc|16,204|
|Binary node_activity|864|
|Binary charge_mode|32|
|총 Binary|896|
|원래1,500 Binary 상한 통과|PASS|
|중복 없는 내부 endpoint groups|11,752|
|내부 parallel groups|0|
|창 이전 출발 incoming arcs|4,452|
|incoming parallel arrival groups|280|

Compact 동등성은 내부 경로·Mode/PQ/SOC·Grid/rho/objective의 정수 물리 사영에 대해 성립한다. 과거 경계진입 arc 좌표 자체의 값까지 같다고 주장하지 않는다. 경계 이전 incoming parallel mixture를 같은 도착 site/time 그룹의 한 원본 arc로 치환해도 실제 CSC physical-column signature가 같고 창 안 energy/PQ 행에 사용되지 않아 모든 창 안 값을 보존한다. 모든16,204개 원본 arc 변수를 삭제하지 않고 C로 유지했으며896 Binary는 원래1,500 안전 상한 안에 있다.

전체8슬롯 원본 Security67,880행과 helper9,120행을 복원했다. 정확한 Fraction helper affine9120개 및 Security 선형 결합67880개를 검증하는 factorized 소거는 반복되는 약1,900만 dense facet 계수를 저장하지 않아도 원본 helper lift와 정확히 동등하다. Grid Native0 wall46.871512초이며 계통 NNZ는1,264,501다. 실제 Native 모델은 Rows≤100,000,NNZ≤1,500,000 및 해당 Binary authority와 메모리/다른 Heavy gate를 통과하고 Window Optimize1회를 실행했다.

Window 실제 Solver Global Bound는0.309531105270, incumbent는0.312183120564, Native Runtime은360.198000초다. TimeLimit360초는 최대 예산이며 OPTIMAL이면 앞서 종료한다. Window incumbent를 FULL UB/Actual PASS로 사용하지 않으며 strict exact incumbent 가능점 상한 증인은 이번 Window 인증의 주장에 포함하지 않는다.

## 11. RAM·Commit·Native Ledger

|Slot|Peak RSS (GiB)|Peak private commit (GiB)|Gurobi MaxMemUsed (GB)|최소 RAM Available (GiB)|최소 Commit Available (GiB)|
|---|---|---|---|---|---|
|75|0.14201736|1.11754608|0.07152480|16.13334656|26.66961288|
|82|0.17028046|1.14378357|0.09883224|16.13373947|26.76642227|
|94|0.14251709|1.11748505|0.07155930|16.18603897|26.82360077|
|Window[88,96)|0.55997849|1.75595093|0.69475045|15.86314774|26.02591705|

Native Runtime 합 399.039000초, Optimize wall 합 407.402078초, 요청 TimeLimit 합450초(기존 Snapshot90+사용자 승인 Window360)다. Callback 안전 감사시간이 Runtime/wall에 포함되므로 순수 Solver 속도와 동일시하지 않는다. Native Peak RSS 0.559978GiB·Peak private commit 1.755951GiB, 실행 중 최소 Available RAM 15.863148GiB·Commit 26.025917GiB다.

Window Python callback stopwatch 합은110.699762초이고 Gurobi log의 callback 계측은73.39초/9,605회다. 서로 다른 instrument scope를 그대로 기록하며 Runtime에서 어느 값을 빼서 순수 Solver 시간이나 동등한 성능 향상을 추정하지 않는다. 원시 log SHA를 CALLBACK_TIMING_DIAGNOSTIC.json에 고정했다.

공통 원본 Fraction grid 추출 Native0 wall은 160.394479초다. Native 모델 생성시간·각 슬롯 추출시간·독립 Native0 검증시간은 각각 원시 JSON에 분리 기록했다. 작은 Native solve의 시간만으로 전체 감사 pipeline 비용이 사라졌다고 주장하지 않는다.

모델 생성 후 실제 Available RAM≥4GiB, Commit≥6GiB에 max(2GiB,4×실제 private 증가) 추가 reserve를 적용한다. 다른 실제 Heavy Native Solver·unknown Gurobi DLL peer가 있으면 보류하며 기존 프로세스를 종료하지 않는다. Callback은 own B2 모델만 안전 중단할 수 있다. Snapshot3회 prefix를 SNAPSHOT_NATIVE_LEDGER.json에 고정 보존하고 신규 연구 Ledger에 사용자 승인 Window1회만 추가했다. 기존 PR의 보호 Native Ledger는 수정하지 않았다.

|실행 구분|실제 호출|요청 TimeLimit 합|
|---|---|---|
|Snapshot MILP|3|90|
|사용자 승인 Window|1|360|
|원본 Full96 Optimize|0|0|
|B1 Supervisor/Worker/Campaign|0|0|
|공식 5월 캠페인|0|0|
|Selective Integrality|0|0|

## 12. 과거 PR111/169/182와의 수학적 차이

|연구|이전 실제 영역|이번 연구와의 차이|
|---|---|---|
|PR111 W7|슬롯40–46 Grid와 네 차량96슬롯 물리를 유지한 연속완화 및 조건부 epigraph 셀 감사|이번 Snapshot은 실제 Binary 위치/Mode를 남기고 시간 물리를 완화한다. 조건부 epigraph나 과거 상한을 현재 LB에 합산하지 않는다.|
|PR169 Joint trajectory hull|MESS04 국소 경로·mode disjunction의 hull EF와 기존 Full96 모든 행, 이후 Selective Integrality 진단|이번 모델은 hull EF를 Full96 위에 쌓지 않는다. Window 경계 사영 위험은 같은 물리 문제지만 과거 LB/UB 결과를 Source18r 인증으로 재사용하지 않는다.|
|PR182 fleet/time/grid EF|occupancy disjunction 또는 Boolean selector RLT·symmetry를 Full96 위에 추가한 동등 EF|이번 Snapshot은 의도적인 사영 완화다. 최대256/1500 Binary·행/NNZ 상한으로 작은 MILP의 실용성을 검증한다.|

PR111의 한 창 feasible-upper와 당시 default 값, PR169의 다른 Source 선택 Binary 비개선, PR182의600초 미완료 ROOT 결과는 현재 B2 LB가 아니다. 한 약한 창의 결과가 모든 시간 분해를 배제하지 않는 점과 대규모 EF 계산비용만 설계 교훈으로 반영했다. 정확한 Git blob/SHA·일차 코드/증명/CSV 보존본은 HISTORICAL_WINDOW_JOINT_AUDIT.json과 historical_primary에 있으며 실행/import하지 않았다.

## 13. Source18r·U4·B1 및 실행 상태 보존

|최종17항 보존/실행 감사|결과|
|---|---|
|final_all_seven_local_remote_sources_B1_stopped_tasks_automations_PASS|PASS|
|immutable_Snapshot_post_audit_and_ledger_bytes_preserved|PASS|
|exact_original_three_snapshot_ledger_prefix|PASS|
|exact_four_calls_one_Window_total450_requested_seconds|PASS|
|explicit_360_second_single_Window_user_authority|PASS|
|Source18r_compact_Node_Mode_896_binary_original1500_cap_PASS|PASS|
|complete_Window_size_Rows_NNZ_caps_PASS|PASS|
|Window_actual_native_readback_PASS|PASS|
|Window_fresh_post_build_memory_source_resource_admission_PASS|PASS|
|Window_singlethread_actual_TimeLimit360_contract|PASS|
|all_recorded_Window_RAM_Commit_floors_PASS|PASS|
|no_observed_Window_callback_Heavy_memory_or_numeric_stops|PASS|
|exact_archived_execution_source_copies|PASS|
|scientific_Native_sources_still_match_execution|PASS|
|all_sealed_executed_Native_matrices_physical_and_grid_packets_preserved|PASS|
|independent_Window_Global_Solver_Bound_certificate_PASS|PASS|
|no_B1_Full96_MILP_campaign_or_incumbent_UB_Pass_promotion|PASS|

최신 WINDOW_POST_RUN_RESOURCE_SOURCE_AUDIT.json 관측 시각은 2026-10-12T11:30:34.103865+09:00 (Asia/Seoul)이며 전체 감사 PASS=True다. Snapshot 종료 당시 POST_RUN_RESOURCE_SOURCE_AUDIT.json(PASS=True)도 수정하지 않고 보존했다. 기존 Source HEAD/clean·remote HEAD, 보호 원본 파일943개·기존 Native Ledger, B1 중지 receipt·결과, Windows Task action/enabled 계약 및 PAUSED 자동화를 대조했다. 이 작업은 B1 Supervisor/Worker/Task/예약/자동화를 시작·활성화하거나 기존 타 연구 프로세스를 종료하지 않았다.

B1 현재 사용자 중지 상태와 기존 5월 HOLD를 유지한다. 과거 Task State나 monitor 관측만으로 실제 Native 실행·31일 완료를 추정하지 않는다. B1 전체31일 완료는 이번 보고의 주장에 포함하지 않는다.

## 14. Selective Integrality 별도 후속 후보

|후속 항목|Native0 측정/설계|
|---|---|
|Critical slots|75 / 82 / 94|
|정수 유지 예상|node_activity288 + charge_mode12 =300 Binary|
|나머지 원래 Binary 연속완화|9,022|
|Rows|143,308|
|Columns|244,265|
|NNZ|1,257,052|
|새 행/열|0 / 0|
|이번 Native Solve|0|

기존 K48의96슬롯 모든 Route/SOC/PCS/Grid 행·RHS/Sense/Bounds/Objective는 그대로 두고 Critical Slot의 원래 node_activity/charge_mode만 C→B로 되돌리는 후보이다. 원본 FULL 정수 가능해의 K48 사영이 F_selective에 포함되고 F_selective⊆F_K48_LP이다. 검증 Global Solver Bound만 FULL 하한으로 옮길 수 있다. Saved BASE LP에서 선택300개 중82개가 fractional이라는 사실은 향후 개선의 인증이 아니다.

현재 모델 재구성·Native는0회이며 별도 후속 승인 대상으로 보류한다. Binary300개가 적어도 기존143,308행/244,265열 연속 행렬의 Root 시간·RAM 부담을 유지하므로 값싼 실행이나 Material 향상을 가정하지 않는다.

## 15. 정식화 채택·기각과 증거

이번 세 선정 Snapshot과[88,96) Window는 Material Global LB 강화 방법으로 채택하지 않는다. 이 판단은 현재 선택 슬롯/창과 실행 예산의 관측에 한정하며 모든 다기간 Window의 가능성을 배제하지 않는다.

사용자가 별도 요청한 Window360과 Source18r compact 동등 표현 검토만 추가했고 더 큰 창·가중치 반복·Constraint Generation·Parameter sweep·동일 Snapshot/Window 반복 실행은 수행하지 않았다. 후속 Selective Integrality는 현재 결과 검토 후 별도 연구 후보로만 남긴다. 원본 Planning 가능해 판정과 U4 UB 엔진에는 어떤 새 하한 모델도 적용하지 않았다.

결과·전체 Solver log·Memory/Resource trace·Native ledger·실제 실행 소스 사본·원본/소거 계수·독립 인증을 새 연구 디렉터리에 보존한다. FINAL_RESULT.json의 집계, 각 슬롯 RESULT/INDEPENDENT_CERTIFICATE, WINDOW_NATIVE0_DESIGN 및 보호 감사가 수치 authority다. 이후 Evidence Index는 실행 byte와 Git 저장 byte를 대조한다.

Window Native0의 반복 dense facet prototype은 자체 no-Gurobi 프로세스만 중단하고 정확한 helper factorization으로 교체했다. 중단 당시 소스·진행 receipt는 보존했고 Native Optimize 호출은0회다.

자동 승인 검토가 자체 Native0 파생 임시 NPY 폴더의 검증된 재귀 정리 명령을 “blocked by policy”로 거절하여 임시 파일을 보존했다. 다른 삭제 방법으로 재시도하지 않았고 모델·Solver·기존 연구/B1에는 영향이 없다. 자세한 명령/경로는 TEMP_CLEANUP_AUTO_REVIEW_REJECTION.json에 기록했다.
