# 최종 두 목적 계약 검토

최종 scientific objective는 P1 MAX_LINE_LOADING → P2 MIN_INTERVENTION 두 그룹입니다. Corrected full-May A1 complete=True, independent physical PASS=True. Reserve-P2 후속 작업은 중단·로컬 historical checkpoint 보존했으며 이 branch에 포함하지 않았습니다.

전체 모델: 7,449,002 columns / 9,126,514 rows / 53,621,850 nonzeros. 원본 constraint/domain fingerprint를 유지했습니다. PR103 모든 기존 tracked 파일 raw byte preservation PASS. 테스트 총 452개 PASS. Single-worker peak RSS=22800445440 bytes.

### 1. 최종 scientific objective는 몇 개인가?

2개: MAX_LINE_LOADING → MIN_INTERVENTION.

### 2. P1은 무엇인가?

기존 정규화 non-transformer phase-line 최대 부하 rho를 최소화합니다. 전압·변압기 제한은 hard constraint입니다.

### 3. P2는 무엇인가?

P1 lock 안에서 불필요한 운영 개입을 최소화합니다.

### 4. reserve shortfall은 objective인가?

아닙니다. soft reliability/불확실성 coverage 보고 지표입니다.

### 5. CC4 deviation은 objective인가?

아닙니다. frozen CC4 service 신호의 보고 지표입니다.

### 6. migration은 어디에 속하는가?

P2 AIDC의 첫 내부 component입니다.

### 7. shift는 어디에 속하는가?

P2 AIDC의 두 번째 내부 component인 absolute shift magnitude입니다.

### 8. pre-start placement는 어디에 속하는가?

P2 AIDC의 세 번째 내부 component입니다.

### 9. MESS movement는 어디에 속하는가?

P2 MESS 내부 tuple: movement energy → movement count. MESS campaign은 실행하지 않았습니다.

### 10. arbitrary weighted sum을 사용했는가?

사용하지 않았습니다. 순차 subpass와 기존 tolerance lock을 사용합니다.

### 11. P2 internal tuple은 무엇인가?

AIDC: migration → shift magnitude → prestart relocation. 이들은 별도 scientific P3/P4/P5가 아닙니다.

### 12. deterministic tie는 scientific objective인가?

아닙니다. 고정 trajectory multiset에 대한 canonical UID reconstruction만 사용합니다.

### 13. PR103 P1 결과는 유지됐는가?

유지됐습니다. 전체 replay P1 UB=0.6715924043100266, LB=0.6715924043100266이고 원본 물리 모델 fingerprint/count가 동일합니다.

### 14. PR103 reserve-P2 result는 final P2인가?

아닙니다.

### 15. 왜 아닌가?

사용자의 최종 objective contract가 reserve shortfall 대신 MIN_INTERVENTION을 P2로 정했기 때문입니다.

### 16. reserve는 현재 어떻게 사용되는가?

원본 변수·headroom·target 제약을 유지하고 결과/limitation으로 보고합니다. zero shortfall로 harden하지 않았습니다.

### 17. CC4는 현재 어떻게 사용되는가?

work conservation/carryout/depletion/causal Q10/Q90 timing envelope와 전력 interface를 그대로 유지합니다.

### 18. P1 lock tolerance는?

P1 epsilon=1e-7; exact authority rho=0.6715924043100266, lock RHS=0.6715925043100266.

### 19. P2가 P1을 악화시킬 수 있는가?

기존 허용 tolerance 내에서만 가능합니다. P1 lock을 완화하지 않았습니다.

### 20. equal-P1에서 STAY가 선택되는가?

adversarial equal-P1 fixture에서 STAY가 migration보다 우선했습니다.

### 21. Runtime provider가 바뀌었는가?

바뀌지 않았습니다. frozen Q50 inference와 gamma authority를 보존합니다.

### 22. service duration이 바뀌었는가?

바뀌지 않았습니다.

### 23. D24 deadline을 만들었는가?

만들지 않았습니다.

### 24. carryover service는 유지되는가?

full required service와 representation tail/carryover를 유지하고 독립 검증했습니다.

