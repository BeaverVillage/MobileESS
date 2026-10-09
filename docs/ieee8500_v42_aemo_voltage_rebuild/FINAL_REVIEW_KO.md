# IEEE8500 V42 호주 데이터 연결 및 전압 재검증

**P5는 B0 AC 물리 검증을 통과했다. 전체 Production 승격은 차단되어 있다.** Planning·Actual·각 독립 Fresh의 96슬롯에서 원본 전압·선로·변압기 위반은 모두 0건이다. 2025-05-01은 이미 사용한 개발일이며 독립 미노출 평가일이 아니다.

| 지표 | 이전 정적 PR193 | 새 P5 Planning | 새 P5 Actual |
|---|---:|---:|---:|
| 전체 최대 ρ | 0.921957508 | 0.939955961 | 0.939831403 |
| Primary 최대 ρ | 0.780215439 | 0.529585849 | 0.572277146 |
| Triplex 최대 ρ | 0.921957508 | 0.939955961 | 0.939831403 |
| Vmin / Vmax (pu) | 0.986703210 / 1.052725879 | 0.962436203 / 1.041741567 | 0.966540541 / 1.040245991 |
| 전압 위반 node×slot | 1,373 | 0 | 0 |
| 선로·변압기 과부하 | 0 | 0 | 0 |
| Triplex가 최대인 슬롯 | 96 | 96 | 96 |

**Q1. 호주 수요·PV가 누락되어 있었는가?**

PR193은 원본 고객 부하에 정적 BG를 적용했고 PV 객체가 0개였다. AIDC의 GFS/C1는 연결되어 있었지만 고객 부하의 AEMO 시계열과 Rooftop PV 전기 주입은 누락되어 있었다.

**Q2. 무엇을 어디에 연결했는가?**

VIC1 Forecast/Actual은 원본 2,306개 Variable Load의 P/Q 시간 배율에 연결했다. 48개 Fixed Load는 원래 Status와 정적 BG=.552를 유지한다. Rooftop Forecast/Actual은 원본 고객 버스·상에 접속한 2,354개 연구용 Generator에 연결했다. 설치용량 1,276.937105 kW/kVA는 양쪽에서 동일하다. 원본 IEEE8500에는 PV가 없었으며, 이 설비는 연구 overlay다.

GFS/NOAA는 각각 Planning/Actual의 12개 AIDC C1에, 원본 Kestrel/CC4/Runtime/reference/queue는 원래 780 GPU의 점유율과 시설 P/Q에 연결했다. Planning 1,649개 known UID와 Actual 2,498개 UID를 원본 archive에서 검산했다. 지역 MW를 직접 주입하지 않고 고정 V42 정규화로 시간 형상을 매핑한다. 개별 고객 실측 프로파일이라는 주장은 하지 않는다.

Demand Actual은 세 개의 5분 interval-ending 값을 평균해 15분으로 변환한다. 기존 말점 선택과의 지역 에너지 차이 14.319167 MWh를 수정했으며 원본 producer는 보존했다. Forecast/PV의 30분 평균은 두 번 반복해 에너지를 보존한다.

**Q3. Source·Feeder Vreg·CAPBank3 및 하류 Vreg의 효과는 무엇인가?**

P0/P1/P2/P3의 Planning Vmax는 각각 1.072682/1.067719/1.055985/1.054115 pu였다. Source 1.04만으로 충분하지 않았고, Feeder 123.5 및 CAPBank3 OFF도 위반을 완전히 제거하지 못했다.

긴급 지시 후 VREG3 세 상만 123.5 V로 낮춘 P4는 Planning Vmax 1.049872로 통과했지만 Actual 1.050016의 엄격한 위반 때문에 기각했다. 미리 등록한 다음 후보 P5는 **Source 1.04, 모든 12개 RegControl Vreg 123.5 V, CAPBank3 OFF**다. PR62에서 실제로 사용한 전체 Vreg 목표와 같다. 원본 deadband·탭 한계·지연·정격을 유지했고 모든 9개 CapControl의 감시 위치·임계값·재투입 조건을 변경하지 않았다. Actual은 후보의 하드 제약 기각에 사용했으며 Planning 입력 또는 B정책 성능 선택에 사용하지 않았다.

