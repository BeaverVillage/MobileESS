# 4-MESS Joint Route-Pool 및 Selective K32 포함관계

원본 Source18r Exact C3A+Dense의 변수, 행, bounds, types, 목적함수를 각각
`y, A, b, [l,h], t, c`로 둔다. 각 차량 u의 후보 경로 r는 원본 DAG에서
초기 vertex부터 slot96까지 이어지는 완성 경로다. 실제 MOVE ETA와 에너지는
원본 arc 객체의 값이며 별도로 생성하거나 조정하지 않는다.

각 경로의 Native Route Flow/Node indicator를 `a[u,r,j]`로 정의한다.
Joint 모델에는 다음 정의식만 추가한다.

```
lambda[u,r] in {0,1}
sum_r lambda[u,r] = 1                  (각 차량 u)
y[j] = sum_r a[u,r,j] lambda[u,r]       (해당 차량의 Route 좌표)
```

모든 후보에서 같은 값을 갖는 좌표는 그 공통 값으로 bounds를 고정한다.
나머지 좌표는 위 등식으로 연결한다. 각 차량은 정확히 하나의 완성 원본
경로를 선택한다. 원본 Arc의 affine inverse alias를 각 경로에서 독립 전개해
선택된 Arc/Node/Flow가 동일 경로라는 것을 검증한다. Alias의 상수항도
`sum lambda=1` 아래에서 그대로 유지된다. Source의 모든 나머지 행과
384 Charge Mode/Pch/Pdis/Q/SOC97의 원래 bounds/types를 보존한다.

따라서 Joint 가능점의 원본 변수 사영은 원본 FULL 가능영역에 속한다.
이는 제한 부분집합의 Primal 보증이며, 제한 문제의 ObjBound는 원본
Global LB가 아니다. 후보마다 STAY와 MOVE가 있고 네 차량의 선택권이
동시에 열리지만, 모든 차량의 MOVE를 강제하지 않는다. 경로상 가능한
4대 MOVE 조합의 SOC/Grid 공동 가능성은 실제 MILP와 FULL Replay로 판정한다.

PR220와 현재 FULL 중심의 경로는 후보집합에 포함한다. 원본 Raw의 배열을
그대로 Start에 넣고, 그 경로의 one-hot lambda Start를 별도로 읽어 검증한다.
경로가 맞지 않는 전체 Raw를 비교군의 Start로 넣지 않는다.

Dual 모델은 별도 방향의 포함관계를 갖는다. 독립 인증된 K32 사영을 P,
전체 원본 Binary를 B, 유지하는 부분집합을 S로 두면 다음이 성립한다.

```
Projection(FULL integer feasible set) subset P with all B integer
                                     subset P with S integer and B\S continuous
```

이번에는 원래 [0,1] bounds를 유지한 채 일부 원본 Binary의 타입만 C로
완화한다. K32의 모든 계수/RHS/Sense/Objective 및 기존 conservative outward
projection은 그대로다. 새 Grid 행이나 새로운 반올림은 없다. 따라서
실제 Native ObjBound가 숫자·Readback·Resource·포함관계 Gate를 통과하면
Global LB 후보로 사용할 수 있다. 기존 K48보다 낮으면 K48을 유지한다.

K32의 기존 축소 정수 witness 목적값0.4812227124583283은 이 Selective
모델에서도 가능하므로, K32 행을 유지하는 실험에는 그 정식화 상한이
있다. 이를 FULL UB로 사용하거나 3% Gap 목표의 달성으로 해석하지 않는다.

V1의 extended NPZ는 원본 validator의 point-only packet 계약에 맞지 않았다.
V1 Native 패킷, lambda, 소스와 원장은 변경하지 않았다. 계획 배열의 모든
비트를 비교한 뒤 point 필드만 원본 입력 형식에 저장해 독립 FULL Replay를
수행했다. 이는 포장 형식의 무손실 분리이며 수치 rounding/clipping/repair가
아니다. V2 Native는 처음부터 point-only 패킷을 저장하고 lambda 원시값은
Native capture JSON에 보존한다. V1 Runtime도 같은1,800초 예산에 합산한다.

이 구조적 정확성, 원본 수치 FULL validator의 PASS 및 Gurobi의 numerical
B&B ObjBound 계약은 서로 구분한다. Exact rational primal feasibility나
전역 경로 최적성, 전체 원본 경로 공간 소진을 주장하지 않는다.
