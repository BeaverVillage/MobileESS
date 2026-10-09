# 단일 공동 PCC 연구 시나리오 결정

선정은 **C2, BG=0.85, 원본 설치 GPU 합계780, AIDC12·STA12·MESS6**이다. STA는 중압12·저압0이고 원본 ABC 12.47 kV 버스에 별도 750 kVA·12.47/0.480 kV 전용 변압기와 480 V 3상 포트를 모델링했다. 모든 원본 선로·서비스 변압기·전압0.95–1.05 pu 제약 및 전체 `min rho_max` 목적은 유지했다. 원본 DSS와 기존 캠페인, Native/Adaptive/RMP/Pricing/독립 UB/LB 알고리즘을 바꾸지 않았다.

입지·8권역·권역 cap·C1의6MV/6LV parity 및 C2의12MV가 점수와 정책 결과 전에 사전등록됐다. 최종 점수는 기존 C0·BG0.85 B0의 복수 혼잡선로/시간 ±1 kW/±1 kvar AC에 기반하며 6시간 자료와 peak74 보충 자료를 구분 보존했다. 공통 proper similarity135°에서 276쌍/552축·24개 버스 고유성·분산 제약이 PASS였다. 전역 최적화가 아니라 점수 우선순위의 첫 완전 공동 witness이며 overlap은 감사했으나 최적화하지 않았다.

Planning으로만 C1/C2×BG[0.552,0.65,0.75,0.85,0.95] 10개 B0 96슬롯을 검사했다. 원본 제약 PASS·전체ρ0.75–0.85 후보 중 C2 우선, 0.8에 가까운 값, 작은 BG 순이라는 동결 규칙에 따라 C2/BG0.85를 선정했다. Actual·MESS 효과·B1/B2/B3 결과는 입지·BG·GPU·포트 정격 선택에 사용하지 않았다. 선정 당시 B0 peak는 slot74의 Line.ln6504019-5 node2이다.

| 입력 | B0 전체/Primary/Triplex 최대ρ | MESS=적용 Joint 전체최대ρ | B0 Vmin/Vmax | 전압/선로/변압기 위반 |
|---|---|---:|---|---|
| PLANNING May01 | 0.810230773 / 0.810230773 / 0.730790494 | 0.804653414 | 0.964367216 / 1.041439225 | 0/0/0 |
| ACTUAL May01 | 0.848320702 / 0.848320702 / 0.731301776 | 0.841617405 | 0.957889181 / 1.041593772 | 0/0/0 |

Planning/Actual 각각 B0·MESS와 별도 Fresh compile을 포함한 May01 8개 완전96슬롯 결과의 모델 전기 적격성은 **PASS**다. 이 결과는 현장 설치 인증 또는 AIDC 비영 유연성·B1/B2/B3 Production 인증이 아니다. 최신 날짜 지시는 May01-only이며 May02 입력/과거 결과는 보존하고 새 공동 선정·효과 검증에서 제외했다. Forecast와 private Actual의 paired replay이며 미노출 독립 검증일이라고 주장하지 않는다.

**완전 P450/Q300 제어 영역은 NOT_CERTIFIED다.** 별도 순간 finite endpoint190개 중20개가 P=-450 kW·Q=-300 kvar injection에서 과전압으로 FAIL했고 최고전압은1.068246498422 pu였다. line/TX/port-limit 위반0은 과전압을 상쇄하지 않는다. 선택한 완전96 Q0 schedule의 PASS를 임의 Q정책 지원 PASS로 확대하지 않았다. 정격·위치·제어 목표를 바꾸어 통과시키지 않았다.

차량은 P450 kW·S600 kVA·E1800 kWh·Emin660/Emax1620·initial/terminal1140 kWh다. 중압 포트의 실제 상전류 한계는721.687836 A이며 kVA circle만으로 통과시키지 않았다. 원본6개 초기 STA에서 이동0·600초 초기 연결 가정·slot0 차단·STA당 차량1·Q0의 고정 feasible proxy schedule을 사용했다. 충전slot8–15, 방전68–75는 효과 결과 전에 결정됐다. M3의 nominal P450과 실제 schedule 출력은 다르다. 배터리 headroom480 kWh/2h·효율0.95로 충전은252.631579 kW/대, 방전228 kW/대로 제한된다. M2/M3가 같은 이 고정 schedule을 가질 수 있으며 이는 M3 완전450 kW 운전이나 최적 schedule을 인증하지 않는다.

비영96슬롯 AIDC QoS/WAN/checkpoint 실행가능성을 검증하지 못했으므로 이번 연구에서 적용한 admissible AIDC action은0이다. 이는 실제 물리적 유연 잠재력이0이라는 증명이 아니다. 원본 Job·PF0.95·Reference/Queue/C1과 known-mask relaxation은 보존했다. 따라서 이 조건부 모델 AC/SOC 기록에서 AIDC-only=B0, Joint=MESS-only이며 관측 추가 이득은0, 비영 AIDC 공동 기여는미입증이다. 순간 known-mask 또는6STA endpoint는 정책 개선율이 아니다.

C2는 원본 트리8권역 중7권역을 덮지만 STA–STA66쌍 모두 frozen screening P-response cosine≥0.95이고 중앙값0.998440·support Jaccard1.0이다. 3개 named major lateral 라벨과 TRUNK_OR_MINOR_LATERAL 집계 bucket에 걸쳐 있다는 사실을7개 독립 feeder나4개 독립 physical lateral로 바꾸어 표현하지 않는다. 실제 전기적 제어 독립성·공동 추가 이득은 UNPROVEN이다.

하드웨어/GIS·이동의 한계는 **ENGINEERING_SCENARIO_NOT_FIELD_VERIFIED / UNVERIFIED**다. 750 kVA·5.75% |Z|·12.47Δ/0.480Y 사양은 상용 topology 근거를 사용했으며 %R=1, XHL=5.662375826%, noloadloss0.2%, imag0.5%, node0 solid grounding은 연구 가정이다. 실제 mobile600 kVA 제품/DC interface/온도 derating, short-circuit·relay/fuse coordination·역송전 승인·anti-islanding·접지·현장 road access·도식 CRS는 미인증이다. 원본 추상 traffic ETA를 새 PCC의 실측 접근시간이라고 부르지 않는다. 현장 승인 export 기본값0과 시뮬레이션 reverse injection을 구분한다.

최종 map SHA: `900dec7fd8f16da4356bb109f2b629fa781c34de3ec94932d00264622fa5dd5a`. top-level JOINT_LOCATION_SELECTION.csv는 선택한 원본 파일의 byte-identical copy다. 배치·BG는 검증 후 효과로 재조정하지 않았으며 source SHA와 모든 실패 endpoint를 보존했다. B1/B2/B3 장시간 Solver 호출은0이다. 새 MV 및6대 DTO Native/grid interface, 실제 비영 AIDC96QoS, 현장 하드웨어/보호/GIS gate가 해결될 때까지 Production 승격은 차단한다.
