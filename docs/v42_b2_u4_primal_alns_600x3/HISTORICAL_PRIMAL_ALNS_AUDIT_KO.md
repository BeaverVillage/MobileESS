# Primal ALNS 실행 전 과거 Primary Source 감사

PR169/179/183/194의 Model·계수·UB는 다른 Source의 연구 수치다. 이번 Source18r의 초기 UB 또는 후보 해로 재사용하지 않는다. 현재 초기점은 원본 FULL에서 검증된 U4의0.6760534504652341이며 세 후보 모두 그 동일 point/SHA에서 독립 시작한다. K32를 기본 LB 모델로 참조하되 같은 문제 K48의 더 높은 인증 하한0.46498486997548166도 보존하고 새 하한 최적화는 하지 않는다.

|Primary 연구|검증된 관측과 실제 한계|현재 설계 반영|
|---|---|---|
|PR169|차량4대 node/mode 슬롯64..84, 자유 Binary2100, Hamming24, TimeLimit300/Threads1. 실제112.52999997초에서 UB0.6694159238756877→0.6339776033797229, 원본 replay PASS. 모든 이산변수 고정 P/Q 재최적화는0.680초, 개선8.27e−12 수준.|Mode와 실제 이동을 함께 개방할 근거다. 과거21슬롯·radius24는 참고이며 현재 signed grid/ETA/SOC/return 가능성으로 결정한다. 과거 UB를 현재 UB로 옮기지 않는다.|
|PR179|Native control1800.183초에2 nodes, production3603.095초에1 node. Cold child53시도 중52 OPTIMAL, 중앙197.566초/p90275.129초이나 인증하한 상승·exact pruning0. Global gap9.82144% 정체.|새 unrestricted Full B&B를 실행하지 않고 FULL 모든 물리를 유지하는 제한 neighborhood만 비교한다. Restricted BestBound를 Global LB로 사용하지 않는다.|
|PR183|20개 기존 이산배정의 feasible recourse는 median2.002초/p902.231초이고 당시 UB0.6306505800→0.6284141956 개선. 첫 새 master 배정의 recourse120초는 TIME_LIMIT, 유효 분리 cut 미완료로 canary 중단.|기존 가능한 경로의 P/Q와 새 경로의 recourse 난이도를 구분한다. TIME_LIMIT은 infeasibility 증명이 아니다. Raw point와 FULL replay 성공/실패를 모두 보존한다.|
|PR194|초기 stationary 점의 전압 한계 실패와 Seed 예산 소진·복구 누적을 감사했다. May01 저장 시도는 finite-bound exact LB 인증 예외로 IMPLEMENTATION_FAILURE, cumulative Native4538.198초이며 Adaptive에 진입하지 못했다.|이미 검증된 동일 U4 FULL point에서 시작해 Seed/새 LB Solve를 생략한다. 실패·중단도 해당 Ni의 actual Runtime에 누적하고 예산을 재설정하지 않는다. Unbounded helper를 임의 finite로 바꿔 인증을 만들지 않는다.|
|PR207|같은 Source18r FRESH_U4는 요청90초, 실제38.5069999695초, 제한 neighborhood OPTIMAL. 초기 UB와최종 UB가 동일하고0nodes/0simplex, presolve30.18초. Unrestricted Full600은 실제601.896999836초, ROOT528.89초까지 미완료.|U4의 빠른 제한 OPTIMAL은 FULL 전역 최적성이나 이동해 개선 불가능성 증명이 아니다. Mode/route 개방 범위와 signed grid를 확장할 여지가 있으며 실제600초 비교로 판단한다.|
|PR211|K32의0.4812227124583283 integer incumbent는 reduced Grid 해이며 원본 FULL Security 위반이 있었다. K32 LB0.46497617639758426와 추가K48 LB0.46498486997548166는 하한 인증 증거다.|K32 경로/Mode는 선정 진단에만 사용한다. K32 incumbent를 FULL UB 또는새 Global LB로 승격하거나 FULL 가능성 복구용 추가 Heavy Solve를 실행하지 않는다.|
|PR214|SOC32행은 BASE와같은 LP 목적값, 인증 correction 차이2.4e−8 수준. GRID16은 중단되어 효과 미인증. 물리적 강화로 material LB 개선을 입증하지 못했다.|가중치/Root LP/제약 반복 연구를 다시 실행하지 않는다. 현재 비교는 실제 원본 FULL 검증 UB 개선에 집중한다.|
|PR215|Snapshot75/82/94와 compact896B Window[88,96)의 유효 LB는 기존0.46498486997548166보다 약했다. 자유 Window 경계와 외부 시간 완화는 FULL보다 넓은 영역이다.|Snapshot/Window incumbent는 FULL 초기점·UB로 재사용하지 않는다. 이번96슬롯 원본 SOC·경로·전체 Grid를 모두 보존한 Primal neighborhood와 수학적으로 구분한다.|

Source18r U4 실제 log/result/parameter/replay bytes는 원본 Git evidence index 및 중첩 native receipt SHA와 독립 대조하고 historical_primary/PR207에 보존했다. U4의 raw log는 presolve 이후840 Binary와 loaded user MIP start를 보여주며,38.507초 종료의 정확한 제한영역 결과를 뒷받침한다. 이것은 전체 FULL 가능영역의 최적성 인증이 아니다.

원래 v42_common_mess.engine.optimize_case는 U4의 유한 탐색 종료 후 _full_milp_phase fallback으로 이동할 수 있다. 이번 연구 Adapter는 이 fallback을 호출하지 않으며 모든 Native를 N1/N2/N3의 검증된 Restricted Neighborhood로만 실행해야 한다. 원본 모듈은 덮어쓰지 않는다. 기존 U4가 모든 mode0이라고 PR169 이력에서 추정하지 않고 현재 point의 실제 Mode/P/Q/경로를 별도로 진단한다.

요청의 중심 정의는 각 Ni의 실제 Native Runtime 합계600초다. 각 호출의 요청 TimeLimit·실제 Runtime·반환 overhead를 따로 기록하며, 조기 OPTIMAL 호출의 사용하지 않은 요청시간을 Native 사용량으로 차감하지 않는다. 다음 호출은600−누적actual Runtime의 남은 예산에서1초 반환 여유를 두고 TimeLimit을 설정한다. 따라서 조기 종료가 여러 번이면 요청 TimeLimit 합계가600을 넘을 수 있지만 실제 Native 사용량은 리셋되지 않고600초 이내로 관리한다. 실제 Runtime 미확정은 해당 후보 예산을 격리하며 임의0으로 만들지 않는다. 동일 실패 neighborhood 반복·parameter sweep·후보 간 예산 이월은 금지한다. Solver 반환 초과는 숨기거나 Runtime을600으로 잘라내지 않고 실제 초과 여부도 보고한다.

Primary code/result/proof의 exact Git blob OID/SHA256와 원문 사본 목록은 HISTORICAL_PRIMAL_ALNS_AUDIT.json에 있다. 사본 Python을 import/실행하지 않았고, 감사 Native/Gurobi import/모델 생성은0회다.
