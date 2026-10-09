# Physics-Guided Two-Way LP 실제 검증

판정: **GROUP_BRANCHING_NONMATERIAL**. 실제 Native optimize 5회, 총 Runtime 1664.738000초, Work 2394.028127를 소비했다. 예산 6회/2,880초를 지켰다.

기존 LB 0.5687116104049206 → 인증 Global LB **0.5687116104049206**, ΔLB **0.0000000000000000**. UB는 0.6284141956452488로 유지한다. Global Gap 9.500515051069% → **9.500515051069%**. Material ΔLB≥0.001 Gate=False, M1_ACCEPTED=False. Production·P2·downstream 실행은 모두 0회다.

첫 z=0은 TIME_LIMIT, Runtime 480.078000초/Work 475.722446였다. 사용자의 추가 지시로 z=0만 TimeLimit=1,800초의 fresh solve를 1회 실행했다. 나머지 설정과 scientific model은 그대로이며 z=1은 재실행하지 않았다. 다음 표의 z=0은 추가 실행 결과다. 최초 480초 원시값·diagnostic exact proof와 판정은 INITIAL_480 및 children/C01/z0에 보존했다. 총 호출/Runtime에는 이 첫 실패도 포함한다.

## 실제 양방향 하한

|후보 / 실제 원본 변수|Child|Native 목적값|Exact LB|인증 손실|Runtime(s)|Work|독립 인증|
|---|---:|---:|---:|---:|---:|---:|---|
|C01 charge_mode[MESS02,77]|0|0.568711703525|0.568433650558|0.000278052967|316.039999961853|598.259246514280|True|
|C01 charge_mode[MESS02,77]|1|0.568727375309|0.565357797241|0.003369578068|399.467000007629|407.626045090905|True|
|C02 node_activity[MESS01,STA12,67]|0|0.568716909768|0.566582504650|0.002134405118|231.430999994278|452.998896903691|True|
|C02 node_activity[MESS01,STA12,67]|1|0.568757282931|0.568664132332|0.000093150599|237.722000122070|459.421492343713|True|
|C03 charge_mode[MESS04,77]|0|NOT_RUN|NOT_RUN|NOT_RUN|NOT_RUN|NOT_RUN|False|
|C03 charge_mode[MESS04,77]|1|NOT_RUN|NOT_RUN|NOT_RUN|NOT_RUN|NOT_RUN|False|

|후보|LB_pair = min(양쪽 Exact LB)|보존한 Global LB|ΔLB|병렬 Wall(s)|Native 합계(s)|Work 합계|
|---|---:|---:|---:|---:|---:|---:|
|C01|0.565357797241|0.568711610405|0.000000000000|488.595624700014|715.506999969482|1005.885291605185|
|C02|0.566582504650|0.568711610405|0.000000000000|260.050726299989|469.153000116348|912.420389247404|
|C03|NOT_RUN|0.568711610405|0.000000000000|NOT_RUN|NOT_RUN|NOT_RUN|

C01의 병렬 Wall은 최초 480초 pair의 관측값이고 Native 합계/Work 합계는 최종 proof를 제공한 새 z=0과 재사용 z=1의 합계다. 최초 실패 비용 480.078초를 포함한 모든 소비는 전체 Runtime과 RUNTIME_WORK_BENCHMARK에 들어 있다. C02의 성능 열은 실제 동시 실행의 동일 pair다. C03은 추가 pair를 실행하면 총7회가 되어 호출 예산을 넘으므로 NOT_RUN_CALL_BUDGET다.

실측 후보 중 가장 강한 pair는 **C02 node_activity[MESS01,STA12,67]**, Exact pair LB 0.5665825046503802이다. 그러나 inherited Global LB보다 낮아 최종 개선과 Material Gate를 통과한 후보는 없다.


## 영역·과학적 동치성과 인증

PR187 exact HEAD `e67ecfa827e4262c2f2df17c226d6442656af18b` 및 원본 C3A hash를 검증했다. 원본 582,808행/306,040열에 기존 B2 651행만 이어 사용했다. 원본 min rho_max 목적 계수·ObjCon·변수축·목적 hash `0e2ee6d3d0a1ff628b24c04f453eccf08583b22dbe2dd2d23571caa5afa38335`를 보존했다. 각 Child는 선택 binary bounds 한 개만 0/0 또는 1/1로 고정했고 나머지 binary를 LP에서 C로 완화했다. route_flow 207,736개는 원래 continuous를 유지했다. 원래 feasible integer 영역의 두 부분 합집합을 증명했으며, Child 하한 하나나 Native 목적값을 전체 Global LB로 승격하지 않았다.

저장 ROOT의 equality repair Exact LB=0.5667436728775703, 인증 손실=0.0019702173804204, 옛 1e-4 품질 Gate=False를 그대로 보존했다. 사용자의 재개 지시로 손실 크기는 진단으로만 사용하고, 독립 exact proof PASS를 실행 Gate로 삼았다. 기존 DUAL_CERTIFICATION_BLOCKED 표기는 당시 상태이며 최종 실제 실험 판정은 이 문서와 FINAL_DECISION이다.

