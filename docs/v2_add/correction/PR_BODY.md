V2_add의 목적함수를 r043 parent terminal/원본 NormalAmps 및 TIME 슬롯 최종 상태 기준으로 수정했습니다. 기존56개 배열의 독립 재계산, 사전 등록 S0 배율 Planning96/Actual120/Fresh, 유한 MESS와 AIDC 정책 재감사를 추가하며 기존 증거를 보존합니다.

기존 RegControl12의 Winding2/TapNumber/한계/Queue를 계측하고 S0 진단을 먼저 SHA 봉인했습니다. 이후 물리적 직렬 SVR3/6/12 Bank를 β1/1.5/2/2.05/2.1에서 TIME/Fresh 비교했습니다. 원본3703 선로의 임피던스/정격/목적함수와 P5/실제 지연을 유지하며, 슬롯 최종 지표와 이벤트·Prefix 안전을 분리합니다.

추가3 Bank/β2.00의 Actual 평가96 B0는 최대75.710958%, 최소0.951568pu로 최종·이벤트 물리를 통과했습니다. 같은 구성의 유한 MESS는 전역 최대를74.139349%로1.571609%p 낮췄고 새 피크는74입니다. 기존12 제어기의 Tap 포화는0개였으며, 6/12 Bank는 중간 전압 위반을 남겼습니다. 3 Bank의 차가운 초기 Prefix 저전압23초와 평가96 합격을 구분합니다.

Primary 미인증/G4_NOT_READY입니다. Planning414 FULL 도메인과 Actual192 연구정책 QoS 측정을 구분하며 Source QoS/비영 Actual AIDC는 미인증입니다. A1/M1/A2/M2/K48/Joint MILP/장시간 Native를 실행하지 않았습니다.

상세: docs/v2_add/correction/FINAL_V2_ADD_CORRECTION_REVIEW_KO.md
최종 수치: correction/canonical/ 및 correction/svr/
독립 테스트: correction/INDEPENDENT_REGRESSION_TESTS.json
추가 SVR 독립 테스트: correction/svr/INDEPENDENT_SVR_TESTS.json (총17개 회귀 PASS)
원시 AC/이벤트·SHA는 Receipt의 격리된 V2_add_runtime 경로를 참조합니다.
