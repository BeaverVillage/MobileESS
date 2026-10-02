# 다음 수정

판정: STOP_CANARY_START_NOT_ACCEPTED.

Full domain과 모든 scientific rows를 보존한 채 integer dimension은 95.477% 감소했다. Connected expression의 outgoing-movement 치환으로 nnz는 53.074% 증가하므로 presolve, simplex factorization, branch 성능을 증거로 해석해야 한다. Root projection은 동일해야 하며 bound 자체 강화는 이 representation의 목표가 아니다.

사전 material 기준은 gap 20% 또는 valid LB 0.001 개선이며 결과 후 변경하지 않는다. Promising이면 별도 사용자 승인 후 1800초 production을 실행할 수 있다. 미달이면 exact 보조 connected continuous variable와 sparse linking row를 사용하는 대안의 exact projection/계수/새 preregistration을 먼저 준비할 수 있으나 이번 결과를 바꿔 재실행하지 않는다. Root equivalence가 미인증이면 full MILP를 계속하지 않고 수치 종료 상태와 mapping 잔차를 확인한다.

MIP start가 solver에서 채택되지 않았다면, 이는 compact 성능 열위를 확정하는 결과가 아니다. 원 physical point는 독립 검증 PASS이나 봉인된 F3 matrix 최대 잔차 3.0752360699604075e-8은 등록된 FeasibilityTol=1e-8보다 크다. Start 거부의 가능한 원인으로 기록한다; solver가 원인 행을 공개하지 않아 인과를 단정하지 않는다. 다음 별도 등록 실험에서는 scientific P/Q/SOC/rho를 바꾸지 않는 auxiliary consistency 재구성과 양 arm의 완전한 Start tolerance audit를 먼저 준비할 수 있다. 이번 paired canary의 tolerance/Start를 사후 수정하지 않는다. 실패한 Start 조건에서 post-root branching 개선을 입증했다고 주장하지 않는다.

P2/A2/M2/Actual/Fresh AC는 NOT_RUN. M1_ACCEPTED 및 Problem13_FINAL은 false 유지. 중단한 Benders acceleration lane은 그대로 보존한다.
