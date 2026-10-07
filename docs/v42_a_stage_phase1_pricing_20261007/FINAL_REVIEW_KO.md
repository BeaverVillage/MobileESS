PHASE1_TRACTABILITY_FAIL

SPEED_GATE_V2_FAIL. Full-domain scientific acceptance=False.

실제 실행 source HEAD: `3c7fe3a097dc733c5514078894f5ee09cae20004`. Source archive SHA256: `42d8b07696d11c32b368081a6495e6af69003b06c0070bf870ef78b8a2c598ac`.

사전 검증128 tests PASS,150 native classes exact incidence/reassembly PASS. 실제 canary native calls=71; incomplete pricing/zero/full infeasibility를 성공으로 해석하지 않습니다.

| architecture | rows | columns | nnz | max factor | estimated GB | native s |
|---|---:|---:|---:|---:|---:|---:|
| A_historical_restricted_PR165_S_A | 3028171 | 2684757 | 18249864 | 194200000.0 | 2.0 | 600.8179998397827 |
| B_V2_COMPLETE_STAY_ALL_ACTIVE | 4417827 | 4316192 | 49651657 | 1562000000.0 | 15.0 | 3606.6459999084473 |
| C_PHASE1_FAST_ACTIVE_ORIGINAL | 712791 | 83751 | 13751140 | 16090000.0 | 0.4 | 279.13099908828735 |
| C_PHASE1_AUXILIARY_ACTUALLY_SOLVED | 712791 | 779175 | 14446564 | 16090000.0 | 0.4 | 279.13099908828735 |

A는 과거 PR165 S_A zero-objective restricted feasibility LP입니다. B는 COMPLETE-STAY rho MILP root, C는 새로운 auxiliary Phase-I LP입니다. 완료된 root speedup으로 비교하지 않습니다. Complete provider qualification과 실제 pricing closure는 분리합니다.

1. **Exact base HEAD?** 9336d8f7fba243df86e8dff0276e70942855039c

2. **PR168 실패 이유?** 제한 active LP가84.455초에 INFEASIBLE(status3)을 반환했고 usable FarkasDual을 회수하지 못해 feasibility activation과 전체 LP pricing closure가 막혔습니다.

3. **속도 감소 자체는 성공했는가?** 행/열/nnz 및 최대 factor25.46M/0.5GB로 감소했습니다. 완료된 feasible root의 speedup은 측정되지 않았습니다.

4. **FarkasDual 문제?** 수치 trouble 및 내부 barrier 재시도 후 해당 attribute가 unavailable했습니다. solver 설정이나 물리 infeasibility의 원인을 증명한 것은 아닙니다.

5. **Phase-I가 Farkas를 피하는 방식?** 항상 feasible한 별도 elastic LP의 Pi와 실제 RC를 저장하고, complete native local block의 feasibility 가격을 계산합니다. FarkasDual을 읽지 않습니다.

6. **정확한 formulation?** 등식 a·x+u−v=b, ≤행 a·x−s≤b, ≥행 a·x+s≥b; u,v,s≥0. original scientific columns/rows/bounds를 복사하고 auxiliary columns만 추가합니다.

7. **artificial 대상 행?** 692160개 global/nonlocal 행. GPU, Runtime, WAN, ACTIVE 결합과 grid/CC4 전역 행입니다. Hard local20631행에는 추가하지 않습니다.

8. **hard physical constraints?** class exact-cardinality, release/complete/compatibility, native local flow/state/checkpoint/transfer/WAN/service/finish 및 original variable bounds를 유지합니다. GPU/Runtime/global capacity는 Phase-I copy에서만 elastic이며 original 모델에서는 hard입니다.

9. **Phi objective?** Σw_i artificial_i. 최초 original row scale의 다음2의 거듭제곱 역수인 양의 dyadic rational을 사전 고정했습니다. 695424개 actual weight의 NPZ byte receipt를 저장했고 activation 후에도 retune하지 않습니다.

