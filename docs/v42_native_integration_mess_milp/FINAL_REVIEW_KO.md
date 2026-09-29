# V42 native integration 최종 검토

구현/합성 검증과 실제 native 운용 검증을 구분한다. 모든 번호는 요청한 50개 질문과 같은 순서다.

1. 최신 local generic V42 canonical/checkpoint_planning/blocks/joint_mobility, V40A grid, V41 Fresh OpenDSS 및 PR90/79/75를 SHA로 추적했다. NATIVE_SOURCE_AUTHORITY_AUDIT 참조.

2. PR90의 3개 독립 mask·8개 complete option·GPU/rack/WAN/checkpoint 검사를 새 Gurobi AIDC adapter에 연결했다. native population 실행/승격은 아직 하지 않았다.

3. 중복 episode 0개. counterfactual 계획 start와 나중 causal 실행 start가 일치하지 않는 continuing occupancy가 현재 synthetic site capacity와 충돌한다. 321구간/26,586기여행을 source join했다.

4. NO. 물리적 conflict 해결 0개. 이미 PR79가 RUNNING 현재 remaining으로 교체하므로 stale 중복 삭제로 고칠 수 없었다. 임의 이동·축소·requeue 없이 fail closed.

5. NO. D24는 전기 평가 경계이며 job deadline이 아니다.

6. exact compute seconds와 ceil(seconds/900) gang reservation을 분리하고 prefix+tail=전체 service를 검증한다. transfer/restart는 compute가 아니다.

7. NO. tail GPU/resource ledger를 전부 유지한다. post-H 전기 안전성은 주장하지 않는다.

8. YES. continuing site 일치 검사를 유지한다. 다른 사이트로 바꾸어 자원 충돌을 숨기지 않는다.

9. YES, adapter complete option 안에서 start/site/migration이 공동 결정된다. 실제 native cohort binding은 아직 false다.

10. 구조적으로 지원한다. 그러나 source-backed start window와 native physical validation 전에는 새 조합의 운영 승격을 하지 않는다.

11. 합성 완전 option domain의 compute·gang·WAN·checkpoint·transfer/restart·tail invariants는 PASS. native joint-combination 검증은 미실행이다.

12. NO. 제출 시 runtime interface와 frozen site policy만 호출한다. 없는 runtime은 unresolved 처리하고 global MILP 호출은 0이다.

13. UNPROMOTED. provider interface는 구현했지만 production readiness=false. requested walltime을 realized runtime으로 대체하지 않는다.

14. NO. future Actual runtime decision reads=0. 과거 source hash/forensic 열람은 새 planning/policy evaluation이 아니다.

15. connection binary와 함께 P²+Q²<=S²x quadratic PCS를 가지고 있어서 MISOCP였다.

16. 최신 joint_mobility와 구형 mobility 각각 하나의 반복 PCS quadratic family. quadratic objective 없음. 생성 모델도 전수 구조 검사한다.

17. 최신 inner16와 공존하던 중복 exact PCS circle만 제거했다. 구형 circle-only 대비는 보수적인 부분집합 변환이다.

18. cos(2πf/16)P+sin(2πf/16)Q<=S cos(π/16)x_connected, f=0..15.

19. YES. 인접 face 교점 반지름이 Sx이고 convex hull이 circle 내부. x=0은 원점. 완화 x∈[0,1]에서도 circle row가 함의된다.

20. 최악 방사방향 용량 손실 1.921472%. face sweep은 하지 않았다.

21. YES, 구현한 primary MESS constructor 및 bounded generated model에서 0. native day 모델 생성은 source gate로 미실행.

22. YES, linear objective/constraints, QConstr=0, quadratic objective=0, SOS=0, general constraints=0 검사를 통과한다. 이것이 native campaign 준비 완료를 뜻하지 않는다.

23. YES. M1/M2에서 Pch/Pdis 및 Q를 이동·SOC와 공동 결정한다.

24. YES. stay connection bound와 inner polygon이 disconnected/transit P/Q=0을 강제한다.

25. YES. 0.25h·충방전효율·initial/terminal SOC를 적용한다. Actual P 보정도 전체 suffix SOC를 다시 계산한다.

