# PR180 이후 새 A-stage continuation

BASE는 Draft PR180 exact HEAD `8b90bdda26de480715e243249f62d46ff9bf1a54`이다. PR180 artifact와 expired budget은 byte-identical로 보존한다.

사용자가 새 continuation budget 생성과 native 실험을 승인했다. 기존 authoritative A1 time contract `v42_pr134_b1.common.BUDGET=3600` 및 PR134 A1 `total_TimeLimit=3600`에 따라 하루 optimizer 합계 3,600초, 네 날짜 합계 14,400초를 적용한다. build/pricing/validation overhead를 포함하는 새 8시간 wall safety guard를 별도로 기록한다. 이 guard는 과거 PR180 deadline을 수정하지 않는다. 30분은 end-to-end practical acceptance 목표이며, 3,600초 optimizer limit으로 PASS가 자동 성립하지 않는다.

May19 shift는 full-domain 원본 integer 모델·원본 objective cutoff partition·final native bound를 독립 재구성하고 incumbent 물리 replay를 재실행한다. LB948/UB950의 gap이 0.5% 이내여도 정확한 최적값 950을 주장하지 않는다. 별도 GLOBAL_GAP_ACCEPTANCE만 발행한다.

통과하면 rho accepted UB +1e-7, migration_count=0, accepted shift=950을 lock하고 원래 prestart objective를 실행한다. replay-PASS incumbent를 nonbinding MIP Start로 사용하며 원래 행·계수·bounds·integer types·scientific tolerances를 변경하지 않는다.

May19 4목적·전체 original physical replay·job/input identity와 freeze가 PASS일 때만 May17 → May10 → May12를 실행한다. 다음 날짜의 full physical 후보 cache는 해당 날짜의 데이터와 producer byte identities를 검증한 뒤 freshly price한다. May19 후보는 재사용하지 않는다. 각 날짜의 결과와 실패를 보존하고 독립적으로 수락한다.

모든 native solve는 Threads=1이며 한 process로 순차 실행한다. System RAM/commit reserve는 기존 2GiB guard를 유지한다. M-stage worktree/process는 조회하거나 제어하지 않는다. M1/A2/M2/Planning/Actual/Fresh AC는 이 continuation 범위 밖이다.
