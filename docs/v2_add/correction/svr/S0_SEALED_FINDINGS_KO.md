# S0 진단 봉인 — 추가 SVR 평가 이전

원본 r043과 같은 목적함수는 각 슬롯의 TIME 제어 처리 후 최종 상태에서
source-rooted parent terminal 전류 / 원본 NormalAmps를 측정한 평가96 최대값이다.
모든 이벤트의 극값과 Prefix24 안전은 별도이다. 이전 correction 루트 TIME CSV는
이벤트 envelope 중간 자료이며 canonical/ 및 본 S0 CSV가 최종상태 목적함수이다.

β2.00 Actual: 75.3595439519%, 최소0.9465536641pu.
β2.10 Actual: 78.9655574355%, 최소0.9436775897pu.
이 S0 결과만으로 추가 SVR 장비 후보를 탈락시키거나 Primary를 최종 판정하지 않는다.
IEEE123의 전기 반복15는 β1.50 Actual 초기에서 비수렴했다. IEEE8500의 기존
전기 반복100을 쓰면 원본 TIME 지연을 유지하면서 수렴한다. 제어 반복한도100은 동일하다.
이는 수치 예산 차이이며 Tap/Delay/Source의 사후 조정이 아니다.

기존12 제어기 static 계약과 저전압 노드/경로, 슬롯말 Tap 포화를 봉인한다.
기존 archive에는 이벤트별 RegControl TapNumber가 없으므로 그 검증은
독립 S0 재생 및 S1에서 새로 계측하며 기존 기록에 소급하여 PASS를 부여하지 않는다.