CAPBank0A의 원인은 다음과 같이 확인했다. P3 Planning slot48에서 ON이며 실제 444.409 kvar를 공급했다. 제어기는 Line.cap_3a terminal1의 q16642 A상 전압을 PTRatio=1로 감시한다. 실제 7,589.109 V(1.054108 pu)는 원본 Override 7,740 V(1.075066 pu)보다 낮다. 감시 Q는 −298.688 kvar여서 OFF 조건 −300 kvar에도 도달하지 않았다. ON 조건 200 kvar, ON/OFF 지연 100/80초, DeadTime 300초, Vmin 7,110 V를 확인했다. 이 Override 자체는 1.05 pu 전역 전압 상한을 보장하지 않는다.

같은 입력·탭에서 A상만 OFF하면 r42246.1은 Planning 1.054115→0.995363, Actual 1.044206→0.983956 pu로 내려간다. 그러나 전체 Vmax는 다른 상에서 각각 1.056962/1.067969 pu로 악화한다. 따라서 강제 OFF를 최종 정책으로 채택하지 않았다. B/C 개별 및 ABC ON/OFF 결과도 별도 CSV에 보존했다.

Actual의 최고전압은 slot45의 m1069517.2(B상)이며 r42246.1(A상)과 구분한다. 이때 CAPBank0 A/B/C는 모두 ON이었다. CAPBank0B는 441.063 kvar를 공급하고 감시 전압은 7,560.584 V(1.050146 pu), 감시 Q는 −298.903 kvar였다. B상 역시 7,740 V/−300 kvar의 개방 조건을 넘지 않았다.

VREG3-A는 P3에서 125±1 V이며 감시 전압 125.554 V는 deadband 안이었다. 탭 +2로 포화하지 않았고 정상 정착했다. 조정기 출력 1.046346 pu 이후 leading-Q 경로에서 r42246.1까지 전압이 상승했다. 최고전압은 제어 고장이나 탭 한계 때문이 아니다.

고정탭 PV OFF 반사실의 Vmax는 Planning 1.046608, Actual 1.046014 pu였다. Planning의 PV는 586.779 kW/Q≈0, CAPBank0A 공급은 444.409 kvar, VREG3-A 상위 흐름은 P=416.693 kW/Q=−281.842 kvar로 분리했다. **최종 P5에서는 PV를 유지한다.** 커패시터 임계값을 상한에 맞춰 임의 변경하지 않았다.

**Q4. 모든 96슬롯의 전압을 만족하는가?**

P5 Planning 0.962436203–1.041741567, Actual 0.966540541–1.040245991 pu다. 각 96슬롯과 각 독립 Fresh에서 위반 0건이다. 원본 8,531개 노드를 전수 검사했으며 반올림이나 제약 완화 없이 판정했다. Planning과 Actual은 별도 Source 초기화·자동 제어로 실행했고 Planning 탭을 Actual에 재생하지 않았다.

**Q5. 전체 최대 선로부하율은 얼마인가?**

Planning 0.939955961, Actual 0.939831403다. 이는 원래 V42의 source-rooted parent-terminal 목적함수다. 별도의 양단·전체 도체 감사 최대값은 각각 0.939955980/0.939831422이며 모두 원래 정격 이하다.

**Q6. Primary 최대는 얼마인가?**

Planning 0.529585849, Actual 0.572277146다.

**Q7. Triplex 최대는 얼마인가?**

Planning 0.939955961, Actual 0.939831403다. 원본 156 A 등의 NormalAmps와 1,190개 변압기의 원래 전류·nameplate 한계를 유지했다.

