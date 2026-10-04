1. 요청 branch `codex/v42-m1-dw-dominance-threshold-bound-v1`. Draft PR과 최종 remote SHA는 게시 후 PR 본문에 기록한다. Semantic 361 PASS, full pytest 1808 PASS. Git clean은 게시 후 확인한다.
2. PR142 exact head `29a115748e7c1f3a983019fe005e91710defa0d2` 및 remote Draft identity PASS.
3. checkpoint retained trajectory 1,158개 전부 SHA, 원본 local rows, raw integrality, physical semantics, coupling projection 감사 PASS. Old pricing replay 0.
4. `conv(X_m^I) ⊆ P_m^arc`, 원본 축 복원 및 full-scale projected inclusion PASS. 따라서 `z_arc_LP ≤ z_DW_root`. 이는 모든 미발견 legal trajectory에도 성립하는 affine inclusion이다.
5. route split, charge mode, SOC/travel energy, PCS, grid coupling, terminal SOC, multi-MESS 등 7개 bounded fixture의 모든 integer face/continuous vertices를 Fraction으로 전수 열거했다. `z_arc ≤ z_DW ≤ z_integer` 및 integer master 동등성 PASS. Native optimize 0.
6. **요청 scalar floor 채택은 중단했다.** `0.5687116103498322`의 저장 출처는 interrupted integer MIP의 terminal global BestBd다. Exact original arc-LP dual certificate는 없고, root message는 반올림값이며 LP point에는 primal values만 있다. 기존 integer certificate를 부정한 것이 아니라 DW root로의 bound 전이를 인증하지 못한 것이다. LP objective와의 수치적 근접성은 수학적 lower-bound 증명이 아니다.
7. optimize 없이 유지한 certified PR142 interval: `[0.5215744487783405, 0.5836817975103938]`. 조건부 arithmetic `[0.5687116103498322, 0.5836817975103938]`는 별도로 기록했으며 certified interval로 표시하지 않았다.
8. PR142 Certification pricing diagnosis: exact negative RC가 약한 corrected LB를 설명한다. 최종 기존 receipt 네 개 모두 OPTIMAL, native BestBd=incumbent objective, native gap 0.
9. 최종 PR142 MESS proof gaps: MESS01: 6.94e-18 / MESS02: 3.47e-18 / MESS03: 0 / MESS04: 0. 수치 RC 재계산의 1e-8 이내 음수 roundoff는 diagnostic gap에서 0으로 표시했다.
10. Pricing root objective는 native log가 cutoff인 경우 NULL이다. Root relaxation의 native phase duration은 cutoff 로그까지 별도 기재했다. 정확한 root 완료 wall timestamp는 NULL이다. First incumbent exact timestamp는 저장되지 않아 NULL. Terminal bounds/RC/native gap/node count는 CSV에 있다. 관측되지 않은 root gap을 만들어 쓰지 않았다.
11. PR142 receipt 기반 `PRICING_BOUND_CLASSIFICATION=TRUE_NEGATIVE_RC_DOMINANT`. Summed actual negative RC magnitude=0.079229063850; summed proof weakness room=1.04083408559e-17. Causal uniqueness를 주장하지 않는다.
12. 새 Discovery rounds 0. Lower-floor gate에서 중단했다.
13. 새 validated columns 0; retained 1,158.
14. 새 columns/min N/A. 실행하지 않은 실험을 0 throughput 측정으로 보고하지 않았다. PR142 reference 6.910010.
15. 새 RMP upper trajectory 없음; 기존 smallest audited upper `0.5836817975103938` 유지.
16. 기존 certified point의 `D_U=0.009970187161`, `D_L=0.052137161571`. Floor 미채택 기준이다. 새 trajectory 없음.
17. Final Certification NOT_RUN_PREOPT_GATE_STOP. 새로운 900-s budget 사용 0 s; 자동 연장 없음.
18. 유지한 best pricing-corrected LB `0.5215744487783405`. 기존 마지막 PR142 corrected LB `0.5044526936603798`는 별도 기록.
19. `max(arc,corr)` theorem은 두 lower bound가 같은 DW optimum을 대상으로 유효하다는 조건 아래만 성립한다. Arc premise 미인증으로 적용하지 않았다. Aggregated lower floor NULL.
20. Smallest audited RMP upper `0.5836817975103938`.
21. 최종 certified DW interval `[0.5215744487783405, 0.5836817975103938]`.
22. 요청 material threshold `0.5737116103498322` 유지. Threshold 숫자와 floor certificate는 별도 authority다.
23. DW materiality INCONCLUSIVE. 이번 threshold experiment NOT_RUN; budget 소진 실험으로 포장하지 않았다.
24. Exact CG convergence 인증 안 됨. 기존 pricing optimum들은 실제 negative RC다.
25. 다음 단일 blocker: 원본 frozen arc LP에 대한 lower-bound certificate 확보. 이 gate가 통과한 뒤의 CG 방향은 fixed four-way smoothed Discovery다. 이번 작업에서 pricing formulation redesign/추가 CG/parameter tuning은 하지 않았다.
26. Branch-and-Price NOT_RUN; future gate 변경 없음.
27. May day workers 4/1/4/1, 각각 31일, Threads 1 보존.
28. B2 inner pricing 1 / B3 inner pricing 4 보존.
29. May optimizer / Actual / Fresh AC calls 0/0/0. Production M1/P2/A2/M2 미실행.
30. A1 freeze, 4 MESS, 96 slots, full original route/mode/PCS16/SOC/grid/objective/P2 scientific contract 및 모든 기존 tracked source/artifact bytes 보존. Warm RMP 재시험/worker/RAM/alpha sweep 없음.

요청된 마지막 문구 중 “기존 arc-LP lower bound를 … 사용했다”는 이번 결과에는 적용할 수 없다. 정확한 결과는 다음과 같다.

이번 작업에서는 full-scale feasible-set inclusion을 증명했지만, 기존 scalar의 arc-LP lower-bound authority가 확인되지 않아 D-W root의 independent lower floor로 사용하지 않았다.

Pricing incumbent는 global lower bound로 사용하지 않았으며,
pricing BestBd와 feasible reduced-cost trajectory의 차이는
certification weakness 진단에만 사용했다.

Adaptive dual smoothing은 Discovery에만 사용하고,
column acceptance와 scientific certificate는 true RMP dual authority를 유지하도록 preregister했다. 이번 작업의 새 pricing은 gate 실패로 실행하지 않았다.

Branch-and-Price와 May production은 실행하지 않았다.
