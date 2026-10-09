# 공식 Balanced IEEE8500 P5 검증 — 한국어 최종 검토

**Balanced P5의 Planning96 / Actual96 / 각각 Fresh96 모두 실제 AC 전압·선로·변압기 제약을 통과했다. 고객 총 P/Q를 보존하면서 Triplex 최고값이 낮아졌고, 일별 전역 최고점은 중압 선로 `Line.ln6504019-5`가 결정한다.** 두 모델 차이는 부하 구성을 바꾼 효과이며 AIDC–MESS 최적화 개선율이 아니다.

| 항목 | Unbalanced Planning | Balanced Planning | Unbalanced Actual | Balanced Actual |
|---|---:|---:|---:|---:|
| 전체 최대 rho | 0.939955961 | 0.528279075 | 0.939831403 | 0.570974936 |
| Primary 최대 rho | 0.529585849 | 0.528279075 | 0.572277146 | 0.570974936 |
| Triplex 최대 rho | 0.939955961 | 0.468376642 | 0.939831403 | 0.467035775 |
| Vmin | 0.962436203 | 0.979170031 | 0.966540541 | 0.980022141 |
| Vmax | 1.041741567 | 1.041752129 | 1.040245991 | 1.040247149 |
| Primary 최대 슬롯 수 | 0 | 32 | 0 | 43 |
| Triplex 최대 슬롯 수 | 96 | 64 | 96 | 53 |
| 옛 tpx21459660c0 최대 슬롯 수 | 96 | 26 | 96 | 29 |
| 병목 전환 횟수 | 0 | 9 | 0 | 5 |


## Q1. 고객 총 P/Q는 일치하는가?

PASS. 1,177 고객별 ID, 연결 bus, 상위 Primary phase, PF.97, Model1, Vmin.88/Vmax1.05, Fixed/Variable을 전수 대조했다. 원본 합계 10,773.17 kW / 2700.010911176 kvar다. 최대 P/Q 잔차는 5.15e-14 / 1.33e-14이다. Balanced1177개 Load와 Unbalanced2354개 Load의 차이는 객체/레그 분배이며 고객 전력을 반감하지 않았다. 96슬롯 intended P/Q도 기존 P5 두 Load의 합과 오차1e-10 미만으로 일치한다. AC 두 레그 각 P/Q=총입력/2 최대 잔차 1.02e-08 kW/kvar다.

## Q2. 원본 3,703 Line / 1,177 Triplex가 유지됐는가?

PASS. 3,703개 Line(활성3,698, 원본 비활성5 포함), 1,177 Triplex, 1,190 Transformer와 8,531 node를 보존했다. LineCode·length·impedance·NormalAmps·CT nameplate·phase/node·Source DSS byte 변경은 0건이다. 전체 Line 양단·모든 CT conductor와 winding kVA를 보존한 archive로 검산했다. 원래 전체 `min rho_max`의 source-rooted parent-terminal 정의를 유지하며 별도로 더 보수적인 모든 양단/도체 thermal 검사도 통과했다. 다른 저압 Secondary category는 존재하지 않는다.

## Q3. Balanced P5 Planning/Actual 보안 제약은 통과하는가?

PASS. 두 96슬롯과 각각 Fresh96의 전압0.95–1.05, 원본 Line ampacity, CT winding current/nameplate kVA 위반은 모두0이다. RegControl/CapControl 자동 제어는 수렴·ControlActionsDone·빈 queue로 확인했다. 전압/전류/고객/PV/PCC/phasor 배열 및 제어 상태 Fresh 차이는0이다. 전력수지 최대 오차 3.61e-06 kW/kvar이며 Source 설정을 재조정하지 않았다. 두 모델의 P5 설정이 같아도 부하 변화에 따라 탭·capacitor 궤적은 달라진다.

## Q4. 전체 최대 선로부하율은?

