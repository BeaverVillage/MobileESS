# 실제 LP 분기의 물리적 해석

다음 값은 복원된 original FULL 변수축에서 측정한 fractional LP 진단이다. strict replay가 FAIL이면 운전 feasible 해로 해석할 수 없다. SOC 표의 min/max는 한 점의 시간축 범위이며 최적화로 구한 SOC feasible envelope가 아니다.

|후보|Child|MESS/slot/site|선택 slot Pch(kW)|Pdis(kW)|Q(kvar)|SOC 시간 min/max(kWh)|Travel energy 가중합(kWh)|FULL replay|
|---|---:|---|---:|---:|---:|---|---:|---|
|C01|0|MESS02/77/mode|0.00000000|103.82784062|231.47724475|692.27443549/1079.99999996|332.59581662|True|
|C01|1|MESS02/77/mode|0.00000062|0.00000000|332.27760972|745.82191601/1079.99999993|357.52537364|False|
|C02|0|MESS01/67/STA12|5.78020368|10.69681805|191.87057038|689.68474973/1079.99999985|365.35490221|False|
|C02|1|MESS01/67/STA12|0.00000004|0.00000007|-392.31411094|749.90291963/1079.99999998|357.54102161|False|

C01/C03의 z=0은 해당 MESS/slot에서 charge를 차단하고 discharge를 허용한다. z=1은 discharge를 차단하고 charge를 허용한다. 24개 원래 site의 Pch/Pdis와 SOC/PCS/grid coupling을 사용하며 Q는 모드와 독립이다. Q나 다른 MESS의 위치를 추가로 고정하지 않았다. 따라서 다른 위치와 시점으로 power·SOC·route를 재배분해 단일 mode 고정을 우회하는 fractional 대체해가 가능하다. 실제 재배분은 PHYSICAL_INTERPRETATION_DATA와 가족별 L1 변화에 기록한다.

C02 z=0은 MESS01/STA12/67 outgoing flow를 원본 equality와 nonnegativity로 0으로 만든다. z=1은 이 vertex의 through-mass를 1로 제한한다. 이는 travel departure도 허용하므로 STAY나 charging을 강제하지 않는다. 다른 site 활동과 travel의 시간 cut을 함께 고려하며 임의 one-hot를 추가하지 않았다.

원본 critical rho 행 100개의 실제 branch/time label을 source descriptor와 대조했다. Child별 정상화 slack, raw Pi, SOC97/Pch96/Pdis96/Q96/stay/travel weighted trajectories, 주요 node_activity 변화 20개를 보존한다. Voltage/thermal/PCS/route/SOC binding 행의 strict violation은 FRACTIONAL_SOLUTION_COMPARISON의 physical_row_families에 기록했다. Raw Pi는 shadow-price 인증으로 사용하지 않는다.

정확한 Q/PCS 수치 손실과 binary 고정의 구조 효과는 별개다. CHILD_NUMERICAL_AUDIT는 선택된 multiplier의 finite-bound 손실과 row-residual 항을 분해하며 float 분해를 exact 증명과 구분한다. 원본 tolerance·물리 제약과 651개 B2 행은 변경하지 않았다.

- C01/z0: 상위 finite-bound 손실 Q=0.000262739954778, Pch=9.99141513039e-06, Pdis=1.05416658336e-06.
- C01/z1: 상위 finite-bound 손실 Q=0.00190237875379, Pdis=0.00143325517402, Pch=5.64515360076e-07.
- C02/z0: 상위 finite-bound 손실 Q=0.00208696928629, Pdis=1.00184302529e-05, Pch=4.01827007434e-07.
- C02/z1: 상위 finite-bound 손실 Q=9.0115227727e-05, Pdis=4.184582763e-07, Pch=1.75242985812e-08.