10. **Phi>0 의미?** 제한 active auxiliary LP의 잔여 violation입니다. Full-domain physical infeasibility나 production feasibility를 뜻하지 않습니다. 엄밀한 full lower bound>0과 complete pricing closure 없이는 full LP infeasible을 선언하지 않습니다.

11. **초기 May19 Phi?** native ObjVal=0.006626776621085752; raw replay Phi=488969809451242447/73786976294838206464; native status=2.0. 원 solver 값은 진단이며 원본 물리 feasibility가 아닙니다.

12. **Phase-I iterations?** 1 native master solve; activation rounds=0

13. **STAY activation?** 0

14. **migration activation?** 0

15. **complete STAY pool 가격 계산?** 197537 physical STAY/161644 initial inactive STAY의 lossless provider와 native coupling을 검증했습니다. 실제 complete canary pricing 수행 여부는 Phase-I/closure receipt에 따르며 static producer PASS는 가격 완료가 아닙니다. 실제 complete-block pricing은 77/150 class에서 완료했습니다. 이 범위의 physical STAY=104,684, migration=35,375,982, compact blocks=605,756이며 음의 block direction=70개를 발견했습니다. 남은 class를 가격 계산하지 않았으므로 complete STAY/migration closure=False이며 전체 omitted minimum rc와 physical negative candidate count는 미측정입니다. 저장된 모든 완료 certificate의 bound를 원본 frozen cache와 실제 master Pi에서 독립 재계산했습니다.

16. **complete migration lossless 가격?** 97724022 physical paths/1710374 compact blocks의 전체 graph union과 original native hard LP를 만들었습니다. 모든 mixed fractional finish 방향을 포함하고 N개의 동일 continuous lane 합 투영을 증명/검증했습니다. Native canary complete pricing closure는 False입니다. 실제 누락 class=73; full pricing PASS=False.

17. **마지막 omitted minimum rc?** complete pricing result가 없으면 미측정입니다. 각 block은 exact original-binary64 rational lower bound와 native feasible point 가격의 interval을 반환하며, gap 미인증을 exact attained minimum으로 표시하지 않습니다. 완료 subset block lower bound minimum=-22667359117774297777960461/75557863725914323419136; full-domain minimum과 다릅니다.

18. **Phi certified zero?** False; original rows/bounds replay와1e−8 Phi zero tolerance를 모두 요구합니다.

19. **full LP infeasibility proven?** False

20. **후보 영구 삭제?** NO. D_ACTIVE⊂D_PHYSICAL, D_POOL=D_PHYSICAL\D_ACTIVE. Engineering threshold는 실행/활성화를 멈추며 물리 pool을 삭제하지 않습니다.

21. **reference_start hard cutoff?** NO. 순위/warm support/objective 정보만 유지합니다.

22. **final active model size?** {'rows': 712791, 'cols': 83751, 'nnz': 13751140}; initial actually-solved Phase-I=712791 rows/779175 columns/14446564 nnz, 별도 artificial695424개 포함.

23. **maximum factor nnz?** 16090000.0; 모든 내부 barrier attempt를 읽은 maximum, log rounded value.

24. **maximum factor memory?** 0.4 GB estimated from log; process peak RSS와 구분합니다.

25. **Phase-I runtime?** 268.6229999065399 native seconds

26. **pricing runtime?** 321.0134300000209 wall seconds; partial pricing도 charge하며 pricing-native overlap을 보수적으로 중복 계산합니다. 보수적으로 charge한 native+pricing=600.144429s, 600s soft-stop overshoot=0.144429s.

27. **artificial-free original P1 feasible?** False; original P1 solve 상태는 ORIGINAL_LP_RESULT.json에 저장했습니다.

28. **P1 pricing closed?** False

29. **P1 root runtime?** 0 seconds; 미실행이면0은 완료 시간이 아닙니다.

30. **complete-active 대비 speedup?** 성공적으로 완료된 feasible root 간 speedup은 미측정. 별도 PERFORMANCE_COMPARISON.csv에서 timeout/budget과 objective의 차이를 명시하고 실제 original/auxiliary 크기를 함께 비교합니다.

