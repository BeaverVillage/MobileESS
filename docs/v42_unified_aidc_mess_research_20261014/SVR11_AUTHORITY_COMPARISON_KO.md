# 11-SVR 전압 권위 감사

PR223과 PR230은 동일한 11개 SVR, 기존 7개 RegControl, 원본 LDC, 153개 변압기 상별 축과 Electrical Certificate/계수 bytes를 사용한다. 두 Case와 실제 P/Q trace는 다르므로 PR223 Fresh96 PASS를 이전할 수 없다.

Planning 계수는 한 고정 탭 상태의 모델이 아니다. 각 부호별 probe가 동일한 과거 AUTO prefix를 새로 재생하여 중앙 secant와 LDC interval을 생성한다. 자동 탭 임계점을 건너는 응답은 큰 기준점 변화에서 물리 오차를 만들 수 있다. 개별 probe의 최종 탭은 packet에 저장되지 않았다. Actual은 원래 AUTO/TIME 제어를 독립 초기화한다.

PR230 C0/C2는 PCC P/Q와 모든 GPU 배열의 차이가 정확히 0이다. 두 비교군의 affine 위반은 슬롯 10·12에 동일하며 새 Allocator의 추가 영향이 아니다. 해당 행의 최소 v² 0.5821213/0.7003066은 선형 추정값이다. 실제 전압 판정은 아래 별도 Fresh AC 실행 증거를 따른다.
