# LP 양방향 사영과 Pricing 범위

원본의 동일 Class C에 속하는 UID i의 연속 Local Polytope를 P={x: Ax (sense) b, l≤x≤u}라 하자. 모든 UID의 실제 A/B/b/l/u 및 목적함수가 정확히 같음을 확인한다. Global 변수 z와 각 Local 변수 x_i가 연결되는 원본 행은 Gz+Σ_i Bx_i (sense) d다.

집계 변수 Y=Σ_i x_i를 사용하면 Local 행/Bounds는 AY (sense) N b, N l≤Y≤N u이고 Global 행은 Gz+BY (sense) d다. 원본 가능점의 합은 집계 가능점이다. 역으로 집계 가능점에서 각 x_i=Y/N을 유리수로 두면 모든 원본 Local 행과 Bounds를 만족하고 Global 행 및 목적함수가 보존된다. 따라서 양방향 연속 LP 사영이 성립한다. d는 현재 날짜/Stage/Fixed-MESS의 값을 그대로 유지하며 특정 May01 값으로 대체하지 않는다.

N배 RHS/유한 Bounds가 binary64에 정확히 표현되지 않는 후보군은 개별 UID 블록으로 남긴다. 작은 계수를 버리거나 허용오차를 늘리지 않는다. 실제 Global Forward Identity는 열 Gathering으로 비교하며 반올림되는 계수 합산을 증거로 사용하지 않는다. 독립 검사기는 Constructor의 PASS/Header/Hash에 의존하지 않고 모든 원본 행·열·UID Coverage와 실제 CSR 계수, RHS, Box, Objective를 다시 확인한다.

이 증명은 연속 LP에 한정한다. Y가 정수여도 Y/N은 정수가 아닐 수 있으므로 정수 분해 가능성을 주장하지 않는다. 원본 FULL 정수 모델의 행·열·Binary·NNZ 제거량은 모두 0이다. 새 P1의 실제 Raw Point도 원본 UID LP 좌표로 다시 Lift하고 기존 원본 Primal Replay를 통과해야 LB 인증을 발급한다.

Runtime Auxiliary 제거는 기존 Equality Substitution을 한 번만 적용한다. 모든 원본 Equality/Finish 식과 영향받는 계수/RHS를 정확한 유리수로 확인한다. 상수 Runtime Auxiliary는 원본 Global Prefix에 보존한다. May01에서 제거되는 69,542개 변수/Equality는 기존 DW 투영이며 이번 집계의 추가 제거량으로 중복 계산하지 않는다.

추가 행 제거는 실제 계수·Sense·RHS가 같은 중복 행과 0≤b 등의 참인 상수 행뿐이다. May01에서 각각 69,028개와 5,194개다. 이름으로 연결된 GPU/WAN/Runtime/ACTIVE Coupling 행은 중복/상수여도 유지한다. 전압·전류·변압기·GPU·QoS·WAN·CC4·Deadline 조건의 임의 삭제는 없다.

각 Class Pricing Cache는 축약된 전체 Local Fractional Kernel과 원본 Complete Physical Graph를 갖는다. 기존 `phase.run`, `pricing.full_pricing`, 정확한 Dual 보정, Row Separation과 Policy를 그대로 호출한다. STAY나 Migration 경로의 일부만 남기는 휴리스틱 범위 축소는 없다. Native0의 Zero-dual 분석은 전체 Oracle/Block 연결 검증이며 실제 Production P1 Global LB/최적성 인증으로 사용하지 않는다.

Native0 또는 실제 Compression 검증이 실패하면 해당 Stage는 원인·Raw를 남기고 차단한다. 원본 FULL-feasible 해가 없으면 Actual96/Fresh96을 생성하지 않는다. 날짜별 실패 후 다음 날짜 진행, 기존 Native 누적 재시작 및 공통 Production Launch Gate는 유지한다.
