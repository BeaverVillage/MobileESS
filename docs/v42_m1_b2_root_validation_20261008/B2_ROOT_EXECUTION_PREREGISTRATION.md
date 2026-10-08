# B2 ROOT 900초 단일 실행 사전등록

직접 기준 PR185 exact HEAD: `6d1d64beaf012d32ddf39245890785e3d8f01d4b`. 과학적 기준은 PR162 original C3A이며 min rho_max objective SHA256은 `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`다. PR185의 root.py·temporal.py·exact_cut.py·resource.py·verify.py를 byte-identical로 재사용한다. 새 코드의 추가 기능은 source/model transport 확인, raw native attribute·presolve 수집, 사후 비교다.

원래 306,040열·582,808행·5,351,612 nnz와 651개 route–SOC 행·1,302 nnz를 사용한다. 최종 583,459행·5,352,914 nnz다. 새 cut 생성·변수·domain 변경은 없다. Original binary 9,322개는 ROOT에서만 연속 완화한다. 원래 objective·ObjCon·axis·matrix·RHS·senses·bounds·types와 원본 물리를 보존한다.

설정: Threads=1, Method=2, NodeMethod=1, Crossover=0, MIPFocus=3, MIPGap=0.005, FeasibilityTol=OptimalityTol=IntFeasTol=BarConvTol=1e-8, DegenMoves=0, Seed=20260929, TimeLimit=900. 실제 native 모델에서 읽어 동일성을 검증한다. MemLimit·SoftMemLimit은 default infinity이며 RAM은 관측만 한다.

이번 별도 namespace에서 native optimize는 최대 한 번이며 자원 격리·equivalence가 통과한 경우 정확히 한 번 실행한다. 기존 resource.py 진입 검사를 그대로 따른다. 실패하면 optimize=0으로 종료한다. 다른 프로세스·priority·source·checkpoint·로그를 수정하지 않는다. B0는 archived 결과를 사용하고 B1·H2·canary·production·downstream은 실행하지 않는다. 재실행·parameter sweep·추가 root는 금지한다.

Native 종료 직후 X/Pi/RC/Slack와 native 속성·callback 메시지를 먼저 저장한다. 종료 상태와 exact LB certificate를 구분한다. OPTIMAL일 때만 원래 full augmented CSR와 모든 finite bounds에서 exact weak-duality LB를 검증한다. Raw 부호 오류는 거부하고 별도 수학적 multiplier가 있으면 원본과 구분한다. 인증 검증은 optimize=0으로 수행한다. Native ObjBound나 LP fractional point를 global LB 또는 integer UB로 채택하지 않는다.

기존 LB=0.5687116104049206, UB=0.6284141956452488, archived native LP objective=0.568711942993466. Final valid LB=max(inherited LB, independently certified B2 LB), UB는 고정이다. Delta_LB는 이 final valid LB의 개선량이다. Material gate는 OPTIMAL·integer equivalence·독립 certificate PASS·Delta_LB≥0.001·Runtime≤900초의 동시 통과다. 0.5% 목표 LB=0.6252721246670225와 구분한다. M1_ACCEPTED=false를 유지한다.

Native objective가 archived 값과 절대 차이≤1e-6이면 SAME_LP_OPTIMUM 비교 분류를 사용한다. 이는 native 수치의 비교 기준이며 scientific feasibility tolerance 변경이나 두 exact LP 최적값의 동일성 증명이 아니다. 정확한 source residual, exact LB, 인증 손실을 따로 기록한다. OPTIMAL이어도 인증 실패면 NUMERICAL_CERTIFICATION_FAIL이다. 미완료/Runtime>900초면 TRACTABILITY_FAIL, 자원 진입 실패면 RESOURCE_PENDING이다. 나머지 유효 certificate 결과는 ΔLB≥0.001 여부로 MATERIAL/NONMATERIAL을 구분한다.

651행의 archived/new exact violation·slack·Pi, fractionality와 SOC·route/PQ/PCS/grid 변화를 사후에 분석한다. 실행하지 않았거나 속성이 없으면 null/NOT_MEASURED로 표기한다. 보고서 작성 중 추가 optimize를 허용하지 않는다. 다음 행동은 결과에 근거해 정확히 하나만 추천하고 실행하지 않는다.
