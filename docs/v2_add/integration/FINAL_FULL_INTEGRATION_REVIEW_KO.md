# V2_add PR #236 FULL 통합 준비 검토

**PRESTART_BLOCKED_WITH_EVIDENCE**. `READY_FOR_USER_CAMPAIGN_APPROVAL`과 전역 `SCIENTIFIC_SIMULATION_READY`는 FALSE다. `FIELD_INSTALLATION_UNVERIFIED`는 별도이며 GIS·현장 보호 인증의 부재를 이번 과학 시뮬레이션 차단 사유로 쓰지 않았다. 기준 HEAD `a4dabafb52e9ee12a95858438b7d65b6b751d34f`, 원본 `affc7226a519adbe072d7debbc3ae25ea71c3487`, 동일 Draft PR #236을 유지했다. 공식 캠페인, A1/M1/A2/M2/K48/Joint 최적화를 실행하지 않았다. Native0 생성자의 optimizer/presolve는 차단했다.

## 수정과 독립 검증

1. **원본 B0 FCFS 수정 완료.** Generic JobEventController를 B0로 사용했던 오차를 제거하고 원본 BaselineController/OriginalFCFS 및 CorrectedReference를 연결했다. 동결 GPU·C1 전력 최대 오차 모두0이며 새 독립 재생 이벤트도 동일하다. 2,498 Job 중 완료2083, Carryout415; 계산량22740.088611111GPUh + 잔여9846.680555556GPUh = 원본 서비스32586.769166667GPUh다. Job별 잔차0초, 전체 시간·사이트 GPU 재적분 오차는1e-13 수준이다. Carryout을 삭제하거나 GPUh를 훼손한 반례는 검증기가 거부한다.
2. **AIDC 제한적 진척.** 원본1499 Job 전체 옵션/공유 GPU·WAN/Rack 도메인 검증을 통과하는 UID8665305의 사전 배치1개를 얻었다. 기존414개 시작시간 위반 캐시는 계속 거부한다. 같은 strict B1 제어기끼리 비교한 최대 전력 차이는0.547723909kW, 의도적 QoS 초과0, 독립 재생 동일이다. 그러나 이 비교의 기준은 원본 FCFS B0가 아니다. 계산 GPUh 차이1.891388889, 완료1663→1652, Carryout835→846이며 서비스 총량만 정확히 보존된다. 같은 정책의 AC 전역 최대 개선은-0.000000000005%p로 사실상0이다. 완성된 r043 FULL 운전 가능해나 B1/B3 성과로 승격하지 않았다. Source QoS와 Known 완화 정책을 구분하고 GPU Scaling은 실행하지 않았다.
3. **IDC 물리 계약을 추적했다.** 원본 DSS는 IDC마다 건물1500kVA와 별도 MESS750kVA 변압기·Generator/Load를 갖는다. IDC는 방문 전용이 아니며 P/Q가 허용된다. 같은 C2 MV 지점에 독립750kVA/480V, 포트600kVA·721.6878A·점유1을 추가했고 AIDC 건물 소비와 차량 주입을 분리했다. 12 IDC × P/Q 네 모서리48개 포트 열·전류 검증은 PASS다. 원본 IDC는 wye/wye, 현재 Adapter는 PR199 계열 delta/grounded-wye·각R0.5%·XHL5.6624%라는 연구 설비 가정이므로 전기적 완전 동일성을 주장하지 않는다. 기존 STA12·도로24위치·Route/ETA/이동 에너지는 유지했다.
4. **중요한 신규 전압 결함.** May01 평가96에서 기존 노드 최대는1.049087915pu지만 신규 `full_mobile_idc08_lv.1`은 t=44134초에1.050523816pu다. 무주입480V 포트도 안전성 검사에 포함했다. 이전 STA12 모델의 평가96 PASS는 이번24포트 모델의 PASS가 아니다. 열 정격 PASS와 운영 전압 PASS를 분리했으며 설비·Source·P5·SVR·PCC를 결과에 맞춰 조정하지 않았다.
5. **날짜별 입력 결함 수정.** May02/07의 원본 hourly wet-bulb 결측2건은 원본 SHA/행을 보존한다. 완전한 직전 관측쌍을 기존 as-of 전진 유지 정책으로 사용하며 최대 관측 나이6300초는 원래7200초 한도 안이다. 보간·미래 조회·원본 값 채움은 없다. May03/07의 Planning 비대상 초기 Running7개는 새 Window/유연성을 만들지 않고 기존 외부 Running의0유연 계약으로 서비스·초기 사이트를 계속한다. 추가 Provider/Case SHA도 별도 바인딩했다. 일곱 날짜 모두 원본 FCFS 재생·Job 작업량·Actual120·독립 Fresh를 확보했다.