Planning **0.528279075 pu**, Actual **0.570974936 pu**다. 최고 슬롯은 각각 72 / 73 (0-based)이며 `Line.ln6504019-5`의 local node2, 즉 Primary B상이다. 최고점에서 다음 선로까지 gap은 각각 5.24e-07 / 3.97e-07 rho이다. 인접 직렬 선로들이 사실상 함께 혼잡하므로 단 하나의 선로 개선만 보지 않아야 한다. [전체 category 최고 전류·정격·phase·slot](PRIMARY_TRIPLEX_LOADING_COMPARISON.csv) 및 [모든 binding96](BINDING_LINE_96SLOT.csv)에 실제값을 저장했다.

## Q5. Primary 최대값은?

Planning 0.528279075, Actual 0.570974936 pu다. 기존 Unbalanced의 0.529585849 / 0.572277146와 차이는 작다. 고객 총 소비전력이 같으므로 주 변화는 두 hot 전류와 LV 손실·전압이며 Primary 전력이 크게 줄었다고 해석하면 안 된다.

## Q6. Triplex 최대값은?

Planning 0.468376642, Actual 0.467035775 pu다. 기존 Unbalanced는 0.939955961 / 0.939831403 pu였다. [Top7 동일 선로 비교](TOP7_TRIPLEX_RELIEF.csv)에 고객전력을 보존한 구성 차이를 기록했다. 전체 고객의 불평형을 균등 배분하는 공식 case 전환 결과이며 임의의 단일 고객 감축이나 정격 확대가 아니다.

## Q7. 옛 Line.tpx21459660c0는 여전히 최대인가?

일별 전역 최고점은 아니다. 다만 Balanced Planning 26슬롯 / Actual 29슬롯에서 여전히 전역 최대다. 원본 Fixed 고객21459660c0의 30.52 kW는 기존30.183847622+0.336152378 kW에서15.26+15.26으로 재분배된다. BG.552 후 명목8.42352 kW씩이며 총부하는 그대로다. 156 A Triplex 정격, 고객 위치/경로와 연구 PV의 기존 hot별 비대칭은 유지된다. 다른 Fixed30.52 kW 고객 tpx227447984c0도 일부 시간 최대가 된다. 이들 static 고객의 전류 차이는 전압·PV·제어·상위 AEMO Variable 부하 영향이며 Fixed에 새 시간 형상을 적용한 것이 아니다.

## Q8. Primary가 전역 최대인 시간은?

Planning **32/96**, Actual **43/96**슬롯이다. 나머지 64 / 53슬롯은 Triplex다. 병목 전환은 9 / 5회다. 96축 및 전환 CSV를 보존해 중압 병목만 있는 것처럼 선택적으로 보고하지 않았다.

## Q9. AIDC–MESS가 실제 전체 최대 선로를 제어할 수 있는가?

**순간 AC에서 작지만 수치로 확인되는 제어 가능성은 있다. 96슬롯 정책 성능과 최적해는 아직 미검증이다.** Planning 최고점 72에서 24 PCC 모두 `Line.ln6504019-5`의 topology 하류지만 3상 AIDC와 단상 고객 STA는 상별 기여가 다르다. 중앙 ±1 kW/kvar fixed-tap 민감도와 자동 제어가 재동작하는 bounded endpoint를 구분했다. 독립 AIDC Q 조작은 실제 actuator로 인정하지 않고 PF.95의 coupled Q만 적용했다.

Planning 최고점: 여섯 초기 STA에서5 kW씩 방전하면 rho 0.524706012, 감소 **0.357306%p**다. 같은 슬롯 eligible-known AIDC P 상한 합계 **6.572687 kW**를 줄이면 감소 **0.087006%p**다. 합친 반사실은 rho 0.523836488, 감소 **0.444259%p**다. Actual 최고점에서 six-STA 반사실 감소는 **0.360212%p**다. Actual의 workload eligible mask를 Planning에서 추정하지 않아 Actual AIDC 감축량은 인증하지 않았다.

