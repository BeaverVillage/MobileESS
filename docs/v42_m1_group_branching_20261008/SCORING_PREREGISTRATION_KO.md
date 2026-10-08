# 분기 점수 사전등록

최초 후보 계산 전 고정한다. Fractionality=2 min(x,1−x), critical_grid=실제 rho 행의 binding 등식으로 복원한 Pch/Pdis/Q sensitivity에 원래 가용 bound 폭을 곱한 합, injection sensitivity=그 sensitivity 절댓값 합, SOC=실제 outgoing movement 에너지 최댓값과 원본 energy_balance의 power 계수×원래 bound 폭 합(kWh), route=실제 outgoing arc 수, PCS=해당 power 열이 연결한 원본 PCS16 행 수, matrix=직접·연결 power 열의 실제 CSR nnz, propagation=0/1 분기에서 원본 비음수·mode 행이 함의하는 zero 열 수, complexity=1/(1+연결 nnz), numerical=1/(1+log10(연결 coefficient max/min))다.

Grid active 후보는 rho_max 계수를 가진 원본 행에서 |native slack|/max(1,|rhs|,max |row coefficient|)≤1e-6으로 고정한다. Native raw 진단의 active 판정이며 exact 물리 feasible point를 주장하지 않는다. Raw Pi를 shadow price나 점수에 사용하지 않는다. All power sensitivity는 원본 CSR binding의 선형 대입이다. Capacity·에너지·nnz는 각각 rho 단위 잠재 변화, kWh, count다. 모드가 Q를 직접 금지한다고 가정하지 않는다.

양의 요소를 전수 binary의 max로 [0,1] 정규화한다. 가중치는 fractionality .15, critical_grid .25, injection .10, SOC .10, route .10, PCS .08, matrix .07, propagation .07, complexity .05, numerical .03이다. Historical 변수별 certified gain은 확인되지 않았으므로 null이며 점수에 가짜 기여를 주지 않는다. PR179의 전체 certified gain=0은 별도 비교한다. 점수는 순위이며 LB certificate가 아니다.

Primary 그룹은 모든 binary를 family/MESS/physical slot별로 정확히 한 번 분류한다. Critical-grid/time과 96-slot SOC/route는 겹침을 허용하는 분석 view다. 그룹 representative는 free binary·B2 fractionality>1e-6 중 점수 최대, 동률이면 원본 column 최소다. 그룹 순위는 representative 점수 내림차순, primary ID 오름차순, column 오름차순이다. 최상위 그룹을 첫 pivot로 선택하고, 그 뒤 다른 family의 최고 변수 하나, critical-grid 영향이 큰 나머지 변수 하나를 택한다. 동일 column과 동일 scalar 영역은 중복하지 않는다. 최대 세 변수, 모델에 추론 고정은 추가하지 않는다.
