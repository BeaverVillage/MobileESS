# Conservative dual authority and Early B&P

수치-zero authority는 TAU_DUAL=1e-8로 고정했다. Wrong-sign Pi 1개,
최대 4.7607799183594876e-11를 정확한0 경계로 canonicalize했다.
그 후 free-coordinate RC 최대 1.4661290417876949e-11는 numerical consistency PASS이며,
원래 equality의 유리수 증명으로 복원한 최종 free stationarity는 정확히0이다. 개별 RC zeroing은 하지 않았다.
전체83,058 RC/bound-dual 항과1,841 retained-column 제약을 처음부터 재계산하고 독립 CSC로 확인했다.

Strong-duality 차이는 1.7415433958910485e-08, OPTIMAL_DUAL_IDENTITY=false로 보존했다.
Weak duality와 exact rational support, same-dual corrected formula는 PASS:
CONSERVATIVE_DUAL_LB_CERTIFICATE=true, EXACT_DUAL_AUTHORITY_FOR_BAP=true.
제한 RMP safe LB 0.57293858807896125는 global M1 LB가 아니다.
동일 canonical dual의 full-domain box-support corrected LB는 -4.9168560342380223로 유효하지만 느슨하다.
현재 B&P global floor는 검증된 기존 0.56871157253362081를 상속했다.

## Integer UB preparation

1,841-column 제한 정수 master의 첫120초 시도는 TIME_LIMIT/no incumbent다.
원래 seed-column MIP 후보를 사용한 후속480초-cap 탐색은 native283.398초에 OPTIMAL,
전체 준비 native 합계403.414999962초다. 유효 integer UB는 0.66941592387568771.
모든 original rows, exact integer pattern, route/SOC/PCS와 objective를 독립 검증했다.
제한-domain native optimal bound를 전역 LB나 원래 M1 optimality로 사용하지 않았다.

## 600s maximum Early B&P microbenchmark

| Metric | Start | End |
|---|---:|---:|
| Valid global UB | 0.66941592387568771 | 0.66941592387568771 |
| Certified global LB | 0.56871157253362081 | 0.56871157253362081 |
| Global relative MIP gap | 15.043614552672% | 15.043614552672% |

연속 wall 600.246686초, native 499.698000초,
B&P 생성 nodes 11, pricing calls 16, RMP calls 5,
추가 검증 열 16. Node-queue/trajectory/native receipts/raw snapshots는 별도 파일로 저장했다.
Root exact CG convergence 전에 원래 binary projection으로 분기했고 모든 자식이 valid parent floor를 상속했다.
Unfinished RMP objective와 제한-domain MIP bound는 global LB로 사용하지 않았다.
TIME_LIMIT/INTERRUPTED pricing은 최적해로 선언하지 않고 검증된 native bound에만 원래1e-8 safety를 적용했다.
실제 negative pricing RC는 제거/zeroing하지 않았다. Original branch equalities는 retained/unseen trajectories에 동일하게 적용했다.
Restricted infeasibility/미완료 노드는 폐기하지 않고 open domain으로 남겼다.

Peak process RSS 3.250GiB,
process commit 4.384GiB,
minimum available RAM 14.964GiB.
이는 읽기 전용 관찰이며 RAM-based stop/wait/kill/solver-setting policy는 없다.

Gap reduction/wall-second=0.
과거 PR155 root continuation은 같은 certified floor를 유지했다. 이번 integer UB를 고정한
역사적 global-gap 비교의 baseline은0이며, root restricted-LP objective 개선을 integer-global gap 개선으로 대체하지 않았다.
이는 paired fresh-runtime comparison이 아니므로 전체 알고리즘 속도 우열을 주장하지 않는다.
노드/새 열 수 증가만으로 practical selection을 PASS 처리하지 않았다.

EARLY_BAP_SELECTED=false.7200초 grant/실행은 하지 않았다.
최종 global UB 0.66941592387568771, LB 0.56871157253362081, gap 15.043614552672% >0.5%.
P1 NOT_ACCEPTED, P2 NOT_RUN. Physical constraints, full pricing domain, branch coverage,
실제 negative RC 및 global-gap .005를 완화하지 않았다.

600초 시점에 native 종료를 요청했고 마지막 native 호출 종료는 600.022559초다.
종료 영수증과 ledger 기록 0.224127초를 포함한 실제 wall을 그대로 보고했다.
600초 이후 새 optimize 호출이나 예산 연장은 하지 않았다.

System commit은 실험 중 한 번의 read-only spot sample로
20.853GiB /
63.711GiB이었다. 연속 peak 값으로 주장하지 않는다.

검증:81 regression tests PASS,5개 새 early-branch fixture가 direct MILP/complete master와 일치했다.
PR155974개 및 이전 reproduction30개/numerical38개 evidence bytes는 모두 보존했다.
실험 source는 b7c48b95746d1c25cb7a09dab6180f23d7100a11, 신규 Draft PR157이다.
실험 종료 후 adapter에 원래 convexity/bound1e-8 gate와 invalid native point에 딸린 bound 거부를
명시적으로 추가했다. 독립 closeout에서 이번 모든 기록이 이미 이 조건을 통과했음을 확인했다.
이 추가 guard를 이유로 full-scale solve를 다시 실행하지 않았다.
