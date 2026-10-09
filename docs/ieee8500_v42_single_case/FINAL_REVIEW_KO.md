# IEEE8500 V42 중간 보고 — 공동 연구 배치와 운영 승격 차단

**AIDC 12곳·저압 STA 12곳 공동 연구 배치를 구성했지만 최종 적격 운영 시나리오는 미선정이다. V42 전체 Native 이식은 미완료다.** 24개 원 교통ID·네트워크·ETA와6대 MESS를 보존했다. 원 선로·변압기·전압 제약 및 전체 `min rho_max`는 그대로다. 12개 사전 스케일 모두 원 전역 전압 제약을 실패하므로 Source/Vreg 변경 없이 Production을 차단했다. B1/B2/B3 Native·전체 모델·장시간 정책 Solver 실행은0회다. 현재 실행 캠페인에는 쓰지 않았다.

**기존 v3 방향 충돌 원인.** 원 AIDC12 좌표와 교통12 좌표의66쌍/132축을 독립 검사했다. 원 XY를 그대로 쓰면115축, 공통 proper similarity 진단 정합 후에도17쌍/17축이 충돌한다. 좌우 제약 AIDC02–03/07–11/11–12의 signed원벡터는 양의 가중치(.4739314708,.4681085601,.0579599691)로0이 된다. 상하 AIDC09–12/10–12/11–12도(.3168031544,.6142251063,.0689717393)로0이다. 각 벡터의 동일 선형 투영을 모두 양수로 요구하면 그 가중합도 양수여야 하므로0과 모순된다. 독립 검토는 원 decimal을 정확한 Fraction으로 계산했다. 이는 고정된 이전12버스의 허용 공통 선형 정합에 대한 certificate이며 최적화 실패를 수학적 불가능으로 바꾼 주장도, 새 버스 재선정의 불가능 증명도 아니다. 모든 쌍의 이름·교통/원XY/정합XY·차이·부호는 [66쌍 CSV](AIDC_66_DIRECTION_AUDIT.csv), [전체 충돌 CSV](AIDC_DIRECTION_CONFLICTS.csv), [exact certificate](GEOMETRY_INDEPENDENT_REVIEW.json)에 있다.

