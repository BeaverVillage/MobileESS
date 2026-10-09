# PCC 설비 적격성: 원본 설비·역사적 설계·현장 포트 구분

원본 `Master-unbal.dss`에는 1,190개 변압기, 3,703개 선로, 2,354개 고객 Load가 있다. 원본 120/240 V 서비스 변압기와 고객 측 Triplex hot1/hot2 연결은 실제 OpenDSS 원본으로 확인했다. 원본 전용 AIDC PCC 1,500 kVA 변압기와 MESS PCC 750 kVA 변압기는 **0개**다. 원본에 고객 저압 선로가 있다는 사실은 차량용 접속 커넥터·PCS·절연·동기화·차단기·보호 계전·역송전 허가·차량 접근성이 존재한다는 증거가 아니다.

역사적 `IEEE8500_pcc_overlay_20260911/STATIC_PCC_REFERENCE_PROVENANCE.json`은 당시 연구의 명시적 사용자 설계 정격으로 AIDC 1,500 kVA, MESS 750 kVA를 기록한다. V41 정적 4.16/0.48 kV 템플릿을 IEEE8500의 12.47/0.48 kV에 맞췄고 XHL=5.75%, %Rs=[0.8,0.2], 3상 wye/wye를 사용했다. overlay는 AIDC 12개와 MESS 24개의 독립 변압기 분기를 새로 추가한 연구 설계다. 원본 IEEE8500의 기설 설비 증명이 아니다. 원본 템플릿 SHA는 `ba13e3081df606c18d61f1e02300b23f7be00dc2d22bc4c8064d04f40beec719`, 정격 contract SHA는 `4da7937328e8d76eed63cc7630144784796a6a5537d99fbd8b626c1fd8b546c9`, 역사적 IEEE8500 overlay SHA는 `0dfc0bbdbdb269fda18d88860d99fce13c28a6aca9ad1b0265c5b9a924fbb5de`이다.

당시 검증 결과는 `PASS_IEEE8500_ADDITIVE_PCC_OVERLAY_ZERO_INJECTION_STRUCTURAL_VALIDATION`이고 운영 부하를 넣은 explicit_operational_solve_count=0다. 정격과 정적 전기 모델의 출처는 확인했지만 현재 V42 GPU/Rack/시설·부하·MESS 운영 적격성까지 통과했다는 뜻이 아니다. 역사적 launcher·Solver·overlay는 실행하지 않았고 파일은 읽기만 했다. 현재 공동 재선정에서 host가 이동하면 기존 설계 정격을 참고할 수는 있으나 새 host의 변압기·회선·접속·보호 설계가 성립한다는 장소별 가정과 검증이 필요하다. 이번 AC 엔진의 MV_3PH는 원본 MV bus에 균형 3상 수요/주입을 모델링하므로 상류 계통 반응을 측정한다. 이 모델만으로 전용 변압기 하류 시설 전압·정격·장치 존재를 입증할 수 없다.

저압 모델은 서로 다른 세 방식을 구별한다: LV_SPLIT_240은 단상 delta를 `.1.2`, kV=0.24에 연결하여 두 hot에 같은 크기·반대 방향의 전류를 만든다. LV_LEG1_120과 LV_LEG2_120은 단상 wye를 각각 `.1.0`/`.2.0`, kV=0.12에 연결한다. 모든 방식은 원본 node 연결과 고객 부하를 보존했고 실제 DSS P/Q·도체 전류·전력수지로 검증했다. 이들은 **가상 전기 응답 모델**이며 접속 장치의 설치 승인을 의미하지 않는다. 120 V 모델의 node0은 원본 접지 기준이며 실제 중성선·접지 귀로의 분담은 원본 Kron 모델에서 분리되지 않는다.

원본 4/0Triplex의 hot NormalAmps=156 A는 명목 240 V 균형 연결에서 37.44 kVA, 120 V 한 hot에서 18.72 kVA에 해당한다. 750_Triplex의 580 A는 240 V에서 139.2 kVA다. 이는 단순 명목 전압×hot 정격의 전류 환산값이며 실제 차량 출력 허용량은 아니다. 실제 전압, 기존 부하와의 복소 전류 합, 서비스 변압기 각 권선의 원본 kVA, 접속장치 정격, 역송전 보호, 중성선 및 전압 제약을 함께 확인해야 한다. 대당 450 kW/600 kVA를 저압에 그대로 허용할 수 없다. 원본 변압기의 DSS NormalAmps와 NormHkVA는 전류 정상 정격을 보존하되 각 권선 kVA의 엄격한 nameplate 한계도 별도 검사했다. 기본 NormHkVA=110%를 nameplate 제약으로 대신 쓰지 않았다.

