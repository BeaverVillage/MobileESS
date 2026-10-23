# V2_add — IEEE8500 실제 B0 Scale Screening 및 제어 Pilot

**판정: NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO.** G1 매핑 PASS, G2 사전 후보9개 실제 AC/Fresh 완료, G3 MESS/Planning-AIDC 제한된 Pilot 완료·Actual 비영 AIDC witness 미검증, G4 최적화기 이식 미실행이다. 허용 beta 범위에서 B0 Actual이70%에 도달하지 않아 Primary Scenario를 선정하지 않았다. 이는 계통 매핑 실패나 제어력 부재 판정이 아니다. 진단용 beta1.50을 Primary로 동결하지 않는다.

## PV 매핑과 전력수지

PR197의 2,354개 Hot Leg Generator를 같은 버스/상, .12kV 단상 wye, Model1, Q=0, Vmin=.88/Vmax=1.05로 구현했다. 설치용량 총 1276.937105381 kVA와 각 hot 설치용량은 그대로다. V44의 최종 PV 총량만 고정 설치용량 가중치로 배분하며 2.4kV Generator를 LV에 붙이거나 기존 PV를 중복 투입/부하 차감하지 않았다. 전 슬롯 최대 설치용량 대비 지령 비율은 25.6824%다.

각 beta Planning96/Actual Prefix24+96 및 독립 Fresh에서 실제 PV P/Q와 BG/PCC/Capacitor/손실/Source 전력수지를 측정했다. 기본 B0 전 케이스의 PV 실제 총량 최대 오차 3e-08 kW, P/Q 전력수지 최대 절댓값 4.49e-06 kW/kvar다. 용량 가중치가 고정되어 개별 PV 출력 제한도 전수 유지된다. 원본 입력·복원·SHA 59개 정적 검증은 재실행하지 않고 재사용했다.

## PCC/MESS와 고정 전압제어

C2의 AIDC12는 원래 3상 MV PCC에, STA12는 PR199의 동일한 12.47kV delta→480V grounded-wye 750kVA 전용 변압기에 연결했다. 원본 선로/변압기 정격을 수정하지 않았다. STA 접속 인터페이스는 기존 600kVA/721.688A이며 차량은 P±300kW/Q±250kvar/PCS400kVA와 원본 PCS16 부등식을 따른다. P/Q box는 PCS16 안에 있지만 전체 box의 모든 계통 운전점을 무조건 허용하지 않는다.

beta1.50에서 단일 STA 및 초기 8대 동시 P/Q corner를 Planning/Actual 각각 AC로 검사했다. 총 104개 순간점 중 89개가 전체 물리 제약을 통과했다. 실패점은 STA_P300_Q250_AC_ENDPOINTS.csv에 그대로 남겼다. 이 순간 endpoint는 SOC/96슬롯 보장이 아니다. 아래 일일 Pilot은 8대 동시 접속·충방전·SOC·재충전·전체 계통 제약을 따로 만족한 사례다.

초기 MESS01~04의 STA01/12/08/06을 유지하고 추가 차량은 이미 제안한 STA02/03/04/05를 사용했다. 모두 서로 다른 기존 STA 포트다. 원본 Route Table의 8×96개 same-site stay 행에서 ETA/ready/이동 에너지 0을 확인했다. 교통망·ETA·에너지 재생성은 없다. 정지 Pilot은 제한된 진단 후보이며 이후 최적화기의 MOVE/STAY를 강제하지 않는다. 전용 변압기·인버터 접속은 연구용 정상상태 AC 모델 가정이며 현장 보호·GIS·제조사 인증으로 확대하지 않는다.

P5는 **Source1.04pu, RegControl12개 Vreg123.5V, CAPBank3 초기 OFF, 원래 CapControl9개**로 사전에 동결했다. 모든 beta/진단 비교군에서 동일하다. 시간별 Tap/Cap 상태는 B0_TAP_CAP_TIME_SERIES.csv에 있다. 각 Planning/Actual은 별도 초기 context를 사용하고 Actual은 Prefix24를 포함해 native 제어 상태를 이어간다. Fresh는 새 context로 동일 순서를 독립 재생한다.

IEEE123의 Planning7/Actual43/SVR12 하드웨어를 숫자 그대로 복사하지 않았다. 이 단계는 PR197/199의 P5 native **static automatic settling**을 사용한다. V44 Actual의 지연을 가진 TIME 제어·Actual 전용 SVR12와 물리 의미가 다르며, 해당 TIME/지연 계약과 IEEE8500의 최종 알고리즘 검증 연결은 G4 잔여 과제다. 이번 결과를 기존 IEEE123 물리 계약과 완전히 같은 설정이라고 주장하지 않는다.

