이번 재검증은 PR153 parent 3d33133e0c4177cb417ee3f03a85cde21f2b43a0에서 시작한다. 원래 A/B raw receipts와 PR152 artifacts는 변경하지 않고 clean_revalidation 아래에 새로운 read-only snapshot과 출력을 보관한다.

Guard는 nonblocking py-spy snapshot의 PID와 동일한 process create_time, native engine mapping, 현재 실행 중인 source-bound optimize/presolve/Solve 호출 행을 함께 확인한 경우만 foreign native conflict로 판정한다. 단순 import/reservation, Python mock/scheduler, 읽을 수 없는 state는 확인되지 않은 상태로 기록하며 conflict로 간주하지 않는다. 모든 positive proof에 PID, thread, source text SHA, 호출 행, 관측 시각을 남긴다. 샘플 기반 관측이므로 미관측 호출의 부재를 수학적으로 보증하지 않는다. 다른 Lane의 제어는 하지 않는다.

A-stage의 전용 supervisor/worker lifecycle barrier는 별개다. benchmark_a_stage_vnext2.py의 live PID가 모두 종료되고 terminal receipt를 읽은 뒤 pair admission을 한다. 기존 RAM >=1GiB, commit<95%, sustained paging 보호는 유지한다.

Preflight 대기는 시계 시작 전에 완료한다. 시계는 pair child launch 전에 시작해 두 leg의 시작 검사, 모델 build, pricing, admission audit, RMP, cleanup, intervening waits와 process reap까지 연속으로 측정한다. 최대600s, 자동 연장 및 재시작 없음. Native budget<=300s/leg도 추가 보호로 유지한다. Pricing20s/worker, four-way Threads=1; original cold RMP cap200s. Shared wall 잔여가 부족하면 cap을 줄이고, wall reserve에 도달하면 own solve만 중단한다. 실패한/중단된 native receipt는 certificate에 사용하지 않는다.

Efficiency=(audited upper_before-upper_after)/full leg wall seconds. Full leg wall에는 원본 hash 검사, admission/build, pricing, independent candidate audit, RMP audit 및 dispose/cleanup도 포함한다. 선택은 science PASS, invalid=0, guard interruption=0, both upper nonincreasing, pair wall<=600s, Challenger efficiency>=1.2*Baseline을 모두 만족할 때만 true다. Single pair이며 통계적 causal uniqueness는 주장하지 않는다.

Harvest selection/physics/worker/Certification implementation은 PR153에서 byte-identical이다. Alpha=.1, original full domain, exact true-dual acceptance, K8/MESS32/round를 유지한다. 각 leg 정확히1Discovery+1RMP. Authoritative continuation, Certification, B&P, May production은0. 선택 여부와 관계없이 이 pair 이후 STOP한다.