동일 PCC 차량 합산에는 차량별 PCS 600 kVA 원제약과 위치별 연결 모드·상별 전류, 합산 P/Q 및 공유 회선/변압기 한계를 동시에 적용해야 한다. 차량 6대, 경로·SOC·이동시간·이동에너지·도착/출발을 보존하며 서로 다른 포트에서 같은 출력을 이중 집계할 수 없다. AIDC 유연성 범위는 최신 V42의 원본 Job/GPU·동시 실행·Rack·PUE·냉각·QoS·WAN·Deadline로 계산해야 한다. 1 kW 또는 0.1 kW의 작은 주입 응답이나 정격 자체는 실제 이동 가능한 Workload와 MESS 가용성을 증명하지 않는다. 설치 GPU 수를 늘려도 원본 Job를 복제하거나 임의 유연성 비율을 만들 수 없다.

원본 Triplex는 양단 접지된 중성선을 Kron reduction으로 제거했다. 따라서 모든 명시적 hot 전류는 원본 정격으로 검사했고, `-(Ihot1+Ihot2)`의 벡터합을 implied-neutral 감사값으로 추가했다. 독립 중성선 ampacity는 원본에 없으므로 값을 만들거나 hot 정격을 중성선에 대입하지 않았다. 해당 정보가 없으면 중성선·보호를 포함한 현장 포트 적격성은 미입증이다. 원본 Master가 실제 로드한 보호 객체 class count는 {}이며 원본 폴더의 별도 `Fuses.DSS`가 있다는 이유로 Master에 활성화된 보호 장치를 가정하지 않았다.

원본 BG=1.0/AIDC=MESS=PV=0의 전류 병목은 다음과 같다. 목표함수는 원본 NormalAmps와 source-rooted parent terminal의 hot/상 전류이며, 다른 단자와 추정 중성선은 별도 감사다. 상위 20개 전체는 `ORIGINAL_TOP20_LINE_CONGESTION.csv`에 있다. 이 목록은 원본 진단이며 재선정의 B3 성능 점수나 최종 시설 스케일 선정 결과가 아니다.

| 순위 | 원본 선로 | 구분 | local node | 전류 A | 원본 NormalAmps A | 부하율 pu |
|---:|---|---|---:|---:|---:|---:|
| 1 | Line.tpx21459660c0 | Triplex | 1 | 273.658 | 156 | 1.754217 |
| 2 | Line.tpx260595c0 | Triplex | 2 | 256.695 | 156 | 1.645483 |
| 3 | Line.tpx226308719b0 | Triplex | 1 | 255.390 | 156 | 1.637112 |
| 4 | Line.tpx226308710b0 | Triplex | 2 | 251.007 | 156 | 1.609022 |
| 5 | Line.tpx21197413c0 | Triplex | 1 | 248.151 | 156 | 1.590709 |
| 6 | Line.tpx2224230689c0 | Triplex | 2 | 242.663 | 156 | 1.555529 |
| 7 | Line.tpx226308725b0 | Triplex | 2 | 237.730 | 156 | 1.523908 |
| 8 | Line.tpx226192801c0 | Triplex | 2 | 218.494 | 156 | 1.400604 |
| 9 | Line.ln6291242-1 | Primary | 1 | 556.951 | 400 | 1.392378 |
| 10 | Line.ln5654466-1 | Primary | 1 | 556.951 | 400 | 1.392377 |

현재 증명 가능한 범위는 원본 연결·전압·전류·정격과 가상 P/Q의 AC 응답, 역사적 연구 PCC 설계의 정격·출처다. 새 24개 위치의 실제 장치·보호·교통 접근·설치 GPU/Rack/냉각·시계열 배경부하가 확보되지 않은 부분은 명시적 연구 가정 또는 미검증으로 유지한다. AC 응답이 좋다는 이유로 이 항목들을 승인하거나 Production 적격성을 선언하지 않는다.
