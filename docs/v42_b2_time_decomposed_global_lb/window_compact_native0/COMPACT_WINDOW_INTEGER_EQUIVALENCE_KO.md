# Window Binary 규모 및 정수 동등성

원래16,236 Binary 창은 PR209의 literal arc-Binary 차량 영역에서 잘라낸 표현이다. 96슬롯K48의9,322 Binary는 Source18r의 기존 node-activity compact/C2/C3A 표현이다. 시간 범위 차이만으로 Binary 수를 비교하면 서로 다른 표현을 혼동한다.

사전등록창[88,96)의 literal16,204 arc 열은 모두 남긴다. 그 type만[0,1] 연속으로 바꾸고, 실제24개 site·4대·88..96의864개 node-throughput Binary와 원래32개 mode Binary를 유지한다. 총896 Binary이며 실제 물리 크기는18,472행/19,440열/118,124 NNZ다. 계통행을 포함한 최소 행 수는86,352이다. 원래 physical row/RHS/sense/Bounds/SOC/PQ/PCS를 삭제·변경하지 않았다.

Source18r의 v42_supercompact.formulation.Compact는 route_flow를 연속으로 바꾸고 Binary node_activity와 원본 flow equality를 유지한다. 진짜 parallel endpoint arc가 있으면 selector Binary를 유지하는 정책이다. 현재 창의 모든 내부 endpoint group은 실제 검사에서 유일하다. 과거 경계를 넘어 들어오는 arc는 4,452개이며, 같은 최초 연결(site,time) 그룹은 실제 저장된 창 행렬에서 동일한 열이다. 이 열에는 창 내부 이동에너지·P/Q 항이 없다. 이번 작업은 Source18r의 기존 개념을 창의 자유 경계에 적용한 재표현이며 새 strengthening이 아니다.

원본 literal 정수 경로는 node throughput0/1로 직접 lift한다. 반대로 compact의 비음수 flow와 entry mass1, node0/1을 이용하면 최초 visited node가 전체 유량1을 받는다. 모든 내부 endpoint arc가 유일하고 시간이 엄격히 증가하므로 내부 경로는 순서대로0/1이다. 최초 연결 node로 들어오는 과거 boundary arc들만 서로 섞일 수 있으나, 실제 전체 물리 열이 동일하므로 하나의 원래 arc를1로 선택하고 나머지를0으로 두어도 내부 SOC/PQ/mode/경로·모든 슬롯 계통 식·rho와 목적값이 그대로다. 원래 departure debit이88보다 앞선 에너지는 창 밖에서 이미 차감되어 창 energy row에 넣지 않는다.

동등성은 power/SOC/mode/내부 route와 계통·목적에 대한 정수 물리 사영의 동등성이다. 과거 boundary arc 각각의 raw 좌표까지 같다는 주장은 하지 않는다. 원본 FULL→literal window 포함관계와 이 사영 동등성을 결합하면 original FULL 정수 가능해는 compact Window에 포함된다. 창 시작 위치/SOC와 종단SOC를 원래 초기/종단값으로 고정하지 않고, 모든 crossing arc를 유지한다.

실제 endpoint 유일성·boundary column signature·added node links·U4 lift의 독립 verifier PASS와 전체 계통/Native readback/RAM gates 이후에만 한 번의360초 Native 후보로 사용할 수 있다. 이 생성기는 Gurobi import/Optimize/Full96 생성0회다.
