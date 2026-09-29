# V42 job capability 최종 검토

세 capability, 완전 joint option, 합성 MILP 검증을 구현했다. 실제 V42 service/carry-over authority와 native backend가 미확정이므로 **production 승격·최종 temporal 비율 동결은 하지 않았다**. `TIMESHIFT_RULE_SELECTED=NONE`, `AIDC_MILP_JOINT_ACTION_READY=FALSE`다. 기존 ML·native optimizer·May 평가를 실행하거나 수정하지 않았다.

1. **기존 FLEX/FIX는?** PR75 temporal은 PENDING standby + RSP/runtime/RW gate와 복원된 terminal bounds였다. spatial/migration membership은 별도 frozen 권한이었다. 단일 FLEX는 이들의 요약 OR이지 물리 action 규칙 전체가 아니다.
2. **28.76%, 10.43%, 3.45%는?** 각각 stored gate 18,588 job-days/143,867.5 GPUh, restored temporal domain 4,767/52,192.75, 다른 작업을 고정한 standalone witness 1,611/17,273.5다. 분모는 500,223.5 Day-D GPUh다.
3. **왜 합치면 안 되는가?** eligibility, 기하학적 도메인, 추가 용량 witness이며 optimizer가 선택한 action도 아니다. R0 gate와 bounds를 47,009 published 행에서 재계산해 불일치 0을 확인했다. 기존 witness 집계는 보존·확인했고 재최적화하지 않았다.
4. **새 FLEX는?** `can_timeshift OR can_prestart_place OR can_checkpoint_migrate`. 셋 다 false일 때만 FIX다. authority 미확정 null은 FIX가 아니다.
5. **can_timeshift 조건은?** 아직 시작하지 않은 admitted 비보호 작업, causal eligibility, 최종 service window, 전체 service/resource/grid joint feasibility를 만족하는 reference와 대안 start가 모두 존재해야 한다. prototype은 강제-option MILP witness로 확인한다.
6. **can_prestart_place 조건은?** PENDING의 어느 feasible start에서 residency/pinning, GPU/rack 및 전체 hard constraints를 통과하는 initial site가 최소 2개다. timeshift gate와 독립적이다.
7. **can_checkpoint_migrate 조건은?** 명시적 checkpoint 권한, causal phase, 한 번 이하 migration, 유효 WAN/payload/restart, 목적지 whole-gang capacity와 남은 compute service가 있는 feasible option이 필요하다.
8. **FIX 처리는?** singleton option의 전체 compute/GPU/grid 부하를 상수로 넣는다. 삭제하지 않는다. 미승인 job은 별도 backlog authority가 필요하므로 admitted solver에 조용히 넣지 않는다. historical ledger에서는 해당 행을 보존했다.
9. **standby면 executable인가?** 아니다. scheduler candidate일 뿐 window·service·물리 constraints가 필요하다. Case A가 candidate이지만 executable TS=false인 예다.
10. **normal도 candidate인가?** 사전등록 T1 median 또는 T2 Q25의 TRAIN cohort support 조건을 만족하면 eligibility proxy가 될 수 있다. 최종 service authority가 없으므로 현재 실제 candidate/executable 승격은 하지 않는다. 과거 D24 결과는 normal의 본질적 비유연성을 증명하지 않는다.
11. **현재 job realized queue 사용?** NO. validation current-job queue/start/end/runtime은 rule 입력이 아니다. TRAIN에서 이미 관측된 과거 queue만 통계에 사용했다.
12. **TRAIN 구성은?** PR75의 persisted 439,534 pre-2025 completed GPU records, 260 cohorts를 재사용했다. start/end가 2025-01-01 UTC 이전임을 재검사했다. qos/partition/frozen QoS-derived workload_class/protected/GPU bucket/wall bucket/requested nodes이며 semantic class는 없다. 원 request version은 UNVERIFIED이므로 production causality 인증은 별도 blocker다.
13. **Q25 의미는?** 충분히 관측된 cohort의 경험적 queue 분포 25% 분위수를 900초 단위로 내린 지연 proxy다. SLA, user deadline 또는 보장된 허용 지연이 아니다. N≥100, Q25≥900초를 사전등록했으며 결과로 수정하지 않았다.
14. **20/30/40% 목표 조정?** NO. target share=false. 합성 fixture 비율은 실제 workload share가 아니다.
15. **각 rule job-count 비율은?** 최종 flexibility 비율은 NOT_AVAILABLE. pre-May validation 90,706 job-days에서 service/admission을 아직 통과하지 않은 eligibility proxy는 T0 39,242(43.262849%), T1 39,291(43.316870%), T2 39,242(43.262849%)다. T0 proxy도 완전 R0 executable 재현과 구별한다.
16. **각 rule GPUh 비율은?** 위 proxy의 authorized-duration ledger GPUh는 T0/T2 1,520,877(39.472203%), T1 1,526,037(39.606123%)다. 분모 3,853,033 full requested/safe-service **job-day reservation GPUh**이며 고유 job의 실제 실행량·Day-D 전력·PCC energy가 아니다. 실행 가능성이나 실측 runtime으로 해석하지 않는다.
17. **실제 executable TS share는?** NOT_AVAILABLE. 최종 service boundary, native state, original request-version binding이 없다. 값 0으로 대체하지 않았다. 합성 10건 중 4건 TS는 테스트 coverage다.
18. **prestart share는?** 새로운 실제 joint-domain share는 NOT_AVAILABLE. PR79 legacy spatial flag를 새 TS/PS/MG 도메인 결과로 승격하지 않았다. 합성은 5/10이다. native all12 prestaging은 case-study 가정이며 측정된 Kestrel residency가 아니다.
19. **migration share는?** 실제 native share NOT_AVAILABLE; 합성은 2/10. WAN 실패 Case G, GPU/rack 실패 Case H도 retained audit에 있다. 모델 payload는 측정 checkpoint bytes가 아니다.
20. **union FLEX share는?** 실제값 NOT_AVAILABLE; 합성은 FLEX 7/10, FIX 3/10. 전체 242,842 historical job-day 행의 미확정 masks는 null로 local SHA-bound ledger에 보존했다.
21. **overlap은?** 합성 TS-only 1, PS-only 2, MG-only 1, TS+PS 2, TS+MG 0, PS+MG 0, TS+PS+MG 1, FIX 3. job/GPUh 분모를 별도 CSV 열로 제공한다. 실제 overlap은 authority gate 뒤에 계산해야 한다.
22. **start/site 동시 결정?** 예. 하나의 complete-option binary가 start·initial site·migration을 함께 선택한다. joint shift+placement가 primary를 개선하는 별도 테스트도 통과했다.
23. **timeshift/site 중 사전 선택?** NO. 동일 A block 도메인에 모두 포함한다. secondary 선호순위는 feasible action을 사전 배제하는 hierarchy가 아니다.
24. **둘 다 변경 가능한가?** 예. SHIFT_PREPLACE와 SHIFT_PREPLACE_MIGRATE가 합성 도메인에 존재한다.
25. **기존 prohibition은?** 기존 frozen 파일을 수정하지 않았다. 새 synthetic provider domain에서는 invariant 검증을 거쳐 lifted했다. native lift는 service/provider binding 이후 별도 승격한다.
26. **combined invariants는?** 전체 GPU-slot service, 겹침/중복 없음, execution-phase checkpoint, 한 번 이하, source≠destination, 모든 WAN link payload/공유 용량, restart, 정확한 remaining work, whole gang/rack/site, 전체 tail completion bound를 검사한다. global constraints는 joint MILP가 결합한다.
27. **RUNNING timeshift?** NO. remaining-service 시작은 현재 event boundary로 고정되고 역사적 실행 시작을 재작성하지 않는다.
28. **RUNNING initial site 변경?** NO. site 변경은 승인된 이후 checkpoint migration으로만 표현한다.
29. **어느 checkpoint?** causal elapsed_seconds에서 1800초 위상을 복구하고 다음 900초 control boundary로 ceil한다. exact current boundary를 포함한다. phase reset/임의 modeled-start 복원/역방향 rounding은 없다. elapsed가 없을 때만 native checkpoint binding을 fail closed한다.
30. **migration 횟수는?** job execution당 최대 1회. `migrations_used=1`이면 추가 migration option을 만들지 않는다.
31. **WAN/restart 반영?** 예. 모든 path link에 payload 전체가 전달되고 compute interruption 및 1-slot restart가 있다. native payload authority는 GPU당 80e9 bytes engineering model, 새 canary는 단위시험용 축소 bytes로 명시했다. 구 PFR 5분 restart와 V42 15분 restart를 혼용하지 않는다.
32. **RADDiT label 사용?** NO. RADDiT/SEM32/Runtime/CC4 호출·embedding 사용은 없다.
33. **option 수는?** 합성 A–J에서 구성된 complete option 127개 중 hard prescreen 뒤 76개. Case F는 56→40이며 8개 action class 모두 포함한다. WAN 미완료 등 완성 전 branch skips는 별도 count이며 127과 혼합하지 않는다.
34. **prescreen exact-safe?** 선언된 finite transfer/start/provider 계약 안에서 hard infeasibility/정확한 중복만 제거한다. grid benefit, topK, 임의 dominance는 사용하지 않는다. 다른 movable job을 reference에 고정해 joint swap을 제거하지 않는 테스트를 포함했다. 일반 native scalability 증명은 아니다.
35. **full service 보존?** 합성 retained 76개 option에서 service/GPU-slot identity 위반 0이다. native 전체 population의 service feasibility PASS를 주장하지 않는다.
36. **carry-over 처리는?** H 이후 compute와 resource reservation을 끝까지 유지한다. H로 truncate하지 않는다. electrical 지원 horizon 이후 안전을 주장하지 않는다. 실제 finalized carry-over contract가 없어 final temporal freeze를 차단한다.
37. **기존 P1–P5는?** worst line rho, H4 reserve shortfall, migration 수, reference schedule deviation, deterministic tie다. 최신 generic V42는 callback objective list와 reserve/migration을 조립하므로 native 5개가 자동 보장되는 것은 아니다.
38. **MILP와 lex는 왜 별개?** MILP는 변수·constraint 표현이고 lex는 여러 feasible optimum 사이 선호다. 또한 현재 local MESS는 PCS quadratic constraint를 포함한 MISOCP다. 이를 MILP로 잘못 부르거나 security constraint를 제거하지 않았다.
39. **primary-only degeneracy는?** 예. 합성 STAY와 SHIFT_PREPLACE_MIGRATE의 rho가 모두 0.54지만 intervention은 다르다. secondary는 STAY를 선택한다. native 개선량의 증거는 아니다.
40. **새 primary는?** MAX_LINE_LOADING. transformer는 포함하지 않고 별도 hard limit이다. inherited grid source와 같은 정의다.
41. **voltage/transformer/SOC/service hard?** 기존 physical hard constraints를 유지한다. canary는 affine line/voltage/transformer, whole service/GPU/WAN을 직접 검사했다. SOC/PCS/mobility는 기존 MESS source audit만 수행했고 새 native MESS dispatch 검증은 하지 않았다.
42. **P2 필요한가?** 현재는 필요하다. known full service가 hard여도 uncertainty reserve가 전부 확보 가능하다는 증명이 없다. 기존 envelope는 uncovered uncertainty를 허용하므로 native P2를 삭제하지 않았다. optional shortfall-before-intervention test를 추가했다.
43. **secondary 이유는?** 동일한 electrical optimum에서 불필요한 migration/shift/placement/MESS 이동을 막기 위해서다. 임의 결과기반 weight 없이 lex tuple을 사용한다. A block의 MESS movement는 고정 상수다.
44. **P5 scientific objective?** 아니다. 최종 per-job deterministic tie는 재현성 장치다. 논문 목적은 worst network loading과 필요한 service/최소 intervention으로 요약한다.
45. **outer structure 변경?** NO. 기존 A1→M1→A2→M2는 그대로다. 이번 모듈은 native pipeline에 bind하지 않았다.
46. **A block joint?** 합성 MILP에서는 예. start/site/optional migration이 동일 binary에 결합된다. native A1/A2 promotion은 아직 false다.
47. **full IEEE123 실행?** NO. unit·synthetic·작은 MILP만 실행했다. 1ROUND/2ROUND/3ROUND도 없다.
48. **IEEE8500 실행?** NO.
49. **Runtime/CC4 변경?** NO. 해당 branch를 merge/import/수정하지 않았으며 ML을 학습·예측하지 않았다.
50. **다음 1ROUND blocker는?** finalized continuous service/carry-over provider, PR79 pending-reservation/native-capacity 충돌 해결, original request-version/causal authority, 유일하게 freeze된 native grid/backend 및 A/M objective binding, H4 shortfall hard 가능성 판정, unknown temporal/migration authority, 전체-domain scalability/independent physical·fresh-AC validation이다. 이 작업은 어느 것도 결과를 좋게 만들기 위해 임의 완화하지 않았다.

범위: 2024-03-15–2025-04-30의 412 snapshot 날짜를 inventory했다. job-day ledger는 396 nonempty 날짜(첫 행 2024-03-22), 242,842행, 고유 source jobs 106,031개다. TRAIN cutoff 이후 issue만 규칙 비교에 사용하므로 validation은 운영일 2025-01-02부터다. 1월 1일 운영일의 D−1 issue는 cutoff 이전이어서 적용에서 제외되며 행은 inventory에 유지된다. April은 exposed development/validation 기간이고 untouched test 주장은 없다. May는 기존 PR75 published table 재현 외 새로운 평가·tuning에 사용하지 않았다.
