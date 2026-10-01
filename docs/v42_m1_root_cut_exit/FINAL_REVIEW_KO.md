# PR107 successor: exact global-bound proof policy

CP0 interrupted partial; CP1 cancelled at user request. Revised policy=PROOF_AUTO; production run=False; M1 accepted=False.

사용자가 수정한 실험은 BestBd(t)/Gap(t) 및 solver certificate를 우선한다. 아래 first non-root time은 부가 관측이며 production 허용 근거가 아니다.

| Run | DegenMoves | Root LP s | Wall s | UB | BestBd | Gap % | Nodes | First non-root s |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| PROOF_AUTO | -1 | 247.38 | 600.190 | 0.6696147314213984 | 0.571849460049452 | 14.600227083478131 | 1.0 | None |
| PROOF_DG0 | 0 | 241.88 | 600.169 | 0.6696147314213984 | 0.571849460049452 | 14.600227083478131 | 1.0 | None |

## 1. PR107에서 Root LP 자체는 해결됐는가?

그렇다. PR107 root relaxation 완료. 전체 root 처리와 다르다.

## 2. Root LP 시간은?

180.04초.

## 3. 전체 root processing은 얼마나 걸렸는가?

약 1787.36초, 미완료. 전체 optimize 1800.243초.

## 4. 왜 POST_LP_ROOT_PROCESSING이 병목인가?

LP 완료 후 node 0에 오래 머물렀으며 final nodes=1, global bound 개선 없음.

## 5. PR107 cut 수는?

Cover 1, MIR 1818, Flow cover 440, BQP 643.

## 6. cut이 final LB를 얼마나 개선했는가?

관측된 final LB 개선은 0. cut별 인과 효과가 0이라는 주장은 아니다.

## 7. 왜 CutPasses를 먼저 시험했는가?

처음에는 bundled root-loop 운영 정책을 비교했지만, 사용자가 목적을 global-bound proof 가속으로 수정해 CP0를 중단했다.

## 8. 왜 individual cut family는 아직 안 건드렸는가?

cut pass에는 heuristics/probing도 포함된다. 단일 family의 원인 분리 증거 없이 비활성화하지 않았다.

## 9. CP0의 root relaxation 시간은?

370.23초; partial diagnostic.

## 10. CP1의 root relaxation 시간은?

사용자 지시로 CP1 미실행. Heuristics=0/MIPFocus=3/CutPasses=AUTO/DegenMoves=AUTO primary로 대체했다.

## 11. CP0는 언제 첫 branch를 했는가?

None; 558.7053912999982초에 사용자 중단, non-root 미관측은 censored.

## 12. CP1은 언제 첫 branch를 했는가?

사용자 지시로 CP1 미실행. Heuristics=0/MIPFocus=3/CutPasses=AUTO/DegenMoves=AUTO primary로 대체했다.

## 13. CP0의 300초 node 수는?

{"where": "MIP", "incumbent": 0.6696147314213984, "bound": 0.28222432055490354, "nodes": 0.0, "iterations": 0.0, "cuts": 0, "relative_gap": 0.578527312331043, "reached": true, "seconds": 300, "observation_seconds": 24.239700200007064, "observation_age_seconds": 275.76029979999294, "carried_forward": true}

## 14. CP1의 300초 node 수는?

사용자 지시로 CP1 미실행. Heuristics=0/MIPFocus=3/CutPasses=AUTO/DegenMoves=AUTO primary로 대체했다.

## 15. CP0의 600초 node 수는?

600초에 도달하지 않았다. 558.705초 interrupted final NodeCount=1 (root 포함).

## 16. CP1의 600초 node 수는?

사용자 지시로 CP1 미실행. Heuristics=0/MIPFocus=3/CutPasses=AUTO/DegenMoves=AUTO primary로 대체했다.

## 17. CP0 300초 LB/gap은?

{"where": "MIP", "incumbent": 0.6696147314213984, "bound": 0.28222432055490354, "nodes": 0.0, "iterations": 0.0, "cuts": 0, "relative_gap": 0.578527312331043, "reached": true, "seconds": 300, "observation_seconds": 24.239700200007064, "observation_age_seconds": 275.76029979999294, "carried_forward": true}

## 18. CP1 300초 LB/gap은?

사용자 지시로 CP1 미실행. Heuristics=0/MIPFocus=3/CutPasses=AUTO/DegenMoves=AUTO primary로 대체했다.

## 19. CP0 600초 LB/gap은?

600초 checkpoint 없음. interrupted final LB=0.5718494710510547, gap=0.1460022544050313.

## 20. CP1 600초 LB/gap은?

사용자 지시로 CP1 미실행. Heuristics=0/MIPFocus=3/CutPasses=AUTO/DegenMoves=AUTO primary로 대체했다.

## 21. 어느 CutPasses를 선택했는가?

