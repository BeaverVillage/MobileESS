# 원본 FULL과 통합 Primal 제한영역

Scientific Source18r와 Case는 PR216의 동일한 CSR/RHS/sense/bounds/type/objective 및 exact inverse transport 인증으로 고정한다. 새 Adapter는 matrix coefficient, 상수, Source MESS 물리, Forecast, SVR11, 정격과 수치 정책을 변경하지 않는다.

원본 FULL 영역을 F, 기존 인증된 Dense 좌표영역을 D, 원본 좌표 복원을 L이라고 하면 기존 인증은 L(D)=F 및 원본 LP/정수영역의 동등성을 확인한다. 새 문제는 D에 일부 원본 이산변수/route flow bound 고정과 Primal Hamming 행만 추가한다. 따라서 새 영역 D'⊆D이고 L(D')⊆F다. 이는 상한 탐색 제한이고 하한 완화가 아니다. 새 제한 ObjBound는 원본 FULL Global LB로 사용할 수 없다.

Cold 초기화는 기존 Source stationary_paths/values_for가 실제 원본 DAG의 STAY Arc, Node-Activity, terminal slot96과 Mode0 대표값을 생성한다. 이 값은 문자 그대로 0/1이며 저장된 해에서 가져오지 않는다. 원본 type은 유지하고 고정 대표값 이외의 P/Q/SOC/helper bounds는 원본과 같다. 첫 모델에는 start=None이며 NumStart=0을 Native에서 읽어 확인한다. 이후의 모든 start 파일은 이번 Canary의 calls/ 아래에 생성된 Raw 및 원본 FULL Replay로 한정한다.

U4는 기존 Source selector의 free/fixed set, radius48 및 동일한 signed Grid/PCS16 로직을 재사용한다. 해당 selector가 library import로 Gurobi DLL을 로드하므로 별도 Native0 프로세스가 이를 수행하고 종료한 뒤 Native worker를 시작한다. Guard를 제외하거나 DLL 검사를 완화하지 않는다. 후보 선정 동안 필요한 원본 FULL CSR은 모델 없는 scope에서 하나만 읽고 해제한다.

N1은 모든 Route/Node/route flow 및 alias를 중심점에 고정하고 4대의 384개 Mode를 모두 개방한다. Hamming radius384는 모든 Mode 이진 조합에 대해 추가 제한을 만들지 않는다. N2+/N3+는 선택한 1대/2대의 Node와 원본 Route를 개방하면서 384개 Mode 전체를 개방한다. 나머지 차량 Route는 고정하되 해당 차량 Mode/P/Q/SOC는 재최적화한다. 각 차량의 독립 SOC/PCS/ETA/이동에너지는 유지하며 fleet 합산 ESS가 없다.

N2+/N3+ Hamming 집합 H는 free Node-Activity만 포함한다. c_j=1−2x̄_j, RHS=R−Σ_{j∈H}x̄_j이며 cᵀx≤R−Σx̄이다. 중심의 변경거리는 정확히0이다. H와 전체 Mode 집합은 서로소이므로 384개 Mode를 모두 뒤집어도 Hamming 행 activity는 바뀌지 않는다. 실제 Native getRow에서 coefficient/index/RHS/sense를 독립 대조한다. Node radius는48/96으로 사전 고정하며 radius sweep을 하지 않는다.

Unselected 차량의 원본 Arc는 고정된 retained Node/route 좌표와 exact alias만의 함수임을 기존 PR216 auditor로 확인한다. 새 actual fixing 배열은 원본 box 안에서 동일 이산/route 좌표만 고정하며, 모든 비route 연속 bounds는 원본과 같다. 기존 FULL Replay를 통과한 중심점에 대해 실제 Native0를 다시 수행한다. 원본 terminal 위치 조건과 SOC760 복원은 그대로이며 추가 귀환 방정식이 없다. 개별 Neighborhood의 window 밖 Node 고정은 Primal 검색 범위를 제한할 수 있지만 원본 전역 문제의 terminal 의미나 차량의 글로벌 귀환 의무로 해석하지 않는다.

원시 callback/final 점은 각각 보존하며 rounding/clipping/PQ/SOC repair를 하지 않는다. 이산 패턴과 목적값 transport는 문자 그대로 검증한다. 연속 원본 가능성은 기존 Source validator의 bound/integrality1e−8, 중요 flow/Grid1e−8, 기타 행1e−6 계약을 유지한다. 보고는 정확한 유리수 연속 가능성 또는0-residual 인증을 주장하지 않는다. 동일 목적의 별도 Solver FINAL 점을 중심으로 고르는 것은 Raw 보정이나 과거 점 대체가 아니다.

Global LB는 동일 Source/Case의 기존 K32/K48 독립 인증만 사용한다. Native 시간은 초기화부터 모든 신규 Optimize actual Runtime을 하나의 Ledger에 누적하고 실패/중단을 포함한다. Solver에 진입하지 못한 Guard 거부는 이전 execution source와 straight-line entry 순서, log, model 부재로 별도 확인하며0회 Optimize를 임의 unknown Runtime의0 대체와 혼동하지 않는다.
