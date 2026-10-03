# May reg1a A상 current violation 원인 감사

BASE: PR #129 `97ef9cc9b655d93a42b0b43d593aac01b951c6f3`. 운영 모델 수정 없이 4일×96 slots를 fresh autonomous OpenDSS로 재현했다. 추가 network terminal 감사도 동일 384 slots를 재현했으며, 기존 V/current/current_pu/kVA/tap 배열과 차이는 모두 0이다. 12개 위반 slots와 사전 고정한 인접 정상 8 slots를 상세 측정했다.

1. **12/12 PCC 및 상위 PCC transformer가 ABC 3상 정상 연결**이다. Load의 NumConductors=4, NodeOrder=[1,2,3,0], wye, 0.48 kV를 compiled 객체에서 확인했다. 단상 또는 누락·오배치 상은 발견되지 않았다.
2. conductor별 실제 P/Q는 근사 균형이다. 240 PCC-slot 표본에서 최대 상간 spread는 P=0.002547456 kW, Q=0.002879674 kvar이다. 완전한 0 차이는 아니며 상전압이 달라 I까지 동일할 필요는 없다. 각 PCC의 spread 및 상대 차이는 PCC_PHASE_BALANCE_SUMMARY.csv에 보존했다.
3. May 전체 reg1a upstream peak A/B/C는 **730.905264185/509.612173208/598.636767800 A**다. 세 peak 모두 May 21 slot 31이다. downstream A/B/C와 bus V, tap, controller 상태는 REG1A_PHASE_CURRENT_AUDIT.csv에 모두 기록했다. reg1a는 하나의 3상 transformer이며 존재하지 않는 reg1b/reg1c를 가정하지 않았다.
4. native source base P A/B/C=1400.0/952.5/1137.5 kW, Q=762.5/540.0/617.5 kvar이다. peak slot 실제 native P=1360.603212/938.733120/1117.877372 kW, Q=817.964902/638.402532/674.263617 kvar이다. A-B native P 차이는 421.870092 kW이며 AIDC P는 상마다 약 176.64 kW이다. PV/고정 capacitor 및 network loss·phase transfer를 별도 분리했고, 12개 위반 slot 모두 native A상 P가 가장 크다.
5. **693.930612006762 A = 5000/(√3×4.16)**. IEEE123Master.dss line 26의 5000 kVA/4.16 kV 3상 nameplate를 frozen backend가 parent bus 150/winding 1에서 사용한다. NodeOrder로 A/B/C conductor를 정확히 읽는다. CTPrim=700은 RegControl CT authority이며 backend thermal 분모가 아니다. Generated_Planning_Line_Ratings_u080.dss는 Line만 edit하고 reg1a를 변경하지 않는다.
6. OpenDSS compiled NormalAmps=763.323673207 A, EmergAmps=1040.895918010 A이며 frozen backend는 이를 transformer 분모로 쓰지 않는다. **12개는 frozen 100% nameplate current 초과이고 source NormalAmps 초과는 0**이다. aggregate transformer kVA가 1 미만이어도 특정 상 전류는 nameplate 분모를 초과할 수 있다. 기준을 완화하거나 결과를 재분류해 기존 PR129 count를 바꾸지 않았다.
7. H1 **NOT_SUPPORTED**, H2 **STRONGLY_SUPPORTED**, H3(frozen contract measurement/분모 오류) **NOT_SUPPORTED**. 가장 직접적인 설명은 native feeder A상 P/Q 편중과 상별 network 손실에 balanced AIDC 부하가 더해져 frozen 상별 nameplate 한계를 넘은 것이다. source NormalAmps와 100% nameplate policy의 차이는 명시적으로 구분한다. 반사실적 부하 제거 실험은 수행하지 않았으므로 native 단독 원인으로 과도하게 단정하지 않는다.
8. **PCC mapping 수정 불필요**. H1이 CONFIRMED되지 않아 exact fix proposal은 작성하지 않았다. rating/phase/tap/PQ/부하 분배/Runtime/CC4/queue/Planning voltage/margin은 모두 수정하지 않았다. B1/B2/B3/M1/A2/M2 NOT_RUN.

수치 감사의 한계: 추가 passive terminal 합계의 strict algebraic 1e-7 보존 검사는 실패했고 원본 FAIL receipt를 유지한다. 최대 discrepancy는 0.121177067 kW/kvar이다. frozen convergence tolerance=0.0001; nodal current residual을 별도로 합산해 이 차이와 3.51305350667e-06 kW/kvar 이내로 일치함을 확인했다. solver tolerance는 변경하지 않았다. 이 오차를 정확한 물리 손실로 은폐하지 않고 NETWORK_NUMERICAL_LIMITATION.json에 기록했다.

최종 테스트와 exact BASE byte 보존/외부 source SHA 검증은 TEST_RECEIPT.json 및 VERIFICATION.json을 참조한다.

검증: full pytest **1362 passed, 1 inherited warning**; PR #129 기존 4525개 파일 byte/SHA 동일 및 외부 frozen source SHA 검증 PASS.
