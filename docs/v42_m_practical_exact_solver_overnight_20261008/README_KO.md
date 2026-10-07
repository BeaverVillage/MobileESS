# M-stage practical exact solver candidate

원본 PR162 C3A의 `minimize rho` 목적함수와 수치 배열을 실행 전에 대조합니다. 원본 전체 C3A/route/SOC/PQ/PCS/grid/A1 replay를 통과한 해만 UB로 인정합니다. 기준 LB와 원본 전체-domain native bound 또는 모든 OPEN 노드를 포함한 exact external certificate를 구분합니다. Hamming 실험의 bound는 전역 LB가 아닙니다.

`IMMUTABLE_DEADLINE.json`의 한 deadline이 preflight, build, solve, replay, 보고서, 게시까지 포함합니다. 종료 시각을 stage마다 새로 만들지 않습니다. 각 run의 `OPTIMIZE_ONCE.json`은 중복 실행을 차단합니다.

`native_runner.py`는 한 번의 1800s Cuts=0 대조 실행과 조건부 primal 실험을 수행합니다. `native_production_runner.py`는 동일한 원본 모델의 production 후보이며, callback payload가 없는 POLLING에서도 wall deadline와 첫 60분 정체를 확인합니다. 실행별 전체 MIP start, 모든 incumbent event, 관측 node/bound ledger, root 단계, Runtime/Work/RSS, numerical warnings와 원본 replay를 저장합니다.

**Native Gurobi tree의 재시작은 지원한다고 주장하지 않습니다.** 저장한 valid incumbent를 MIP start로 공급한 후 새로 optimize하는 것은 fresh solve입니다. native callback ledger는 모든 관측 MIPNODE와 bound 상태이며, Gurobi가 API로 노출하지 않는 내부 node별 proof까지 포함한다고 주장하지 않습니다.

`external_controller.py`는 deterministic best-bound OPEN 큐를 실제 checkpoint에서 복원합니다. 원본 binary bound fixing만 적용하고 분기 양쪽을 유지합니다. OPTIMAL LP 이후 original-domain exact dyadic dual certificate, exact Farkas contradiction 또는 validated UB와의 인증된 비교만 pruning을 허용합니다. solver-independent core는 등록된 M0 `bb_controller.py`의 byte identity를 유지합니다.

부모의 완전한 VBasis/CBasis를 자식에게 공급하고 dual simplex를 사용합니다. 실제 log에 수용 근거가 있을 때만 basis accepted라고 기록합니다. 비교 실행 없이 warm-start speedup을 주장하지 않습니다. 재시작 전 certificate를 원본 배열에서 독립적으로 다시 계산하며, 실패한 시도도 SHA와 함께 보존합니다. numerical/time-limited node는 OPEN에 남습니다. 기존 M0 PID/script/worktree가 실행 중이면 새로운 external root를 차단합니다.

예시 명령은 새 실험 승인이 있을 때 사용합니다. 이 야간 작업의 deadline이 지난 뒤에는 자동으로 실행되지 않습니다.

```powershell
python docs/v42_m_practical_exact_solver_overnight_20261008/native_production_runner.py --name fresh_production --kind production --seconds 10800 --center <replay-PASS-point.npz> --initial-lb <valid-global-LB>
python docs/v42_m_practical_exact_solver_overnight_20261008/external_controller.py --resume --center <replay-PASS-point.npz>
```

External crash로 node LP가 미완료라면 `--recover-node <id>`를 명시해야 합니다. 이전 시도를 원본 byte 그대로 보존하고 같은 OPEN domain에서 새 LP를 실행합니다. native tree resume와 혼동하지 않습니다. checkpoint는 최소 매 5분 및 모든 node 완료 후 저장합니다.

검증 명령: `test_protocol.py`, `test_production_restart.py`, 등록된 M0 `test_exact_bb.py`. 이 fixture들은 native optimize를 호출하지 않습니다. 수학적 terminal proof, 양쪽 자식 coverage, deterministic best-bound, checkpoint 복구, 변조 거부 및 restricted-bound 권한 구분을 확인합니다.

P2는 원본 inherited P1 acceptance를 만족한 뒤에만 movement energy → movement count로 실행합니다. P1 lock은 repository `P1_EPS=1e-7`, 후속 component lock은 `COMPONENT_EPS=1e-8`입니다. 아직 acceptance가 없으면 P2를 실행하지 않습니다. A2/M2/Planning/Actual/Fresh AC는 이 패키지 실행 범위에 없습니다.