## 실제 B0 날짜별 수치

전역 목적함수는 원본 선로 parent terminal의 평가96 **각 슬롯 마지막 TIME 해** 최대다. 이벤트 극값·전체120 안전은 별도이며 MV/LV를 목적함수에서 제외하지 않았다. 저/고 위반 시간은 전체120의 Native 해가 다음 물리 이벤트까지 유지되는 시간이다.

|날짜|Planning 최대%|Actual 전역%|MV%|LV%|MV−LV %p|평가 이벤트 Vmin–Vmax|전체 저/고 초|전체TIME|Fresh|
|---|---:|---:|---:|---:|---:|---|---:|---|---|
|05-01|72.016896|75.711000|75.711000|46.810641|28.900359|0.951108–1.050524|23/31|FAIL|PASS|
|05-02|69.387383|78.723142|78.723142|48.701827|30.021315|0.945840–1.048349|936/4|FAIL|PASS|
|05-03|60.114828|63.194336|63.194336|38.107098|25.087238|0.972090–1.057673|21/53|FAIL|PASS|
|05-04|57.471381|62.561556|62.561556|38.137313|24.424242|0.972297–1.060670|17/120|FAIL|PASS|
|05-05|64.394272|68.217065|68.217065|41.643971|26.573094|0.960132–1.051141|17/48|FAIL|PASS|
|05-06|65.113937|68.429739|68.429739|41.043289|27.386450|0.973686–1.048020|19/15|FAIL|PASS|
|05-07|66.306286|70.560336|70.560336|42.295301|28.265035|0.970848–1.050812|19/30|FAIL|PASS|

모든 날짜 β_BG2.00/Actual SVR3/C2/GPU780/MESS8로 동일하다. Fresh는 새 DSS 문맥이며 모든 저장 배열이 같았다. 상세 선로·상별 슬롯 병목과 Top20은 `ALL_DATES_SETTLED_SLOT_BOTTLENECKS.csv`, `ALL_DATES_SETTLED_TOP20.csv`에 있다. 모든 전압 위반과 선로·변압기·포트 검사 원본은 Runtime에 보존했다. May02 이후 β/PCC를 재선정하지 않았다.

## TIME 및 제어 Authority

Planning은 원래 Reg12/CapControl9, Actual은 원래 Reg12 + 추가3상 Bank3개/Reg9 = Reg21이다. P5 Source1.04/Vreg123.5/CAPBank3 초기OFF, 원래 Delay15/TapDelay2와 추가 SVR의 Vreg120/Delay30/TapDelay2/MaxTapChange1을 유지했다. 7일 모든 Native TapNumber–Winding2 대조·시간 순서·미래 Queue 검증 PASS, 포화 설비0개다. HVMV_Sub·STA750·IDC750에는 자동 RegControl이 없다. 수치 반복100은 물리 지연을 생략하지 않는다.

원시 이전 AEMO/Weather 관측은 존재한다. 그러나 원본 May01 초기 사이트는 모델상 배치이며 이전 IEEE8500의 연속 Job-site 전력·Tap/Cap 내부 상태·Queue를 함께 고정한 이력은 없다. IEEE123 Tap, 이후 정착 상태 또는 반복 Prefix를 인과 초기 상태로 복사하지 않았다. 냉시동 저23초/고18초를 삭제하지 않았으며 신규 IDC 평가 이벤트 과전압13초도 추가 기록했다. Planning TIME과 다른 날짜의 위반도 남는다. 초기 이력만 고치면 전체 날짜가 해결된다는 인증은 없다.

## 전체 Grid + MESS8 Native0

원본3703개 선로/1177 Triplex/정격·비활성5개와 원본 변압기를 보존했다. 96슬롯 × 60 controls(AIDC12 부하,24 차량 사이트 P/Q)의 실제 IEEE8500 계수를 생성했다. Parent6156셀, 양단12322셀, 전압8603노드, 변압기 전류7310셀·kVA3605 winding을 유지한다. Planning96의 이전/현재 Tap·Cap 상태는 모두 동일하며 앵커 차이는 전류비1.4e-9·전압제곱1.33e-9다. 5kW/kvar 독립 holdout27건의 최대 전류비 오차0.0003623·전압제곱5.024e-7을 기록했다. 이는 전역 AC 정확도 증명이 아니며 Actual/Fresh가 필요하다.

