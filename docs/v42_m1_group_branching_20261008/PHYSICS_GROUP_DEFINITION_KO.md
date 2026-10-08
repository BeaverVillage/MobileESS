# 물리적 그룹과 시간 의미

A_LOCATION은 MESS/physical slot별 site through-flow binary 그룹, B_MODE는 MESS/slot별 charge_mode 하나다. 모든 9,322개 binary는 두 primary 종류 중 하나에 정확히 한 번 속한다. C_GRID는 실제 CSR sensitivity로 연결된 critical rho 행/time 분석 view, D_96SLOT은 해당 MESS의 전체 SOC·route 분석 view다. C/D는 primary partition과 겹치며 이를 multi-way domain split으로 사용하지 않는다.

node_activity는 STAY 전용 binary가 아니라 forward DAG vertex의 outgoing mass다. 이동 중간에는 site vertex가 없어서 site activity 합을 항상 1로 가정할 수 없다. Unit source→sink flow의 시간 cut에서 site outgoing activity와 이전에 출발하여 아직 도착하지 않은 travel arc mass의 합이 1이다. 따라서 site activity는 조건부 at-most-one이며 이동 중 all-zero가 가능하다. Charge/PCS는 실제 STAY와 연결한 별도 원본 행으로 판정한다. 원본 label96의 terminal node 96개는 travel arrival<96과 마지막 STAY로 physical slot95에 대응하며 saved inverse의 exact alias를 전수 대조했다. Slot0의 초기 위치는 unit source flow/constant로 보존되며 새 binary를 만들지 않는다.

원래 route_flow 207,736개는 continuous다. 비평행 forward DAG, 모든 through-mass binary와 원래 flow 보존을 사용한 PR183의 일반 정수 path projection 증명을 SHA로 재사용한다. 이전 불가능 배정은 그 전체 배정의 모순이며 개별 pivot을 전역 infeasible로 선언하지 않는다. 새 모델의 implied zero columns는 점수용 추론만 기록하고 Child에 실제 추가 고정하지 않는다.
