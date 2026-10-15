# S1 실제 Root 및 고정 실험 진단

이 자료는 과거 동일 S1 Source/Case의 진단이다. 새 D0 M1/M2 결과나 원래 4×24 Global LB로 이전하지 않는다.

저장된 Root에서 Arc 4307개, Mode 192개가 분수이다. 다중 위치 187 차량·슬롯, 동시 충·방전 192 차량·슬롯을 원래 계수와 대조했다.

Pch/Pdis/Q의 Signed 계수·차량별 기여·SOC 재귀식과 Critical Line/Phase/Slot은 S1_ACTUAL_ROOT_LITERAL_DIAGNOSIS.json에 저장했다. 분수해의 관측만으로 Route 또는 Mode가 5.02% gap의 유일하거나 지배적인 원인이라고 증명하지 않는다.

원래 CSR는 836,244행/23,258,846 NNZ이다. 최소 비영 계수 1e-13, 최대 절댓값 400로 넓은 계수 범위를 확인했다. 이는 수치 조건수 측정이나 모델 변경 근거는 아니다.

기존 Integer oracle Native 40.174초에서 Presolve 표기 [6.96, 4.76], Barrier 완료 누적 시각 [23.49], Crossover [6.52], Root relaxation [17.69]초를 보존했다. Solver 내부 중첩 값은 합산하지 않는다. Root 처리 완료 이후 1 node에서 제한시간으로 종료했다.

S1-A는 기존 연속 LP를 재사용한다. S1-B는 검증된 STAY Arc를 고정하고 Mode/Power를 연속 완화한다. S1-C는 같은 Raw의 Mode만 고정하고 Route를 완화한다. S1-D는 둘을 함께 고정한다. B/C/D는 원래 행·목적함수를 유지하는 Domain Overlay까지 준비했으며 Native 실행은 NOT_RUN이다.

고정 LP의 목적값이 상승하더라도 그 패턴에 대한 조건부 결과다. 원래 S1 또는 4×24 Global LB로 사용할 수 없고, 가족별 gap을 더하거나 유일한 원인을 인증할 수 없다. 과거 Mode Hull384와 SOC Hull384는 반복하지 않았다.

새 수학적 강화 선택은 B/C/D 결과까지 확인한 뒤로 남긴다. 차량 전체 궤적 DW는 연구 후보이며 공식 K48을 대체하지 않는다. 완전한 원래 도메인 Pricing과 독립 Dual Certificate가 없는 Restricted Master 값은 Global LB가 아니다.

B/C/D 제안 상한은 각 15초(합 45초)와 반환 여유 30초이다. A1이 우선이며 Supervisor가 배분하기 전에는 실행하지 않는다. 현재 예산만으로 세 LP 완료를 보장하지 않는다.
