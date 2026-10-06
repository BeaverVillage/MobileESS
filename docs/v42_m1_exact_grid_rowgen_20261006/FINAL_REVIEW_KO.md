# Exact grid row-generation 개발 결과

최종 상태: **NEW_DECOMPOSITION_REJECTED**. NEW_M1_DECOMPOSITION_SELECTED=false.

분류: DIRECT_EXACT_ROW_GENERATION_POSSIBLE. 모든 P/Q/SOC/route/mode/rho는 master에 남는다. Grid-only Benders는 직접 affine 평가가 가능해 불필요·미실행이며 giant recourse는 재도입하지 않았다.
기존 PR157 original worktree100개 evidence의 manifest SHA는 그대로 PASS다. 새 checkout의12개 text evidence는 inherited Git blob의 CRLF/LF 정규화 차이만 있었으며, 원래 byte를 별도 history/PR157_ORIGINAL_WORKTREE_BYTES에 보존했다. 기존 baseline 파일을 수정하지 않았다.

V16.3 May02 Standard BD29→CL-MC-BD7 iterations,71.488→38.376초, 동일 monolithic optimum. Monolithic 자체4.82초였으므로 전체 M1 가속으로 일반화하지 않았다. V42 PR115–1201000–1400초 recourse/Kappa/인증 문제와 PR124 binary감소만으로 runtime 개선을 입증하지 못한 결론을 보존했다. PR157 D-W/Early B&P 원래 증거100개와 모든 inherited Git files는 보존했다.

| Variable category | Columns |
|---|---:|
| A_ROUTE_MOVEMENT_LOCATION | 207,928 |
| B_CHARGE_DISCHARGE_MODE | 384 |
| C_P | 17,884 |
| D_Q | 8,942 |
| E_SOC | 388 |
| F_RHO_OBJECTIVE | 1 |
| G_GRID_ONLY_AUXILIARIES | 81,216 |

| Original row family | Rows | nnz |
|---|---:|---:|
| NormalAmps | 11,520 | 525,887 |
| PCS16 | 143,072 | 518,636 |
| connected_Pch | 8,942 | 17,884 |
| connected_Pdis | 8,942 | 17,884 |
| connected_Qmax | 8,942 | 17,884 |
| connected_Qmin | 8,942 | 17,884 |
| energy_balance | 384 | 217,638 |
| flow | 9,216 | 415,760 |
| initial_SOC | 4 | 4 |
| injection_P_binding | 2,304 | 20,188 |
| injection_Q_binding | 2,304 | 11,246 |
| line_thermal_face | 402,433 | 1,509,121 |
| no_simultaneous_charge | 8,942 | 17,884 |
| no_simultaneous_discharge | 8,942 | 17,884 |
| response_line_P_binding | 25,152 | 121,056 |
| response_line_Q_binding | 25,152 | 121,056 |
| response_line_correction_binding | 25,152 | 1,229,747 |
| response_transformer_P_binding | 576 | 10,656 |
| response_transformer_Q_binding | 576 | 10,656 |
| terminal_SOC | 4 | 4 |
| terminal_location | 4 | 96 |
| transformer_kVA | 110,592 | 80,640 |
| voltage_lower | 36,960 | 1,774,080 |
| voltage_upper | 36,960 | 1,774,080 |

Security grid rows598,465개, affine definition/grid auxiliary81,216개. Native+1 pivot과 acyclic P/Q→injection→response를 확인했다. 제거한 auxiliary0개/0%: sparse factoring을 유지했다.

| Model | Rows | Columns | Binary | Continuous | nnz |
|---|---:|---:|---:|---:|---:|
| Current original | 886,017 | 316,743 | 208,312 | 108,431 | 8,447,855 |
| Initial master | 287,552 | 316,743 | 208,312 | 108,431 | 2,784,047 |

초기 rows감소67.546%, nnz감소67.044%. CSR예상104,918,332→34,558,776byte는 native RSS/factorization 예측이 아니다.

Exactness:12 physical fixtures,1536 exhaustive binary assignments(49 feasible/1487 infeasible) status/optimum 일치. 모든 original row coefficient/sign identity와 <=/>=/=, constant/cancellation/threshold exact-rational fallback, omitted violation 및 final separation 제거 반례 PASS. 회귀52개 PASS. 독립 최종 감사 native solve0회.

동일 frozen current hard May01 M1을 sequential A→B로 비교했다. 두 arm을 합친 연속 wall554.019087초,600초 이내. 각 arm의 최대280초에 build/row insertion을 포함했다. Paper runtime은 측정하지 않았다.

