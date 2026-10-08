# 양방향 정수 영역 포괄 증명

선택 column j는 원래 C3A의 binary이며 원래 bounds는 [0,1]이다. 따라서 모든 원래 정수 feasible vector의 z_j는 정확히 0 또는 1이다. 원래 정수 영역 F=F(z_j=0)∪F(z_j=1)이며 두 영역은 서로소다. 기존 651개 부등식은 모든 원래 정수 vector에 유효하므로 각 child LP는 해당 원래 정수 영역을 포함한다. LP 구성은 선택 column의 두 bounds만 [0,0]/[1,1]로 바꾸고 나머지 binary를 C로 완화한다. 다른 위치나 route의 추가 고정은 없다. 목적함수·전체 CSR·RHS·senses·나머지 bounds는 원본 augmented 모델과 bit-identical이다.

각 child의 정확한 bounded weak-duality 하한을 L0,L1이라 하면 모든 F의 목적값은 min(L0,L1) 이상이다. 한쪽 native 목적값을 전체 하한으로 사용하지 않는다. 독립 pair들의 유효한 min 값만 max(inherited LB, pair1, pair2, pair3)에 넣는다. 미완료/미인증 sibling은 폐기하지 않고 unresolved로 유지한다. Native INFEASIBLE은 독립 Farkas proof가 없으면 +infinity로 승격하지 않는다.

Charge_mode는 unit/time마다 독립 원본 column이다. 선정된 두 mode의 네 가지 0/1 조합을 원본 idle feasible start의 같은 route/PQ/SOC에 대입해 원본 행·B2 행을 검사하여 서로 동치가 아님을 확인했다. 일반 path 정수 projection은 원래 nonparallel forward DAG와 unit source flow, binary vertex through-mass에 대한 PR183의 SHA 보존 증명을 재사용한다. 과거 불가능한 전체 배정은 개별 pivot의 전역 infeasibility 증명이 아니다.