CutPasses=AUTO 고정; selected=PROOF_AUTO, Heuristics=0, MIPFocus=3, DegenMoves=-1.

## 22. 선택 기준은 무엇인가?

solver-certified P1 quality, higher final BestBd, lower Gap, work/wall; first branch and node count are descriptive; gates={'PROOF_AUTO': {'PASS': False, 'solver_certified_P1_quality': False, 'global_bound_gain': -1.1001602628901708e-08, 'bound_gain_threshold': 0.0001, 'first_branch_not_authorization_basis': True, 'primal_heuristic_improvement_not_authorization_basis': True}, 'PROOF_DG0': {'PASS': False, 'solver_certified_P1_quality': False, 'global_bound_gain': -1.1001602628901708e-08, 'bound_gain_threshold': 0.0001, 'first_branch_not_authorization_basis': True, 'primal_heuristic_improvement_not_authorization_basis': True}}.

## 23. Heuristics=0 isolation을 실행했는가?

기존 CP0_H0 isolation은 미실행. 새 primary Heuristics=0은 complete isolation이 아니다.

## 24. 실행했다면 무엇을 보여줬는가?

DG0 diagnostic run=True. 새 primary/conditional의 BestBd(t), Gap(t)는 PROOF_CANARY_COMPARISON.csv 참조. probing/기타 root 처리는 분리하지 않았다.

## 25. production run이 authorized됐는가?

False; branch 또는 primal 개선만으로 허용하지 않았다.

## 26. production first branch time은?

None; secondary descriptive metric.

## 27. production에서 몇 node까지 갔는가?

None

## 28. first incumbent는?

0.06900749998749234초; validated PR107 MIP start accepted=True; source=PROOF_AUTO.

## 29. UB는?

0.6696147314213984; diagnostic only

## 30. LB는?

0.571849460049452; diagnostic only

## 31. final P1 gap은?

14.600227083478131%; diagnostic only

## 32. 0.5% 달성했는가?

production certified P1=False; diagnostic certificate=False.

## 33. PR107 14.6002% 대비 얼마나 개선됐는가?

-1.642975000493152e-06 percentage points; source=PROOF_AUTO. Bound gain=-1.1001602628901708e-08.

## 34. P2를 실행했는가?

production passes=0; P2 complete=False.

## 35. movement energy는?

0 kWh; incumbent metric, P2 certificate=False

## 36. movement count는?

0; incumbent metric, P2 certificate=False

## 37. M1 accepted인가?

False

## 38. physical validation은 PASS인가?

True

## 39. robust voltage는 PASS인가?

True; min/max=0.9549999999996363/1.0449999999997646.

## 40. node83.2 slot79는?

1.0407128548060747 pu.

## 41. Q saturation은?

{"connected_count": 384, "connected_fraction": 1.0, "Q_active_epsilon_kvar": 1e-06, "Q_active_fraction": 1.0, "median_utilization": 0.9807852804032396, "P95_utilization": 0.9807852804032413, "max_utilization": 0.9807852804032435, "near_cap_threshold": 0.95, "near_cap_fraction": 0.6067708333333334, "formula": "abs(Q)/sqrt(max(S_nameplate^2-P_net^2,0)), connected unit/time only", "diagnostic_only": true, "production_PCS_faces": 16, "Q_penalty": false}; accepted M1 metric=False.

## 42. formulation을 변경했는가?

변경 없음. inherited F3 builder/native physics byte와 fingerprint/size가 동일하다.

## 43. route domain을 변경했는가?

변경 없음. complete domain SHA 및 route constructor 보존.

## 44. SOC/PCS를 변경했는가?

변경 없음. 개별 SOC/terminal equality/PCS inner16 400-kVA 보존.

## 45. voltage margin을 변경했는가?

변경 없음. M1 0.955–1.045.

## 46. A1을 다시 돌렸는가?

A1 optimize 0회. accepted anchor/handoff/known1499/CC4/Runtime 그대로 재사용.

## 47. Actual P/Q repair를 다시 켰는가?

Actual P/Q correction 및 local repair OFF.

## 48. 현재 남은 병목은?

POST_LP_ROOT_PROCESSING_WITH_INSUFFICIENT_GLOBAL_BOUND_GAIN

## 49. 다음 exact computational action은 무엇인가?

Retain the full F3/domain/physics; in a future task measure and investigate exact global-bound progress, LP reoptimization and unresolved root work. Do not use primal heuristic improvements or earlier branching as scientific acceptance. Do not attribute a bundled-policy result to an individual internal routine.

## 50. A2를 왜 실행하거나 실행하지 않았는가?

명시적으로 금지된 후속 단계이므로 실행하지 않았다. P1의 solver-certified gap 및 독립 물리 검증, inherited P2 acceptance를 충족해야 full M1 accepted이다.
