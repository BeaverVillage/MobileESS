# V2_add — 공식 Balanced 원본 감사

PR #197 `35079f458fc9d87a469ebd79e0e5d2cb7bd5fe1e` Git blob에서 공식 feeder 파일을 바이트 그대로 복원했다. `SOURCE_COPY_RECEIPTS.json`은 파일별 SHA를 기록한다. 운영 전력 크기·PV·PCC는 PR197의 BG=.552 조건에서 가져오지 않았다.

독립 DSS context의 실제 compile 결과: 전기 노드 8,531, 선로 3,703, Triplex 1,177, 변압기 1,190, 고객 Load 1,177, RegControl 12, CapControl 9. 사전 기준 개수 일치: True.

Master의 CalcVoltageBases 및 NodeOrder 초기화용 control-off 명목 snapshot 1회를 실행했다. 이것은 원본 inventory 확인이며 V44 입력 B0, 전압 적합성, 96슬롯 Fresh AC 또는 제어 민감도 결과가 아니다. P5 overlay는 적용하지 않았다. 원본 정상/비상 정격과 winding kVA는 OFFICIAL_BALANCED_AXES.json에 보존했다. 어떤 Triplex도 제거하지 않았다.

모든 공식 고객은 2상 wye .208kV 정의다. 두 반대 hot에 고객 총 P/Q를 나누는 공식 연결을 유지하며 전체 ABC 완전 평형이나 MESS의 동적 상 변환으로 해석하지 않는다. 고객별 명목 P/Q는 공간 가중치로만 사용한다. 원본 명목 부하를 V44 운영 P/Q에 더하지 않는다.

원본 명목 총 P=10773.170000000000 kW, Q=2700.010911176059 kvar. 원본 ZIP 출처/해시는 PR197 출처 감사가 권위이며 최신 배포본 재수집은 하지 않았다. 실행 엔진: DSS C-API Library version 0.14.5 revision 87d85c2622c8281b92255335bc7c09b11191b21d based on OpenDSS SVN 3723 [FPC 3.2.2] (64-bit build) MVMULT INCREMENTAL_Y CONTEXT_API PM 20240329033747; License Status: Open DSS-Python version: 0.15.7 OpenDSSDirect.py version: 0.9.4.

V44 Planning 7개/Actual 43개 RegControl 계약과 공식 모델의 차이는 미해결이다. PR197 P5(Source1.04, Vreg123.5, capbank3 off)를 검토 후보로만 기록한다. Scale마다 전압제어를 조정하지 않는다.
