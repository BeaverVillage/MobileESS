# Source18r Primal 영역 인증

원본 가능영역을 F, 저장된 Dense Response 동등 모델의 가능영역을 D, 원본 좌표 복원 함수를 L이라 둔다. Source18r의 기존 정수 동등성 증명과 이번 독립 원본 검증은 L(D)의 물리·정수·계통 조건 및 목적함수가 원본과 같음을 확인한다. 이번 연구는 원본 FULL 1,130,336행/344,967열을 새롭게 완화하지 않고, 동등한 Dense 715,596행/354,277열 및 9,322 Binary를 복제한다. Response 보조변수·RHS·Sense·목적 상수·변수 Bound는 원본 저장 데이터와 실제 Native Readback으로 대조한다.

후보 중심 p는 동일 Source/Case의 원본 FULL 검증점이다. Binary 자유 집합 J, 고정 집합 K, 고정 Continuous Route Flow 집합 R, 사전 결정된 반경 r에 대해 연구 영역은 다음과 같다.

`D_N = {y in D : y[K]=p[K], y[R]=p[R], sum(j in J)|y[j]-p[j]| <= r}`

Binary p에 대한 마지막 행은 정확히 `(1-2p[J])^T y[J] <= r-sum(p[J])`다. 고정 값은 원본 Bound 내부에 있고 중심의 Hamming 거리는 0이므로 p가 포함된다. 모든 원본 행과 형식을 유지한 채 고정 및 한 개의 Hamming 행만 추가하므로 `L(D_N) subset F`다. 따라서 독립 FULL 검증을 통과한 후보의 목적값은 유효한 Primal UB다. 제한 문제의 Solver ObjBound는 원본 전체 문제의 Global LB로 사용할 수 없다.

N1은 384개 전체 96슬롯 Mode만 자유로 두고 모든 Node 및 Continuous Route Flow를 중심에 고정한다. r=384이므로 Mode에 대한 Hamming은 전체 Binary 상자에서 제한을 추가하지 않는다. Alias 의존성 검사로 네 차량의 원본 Arc가 모두 고정됨을 확인한다. 각 차량의 Pch/Pdis/Q/SOC는 원본 Bound 및 모든 원본 제약 아래에서 자유다.

N2는 차량 한 대, N3는 두 대의 전체 96개 Mode와 선정 시간구간의 Node를 개방한다. 선택 차량의 원본 Continuous Route Flow는 원본 영역에서 유지하고, 나머지 차량의 Binary와 Route Flow는 해당 알고리즘의 독립 검증된 중심에 고정한다. 반경은 차량당 48로 사전 결정하며 별도 반경 Sweep은 없다. SOC나 PCS를 차량 간 합산하지 않는다. 다른 세/두 차량의 P/Q/SOC도 연속변수로 유지한다.

원본 terminal 위치는 96시점의 허용 접속지이며 출발지 복귀를 새 원본 조건으로 추가하지 않는다. 다만 선택 차량의 구간 밖 Node를 중심에 고정하는 Primal 제한은 구간 경계에서 중심 경로로 재합류하도록 요구할 수 있다. 이 제한은 명시된 Neighborhood의 일부이며 원본 FULL의 복귀 의무로 해석하지 않는다. 전체 97개 SOC 경계, 초기/종단 SOC, 이동시간·이동에너지, 충방전 Mode, PCS16, 이동 중 P/Q 금지 및 Rebound 제약은 그대로 유지한다.

실측 원본 U4는 모든 Mode=0, Pch=Pdis=0, 이동=0, SOC=760이다. Mode=0이면 Pch=0이고 원본 SOC 전체 보존식 및 SOC96=SOC0에서 비음수 Pdis의 총합도 0이다. 따라서 초기 N2/N3의 비선택 차량은 Q를 재최적화할 수 있지만 유효전력 순환은 할 수 없다. 이후 같은 알고리즘의 검증된 중심에서 Mode가 활성화된 차량은 해당 고정 Mode 안에서 P/Q/SOC를 다시 최적화할 수 있다.

후보 순위는 부호 있는 원본 P/Q 계수와 실제 Route DAG의 중심 점유 정점·ETA·이동에너지, 사전 충전 및 이후 복원 시간을 참고하는 휴리스틱이다. DAG 경로 증거는 SOC/PCS/Grid 가능성 증명이 아니다. 모든 후보는 원본 FULL Validator의 실제 검사 이후에만 채택한다. 개선된 중심에서는 원본 814,560개 Security 행을 다시 검사하고 새 선택 행의 보조변수 소거·상수·부호를 독립 검증한다. 선정하지 않은 Grid 행도 Native 및 최종 FULL Replay에서 유지한다.

Raw Native 점을 반올림·클리핑·수리하지 않는다. 9,322개 Dense Binary와 복원된 208,312개 FULL Binary는 정확한 0/1이어야 하며 목적값의 원본 좌표 운반과 Solver ObjVal은 일치해야 한다. 행의 수치 가능성은 변경되지 않은 원본 Validator 기준(주요 Grid/Flow 1e-8, 나머지 FULL 행 1e-6 등)으로 검사한다. 모든 연속행의 유리수 정확 가능성을 별도로 증명했다는 뜻은 아니다.

Planning FULL PASS와 Actual Fresh AC96은 구분한다. 이번 작업은 Actual을 실행하지 않으며 `ACTUAL_NOT_RUN`을 유지한다. 기존 K32/K48 인증 Global LB를 보존하고 신규 LB Optimize는 호출하지 않는다.
