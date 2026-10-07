# May19 residual-directed + migration-inclusive Phase-I

최종 판정: **PHASE1_TRACTABILITY_FAIL**. 과학적 상태 **INCONCLUSIVE**. Phi=0 도달: **False**.
중단 사유: `PHASE1_DOMAIN_EXPANSION_TOO_LARGE`.

PR176 exact base `1b34350663b972aeeaeb3a1c20596cbc0dd34b65`에서 새 Draft PR로 적층한다. 실행 source HEAD `12c30cfb66c6a0c4d0a07518a24ea6d0647c538c`. 최종 게시 HEAD/URL은 GitHub PR 본문과 외부 `FINAL_PUBLICATION_RECEIPT.json`에 기록한다. 실행 source archive와 실제 모델·raw 데이터 SHA는 `SOURCE_FREEZE.json`, `SHA256_MANIFEST.json`에 보존한다.

May19 한 번, cumulative 1200초, Threads=1/native, pricing worker 4개. 모든 이전 48개 활성화와 전체 scientific candidate domain을 보존했다. 물리식·Runtime·CC4·GPU·WAN·grid·허용오차·목적함수·Phi weight 변경은 0건이다. P1·다른 날짜·full A1·Planning/Actual/Fresh AC·production 실행은 0건이다. 150/150 closure를 주장하지 않는다.

초기 새 최적 Phi: `0.006627342398282464`. 마지막 인증된 Phi: `0.006627342398282464`.
저장된 이전 PR176 R2 최적점은 먼저 별도로 분해했다. 이전 최적점을 마지막 expanded 모델의 최적점이라고 부르지 않았으며, 새 initial master를 따로 풀었다. 모든 master에 이전 feasible point의 inclusion witness PASS가 있다. Raw Phi 증가가 있어도 feasible 이전 동일-Phi point가 보존되면 실제 악화로 해석하지 않는다. 이 실험의 1% materiality gate에는 raw before/after 값을 그대로 사용한다.

| Master | Native status | Raw Phi | Exact Phi | Zero |
|---|---:|---:|---|---|
| R0 | 2.0 | 0.0066273423982824639 | `244505778219922191/36893488147419103232` | False |

| Batch | STAY | Migration | Size | Phi before | Phi after | Relative reduction | Re-solved |
|---|---:|---:|---:|---:|---:|---:|---|
| 0 | 32 | 32 | 64 | 0.006627342398282464 | None | None | False |

확정 activation rounds: 0. 실제 활성화 STAY 0, migration 0. Batch는 completed targeted migration 조회와 bounded physical recovery 후에만 선택했다. 최대64, migration 최대32; 검증된 migration이 남는 동안 STAY 최대32. 정확한 class+coupling 효과를 deduplicate하고 residual score→exact rc→identity로 결정한다.

이번 batch가 확정되지 않은 경우 before/after Phi 감소율은 미측정이다. 선택한 후보 수를 활성화 수로 보고하거나 NONMATERIAL로 해석하지 않는다.

조회한 unique classes 24; 완료된 STAY native queries 24, migration native queries 16; concrete recovery 완료 class-rounds 24.
Migration이 없는 8개 class도 조회를 생략 처리하지 않고 complete physical domain의 no-migration support를 별도로 기록했다. Migration native queries의 algebraic full-domain coverage는 physical paths 13,912,566, compact blocks 238,568이다. 이것은 그 경로들을 개별 열로 전수 enumerate했다는 뜻이 아니다. Class별 값은 `TARGETED_CLASS_SUMMARY.csv`에 있다.
독립 검증된 negative concrete STAY 96, migration 32. Unmaterialized negative-query directions 0. Quota 밖의 미회수 physical negative block 전수 개수는 UNKNOWN이다.
Compact physical recovery: blocks examined 15, paths evaluated 84, exact reusable tail terms 1740, exact nonnegative block pruning 0, covered physical paths by exact pruning 0. Native-point-supported physical migration paths additionally examined 17.

각 migration-capable target class의 full compact MIGRATION-only LP(q-sum=N)를 STAY-only LP(q-sum=0)보다 먼저 풀었다. 임시 조회 제약은 scientific model을 변경하거나 후보를 삭제하지 않는다. Native query의 물리 경로 전체 coverage와 bounded concrete recovery의 개별 경로 검사 수를 구분한다. Class당 최대4 STAY·2 migration recovery는 수집 quota이며 domain closure가 아니다. Unmaterialized 값은 음수 인증 bound가 있지만 물리 concrete witness를 회수하지 못한 query 방향 수다. 모든 물리 음수 block의 전수 개수는 미측정이다. Quota 밖의 negative directions도 삭제하지 않는다.

잔차 분해 기준 Phi `244505778219922191/36893488147419103232` (새 initial optimal R0). Signed raw artificial contribution을 그대로 합산했다. Positive weighted sum `244510455850742063/36893488147419103232`; negative roundoff offset `-146175963121/1152921504606846976`. Raw clipping/rounding/weight 수정은 없다.

| Original row family | Exact weighted Phi | Float |
|---|---|---:|
| voltage_upper | `244505778219922191/36893488147419103232` | 0.0066273423982824639 |