### 25. unknown future leakage가 있는가?

추가하지 않았습니다. 기존 causal input/행동 authority tests가 통과했습니다.

### 26. Actual full reoptimization을 추가했는가?

추가하지 않았습니다.

### 27. site/power authority가 바뀌었는가?

바뀌지 않았습니다. episode site, rack/gang, GPU-power/PUE/PF/PCC source를 보존합니다.

### 28. Planning/Actual response가 바뀌었는가?

바뀌지 않았습니다.

### 29. outer A1→M1→A2→M2가 바뀌었는가?

바뀌지 않았습니다. 이번 task는 corrected A1 뒤에서 멈춥니다.

### 30. D-W를 사용했는가?

사용하지 않았습니다.

### 31. candidate feasible set을 줄였는가?

줄이지 않았습니다. 모든 1,499 jobs, 117 scientific classes, F2-CRA full domains를 유지합니다.

### 32. can_timeshift는 유지되는가?

유지됩니다.

### 33. can_prestart_place는 유지되는가?

유지됩니다.

### 34. can_checkpoint_migrate는 유지되는가?

유지됩니다.

### 35. max migration/job은?

execution당 최대 1회입니다.

### 36. IEEE8500을 실행했는가?

실행하지 않았습니다.

### 37. P1 solve time은?

599.4546597000153초 (P1 optimize-only).

### 38. P1 final gap은?

P1 solve relative gap=0.0; 최종 P1 원문제 global gap fraction=1.488998154470192e-07.

### 39. P2 intervention solve time은?

P2 내부 subpass optimize 합계=504.4207849999948초; diagnostic은 별도 기록입니다.

### 40. P2 component별 incumbent/bound는?

migration_count: UB=0.0, LB=0.0, status=2, gap=None, integer exact=True; shift_magnitude: UB=387.0, LB=386.0, status=2, gap=0.002583979328165375, integer exact=False; prestart_relocation: UB=221.0, LB=220.0, status=2, gap=0.004524886877828055, integer exact=False

### 41. reserve shortfall 결과값은?

선택된 upstream 조건에서 최소 총 shortfall=76745.90404808165; raw 미최적화 auxiliary 합계=89833.0. Component split은 비유일한 reporting label이며 과학 목적이 아닙니다.

### 42. CC4 reporting metric은?

미최적화 CC4 deviation auxiliary=2.4843577673160966; 실제 고정 timing에서 직접 계산한 deviation={'nominal': 0.9153264035280837, 'reserve': 1.4239426365914867, 'total': 2.3392690401195706}. 별도 목적 pass가 없습니다.

### 43. physical validation은 PASS인가?

True. Runtime/known GPU/CC4/service/WAN/native grid 독립 certificate를 확인했습니다. Fresh AC 결과는 아닙니다.

### 44. two-objective A1은 complete인가?

True. 전체 optimize wall=1103.8754447000101초.

### 45. Threads는?

1 thread/solve입니다. 동시 case campaign은 실행하지 않았습니다.

### 46. GPU는?

사용하지 않았습니다.

### 47. next M1 gate는 만족됐는가?

corrected A1 acceptance gate는 만족했습니다. M1의 자체 native preflight/handoff 검증은 M1 시작 시 별도로 필요하며 이번 task에서는 실행하지 않았습니다.

### 48. 다음 pipeline step은?

accepted corrected A1 이후 M1 → A2 → M2 → Fresh AC gate입니다. 이번에는 M1 이전에서 멈춥니다.

### 49. 기존 six-level objective를 다시 사용한 곳이 남아 있는가?

원본 historical source/test/evidence에는 남아 있습니다. 최종 실행 경로 v42_two.production 및 MESS adapter에서는 reserve/CC4/rank를 scientific objective로 사용하지 않습니다.

### 50. numbered Problems 1,2,3,4,5,6,8,10 중 regression이 있는가?

없습니다. 번호별 원본 byte seal, inherited 440 tests, 새 12 tests, 전체 모델/domain 및 physical regression 증거를 기록했습니다.
