FAST_ACTIVE_DOMAIN_TRACTABILITY_FAIL

SPEED_GATE=SPEED_GATE_FAIL. 전체 native LP pricing 및 integer-domain closure 미증명으로 전체 재실행을 막았습니다.

1. 완전 STAY와 큰 기존 migration active 그래프가 native 변수/행과 barrier fill-in을 늘렸습니다.
2. May19 baseline: 4,417,827 rows / 4,316,192 cols / 49,651,657 nnz.
3. Factor NZ 약1.562e9, 추정 메모리15.0 GB. 원본 log의 반올림 값입니다.
4. 아니오. root 완료 전에 TIME_LIMIT; native Runtime3606.646초(요청3600초 종료 overshoot6.646초).
5. INFEASIBLE이 아닙니다. COMPLETE_STAY_ALL_ACTIVE_ROOT_TIMEOUT입니다.
6. 전체 hard-valid V2 과학적 domain, class cardinality, frozen 물리 계수를 보존했습니다.
7. 유효 anchor/기존 STAY/rescue/검증 incumbent + 같은 site ±2 + class당 순위 추가8개; migration은 작은 유효 seed입니다.
8. 생략 STAY는 site별 start interval과 immutable 물리/계수 provider로 저장하고 native 변수0개를 생성합니다.
9. 아니오. 기준 시각은 초기 순위·warm support·목적함수에만 사용합니다.
10. 아니오. 낮은 grid 순위도 D_POOL에 남습니다.
11. 필수 지원을 먼저 포함하고 frozen signed thermal 계수의 GPU occupancy 순위로 추가 후보를 결정합니다.
12. 유효한 실제 Farkas ray가 있으면 원본 coupling 계수로 정확한 유리수 후보 점수를 계산하는 검증기를 구현했습니다. 이번 May19는 FarkasDual 회수 불가로 certifiable feasibility activation을 수행하지 못했습니다. 완전 native 증명 없이는 과학적 infeasible을 선언하지 않습니다.
13. 실제 LP Pi, 원본 GPU/Runtime/WAN/ACTIVE 행과 class cardinality potential을 사용합니다. native primitive/block dual 검증 API를 별도로 두었습니다.
14. 아니오. LP pricing closure와 integer-domain closure는 독립된 상태입니다.
15. FULL_DOMAIN_OPTIMALITY_UNRESOLVED. 실제 전체 native pricing producer와 branch-price/정수 closure 증명이 미완성입니다.
16. 새 May17 초기 크기: 692,247 rows / 19,221 cols / 12,634,730 nnz.
17. 수정된 May17 제한 LP native1.599000초; 보존된 첫 시도1.382000초를 합한 실제 native2.981000초; build는 BUILD_PROFILE.csv에 분리합니다.
18. May17 제한 LP feasible=True; 이전 검증된 integer schedule을 현재 native 행렬에 새로 replay한 결과 PASS=True.
19. 새 May19 초기 크기: 712,791 rows / 83,751 cols / 13,751,140 nnz.
20. May19 native 호출84.455초에서 제한 모델 INFEASIBLE status3. 수치 trouble 뒤 FarkasDual을 회수하지 못했습니다. feasible root 완료 시간은 미측정이며 과학적 전체-domain infeasible 증명도 없습니다.
21. 전체 A1 4-pass 실행 없음. LP closure gate가 MILP를 막았습니다.
22. 완료된 feasible root나 전체 A1의 speedup은 미측정입니다. Raw cols98.06%, rows83.87%, nnz72.30% 감소는 실제 초기 행렬 비교입니다.
23. 한 native 호출 내부 barrier4회에서 관측된 최대 factor NZ25.46M, 추정메모리0.5GB. Baseline 대비 factor NZ98.37%, 메모리96.67% 감소. 최대 ordering0.81초; 첫 factor만 사용하지 않습니다.
24. 아니오. 속도 때문에 영구 삭제한 유효 후보0개.
25. 아니오. 물리·Runtime·CC4·GPU·WAN·grid 한계를 바꾸지 않았습니다.
26. 아니오. 원본 scientific tolerances를 보존했습니다.
27. 아니오. solver parameter sweep0회. InfUnbdInfo=1은 정보 회수용입니다.
28. May12 native optimize 미실행. 이전 parent가 시작한 build 전 child를 중단했고 새 production도 proof gate로 중단했습니다.
29. May12 root 결과 없음: NOT_RUN_PROOF_GATE.
30. May10 shift 단계 미도달. native optimize0회.
31. May10 shift 결과 없음. exact fresh lock/rebuild/zero projection/정수 인증 구현은 테스트로 보존했습니다.
32. 새 4단계 active integer-solved 날짜0개. 두 날짜는 제한 LP diagnostic만 수행했습니다.
33. full-domain closure proven 날짜0개.
34. production accepted 날짜0개. Planning/Actual/Fresh0회.
35. 최종 정확한 HEAD는 publication 시 외부 FINAL_PUBLICATION_RECEIPT.json과 최종 응답으로 제공합니다(자기참조 hash 없음).
36. Draft PR URL은 publication receipt와 최종 응답으로 제공합니다.

현재 행렬에서 replay한 May17 incumbent 지원: rho=0.6653690555462561, migration=0.0, shift=105102.0. 이는 새 최적값/새 bound/새 lex lock이 아닙니다.

LP 물리 경로 점수만으로 native mixed-flow의 fractional finish 방향 전체를 증명할 수 없습니다. 유효 block-dual 검증기는 구현했지만 실제 모든 생략 primitive 방향을 공급·검증하는 producer와 budgeted block oracle은 미완성입니다. 이를 완료해야 production MILP를 실행할 수 있습니다.

May19의 원본 solver 로그·상태·first-match telemetry는 그대로 보존했습니다. INTERNAL_BARRIER_ATTEMPTS.json이 내부4회 재시도와 서로 다른 elapsed clock을 보충합니다. Gurobi는 barrier에서 infeasibility가 결정되는 경우 InfUnbdInfo=1이어도 증명 정보가 없을 수 있다고 문서화합니다. [Gurobi InfUnbdInfo](https://docs.gurobi.com/projects/optimizer/en/current/reference/parameters.html#parameter:InfUnbdInfo). 이번 정확한 원인은 로그와 attribute 오류에 기반한 추론이며, 유효한 Farkas 증명은 확보하지 못했습니다.

Farkas/전체 native LP closure가 없고 SPEED_GATE_FAIL이므로 추가300/3600초 실행이나 solver 변경 없이 중단했습니다. May12·May10은 static census만 수행했습니다. 첫 NumPy bool false rejection은 원본 source/permit/gates/결과와 별도 진단을 보존했고, 수정된 canary 예산에서 이미 쓴1.382초를 차감했습니다.

May17에는 현재 native 행렬에 독립 replay된 유효한 정수 feasible witness가 있습니다. 따라서 ACTIVE_DOMAIN_SOLUTION_VALID=True이며, 새 solver가 네 lex 목적을 해결했다는 뜻은 아닙니다. ACTIVE_INTEGER_SOLVED=False 및 full closure/acceptance=False를 유지합니다.

검증: 전체 suite 1,732 PASS와 수정 후 targeted 60 PASS의 고유 합집합은 1,753 PASS입니다. 실행 뒤 추가한 postsolve 모듈은 로그의 전체 barrier attempt를 검토하는 용도이며 compile·수동 assertion·두 번 실행의 byte idempotence를 확인했습니다. Canary 실행 source는 0f28a361374bb77fc04f3c239004f231b6147a40으로 동결·별도 보존했고, 최종 publication HEAD와 구별합니다.
