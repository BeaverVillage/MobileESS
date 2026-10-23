# 목적함수·측정시점 계약 감사

기존 All-Terminal Mask는 원본과 불일치했다. r043 `v42_thermal/measurement.py:branch_measurement`의 source-rooted parent terminal/원본 NormalAmps로 복원했다. `v42_native/grid.py:add_grid`의 변압기 제약은 선로 목적함수와 별도다. 독립 Dijkstra와 PR197 방향은 일치한다. 원본3703개, parent 실제도체6156개, 양단 안전도체12322개, 역방향terminal2 선로1개, disabled5개를 보존한다. LV/Triplex1177개를 포함한다.

기존56개 배열은 새 Solve 없이 재계산했다. Static β1.50 Actual B0 **56.146844618957%**, MESS 감소 **0.201752365689%p**다. 기존 양단56.1468981373%/0.2017599331%p와의 차이는 정의 차이에 따른다.

원본 `v44/svr11_frozen/v42_voltage_control/integration.py:PhysicalScenario.settle_actual`는 `CommonClock.settle_slot` 이후 측정한다. `v43_actual/current_ac.py:_probe`/`v44/svr11_ac.py:probe_body`도 이 상태를 읽고 `v43_actual/compare.py`의 Fresh 범위는 physical_steps[24:]다. **각 슬롯 마지막 native solved state에서 parent 비율을 구한 평가96 최대값**이 원본 목적함수다. 모든 이벤트 최대값은 안전 진단이다.

correction 루트의 기존 TIME CSV는 이벤트 envelope 중간 산출물로 보존한다. 최종 수치는 `canonical/`, SVR 수치는 `svr/`를 따른다. `CURRENT_MEASUREMENT_CONTRACT.json`과 선택 index Receipt가 이를 명시한다. 저장 배열 재투영에 추가 Solve는 없다. Prefix24/전체120 이벤트 안전도 별도 표시한다. 직접 CAPI CurrentsMagAng/NormalAmps, 원본 정격, 독립 마지막 이벤트 선택 및 float64 허용오차1e-12를 검사했다. 독립 Fresh 허용오차1e-9, 전력수지1e-4는 계산 전에 등록했다.
