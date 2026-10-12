# 과거 Window·Joint 연구와 현재 파일럿의 차이

현재 실험은 Source18r PR207, B2 May01 원본 Case authority를 고정하고, 슬롯75/82/94에서 네 차량의 Binary 접속·Mode/PQ/PCS와 해당 시간의 원본 전체 Grid Security를 보존하는 작은 MILP다. Route·SOC·Rebound의 시간 간 결합은 사영을 포함하도록 완화한다. 현재 결과는 오직 이번 실험의 독립 인증 Bound로만 판정한다.

|과거 연구|실제 수학적 영역|이번 파일럿과의 차이|
|---|---|---|
|PR111 W7|슬롯40–46의 Grid만 남겼으나 네 차량의96슬롯 Route/SOC/terminal physics는 모두 유지한 연속완화. G1/G2/G3 조건부 W7 LP와 별도 feasible-upper 증인으로 전체 조건부 셀을 감사했다.|이번 Snapshot은 실제 Binary 접속/Mode를 유지하고 시간 간 물리를 완화한다. 조건부 epigraph 계수를 만들거나 기존 default와 합산하지 않고, 세 개의 독립 MILP Global Bound를 max로 결합한다.|
|PR169 local trajectory hull|MESS04의69–72 국소 경로149,817개·mode word16개를 유한 disjunction으로 convexify. 자유 boundary SOC와 경계를 가로지르는 원본 이동 arc를 포함하고, 원래96슬롯 C3A 행을 모두 남겼다. 이후 다른 MESS/여러 hull 및 별도 Selective Integrality를 진단했다.|새 Snapshot은 hull EF를 추가하지 않는다. 조건부 Window는 원본96슬롯 문제의 보수적인 사영 완화로 설계하며, full C3A 위에 수백만 private EF 열을 쌓지 않는다. Boundary 출발 debit/진입 transit/free SOC 증명은 같은 물리적 위험을 감사하지만, 과거 결과를 현재 Source18r 인증으로 재사용하지 않는다.|
|PR182 공동 fleet/time/grid EF|76–79의 두 차량 occupancy-count9개 disjunction, 또는 네 차량8개 Boolean selector에 원본 grid/SOC/route rows를 곱한 RLT와 cross-selector symmetry. 모든 원본96슬롯 행을 유지하고 원래 정수 projection의 양방향 동등성을 증명했다.|이번 Snapshot/Window는 의도적인 하한용 사영 완화이며 원본 정수 projection과 동등하다고 주장하지 않는다. 최대256/1,500 Binary 및 행·NNZ 안전상한으로 작은 실제 정수 MILP의 실용성을 측정한다.|

PR111의 W7 feasible-upper 증인은 해당 조건부 창의 최적값이 inherited default보다 약함을 증명했으며 Full 문제의 LB가 아니다. 과거 upper_max0.3441896824와 당시 default0.5722125039는 현재 B2 수치로 옮기지 않는다. 당시 사전 선정 창 밖 슬롯89가 중요했으므로 한 약한 창으로 모든 시간 분해를 기각할 수 없다는 점만 연구 설계에 반영한다.

PR169의100/200개 선택 Binary 실험과192개 cross-master는 그 당시 Source에서 인증 Global LB 개선0이었다. 이 관측은 이번300개 Binary 후보의 성능을 증명하지 않는다. PR169는 실제 UB 개선도 관측했으나, 현재 U4 UB 엔진을 변경하는 근거로 사용하지 않는다.

PR182 A/B는 각각 추가133,254/225,952개 연속 열, 추가312,931/1,001,388행이었다. 두 ROOT LP는600초 예산에서 TIME_LIMIT였으며 미완료 point/raw bound를 신규 Global LB로 승격하지 않았다. 이번 연구는 이러한 full-horizon EF 계산비용을 재현하지 않고 Snapshot 최대3×30초 및 조건부 Window 최대120초만 허용한다.

코드·증명·원시 결과 CSV의 exact Git blob OID/SHA256 및 보존 사본은 HISTORICAL_WINDOW_JOINT_AUDIT.json과 historical_primary에 있다. 사본 Python 파일은 실행·import하지 않았다. Native 호출0회, 기존 Source/결과 변경0회다.
