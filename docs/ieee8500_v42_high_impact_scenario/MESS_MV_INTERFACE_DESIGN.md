# MESS 중압 연계 설계와 실제 후보 적격성

현재 STA 12곳의 고객 측 120/240 V 포트는 보존한다. 같은 위치 Proxy의 상위 Primary 버스는 모두 단상이다. **동일 Proxy에 M1/M2/M3를 설치할 수 있는 적격 3상 호스트는 0곳**이다. `.1.2.3`를 붙여 누락된 상을 만들거나 450 kW를 기존 Triplex에 주입하지 않았다.

별도 위치 변경 시나리오를 사전등록해, AIDC 12곳을 고정하고 source proximity guard를 통과한 원본 606개 12.47 kV ABC 버스를 검토했다. 선정 순서는 기존 Proxy와의 형상 거리이며 AC 민감도·병목선로·정책 성능을 사용하지 않았다. 기존 프레임에서는 STA01·02·05·06·07·10의 후보가 없고 3,636개 거절 증거를 출력했다. 고정 AIDC 12곳의 132개 축 조건을 만족하는 전체 공통 회전은 191.3192150747514°–191.82333172004934°의 열린 구간뿐이다. 이 구간 전체에서도 STA01·STA02·STA05·STA06·STA07·STA10의 적격 MV 후보 수는 각각 0이다. 원본 십진 좌표를 유리수로 계산한 전 각도 후보 구간 증명으로, 현재 AIDC 고정과 606개 후보 집합에서 공동 MV 재배치는 불가능하다. AIDC 재선정이나 새로운 Primary 배선을 포함한 다른 문제의 불가능성을 주장하지 않는다.

따라서 아래 M1–M3는 **UNAVAILABLE_AT_CURRENT_STA_AND_FIXED_AIDC_GEOMETRY**인 기술 설계 후보다. 현재 IEEE8500에 새 변압기를 설치한 적격 시나리오라고 표현하지 않는다. 실제 추가 변압기는 0개다. L0만 기존 연구 포트에서 실행할 수 있다.

| 인터페이스 | 차량당 P 한도 | 차량/설계 포트 S 한도 | P 한도에서 Q 원 상한 | 연결 |
|---|---:|---:|---:|---|
| L0 | ±5 kW | 포트 6 kVA | 별도 ±3 kvar | 기존 120/240 V, hot 전류 27 A |
| M1 | ±150 kW | 600 kVA | 580.947502 kvar | 적격 ABC Primary → 전용 변압기 → 480 V 3상 |
| M2 | ±300 kW | 600 kVA | 519.615242 kvar | 같은 구조 |
| M3 | ±450 kW | 600 kVA | 396.862697 kvar | 같은 구조 |

차량은 6대·450 kW·600 kVA·1,800 kWh를 유지한다. P²+Q²≤S²를 항상 적용하고, 현장 포트/변압기/도체/전압/SOC/ETA 제약은 추가로 출력을 줄일 수 있다. Q를 원 한계까지 쓸 수 있다는 표는 기술적 산술 상한이며 계통 허용 판정이 아니다. 각 STA 동시 접속은 1대로 가정한다. 3상 명령 P/Q는 총량의 1/3씩이며, 실제 전류는 불평형 전압과 변압기 손실을 포함한 AC로 읽어야 한다. 450 kW 전부를 B상에 넣지 않는다.