낮은 부하/Triplex binding 시간에는 상위 MV 감축이 원격 Triplex에 미치는 효과가 약하고 제어 재동작으로 증가할 수도 있다. 특정 상 STA의 충전도 B상 전류를 낮추는 경우가 있으므로 P의 부호만으로 개선을 가정하지 않는다. 직접 downstream 경로·상별 derivative·full-network endpoint·새 병목 전환을 모두 CSV에 기록했다. 모든 sampled 자동 endpoint는 원본 보안 제약 및 LV P±5/Q±3/S6/I27를 통과했다. 최대 실제 hot 전류는 24.463666 A다.

이는 당일 알려진 유연 job의 순간 전력 상한 및 초기 주차 위치의 가정이다. 동시에 실행 가능한 TS/PS/MG·마감시간·SOC·ETA/연결600초·차량 이동 스케줄을 증명하지 않는다. AIDC 시설 설치780 GPU 및 모든 idle/CC4 전력이 유연 부하라는 주장은 하지 않는다. 모든6차량의 Native/Actual/Fresh 연결은 기존 UNVERIFIED를 유지한다.

## Q10. Balanced IEEE8500을 V42 확장성 연구에 쓰는 것이 타당한가?

공식 synthetic 고객 hot 균형 시나리오로 **물리적·학술적으로 유효한 비교/확장성 후보**다. 실측 고객 프로파일 또는 완전 ABC 평형을 의미하지 않는다. Unbalanced 결과를 본 뒤 이 case를 추가했다는 이력을 명시하며 불리한 원본 P5 결과·SHA를 모두 보존했다. 본 결과만으로 논문 주 검증 계통을 결정하거나 유리한 B1–B3 결과에 따라 선택하지 않는다. 주 시나리오는 B1–B3 성과를 보기 전에 연구 목적과 공개된 물리 조건으로 별도 결정해야 한다.

계산 규모는 동일한8,531 node/3,703 Line/1,190 CT이지만 Load 객체1177개로 줄어든다. AC 통과는 Native scalability·6차량 QoS/이동·SOC 구현이나 글로벌 최적성 증명이 아니다. 데이터 as-of, full Native bridge, 실제 지리 좌표/접근/보호 승인, LV 보조 인버터 등 미검증 사유로 Production 승격은 차단한다. 276쌍552축은 동결한1 m 상당 공차와 하나의 proper similarity로 다시 검증했으며 **ASSUMED_PROXY_DIRECTION_PASS**다. RMS 형상 오차5.696 km 상당, 최대9.543 km 상당은 도식 proxy 오차이며 현장 지리 인증이 아니다.

## Q11. 450 kW MESS를 사용하려면 MV 접속 설계가 필요한가?

현재240 V LV 포트는5 kW/±3 kvar/6 kVA/27 A hot 제약이므로 **450 kW PCS 전체 사용에는 별도의 적격 MV 연계 또는 그에 맞는 고용량 인터페이스 설계가 필요하다.** 기존 service transformer/Triplex에450 kW를 주입할 수 없다. 차량 정격450 kW/600 kVA/1,800 kWh는 포트 정격과 분리했다. 단순 240 V450 kW의 약1,875 A를 현재 포트에 적용하지 않았다. 12.47 kV 3상에서450 kW unity-PF의 약20.84 A라는 산술 환산은 MV PCC 적격성·절연·보호·정격·역송전·전압 AC 승인을 대체하지 않는다. 이번에 STA 이동이나 신규 transformer/충전소를 추가하지 않았다. MV STA는 후속 연구 설계 후보다.

## 재현·보존·종료 상태

Balanced4일384슬롯 AC, full-axis/고객/PV/PCC/전력수지 독립 산술 검증, 5개Planning 및1개Actual 시점의 bounded sensitivity를 완료했다. 원본 입력·모델·기존 캠페인에 쓰거나 중단하거나 Scheduler를 변경한 횟수는0이다. 캠페인 원본 source/manifest SHA와 외부 관측 변화는 별도 before/after 문서로 저장한다. B1/B2/B3 Solver 및 Native 호출0, 시나리오 최종 동결0이다. 그림6쌍과 필수15개 결과, 부가 검증 CSV/JSON, Python source 및 SHA manifest를 같은 디렉터리 패키지에 포함한다. 경량 회귀 테스트와 PR 정보는 종료 receipt를 참조한다.
