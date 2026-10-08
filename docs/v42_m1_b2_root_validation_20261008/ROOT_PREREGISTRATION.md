# ROOT 사전등록

Source: PR183 `3100039d19a22ec407713f36a9e978b2e96533a8`, scientific PR162 C3A. B0는 archived C3A ROOT를 재사용한다. H1의 grid closure인 B1은 원래 LP와 동일하므로 중복 optimize=0이다. H2는 원본 380 SOC 열의 exact cumulative substitution이며 완화가 같고 예상 nnz 25,937,190으로 채택하지 않는다.

B2는 full 96-slot physics + 모든 원래 grid 행을 보유한 compact monolithic branch-and-cut이다. 원래 변수 306,040개와 binary 9,322개를 그대로 유지하고 exact 정수 유효 이동/SOC 도달 제약 651행, 1,302 nnz를 추가한다. 총 583,459행, 5,352,914 nnz. 모든 scientific coefficients/ObjCon/원본 변수 bounds·types·행을 보존하며 ROOT 실행에서만 이산변수를 연속 완화한다.

Full-scale B2 ROOT optimize는 자원 격리 통과 후에만 최대 1회, TimeLimit=900, Threads=1. 등록 설정: `{"Threads": 1, "Method": 2, "NodeMethod": 1, "Crossover": 0, "MIPFocus": 3, "MIPGap": 0.005, "FeasibilityTol": 1e-08, "OptimalityTol": 1e-08, "IntFeasTol": 1e-08, "Seed": 20260929, "DegenMoves": 0, "BarConvTol": 1e-08, "TimeLimit": 900}`. 원본 min rho_max objective hash `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`. ROOT 종료 후 primal/Pi/RC/slack를 먼저 저장하고 original augmented array의 exact finite-bound lower certificate만 채택한다. raw invalid multiplier는 거부하고 별도의 수학적 multiplier가 필요한 경우 명시적으로 별도 보존한다.

Material gate: certified LB − 0.5687116104049206 ≥0.001, OPTIMAL 종료, Runtime≤900초, 원본 정수 domain/물리/objective 동치성 PASS. Native ObjVal/불완전 pricing/restricted bound를 global LB로 사용하지 않는다. 미완료 ROOT는 tractability failure다. 기존 UB=0.6284141956452488, gap=9.500515051%, 0.5% 목표 LB=0.6252721246670225. 수치 보정만으로 그 차이를 메우겠다고 주장하지 않는다.

Canary는 ROOT material gate 후에만 최대900초, validated incumbent Start, Threads1, original tolerance1e-8, full replay를 요구한다. Production은 canary의 valid bound gain과 search tractability가 확인될 때만 허용한다. 신규 full-scale native 전체 예산을 보수적으로3600초 이내로 기록하며 과거 Runtime을 초기화·삭제하지 않는다. 이번 자원 대기 상태에서는 canary/production을 실행하지 않는다. M1 accepted false와 downstream 금지를 유지한다. MemLimit/SoftMemLimit/RAM 자동 종료는 추가하지 않는다.

다른 A/M native 프로세스가 관측되어 자원 격리를 확보하지 못하면 ROOT를 시작하지 않는다. 다른 작업의 PID/source/worktree/checkpoint/로그를 중지·수정하지 않는다.