26. YES. route departure의 source-backed travel kWh를 SOC에서 차감한다. bounded fixture는 0.1kWh 이동을 보존했다.

27. YES. time-expanded route/stay flow binary, 출발/연결시점은 source arc를 따른다. stationary battery로 바꾸지 않았다.

28. 합성 동일 fixture: MILP−circle-only Δrho=0.000373435308472; MILP−기존 circle+inner16=-1.41371008344e-07. native objective 차이는 미측정.

29. YES, bounded 모든 선택 P/Q의 exact circle ratio<=1을 독립 검사했다. 원 내부 증명과 CSV가 있다.

30. 미실행. OpenDSS 설치와 receipt rejection unit test는 Fresh AC PASS가 아니다. FRESH_AC_CANARY_PASS=false.

31. YES. coordinator가 A1→M1→A2→M2와 A1/A2, M1/M2 state handoff, fixed-A2 M2 no-regret를 유지한다. frozen native backend는 미완성.

32. 합성 pre-lex 모델: A1/A2 binary24, integer0, continuous1, linear47, NZ340; M1/M2 binary23, integer0, continuous49, linear377, NZ1093. 모두 Q/SOS/general0. native 수치는 null.

33. native 네 block 모두 NOT_RUN/null. 합성 OS-supervised wall: A1 0.250000s; M1 0.266000s; A2 0.250000s; M2 0.281000s. 합성 속도를 native 성능으로 대체하지 않는다.

34. native first incumbent=null. 합성 callback: A1 0.000515s; M1 0.001025s; A2 0.000514s; M2 0.000985s. root/presolve는 callback 관측치이며 별도 LP 시간으로 추정하지 않는다.

35. native gap=null. 합성 네 block 각 objective 최종 gap=0. timeout/null을 0으로 채우지 않는다.

36. 중복 PCS cone 제거, FIX constant, exact-safe complete-option prescreen, reachable route/PQ column 제거, indexed resource/flow assembly, objective-level model 재사용과 MIP start. 4h native 대비 speedup은 입증하지 않았다.

37. 합성 A1/A2 raw40→retained24, 40% 감소. native cohort 감소율은 미측정/null. 원인별 CSV 제공.

38. YES. singleton option은 상수1이고 별도 binary를 만들지 않는다.

39. 검사한 hard resource/service/checkpoint/WAN 불가능성과 동일 option 중복만 제거한다. grid benefit top-K·favorable site·campaign 결과 기반 제거 없음.

40. 합성 A2 25개/M2 72개 시작값 적용, solver Loaded user MIP start 로그로 수락 확인. native 사용=false, node 감소율 미측정.

41. MAX_LINE_LOADING: non-transformer phase-line rho 최대값 최소화. transformer/voltage는 hard constraint.

42. P2 유지. uncertainty reserve가 항상 hard feasible임을 증명하지 못했다. known admitted compute에는 slack이 없다.

43. A: migration count→shift magnitude→pre-start relocation→tie. M: movement energy→movement count→tie. rho/P2 lock 이후 수행한다.

44. NO. deterministic tie는 구현상 반복성 보조이며 과학적 목적이나 unique-solution 증명이 아니다.

45. NO. IEEE123 1/2/3ROUND, IEEE8500, May 신규 평가 모두 미실행.

46. NO. FLEX sensitivity 및 PCS face-count sweep 미실행.

47. NO. ML branch 대기/merge/retrain 없음. semantic ML OFF. provider 부재와 physical adapter 작업을 분리했다.

48. NO. native grid bottleneck 측정이 없어서 CL-MC-BD trigger=false.

49. reference/resources 및 causal start/duration authority 해결, final native backend/grid/MESS/route/provider freeze, matching kernel 재생성·active-policy gate, 600s/block 단일 native canary와 Fresh AC가 남았다.

50. PARTIAL_NATIVE_ARCHITECTURE_IMPLEMENTED_SCIENTIFIC_ACTIVATION_BLOCKED. service/tail 독립 snapshot semantics와 MILP adapter는 구현·검증(188 tests PASS). native optimizer/runtime readiness=false, PR79 unresolved, Fresh AC=false. source binding이 확보되기 전 full campaign 금지.