선택된/진단용 exact proof 4개를 Worker별 CSR 독립 checker와 Controller 사후 checker가 재검증했다. Native 미완료 Child의 diagnostic certificate는 Global pair에 채택하지 않는다. Producer는 CSC 열, checker는 CSR 행을 exact integer dyadic으로 계산하며 모든 306,040개 finite-bound support를 대조한다. 부호가 잘못된 raw Pi를 거부하고 별도 sign-cone/equality multiplier를 저장했다. 원시 X/Pi/RC/slack과 repair 전후 증거를 보존했다. 최종 portable verify_saved도 solve 없이 이 증거를 검사한다.

Raw fractional 해의 strict C3A/복원 FULL replay 결과는 FRACTIONAL_SOLUTION_COMPARISON에 그대로 기록한다. FAIL 해를 실제 물리 운전이나 integer incumbent로 표현하지 않으며 UB를 갱신하지 않는다. 인증된 weak-duality LB는 primal replay와 별도 수학적 증거다.

## 병렬 성능과 다른 작업

Controller Wall 합계=1093.276532초(초기 병렬+추가 z=0+Phase B, 분석·사용자 steering 사이 시간 제외). launch/checkpoint 시각으로 관측한 실험 elapsed Wall=1435.195482초는 사용자 steering·코드·분석 사이 시간을 포함한다. 최초 pair는 spawn 독립 Process 두 개, 독립 Env/Model, Threads=1, TimeLimit=480초다. 두 모델이 동시에 license를 확보한 후 공통 event로 시작했다. 최초 병렬 Wall=488.595624700014초, 추가 z=0 Worker Wall=337.80785209999885초다. worker별 model loading/build, wait, Native Runtime/Work, certificate, CPU/RSS를 별도로 보존했다. max_workers=2를 유지했고 추가 z=0은 Worker 한 개다.

동일 TimeLimit/종료상태의 완전한 순차 baseline은 없다. 최초 z=0과 추가 z=0은 matched barrier prefix를 비교하지만 elapsed ratio는 시간제한·종료상태 및 공유 host 경합의 영향이 있는 진단이다. Native Runtime 합계/Native span도 실제 겹침 지표이며 speedup이 아니다. PR187 210.226초 ROOT는 historical baseline으로만 사용한다. 다른 May12 native 작업이 관측된 공유 host이므로 인과적인 병렬 가속이나 무경합 성능을 주장하지 않는다. 메모리 대역폭 counter는 NOT_MEASURED다. CPU/RSS/page fault/I/O는 관측했으며 MemLimit/SoftMemLimit이나 RAM 기반 자동 종료는 추가하지 않았다.

첫 admission에서 다른 solver의 존재만으로 보류한 optimize=0 증거를 PRE_ADMISSION 파일과 첫 snapshot에 보존했다. 첫 호출 전 CPU 여유 및 독립 Threads=1 process 기준으로 admission을 보완하고 사전등록했다. 다른 작업의 프로세스·설정·증거는 중지하거나 수정하지 않았다.

## 분기 실용성과 후속 판단

9,322개 전수 변수 및 764개 primary group을 매핑했다. C01은 MESS02/77 충방전 모드, C02는 MESS01/STA12/67 outgoing node mass, C03은 MESS04/77 충방전 모드다. 전체 그룹을 고정하거나 multi-way 분할하지 않았다. 위치 through-mass는 STAY와 같지 않으며 이동 중 site activity가 모두 0일 수 있다. Label96 terminal aliases 96개는 physical slot95로 전수 검증했다.

이 scalar group ranking을 production BranchPriority나 전체 Branch-and-Cut에 통합할 근거를 확보하지 못했다. 새로운 많은 분기를 추가하지 않는다. 점수는 후보 순위이며 인증 하한이 아니다. Native 목적값 증가와 Exact certificate/global 개선을 분리했다.

Gurobi BranchPriority는 scalar fractional binary 우선순위이며 물리 그룹 전체를 정확히 분할하는 사용자 branching 기능과 같지 않다. 미해결 sibling의 낮은 하한을 버리면 안 된다. 여러 변수의 joint branch는 전체 조합 coverage 증명이 필요하며 이번에 실행하지 않았다.

[Gurobi multiprocessing 공식 지침](https://support.gurobi.com/hc/en-us/articles/360043111231-How-do-I-use-multiprocessing-in-Python-with-Gurobi)은 process마다 독립 Env를 요구한다. [BranchPriority 공식 속성](https://docs.gurobi.com/projects/optimizer/en/current/reference/attributes/variable.html#branchpriority)은 scalar variable 우선순위를 설명한다.

다음 행동은 정확히 하나: **저장된 Child의 Q·PCS 등식 stationarity와 finite-bound 손실을 함께 상쇄할 수 있는 exact multiplier repair를 optimize=0으로 한 건 검증한다.** 이번 작업에서 실행하지 않았다.

## 재현·Git

모든 신규 코드와 원시 evidence, 0/1 dual proof, 원본 source identity, 사전등록·call ledger·resource telemetry·한국어 보고서가 새 namespace에 포함된다. SHA256_MANIFEST는 자신을 제외한 증거·코드 hash를 보존한다. 원본 PR187/PR185 파일과 과학 모듈 hash는 unchanged다. 최종 commit/stacked Draft PR URL·remote equality·clean tree는 commit 자기참조를 피하여 WORK/reports/GIT_COMPLETION.json과 최종 대화에 기록한다.