| Metric | A original monolithic | B exact row generation |
|---|---:|---:|
| Initial valid UB | 0.6694159238756877 | 0.6694159238756877 |
| Final valid UB | 0.6694159238756877 | 0.6694159238756877 |
| Initial valid LB | 0.5687115725336208 | 0.5687115725336208 |
| Final valid LB | 0.5687115725336208 | 0.5687115725336208 |
| Initial relative gap | 0.15043614552672033 | 0.15043614552672033 |
| Final relative gap | 0.15043614552672033 | 0.15043614552672033 |
| Gap reduction / wall sec | 0.0 | 0.0 |
| First valid existing integer time | 0.0 | 0.0 |
| First new valid integer sec | None | None |
| First native valid integer sec | 2.9092662000039127 | 1.5112331999989692 |
| Master solves | 1 | 2 |
| Row-generation iterations | 0 | 2 |
| Rows added | 0 | 217098 |
| Final active rows | 886017 | 504650 |
| Native sec | 273.095999956131 | 272.52999997138977 |
| Build-inclusive wall sec | 277.26425180002116 | 276.47627539999667 |
| Peak process RSS bytes | 3230310400 | 2261442560 |
| Peak process commit bytes | 3946516480 | 2790981632 |
| Peak system commit bytes | 25308295168 | 24198918144 |
| Min free RAM bytes | 16654303232 | 17590435840 |

| Memory | A | B |
|---|---:|---:|
| Peak RSS | 3.008 GiB | 2.106 GiB |
| Peak process commit | 3.675 GiB | 2.599 GiB |
| Peak system commit | 23.570 GiB | 22.537 GiB |
| Min free RAM | 15.511 GiB | 16.382 GiB |

RSS감소29.993%, process commit감소29.280%. Native bound는 A0.25295395759592587/B0.5635117196342438로 B가 더 높지만, 둘 다 이미 유효한 시작 floor0.5687115725336208보다 낮아 certified global LB를 개선하지 못했다. 마지막 후보의3,941개 위반은 모두 voltage_upper이며 최대 squared-row violation0.12322020406937549다. 두 제한 solve의 node count는 모두1로, 메모리 감소가 더 빠른 B&B를 가능하게 했다는 증거는 없다.

Rows-added-per-iteration:[213157, 3941]. 마지막 rowgen native 후보 objective0.6548888653197326은 original grid3,941행을 위반해 valid UB로 수락하지 않았다. 그 행들을 모두 추가했지만 wall 예산 종료로 추가 solve를 하지 않았다. Row generation의 scientific convergence=False. 최종 best UB는 양쪽 모두 원래 검증된 Start이며 full unreduced original grid exhaustive separation PASS다. 이는 마지막 개발 후보의 convergence PASS를 의미하지 않는다.

초기 full-domain UB/LB는 동일 과학 모델의 검증된 PR1570.6694159238756877/0.5687115725336208다. Native relaxation-subset bound만 기존1e-8 outward safety로 추가 사용했다. 선택 rate gate=False, matched stronger-bound gate=False; P1accepted=False, global gap.005 유지.

RAM/commit은 read-only 관찰이다. 순차 두 모델은 같은 process/environment를 사용하므로 allocator/cache retention이 RSS에 영향을 줄 수 있다. Memory만으로 선택하거나 production speedup을 주장하지 않았다. RAM/commit/paging 기반 stop/wait/kill/parameter 정책은 없다. Benchmark의 등록된 wall deadline만 자기 child 종료 권한을 가진다.

Critical gamma threshold와 PR124 compact challenger는 미시험. 3600초 canary, full May M campaign, P2, B2/B3는 실행하지 않았다.

Benchmark source commit:7bdd54684ba2af6421a812ee2c54fcd2b8d01525. 최종 commit/Draft PR은 대화 답변에 기록한다.

아래 문장은 알고리즘의 성공적 scientific 종료/수락 조건이다. 이번 bounded 개발 STOP은 그 종료 조건을 달성했다는 주장이 아니다.
본 알고리즘은 일부 grid row로 시작하더라도 종료 전에 모든 원래
grid constraint를 exhaustive separation으로 검사하고 모든 violation을
제거하므로 heuristic feasible-set restriction이 아니다.

Critical-line/multi-row 선택은 계산 순서 가속에만 사용하며,
최종 scientific feasibility와 optimality certificate를 대체하지 않는다.