단일 실제 Gurobi 모델은 보호 한도에서 중단됐다: Binary417,296, Continuous871,199, Rows5,338,586, Nonzero76,723,045, 977.81초, Peak RSS4.0013GiB. 완료23슬롯+다음 슬롯 일부의 **부분 모델 실측**이며 전체 FULL PASS가 아니다. 이 첫 코어 시도 이후 추가한600kVA 포트 명시 행은 아래 전체 팩에 포함된다.

메모리를 제한한 실제 Native0 이동 모델과 실제 Native0 전기 블록96개를 생성하고, 임시 포트 alias만 ±1 가중치로 원본8대 Pdis−Pch/Q에 정확히 대입해 전체 행렬·변수 도메인을 저장했다. 행이나 Route를 줄이지 않았다. 전압 equality+bound, 원본16face 전류 보정식, 양단전류, 모든 transformer winding current/kVA,24포트 전류/600kVA16face, 원본 flow/mode/PCS16/P300/Q250/SOC/이동에너지 및2304점유 행이 들어 있다. Gurobi가 작은 비영 계수를 버리지 않도록 양의2거듭제곱 행 배율을 기록했고 원본 Solver budget/Gap은 바꾸지 않았다.

완성 행렬 팩 실측: **Binary417,296, Continuous3,350,097, 전체 변수3,767,393, Rows20,634,824, Nonzero302,476,152**. Case SHA `dc7dbe4906cd58685e4350d6f1e7fa5453ef68767e86ae0c524354a3b9500d86`. Source 원본 차량 검증기와 독립 전체 행/box/integrality 검증을 통과하는 B0 고정-AIDC STAY/PQ0 점을 얻었다(ρ=0.720168956466). STAY/MOVE 변수 도메인은 자유이며 이 점만 STAY 증인이다. 최적화·LB·Gap·B3 성과가 아니다. **전체 행렬 팩과 단일96슬롯 Gurobi 생성 성공을 구분한다.**

기존 Q50 두 피크 유한 Pilot도24포트 모델에서 재생했다. B075.711000%→73.744160%, 개선1.966840%p, Source SOC/PCS/초기종단760 검증 및 Fresh 동일이다. 그러나 신규 IDC 무주입 과전압과 Prefix 때문에 전체 운영 PASS는 아니다. 2.4MW 순간 정격을 하루 에너지로 계산하지 않았다.

## 남은 단계와 실행 HOLD

완료한 M1 팩은 **May01 B0 고정 AIDC의 Planning affine FULL 모델**이다. May02–07의 optimizer용 응답 계수, A1/A2의 CC4/Job/GPU→C1→전체 Grid 가변 연결, 실제 r043 C0/C1/Current-AC/완화 Known 정책의 분리된 수용 검사, K48/Adaptive Beam/Direct Joint의 새 행렬·도메인·물리 metadata와 독립 Global-LB 인터페이스, 고정 M1→A2→M2 handoff 및 실제 Stage handler/Worker는 남는다. 원래7/43·120행·4대 guard를 숫자만 치환해 통과시키지 않았다. 예전 bounds·Golden414·restricted bounds를 이식하지 않았다.

독립 검사21개 및 그 안의 기존 수용·Checkpoint·HOLD 회귀8개를 통과했다. 원본 B0/B1/B2/B3 Chain과 Checkpoint/Resume/중복 OS lease/원장 재조정·Budget 보존 fixture를 재검증했다. A5400초/K48300초/M900초/Gap0.5%·3% 및 r043 Q250_M4의 실제 Joint call cap300초·M4 threads/A1 thread1을 기록했다. 이번 작업의 Heavy Native optimizer 호출은0이며 기존 Worker·Source·원장·V1_add는 수정하지 않았다. 기준368개 V2_add 파일은 모두 같은 SHA다.

`python -m v2_add_preflight.full_execution plan`으로 보류 설정과 준비 명령을 확인할 수 있다. 실제 캠페인 명령은 필수 결함과 실제 handler 연결이 해소될 때까지 fail-closed다. 별도 사용자 캠페인 승인을 요구할 수 있는 READY 상태로 아직 승격하지 않는다. 현장 인증의 부재와 과학 모델의 전압·수학/알고리즘 통합 미완료를 혼동하지 않는다.