| Time slot | Weighted Phi |
|---|---:|
| 25 | -6.339370928968701e-08 |
| 26 | 0.00013198519904997243 |
| 27 | -6.3393728135072332e-08 |
| 28 | 0.0015363765706594588 |
| 29 | 6.3393732694792988e-08 |
| 30 | 0.0040027426482496502 |
| 31 | 6.3393763561540948e-08 |
| 32 | 0.00023185590269479814 |
| 33 | 0.00072438207756975312 |

| Site/node grouping | Weighted Phi |
|---|---:|
| BUS_83 | 0.0033139565662260798 |
| MESS_STA12 | 0.0033133858320563846 |

| Phi concentration | Minimum rows | Cumulative positive share |
|---|---:|---:|
| 50% | 2 | 60.397402272% |
| 80% | 4 | 83.579795430% |
| 90% | 6 | 94.509999938% |

| Top original row | Time | Node | Weighted artificial | Cumulative share |
|---|---:|---|---:|---:|
| 60407 | 30 | 83.2 | 0.0020014030785397486 | 30.199180279% |
| 60697 | 30 | mess_sta12_pcc.2 | 0.0020013395697099016 | 60.397402272% |
| 46511 | 28 | 83.2 | 0.00076822000428815318 | 71.989077458% |
| 46801 | 28 | mess_sta12_pcc.2 | 0.00076815656637130563 | 83.579795430% |
| 81251 | 33 | 83.2 | 0.00036222274607770498 | 89.045376115% |
| 81541 | 33 | mess_sta12_pcc.2 | 0.00036215933149204814 | 94.509999938% |
| 74303 | 32 | 83.2 | 0.0001159596515450492 | 96.259715654% |
| 74593 | 32 | mess_sta12_pcc.2 | 0.00011589625114974894 | 98.008474722% |
| 32615 | 26 | 83.2 | 6.6024298279167577e-05 | 99.004715663% |
| 32905 | 26 | mess_sta12_pcc.2 | 6.5960900770804855e-05 | 99.999999999% |
| 67355 | 31 | 83.2 | 6.3393763561540948e-08 | 100.000956548% |
| 53459 | 29 | 83.2 | 6.3393732694792988e-08 | 100.001913096% |
| 25957 | 25 | mess_sta12_pcc.2 | -6.339370928968701e-08 | 100.001913096% |
| 39853 | 27 | mess_sta12_pcc.2 | -6.3393728135072332e-08 | 100.001913096% |

GPU/Runtime/WAN/CC4/grid별 직접 artificial attribution: `{'GRID': '244505778219922191/36893488147419103232'}`. GPU/Runtime/WAN/CC4 직접 row-family artificial contribution은 각각0이며, 모두 GRID에 속한다. 해당 전압 행은 공유 global grid 행이므로 workload class/AIDC별 독점적 인과 Phi 배분은 식별되지 않는다. 정확한 node/site mapping과 원래 resource-binding 계수로 계산한 heuristic influence를 별도 보고한다. `RESIDUAL_ATTRIBUTION.json`의 모든150개 class 순위와 target IDs, `RESIDUAL_ROWS.csv`, `TARGETED_CLASS_AUDIT.json`에 세부 근거가 있다. Influence는 순위에만 쓰며, admissibility는 original physical membership/local primal/coupling/exact rc<-1e-8의 독립 PASS에만 따른다.

최종 original active 모델 rows/cols/nnz: 713,288 / 83,863 / 13,756,154.
Master 및 pricing의 실제 rows/cols/nnz·factor·RSS는 `ACTUAL_NATIVE_MODEL_SIZE_TRACE.csv`, master auxiliary sizes는 `MODEL_SIZE_TRACE.csv`에 있다. 최대 factor nnz 16,100,000.0; 최대 factor memory 0.4 GB.
Native calls 41; 모든 native Runtime 합 123.965000s; Work 합 304.407473602811. 실행 wall 247.644080s; 누적 accounting 247.644082s; 1200초 초과 persistence/cleanup 0.000000s. Budget reset/sweep/automatic extension 없음. Static reconstruction/qualification과 종료 후 read-only audit는 실행 budget 밖이며 native optimize를 하지 않았다.

검증: synthetic tests173 PASS, tiny1/4-worker raw X/Pi/RC/Slack·exact certificates 동일. 실제 raw native audit 41, query certificates 재계산 40, active normalization potentials 재계산 24, concrete 후보 재검증 128. `VERIFICATION.json` PASS. Frozen original matrix/weights와 sequential activation 재구성, 이전 point inclusion, 모든 source archive bytes를 검증했다.

1200초/engineering 제한 내 materiality 판단을 완료하지 못했다. 전체 scientific domain infeasibility 증명이나 NONMATERIAL 결론으로 해석하지 않는다. 추가 실행 없이 중단했다.

확정하지 않은64-column batch의 independently reconstructed original 모델은 rows/cols/nnz 1,046,444/362,044/14,820,623이다. 64개 concrete class column은 원래 native primitive/lane 모델로 확장되므로 native 변수64개 증가와 같지 않다. Native 열 증가 278,181은 구현에서 사전 고정한100,000 증가 제한을, 전체 362,044열은200,000 active 열 제한을 넘는다. 두 제한 모두 초과했다. Factor 제한이나1200초 소진으로 중단한 것이 아니다. 이 모델에 native solve를 하지 않았으며 factor memory와 실제 solve 가능성은 미측정이다. 이전 R0 optimal point의 동일-Phi inclusion witness는 이 미확정 모델에서도 PASS이다. `UNCOMMITTED_BATCH_AUDIT.json`에 근거를 보존했다.
