# V42 M-stage exact completion 검토

최종 중단 상태: **M1_ROOT_NOT_CONVERGED**. Root 미수렴이므로 B&P, P2, fresh M1/M2 canary 및 May B2/B3/L1–L4 production은 실행하지 않았다.

| 항목 | 결과 |
|---|---|
| Hybrid global optimum 동등성 | 증명 실패; 네 MESS 모두 점검 |
| Hybrid/Gurobi 속도 | 인증 실패로 INCONCLUSIVE; 20% 개선 주장 없음 |
| 선택 pricing backend | ORIGINAL_GUROBI_EXACT |
| 신규 root Discovery rounds | 15 |
| 신규 RMP / pricing calls | 15 / 64 |
| 최종 retained pool | 1841 |
| Exact root LP objective | 미확정 |
| 최저 audited restricted LP upper | 0.5729695797088222 |
| Certified LB | 0.5687115725336208 |
| Exact root CG convergence | false |
| Materiality | PROVEN_NONMATERIAL |
| 신규 root development native interval union | 1010.135999초 / 1800초 |
| 신규 root 모델별 native 시간 합계 | 1607.627604초 |
| 기존 development native union | 2122.716214초 |
| 기존 + 신규 development native union | 3132.852213초 |
| Root constructor build-only | 미복원 |
| 첫 native optimize 전 준비/복원/감사 | 49.87632549999398초 (telemetry epoch 기준) |
| Root build/audit/solve 전체 경과 | 2332.898541초 |
| B&P nodes / incumbent / global LB / gap | 0 / 미실행 / 미실행 / 미실행 |
| M1 P1 / P2 movement energy / count | 미수락 / 미실행 / 미실행 |
| M1 development acceptance | false |
| Fresh M1 runtime / status | 0초 / NOT_RUN_PREREQUISITE |
| A2 prerequisite / current M2 formulation | 미평가 / 미평가 |
| M2 runtime / status | 0초 / NOT_RUN_PREREQUISITE |
| 최저 가용 RAM | 4.229 GiB |
| 최고 commit | 52.903% |
| 최고 작업 트리 RSS | 15.819 GiB |
| 회귀검증 | REGRESSION_TESTS.log 및 REGRESSION_RECEIPT.json 참조 |

원래 MESS01 Gurobi pricing은 완료된 log/point를 복구했으며 재실행하지 않았다. Hybrid의 RAW_PI_SIGN_INVALID 검증 실패를 보존하고, 사용자 중단 이후 나머지 세 MESS만 비교했다. Benchmark 두 실행 구간의 active wall 합계는 209.892335초이다. 사용자 중단을 포함한 시간을 단일 continuous wall 성능 결과로 주장하지 않았다. 동등성과 속도 개선이 입증되지 않아 기존 pricing backend의 reject/freeze 결정을 그대로 유지했다.

1800초 신규 root grant는 역사적 예산과 분리했다. 병렬 pricing의 예산은 PR152와 동일한 optimize interval union으로 집계했으며, 모델별 native 합계도 별도 공개한다. Build/audit/wait는 production runtime으로 바꾸어 보고하지 않는다. 중단 사유는 EXACT_RMP_DUAL_SIGN_REJECTED이다. 예산 소진으로 종료한 것이 아니며 exact dual 부호 검증 실패로 중단했다. 마지막 RMP optimize의 start/end interval은 종료 과정에서 저장되지 않았으므로, 실제 측정된 durable budget journal debit을 사용하고 구간을 만들어 내지 않았다. RMP upper는 fractional restricted-master 상한이며, 정수 M1 incumbent acceptance가 아니다. Build-only 시간은 실패 시 보존되지 않아 초기 pool/audit 복원 wall을 별도 표기한 측정 한계가 있다.

PR152의 1,604-column checkpoint는 M1 알고리즘 개발 및 exact root completion에만 사용했으며, 논문용 fresh M1 runtime 측정에는 development checkpoint에서 학습된 column을 주입하지 않았다.

Hybrid DP-LP pricing은 full original pricing problem과 global optimum equivalence가 증명된 경우에만 exact pricing backend로 채택했다. 이번 실행은 증명 실패로 미채택이다.

Root CG는 모든 pricing subproblem의 exact nonnegative reduced-cost certificate가 확보된 경우에만 converged로 판정했다. 이번 실행의 converged 판정은 false이다.

Branch-and-Price는 exact node pricing과 valid global bounds를 유지했으며, 휴리스틱 incumbent만으로 node 또는 M1을 acceptance하지 않았다. 이번 task에서는 root 선행조건 실패로 B&P를 실행하지 않았으므로 실제 B&P 검증 완료를 주장하지 않는다.

최종 M1/M2 production-style canary는 각각 3600초 stage budget을 초과하지 않았으며, 시간 초과 시 자동 완화나 추가 예산 없이 FAIL로 종료했다. 이번 task에서는 canary가 선행조건 실패로 미실행이므로 PASS/FAIL_TIME_LIMIT 실행 결과를 주장하지 않는다.

Commit/Draft PR는 PUBLICATION_RECEIPT.json에 기록한다. PR152/PR154 history를 수정하지 않고 새 child branch에서만 변경했다.