31. **tolerance 완화?** NO. solver FeasibilityTol/OptimalityTol1e−6와 frozen Method2/Threads1 정책을 유지했습니다. Raw original replay1e−6; pricing/zero epsilon1e−8; no sweep.

32. **physics 변경?** NO. PR168 scientific source/evidence 변경0, original initial matrix/all four objectives 재조립 동일. Native builders와 original binary64 coupling을 재사용했습니다.

33. **May17 regression?** 이번 task native 미실행. SPEED_GATE_V2_PASS 전 금지; 과거 independent replay-valid witness 및 source/membership evidence는 그대로 보존합니다.

34. **May12 실행?** NO. Speed gate 이후에만 허용됩니다.

35. **May10 실행?** NO. 기존 lex rebuild/zero migration projection/direct shift/integer certificate/strengthening 소스와 테스트를 보존했습니다.

36. **증명된 closure?** {"ACTIVE_DOMAIN_FEASIBLE": false, "FULL_LP_FEASIBILITY_CLOSED": false, "FULL_LP_DOMAIN_INFEASIBLE": false, "LP_PRICING_CLOSED": false, "INTEGER_DOMAIN_CLOSURE_PROVEN": false}

37. **production accepted dates?** 없음. Planning/Actual/Fresh OpenDSS0; 다른27일0; integer closure=False.

38. **primary classification?** PHASE1_TRACTABILITY_FAIL / SPEED_GATE_V2_FAIL; error=PHASE1_PREREGISTERED_CUMULATIVE_BUDGET

39. **final commit SHA?** 실제 native executed HEAD=3c7fe3a097dc733c5514078894f5ee09cae20004. 최종 publication HEAD/clean/remote match는 [외부 FINAL_PUBLICATION_RECEIPT.json](C:\Users\kjw39\Documents\Codex\2026-10-07\v42-a-stage-phase1-static\FINAL_PUBLICATION_RECEIPT.json)을 권위로 사용합니다. 보고서가 자신의 최종 commit hash를 포함하는 순환 참조를 만들지 않습니다.

40. **Draft PR URL?** PENDING_PUBLICATION

실행 원본: MAY19/NATIVE_CALLS.json, NATIVE_RUN_SOURCES.csv, ROUND_000/NATIVE_RESULT.json, POSTSOLVE_REVIEW.json. 모델/원본 NPZ/가중치/cache/source ZIP은 external SHA receipt로 연결합니다.
첫 receipt 저장 경로가 Windows 한계를 넘은 오류는 ATTEMPT_001에 보존했습니다. C1 continuation은 이미 최적인 master/첫 block raw를 재사용하고 prior native/pricing ledger를 이어받았습니다. Native budget/weights/policy/physics를 reset하거나 추가하지 않았습니다.
새 reporter는 source freeze 후의 관찰/문서 작업이며 native solver policy, weights, source, status, raw arrays를 수정하지 않습니다.

실제 complete-block pricing은 77/150 class에서 완료했습니다. 이 범위의 physical STAY=104,684, migration=35,375,982, compact blocks=605,756이며 음의 block direction=70개를 발견했습니다. 남은 class를 가격 계산하지 않았으므로 complete STAY/migration closure=False이며 전체 omitted minimum rc와 physical negative candidate count는 미측정입니다. 저장된 모든 완료 certificate의 bound를 원본 frozen cache와 실제 master Pi에서 독립 재계산했습니다.

Native 실행 source는 두 version입니다: master와 첫 block=6fde0f1806b1e5d425de50d43bb1202b0e2baae5 (archive SHA256 9fe57c729f0e8f3a0e9cf0290d247f0d1483c68ee23edc18b393cf81403cdce2), 나머지69 block solves=3c7fe3a097dc733c5514078894f5ee09cae20004 (archive SHA256 42d8b07696d11c32b368081a6495e6af69003b06c0070bf870ef78b8a2c598ac). 모든71 raw primal/RC replay PASS. Artificial 제거 시 original 최대 행 violation0.00116485794 >1e-6로 물리 feasibility는 FAIL입니다.
