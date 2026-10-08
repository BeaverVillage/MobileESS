# 구조 진단

PR183 master는 graph·z·f·theta와 20개 cut을 반영하고, 전체 96-slot SOC·충전·P/Q·PCS를 recourse로 넘겼다. 첫 저장 배정에는 충전 가능한 정차가 없으면서 네 MESS에 합계 3,996.531325 kWh의 이동 에너지가 필요했다. Initial SOC와 terminal SOC가 같으므로 충전 없는 에너지 수지는 모순이다.

완료된 `(z,f)` 작업의 별도 original CSR exact certificate는 energy equality 384개와 zero-capacity charging gate 8,942개를 결합해 separation `3996.5313250220725`를 얻었다. Native TIME_LIMIT를 INFEASIBLE로 해석한 결과가 아니다. Raw native Pi를 사용하지 않은 별도의 수학적 multiplier이며, 원래 finite-bound support와 기존 witness 20개 검사를 통과했다. 기존 로그·상태·후속 certificate는 읽기 전용으로 보존했다. 기존 review는 이 늦은 certificate 이후 재작성하지 않았다.

Full C3A에는 이미 전체 물리가 있다. Archived ROOT의 continuous route_flow 207,736개 중 140,502개가 진단 기준 1e-8 < x < 1−1e-8의 분수값이고 최댓값은 0.270720702다. Charge_mode 384개도 모두 분수다. SOC는 약 689.13–1,080 kWh이며 높은 SOC에도 이동 mass를 허용한다. 실제 원본 계수에서 도출한 arrival-SOC reachability 651행의 최대 위반은 0.722566787 kWh다. Critical-grid 행은 rho 열과 Pi를 따라 추적하고 전체 grid 행을 보유한다. Archive에 native Slack이 없어 CSR로 재구성했다. Raw ROOT point는 strict residual 검사에 실패했으므로 정수 UB나 global LB로 채택하지 않았다.

Native ROOT 목적값 0.568711942993466은 현재 유효 LB 0.5687116104049206와 가깝다. 수치 인증 보정만으로 0.5% 목표 LB 0.6252721246670225까지 올릴 수 없다. 현재 UB 0.6284141956452488의 최적성도 증명되지 않았으므로 남은 9.500515051% 전체를 진정한 integrality gap으로 단정하지 않는다.

물리를 master로 옮기면 PR183의 물리적으로 불가능한 배정을 배제하지만 original C3A LP 자체는 강화되지 않는다. H2의 정확한 SOC 치환도 같은 LP이며 예상 nnz가 25,937,190으로 늘어난다. 새 강화 요소는 정수 경로의 이동 중 dispatch가 0임을 이용한 다기간 route–SOC disjunction이다. 추가 열 없이 정수 영역을 보존한다. 실제 M1의 certified LB 효과는 `NOT_MEASURED_RESOURCE_PENDING`다.
