# 알고리즘 계약

Source18r PR207, IEEE123 B2 May01의 원본 FULL Identity를 유지한다. 변경은 새 연구 Adapter와 증거 디렉터리에 한정한다.

Cold stationary→U4→N1으로 이번 실행의 FULL UB를 만들며, 기존 N1은 회귀/성능 참고만 허용한다. 이후 모든 Route-Fixed 후보는 원본 DAG MOVE≥1을 포함하고 N1 stationary 경로와 다르다. 전체384 Mode와 원본 Pch/Pdis/Q/SOC 경계·Grid/PCS/SVR/Cap/AIDC/초기종단SOC를 유지한다. Node/Arc/Flow/Alias 고정과 실제 ETA/이동에너지 및 Native Readback을 확인한다. 신규 경로에는 모순된 N1 Solver Start를 주지 않는다.

BEST_GLOBAL_UB와 BEST_MOVING_FEASIBLE_UB를 분리하며 Original FULL Replay PASS 및 1e-8 이상 실질적 개선만 Global 중심을 갱신한다. TIME_LIMIT을 INFEASIBLE로 해석하지 않는다. Restricted ObjBound는 Original Global LB가 아니다. K32/K48와 원본 유효행으로 강화된 relaxation의 인증 Gurobi ObjBound만 Global LB 후보다.

Beam64 및 최대3회 이동깊이/Score/다양성은 Heuristic이다. Hard Pruning은 원본 고정0 Arc 및 최대충전 SOC 상한의 안전한 필요조건 위반이다. 이동해 진단을 FULL 전역 최적해로 승격하지 않는다.

모든 Optimize는 Heavy Worker1/Threads1로 순차 실행하고 단일 Native Runtime 원장 최대1800초를 공유한다. 5초 종료 여유를 두며 조기 종료를 허용한다. Source Drift 및 RAM4GiB/Commit6GiB/모델증가 Reserve 위반은 FAIL-CLOSED한다. Raw를 수정하지 않고 실패 Raw도 보존한다. B1/B3/IEEE8500/다른 날짜/May 전체/Actual 실행은 하지 않는다. 계약 충족의 Planning Freeze가 없어 ACTUAL_NOT_RUN을 기록한다.
