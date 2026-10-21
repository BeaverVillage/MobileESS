# V2_add — r043 → IEEE8500 MESS8 이식 Gate

기준 `affc7226a519adbe072d7debbc3ae25ea71c3487` 소스는 수정하지 않았다. PR200은 V42 6대 shape-only 준비이며 V44 통합 인증이 아니다. 이번에 원본 4대→8대 모델 생성·최적화는 실행하지 않았다.

검토해야 할 원본 결합: v44/inputs.py 초기 4대 roster, v44/initial_states.py, v42_may_campaign_native90/traffic.py, operations.py, m_model.py, v43_actual/planning_reference.py, v44/svr11_ac.py의 96×4 배열, v43_arms/current_ac.py, v44/svr11_frozen/v42_voltage_control/authority.py. 탐색 MOVE depth=4와 시간 quarter=4는 차량 축으로 일괄 치환하지 않는다.

A1–M1–A2–M2, K48, Adaptive Beam, Direct Joint MILP, Gap/시간/독립 FULL 및 LB/UB 인증 정책은 그대로 유지해야 한다. IEEE123 전용 노드/선로/제어기 축을 가져오지 않는다. 전체 원본 3,703개 선로와 1,177개 Triplex가 목적함수/검증 대상이다. 선로 양단 도체 전류와 실제 상을 독립 검증하고 NormalAmps를 바꾸지 않는다.

변수/제약/nonzero, 모델 생성시간, peak RAM, K48/Joint MILP 시간, UB/LB/Gap, AC/Actual/Fresh 시간은 모두 NOT_VERIFIED다. 계통과 차량 수가 동시에 증가하므로 IEEE123 4대 대비 차이를 차량 증가만의 효과로 해석하지 않는다.

P±300 kW/Q±250 kvar의 box corner는 390.512 kVA지만 기존 PCS 부등식/다각형과 충방전 mode/SOC/효율/이동 에너지 제약을 그대로 이식해야 한다. 순간 정격 2.4MW는 96슬롯 보장 운전량이 아니다. 사전 초기 STA 후보: {"MESS01": "STA01", "MESS02": "STA12", "MESS03": "STA08", "MESS04": "STA06", "MESS05": "STA02", "MESS06": "STA03", "MESS07": "STA04", "MESS08": "STA05"}. 원본 첫 4개를 유지하고 나머지는 미사용 STA의 사전 lexical 순서다. 물리 수용성 PASS 이전에는 동결된 운전 초기상태로 사용하지 않는다.