**Q8. 이전 Triplex 병목이 유지되는가?**

Line.tpx21459660c0의 local hot1이 양쪽 모두 96/96슬롯의 최대다. Binding line 변경 0회, Primary binding 0슬롯이다. Planning peak는 slot93, Actual은 slot70이다. Triplex hot1/2는 MV 상 명칭과 구분했다. 새 최대 ρ는 이전보다 높아졌다. 서로 다른 부하·PV·전압 정책의 차이를 B2/B3 개선율로 주장하지 않는다.

**Q9. AIDC·MESS가 최대 병목을 얼마나 제어할 수 있는가?**

Planning P5의 24 PCC×96슬롯×P/Q±1 고정탭 AC를 9,216회 실행하고, 별도로 자동 제어 정착 후 유한 교란을 계산했다. 사전 지정한 0/9/48/75슬롯과 추가 Planning 최대 부하율 슬롯93을 진단했다. 최대 Triplex 직접 하류에 AIDC·STA는 없다. 알려진 Job의 감축 가능 상한과 PF 결합 Q만 사용한 단일 AIDC 시험의 최대 완화는 0.000830984ρ(0.08310%p), 단일 STA의 ±5 kW/±3 kvar 시험은 0.001150374ρ(0.11504%p)였다. 이는 시험한 endpoint 최대이며 연속 영역의 최대가 아니다. Actual 96슬롯은 별도 B0/Fresh 검증이며 이 Planning 미분을 Actual 민감도라고 주장하지 않는다.

6개 초기 STA에서 −5 kW씩 주입한 순간 반사실은 -0.003346043–0.000442937ρ였다. 일부 슬롯에서 악화했다. 이 결과를 SOC·ETA·Job QoS/WAN을 만족하는 96슬롯 dispatch로 취급하지 않는다. 12 STA 동시 사용이나 모든 알려진 Job 동시 감축을 feasible schedule로 주장하지 않는다. 20개 병목 및 상위 5개 Primary의 미분·자동 endpoint·새 병목·전압·CT·저압 각 hot 전류를 CSV로 제공한다. AIDC 독립 Q 미분은 수학적 진단이며 실제 독립 Q actuator라는 뜻이 아니다.

**Q10. Production 준비 상태는 무엇인가?**

B0의 데이터 연결, 원본 full-network AC, 독립 Fresh, 물리 검산과 새 운전점 민감도 계산은 완료했다. B1/B2/B3 장시간 Native/Production 및 6차량 Native 호출은 0회다. 현장 geo/access/protection/LV 인터페이스, 6대 Actual SUMO/SOC/C3A 통합과 as-of-D1 calibration/GFS publication 증거는 UNVERIFIED다. Planning에 Actual 값은 0회 전달했지만 전체 calibration의 미래정보누수 0 인증을 하지 않는다. 이 한계 때문에 Production 승격을 차단한다.

SINGLE_SCENARIO_DRAFT.json은 단일 연구 초안이며 Production_configuration_frozen=false다. P5는 향후 B0–B3 공통 전압 정책 후보로 기록한다. 사용자 승인 전 최종 Production 설정을 동결하지 않는다. 기존 캠페인 편집·중단 호출은 0회다. 시작 시 소스·입력 1,105개의 SHA는 동일했지만 병행 작업 중 예약 등록 1개 추가/1개 변경이 관측돼 전체 scheduler 동일성 PASS는 선언하지 않는다. LIVE_CAMPAIGN_OBSERVATION.md에 범위를 구분했다.

필수 16개 산출물, Python SVG/PNG 8쌍, AC 배열·제어 상태·CSV·SHA manifest를 제공한다. REPRODUCE.md에 명령과 외부 raw archive 의존성을 기록했다. 독립 미노출 평가·실증 설치·글로벌 최적성·B3 개선 성능을 주장하지 않는다.
