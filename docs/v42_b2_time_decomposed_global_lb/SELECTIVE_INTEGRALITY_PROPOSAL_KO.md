# Selective Integrality 후속 후보 — 실행0회

Critical slot을 현재 사전등록과 동일한0-based75/82/94로 고정한다. 기존 저장K48 축·원래 Binary 목록에서 실제로 센 후보는300개다: node_activity288개, charge_mode12개이며 각 슬롯100개다. 나머지9,022개 원래 Binary는 연속완화한다. 선택한 변수의 bounds는 모두 원본[0,1]이다. Saved BASE LP에서 선택300개 중82개가 fractional이지만, 이는 성능 개선의 인증이 아니다.

새 행/열은0개다. 예상 크기는143,308행/244,265열/1,257,052 NNZ/300 Binary다. Route/SOC/PCS/원래K48 계통행 및96슬롯 전체를 그대로 유지한다. 현재 작업에서는 모델을 다시 만들거나 Native를 호출하지 않았다.

원본 FULL 정수 가능해의 검증된K48 사영은 모든 선택 Binary를 만족한다. 선택하지 않은 Binary의[0,1] 연속완화는 가능영역을 넓힌다. 따라서 F_FULL_integer→F_K48_selective⊆F_K48_LP의 포함관계가 성립하며, 향후 검증된 Global Solver Bound만 FULL 하한으로 옮길 수 있다. Selective incumbent는 FULL UB 또는Actual PASS가 아니다.

실험 우선순위는 이번 Snapshot·Window 결과를 확인한 뒤 별도 승인 대상으로 보류한다. 이 후보는 시간 결합을 보존하지만 기존 대규모K48 연속 행렬을 유지하므로 Binary300개만으로 ROOT 시간·RAM 감소를 보장하지 않는다. 과거PR169100/200개 Binary의 하한 개선0은 다른 Source의 관측이며 현재 Source18r의 불가능성 증명이 아니다. 가중치 반복·제약 반복·자동 추가 Solve를 개발하지 않는다.
