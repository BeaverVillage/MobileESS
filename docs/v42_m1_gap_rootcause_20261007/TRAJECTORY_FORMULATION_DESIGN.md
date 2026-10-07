# 궤적 formulation 조건부 설계 검토

이 문서는 설계만 다룬다. 96-slot trajectory 생성, pricing, Dantzig–Wolfe, Branch-and-Price를 구현하거나 실행하지 않는다. 네 슬롯 hull 밖의 점이라는 사실만으로 다기간 약함이 global gap의 주원인이라고 분류하지 않는다. 이번 exact separator는 한 슬롯의 location/mode/PQ 결합에서도 성립하므로 시간 차원의 필요성이 독립적으로 입증된 상태가 아니다. material한 valid LB gain과 substitute/coupling 진단을 최종 근거로 사용한다.

향후 다기간 궤적 약함이 확인된다면 `z[m,p]`는 unit m의 완전한 legal route/stay/transit/mode 경로 p를 선택하고 `sum_p z[m,p]=1`로 둔다. 각 경로의 P/Q/SOC 연속 dispatch는 원래 PCS16과 efficiency/movement-energy/SOC bounds 아래 조건부 LP로 남길 수 있다. location/time/departure/arrival/connection state, mode와 연속 SOC 자원이 필요하다. Q는 mode와 독립이며 유효전력 방향만 mode가 결정한다.

SOC를 임의 grid로 이산화하면 원래 integer-feasible set을 바꾸므로 exact 권위로 허용할 수 없다. 순수 discrete shortest path만으로 pricing이 완결된다고 가정하지 않는다. 연속 SOC와 P/Q를 포함한 resource-constrained path/조건부 polyhedral value function 또는 정확한 경로별 LP가 필요하며, 전체 grid dual의 시점·site별 P/Q 비용과 terminal SOC도 포함해야 한다. Label dominance가 모든 원래 연속 경계와 mode/PQ region에 타당한지 별도 증명이 필요하다.

이번 산출물의 정수 궤적 수는 네 슬롯의 자유 경계 local disjunction 수이며, 이를 96슬롯 수나 pricing 비용으로 지수 외삽하지 않는다. 미래 설계 채택 여부와 다음 실험은 최종 원인 귀속 뒤에 결정한다.
