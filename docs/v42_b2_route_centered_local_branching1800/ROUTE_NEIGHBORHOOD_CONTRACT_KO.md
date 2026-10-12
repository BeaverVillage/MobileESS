# Route-Centered Neighborhood 수학 계약

Source18r의 원본 Exact C3A+Dense CSR/RHS/Sense/types/objective는 변경하지 않는다. 원본 box의 일부 Route Node/Flow만 center literal로 고정하고 원본 bounds보다 좁은 영역에 Hamming 검색 제약을 추가한다. 이 영역은 원본 FULL 가능영역의 부분집합이며 제한 ObjBound는 Global LB가 아니다.

모든384 Mode와 4대 Pch/Pdis/Q/SOC97의 원래 bounds를 유지한다. Hamming은 자유 Route Node만 포함한다. Radius는 실제 원본 DAG witness의 최대 Node 변경거리에 사전등록 slack을 더하며 radius24/48을 강제하지 않는다. 중심과 다른 실제 MOVE 경로를 증명한 뒤 실행한다. Witness는 ETA/Arc/domain/alias/terminal topology의 증거이고 SOC/Grid 대체 가능성은 주장하지 않는다.

변경 구간은 중심의 실제 vertex에서 시작하고 끝난다. 선택 Site와 시간창은 heuristic corridor이며 원본 전체 경로 공간의 정확한 prescreen으로 부르지 않는다. 이 corridor 안에서 원본 Arc의 forward/backward reachability로 dangling Arc만 정확히 제외한다. 후속 Node/Flow와 원래 slot96 terminal 상태를 함께 열고 unselected 차량과 외부 구간은 원래 경로로 고정한다. 구간 경계의 기존 Site 고정은 이웃 정의이며 새 물리적 복귀 의무가 아니다.

원본 역 Alias를 독립 재귀 전개하여 닫힌 Original Arc/Node가 자유 Native 열을 통해 활성화되지 않음을 box에서 검증한다. Hamming native 계수/RHS/sense, full Source prefix, types, objective, bounds, Start vector와 center 포함성을 readback한다.

PR219 Raw는 원본 수치 validator PASS인 point이며 약5e-13 연속 상한 잔차를 보정하지 않는다. 원본 FeasibilityTol 정책을 유지하고 새 fixings/Hamming은 literal로 만족한다. 이 점을 dyadic exact primal feasible point라고 과장하지 않는다. 경로 고정 ablation은 center 경로와 모순되어 MIP Start를 사용하지 않는 별도 진단이다. A0를 재최적화하지 않는다.

R1/R2는 첫/후반 MOVE의 제한 연결, R3는 MESS03의96슬롯 경로와 고정된 나머지3대, R4는 MESS03+한 차량을 변경한다. R5는 앞 단계 정체 후 새 Beam path와 주변 Arc를 하나의 제한 MILP에 합쳐 보조한다. 동일 mathematical bounds/Hamming signature를 반복 실행하지 않는다. 개선 center는 FULL PASS이고 이전 UB보다 유의하게 낮을 때만 갱신한다.