**현재 방향 검증.** 사용자 변경에 따라 이전 v3 버스 고정을 풀었다. 모든 위치에 동일한 `(x′,y′)=(u·x−v·y+tx,v·x+u·y+ty)`를 적용했다. `u=-.0011398737189343131, v=-.00023721373007232747, tx=-1000.2819244675629, ty=14393.330183925018`, 회전−168.2442350517°, 양의 균일척도.001164294829, det=1.355582448852e−6이다. 반사·개별 회전·방향 완화는0회다. 선정 전 동결한 축/근접쌍1m 공차에서 AIDC66+STA66+교차144=276쌍,552축 전부 strict PASS이며 면제축은0이다. 원 좌표 CRS/거리단위/나침반 방향과 정확한 고객 좌표는 검증되지 않았다. LV는 상위 원 서비스 변압기1차버스 좌표 Proxy다. 정합 RMS는5.6960111 layout-equivalent km, 최대9.5434310으로 실제 지리 오차가 아니다. EPRI [BusCoordinates](https://opendss.epri.com/BusCoordinates.html)는 회로도 XY를, [GISCoords](https://opendss.epri.com/GISCoords1.html)는 위경도를 별도로 정의한다. 따라서 **모델/Proxy 방향 PASS, 실제 지리 UNVERIFIED**로 표시한다.

| 위치 | 원 교통ID | 이전 v3 MV버스 | 현재 연구 MV버스 |
|---|---|---|---|
| AIDC01 | TN_01 | l3234149 | m1125934 |
| AIDC02 | TN_02 | e182733 | m1009805 |
| AIDC03 | TN_03 | m1027055 | m1027002 |
| AIDC04 | TN_04 | m1069411 | m1047480 |
| AIDC05 | TN_05 | l2688693 | l3029498 |
| AIDC06 | TN_06 | m1142814 | m1125976 |
| AIDC07 | TN_07 | m1026690 | l3048221 |
| AIDC08 | TN_08 | l3123452 | l2728247 |
| AIDC09 | TN_09 | l2728247 | m1069420 |
| AIDC10 | TN_10 | l2973833 | m1125962 |
| AIDC11 | TN_11 | m1047763 | m1026872 |
| AIDC12 | TN_12 | e192258 | m1142875 |

| STA | 원 교통ID | 현재 LV버스 | 원 서비스CT(kVA) | Triplex(A) |
|---|---|---|---:|---:|
| STA01 | TN_43 | sx2955055b | 25 | 156 |
| STA02 | TN_14 | sx2992657a | 25 | 156 |
| STA03 | TN_35 | sx2936211c | 15 | 156 |
| STA04 | TN_28 | sx3085394c | 15 | 156 |
| STA05 | TN_37 | sx2897766c | 25 | 156 |
| STA06 | TN_41 | sx2822867b | 15 | 156 |
| STA07 | TN_32 | sx3047058a | 37.5 | 156 |
| STA08 | TN_47 | sx3729298a | 37.5 | 156 |
| STA09 | TN_42 | sx3027133a | 25 | 156 |
| STA10 | TN_24 | sx2748125c | 25 | 156 |
| STA11 | TN_44 | sx3085401a | 37.5 | 156 |
| STA12 | TN_17 | sx2710516a | 25 | 156 |

**0.912 pu의 물리 원인.** 원 Master 정적 BG1·PV0·AIDC0·MESS0·Source1.05·feederVreg126.5/기타125·원10Caps/9CapControls에서 `sx2748781a.2`가109.450401 V다. 원 DSS120.088856 V기준 .911411805pu, 정확한 nameplate120V기준 .912086675pu다. 원 source부터127요소를 따라 feeder출력1.048950805→MV l2748781.1 .939214655→37.5kVA CT hot2 .930124003→50ft/4·0Triplex 고객.911411805로 떨어진다. MV 누적하락.10973615, CT.009090652, Triplex.018712198pu다. 해당 두 레그 부하1.826097/11.473903kW(PF.97)가 불균형하고 Model1은 이 전압에서 정전력 구간이다. 해당 Triplex108.074A/156A와CT14.169kVA/37.5kVA는 정격 이내다. 긴 MV 경로의 전류·임피던스에 의한 누적하락과 말단 불균형이 원인이다. 전체 최대혼잡 Line.tpx21459660c0의ρ1.75421678은 다른 지점이다.

원 자동 탭 제어12개는 실제 동작했다. 최저전압 경로의 FEEDER_REGA만 +2/1.0125이며125.866V로126.5±1Vband 안이고 제한에 닿지 않았다. VREG2/3/4는 이 고객 경로 상류에 없다. 다른 분기 VREG3_A는+16/1.10 상한, monitor123.7116V로125±1Vband 아래다. 수렴·queue0·ControlActionsDone은 전체 전압 적격을 보장하지 않는다. 이 원 정적 실행에서 capbank0a/b/c(각400kvar), capbank1a/b/c(각300kvar), capbank2a/b/c(각300kvar), capbank3(900kvar)는10개 모두 enabled, settledstate=[1]이다. 원9개CapControl을 자동운영했으며 명판합3900kvar와 실제전압에서의 AC 무효주입4073.675kvar를 구분한다. [127요소 경로](LOWEST_VOLTAGE_PATH.csv), [12개 제어 상태](LOW_VOLTAGE_REGCONTROL.csv), [원인 보고](VOLTAGE_ROOT_CAUSE_KO.md)에 상세값을 저장했다. 원 배경만 .552로 한 반사실은ρ.923825088/Vmin.987290597/Vmax1.050049498이다. 과거 BG.552 실험은 시간변동 AEMO부하·PV·옛AIDC2.4·Source1.04·Vreg123.5·CAPBank3OFF·추가36PCC CT로 조건이 다르다. 과거 정책 성과와 현재 원 정적 실험을 섞지 않았다.

**선정의 전기적 근거와 한계.** 원 Source proximity guard와12.47kV ABC 적격성을 통과한606MV, 원 CT/Triplex 고객하류1177LV의 실제 P/Q 중앙 AC 민감도를 개발4슬롯(0,9,48,75)·사전20혼잡선로에 계산했다. AIDC는 원1649UID의 활성GPU·C1·swing만으로 얻은 known-only 감소 상한(최대43.8179kW/사이트, 동시 system상한342.8752kW)과PF.95의Q/P.328684105를 사용했다. 시설idle·CC4·설비확장을 flexible전력으로 세지 않았다. STA는 원 local전압/CT/Triplex 선형여유와 포트한도 교집합, 동일시점 모든20선로에 하나의P/Qvector, 원6개 초기위치에서 unchanged safeETA+600초 연결지연의 도달가중치를 적용했다. 6/12노출계수는 연구 heuristic이며12동시방전·route/SOC의 적격 증명이 아니다. 20선로×4시점에 역효과2배벌점을 둔 입지 surrogate는 기존 최종운영 `min rho_max`를 대체하지 않는다. 최종 입지는 one/two-site local exchange 결과이며 global 최적성이 아니다. B3 결과를 보고 재선정·정격튜닝하지 않았다. [선정 근거](joint_selection_v3/score_selection/SCORE_SELECTION_REPORT_KO.md), [21,396행 독립 점수검토](joint_selection_v3/selection_scores/JOINT_SCORE_REVIEW_KO.md)를 참고한다.

개발일2025-05-01은 이전 IEEE8500 분석에 이미 노출된 날짜다. 독립 미노출 평가일은 미선정/미실행이다. 현재 modelable B0 reference와 Native windows 사이1024개 시작 시점 불일치가 발견되었고 QoS/WAN/재시작의 결합 dispatch를 풀지 않았다. 따라서 known-job 전력은 유연성의 상한이며 실현 가능한 전체 스케줄이라고 주장하지 않는다. [원 Job 감사](FLEXIBLE_WORKLOAD_AUDIT_KO.md)와 [교통/ETA 감사](TRAFFIC_MOBILITY_AUDIT_KO.md)에 원 데이터 보존·도달 한계를 명시했다.

**저압 접속 설계와 AC 증거.** 12개STA 모두 원 고객측 split-phase120/240V `.1.2` 버스다. 새 변압기/추가STA 없이 별도 소출력 인버터·절연·보호 dock을 연구 설계했다. [Schneider XW Pro6848NA 제조사 사양](https://solar.se.com/us/wp-content/uploads/sites/7/2021/10/XW-Pro-UL-Datasheet.pdf)의 grid-sell6kW/27A,120/240V,48V배터리를 근거로 P±5kW/Q±3kvar/S6kVA 및실제VLL×27A 상한을 정의했다. 60A relay는 인버터정격으로 쓰지 않았다. Q±3kvar 독립제어·차량고전압→48V DC/DC·BMS·절연·역송보호·접속승인은 전체조립품 자료가 없어 UNVERIFIED 연구 가정이다. 차량450kW/600kVA 전체는 저압에 주입하지 않는다.

각12포트×96슬롯×8정격 P/Q점=9216fixed제어 AC와 별도384automatic AC를 실행했다. 9216점 모두 실제두hot/KCL/PQ, 포트전류, 원국부전압·Triplex·CTcurrent/nameplate한도를 통과했다. actualPQ 오차 최대6.844e−9, hotKCL0A다. 선정48개 bounded조합도 새 공동배치 국부AC PASS다. 최초384auto글로벌기록을 보존하고 국부PCC읽기를 보강한384auto재검사도 수행했다. 국부/하드웨어표본 전부PASS, 실제최대hot24.279982A, PQ오차7.432e−9이며384개tap/cap상태SHA를 저장·독립검토했다. [자동 국부 증거와 고정/자동 독립검토](joint_selection_v3/selected_port_ac/INDEPENDENT_PORT_REVIEW_KO.md)를 제공한다. 이는 표본점을 검증한 것이며 연속P/Q영역·자동탭영역·6대route/SOC전체정책의 인증은 아니다. 방전5kW에서 개별CT leg역송과 일부hot 전류절댓값 증가를 관측했다. hot별phasor/branch실전력이 저장되지 않아 동일hot의 직접인과까지 단정하지 않으며 모든레그 전류가 감소한다고 주장하지 않는다. 원 Krön-reduced Triplex는 독립neutralampacity가 없어 재구성neutral전류만 출력했다. [포트별96슬롯 요약](joint_selection_v3/selected_port_ac/PORT_QUALIFICATION_SUMMARY.csv), [모든hot전류](joint_selection_v3/selected_port_ac/TRIPLEX_ALL_HOT_CURRENT96.csv), [순간 공동기여 반사실](joint_selection_v3/selected_response/INSTANTANEOUS_COMPLEMENTARITY_NOT_POLICY.csv)은 B0–B3 성과 또는 가능한스케줄을 뜻하지 않는다. 선정된포트는 사전상위7개Triplex혼잡선로의 직접하류가 아니다. 따라서 그선로에는 전압/상호결합의 간접제어가 주이고 국부Triplex 전류감소를 전체최대ρ개선으로 확대해석할 수 없다. 여러상위MV선로에는 AIDC·STA가 함께하류에 연결된다. [20개 선로 모두의 경로·허용전력·유한AC기여](joint_selection_v3/selected_response/ALL20_CONTROLLABILITY_KO.md)를 별도로 작성했다.

| STA | 방전5kW hot전류변화 범위(A) | 충전5kW 최대ρ | 모든8점×96 국부 | 상위CT역송 |
|---|---:|---:|---|---|
| STA01 | -18.192…-13.449 | 0.300248 | True | False |
| STA02 | -15.923…-15.157 | 0.264683 | True | True |
| STA03 | -14.311…2.889 | 0.252313 | True | True |
| STA04 | -17.709…13.072 | 0.288270 | True | True |
| STA05 | -18.781…-10.815 | 0.326584 | True | False |
| STA06 | -18.190…16.697 | 0.297294 | True | True |
| STA07 | -19.350…-18.504 | 0.356098 | True | False |
| STA08 | -19.571…-4.483 | 0.445931 | True | False |
| STA09 | -16.455…-14.655 | 0.270566 | True | True |
| STA10 | -18.053…-15.953 | 0.296352 | True | False |
| STA11 | -19.253…-13.923 | 0.401823 | True | False |
| STA12 | -18.725…-5.074 | 0.314379 | True | True |

**스케일을 분리한 B0 검증.** BG는 원 정적 부하의 균일배율, GPU설비는780/975/1170, 실제 Job 모집단/유연Job비율은1.0으로 유지했다. 시설PCC는 원V42 C1/대기전력/날씨/원logicalpool식을 그대로 썼다. 기존780GPU case에서 시설전체소비전력193.5367–568.2575kW이며 이것이 유연Workload전력과 같지 않다. MV시설rack/cooling/전용CT실물정격은 UNVERIFIED로 남겼다. PV0,Source1.05,Vreg126.5/125, 원caps와원모든선로/CT정격은12case에서 동일하다. 다음각행은96슬롯 실제AC다.

| BG | GPU scale | 전체최대ρ | Vmin | Vmax | 전압위반 node×slot | 적격 |
|---:|---:|---:|---:|---:|---:|---|
| 1.0 | 1.0 | 1.75941071 | 0.90410161 | 1.05601557 | 23811 | FAIL |
| 1.0 | 1.25 | 1.76317229 | 0.89973922 | 1.05590186 | 23797 | FAIL |
| 1.0 | 1.5 | 1.76537587 | 0.89728343 | 1.05579893 | 24039 | FAIL |
| 0.8 | 1.0 | 1.38087914 | 0.94895972 | 1.05866115 | 5469 | FAIL |
| 0.8 | 1.25 | 1.38077859 | 0.94752496 | 1.05856758 | 4779 | FAIL |
| 0.8 | 1.5 | 1.38073845 | 0.94589677 | 1.05847371 | 4622 | FAIL |
| 0.65 | 1.0 | 1.09787726 | 0.96628896 | 1.06099305 | 4546 | FAIL |
| 0.65 | 1.25 | 1.10818566 | 0.96141391 | 1.06087893 | 4915 | FAIL |
| 0.65 | 1.5 | 1.10180244 | 0.96958876 | 1.06077667 | 4585 | FAIL |
| 0.552 | 1.0 | 0.92195751 | 0.98670321 | 1.05272588 | 1373 | FAIL |
| 0.552 | 1.25 | 0.92359060 | 0.98416065 | 1.05445450 | 9700 | FAIL |
| 0.552 | 1.5 | 0.92308187 | 0.98292242 | 1.05437445 | 9322 | FAIL |

BG.552/780GPU 연구 기준은 전체최대ρ=0.921957508, Vmin=0.986703210, Vmax=1.052725879, 전압위반1373 node×slot이다. 원모든선로·CT열제약은 이case에서 통과하지만 원전압상한을 실패한다. 가장 큰ρ는 Line.tpx21459660c0이다. 0.80–0.85 목표를 강제하지 않았다. 고정된 연구기준 .552/1.0은 역사적 counterfactual/최소설비확장 기준이며 B정책성과 승자가 아니다. 다른날짜/부하형상/설치설계를 별도로 정당화하지 않고 적격운영case라고 선언할 근거는 없다. Fresh96슬롯 source-only 재현의6개 전류/전압/CT배열 최대오차와tap/cap상태차이는 모두0이다. [독립 스케일감사](joint_selection_v3/selected_ac/INDEPENDENT_SCALE_REVIEW_KO.md)에 모든조건/위반셀을 기록했다.

**단일 연구 snapshot과 V42 준비 상태.** 연구구성 canonicalSHA256은 `8f1ad20d080ecf04609be7a66fe912983dcb6ce8bf5b6afdd740b4bccc6aa1f6`, mappingSHA256은 `4a70fd13bf08c8512d30f74e48dfafb46fdddd4e112a3aee92a8191f22cad016`다. [STUDY_CONFIGURATION_DRAFT.json](STUDY_CONFIGURATION_DRAFT.json)은 하나의 검토용 연구 snapshot이며 [FINAL_SINGLE_SCENARIO.json](FINAL_SINGLE_SCENARIO.json)의 최종운영/Production구성은 null이다. A/M/B0–B3 인터페이스와append-onlyPCC제약이 준비되어도 현Native IEEE123/4대/고정그리드축·six-unit교통SOC·LV효율 .90×원배터리 .95=.855·source-causal windows·FULL/Compact/C3A동치·96슬롯연속affinecontrolcertificate·독립SUMOActual/Fresh·미노출평가일 및 현재전압FAIL이 해결되기 전 Production은 실행하지 않는다. A1/M1/A2/M2 실행budget/gap과sameSHA 요청만 마련했고 solver를 대체하지 않았다. [이식 보고](V42_INTEGRATION_REPORT.md), [동일SHA B0–B3 요청](COMPARISON_PLAN_BLOCKED.json), [캠페인 보존](CAMPAIGN_PRESERVATION_CHECK.json), [전체검증](FINAL_LIGHTWEIGHT_TEST_RECEIPT.json)을 함께 검토할 수 있다. 검토시작의138개권위파일·44개예약작업 등록은 보존됐으나 작업도중외부RecoveryV10작업3개와CONTINUATION_V10_MANIFEST가 새로관측됐다. 전체live상태가완전히동일하다고 주장하지 않으며 본작업의캠페인/예약작업쓰기는0회다. 분석기준source는 시작시점de6f79로 고정했다. 종료검토에서 v42원격87480938로의진행을 관측했으며 [시작점 이후 source진행 감사](SOURCE_ADVANCE_SINCE_REVIEW.json)와 이식보고에 차이를 남긴다. 새source 전체Native연결이 인증됐다고 주장하지 않는다.

각 PCC와20혼잡선로 민감도/전기적경로·허용전력·ETA기여는 [상세 위치감사](joint_selection_v3/score_selection/SELECTED_LOCATION_AUDIT_KO.md)에, Python/SVG/PNG계통도·히트맵은 같은score_selection폴더와figures에 저장했다. 이전v3고정시점의루트MAIN결과는 `historical_fixed_v3_outputs/`에 보존했다. 현재상대276쌍/STA/scale/line/tap/capacity루트CSV는새공동배치결과다. 과거시험의약1.36%p차이를 이번정책개선수치로이전하지 않았고 B0–B3성능차이는 아직측정하지 않았다.
