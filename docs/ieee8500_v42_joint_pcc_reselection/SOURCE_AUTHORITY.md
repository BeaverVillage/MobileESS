# 공동 PCC 재선정: 원본·교통·검증일 권한

고정 부모는 PR197 `35079f458fc9d87a469ebd79e0e5d2cb7bd5fe1e`다. 원본 feeder·Job·Rack/GPU·V42 알고리즘과 기존 캠페인은 변경하지 않는다. 계승 V42 소스 권한 `625bbcb8b9a54a00c1660c26d96f7737c2f75457`은 이 작업이 검토한 기준이며 현재 원격 최신 HEAD라는 주장은 하지 않는다. `../ieee8500_v42_high_impact_scenario/SOURCE_AUTHORITY.md`와 `SOURCE_AUDIT.json`에 Forecast/Actual/GFS/NOAA/Kestrel source SHA, 원본 순수 Reference/Queue/C1 pipeline의 부모 Git blob 일치 및 as-of 미해결 항목이 있다. 새 MV 접속의 Native/grid/six-axis API 호환성과 정격·보호·현장 접속은 별도 검증이다.

기존 24개 교통 서비스 `IDC01..IDC12, STA01..STA12`와 원본 TN road-node를 보존한다. AIDC 논리 ID는 route service `IDC`에만 명시적으로 대응시킨다. service CSV의 `feeder_bus`는 오래된 원본 서비스 registry 필드이며 새 IEEE8500 PCC의 접속 버스 권한으로 쓰지 않는다. 새 전력 PCC 좌표는 원본 Buscoords/명시한 LV primary proxy이고, 하나의 proper similarity 아래 552개 strict 방향 검사는 새 mapping의 별도 geometry audit에 속한다. 도식 방향을 만족해도 교통 road-node와 새 PCC가 현장에서 같은 장소라는 근거는 아니다. 거리·방향 fidelity, 측량 GIS·진입로·보호·접속권은 UNVERIFIED다. 기존 fixed-AIDC 불가능성을 AIDC도 해제한 후보 공간의 불가능성으로 확대하지 않는다.

`ieee8500_v42_joint/traffic_eta.py`는 SHA가 검증된 portable 원본 route/forecast/static graph/vehicle physics를 읽고 새 route를 만들지 않는다. 출력 `TRAFFIC_ETA_ACCESS_AUDIT.csv`는 원본 6대 초기 위치 `STA01, STA12, STA08, STA06, STA03, STA10`에서 각 STA 12곳으로 출발하는 6개 사전등록 slot `0,9,48,68,72,75`의 432개 가상 단일 이동이다. 각 행의 source ETA는 원본 Q50+기존 safety calibration이며 Q90로 대체하거나 다시 맞추지 않는다. source road path 연결성, 5분 traffic forecast의 원본 departure snapshot 합, physical-edge 거리, 28,000 kg 원본 longitudinal energy, 600초 연결 지연과 ready offset을 직접 검증한다. 전체 55,296개 원본 route key와 raw/container/decoded SHA도 보존한다.

원본 same-site stay의 route ETA·에너지·ready offset은 0이다. 새 연구의 초기 접속은 600초가 필요하다는 명시적 가정으로 slot0 전체를 차단한다. canonical route offset을 바꾸지 않고 effective readiness를 별도 열에 기록했다. 연결 용량은 STA당 차량 1대로 사전등록했으며 여러 차량의 가상 단일 이동 행을 동시에 실행 가능한 fleet schedule로 합치면 안 된다. 각 행의 SOC는 초기 1140 kWh에서 그 단일 이동의 source-safe energy만 뺀 값이고, E_min=660 kWh 검사만 한다. 실제 전체 이동·충방전·terminal SOC·동시 접속·Actual committed SUMO gate의 인증이 아니다. 현재 Native의 원본 4대와 사용자 연구 6대 DTO 호환성도 별도 미검증이다.