가정한 전용 변압기는 750 kVA, 12.47 kV delta / 480Y/277 V이며 tap=1 고정이다. [ELSCO의 750 kVA 상품](https://elscotransformers.com/transformers/dry-type-transformers/750-kva-12470-delta-to-480y-277/)은 이 전압과 결선 조합의 상용 가능성을 뒷받침한다. 이는 실제 특정 STA의 승인 또는 납품 자료가 아니다. [Eaton CA202003EN](https://www.eaton.com/content/dam/eaton/products/utility-and-grid-solutions/transformer/pad-mounted-transformer/Eaton-Pad-mounted-Transformer-Brochure-EN-US.pdf)은 750 kVA 및 5.75% 임피던스와 delta–wye 중성점 접지 구성을 명시한다. 이 두 상품의 사양을 단일 구매품 인증으로 합치지 않았다.

연구 모델의 |Z|=5.75%는 위 카탈로그 범위로 정하고, 총 R=1.0%를 두 권선 0.5%씩 나누는 것은 **미실측 설계 가정**이다. 따라서 XHL=√(5.75²−1²)=5.662375826453%로 계산한다. XHL에 |Z|를 그대로 대입하지 않는다. 무부하손실 0.2%·여자전류 0.5%도 가정이며 구매품 시험성적서가 없다. 두 권선 정격 및 Normal/Emergency kVA는 750으로 동일하다. 750 kVA 정격 전류는 HV 34.724355 A, LV 902.109796 A이다. [EPRI Transformer Properties](https://opendss.epri.com/Properties16.html)의 3상 LL 전압·권선 R·XHL 정의를 적용했다.

480 V 600 kVA 포트의 명목 전류는 721.687836 A이다. [Dynapower MPS-125 자료](https://dynapower.com/wp-content/uploads/2021/12/MPS-125_Datasheet_Dec2021.pdf)는 480 V 3상 125 kVA/125 kW 모듈을 제시하며 [제조사 제품 설명](https://dynapower.com/products/energy-storage/mps-125-energy-storage-inverter/)은 병렬 구성을 허용한다. 5개 모듈 625 kVA에서 600 kVA로 제한하는 구성은 규모의 근거가 될 수 있지만, 차량에 이 PCS가 설치됐다는 주장이나 정확한 600 kVA 이동형 제품 인증이 아니다. 차량 DC 전압·커넥터·온도 디레이팅·배터리 호환성은 UNVERIFIED다. 최고효율을 96슬롯 충방전 효율로 대신하지 않고 기존 V42 효율을 보존한다.

모델은 LV `.1.2.3.0`, Rneut=0인 이상적 고정 접지를 사용한다. HV delta는 LV 영영상 전류를 HV 선로로 전달하지 않는 결선 선택이며 현장 접지 인증이 아니다. [EPRI Neutral Rules](https://opendss.epri.com/OpenDSSNeutralRules.html)에 따라 중성점과 접지 임피던스를 명시했다. 접지전극, 접촉/보폭전압, 단선 및 지락 동작은 검증되지 않았다.

[IEEE 1547-2018](https://standards.ieee.org/ieee/1547/5915/)의 전압/무효전력, 비정상 전압·주파수, 전력품질, 단독운전, 상호운용과 시험 요구를 검토 대상으로 둔다. [NREL의 단독운전 보호 해설](https://www.nrel.gov/docs/fy22osti/77782.pdf)에 근거해 정적 AC 통과를 anti-islanding/보호 적격성으로 승격하지 않는다. 현장 릴레이·퓨즈·recloser 협조, 변압기 여자돌입, 고장시 PCS 전류와 지속시간, 차단용량, 원격 차단, utility export 승인 및 IEEE 1547.1 시험 자료가 없다. 모두 **UNVERIFIED**, 설계 상태는 **ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED**다. 현장 승인된 역송전 한도는 입증된 값이 없어 0으로 둔다. 연구 반사실의 양방향 P/Q 허용 가정은 이와 구분한다.

변압기와 무한대 강도 HV 전원을 가정한 LV 3상 단락 전류 산술 화면은 15688.866011 A다. 이는 실제 계통 단락해석, PCS 기여, 차단 duty 또는 PASS 증거가 아니다. 현재 3상 호스트 자체가 없으므로 이 숫자로 사이트 적격성을 판정하지 않는다.

교통 노드 24개, MESS 6대, 기존 도로·ETA·거리·연결 지연 파일의 SHA를 MV_RELOCATION_PREREGISTRATION.json에 봉인했다. 새로운 MV 위치의 형상 거리로 도로 거리를 환산하지 않았다. 위치 변경 시 실제 ETA·이동에너지·현장 접근성 재검증은 UNVERIFIED이며, 기존 서비스 노드 ETA를 쓰는 것은 추상 연구 Proxy 가정에 한정한다.

재현: `python -B -m ieee8500_v42_high.mv_design --relocate` 다음 `python -B -m ieee8500_v42_high.mv_relocation`. 단상 거절·P/Q 원 한도·전용 변압기·3상 전력 readback은 MV_COMPONENT_REGRESSION.json의 별도 작은 구성요소 회귀로 검증한다. 이것은 실제 IEEE8500 MV 접속 입지 또는 96슬롯 운전 적격성 증거가 아니다. 기존 원본 선로 3,703개·Triplex 1,177개·변압기 1,190개와 DSS 31개는 변경하지 않았다.

구성요소 AC에서 P=150 kW/Q=580.947502 kvar인 600 kVA 충전 명령의 실제 LV 전류는 약 758.47 A였다. 480 V/600 kVA의 명목 전류 한도 721.687836 A를 초과하므로 이 끝점은 포트 전류 FAIL이다. S 원 제약만으로 저전압에서의 전류 제한이 보장되지 않으며, 향후 MV 포트 구현에서는 상별 실제 전압·전류에 따른 추가 디레이팅이 필요하다. MV_COMPONENT_REGRESSION의 PASS는 파라미터와 상별 전력 readback 검사만을 뜻하고 모든 끝점의 물리적 PASS가 아니다.

출처 원문 바이트를 보존한 자료는 mv_sources와 MV_SOURCE_EVIDENCE.json에 SHA를 기록했다. 서버 오류로 원문 바이트를 내려받지 못한 자료는 FETCH_UNVERIFIED로 표시했으며, 별도 Primary 웹 도구로 읽은 근거 추출은 MV_PRIMARY_WEB_FACTS.json에 보존했다. 이 추출 SHA를 내려받지 못한 원문 전체의 SHA라고 주장하지 않는다.

## 별도 AIDC–STA 공동 재선정 진단의 추가 결과

위 불가능 판정과 M1–M3 UNAVAILABLE은 **기존 AIDC 12개 버스를 고정한 문제**에 한정한다. 이후 사용자 지시에 따른 별도 공동 형상 진단에서는 AIDC 고정을 해제하되 v3 전기 적격성·source guard·원본 606개 ABC 후보·24개 서비스 ID·276쌍 방향을 유지했다. 사전등록한 135° 공통 회전에서 24개 모두 MV인 witness를 확보했으며 276쌍/552축이 모두 PASS다. AIDC 10곳이 변경됐다. 기존 저압 및 기존 P5 결과는 별도 보존된다.

JOINT_MV_GEOMETRY_DIAGNOSTIC_MAPPING.csv의 STA 12곳은 전용 변압기 연구 설계를 검토할 수 있는 **별도 원본 MV 호스트 후보**다. Master.dss Fresh compile의 ABC/12.47kV/원본 좌표와 source guard는 JOINT_MV_HOST_SOURCE_AUDIT.csv에서 확인했다. 이것을 M1–M3 설비 또는 96슬롯 운전 적격성 PASS로 승격하지 않았다. 향후 새 연구 overlay에 전용 변압기 12개를 설치하는 경우 원본 1,190개와 명확히 구분해 각 신규 권선·480V 노드·PCS 상전류·전력 손실을 다시 AC로 검증해야 한다.

공동 진단은 AC 효과를 읽지 않은 형상 우선 결과다. 실제 GIS·접근성·물리 ETA·단락/보호·현장 접속 승인과 exact600kVA 차량 하드웨어 호환성은 계속 UNVERIFIED다. 최종 Production 또는 단일 운전 시나리오를 동결하지 않았다.