## 실제 B0 결과

| beta | Planning 최대 | Actual 최대/MV | Actual LV/Triplex | MV−LV |
|---:|---:|---:|---:|---:|
| 1.00 | 37.8288% | 39.4819% | 23.1010% | 16.3809%p |
| 1.05 | 39.5797% | 41.2458% | 24.3256% | 16.9202%p |
| 1.10 | 41.1894% | 42.8174% | 25.2232% | 17.5941%p |
| 1.15 | 42.7711% | 44.2682% | 26.4399% | 17.8283%p |
| 1.20 | 44.2932% | 45.8797% | 27.6694% | 18.2103%p |
| 1.25 | 45.8987% | 47.5381% | 28.9428% | 18.5953%p |
| 1.30 | 47.5340% | 49.2104% | 30.0711% | 19.1393%p |
| 1.40 | 50.9166% | 52.2589% | 32.2306% | 20.0283%p |
| 1.50 | 54.3978% | 56.1469% | 34.8850% | 21.2619%p |


전체 원본 3,703개 선로의 실제 상 도체와 양단을 목적함수/검증에 포함했다. 원래 disabled인 스위치 선로 5개도 축에서 보존하고 전류0으로 포함했다. 원래 Kron-reduced Triplex의 별도 정격이 없는 가상 neutral은 새 정격 도체로 만들지 않았다. 원래 Triplex hot 두 상과 원본 NormalAmps는 모두 포함한다. Primary/MV와 LV 지표는 원본 전압 계급 분류를 따른다.

모든 9개 beta에서 선로·노드 전압·변압기·포트 위반은 0이었다. 전체 전압 범위는 0.973728~1.042972 pu(Planning/Actual 전체와 Prefix 포함)다. 독립 Fresh 18쌍이 전수 통과했으며 B0 운전 Solve는 3888회다. Source 초기화용 solve는 이 횟수와 별개다.

75~85% 및 완화한70~85%에 해당하는 후보가 없다. V44 최종 BG 피크는 약2.713MW이며 beta1.50에서도 약4.069MW다. 원본 IEEE8500의 약10.773MW 명목 부하를 운영 크기로 다시 더하거나 PR197 BG=.552/PR199 BG=.85를 beta와 혼용하지 않았다. 작은 입력 총량이 낮은 혼잡 수준의 주요 원인이다. 마지막 두 beta 사이의 국부 secant만 외삽하면75%에는 beta약1.98가 필요하지만, 이는 Tap/Cap 및 병목 전환을 검증하지 않은 추정치다. 범위 밖 AC는 실행하지 않았다.

## 실제 전기적 민감도와 96슬롯 Pilot

beta1.00과1.50의 Planning/Actual B0 피크에서 24 PCC를 ±5kW/kvar로 교란했다. AIDC의 P 교란은 PF=.95의 Q를 함께 적용했다. 고정 Tap/Cap과 native auto 응답을 구분했고 무제어 재계산 noise를 따로 기록했다. 이 국부 전기적 교란을 Job/SOC 실현 가능한 제어량으로 해석하지 않는다.

beta1.50 Actual native-auto에서 AIDC5kW 감소(PF연동)의 전역 감소는 0.060499~0.067160%p, STA5kW 주입은 0.058468~0.064766%p, STA5kvar 주입은 0.004193~0.005972%p다. 무제어 재계산 noise의 최대 절댓값은 약4.08e-8%p다. beta1.50 Actual 최상위 병목의 위상적 하류에는 AIDC12/STA12가 모두 있지만, 이는 실제 가용 Job이나 하루 SOC 제어량을 보장하지 않는다. Top20별 하류 PCC 목록을 별도 CSV로 남겼다.

별도의96슬롯 Pilot은 beta1.50에서 AIDC-only/MESS-only/Joint를 비교했다. MESS는 사전에 고정한08~15슬롯 충전,68~75슬롯 방전의 원래 C2 진단 시간대를 재사용하고, V44 SOC440~1080/초기·종단760kWh/효율.95로 amplitude .25/.50/1.00을 검사했다. 1.00의 차량당 충전168.421kW/방전152kW, SOC760→1080→760이며 각 amplitude는 같은 SOC 보존 비율이다. 모든 충전 Rebound와 다른 선로로의 병목 전환을 일일 전역 최대값에 포함했다. 차량당300kW나 합계2.4MW를 하루 보장 운전량으로 사용하지 않았다.