전력 PCC를 재배치하더라도 현재 연구 모델은 기존 추상 서비스 ID/ETA를 유지한다. 따라서 `source_route_distance_km`는 **원본 service-road-node 사이의 모델 거리**이며 새 PCC까지의 실거리로 주장하지 않는다. MV용 150/300/450 kW·750 kVA 접속설비와 LV 5 kW/3 kvar/6 kVA/27 A는 원본 차량 450 kW/600 kVA/1800 kWh와 별도 인터페이스 정격이다. 도로 물리 모델의 28톤은 유지했지만 새 1800 kWh pack에 대한 실제 질량 적합성은 UNVERIFIED다. 선택 이후 실제 AC 및 SOC/occupancy/route gate가 필요하며 metadata input PASS를 field-ready 또는 B1/B2/B3 정책 효과 PASS로 확대하지 않는다.

날짜 May02 원본 입력은 source-backed이며 원본 288개 Actual 5분 수요를 3개씩 평균하고 PV 30분 값을 반복해 MWh를 보존한다. 다만 May02는 IEEE123에서 이미 관측되었고 이번 앞선 IEEE8500 high-case AC에서도 관측되었다. 새 공동 입지의 May02는 고정된 배치에 대한 **별도 paired engineering check**이며 미노출 IEEE8500 holdout이라고 부르지 않는다. Actual 결과로 입지·BG·GPU·PCC 정격·출발 slot을 다시 선택하지 않는다. GFS publication latency, 계승 CC4/runtime calibration과 P95/alpha의 D1 입수·선택 시점, request version history의 source-proxy 한계도 그대로 남긴다.

원본 source records와 audit producer SHA는 `TRAFFIC_ACCESS_SOURCE_RECEIPT.json`에 있다. raw Kestrel/Forecast archive와 Actual SUMO는 새로 복사하거나 호출하지 않았다. 이 감사의 AC·Native·FULL·route generation·Actual SUMO read·원본 캠페인 쓰기는 모두 0이다. 최종 read-only campaign snapshot은 parent의 완료 통지 후 별도 high-case 보존 receipt에 남긴다.


# 최신 범위 정정 — May01 전용 공동 연구

사용자의 최신 지시에 따라 현재 공동 연구의 선정·보안·효과 평가와 앞으로의 실행은 **2025-05-01만** 사용한다. 이 정정은 앞선 May02 paired validation 사용 언급보다 우선한다. May02 결과와 source/receipt는 삭제·변경하지 않고 `PRESERVED_MAY02_PROVENANCE_SHA256.json`에 원래 bytes의 SHA를 남겼다. 기존 high-case May02 결과, private input, IEEE123 및 IEEE8500 노출 기록은 역사적 provenance로만 보관하며 공동 입지 선택·BG 선택·제어 효과·독립성 주장의 근거에서 제외한다. May02를 다시 실행하거나 재계산하지 않는다.

현재 1,783개 후보 × 7개 시간대 민감도는 재사용한다. 기존 six-time 및 peak74 receipt가 동일한 May01 Planning B0 receipt와 입력 SHA를 가리키는지 읽기만 했다. BG=.85, GPU=780, 기존 P5 source1.04/all12 Vreg123.5/CAPBank3 off, 원본 31개 계통 source SHA 및 원본 정격·control receipt가 일치한다. 7개 slot은 원래 `[0,9,48,68,72,75]`에 사전등록 peak74를 추가한 `[0,9,48,68,72,75,74]`이며, 606 MV+1,177 LV 후보의 기존 두 archive와 최종 결합 archive/score SHA가 고정 receipt에 맞는다. 원래 사전등록·민감도·점수·mapping을 다시 만들거나 재동결하지 않았다.

`MAY01_SENSITIVITY_EXECUTION_REUSE.json`의 REUSED는 기존 receipt 및 저장 bytes/NPY header의 동일성 근거다. 기존 49,931 AC 호출은 역사적 실행 횟수이고 이번 범위 정정의 새 호출은 0이다. 새 AC·후보 탐색·테스트·Native·원본 캠페인 쓰기는 모두 0이며, 민감도 수치를 새로 검증하거나 정책 효과/field-ready 적격성을 추가 인증하지 않았다. 앞으로의 평가도 May01 Planning으로 사전등록한 배치를 고정한 뒤 동일한 May01 private Actual로 검증하며 Actual FAIL을 숨기거나 retune하지 않는다.
