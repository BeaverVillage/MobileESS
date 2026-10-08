# Grid 원본 보존과 정확한 separation

모든 original voltage·thermal·transformer·injection-binding·response-binding 행과 finite bounds를 처음부터 보유한다. 일부 critical row만 남기는 축소나 변수 복사는 없다. 잔여 network variables의 유일 affine 표현을 가정하거나 임의로 삭제하지 않는다.

Archived fractional LP와 원래 integer UB를 v42_rowgen.core.separate로 전체 582,808행에서 검사했다. Sparse product의 roundoff enclosure로 screening하고 1e-8 boundary의 불명확한 행은 exact binary-rational dot으로 판정한다. 모든 위반을 반환하며 top-K는 없다. Fractional point의 strict residual FAIL을 보존하고 UB/global LB로 사용하지 않는다. 원래 UB는 전체 C3A와 unreduced grid 673,920행, A1·route·SOC·P/Q·PCS replay를 통과했다.

새 ROOT에서는 모든 원래 행과 유효 추가 651행을 명시적으로 포함한다. LB는 그 augmented array와 원래 finite bounds의 weak-duality certificate에서만 채택한다. Grid-only row generation을 다시 실행하는 구조가 아니다. 신규 강화 요소는 route–SOC temporal integer disjunction이며 실제 LB 효과는 새 ROOT에서 측정해야 한다.