| 역할 | 진단 제어 | amplitude | B0 전역 최대 | Pilot 전역 최대 | 전역 감소 |
|---|---|---:|---:|---:|---:|
| PLANNING | AIDC_ONLY | 0.00 | 54.3978% | 54.3978% | 0.0000%p |
| PLANNING | MESS_ONLY | 0.50 | 54.3978% | 53.7955% | 0.6023%p |
| PLANNING | JOINT | 0.50 | 54.3978% | 53.7955% | 0.6023%p |
| ACTUAL | AIDC_ONLY | 0.00 | 56.1469% | 56.1469% | 0.0000%p |
| ACTUAL | MESS_ONLY | 1.00 | 56.1469% | 55.9451% | 0.2018%p |
| ACTUAL | JOINT | 1.00 | 56.1469% | 55.9451% | 0.2018%p |


Actual MESS 최선 후보의 새 최대값은 슬롯76(19:00), 같은 MV Line.ln5775442-1 A상이다. 고정 방전 구간68~75가 끝난 뒤의 피크로 넘어가 전역 개선이0.2018%p에 그쳤다. LV floor로 전환된 결과가 아니다. 이 제한된 진단에서 선호 목표1%p 감소를 달성하지 못했으며 더 넓은 최적 운전의 상한을 뜻하지 않는다. amplitude1.00의8대 합계 충전/방전 에너지는2694.7368/2432kWh로 초기·종단 SOC를 함께 만족했다.

AIDC는 과거 accepted라는 이유만으로 이전 스케줄을 실행 가능하다고 간주하지 않았다. 과거 Planning 후보는 현재 원본 WINDOWS의 허용 시작점과 불일치414개, 과거 Actual 후보는 원래 의도적 지연 예산 초과192개가 발견되어 둘 다 제외했다. 이는 원본 캠페인의 모든 acceptance 변환을 재감사한 판정이 아니라, 이번 입력에 그대로 옮길 후보가 strict 조건을 통과하지 못했다는 의미다. 제약을 완화하거나 새 IEEE8500 B1 성과로 쓰지 않았다.

Planning은 원본 B0 Reference에서 같은 사이트 단일-GPU Job 10개만 허용 시작점/서비스 슬롯/사이트 용량/WAN0 및 Rebound를 보존한 제한된 지연 witness로 구성했다. GPUh 변화는 0.000000이고 원래 Planning C1 affine envelope를 1.42e-14kW 오차로 재현했다. Actual의 exact C1로 Planning 모델을 바꾸지 않았다.

Actual은 원본 FCFS를 바탕으로 같은 사이트의 단일-GPU Job만 최대1개/사이트, 원래 허용 시작점과 QoS/Deadline/사이트 용량을 만족하는1~4슬롯 지연으로 제한해 확인했다. 피크 겹침 후보가 없어 AC 효과를 보지 않는 사전 기록된 사전순 하루 전체 후보도 확인했다. 실제 채택 Job 변경은 0개로 비영 Actual witness를 인증하지 못했다. 표의 Actual AIDC-only는 원본 FCFS 재생, Actual Joint는 MESS+변경하지 않은 AIDC다. 성공적인 비영 AIDC/공동 제어로 해석하지 않는다. GPUh 변화 0.000000, 이 제한 후보의 피크 감소는 0.000000kW이며 최대 사이트 감소/되받음은 0.000000/0.000000kW다. 이는 실제 최대 AIDC 제어력이0이라는 상한 증명이 아니다. 같은 exact C1을 실제 as-of 날씨에 적용해 무제어 전력을 0kW 오차로 재현했다. Job 수1,024를 전력량으로 치환하지 않았다. GPU gang>1·pre-site·checkpoint migration 등 더 넓은 실제 Job 제어 witness는 잔여 과제다.

상기 개선은 **AC 진단 Pilot**이며 B3 최적화 성과가 아니다. 관측된 가장 좋은 제한 후보와 최적가능량을 구분한다. 각각의 가장 좋은 물리 PASS 후보를 새 context Fresh로 재검증했다.

## 다음 단계

현재 허용 범위에는 Primary Scenario가 없다. beta/PCC/차량 정격·Job을 임의 변경하지 않았다. G4는 기존 r043 A1/M1/A2/M2, K48, Beam/Joint MILP의8대 변수·Route/SOC/PQ/입출력·독립 FULL 검증기, 전기적 전체 민감도/행 생성, P5 및 Actual TIME 계약, UB/LB/Gap/규모 측정 연결이 남는다. A1/M1/A2/M2나 장시간 Native Solver는0회다. 기존 V44/V1_add 소스·Worker·Monitor·예산·결과는 변경하지 않았다.
