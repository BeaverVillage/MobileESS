V2_add PR236의 G1 물리 매핑을 해소하고 G2 실제 B0 Scale Screening 및 G3 제한된 제어 Pilot을 추가했습니다. 기존59개 정적 검증/190행 SHA 및 공식 계통 복원은 재사용했습니다.

- PV: PR197의2354개 Hot Leg/.12kV/설치용량/Model1/Q0를 유지하고 V44의 총량을 고정 설치용량 가중치로 배분합니다. C2 AIDC12/STA12와 기존750kVA 변압기, V44 MESS8 P300/Q250/PCS400/SOC440~1080/초기종단760을 사용합니다.
- P5 source1.04/12Vreg123.5/CAPBank3 초기OFF를 모든 beta에 고정했습니다. IEEE123 Planning7/Actual43 및 Actual TIME/SVR12와의 차이를 명시했습니다. 연구용 정상상태 AC 가정이며 field 인증이 아닙니다.
- beta9개 × Planning96/Actual120 × 독립Fresh: **3888 운영 AC**, Fresh18쌍 PASS. 모든 기본 케이스의 전압/선로/변압기/포트 위반0. 모든 원본3703개 선로/1177Triplex/양단/상 포함, source disabled5개도 보존했습니다.
- Actual B0: beta1.00 **39.4819%**, beta1.50 **56.1469%**. 모든 beta가70% 미만이므로 **NO_QUALIFIED_HIGH_CONTROLLABILITY_SCENARIO**입니다. 후보 범위 밖 배율을 실행하지 않았고 Primary를 동결하지 않았습니다.
- beta1.50의 제한된 MESS96슬롯 Pilot은 Actual56.1469→55.9451%, **0.2018%p 감소**입니다. 새 MV 피크는 방전 종료 후19:00으로 이동했고1%p 선호 목표에 못 미쳤습니다. Planning의 감소는0.6023%p입니다. 순간 P/Q104점 중15점은 전압 등으로 실패했으며, 연결 PASS를 전체 PCS box의 무조건 운전 가능 인증으로 표시하지 않았습니다.
- beta1.00/1.50의 고정/자동제어 민감도와 beta1.50의 제한된 SOC·Job·QoS·Rebound Pilot을 구분했습니다. 과거 후보는 Planning 허용 시작점 불일치414개/Actual 지연 예산 초과192개로 제외했습니다. 새 Planning witness Job10개는 GPUh 변화0으로 검증했으나 Actual 비영 AIDC witness는 미인증입니다. Actual AIDC-only는 FCFS 재생, Joint는 MESS+변경 없는 AIDC이며 공동제어 추가효과로 주장하지 않습니다. Pilot을 B3로 표시하지 않습니다.

G1 PASS / G2 COMPLETE / G3 PARTIAL(MESS·Planning witness PASS, Actual 비영 AIDC NOT_VERIFIED) / G4 NOT_VERIFIED. A1/M1/A2/M2 및 장시간 Native0회. 기존 V44/V1_add Source·Worker·Monitor·예산은 변경0입니다. 전체 scalar/Top20/TapCap CSV, raw AC 경로/SHA, 독립 saved-array 재산술, Python SVG/PNG4쌍 및 실패 endpoint를 보존했습니다.

진입점: docs/v2_add/README_KO.md. 핵심 보고: FINAL_V2_ADD_REVIEW_KO.md, PREFLIGHT_GATES.json, BACKGROUND_SCALE_SCREENING.csv. Draft 유지; merge/Production 승격 요청 없음.
